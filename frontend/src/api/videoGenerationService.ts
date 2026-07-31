import apiClient from './apiClient'

// Use the shared apiClient instead of creating a duplicate
// The shared apiClient already has:
// - Long timeout (3600000ms = 1 hour) for video processing
// - Auth token injection via request interceptor
// - Token refresh handling via response interceptor with proper locking
// - No need to duplicate any of this logic
const api = apiClient

export interface VideoGenerationRequest {
  text: string
  background_type?: 'video' | 'image' | 'image_timeline'
  background_video_url?: string
  background_image_url?: string
  image_timeline?: ImageTimelineSegment[]
  voice_id: string,
  project_title?: string
  existing_audio_id?: string
  project_id?: string
  language_code?: string  // Language code for multi-language support
  video_settings?: {
    aspect_ratio?: string
    resolution?: string
  }
  caption_settings: {
    position: string
    subtitle_style?: string
    font_size?: number
    font_family?: string
    font_file_path?: string
    // Legacy support
    fontSize?: string
    style?: string
  }
  // Music settings
  background_music_id?: string
  music_volume?: number
  music_fade_in?: number
  music_fade_out?: number
  // Xfade transition settings
  use_xfade_transitions?: boolean
  // Optional profile branding applied to final video
  include_watermark_logo?: boolean
  watermark_logo_position?: string
  watermark_logo_url?: string | null
}

export interface ImageTimelineSegment {
  image_id: string
  image_url?: string  // Will be populated from image_id
  start_time: number
  end_time: number
  transition_type?: 'cut' | 'fade' | 'slide' | 'fade' | 'fadeblack' | 'fadewhite' | 'distance' | 'wipeleft' | 'wiperight' | 'wipeup' | 'wipedown' | 'slideleft' | 'slideright' | 'slideup' | 'slidedown' | 'smoothleft' | 'smoothright' | 'smoothup' | 'smoothdown' | 'circlecrop' | 'rectcrop' | 'circleclose' | 'circleopen' | 'horzclose' | 'horzopen' | 'vertclose' | 'vertopen' | 'diagbl' | 'diagbr' | 'diagtl' | 'diagtr' | 'hlslice' | 'hrslice' | 'vuslice' | 'vdslice' | 'dissolve' | 'pixelize' | 'radial' | 'hblur' | 'wipetl' | 'wipetr' | 'wipebl' | 'wipebr' | 'fadegrays' | 'squeezev' | 'squeezeh' | 'zoomin' | 'hlwind' | 'hrwind' | 'vuwind' | 'vdwind' | 'coverleft' | 'coverright' | 'coverup' | 'coverdown' | 'revealleft' | 'revealright' | 'revealup' | 'revealdown'
  transition_duration?: number
  camera_movement?: 'static' | 'pan_right' | 'pan_left' | 'pan_up' | 'pan_down' | 'zoom_in' | 'zoom_out' | 'doodle_slow' | 'doodle_fast'
  greenscreen_effect?: string
  sort_order: number
}

export interface VideoGenerationResponse {
  videoUrl?: string  // Optional for processing responses
  audioFileId: string
  duration: number
  size: number
  status?: 'processing' | 'completed' | 'failed'
  message?: string
  job_id?: string
  project_id?: string
}

export interface GenerationProgress {
  step: string
  progress: number
  message: string
  status: 'processing' | 'completed' | 'failed'
}

// Helper function to get video URL with fallback
const getVideoUrl = async (response: any): Promise<string> => {
  const directUrl = response.data.video_url
  const projectId = response.data.project_id

  // If we already have a direct video URL, return it
  if (directUrl) {
    return directUrl
  }

  // If we have a project_id but no video_url yet, try to get project details
  if (projectId) {
    try {

      const projectResponse = await api.get(`/api/video/projects/${projectId}/details-full`)
      if (projectResponse.data.project?.gcs_signed_url) {
        return projectResponse.data.project.gcs_signed_url
      }
    } catch (error) {
      console.warn(`⚠️ Failed to get project details for ${projectId}:`, error)
      // Fall through to placeholder
    }
  }

  // Fallback to placeholder
  return '/static/placeholder-video.mp4'
}

// Keep greenscreen effects as local effect IDs. The backend resolves local assets.
const getGreenscreenEffectUrl = (effectName: string | undefined): string | undefined => {
  if (!effectName || effectName === '') {
    return undefined
  }
  return effectName
}

export interface TimelineAudioRequest {
  text: string
  voice_id: string
  project_title?: string
  tts_provider?: string
  target_duration?: number
  audio_speed?:number
  language_code?: string  // Language code for multi-language support
}

export interface TimelineAudioResponse {
  audio_file: {
    id: string
    url?: string
    file_path: string
    duration: number
    status: string
  }
  project_id: string
  message: string
}


const resolveWatermarkPayload = (request: VideoGenerationRequest) => {
  const hasWatermarkLogo = Boolean(request.watermark_logo_url)
  const includeWatermarkLogo = request.include_watermark_logo ?? hasWatermarkLogo

  return {
    include_watermark_logo: includeWatermarkLogo,
    watermark_logo_position: request.watermark_logo_position || 'bottom_right',
    watermark_logo_url: includeWatermarkLogo ? request.watermark_logo_url : undefined
  }
}

export const videoGenerationService = {

  async generateVideo(request: VideoGenerationRequest): Promise<VideoGenerationResponse> {
    try {
      
      // Log the request being sent
      // console.log('🚀 Sending video generation request:', {
      //   text_length: request.text.length,
      //   background_video_url: request.background_video_url,
      //   project_title: request.project_title,
      //   caption_settings: request.caption_settings
      // })
      
      // Build request payload based on background type
      const payload: any = {
        text: request.text,
        background_type: request.background_type || 'video',
        voice_id: request.voice_id,
        project_title: request.project_title,
        language_code: request.language_code,  // Pass language code for multi-language support
        video_settings: request.video_settings || {
          aspect_ratio: '9:16',
          resolution: '1080p'
        },
        caption_settings: {
          position: request.caption_settings.position,
          subtitle_style: request.caption_settings.subtitle_style || 'karaoke',
          font_size: request.caption_settings.font_size || 32,
          font_family: request.caption_settings.font_family || 'Luckiest Guy',
          // Legacy fallback
          ...(request.caption_settings.fontSize && { fontSize: request.caption_settings.fontSize }),
          ...(request.caption_settings.style && { style: request.caption_settings.style })
        }
      }

      const watermarkPayload = resolveWatermarkPayload(request)
      payload.include_watermark_logo = watermarkPayload.include_watermark_logo
      payload.watermark_logo_position = watermarkPayload.watermark_logo_position
      if (watermarkPayload.watermark_logo_url) {
        payload.watermark_logo_url = watermarkPayload.watermark_logo_url
      }

      // Add music parameters if provided
      if (request.background_music_id) {
        payload.background_music_id = request.background_music_id
        payload.music_volume = request.music_volume || 0.25
        payload.music_fade_in = request.music_fade_in || 2.0
        payload.music_fade_out = request.music_fade_out || 3.0
      }

      // Add background-specific fields
      if (request.background_type === 'video' || !request.background_type) {
        payload.background_video_url = request.background_video_url
      } else if (request.background_type === 'image') {
        payload.background_image_url = request.background_image_url
      } else if (request.background_type === 'image_timeline') {
        // Convert image IDs to URLs for the backend
        if (request.image_timeline && request.image_timeline.length > 0) {
          try {

            const convertedTimeline = await Promise.all(
              request.image_timeline.map(async (segment) => {
                let imageUrl = segment.image_url // Use existing URL as fallback

                // Try to get fresh signed URL, but fall back to existing URL if it fails
                if (segment.image_id) {
                  try {
                    const imageResponse = await api.post(`/api/image-generation/refresh-urls/${segment.image_id}`)
                    imageUrl = imageResponse.data.signed_url
                  } catch (refreshError: any) {
                    console.warn(`Failed to refresh URL for image ${segment.image_id}, using existing URL:`, refreshError?.message)
                    // Use the fallback URL if refresh fails
                    if (!imageUrl) {
                      throw new Error(`No URL available for image ${segment.image_id}`)
                    }
                  }
                }

                const converted = {
                  image_url: imageUrl,
                  start_time: segment.start_time,
                  end_time: segment.end_time,
                  transition_type: segment.transition_type || 'cut',
                  transition_duration: segment.transition_duration || 0,
                  camera_movement: segment.camera_movement || 'static',
                  greenscreen_effect: getGreenscreenEffectUrl(segment.greenscreen_effect)
                }
                return converted
              })
            )

            // Backend expects 'image_timeline' not 'image_timeline'
            payload.image_timeline = convertedTimeline
          } catch (error) {
            console.error('Failed to convert image IDs to URLs:', error)
            throw new Error('Failed to prepare image timeline for processing')
          }
        }
      }

      // Use the new complete video generation endpoint
      const response = await api.post('/api/video/generate-complete', payload)

      console.log('✅ Video generation completed')

      return {
        videoUrl: response.data.status === 'processing' ? undefined : await getVideoUrl(response),
        audioFileId: response.data.audio_file_id,
        duration: response.data.duration || 0,
        size: response.data.file_size || 0,
        status: response.data.status,
        message: response.data.message,
        job_id: response.data.job_id,
        project_id: response.data.project_id
      }

    } catch (error: any) {
      console.error('❌ Video generation failed:', error)
      throw error
    }
  },

  async generateVideoWithProgress(
    request: VideoGenerationRequest,
    onProgress: (progress: GenerationProgress) => void
  ): Promise<VideoGenerationResponse> {

    try {
      // Step 1: Starting
      onProgress({
        step: 'Starting video generation',
        progress: 5,
        message: 'Initializing services...',
        status: 'processing'
      })

      // Step 2: Generate audio
      onProgress({
        step: 'Generating audio',
        progress: 20,
        message: 'Converting text to speech...',
        status: 'processing'
      })

      // Step 3: Generate captions
      onProgress({
        step: 'Generating captions',
        progress: 50,
        message: 'Creating word-level timestamps...',
        status: 'processing'
      })

      // Step 4: Combine everything
      onProgress({
        step: 'Combining video',
        progress: 80,
        message: 'Merging audio, video, and captions...',
        status: 'processing'
      })

      

      // Build request payload based on background type
      const apiPayload: any = {
        text: request.text,
        background_type: request.background_type || 'video',
        voice_id: request.voice_id,
        project_title: request.project_title,
        language_code: request.language_code,  // Pass language code for multi-language support
        video_settings: request.video_settings || {
          aspect_ratio: '9:16',
          resolution: '1080p'
        },
        caption_settings: {
          position: request.caption_settings.position,
          subtitle_style: request.caption_settings.subtitle_style || 'karaoke',
          font_size: request.caption_settings.font_size || 32,
          font_family: request.caption_settings.font_family || 'Luckiest Guy',
          // Legacy fallback
          ...(request.caption_settings.fontSize && { fontSize: request.caption_settings.fontSize }),
          ...(request.caption_settings.style && { style: request.caption_settings.style })
        }
      }

      const watermarkPayload = resolveWatermarkPayload(request)
      apiPayload.include_watermark_logo = watermarkPayload.include_watermark_logo
      apiPayload.watermark_logo_position = watermarkPayload.watermark_logo_position
      if (watermarkPayload.watermark_logo_url) {
        apiPayload.watermark_logo_url = watermarkPayload.watermark_logo_url
      }

      // Add existing audio information if available
      if (request.existing_audio_id) {
        apiPayload.existing_audio_id = request.existing_audio_id
      }
      if (request.project_id) {
        apiPayload.project_id = request.project_id
      }

      // Add music parameters if provided
      if (request.background_music_id) {
        apiPayload.background_music_id = request.background_music_id
        apiPayload.music_volume = request.music_volume || 0.25
        apiPayload.music_fade_in = request.music_fade_in || 2.0
        apiPayload.music_fade_out = request.music_fade_out || 3.0
      }

      // Add background-specific fields
      if (request.background_type === 'video' || !request.background_type) {
        apiPayload.background_video_url = request.background_video_url
      } else if (request.background_type === 'image') {
        apiPayload.background_image_url = request.background_image_url
      } else if (request.background_type === 'image_timeline') {
        // Convert image IDs to URLs for the backend
        if (request.image_timeline && request.image_timeline.length > 0) {
          try {
            const convertedTimeline = await Promise.all(
              request.image_timeline.map(async (segment) => {
                let imageUrl = segment.image_url // Use existing URL as fallback

                // Try to get fresh signed URL, but fall back to existing URL if it fails
                if (segment.image_id) {
                  try {
                    const imageResponse = await api.post(`/api/image-generation/refresh-urls/${segment.image_id}`)
                    imageUrl = imageResponse.data.signed_url
                  } catch (refreshError: any) {
                    console.warn(`Failed to refresh URL for image ${segment.image_id}, using existing URL:`, refreshError?.message)
                    if (!imageUrl) {
                      throw new Error(`No URL available for image ${segment.image_id}`)
                    }
                  }
                }

                return {
                  image_id: segment.image_id,
                  image_url: imageUrl,
                  start_time: segment.start_time,
                  end_time: segment.end_time,
                  transition_type: segment.transition_type || 'cut',
                  transition_duration: segment.transition_duration || 0,
                  camera_movement: segment.camera_movement || 'static',
                  greenscreen_effect: getGreenscreenEffectUrl(segment.greenscreen_effect)
                }
              })
            )
            // Backend expects 'image_timeline' not 'image_timeline'
            apiPayload.image_timeline = convertedTimeline

            //pass the use_xfade_transitions to final payload
            apiPayload.use_xfade_transitions = request.use_xfade_transitions
          } catch (error) {
            console.error('Failed to convert image IDs to URLs:', error)
            throw new Error('Failed to prepare image timeline for processing')
          }
        }
      }
      console.log('actual payload')
      console.log(apiPayload)
      // Make the actual API call
      const response = await api.post('/api/video/generate-complete', apiPayload)
      const isProcessing = response.data.status === 'processing'

      if (isProcessing) {
        onProgress({
          step: 'Video processing started',
          progress: 90,
          message: response.data.message || 'Video is rendering...',
          status: 'processing'
        })
      } else {
        onProgress({
          step: 'Video completed',
          progress: 100,
          message: 'Video generation successful!',
          status: 'completed'
        })
      }

      return {
        videoUrl: isProcessing ? undefined : await getVideoUrl(response),
        audioFileId: response.data.audio_file_id,
        duration: response.data.duration || 0,
        size: response.data.file_size || 0,
        status: response.data.status,
        message: response.data.message,
        job_id: response.data.job_id,
        project_id: response.data.project_id
      }

    } catch (error: any) {
      onProgress({
        step: 'Generation failed',
        progress: 0,
        message: error instanceof Error ? error.message : 'Video generation failed',
        status: 'failed'
      })
      throw error
    }
  },

  // Fallback method using test processing
  async generateVideoFallback(request: VideoGenerationRequest): Promise<VideoGenerationResponse> {
    try {
      console.log('🔄 Using fallback video generation method...')
      
      // Build fallback request payload
      const fallbackPayload: any = {
        text: request.text,
        background_type: request.background_type || 'video',
        voice_id: request.voice_id,
        project_title: request.project_title,
        video_settings: request.video_settings || {
          aspect_ratio: '9:16',
          resolution: '1080p'
        },
        caption_settings: request.caption_settings
      }

      const watermarkPayload = resolveWatermarkPayload(request)
      fallbackPayload.include_watermark_logo = watermarkPayload.include_watermark_logo
      fallbackPayload.watermark_logo_position = watermarkPayload.watermark_logo_position
      if (watermarkPayload.watermark_logo_url) {
        fallbackPayload.watermark_logo_url = watermarkPayload.watermark_logo_url
      }

      // Add music parameters if provided
      if (request.background_music_id) {
        fallbackPayload.background_music_id = request.background_music_id
        fallbackPayload.music_volume = request.music_volume || 0.25
        fallbackPayload.music_fade_in = request.music_fade_in || 2.0
        fallbackPayload.music_fade_out = request.music_fade_out || 3.0
      }

      // Add background-specific fields
      if (request.background_type === 'video' || !request.background_type) {
        fallbackPayload.background_video_url = request.background_video_url
      } else if (request.background_type === 'image') {
        fallbackPayload.background_image_url = request.background_image_url
      } else if (request.background_type === 'image_timeline') {
        // Convert image IDs to URLs for the backend
        if (request.image_timeline && request.image_timeline.length > 0) {
          try {
            const convertedTimeline = await Promise.all(
              request.image_timeline.map(async (segment) => {
                let imageUrl = segment.image_url // Use existing URL as fallback

                // Try to get fresh signed URL, but fall back to existing URL if it fails
                if (segment.image_id) {
                  try {
                    const imageResponse = await api.post(`/api/image-generation/refresh-urls/${segment.image_id}`)
                    imageUrl = imageResponse.data.signed_url
                  } catch (refreshError: any) {
                    console.warn(`Failed to refresh URL for image ${segment.image_id}, using existing URL:`, refreshError?.message)
                    if (!imageUrl) {
                      throw new Error(`No URL available for image ${segment.image_id}`)
                    }
                  }
                }

                return {
                  image_url: imageUrl,
                  start_time: segment.start_time,
                  end_time: segment.end_time,
                  transition_type: segment.transition_type || 'cut',
                  transition_duration: segment.transition_duration || 0,
                  camera_movement: segment.camera_movement || 'static',
                  greenscreen_effect: getGreenscreenEffectUrl(segment.greenscreen_effect)
                }
              })
            )
            // Backend expects 'image_timeline' not 'image_timeline'
            fallbackPayload.image_timeline = convertedTimeline
          } catch (error) {
            console.error('Failed to convert image IDs to URLs:', error)
            throw new Error('Failed to prepare image timeline for processing')
          }
        }
      }

      // Use the test processing endpoint
      const response = await api.post('/api/video/test-processing', fallbackPayload)

      return {
        videoUrl: response.data.video_url || '/static/test_output.mp4',
        audioFileId: response.data.audio_file_id || 'fallback_audio',
        duration: response.data.duration || 60,
        size: response.data.file_size || 10 * 1024 * 1024
      }

    } catch (error) {
      console.error('❌ Fallback video generation failed:', error)
      throw error
    }
  },

  async generateAudioForTimeline(request: TimelineAudioRequest): Promise<TimelineAudioResponse> {
    try {

      const response = await api.post('/api/generate/audio-for-timeline', request)

      return response.data as TimelineAudioResponse

    } catch (error: any) {
      console.error('❌ Audio generation for timeline failed:', error)
      throw error
    }
  }
}
