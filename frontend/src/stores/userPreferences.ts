import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export type StoryboardVideoResolution = '720p' | '1080p' | '2k_option_1'

export interface UserPreferences {
  defaultVoiceId?: string
  defaultTtsProvider?: string
  defaultAudioSpeed?: number
  defaultMusicId?: string
  defaultMusicEnabled?: boolean
  defaultMusicVolume?: number
  defaultMusicFadeIn?: number
  defaultMusicFadeOut?: number
  defaultLanguageCode?: string
  defaultVideoAspectRatio?: '9:16' | '16:9' | '1:1'
  defaultVideoResolution?: StoryboardVideoResolution
  defaultCaptionEnabled?: boolean
  defaultCaptionPosition?: 'top' | 'center' | 'bottom'
  defaultCaptionStyle?: 'karaoke' | 'word_by_word' | 'sentence'
  defaultCaptionFont?: string
  defaultCaptionFontSize?: number
  defaultStyleTemplate?: string | null
}

export const useUserPreferencesStore = defineStore('userPreferences', () => {
  // State
  const preferences = ref<UserPreferences>({
    defaultVoiceId: undefined,
    defaultTtsProvider: 'minimax',
    defaultAudioSpeed: 1.0,
    defaultMusicId: undefined,
    defaultMusicEnabled: false,
    defaultMusicVolume: 0.1,
    defaultMusicFadeIn: 2,
    defaultMusicFadeOut: 2,
    defaultLanguageCode: undefined,
    defaultVideoAspectRatio: '9:16',
    defaultVideoResolution: '1080p',
    defaultCaptionEnabled: true,
    defaultCaptionPosition: 'bottom',
    defaultCaptionStyle: 'karaoke',
    defaultCaptionFont: 'Luckiest Guy',
    defaultCaptionFontSize: 60,
    defaultStyleTemplate: null
  })

  // Computed
  const hasDefaultVoice = computed(() => !!preferences.value.defaultVoiceId)
  const hasDefaultMusic = computed(() => {
    const result = !!preferences.value.defaultMusicId
    // console.log('Store: hasDefaultMusic computed:', result, 'musicId:', preferences.value.defaultMusicId)
    return result
  })
  const hasDefaultLanguage = computed(() => !!preferences.value.defaultLanguageCode)
  const hasDefaultStyleTemplate = computed(() => preferences.value.defaultStyleTemplate !== undefined && preferences.value.defaultStyleTemplate !== null)

  // Actions
  function loadPreferences() {
    try {
      // console.log('🔵 Store: Loading preferences from localStorage...')
      const stored = localStorage.getItem('userPreferences')
      // console.log('🔵 Store: Raw localStorage value:', stored)

      if (stored) {
        const parsed = JSON.parse(stored)
        if (parsed.defaultVideoResolution === '2k_option_2' || parsed.defaultVideoResolution === '4K') {
          parsed.defaultVideoResolution = '2k_option_1'
        }
        // console.log('🔵 Store: Parsed preferences:', parsed)
        preferences.value = { ...preferences.value, ...parsed }
        // console.log('🔵 Store: Final preferences after merge:', JSON.stringify(preferences.value))
      } else {
        // console.log('🔵 Store: No stored preferences found in localStorage')
      }
    } catch (error) {
      console.error('❌ Store: Error loading user preferences:', error)
    }
  }

  function savePreferences() {
    try {
      // console.log('🔵 Store: Saving preferences to localStorage:', JSON.stringify(preferences.value))
      localStorage.setItem('userPreferences', JSON.stringify(preferences.value))

      // Verify it was actually saved
      const verified = localStorage.getItem('userPreferences')
      // console.log('🔵 Store: Verified localStorage after save:', verified)

      if (verified) {
        const parsed = JSON.parse(verified)
        // console.log('🔵 Store: Parsed saved data:', parsed)
      }
    } catch (error) {
      console.error('❌ Store: Error saving user preferences:', error)
    }
  }

  function setDefaultVoice(voiceId: string, ttsProvider: string) {
    // console.log('🔵 Store: setDefaultVoice called with:', { voiceId, ttsProvider })
    // console.log('🔵 Store: Current preferences before update:', JSON.stringify(preferences.value))

    preferences.value.defaultVoiceId = voiceId
    preferences.value.defaultTtsProvider = ttsProvider

    // console.log('🔵 Store: Updated preferences:', JSON.stringify(preferences.value))
    savePreferences()
  }

  function setDefaultAudioSpeed(speed: number) {
    preferences.value.defaultAudioSpeed = speed
    savePreferences()
  }

  function setDefaultMusic(musicId: string, enabled: boolean = true, volume: number = 0.3) {
    // console.log('Store: Setting default music:', { musicId, enabled, volume })
    preferences.value.defaultMusicId = musicId
    preferences.value.defaultMusicEnabled = enabled
    preferences.value.defaultMusicVolume = volume
    // console.log('Store: Preferences after setting:', preferences.value)
    savePreferences()
  }

  function clearDefaultVoice() {
    preferences.value.defaultVoiceId = undefined
    preferences.value.defaultTtsProvider = 'minimax'
    savePreferences()
  }

  function clearDefaultMusic() {
    preferences.value.defaultMusicId = undefined
    preferences.value.defaultMusicEnabled = false
    savePreferences()
  }

  function setDefaultLanguage(languageCode: string) {
    // console.log('Store: Setting default language:', languageCode)
    preferences.value.defaultLanguageCode = languageCode
    // console.log('Store: Preferences after setting:', preferences.value)
    savePreferences()
  }

  function clearDefaultLanguage() {
    preferences.value.defaultLanguageCode = undefined
    savePreferences()
  }

  function setDefaultStyleTemplate(styleTemplate: string | null) {
    preferences.value.defaultStyleTemplate = styleTemplate
    savePreferences()
  }

  function clearDefaultStyleTemplate() {
    preferences.value.defaultStyleTemplate = null
    savePreferences()
  }

  function setDefaultVideoSettings(
    aspectRatio: '9:16' | '16:9' | '1:1',
    resolution: StoryboardVideoResolution,
    captionEnabled: boolean,
    captionPosition: 'top' | 'center' | 'bottom',
    captionStyle: 'karaoke' | 'word_by_word' | 'sentence',
    captionFont?: string,
    captionFontSize?: number
  ) {
    preferences.value.defaultVideoAspectRatio = aspectRatio
    preferences.value.defaultVideoResolution = resolution
    preferences.value.defaultCaptionEnabled = captionEnabled
    preferences.value.defaultCaptionPosition = captionPosition
    preferences.value.defaultCaptionStyle = captionStyle
    if (captionFont !== undefined) {
      preferences.value.defaultCaptionFont = captionFont
    }
    if (captionFontSize !== undefined) {
      preferences.value.defaultCaptionFontSize = captionFontSize
    }
    savePreferences()
  }

  function resetAllPreferences() {
    preferences.value = {
      defaultVoiceId: undefined,
      defaultTtsProvider: 'minimax',
      defaultAudioSpeed: 1.0,
      defaultMusicId: undefined,
      defaultMusicEnabled: false,
      defaultMusicVolume: 0.1,
      defaultMusicFadeIn: 2,
      defaultMusicFadeOut: 2,
      defaultLanguageCode: undefined,
      defaultVideoAspectRatio: '9:16',
      defaultVideoResolution: '1080p',
      defaultCaptionEnabled: true,
      defaultCaptionPosition: 'bottom',
      defaultCaptionStyle: 'karaoke',
      defaultCaptionFont: 'Luckiest Guy',
      defaultCaptionFontSize: 60,
      defaultStyleTemplate: null
    }
    savePreferences()
  }

  // Initialize preferences on store creation
  loadPreferences()

  return {
    preferences,
    hasDefaultVoice,
    hasDefaultMusic,
    hasDefaultLanguage,
    hasDefaultStyleTemplate,
    loadPreferences,
    savePreferences,
    setDefaultVoice,
    setDefaultAudioSpeed,
    setDefaultMusic,
    setDefaultLanguage,
    setDefaultStyleTemplate,
    setDefaultVideoSettings,
    clearDefaultVoice,
    clearDefaultMusic,
    clearDefaultLanguage,
    clearDefaultStyleTemplate,
    resetAllPreferences
  }
})
