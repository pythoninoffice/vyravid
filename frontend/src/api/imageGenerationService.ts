import apiClient from './apiClient'
import { AxiosError } from 'axios'

// Retry configuration
interface RetryConfig {
  maxRetries: number
  baseDelay: number
  maxDelay: number
  retryableStatuses: number[]
}

const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  baseDelay: 1000, // 1 second
  maxDelay: 10000, // 10 seconds
  retryableStatuses: [408, 429, 500, 502, 503, 504]
}

// Error types for better error handling
export class ImageGenerationError extends Error {
  constructor(
    message: string,
    public code?: string,
    public statusCode?: number,
    public retryable: boolean = false
  ) {
    super(message)
    this.name = 'ImageGenerationError'
  }
}

export class ValidationError extends ImageGenerationError {
  constructor(message: string, public errors: string[] = []) {
    super(message, 'VALIDATION_ERROR', 400, false)
  }
}

// Utility functions for retry logic
const sleep = (ms: number): Promise<void> => new Promise(resolve => setTimeout(resolve, ms))

const calculateDelay = (attempt: number, baseDelay: number, maxDelay: number): number => {
  const exponentialDelay = baseDelay * Math.pow(2, attempt - 1)
  const jitter = Math.random() * 0.1 * exponentialDelay // Add 10% jitter
  return Math.min(exponentialDelay + jitter, maxDelay)
}

const isRetryableError = (error: AxiosError, retryableStatuses: number[]): boolean => {
  if (!error.response) {
    // Network errors are generally retryable
    return true
  }
  
  return retryableStatuses.includes(error.response.status)
}

const withRetry = async <T>(
  operation: () => Promise<T>,
  config: Partial<RetryConfig> = {}
): Promise<T> => {
  const retryConfig = { ...DEFAULT_RETRY_CONFIG, ...config }
  let lastError: Error = new Error('Unknown error')

  for (let attempt = 1; attempt <= retryConfig.maxRetries + 1; attempt++) {
    try {
      return await operation()
    } catch (error) {
      lastError = error as Error
      
      // Don't retry on the last attempt
      if (attempt > retryConfig.maxRetries) {
        break
      }
      
      // Check if error is retryable
      if (error instanceof AxiosError) {
        if (!isRetryableError(error, retryConfig.retryableStatuses)) {
          break
        }
        
        // Don't retry auth errors or client errors (except rate limiting)
        if (error.response?.status && error.response.status < 500 && error.response.status !== 429) {
          break
        }
      }
      
      // Calculate delay and wait
      const delay = calculateDelay(attempt, retryConfig.baseDelay, retryConfig.maxDelay)
      await sleep(delay)
    }
  }
  
  throw lastError
}

// Enhanced error handling
const handleApiError = (error: AxiosError): never => {
  if (!error.response) {
    throw new ImageGenerationError(
      'Network error occurred. Please check your connection and try again.',
      'NETWORK_ERROR',
      0,
      true
    )
  }
  
  const { status, data } = error.response

  // Try to extract the most descriptive error message from various response formats
  const detail = (data as any)?.detail
  const detailMessage = typeof detail === 'string'
    ? detail
    : detail?.message || detail?.error_message || detail?.error
  const errorCode = detail?.code || detail?.error || (data as any)?.code || (data as any)?.error
  const message = detailMessage ||
                  (data as any)?.message ||
                  (data as any)?.error_message ||
                  (typeof (data as any)?.error === 'string' ? (data as any).error : null) ||
                  (typeof data === 'string' ? data : null) ||
                  error.message
  
  switch (status) {
    case 400:
      if (message.toLowerCase().includes('validation')) {
        const errors = (data as any)?.errors || []
        throw new ValidationError(message, errors)
      }
      throw new ImageGenerationError(message, 'BAD_REQUEST', status, false)

    case 422:
      if (errorCode === 'content_blocked' || errorCode === 'CONTENT_BLOCKED') {
        throw new ImageGenerationError(message, 'CONTENT_BLOCKED', status, false)
      }
      throw new ValidationError(message)
    
    case 401:
      throw new ImageGenerationError(
        'Authentication failed. Please sign in again.',
        'UNAUTHORIZED',
        status,
        false
      )
    
    case 403:
      throw new ImageGenerationError(message, 'FORBIDDEN', status, false)
    
    case 404:
      throw new ImageGenerationError(
        'Resource not found.',
        'NOT_FOUND',
        status,
        false
      )
    
    case 408:
      throw new ImageGenerationError(
        'Request timeout. Please try again.',
        'TIMEOUT',
        status,
        true
      )
    
    case 429:
      throw new ImageGenerationError(
        'Too many requests. Please wait a moment and try again.',
        'RATE_LIMITED',
        status,
        true
      )
    
    case 500:
      // For 500 errors, try to get the actual error message from the backend
      throw new ImageGenerationError(
        message || 'Server error occurred. Please try again in a moment.',
        'SERVER_ERROR',
        status,
        true
      )

    case 502:
    case 503:
    case 504:
      throw new ImageGenerationError(
        'Server error occurred. Please try again in a moment.',
        'SERVER_ERROR',
        status,
        true
      )
    
    default:
      throw new ImageGenerationError(
        message || 'An unexpected error occurred.',
        'UNKNOWN_ERROR',
        status,
        status >= 500
      )
  }
}

export interface ImageGenerationRequest {
  prompt: string
  model?: string
  width?: number
  height?: number
  num_outputs?: number
  aspect_ratio?: string
  input?: Record<string, any>
  referenceImages?: string[]
  tags?: string[]
}

export interface GeneratedImage {
  id: string
  prompt: string
  model_name: string
  provider: string
  provider_prediction_id?: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  signed_url?: string
  gcs_signed_url?: string
  thumbnail_signed_url?: string
  url_expires_at?: string
  width?: number
  height?: number
  file_size?: number
  generation_time_ms?: number
  created_at: string
  updated_at: string
  tags?: string[]
  media_type?: 'image' | 'video'
  // Public sharing fields
  is_public?: boolean
  copied_from_public_id?: string
  original_public_image_id?: string
  // Folder organization
  folder_id?: string
}

export interface ImageGenerationResponse {
  id: string
  prompt: string
  model_name: string
  status: string
  prediction_id?: string
  estimated_time?: number
}

export interface ImageModel {
  id: string
  name: string
  description: string
  quality?: string
  speed?: string
}

export interface ImageGenerationStats {
  total_generations: number
  successful_generations: number
  failed_generations: number
}

export const imageGenerationService = {
  /**
   * Generate a new image from a text prompt
   */
  async generateImage(request: ImageGenerationRequest): Promise<ImageGenerationResponse> {
    // Validate request first
    const validation = this.validateGenerationRequest(request)
    if (!validation.valid) {
      throw new ValidationError('Invalid generation request', validation.errors)
    }

    try {
      return await withRetry(async () => {
        const response = await apiClient.post('/api/image-generation/generate', request)
        return response.data
      }, {
        maxRetries: 2, // Fewer retries for generation requests
        baseDelay: 2000 // Longer delay for generation
      })
    } catch (error) {
      if (error instanceof ImageGenerationError) {
        throw error
      }
      return handleApiError(error as AxiosError)
    }
  },

  /**
   * Get all generated images for the current user
   */
  async getUserGenerations(page: number = 1, limit: number = 20, folderId?: string): Promise<{
    images: GeneratedImage[]
    total: number
    page: number
    limit: number
    has_more: boolean
  }> {
    try {
      return await withRetry(async () => {
        const params: any = { page, limit }
        if (folderId !== undefined) {
          params.folder_id = folderId
        }

        const response = await apiClient.get('/api/image-generation/generations', {
          params
        })
        return response.data
      })
    } catch (error) {
      if (error instanceof ImageGenerationError) {
        throw error
      }
      return handleApiError(error as AxiosError)
    }
  },

  /**
   * Get a specific generated image by ID
   */
  async getGeneration(imageId: string): Promise<GeneratedImage> {
    if (!imageId?.trim()) {
      throw new ValidationError('Image ID is required')
    }

    try {
      return await withRetry(async () => {
        const response = await apiClient.get(`/api/image-generation/generations/${imageId}`)
        return response.data
      })
    } catch (error) {
      if (error instanceof ImageGenerationError) {
        throw error
      }
      return handleApiError(error as AxiosError)
    }
  },

  /**
   * Delete a generated image
   */
  async deleteGeneration(imageId: string): Promise<void> {
    if (!imageId?.trim()) {
      throw new ValidationError('Image ID is required')
    }

    try {
      await withRetry(async () => {
        await apiClient.delete(`/api/image-generation/generations/${imageId}`)
      }, {
        maxRetries: 2 // Fewer retries for delete operations
      })
    } catch (error) {
      if (error instanceof ImageGenerationError) {
        throw error
      }
      handleApiError(error as AxiosError)
    }
  },

  /**
   * Get available image generation models
   */
  async getAvailableModels(): Promise<ImageModel[]> {
    try {
      return await withRetry(async () => {
        const response = await apiClient.get('/api/image-generation/models')
        return response.data
      })
    } catch (error) {
      if (error instanceof ImageGenerationError) {
        throw error
      }
      return handleApiError(error as AxiosError)
    }
  },

  /**
   * Get generation statistics for the current user
   */
  async getGenerationStats(): Promise<ImageGenerationStats> {
    try {
      return await withRetry(async () => {
        const response = await apiClient.get('/api/image-generation/stats')
        return response.data
      })
    } catch (error) {
      if (error instanceof ImageGenerationError) {
        throw error
      }
      return handleApiError(error as AxiosError)
    }
  },

  /**
   * Refresh signed URLs for an image
   */
  async refreshImageUrls(imageId: string, currentUrl?: string): Promise<{
    signed_url: string
    thumbnail_signed_url?: string
    expires_at: string
  }> {
    if (!imageId?.trim()) {
      throw new ValidationError('Image ID is required')
    }

    try {
      return await withRetry(async () => {
        const response = await apiClient.post(`/api/image-generation/refresh-urls/${imageId}`, currentUrl ? { current_url: currentUrl } : undefined)
        return response.data
      })
    } catch (error) {
      if (error instanceof ImageGenerationError) {
        throw error
      }
      return handleApiError(error as AxiosError)
    }
  },

  /**
   * Download an image with proper filename
   */
  async downloadImage(image: GeneratedImage): Promise<void> {
    const imageUrl = image?.signed_url || image?.gcs_signed_url
    if (!imageUrl) {
      throw new ImageGenerationError('Image URL not available', 'NO_URL', 400, false)
    }

    try {
      // Check if URL needs refresh
      if (this.needsUrlRefresh(image)) {
        console.log('Refreshing image URLs before download...')
        const refreshedUrls = await this.refreshImageUrls(image.id)
        image.signed_url = refreshedUrls.signed_url
      }

      // Create a temporary link element to trigger download
      const link = document.createElement('a')
      const downloadUrl = image.signed_url || image.gcs_signed_url || ''
      link.href = downloadUrl

      // Generate a meaningful filename
      const timestamp = new Date(image.created_at).toISOString().split('T')[0]
      const sanitizedPrompt = image.prompt
        .substring(0, 50)
        .replace(/[^a-zA-Z0-9\s]/g, '')
        .replace(/\s+/g, '_')
        .toLowerCase()

      const fileExtension = downloadUrl.includes('.png') ? 'png' : 'jpg'
      link.download = `generated_image_${timestamp}_${sanitizedPrompt}_${image.id.substring(0, 8)}.${fileExtension}`
      
      // Set attributes for better download behavior
      link.setAttribute('target', '_blank')
      link.setAttribute('rel', 'noopener noreferrer')
      
      // Trigger download
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    } catch (error) {
      console.error('Download failed:', error)
      
      if (error instanceof ImageGenerationError) {
        throw error
      }
      
      // Try fallback: open in new tab
      try {
        window.open(image.signed_url, '_blank')
      } catch (fallbackError) {
        throw new ImageGenerationError(
          'Failed to download image. Please try again or contact support.',
          'DOWNLOAD_FAILED',
          500,
          true
        )
      }
    }
  },

  /**
   * Validate image generation request
   */
  validateGenerationRequest(request: ImageGenerationRequest): { valid: boolean; errors: string[] } {
    const errors: string[] = []
    
    // Validate prompt
    if (!request.prompt || request.prompt.trim().length === 0) {
      errors.push('Prompt is required')
    } else if (request.prompt.trim().length < 3) {
      errors.push('Prompt must be at least 3 characters long')
    }
    
    // Validate dimensions
    if (request.width && (request.width < 512 || request.width > 2048)) {
      errors.push('Width must be between 512 and 2048 pixels')
    }
    
    if (request.height && (request.height < 512 || request.height > 2048)) {
      errors.push('Height must be between 512 and 2048 pixels')
    }
    
    // Validate number of outputs
    if (request.num_outputs && (request.num_outputs < 1 || request.num_outputs > 4)) {
      errors.push('Number of outputs must be between 1 and 4')
    }
    
    return {
      valid: errors.length === 0,
      errors
    }
  },

  /**
   * Get image dimensions from size string
   */
  parseDimensions(sizeString: string): { width: number; height: number } {
    const [width, height] = sizeString.split('x').map(Number)
    return { width, height }
  },

  /**
   * Format generation time
   */
  formatGenerationTime(timeMs?: number): string {
    if (!timeMs) return 'Unknown'
    
    if (timeMs < 1000) {
      return `${timeMs}ms`
    } else if (timeMs < 60000) {
      return `${(timeMs / 1000).toFixed(1)}s`
    } else {
      const minutes = Math.floor(timeMs / 60000)
      const seconds = Math.floor((timeMs % 60000) / 1000)
      return `${minutes}m ${seconds}s`
    }
  },

  /**
   * Get status display info
   */
  getStatusInfo(status: string): { label: string; color: string; description: string } {
    switch (status) {
      case 'pending':
        return {
          label: 'Pending',
          color: 'gray',
          description: 'Generation request is queued'
        }
      case 'processing':
        return {
          label: 'Processing',
          color: 'blue',
          description: 'AI is generating your image'
        }
      case 'completed':
        return {
          label: 'Completed',
          color: 'green',
          description: 'Image generated successfully'
        }
      case 'failed':
        return {
          label: 'Failed',
          color: 'red',
          description: 'Generation failed'
        }
      default:
        return {
          label: 'Unknown',
          color: 'gray',
          description: 'Status unknown'
        }
    }
  },

  /**
   * Estimate generation time based on model and settings
   */
  estimateGenerationTime(model: string, numOutputs: number = 1): number {
    // Base times in seconds (these would be based on actual model performance)
    const baseTimes: Record<string, number> = {
      'prunaai/z-image-turbo:7ea16386290ff5977c7812e66e462d7ec3954d8e007a8cd18ded3e7d41f5d7cf': 15
    }
    
    const baseTime = baseTimes[model] || 20
    return baseTime * numOutputs
  },

  /**
   * Check if image URLs need refresh (within 1 hour of expiry)
   */
  needsUrlRefresh(image: GeneratedImage): boolean {
    if (!image.signed_url) return false

    const now = new Date()

    // If we have url_expires_at, use it to determine if refresh is needed
    if (image.url_expires_at) {
      const expiresAt = new Date(image.url_expires_at)
      // Refresh if URL expires within the next hour (3600000 ms)
      const timeUntilExpiry = expiresAt.getTime() - now.getTime()
      return timeUntilExpiry < 3600000 // 1 hour buffer
    }

    // Fallback: If no expiry info, assume URLs need refresh after 23 hours from creation
    const createdAt = new Date(image.created_at)
    const hoursOld = (now.getTime() - createdAt.getTime()) / (1000 * 60 * 60)

    return hoursOld > 23
  },

  /**
   * Get user-friendly error message from error object
   */
  getErrorMessage(error: unknown): string {
    if (error instanceof ImageGenerationError) {
      return error.message
    }
    
    if (error instanceof Error) {
      return error.message
    }
    
    return 'An unexpected error occurred. Please try again.'
  },

  /**
   * Check if an error is retryable
   */
  isRetryableError(error: unknown): boolean {
    if (error instanceof ImageGenerationError) {
      return error.retryable
    }
    
    return false
  },

  /**
   * Get error type for UI handling
   */
  getErrorType(error: unknown): 'validation' | 'network' | 'server' | 'auth' | 'unknown' {
    if (error instanceof ValidationError) {
      return 'validation'
    }
    
    if (error instanceof ImageGenerationError) {
      switch (error.code) {
        case 'NETWORK_ERROR':
          return 'network'
        case 'UNAUTHORIZED':
          return 'auth'
        case 'SERVER_ERROR':
        case 'TIMEOUT':
        case 'RATE_LIMITED':
          return 'server'
        default:
          return 'unknown'
      }
    }
    
    return 'unknown'
  },

  /**
   * Create a retry function for failed operations
   */
  createRetryFunction<T extends any[]>(
    operation: (...args: T) => Promise<any>,
    ...args: T
  ): () => Promise<any> {
    return () => operation.apply(this, args)
  },

  /**
   * Batch refresh URLs for multiple images
   */
  async batchRefreshUrls(images: GeneratedImage[]): Promise<GeneratedImage[]> {
    const refreshPromises = images
      .filter(image => this.needsUrlRefresh(image))
      .map(async (image) => {
        try {
          const refreshedUrls = await this.refreshImageUrls(image.id)
          return {
            ...image,
            signed_url: refreshedUrls.signed_url,
            thumbnail_signed_url: refreshedUrls.thumbnail_signed_url
          }
        } catch (error) {
          console.warn(`Failed to refresh URLs for image ${image.id}:`, error)
          return image // Return original image if refresh fails
        }
      })

    const refreshedImages = await Promise.allSettled(refreshPromises)

    // Merge refreshed images back with original array
    const refreshedMap = new Map<string, GeneratedImage>()
    refreshedImages.forEach((result) => {
      if (result.status === 'fulfilled') {
        refreshedMap.set(result.value.id, result.value)
      }
    })

    return images.map(image => refreshedMap.get(image.id) || image)
  },

  /**
   * Preload image for better UX
   */
  async preloadImage(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const img = new Image()
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('Failed to preload image'))
      img.src = url
    })
  },

  /**
   * Get image file size in human readable format
   */
  formatFileSize(bytes?: number): string {
    if (!bytes) return 'Unknown'

    const units = ['B', 'KB', 'MB', 'GB']
    let size = bytes
    let unitIndex = 0

    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024
      unitIndex++
    }

    return `${size.toFixed(1)} ${units[unitIndex]}`
  },

  /**
   * Upload images from user's computer
   */
  async uploadImages(files: File[]): Promise<{
    success: boolean
    message: string
    images: GeneratedImage[]
    total_uploaded: number
  }> {
    if (!files || files.length === 0) {
      throw new ValidationError('No files selected for upload')
    }

    if (files.length > 10) {
      throw new ValidationError('Maximum 10 files per upload')
    }

    // Validate file types and sizes
    const maxSize = 50 * 1024 * 1024 // 50MB
    const supportedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']

    for (let i = 0; i < files.length; i++) {
      const file = files[i]

      if (!supportedTypes.includes(file.type)) {
        throw new ValidationError(`File ${i + 1} (${file.name}): Unsupported format. Supported: JPEG, PNG, WebP`)
      }

      if (file.size > maxSize) {
        const sizeMB = (file.size / (1024 * 1024)).toFixed(1)
        throw new ValidationError(`File ${i + 1} (${file.name}): Too large (${sizeMB}MB). Maximum: 50MB`)
      }

      if (file.size === 0) {
        throw new ValidationError(`File ${i + 1} (${file.name}): File is empty`)
      }
    }

    try {
      // Create FormData
      const formData = new FormData()
      files.forEach(file => {
        formData.append('files', file)
      })

      return await withRetry(async () => {
        const response = await apiClient.post('/api/image-generation/upload', formData, {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        })
        return response.data
      }, {
        maxRetries: 1, // Fewer retries for uploads
        baseDelay: 2000
      })
    } catch (error) {
      if (error instanceof ImageGenerationError) {
        throw error
      }
      return handleApiError(error as AxiosError)
    }
  }
}

export default imageGenerationService
