import apiClient from './apiClient'
import { logger } from '@/utils/logger'

export interface UserImage {
  id: string
  filename: string
  original_name: string
  file_size: number
  width?: number
  height?: number
  mime_type: string
  media_type?: string  // From generated_images table: "video" or "image"
  gcs_path: string
  signed_url: string
  thumbnail_signed_url?: string
  upload_date: string
  url_expires_at?: string
  prompt?: string  // Generation prompt for searching/filtering
  tags?: string[]  // Tags for organizing and searching images
}

export interface ImageUploadResponse {
  id: string
  filename: string
  original_name: string
  file_size: number
  width: number
  height: number
  mime_type: string
  gcs_path: string
  bucket_name?: string
  signed_url: string
  thumbnail_signed_url?: string
  upload_date: string
}

export interface ImageTimelineSegment {
  image_id: string
  start_time: number
  end_time: number
  transition_type?: 'cut' | 'fade' | 'slide' | 'fade' | 'fadeblack' | 'fadewhite' | 'distance' | 'wipeleft' | 'wiperight' | 'wipeup' | 'wipedown' | 'slideleft' | 'slideright' | 'slideup' | 'slidedown' | 'smoothleft' | 'smoothright' | 'smoothup' | 'smoothdown' | 'circlecrop' | 'rectcrop' | 'circleclose' | 'circleopen' | 'horzclose' | 'horzopen' | 'vertclose' | 'vertopen' | 'diagbl' | 'diagbr' | 'diagtl' | 'diagtr' | 'hlslice' | 'hrslice' | 'vuslice' | 'vdslice' | 'dissolve' | 'pixelize' | 'radial' | 'hblur' | 'wipetl' | 'wipetr' | 'wipebl' | 'wipebr' | 'fadegrays' | 'squeezev' | 'squeezeh' | 'zoomin' | 'hlwind' | 'hrwind' | 'vuwind' | 'vdwind' | 'coverleft' | 'coverright' | 'coverup' | 'coverdown' | 'revealleft' | 'revealright' | 'revealup' | 'revealdown'
  transition_duration?: number
  camera_movement?: 'static' | 'pan_right' | 'pan_left' | 'pan_up' | 'pan_down' | 'zoom_in' | 'zoom_out' | 'doodle_slow' | 'doodle_fast'
  greenscreen_effect?: string
  sort_order: number
}

export interface ImageTimelineRequest {
  video_project_id: string
  segments: ImageTimelineSegment[]
}

export interface ImageTimelineResponse {
  video_project_id: string
  segments: Array<{
    id: string
    image_id: string
    start_time: number
    end_time: number
    transition_type: string
    transition_duration: number
    sort_order: number
    image_info: {
      filename?: string
      original_name?: string
      signed_url?: string
      thumbnail_signed_url?: string
      width?: number
      height?: number
    }
  }>
  segments_count: number
  total_duration: number
}

type AnimateImageResult = {
  success: boolean
  video_id: string
  signed_url: string
  duration: number
  generation_time_ms: number
  source_image_id: string | null
  animation_prompt: string
}

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

const isAsyncAnimateModel = (model: string) => {
  const normalizedModel = model.toLowerCase()
  return normalizedModel.includes('seedance-2')
    || normalizedModel === 'gemini-omni-flash-preview'
    || normalizedModel === 'kwaivgi/kling-v2.1'
    || normalizedModel === 'kling-video/kling2.1'
    || normalizedModel === 'kwaivgi/kling-v2.6'
    || normalizedModel === 'kwaivgi/kling-v3-video'
}

export const imageService = {
  /**
   * Upload multiple images
   */
  async uploadImages(files: File[]): Promise<ImageUploadResponse[]> {
    if (!files || files.length === 0) {
      throw new Error('No files provided for upload')
    }

    // Validate files before upload
    const validation = this.validateImages(files)
    if (!validation.valid) {
      throw new Error(validation.errors.join('; '))
    }

    // Create FormData for multipart upload
    const formData = new FormData()
    files.forEach((file) => {
      formData.append('files', file)
    })

    try {
      const response = await apiClient.post('/api/image-generation/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        timeout: 30000 // 30 second timeout for uploads
      })

      // Transform the response to match ImageUploadResponse interface
      if (response.data && response.data.images) {
        return response.data.images.map((img: any) => ({
          id: img.id,
          filename: img.filename || img.original_name,
          original_name: img.original_name || img.filename,
          file_size: img.file_size,
          width: img.width || 0,
          height: img.height || 0,
          mime_type: img.mime_type,
          gcs_path: img.gcs_path || '',
          bucket_name: img.bucket_name || undefined,
          signed_url: img.signed_url || '',
          thumbnail_signed_url: img.thumbnail_signed_url || '',
          upload_date: img.upload_date || img.created_at || ''
        }))
      } else {
        throw new Error('Invalid response format from server')
      }
    } catch (error: any) {
      if (error.response?.data?.detail) {
        // Handle API error responses
        const detail = error.response.data.detail
        if (typeof detail === 'string') {
          throw new Error(detail)
        } else if (detail.message) {
          throw new Error(detail.message)
        } else {
          throw new Error('Upload failed. Please try again.')
        }
      } else if (error.message) {
        throw new Error(error.message)
      } else {
        throw new Error('Upload failed. Please check your connection and try again.')
      }
    }
  },

  /**
   * Get all images for the current user with pagination support
   */
  async getUserImages(offset: number = 0, limit: number = 20): Promise<{
    images: UserImage[]
    total: number
    hasMore: boolean
  }> {
    // Try different pagination approaches
    const page = Math.floor(offset / limit) + 1
    logger.log(`📡 API Request: Trying page=${page}, limit=${limit} (calculated from offset=${offset})`)
    
    // Try page-based pagination first
    const response = await apiClient.get('/api/image-generation/generations', {
      params: {
        page,
        limit
      }
    })
    
    
    // Transform the response to match UserImage interface
    const images = response.data.images.map((img: any) => {
      // Determine file extension based on media_type
      const isVideo = img.media_type === 'video'
      const fileExt = isVideo ? '.mp4' : '.jpg'
      const mimeType = isVideo ? 'video/mp4' : 'image/jpeg'

      return {
        id: img.id,
        filename: img.id + fileExt,
        original_name: img.prompt.substring(0, 50) + '...',
        file_size: img.file_size || 0,
        width: img.width,
        height: img.height,
        mime_type: mimeType,
        media_type: img.media_type || 'image',  // Include media_type from API
        gcs_path: img.gcs_path || '',
        signed_url: img.signed_url || '',
        thumbnail_signed_url: img.thumbnail_signed_url || '',
        upload_date: img.created_at,
        url_expires_at: img.url_expires_at,
        prompt: img.prompt,  // Include prompt for searching/filtering
        tags: img.tags  // Include tags for searching/filtering
      }
    })

    const total = response.data.total || images.length
    const hasMore = (offset + limit) < total


    return {
      images,
      total,
      hasMore
    }
  },

  /**
   * Delete an image
   */
  async deleteImage(imageId: string): Promise<void> {
    // Use the image generation service endpoint for deletion
    await apiClient.delete(`/api/image-generation/generations/${imageId}`)
  },

  /**
   * Refresh signed URL for an image
   */
  async refreshImageUrl(imageId: string): Promise<{
    signed_url: string
    thumbnail_signed_url?: string
    expires_at: string
  }> {
    try {
      const response = await apiClient.post(`/api/image-generation/refresh-urls/${imageId}`)

      return {
        signed_url: response.data.signed_url,
        thumbnail_signed_url: response.data.thumbnail_signed_url,
        expires_at: response.data.expires_at
      }
    } catch (error: any) {
      if (error.response?.data?.detail) {
        const detail = error.response.data.detail
        if (typeof detail === 'string') {
          throw new Error(detail)
        } else if (detail.message) {
          throw new Error(detail.message)
        } else {
          throw new Error('Failed to refresh image URL')
        }
      } else if (error.message) {
        throw new Error(error.message)
      } else {
        throw new Error('Failed to refresh image URL. Please try again.')
      }
    }
  },

  /**
   * Animate an image into a video
   */
  async animateImage(
    imageId: string,
    animationPrompt: string,
    model: string = 'wan-video/wan-2.2-i2v-fast',
    resolution: string = '480p',
    endFrameImageId?: string,
    audioUrl?: string,
    duration?: number,
    aspectRatio?: string
  ): Promise<AnimateImageResult> {
    try {
      const formData = new FormData()
      formData.append('image_id', imageId)
      formData.append('animation_prompt', animationPrompt)
      formData.append('model', model)
      formData.append('resolution', resolution)
      if (endFrameImageId) {
        formData.append('end_frame_image_id', endFrameImageId)
      }
      if (audioUrl) {
        formData.append('audio_url', audioUrl)
      }
      if (duration !== undefined) {
        formData.append('duration', duration.toString())
      }
      if (aspectRatio) {
        formData.append('aspect_ratio', aspectRatio)
      }

      if (isAsyncAnimateModel(model)) {
        const startResponse = await apiClient.post('/api/image-generation/animate/start', formData, {
          headers: {
            'Content-Type': 'multipart/form-data'
          },
          timeout: 30000
        })

        const taskId = startResponse.data?.task_id
        if (!taskId) {
          throw new Error('Video animation did not return a task ID')
        }

        const maxPolls = 180 // 15 minutes at 5s
        for (let attempt = 0; attempt < maxPolls; attempt++) {
          await sleep(5000)
          const statusResponse = await apiClient.get(`/api/image-generation/animate/status/${taskId}`, {
            timeout: 30000
          })
          const status = statusResponse.data

          if (status.status === 'completed') {
            if (!status.result?.signed_url) {
              throw new Error('Video animation completed without a video URL')
            }
            return status.result
          }

          if (status.status === 'failed') {
            throw new Error(status.error || 'Video animation failed')
          }
        }

        throw new Error('Video animation is still processing. Please try again later.')
      }

      const response = await apiClient.post('/api/image-generation/animate', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        timeout: 300000 // 2 minute timeout for video generation
      })

      return response.data
    } catch (error: any) {
      if (error.response?.data?.detail) {
        const detail = error.response.data.detail
        if (typeof detail === 'string') {
          throw new Error(detail)
        } else if (detail.message) {
          throw new Error(detail.message)
        } else {
          throw new Error('Video animation failed')
        }
      } else if (error.message) {
        throw new Error(error.message)
      } else {
        throw new Error('Video animation failed. Please try again.')
      }
    }
  },

  /**
   * Generate a video directly from text (currently Gemini Omni Flash).
   */
  async generateTextVideo(
    prompt: string,
    model: string = 'gemini-omni-flash-preview',
    resolution: string = '720p',
    duration?: number,
    aspectRatio?: string
  ): Promise<AnimateImageResult> {
    try {
      const formData = new FormData()
      formData.append('prompt', prompt)
      formData.append('model', model)
      formData.append('resolution', resolution)
      if (duration !== undefined) {
        formData.append('duration', duration.toString())
      }
      if (aspectRatio) {
        formData.append('aspect_ratio', aspectRatio)
      }

      const startResponse = await apiClient.post('/api/image-generation/video/text/start', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        timeout: 30000
      })

      const taskId = startResponse.data?.task_id
      if (!taskId) {
        throw new Error('Text-to-video generation did not return a task ID')
      }

      const maxPolls = 180 // 15 minutes at 5s
      for (let attempt = 0; attempt < maxPolls; attempt++) {
        await sleep(5000)
        const statusResponse = await apiClient.get(`/api/image-generation/animate/status/${taskId}`, {
          timeout: 30000
        })
        const status = statusResponse.data

        if (status.status === 'completed') {
          if (!status.result?.signed_url) {
            throw new Error('Text-to-video generation completed without a video URL')
          }
          return status.result
        }

        if (status.status === 'failed') {
          throw new Error(status.error || 'Text-to-video generation failed')
        }
      }

      throw new Error('Text-to-video generation is still processing. Please try again later.')
    } catch (error: any) {
      if (error.response?.data?.detail) {
        const detail = error.response.data.detail
        if (typeof detail === 'string') {
          throw new Error(detail)
        } else if (detail.message) {
          throw new Error(detail.message)
        } else {
          throw new Error('Text-to-video generation failed')
        }
      } else if (error.message) {
        throw new Error(error.message)
      } else {
        throw new Error('Text-to-video generation failed. Please try again.')
      }
    }
  },

  /**
   * Save image timeline for a video project
   */
  async saveImageTimeline(request: ImageTimelineRequest): Promise<{
    message: string
    video_project_id: string
    segments_count: number
    total_duration: number
  }> {
    // TODO: Implement timeline save endpoint
    throw new Error('Image timeline save not implemented yet')
  },

  /**
   * Get image timeline for a video project
   */
  async getImageTimeline(videoProjectId: string): Promise<ImageTimelineResponse> {
    // TODO: Implement timeline get endpoint
    throw new Error('Image timeline get not implemented yet')
  },

  /**
   * Validate image files before upload
   */
  validateImages(files: File[]): { valid: boolean; errors: string[] } {
    const errors: string[] = []
    const maxFileSize = 50 * 1024 * 1024 // 50MB
    const supportedTypes = ['image/jpeg', 'image/png', 'image/webp', 'video/mp4']
    
    if (files.length === 0) {
      errors.push('No files selected')
      return { valid: false, errors }
    }

    if (files.length > 10) {
      errors.push('Maximum 10 files per upload')
      return { valid: false, errors }
    }

    files.forEach((file, index) => {
      // Check file type
      if (!supportedTypes.includes(file.type)) {
        errors.push(`File ${index + 1} (${file.name}): Unsupported format. Supported: JPEG, PNG, WebP, MP4`)
      }

      // Check file size
      if (file.size > maxFileSize) {
        const sizeMB = (file.size / (1024 * 1024)).toFixed(1)
        errors.push(`File ${index + 1} (${file.name}): Too large (${sizeMB}MB). Maximum: 50MB`)
      }

      // Check for empty files
      if (file.size === 0) {
        errors.push(`File ${index + 1} (${file.name}): File is empty`)
      }
    })

    return {
      valid: errors.length === 0,
      errors
    }
  },

  /**
   * Get file size in human readable format
   */
  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes'
    
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  },

  /**
   * Get aspect ratio from dimensions
   */
  getAspectRatio(width: number, height: number): string {
    if (!width || !height) return 'Unknown'
    
    const gcd = (a: number, b: number): number => {
      return b === 0 ? a : gcd(b, a % b)
    }
    
    const divisor = gcd(width, height)
    const aspectWidth = width / divisor
    const aspectHeight = height / divisor
    
    // Common aspect ratios
    if (aspectWidth === 16 && aspectHeight === 9) return '16:9'
    if (aspectWidth === 4 && aspectHeight === 3) return '4:3'
    if (aspectWidth === 1 && aspectHeight === 1) return '1:1'
    if (aspectWidth === 3 && aspectHeight === 2) return '3:2'
    if (aspectWidth === 9 && aspectHeight === 16) return '9:16'
    
    return `${aspectWidth}:${aspectHeight}`
  },

  /**
   * Validate timeline segments
   */
  validateTimeline(segments: ImageTimelineSegment[], totalDuration: number): { valid: boolean; errors: string[] } {
    const errors: string[] = []
    
    if (segments.length === 0) {
      errors.push('Timeline must contain at least one segment')
      return { valid: false, errors }
    }

    // Sort by start time for validation
    const sortedSegments = [...segments].sort((a, b) => a.start_time - b.start_time)
    
    let previousEnd = 0
    sortedSegments.forEach((segment, index) => {
      // Check segment validity
      if (segment.end_time <= segment.start_time) {
        errors.push(`Segment ${index + 1}: End time must be greater than start time`)
      }
      
      if (segment.start_time < 0) {
        errors.push(`Segment ${index + 1}: Start time cannot be negative`)
      }

      // Check for overlaps
      if (segment.start_time < previousEnd) {
        errors.push(`Segment ${index + 1}: Overlaps with previous segment`)
      }

      // Check for large gaps (warn only)
      if (segment.start_time > previousEnd + 1 && previousEnd > 0) {
        console.warn(`Gap detected between segments: ${previousEnd}s to ${segment.start_time}s`)
      }

      previousEnd = segment.end_time
    })

    // Check total coverage
    if (previousEnd < totalDuration * 0.9) {
      console.warn(`Timeline coverage (${previousEnd}s) is less than total duration (${totalDuration}s)`)
    }

    return {
      valid: errors.length === 0,
      errors
    }
  }
}

export default imageService
