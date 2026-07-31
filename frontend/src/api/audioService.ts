import apiClient from './apiClient'

export interface AudioUploadResponse {
  id: string
  filename: string
  original_name: string
  file_size: number
  duration?: number
  mime_type: string
  gcs_path: string
  signed_url: string
  upload_date: string
  project_id?: string
}

export interface Voice {
  id?: string
  voice_id?: string
  name: string
  description: string
  provider: string
  gradient?: string
  sampleUrl?: string
}

export interface VoicesResponse {
  voices: Voice[]
  providers: string[]
}

export const audioService = {
  /**
   * Upload audio file
   */
  async uploadAudio(file: File, projectId?: string, languageCode?: string): Promise<AudioUploadResponse> {
    const formData = new FormData()
    formData.append('file', file)

    // Add project_id if provided
    if (projectId) {
      formData.append('project_id', projectId)
    }

    // Add language_code if provided (defaults to 'en' on backend)
    if (languageCode) {
      formData.append('language_code', languageCode)
    }

    const response = await apiClient.post('/api/audio/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      },
      // Includes local faster-whisper transcription (large-v3 can take several minutes on CPU)
      timeout: 600000 // 10 minutes
    })

    return response.data
  },

  /**
   * Get available voices for TTS
   */
  async getAvailableVoices(provider?: string): Promise<VoicesResponse> {
    const params = provider ? { provider } : {}
    const response = await apiClient.get('/api/generate/voices', { params })
    return response.data
  },

  /**
   * Refresh signed URL for an audio file
   */
  async refreshAudioUrl(audioId: string): Promise<{
    signed_url: string
    expires_at: string
  }> {
    try {
      const response = await apiClient.post(`/api/audio/refresh-url/${audioId}`)
      return response.data
    } catch (error) {
      throw new Error('Failed to refresh audio URL. Please try again.')
    }
  }
}

export default audioService