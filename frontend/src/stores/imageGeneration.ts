import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { useAuthStore } from './auth'
import imageGenerationService, {
  type ImageGenerationRequest,
  type GeneratedImage,
  type ImageGenerationResponse,
  type ImageModel,
  type ImageGenerationStats,
  ImageGenerationError,
  ValidationError
} from '@/api/imageGenerationService'
import imageFoldersService, {
  type ImageFolder,
  type CreateFolderRequest,
  type UpdateFolderRequest
} from '@/api/imageFoldersService'

// Generation state types
type GenerationStatus = 'idle' | 'validating' | 'generating' | 'uploading' | 'completed' | 'failed'

interface GenerationProgress {
  status: GenerationStatus
  message: string
  progress: number // 0-100
  estimatedTimeRemaining?: number
}

interface GenerationState {
  isGenerating: boolean
  currentRequest?: ImageGenerationRequest
  progress: GenerationProgress
  result?: ImageGenerationResponse
  error?: string
}

interface GalleryState {
  images: GeneratedImage[]
  loading: boolean
  error?: string
  pagination: {
    page: number
    limit: number
    total: number
    hasMore: boolean
  }
  lastFetch: number
}

interface ModelsState {
  models: ImageModel[]
  loading: boolean
  error?: string
  selectedModel?: string
  lastFetch: number
}

interface FoldersState {
  folders: ImageFolder[]
  selectedFolderId: string | null // null = "All Images"
  loading: boolean
  error?: string
  lastFetch: number
}

export const useImageGenerationStore = defineStore('imageGeneration', () => {
  const authStore = useAuthStore()

  // State
  const generation = ref<GenerationState>({
    isGenerating: false,
    progress: {
      status: 'idle',
      message: '',
      progress: 0
    }
  })

  const gallery = ref<GalleryState>({
    images: [],
    loading: false,
    pagination: {
      page: 1,
      limit: 20,
      total: 0,
      hasMore: false
    },
    lastFetch: 0
  })

  const models = ref<ModelsState>({
    models: [],
    loading: false,
    lastFetch: 0
  })

  const stats = ref<ImageGenerationStats | null>(null)
  const statsLoading = ref(false)

  const folders = ref<FoldersState>({
    folders: [],
    selectedFolderId: null, // null = "All Images"
    loading: false,
    lastFetch: 0
  })

  // Computed properties
  const isAuthenticated = computed(() => authStore.isAuthenticated)
  
  const canGenerate = computed(() => {
    return isAuthenticated.value
  })

  const selectedModel = computed(() => {
    if (models.value.selectedModel) {
      return models.value.models.find(m => m.id === models.value.selectedModel)
    }
    return models.value.models[0] // Default to first model
  })

  const recentImages = computed(() => {
    return gallery.value.images.slice(0, 6) // Last 6 images
  })

  const totalGenerations = computed(() => {
    return stats.value?.total_generations || gallery.value.pagination.total
  })

  // Actions

  /**
   * Generate a new image from text prompt
   */
  const generateImage = async (request: ImageGenerationRequest): Promise<GeneratedImage | null> => {
    if (!canGenerate.value) {
      throw new Error('Not ready to generate image')
    }

    try {
      // Reset state
      generation.value = {
        isGenerating: true,
        currentRequest: request,
        progress: {
          status: 'validating',
          message: 'Validating request...',
          progress: 10
        }
      }

      updateProgress('generating', 'Starting image generation...', 30)
      const response = await imageGenerationService.generateImage(request)
      
      generation.value.result = response
      
      // Poll for completion if needed
      if (response.status === 'pending' || response.status === 'processing') {
        await pollGenerationStatus(response.id)
      } else {
        updateProgress('completed', 'Image generated successfully!', 100)
      }

      await fetchGallery(true)

      // Return the completed image
      const completedImage = gallery.value.images.find(img => img.id === response.id)
      return completedImage || null

    } catch (error) {
      console.error('Image generation failed:', error)
      
      const errorMessage = imageGenerationService.getErrorMessage(error)
      generation.value.progress = {
        status: 'failed',
        message: errorMessage,
        progress: 0
      }
      generation.value.error = errorMessage
      
      throw error
    } finally {
      generation.value.isGenerating = false
    }
  }

  /**
   * Poll generation status until completion
   */
  const pollGenerationStatus = async (imageId: string): Promise<void> => {
    const maxAttempts = 60 // 5 minutes max (5s intervals)
    let attempts = 0
    
    while (attempts < maxAttempts) {
      try {
        await new Promise(resolve => setTimeout(resolve, 5000)) // Wait 5 seconds
        
        const image = await imageGenerationService.getGeneration(imageId)
        attempts++
        
        const progress = Math.min(30 + (attempts / maxAttempts) * 60, 90)
        
        if (image.status === 'completed') {
          updateProgress('completed', 'Image generated successfully!', 100)
          return
        } else if (image.status === 'failed') {
          throw new ImageGenerationError('Image generation failed')
        } else {
          updateProgress('generating', `Generating image... (${attempts}/${maxAttempts})`, progress)
        }
      } catch (error) {
        if (attempts >= maxAttempts) {
          throw new ImageGenerationError('Generation timeout - please check your gallery')
        }
        // Continue polling on errors (might be temporary)
      }
    }
    
    throw new ImageGenerationError('Generation timeout - please check your gallery')
  }

  /**
   * Update generation progress
   */
  const updateProgress = (status: GenerationStatus, message: string, progress: number) => {
    generation.value.progress = {
      status,
      message,
      progress: Math.max(0, Math.min(100, progress))
    }
  }

  /**
   * Fetch user's generated images
   */
  const fetchGallery = async (force = false, page = 1): Promise<void> => {
    if (!isAuthenticated.value) return

    // Avoid too frequent requests (cache for 30 seconds)
    const now = Date.now()
    if (!force && page === 1 && now - gallery.value.lastFetch < 30000) {
      return
    }

    try {
      gallery.value.loading = true
      gallery.value.error = undefined

      const response = await imageGenerationService.getUserGenerations(
        page,
        gallery.value.pagination.limit,
        folders.value.selectedFolderId || undefined
      )

      // Don't automatically refresh all URLs on load - only refresh on-demand when images are actually used
      // This prevents N+1 query problem (individual API calls for each image)
      // With lazy loading, URLs will be refreshed automatically when:
      // 1. User clicks to view/use an image (on-demand refresh)
      // 2. Image load error occurs (error handler will refresh)
      // This saves 20+ API calls on initial page load!

      if (page === 1) {
        gallery.value.images = response.images
      } else {
        gallery.value.images.push(...response.images)
      }
      
      gallery.value.pagination = {
        page: response.page,
        limit: response.limit,
        total: response.total,
        hasMore: response.has_more
      }
      
      gallery.value.lastFetch = now

    } catch (error) {
      console.error('Failed to fetch gallery:', error)
      gallery.value.error = imageGenerationService.getErrorMessage(error)
    } finally {
      gallery.value.loading = false
    }
  }

  /**
   * Load more images (pagination)
   */
  const loadMoreImages = async (): Promise<void> => {
    if (!gallery.value.pagination.hasMore || gallery.value.loading) return
    
    await fetchGallery(false, gallery.value.pagination.page + 1)
  }

  /**
   * Refresh a specific image's URLs
   */
  const refreshImageUrls = async (imageId: string): Promise<void> => {
    try {
      const refreshedUrls = await imageGenerationService.refreshImageUrls(imageId)

      // Update the image in gallery
      const imageIndex = gallery.value.images.findIndex(img => img.id === imageId)
      if (imageIndex !== -1) {
        gallery.value.images[imageIndex] = {
          ...gallery.value.images[imageIndex],
          signed_url: refreshedUrls.signed_url,
          thumbnail_signed_url: refreshedUrls.thumbnail_signed_url
        }
      }
    } catch (error) {
      console.error('Failed to refresh image URLs:', error)
      throw error
    }
  }

  /**
   * Batch refresh URLs for gallery images that may be expired
   */
  const batchRefreshGalleryUrls = async (): Promise<void> => {
    try {
      // Refresh URLs for images in gallery
      const refreshedImages = await imageGenerationService.batchRefreshUrls(gallery.value.images)

      // Update gallery with refreshed URLs
      gallery.value.images = refreshedImages
    } catch (error) {
      console.error('Failed to batch refresh gallery URLs:', error)
      // Don't throw - gallery should still be usable even if refresh fails
    }
  }

  /**
   * Delete a generated image
   */
  const deleteImage = async (imageId: string): Promise<void> => {
    try {
      await imageGenerationService.deleteGeneration(imageId)
      
      // Remove from gallery
      gallery.value.images = gallery.value.images.filter(img => img.id !== imageId)
      gallery.value.pagination.total = Math.max(0, gallery.value.pagination.total - 1)
      
      // Refresh stats
      await fetchStats(true)
      
    } catch (error) {
      console.error('Failed to delete image:', error)
      throw error
    }
  }

  /**
   * Download an image
   */
  const downloadImage = async (image: GeneratedImage): Promise<void> => {
    try {
      await imageGenerationService.downloadImage(image)
    } catch (error) {
      console.error('Failed to download image:', error)
      throw error
    }
  }

  /**
   * Upload images from user's computer
   */
  const uploadImages = async (files: File[]): Promise<{
    success: boolean
    message: string
    images: GeneratedImage[]
    total_uploaded: number
  }> => {
    try {
      const result = await imageGenerationService.uploadImages(files)

      // Add uploaded images to gallery
      if (result.success && result.images.length > 0) {
        gallery.value.images.unshift(...result.images)
        gallery.value.pagination.total += result.images.length
      }

      return result
    } catch (error) {
      console.error('Failed to upload images:', error)
      throw error
    }
  }

  /**
   * Fetch available models
   */
  const fetchModels = async (force = false): Promise<void> => {
    // Avoid too frequent requests (cache for 5 minutes)
    const now = Date.now()
    if (!force && now - models.value.lastFetch < 300000) {
      return
    }

    try {
      models.value.loading = true
      models.value.error = undefined

      const modelList = await imageGenerationService.getAvailableModels()
      models.value.models = modelList
      models.value.lastFetch = now

      // Set default model if none selected
      if (!models.value.selectedModel && modelList.length > 0) {
        models.value.selectedModel = modelList[0].id
      }

    } catch (error) {
      console.error('Failed to fetch models:', error)
      models.value.error = imageGenerationService.getErrorMessage(error)
    } finally {
      models.value.loading = false
    }
  }

  /**
   * Select a model for generation
   */
  const selectModel = (modelId: string): void => {
    const model = models.value.models.find(m => m.id === modelId)
    if (model) {
      models.value.selectedModel = modelId
    }
  }

  /**
   * Fetch generation statistics
   */
  const fetchStats = async (force = false): Promise<void> => {
    if (!isAuthenticated.value) return

    try {
      statsLoading.value = true
      const statistics = await imageGenerationService.getGenerationStats()
      stats.value = statistics
    } catch (error) {
      console.error('Failed to fetch stats:', error)
    } finally {
      statsLoading.value = false
    }
  }

  /**
   * Reset generation state
   */
  const resetGeneration = (): void => {
    generation.value = {
      isGenerating: false,
      progress: {
        status: 'idle',
        message: '',
        progress: 0
      }
    }
  }

  /**
   * Fetch user's folders
   */
  const fetchFolders = async (force = false): Promise<void> => {
    if (!isAuthenticated.value) return

    // Avoid too frequent requests (cache for 30 seconds)
    const now = Date.now()
    if (!force && now - folders.value.lastFetch < 30000) {
      return
    }

    try {
      folders.value.loading = true
      folders.value.error = undefined

      const response = await imageFoldersService.listFolders()
      folders.value.folders = response.folders
      folders.value.lastFetch = now

    } catch (error) {
      console.error('Failed to fetch folders:', error)
      folders.value.error = 'Failed to load folders'
    } finally {
      folders.value.loading = false
    }
  }

  /**
   * Create a new folder
   */
  const createFolder = async (data: CreateFolderRequest): Promise<ImageFolder> => {
    try {
      const folder = await imageFoldersService.createFolder(data)

      // Add to local state
      folders.value.folders.push(folder)

      // Invalidate cache
      folders.value.lastFetch = 0

      return folder
    } catch (error) {
      console.error('Failed to create folder:', error)
      throw error
    }
  }

  /**
   * Update a folder (rename, change color, reorder)
   */
  const updateFolder = async (folderId: string, data: UpdateFolderRequest): Promise<ImageFolder> => {
    try {
      const updatedFolder = await imageFoldersService.updateFolder(folderId, data)

      // Update in local state
      const index = folders.value.folders.findIndex(f => f.id === folderId)
      if (index !== -1) {
        folders.value.folders[index] = updatedFolder
      }

      // Invalidate cache
      folders.value.lastFetch = 0

      return updatedFolder
    } catch (error) {
      console.error('Failed to update folder:', error)
      throw error
    }
  }

  /**
   * Delete a folder
   */
  const deleteFolder = async (folderId: string): Promise<void> => {
    try {
      await imageFoldersService.deleteFolder(folderId)

      // Remove from local state
      folders.value.folders = folders.value.folders.filter(f => f.id !== folderId)

      // If deleted folder was selected, switch to "All Images"
      if (folders.value.selectedFolderId === folderId) {
        folders.value.selectedFolderId = null
      }

      // Invalidate cache and refresh gallery
      folders.value.lastFetch = 0
      await fetchGallery(true)

    } catch (error) {
      console.error('Failed to delete folder:', error)
      throw error
    }
  }

  /**
   * Move an image to a folder
   */
  const moveImageToFolder = async (imageId: string, folderId: string | null): Promise<void> => {
    try {
      await imageFoldersService.moveImageToFolder(imageId, folderId)

      // Update image in local state
      const image = gallery.value.images.find(img => img.id === imageId)
      if (image) {
        image.folder_id = folderId || undefined
      }

      // Invalidate folders cache to refresh counts
      folders.value.lastFetch = 0
      await fetchFolders(true)

      // If we're viewing a specific folder, refresh gallery to update view
      if (folders.value.selectedFolderId) {
        await fetchGallery(true)
      }

    } catch (error) {
      console.error('Failed to move image to folder:', error)
      throw error
    }
  }

  /**
   * Move multiple images to a folder
   */
  const moveImagesToFolder = async (imageIds: string[], folderId: string | null): Promise<void> => {
    try {
      await imageFoldersService.bulkMoveImages(imageIds, folderId)

      // Update images in local state
      for (const imageId of imageIds) {
        const image = gallery.value.images.find(img => img.id === imageId)
        if (image) {
          image.folder_id = folderId || undefined
        }
      }

      // Invalidate folders cache to refresh counts
      folders.value.lastFetch = 0
      await fetchFolders(true)

      // If we're viewing a specific folder, refresh gallery to update view
      if (folders.value.selectedFolderId) {
        await fetchGallery(true)
      }

    } catch (error) {
      console.error('Failed to move images to folder:', error)
      throw error
    }
  }

  /**
   * Select a folder to filter gallery
   */
  const setSelectedFolder = (folderId: string | null): void => {
    folders.value.selectedFolderId = folderId
    // Reset pagination and fetch gallery for selected folder
    gallery.value.pagination.page = 1
    fetchGallery(true)
  }

  /**
   * Get uncategorized image count
   */
  const getUncategorizedCount = computed(() => {
    return gallery.value.images.filter(img => !img.folder_id).length
  })

  /**
   * Initialize store
   */
  const initialize = async (): Promise<void> => {
    if (!isAuthenticated.value) return

    try {
      await Promise.all([
        fetchModels(),
        fetchFolders(),
        fetchGallery(true),
        fetchStats()
      ])
    } catch (error) {
      console.error('Failed to initialize image generation store:', error)
    }
  }

  /**
   * Reset store (on logout)
   */
  const reset = (): void => {
    generation.value = {
      isGenerating: false,
      progress: {
        status: 'idle',
        message: '',
        progress: 0
      }
    }
    
    gallery.value = {
      images: [],
      loading: false,
      pagination: {
        page: 1,
        limit: 20,
        total: 0,
        hasMore: false
      },
      lastFetch: 0
    }
    
    models.value = {
      models: [],
      loading: false,
      lastFetch: 0
    }

    folders.value = {
      folders: [],
      selectedFolderId: null,
      loading: false,
      lastFetch: 0
    }

    stats.value = null
    statsLoading.value = false
  }

  // Watch for auth changes
  watch(() => authStore.isAuthenticated, (isAuth) => {
    if (isAuth) {
      initialize()
    } else {
      reset()
    }
  })
return {
    // State
    generation: computed(() => generation.value),
    gallery: computed(() => gallery.value),
    models: computed(() => models.value),
    folders: computed(() => folders.value),
    stats: computed(() => stats.value),
    statsLoading: computed(() => statsLoading.value),

    // Computed
    isAuthenticated,
    canGenerate,
    selectedModel,
    recentImages,
    totalGenerations,
    getUncategorizedCount,

    // Actions
    generateImage,
    fetchGallery,
    loadMoreImages,
    refreshImageUrls,
    batchRefreshGalleryUrls,
    deleteImage,
    downloadImage,
    uploadImages,
    fetchModels,
    selectModel,
    fetchStats,
    fetchFolders,
    createFolder,
    updateFolder,
    deleteFolder,
    moveImageToFolder,
    moveImagesToFolder,
    setSelectedFolder,
    resetGeneration,
    initialize,
    reset
  }
})
