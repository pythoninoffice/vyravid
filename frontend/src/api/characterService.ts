/**
 * Character Design Service
 * Handles API communication for character management
 */

import apiClient from './apiClient'

// =============================================
// Type Definitions
// =============================================

export interface CharacterDesign {
  id: string
  user_id: string
  name: string
  description?: string
  tags: string[]
  visual_style_notes?: string
  collection_id?: string
  thumbnail_image_id?: string
  created_at: string
  updated_at: string
  // Optional nested data
  reference_images?: CharacterReferenceImage[]
  thumbnail_url?: string
  collection_name?: string
}

export interface CharacterDesignCreate {
  name: string
  description?: string
  tags?: string[]
  visual_style_notes?: string
  collection_id?: string
}

export interface CharacterDesignUpdate {
  name?: string
  description?: string
  tags?: string[]
  visual_style_notes?: string
  collection_id?: string
  thumbnail_image_id?: string
}

export interface CharacterReferenceImage {
  id: string
  character_id: string
  generated_image_id: string
  angle_description?: string
  is_primary: boolean
  display_order: number
  created_at: string
  // Nested image data
  image_url?: string
  thumbnail_url?: string
  width?: number
  height?: number
}

export interface CharacterReferenceImageCreate {
  generated_image_id: string
  angle_description?: string
  is_primary?: boolean
  display_order?: number
}

export interface CharacterCollection {
  id: string
  user_id: string
  name: string
  description?: string
  created_at: string
  updated_at: string
  character_count?: number
}

export interface CharacterCollectionCreate {
  name: string
  description?: string
}

export interface CharacterCollectionUpdate {
  name?: string
  description?: string
}

export interface CharacterListResponse {
  characters: CharacterDesign[]
  total: number
  page: number
  limit: number
  has_more: boolean
}

export interface CollectionListResponse {
  collections: CharacterCollection[]
  total: number
}

export interface GenerateScenePromptRequest {
  scene_prompt: string
  character_ids: string[]
  include_visual_notes?: boolean
}

export interface GenerateScenePromptResponse {
  combined_prompt: string
  character_names: string[]
  reference_image_urls: string[]
}

export interface ReorderReferenceImagesRequest {
  image_orders: Array<{ id: string; display_order: number }>
}

export interface DeleteResponse {
  success: boolean
  message: string
}

export interface SetPrimaryImageResponse {
  success: boolean
  message: string
  thumbnail_image_id: string
}

// =============================================
// Error Handling
// =============================================

export class CharacterServiceError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public errorType?: string,
    public details?: any
  ) {
    super(message)
    this.name = 'CharacterServiceError'
  }
}

const handleApiError = (error: any): never => {
  console.error('Character Service Error:', {
    message: error.message,
    response: error.response?.data,
    status: error.response?.status,
    config: {
      url: error.config?.url,
      method: error.config?.method,
      headers: error.config?.headers
    }
  })

  if (error.response) {
    const detail = error.response.data?.detail
    throw new CharacterServiceError(
      detail?.message || error.response.data?.message || error.response.data?.detail || 'An error occurred',
      error.response.status,
      detail?.error,
      detail?.details
    )
  }
  throw new CharacterServiceError(error.message || 'Network error occurred')
}

// =============================================
// API Service
// =============================================

class CharacterService {
  private baseUrl = '/api/characters'

  // =============================================
  // Character CRUD Operations
  // =============================================

  /**
   * Create a new character
   */
  async createCharacter(data: CharacterDesignCreate): Promise<CharacterDesign> {
    try {
      // Debug: Check if token exists
      const token = localStorage.getItem('access_token')

      if (!token) {
        throw new CharacterServiceError(
          'You must be logged in to create characters. Please sign in and try again.',
          401,
          'NO_TOKEN'
        )
      }

      const response = await apiClient.post(this.baseUrl, data)
      return response.data
    } catch (error) {
      return handleApiError(error)
    }
  }

  /**
   * Get list of characters with pagination and filters
   */
  async listCharacters(params?: {
    page?: number
    limit?: number
    collection_id?: string
    search?: string
    tags?: string[]
  }): Promise<CharacterListResponse> {
    try {
      const response = await apiClient.get(this.baseUrl, { params })
      return response.data
    } catch (error) {
      return handleApiError(error)
    }
  }

  /**
   * Get a specific character by ID
   */
  async getCharacter(characterId: string): Promise<CharacterDesign> {
    try {
      const response = await apiClient.get(`${this.baseUrl}/${characterId}`)
      return response.data
    } catch (error) {
      return handleApiError(error)
    }
  }

  /**
   * Update a character
   */
  async updateCharacter(
    characterId: string,
    data: CharacterDesignUpdate
  ): Promise<CharacterDesign> {
    try {
      const response = await apiClient.put(`${this.baseUrl}/${characterId}`, data)
      return response.data
    } catch (error) {
      return handleApiError(error)
    }
  }

  /**
   * Delete a character
   */
  async deleteCharacter(characterId: string): Promise<DeleteResponse> {
    try {
      const response = await apiClient.delete(`${this.baseUrl}/${characterId}`)
      return response.data
    } catch (error) {
      return handleApiError(error)
    }
  }

  // =============================================
  // Reference Image Operations
  // =============================================

  /**
   * Add a reference image to a character
   */
  async addReferenceImage(
    characterId: string,
    data: CharacterReferenceImageCreate
  ): Promise<CharacterReferenceImage> {
    try {
      const response = await apiClient.post(`${this.baseUrl}/${characterId}/reference-images`, data)
      return response.data
    } catch (error) {
      return handleApiError(error)
    }
  }

  /**
   * Remove a reference image from a character
   */
  async removeReferenceImage(
    characterId: string,
    referenceId: string
  ): Promise<DeleteResponse> {
    try {
      const response = await apiClient.delete(
        `${this.baseUrl}/${characterId}/reference-images/${referenceId}`
      )
      return response.data
    } catch (error) {
      return handleApiError(error)
    }
  }

  /**
   * Reorder reference images
   */
  async reorderReferenceImages(
    characterId: string,
    data: ReorderReferenceImagesRequest
  ): Promise<DeleteResponse> {
    try {
      const response = await apiClient.put(
        `${this.baseUrl}/${characterId}/reference-images/reorder`,
        data
      )
      return response.data
    } catch (error) {
      return handleApiError(error)
    }
  }

  /**
   * Set a reference image as primary thumbnail
   */
  async setPrimaryImage(
    characterId: string,
    imageId: string
  ): Promise<SetPrimaryImageResponse> {
    try {
      const response = await apiClient.post(`${this.baseUrl}/${characterId}/set-primary/${imageId}`)
      return response.data
    } catch (error) {
      return handleApiError(error)
    }
  }

  // =============================================
  // Collection Operations
  // =============================================

  /**
   * Create a character collection
   */
  async createCollection(data: CharacterCollectionCreate): Promise<CharacterCollection> {
    try {
      const response = await apiClient.post(`${this.baseUrl}/collections`, data)
      return response.data
    } catch (error) {
      return handleApiError(error)
    }
  }

  /**
   * Get list of collections
   */
  async listCollections(): Promise<CollectionListResponse> {
    try {
      const response = await apiClient.get(`${this.baseUrl}/collections`)
      return response.data
    } catch (error) {
      return handleApiError(error)
    }
  }

  /**
   * Delete a collection
   */
  async deleteCollection(collectionId: string): Promise<DeleteResponse> {
    try {
      const response = await apiClient.delete(`${this.baseUrl}/collections/${collectionId}`)
      return response.data
    } catch (error) {
      return handleApiError(error)
    }
  }

  // =============================================
  // Scene Integration Operations
  // =============================================

  /**
   * Generate a combined scene prompt with characters
   */
  async generateScenePrompt(
    data: GenerateScenePromptRequest
  ): Promise<GenerateScenePromptResponse> {
    try {
      const response = await apiClient.post(`${this.baseUrl}/generate-scene-prompt`, data)
      return response.data
    } catch (error) {
      return handleApiError(error)
    }
  }
}

// Export singleton instance
export const characterService = new CharacterService()
export default characterService
