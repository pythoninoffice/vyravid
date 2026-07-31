import apiClient from './apiClient'
import type { GeneratedImage } from './imageGenerationService'

export interface PublicImage {
  id: string
  user_image_id: string
  original_user_id: string
  title?: string
  description?: string
  tags?: string[]
  is_public: boolean
  view_count: number
  copy_count: number
  created_at: string
  updated_at: string
  // Extended data from user_images/generated_images join
  filename?: string
  original_name?: string
  signed_url?: string
  thumbnail_signed_url?: string
  width?: number
  height?: number
  file_size?: number
  original_creator_name?: string
  // Generated image specific fields
  prompt?: string
  model_name?: string
}

export interface PublicImageMetadata {
  title?: string
  description?: string
  tags?: string[]
}

export interface PublicImagesResponse {
  images: PublicImage[]
  total: number
  page: number
  limit: number
  has_more: boolean
}

export interface PublicImageFilters {
  tags?: string[]
  model_name?: string
  search?: string
  min_copy_count?: number
  sort_by?: 'created_at' | 'view_count' | 'copy_count'
  sort_order?: 'asc' | 'desc'
}

export const publicImagesService = {
  /**
   * Get paginated list of public images
   */
  async getPublicImages(
    page: number = 1,
    limit: number = 20,
    filters: PublicImageFilters = {}
  ): Promise<PublicImagesResponse> {
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: limit.toString()
      })

      // Add filters to params
      if (filters.tags && filters.tags.length > 0) {
        params.append('tags', filters.tags.join(','))
      }
      if (filters.search) {
        params.append('search', filters.search)
      }
      if (filters.min_copy_count) {
        params.append('min_copy_count', filters.min_copy_count.toString())
      }
      if (filters.sort_by) {
        params.append('sort_by', filters.sort_by)
      }
      if (filters.sort_order) {
        params.append('sort_order', filters.sort_order)
      }

      const response = await apiClient.get(`/api/public-images?${params.toString()}`)

      return {
        images: response.data.images || [],
        total: response.data.total || 0,
        page: response.data.page || page,
        limit: response.data.limit || limit,
        has_more: response.data.has_more || false
      }
    } catch (error: any) {
      console.error('Error in getPublicImages:', error)
      if (error.response?.data?.detail) {
        throw new Error(error.response.data.detail)
      }
      throw new Error('Failed to fetch public images')
    }
  },

  /**
   * Make a user image public
   */
  async makeImagePublic(
    imageId: string,
    metadata: PublicImageMetadata,
    userId: string
  ): Promise<PublicImage> {
    try {
      const response = await apiClient.post('/api/public-images', {
        image_id: imageId,
        title: metadata.title,
        description: metadata.description,
        tags: metadata.tags || []
      })

      return response.data
    } catch (error: any) {
      console.error('Error in makeImagePublic:', error)
      if (error.response?.data?.detail) {
        throw new Error(error.response.data.detail)
      }
      throw new Error('Failed to make image public')
    }
  },

  /**
   * Make a public image private
   */
  async makeImagePrivate(imageId: string, userId: string): Promise<void> {
    try {
      await apiClient.delete(`/api/public-images/${imageId}`)
    } catch (error: any) {
      console.error('Error in makeImagePrivate:', error)
      if (error.response?.data?.detail) {
        throw new Error(error.response.data.detail)
      }
      throw new Error('Failed to make image private')
    }
  },

  /**
   * Copy a public image to user's gallery
   */
  async copyPublicImage(publicImageId: string, userId: string): Promise<GeneratedImage> {
    try {
      const response = await apiClient.post(`/api/public-images/${publicImageId}/copy`)
      return response.data
    } catch (error: any) {
      console.error('Error in copyPublicImage:', error)
      if (error.response?.data?.detail) {
        throw new Error(error.response.data.detail)
      }
      throw new Error('Failed to copy public image')
    }
  },

  /**
   * Increment view count for a public image
   */
  async incrementViewCount(publicImageId: string): Promise<void> {
    try {
      await apiClient.post(`/api/public-images/${publicImageId}/view`)
    } catch (error: any) {
      console.error('Error in incrementViewCount:', error)
      // Don't throw error as this is not critical functionality
    }
  },

  /**
   * Search public images
   */
  async searchPublicImages(
    query: string,
    page: number = 1,
    limit: number = 20
  ): Promise<PublicImagesResponse> {
    return this.getPublicImages(page, limit, { search: query })
  },

  /**
   * Get available tags for filtering
   */
  async getAvailableTags(): Promise<string[]> {
    try {
      const response = await apiClient.get('/api/public-images/tags')
      return response.data.tags || []
    } catch (error: any) {
      console.error('Error in getAvailableTags:', error)
      return []
    }
  },

  /**
   * Get public image by ID
   */
  async getPublicImage(publicImageId: string): Promise<PublicImage | null> {
    try {
      const response = await apiClient.get(`/api/public-images/${publicImageId}`)
      return response.data
    } catch (error: any) {
      console.error('Error in getPublicImage:', error)
      return null
    }
  },

  /**
   * Refresh signed URLs for a public image (when image fails to load)
   */
  async refreshPublicImageUrl(publicImageId: string): Promise<PublicImage | null> {
    try {
      const response = await apiClient.post(`/api/public-images/${publicImageId}/refresh-url`)
      return response.data
    } catch (error: any) {
      console.error('Error in refreshPublicImageUrl:', error)
      return null
    }
  }
}

export default publicImagesService