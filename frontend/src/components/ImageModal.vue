<template>
  <!-- Modal Backdrop -->
  <Teleport to="body">
    <div
      v-if="isOpen"
      class="fixed inset-0 z-50 overflow-y-auto"
      @click="closeModal"
    >
      <!-- Backdrop -->
      <div class="fixed inset-0 bg-black bg-opacity-75 transition-opacity"></div>
      
      <!-- Modal Container -->
      <div class="flex min-h-full items-center justify-center p-4">
        <div
          class="relative bg-white rounded-lg shadow-xl max-w-7xl w-full max-h-[90vh] overflow-hidden"
          @click.stop
        >
          <!-- Modal Header -->
          <div class="flex items-center justify-between p-4 border-b border-gray-200">
            <div class="flex items-center gap-3">
              <!-- Status Indicator -->
              <div :class="[
                'w-3 h-3 rounded-full',
                image?.status === 'completed' ? 'bg-green-500' :
                  image?.status === 'processing' ? 'bg-blue-500 animate-pulse' :
                    image?.status === 'failed' ? 'bg-red-500' : 'bg-gray-400'
              ]"></div>
              <div>
                <h3 class="text-lg font-semibold text-gray-900">Generated Image</h3>
                <p v-if="hasMultipleImages" class="text-sm text-gray-600">
                  {{ currentIndex + 1 }} of {{ images.length }}
                </p>
              </div>
            </div>
            
            <!-- Header Actions -->
            <div class="flex items-center gap-2">
              <!-- Download Button -->
              <button
                @click="downloadImage"
                class="p-2 text-gray-400 hover:text-gray-600 transition-colors rounded-lg hover:bg-gray-100"
                title="Download image"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </button>
              
              <!-- Delete Button -->
              <button
                @click="confirmDelete"
                class="p-2 text-gray-400 hover:text-red-600 transition-colors rounded-lg hover:bg-red-50"
                title="Delete image"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
              
              <!-- Close Button -->
              <button
                @click="closeModal"
                class="p-2 text-gray-400 hover:text-gray-600 transition-colors rounded-lg hover:bg-gray-100"
                title="Close modal"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          <!-- Modal Content -->
          <div class="flex flex-col lg:flex-row max-h-[calc(90vh-80px)]">
            <!-- Image Display -->
            <div class="flex-1 flex items-center justify-center bg-gray-50 p-4 lg:p-8 relative min-w-0">
              <!-- Previous Button -->
              <button
                v-if="hasMultipleImages && hasPrevious"
                @click="goToPrevious"
                class="absolute left-4 z-10 p-3 bg-black bg-opacity-50 hover:bg-opacity-75 text-white rounded-full transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-black"
                title="Previous image (←)"
              >
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
                </svg>
              </button>

              <!-- Next Button -->
              <button
                v-if="hasMultipleImages && hasNext"
                @click="goToNext"
                class="absolute right-4 z-10 p-3 bg-black bg-opacity-50 hover:bg-opacity-75 text-white rounded-full transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-black"
                title="Next image (→)"
              >
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </button>

              <div class="relative w-full h-full flex items-center justify-center overflow-hidden">
                <!-- Loading State -->
                <div
                  v-if="imageLoading"
                  class="flex items-center justify-center w-96 h-96 bg-gray-100 rounded-lg"
                >
                  <div class="text-center">
                    <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
                    <p class="text-gray-600">Loading image...</p>
                  </div>
                </div>

                <!-- Error State -->
                <div
                  v-else-if="imageError"
                  class="flex items-center justify-center w-96 h-96 bg-gray-100 rounded-lg"
                >
                  <div class="text-center">
                    <svg class="w-12 h-12 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <p class="text-gray-600 mb-2">Failed to load image</p>
                    <button
                      @click="retryImageLoad"
                      class="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                    >
                      Retry
                    </button>
                  </div>
                </div>

                <!-- Full Size Image -->
                <img
                  v-show="!imageLoading && !imageError && (image?.signed_url || image?.gcs_signed_url || image?.thumbnail_signed_url)"
                  :src="getFullSizeImageUrl(image)"
                  :alt="image?.prompt"
                  class="max-w-full max-h-[calc(90vh-12rem)] lg:max-w-[calc(100vw-32rem)] object-contain rounded-lg shadow-lg transition-transform duration-200"
                  :style="{ transform: `scale(${zoomLevel})` }"
                  @load="onImageLoad"
                  @error="onImageError"
                />
                
                <!-- Debug: Always render image to test -->
                <div v-if="image?.signed_url || image?.gcs_signed_url || image?.thumbnail_signed_url" class="absolute top-0 left-0 opacity-0 pointer-events-none">
                  <img
                    :src="getFullSizeImageUrl(image)"
                    :alt="image?.prompt"
                    @load="onImageLoad"
                    @error="onImageError"
                  />
                </div>

                <!-- Zoom Controls -->
                <div
                  v-if="!imageLoading && !imageError && (image?.signed_url || image?.gcs_signed_url || image?.thumbnail_signed_url)"
                  class="absolute bottom-4 right-4 flex items-center gap-2 bg-black bg-opacity-50 rounded-lg p-2"
                >
                  <button
                    @click="zoomOut"
                    :disabled="zoomLevel <= 0.5"
                    class="p-1 text-white hover:text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Zoom out"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM13 10H7" />
                    </svg>
                  </button>
                  
                  <span class="text-white text-sm px-2">{{ Math.round(zoomLevel * 100) }}%</span>
                  
                  <button
                    @click="zoomIn"
                    :disabled="zoomLevel >= 3"
                    class="p-1 text-white hover:text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Zoom in"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7" />
                    </svg>
                  </button>
                  
                  <button
                    @click="resetZoom"
                    class="p-1 text-white hover:text-gray-300"
                    title="Reset zoom"
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>

            <!-- Image Metadata Sidebar -->
            <div class="w-full lg:w-80 lg:flex-shrink-0 bg-white border-l border-gray-200 overflow-y-auto">
              <div class="p-6 space-y-6">
                <!-- Prompt -->
                <div>
                  <h4 class="text-sm font-medium text-gray-900 mb-2">Prompt</h4>
                  <div class="bg-gray-50 rounded-lg p-3">
                    <p class="text-sm text-gray-700 leading-relaxed">{{ image?.prompt }}</p>
                  </div>
                </div>

                <!-- Generation Details -->
                <div>
                  <h4 class="text-sm font-medium text-gray-900 mb-3">Generation Details</h4>
                  <div class="space-y-3">
                    <!-- Model -->
                    <div class="flex justify-between">
                      <span class="text-sm text-gray-600">Model</span>
                      <span class="text-sm font-medium text-gray-900">{{ image?.model_name }}</span>
                    </div>
                    
                    <!-- Status -->
                    <div class="flex justify-between items-center">
                      <span class="text-sm text-gray-600">Status</span>
                      <div class="flex items-center gap-2">
                        <div :class="[
                          'w-2 h-2 rounded-full',
                          image?.status === 'completed' ? 'bg-green-500' :
                            image?.status === 'processing' ? 'bg-blue-500 animate-pulse' :
                              image?.status === 'failed' ? 'bg-red-500' : 'bg-gray-400'
                        ]"></div>
                        <span class="text-sm font-medium text-gray-900 capitalize">{{ image?.status }}</span>
                      </div>
                    </div>
                    
                    <!-- Dimensions -->
                    <div v-if="image?.width && image?.height" class="flex justify-between">
                      <span class="text-sm text-gray-600">Dimensions</span>
                      <span class="text-sm font-medium text-gray-900">{{ image.width }}×{{ image.height }}</span>
                    </div>
                    
                    <!-- File Size -->
                    <div v-if="image?.file_size" class="flex justify-between">
                      <span class="text-sm text-gray-600">File Size</span>
                      <span class="text-sm font-medium text-gray-900">{{ formatFileSize(image.file_size) }}</span>
                    </div>
                    
                    <!-- Created Date -->
                    <div class="flex justify-between">
                      <span class="text-sm text-gray-600">Created</span>
                      <span class="text-sm font-medium text-gray-900">{{ formatFullDate(image?.created_at) }}</span>
                    </div>
                  </div>
                </div>

                <!-- Actions -->
                <div>
                  <h4 class="text-sm font-medium text-gray-900 mb-3">Actions</h4>
                  <div class="space-y-2">
                    <!-- Create Variants Button -->
                    <button
                      @click="createVariants"
                      :disabled="!canCreateVariants || creatingVariants"
                      class="w-full flex items-center justify-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <svg
                        v-if="creatingVariants"
                        class="w-4 h-4 animate-spin"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      <svg
                        v-else
                        class="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428A8 8 0 118.572 4.572M20 4v5h-5" />
                      </svg>
                      {{ creatingVariants ? 'Creating Variants...' : 'Create More Variants' }}
                    </button>

                    <!-- Create Character Button -->
                    <button
                      @click="createCharacter"
                      class="w-full flex items-center justify-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
                    >
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                      Create Character
                    </button>

                    <!-- Download Button -->
                    <button
                      @click="downloadImage"
                      class="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                    >
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      Download Image
                    </button>

                    <!-- Copy URL Button -->
                    <button
                      @click="copyImageUrl"
                      class="w-full flex items-center justify-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
                    >
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                      Copy URL
                    </button>

                    <!-- Delete Button -->
                    <button
                      @click="confirmDelete"
                      class="w-full flex items-center justify-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                    >
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                      Delete Image
                    </button>
                  </div>
                </div>

                <!-- Copy Success Message -->
                <div
                  v-if="copySuccess"
                  class="p-3 bg-green-50 border border-green-200 rounded-lg"
                >
                  <div class="flex items-center gap-2">
                    <svg class="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                    </svg>
                    <span class="text-sm text-green-800">URL copied to clipboard!</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import type { GeneratedImage } from '@/api/imageGenerationService'

// Props
interface Props {
  image: GeneratedImage | null
  isOpen: boolean
  images?: GeneratedImage[]
  currentIndex?: number
  creatingVariants?: boolean
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  'close': []
  'download': [image: GeneratedImage]
  'delete': [image: GeneratedImage]
  'navigate': [direction: 'previous' | 'next']
  'create-character': [image: GeneratedImage]
  'create-variants': [image: GeneratedImage]
}>()

// Local state
const imageLoading = ref(true)
const imageError = ref(false)
const zoomLevel = ref(1)
const copySuccess = ref(false)

// Computed
const image = computed(() => props.image)
const isOpen = computed(() => props.isOpen)
const images = computed(() => props.images || [])
const currentIndex = computed(() => props.currentIndex || 0)
const creatingVariants = computed(() => props.creatingVariants || false)
const hasMultipleImages = computed(() => images.value.length > 1)
const hasPrevious = computed(() => hasMultipleImages.value && currentIndex.value > 0)
const hasNext = computed(() => hasMultipleImages.value && currentIndex.value < images.value.length - 1)
const canCreateVariants = computed(() => {
  return Boolean(image.value?.prompt && getFullSizeImageUrl(image.value) && image.value.status === 'completed')
})

// Methods
const closeModal = () => {
  emit('close')
}

const downloadImage = async () => {
  if (image.value) {
    try {
      // Import the service dynamically to avoid circular dependencies
      const { default: imageGenerationService } = await import('@/api/imageGenerationService')
      await imageGenerationService.downloadImage(image.value)
    } catch (error) {
      console.error('Download failed:', error)
      // Fallback to emitting the event for parent to handle
      emit('download', image.value)
    }
  }
}

const confirmDelete = () => {
  if (image.value && confirm('Delete this generated image? This action cannot be undone.')) {
    emit('delete', image.value)
  }
}

const createCharacter = () => {
  if (image.value) {
    emit('create-character', image.value)
  }
}

const createVariants = () => {
  if (image.value && canCreateVariants.value && !props.creatingVariants) {
    emit('create-variants', image.value)
  }
}

const onImageLoad = () => {
  imageLoading.value = false
  imageError.value = false
}

const onImageError = (event: Event) => {
  console.error('Image failed to load:', event)
  console.error('Image src:', (event.target as HTMLImageElement)?.src)
  imageLoading.value = false
  imageError.value = true
}

const retryImageLoad = () => {
  imageLoading.value = true
  imageError.value = false
  // Force image reload by updating src
  const imageUrl = getFullSizeImageUrl(image.value)
  if (imageUrl) {
    const img = new Image()
    img.onload = onImageLoad
    img.onerror = (event) => {
      if (event instanceof Event) {
        onImageError(event)
      }
    }
    img.src = imageUrl
  }
}

const zoomIn = () => {
  if (zoomLevel.value < 3) {
    zoomLevel.value = Math.min(zoomLevel.value + 0.25, 3)
  }
}

const zoomOut = () => {
  if (zoomLevel.value > 0.5) {
    zoomLevel.value = Math.max(zoomLevel.value - 0.25, 0.5)
  }
}

const resetZoom = () => {
  zoomLevel.value = 1
}

const getFullSizeImageUrl = (img: GeneratedImage | null): string => {
  if (!img) return ''
  
  // Always prioritize the full-size image URL over thumbnail
  // Check both possible field names for full-size image
  const fullSizeUrl = img.gcs_signed_url || img.signed_url
  
  if (fullSizeUrl) {
    return fullSizeUrl
  } else if (img.thumbnail_signed_url) {
    return img.thumbnail_signed_url
  }
  
  console.warn('No image URL available for image:', img.id)
  return ''
}

const copyImageUrl = async () => {
  const fullImageUrl = getFullSizeImageUrl(image.value)
  if (fullImageUrl) {
    try {
      await navigator.clipboard.writeText(fullImageUrl)
      copySuccess.value = true
      setTimeout(() => {
        copySuccess.value = false
      }, 3000)
    } catch (error) {
      console.error('Failed to copy URL:', error)
      // Fallback for older browsers
      const textArea = document.createElement('textarea')
      textArea.value = fullImageUrl
      document.body.appendChild(textArea)
      textArea.select()
      try {
        document.execCommand('copy')
        copySuccess.value = true
        setTimeout(() => {
          copySuccess.value = false
        }, 3000)
      } catch (fallbackError) {
        console.error('Fallback copy failed:', fallbackError)
      }
      document.body.removeChild(textArea)
    }
  }
}

const goToPrevious = () => {
  if (hasPrevious.value) {
    emit('navigate', 'previous')
  }
}

const goToNext = () => {
  if (hasNext.value) {
    emit('navigate', 'next')
  }
}

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 Bytes'
  
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const formatFullDate = (dateString?: string): string => {
  if (!dateString) return 'Unknown'
  
  const date = new Date(dateString)
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Handle keyboard shortcuts
const handleKeydown = (event: KeyboardEvent) => {
  if (!isOpen.value) return
  
  switch (event.key) {
    case 'Escape':
      closeModal()
      break
    case 'ArrowLeft':
      event.preventDefault()
      goToPrevious()
      break
    case 'ArrowRight':
      event.preventDefault()
      goToNext()
      break
    case 'd':
    case 'D':
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault()
        downloadImage()
      }
      break
    case 'Delete':
    case 'Backspace':
      if (event.shiftKey) {
        event.preventDefault()
        confirmDelete()
      }
      break
  }
}

// Watch for modal open/close to handle keyboard events and reset state
watch(isOpen, (newIsOpen) => {
  if (newIsOpen) {
    // Reset state when opening
    imageLoading.value = true
    imageError.value = false
    zoomLevel.value = 1
    copySuccess.value = false
    
    // Add keyboard event listener
    document.addEventListener('keydown', handleKeydown)
    
    // Prevent body scroll
    document.body.style.overflow = 'hidden'
  } else {
    // Remove keyboard event listener
    document.removeEventListener('keydown', handleKeydown)
    
    // Restore body scroll
    document.body.style.overflow = ''
  }
})

// Watch for image changes to reset loading state
watch(() => props.image?.id, () => {
  if (props.image) {

    imageLoading.value = true
    imageError.value = false
    zoomLevel.value = 1
  }
})

// Watch the loading and error states
watch([imageLoading, imageError], ([loading, error]) => {
  console.log('State changed - imageLoading:', loading, 'imageError:', error)
})
</script>

<style scoped>
/* Custom styles for zoom functionality */
.zoom-container img {
  transform-origin: center center;
  transition: transform 0.2s ease-in-out;
}
</style>
