import apiClient from './apiClient'

export interface TextLayerData {
  id?: string
  text: string
  startTime: number
  endTime: number
  x?: number
  y?: number
  fontSize?: number
  fontColor?: string
  fontWeight?: string
  fontFamily?: string
  backgroundColor?: string
  animation?: string
}

export interface SaveTextLayersResponse {
  project_id: string
  text_layers_count: number
  message: string
}

export interface LoadTextLayersResponse {
  project_id: string
  text_layers: TextLayerData[]
  text_layers_count: number
}

export interface SceneData {
  id?: string  // Scene UUID - preserved across save/load
  scene_index: number
  description: string
  prompt: string
  scene_type?: 'dialogue' | 'monologue' | 'broll' | 'mixed'
  scene_script?: string
  layout_type?: 'single' | 'two_shot' | 'group' | 'speaker_focus'
  target_duration?: number
  start_time?: number
  end_time?: number
  character_ids?: string[]
  dialogue_turns?: Array<{
    id?: string
    speaker_id?: string
    speaker_label?: string
    text: string
    voice_id?: string
    voice_override?: boolean
    provider?: 'minimax' | 'deepgram' | 'google' | 'elevenlabs'
    audio_speed?: number
    start_time?: number
    end_time?: number
    duration?: number
    visual_state?: string
  }>
  character_layout?: Array<{
    character_id?: string
    slot?: string
    x?: number
    y?: number
    scale?: number
    z_index?: number
  }>
  generated_image?: {
    id?: string
    url: string
    width: number
    height: number
    aspectRatio: string
  }
  animation_prompt?: string
  animated_video?: {
    id: string
    url: string
    duration: number
    thumbnailUrl?: string
  }
  camera_movement?: string
  transition_type?: string
  transition_duration?: number
  greenscreen_effect?: string
  scene_audio?: {
    file_id?: string
    url: string
    duration: number
    transcript?: string
  }
  text_layers?: any[]
}

export interface SaveProjectScenesResponse {
  project_id: string
  scenes_count: number
  message: string
}

export interface LoadProjectScenesResponse {
  project_id: string
  scenes: any[]
  scenes_count: number
}

export interface GenerateSceneAudioRequest {
  tts_provider: 'minimax' | 'deepgram' | 'google' | 'elevenlabs'
  default_voice_id: string
  audio_speed?: number
  language_code?: string
  character_voice_map?: Record<string, {
    voice_id: string
    provider: 'minimax' | 'deepgram' | 'google' | 'elevenlabs'
    audio_speed?: number
  }>
}

export interface GenerateSceneAudioResponse {
  project_id: string
  scenes: any[]
  combined_audio?: {
    file_id?: string
    url: string
    duration: number
  } | null
  generated_count: number
  message: string
}

export interface AdjustSceneAudioSpeedRequest {
  audio_speed: number
  current_audio_speed?: number
  language_code?: string
}

export interface AdjustSceneAudioSpeedResponse {
  project_id: string
  audio_speed: number
  duration_scale: number
  scenes: any[]
  combined_audio?: {
    file_id?: string
    url: string
    duration: number
  } | null
  updated_transcript_files?: string[]
  message: string
}

export interface TalkingScenePromptRequest {
  scenes: Array<{
    scene_id: string
    scene_index: number
    scene_type?: 'dialogue' | 'monologue' | 'broll' | 'mixed'
    scene_script: string
    description?: string
    layout_type?: 'single' | 'two_shot' | 'group' | 'speaker_focus'
    character_names?: string[]
    dialogue_turns?: Array<{
      speaker_id?: string
      speaker_label?: string
      text: string
    }>
  }>
  language_code?: string
}

export interface TalkingScenePromptResponse {
  scenes: Array<{
    scene_id: string
    prompt: string
  }>
  total_scenes: number
}

export interface AnimalHaircutPromptRequest {
  animal: string
  haircut_style: string
}

export interface AnimalHaircutPromptResponse {
  animal_name: string
  haircut_style: string
  haircut_description: string
  animal_appearance_details: string
  first_image_prompt: string
  second_image_prompt: string
  video_prompt: string
}

/**
 * Save scenes for a project
 * @param projectId - The UUID of the project
 * @param scenes - Array of scene data to save
 * @returns Response with saved scenes count
 */
export async function saveProjectScenes(
  projectId: string,
  scenes: SceneData[]
): Promise<SaveProjectScenesResponse> {
  try {
    const response = await apiClient.post<SaveProjectScenesResponse>('/api/scenes/save', {
      project_id: projectId,
      scenes
    })
    return response.data
  } catch (error: any) {
    const errorMessage = error.response?.data?.detail || error.message || 'Failed to save scenes'
    throw new Error(errorMessage)
  }
}

/**
 * Load scenes for a project
 * @param projectId - The UUID of the project
 * @returns Response with array of scenes
 */
export async function loadProjectScenes(projectId: string): Promise<LoadProjectScenesResponse> {
  try {
    const response = await apiClient.get<LoadProjectScenesResponse>(`/api/scenes/${projectId}`)
    return response.data
  } catch (error: any) {
    const errorMessage = error.response?.data?.detail || error.message || 'Failed to load scenes'
    throw new Error(errorMessage)
  }
}

export async function generateProjectSceneAudio(
  projectId: string,
  payload: GenerateSceneAudioRequest
): Promise<GenerateSceneAudioResponse> {
  try {
    const response = await apiClient.post<GenerateSceneAudioResponse>(`/api/scenes/${projectId}/generate-audio`, payload)
    return response.data
  } catch (error: any) {
    const errorMessage = error.response?.data?.detail || error.message || 'Failed to generate scene audio'
    throw new Error(errorMessage)
  }
}

export async function adjustProjectSceneAudioSpeed(
  projectId: string,
  payload: AdjustSceneAudioSpeedRequest
): Promise<AdjustSceneAudioSpeedResponse> {
  try {
    const response = await apiClient.post<AdjustSceneAudioSpeedResponse>(`/api/scenes/${projectId}/adjust-audio-speed`, payload)
    return response.data
  } catch (error: any) {
    const errorMessage = error.response?.data?.detail || error.message || 'Failed to adjust audio speed'
    throw new Error(errorMessage)
  }
}

export async function generateTalkingScenePrompts(
  payload: TalkingScenePromptRequest
): Promise<TalkingScenePromptResponse> {
  try {
    const response = await apiClient.post<TalkingScenePromptResponse>('/api/scene-generation/generate-talking-scene-prompts', payload)
    return response.data
  } catch (error: any) {
    const errorMessage = error.response?.data?.detail || error.message || 'Failed to generate talking-scene prompts'
    throw new Error(errorMessage)
  }
}

export async function generateAnimalHaircutPrompts(
  payload: AnimalHaircutPromptRequest
): Promise<AnimalHaircutPromptResponse> {
  try {
    const response = await apiClient.post<AnimalHaircutPromptResponse>('/api/scene-generation/generate-animal-haircut-prompts', payload)
    return response.data
  } catch (error: any) {
    const errorMessage = error.response?.data?.detail || error.message || 'Failed to generate animal haircut prompts'
    throw new Error(errorMessage)
  }
}

export async function saveProjectTextLayers(
  projectId: string,
  textLayers: TextLayerData[]
): Promise<SaveTextLayersResponse> {
  try {
    const response = await apiClient.post<SaveTextLayersResponse>('/api/scenes/text-layers/save', {
      project_id: projectId,
      text_layers: textLayers
    })
    return response.data
  } catch (error: any) {
    const errorMessage = error.response?.data?.detail || error.message || 'Failed to save text layers'
    throw new Error(errorMessage)
  }
}

export async function loadProjectTextLayers(projectId: string): Promise<LoadTextLayersResponse> {
  try {
    const response = await apiClient.get<LoadTextLayersResponse>(`/api/scenes/text-layers/${projectId}`)
    return response.data
  } catch (error: any) {
    const errorMessage = error.response?.data?.detail || error.message || 'Failed to load text layers'
    throw new Error(errorMessage)
  }
}
