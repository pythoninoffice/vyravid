<template>
  <div class="group bg-white/[0.5] backdrop-blur-md border border-white/50 rounded-lg overflow-hidden flex flex-col">
    <!-- Media Section with Overlays (Top) -->
    <div class="relative w-full">
      <!-- Video Display -->
      <div v-if="isVideo.isVideo && isVideo.url" class="relative bg-black">
        <video
          :src="isVideo.url"
          class="w-full object-cover aspect-[16/9]"
          controls
          preload="metadata"
          playsinline
          title="Use controls to play video"
        />
      </div>

      <!-- Image Display -->
      <div v-else-if="scene.generatedImage && !isVideo.isVideo" class="relative">
        <img :src="scene.generatedImage.url"
          :alt="`Scene ${sceneNumber}`"
          class="w-full h-full object-cover cursor-pointer aspect-[16/9]"
          @click="$emit('open-image-modal', scene.generatedImage.url, `Scene ${sceneNumber}`)"
          title="Click to view full size" />
      </div>

      <!-- Empty Placeholder -->
      <div v-else class="bg-gray-200 flex items-center justify-center aspect-[16/9]">
        <div class="text-center text-gray-400">
          <svg class="mx-auto h-12 w-12 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 002 2v12a2 2 0 002 2z" />
          </svg>
          <span class="text-sm">No Media</span>
        </div>
      </div>

      <!-- Scene Number Badge (Top-left overlay) -->
      <div class="absolute top-1 left-10 lg:top-2 lg:left-12 z-10 bg-black/70 text-white px-2 py-0.5 rounded text-[10px] lg:text-xs font-bold leading-none">
        {{ sceneNumber }}
      </div>

      <!-- Time Range Badge (Top-right overlay) -->
      <div v-if="scene.start_time !== undefined && scene.end_time !== undefined"
        class="absolute top-1 right-1 lg:top-2 lg:right-2 z-10"
        :class="isEditingTime ? '' : 'group-hover:right-12 transition-all duration-200'">
        <!-- Edit Mode -->
        <div v-if="isEditingTime"
          ref="timeEditContainer"
          class="flex items-center gap-0.5 lg:gap-1 bg-blue-600 rounded px-0.5 lg:px-1 py-0.5"
          @click.stop
          @mousedown.stop>
          <input
            ref="startTimeInput"
            v-model.number="editStartTime"
            type="number"
            step="0.1"
            min="0"
            class="w-12 px-1 text-xs text-white bg-blue-700 rounded border border-blue-400 focus:outline-none focus:ring-1 focus:ring-white"
            @keydown.enter="saveTimeEdit"
            @keydown.esc="cancelTimeEdit"
            @blur="handleBlur"
          />
          <span class="text-white text-xs">-</span>
          <input
            ref="endTimeInput"
            v-model.number="editEndTime"
            type="number"
            step="0.1"
            min="0"
            class="w-12 px-1 text-xs text-white bg-blue-700 rounded border border-blue-400 focus:outline-none focus:ring-1 focus:ring-white"
            @keydown.enter="saveTimeEdit"
            @keydown.esc="cancelTimeEdit"
            @blur="handleBlur"
          />
          <span class="text-white text-xs">s</span>
        </div>
        <!-- Display Mode -->
        <div v-else
          @click.stop="startEditingTime"
          class="bg-black/70 text-white px-1 rounded text-[10px] lg:text-xs font-medium cursor-pointer hover:bg-black/90 transition-colors"
          title="Click to edit time">
          {{ (scene.start_time).toFixed(1) }}s - {{ (scene.end_time).toFixed(1) }}s
        </div>
      </div>

      <!-- Delete Button (Top-right overlay, appears on hover) -->
      <button
        @click.stop="$emit('delete-scene')"
        class="absolute top-1 right-1 lg:top-2 lg:right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-red-600 hover:bg-red-700 text-white rounded-full p-1 lg:p-1.5 shadow-lg z-20"
        title="Delete scene"
      >
        <svg class="w-3 h-3 lg:w-4 lg:h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>


      <!-- Character Tags (Bottom overlay) -->
      <div v-if="scene.character_ids && scene.character_ids.length > 0"
        class="absolute bottom-1 left-1 right-1 lg:bottom-2 lg:left-2 lg:right-2 flex flex-wrap gap-0.5 lg:gap-1">
        <span
          v-for="charId in scene.character_ids"
          :key="charId"
          class="inline-flex items-center px-1 lg:px-2 py-0.5 rounded-full text-[10px] lg:text-xs font-medium bg-purple-600/90 text-white backdrop-blur-sm"
          :title="getCharacterName(charId)">
          {{ getCharacterName(charId) }}
        </span>
      </div>

      <!-- Image Info -->
      <div v-if="scene.generatedImage"
        class="absolute bottom-1 right-1 lg:bottom-2 lg:right-2 text-[10px] lg:text-xs text-white">
        {{ scene.generatedImage.width }}×{{ scene.generatedImage.height }} • {{ imageAspectRatio }}
      </div>

      <!-- Image Generation Progress Overlay -->
      <div v-if="isGenerating || isAnimating" class="absolute inset-0 bg-black/80 flex flex-col items-center justify-center">
        <div class="animate-spin rounded-full h-6 w-6 lg:h-10 lg:w-10 border-2 lg:border-4 border-white border-t-transparent mb-2 lg:mb-3"></div>
        <span class="text-white text-[10px] lg:text-sm font-medium px-1">{{ isAnimating ? 'Generating Video...' : 'Generating Image...' }}</span>
        <div v-if="isGenerating && generationProgress > 0" class="w-3/4 bg-white/20 rounded-full h-1 lg:h-2 mt-2 lg:mt-3">
          <div class="bg-white h-1 lg:h-2 rounded-full transition-all duration-500"
            :style="{ width: `${generationProgress}%` }"></div>
        </div>
      </div>
    </div>

    <!-- Content Section (Bottom) -->
    <div class="p-1 lg:p-3 flex-1 flex flex-col">
      <!-- Description -->
      <p class="text-[10px] lg:text-xs text-gray-700 mb-1 lg:mb-2 line-clamp-2" v-if="scene.description">{{ scene.description }}</p>

      <!-- Editable Prompt -->
       <!-- commont out for now to remove prompt box -->
      <!-- <div class="flex-1">
        <label class="block text-xs font-medium text-gray-700 mb-1">Prompt:</label>
        <textarea :value="scene.prompt" @input="$emit('update:prompt', ($event.target as HTMLTextAreaElement)?.value ?? '')" rows="3"
          @blur="$emit('update-characters')"
          class="w-full px-2 py-1.5 text-xs border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
          placeholder="Edit your prompt here... (Use @charactername to auto-detect characters)" />
      </div> -->

      <!-- Compact Video Effects - Single Row -->
      <div class="mt-1 lg:mt-2 flex items-center gap-0.5 lg:gap-1">
        <!-- Camera Movement -->
        <div class="flex-1 min-w-0">
          <select
            :value="scene.camera_movement || 'static'"
            @change="$emit('update:camera-movement', ($event.target as HTMLSelectElement)?.value ?? 'static')"
            class="w-full text-[9px] lg:text-[10px] border border-gray-300 rounded px-0.5 py-0.5 lg:px-1.5 lg:py-1 focus:ring-1 focus:ring-purple-500 focus:border-transparent bg-white"
            title="Camera Movement"
          >
            <option value="static">📷 Static</option>
            <option value="pan_right">→ Pan Right</option>
            <option value="pan_left">← Pan Left</option>
            <option value="pan_up">↑ Pan Up</option>
            <option value="pan_down">↓ Pan Down</option>
            <option value="zoom_in">⊕ Zoom In</option>
            <option value="zoom_out">⊖ Zoom Out</option>
            <option value="doodle_slow">✏️ Doodle Slow</option>
            <option value="doodle_fast">✏️ Doodle Fast</option>
          </select>
        </div>

        <!-- Transition -->
        <div class="flex-1 min-w-0">
          <select
            :value="scene.transition_type || 'fade'"
            @change="$emit('update:transition-type', ($event.target as HTMLSelectElement)?.value ?? 'fade')"
            class="w-full text-[9px] lg:text-[10px] border border-gray-300 rounded px-0.5 py-0.5 lg:px-1.5 lg:py-1 focus:ring-1 focus:ring-purple-500 focus:border-transparent bg-white"
            title="Transition"
          >
            <option value="cut">Cut</option>
            <option value="fade">Fade</option>
            <option value="fadeblack">Fade Black</option>
            <option value="fadewhite">Fade White</option>
            <option value="distance">Distance</option>
            <option value="wipeleft">Wipe Left</option>
            <option value="wiperight">Wipe Right</option>
            <option value="wipeup">Wipe Up</option>
            <option value="wipedown">Wipe Down</option>
            <option value="slideleft">Slide Left</option>
            <option value="slideright">Slide Right</option>
            <option value="slideup">Slide Up</option>
            <option value="slidedown">Slide Down</option>
            <option value="smoothleft">Smooth Left</option>
            <option value="smoothright">Smooth Right</option>
            <option value="smoothup">Smooth Up</option>
            <option value="smoothdown">Smooth Down</option>
            <option value="circlecrop">Circle Crop</option>
            <option value="rectcrop">Rect Crop</option>
            <option value="circleclose">Circle Close</option>
            <option value="circleopen">Circle Open</option>
            <option value="horzclose">Horiz Close</option>
            <option value="horzopen">Horiz Open</option>
            <option value="vertclose">Vert Close</option>
            <option value="vertopen">Vert Open</option>
            <option value="diagbl">Diag BL</option>
            <option value="diagbr">Diag BR</option>
            <option value="diagtl">Diag TL</option>
            <option value="diagtr">Diag TR</option>
            <option value="hlslice">H Slice</option>
            <option value="hrslice">H Rev Slice</option>
            <option value="vuslice">V Up Slice</option>
            <option value="vdslice">V Down Slice</option>
            <option value="dissolve">Dissolve</option>
            <option value="pixelize">Pixelize</option>
            <option value="radial">Radial</option>
            <option value="hblur">H Blur</option>
            <option value="fadegrays">Fade Grays</option>
            <option value="wipetl">Wipe TL</option>
            <option value="wipetr">Wipe TR</option>
            <option value="wipebl">Wipe BL</option>
            <option value="wipebr">Wipe BR</option>
            <option value="squeezeh">Squeeze H</option>
            <option value="squeezev">Squeeze V</option>
            <option value="zoomin">Zoom In</option>
            <option value="fadefast">Fade Fast</option>
            <option value="fadeslow">Fade Slow</option>
          </select>
        </div>

        <!-- Greenscreen Effect -->
        <div class="flex-1 min-w-0">
          <select
            :value="scene.greenscreen_effect || ''"
            @change="$emit('update:greenscreen-effect', ($event.target as HTMLSelectElement)?.value ?? '')"
            class="w-full text-[9px] lg:text-[10px] border border-gray-300 rounded px-0.5 py-0.5 lg:px-1.5 lg:py-1 focus:ring-1 focus:ring-purple-500 focus:border-transparent bg-white"
            title="Greenscreen Effect"
          >
            <option
              v-for="effect in greenscreenEffects"
              :key="effect.value"
              :value="effect.value"
            >
              {{ effect.label }}
            </option>
          </select>
        </div>
      </div>
    </div>

    <!-- Animation Section (Admin Only) -->
    <!-- <div v-if="scene.generatedImage && showAnimation" class="mt-4 border-t p-3">
      <div class="flex items-center justify-between mb-2">
        <label class="text-sm font-medium text-gray-900">Convert to video</label>
      </div>

      <div class="mb-2">
        <label class="block text-xs font-medium text-gray-700 mb-1">Animation Model:</label>
        <select
          :value="selectedAnimationModel"
          @change="$emit('update:animation-model', ($event.target as HTMLSelectElement)?.value ?? 'runway-gen2')"
          class="w-full px-2 py-1.5 text-xs border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white"
        >
          <option v-for="model in animationModels" :key="model.value" :value="model.value">
            {{ model.label }} {{ model.recommended ? '⭐' : '' }}
          </option>
        </select>
        <p class="text-[10px] text-gray-500 mt-1">{{ getModelDescription(selectedAnimationModel) }}</p>
      </div>

      <textarea
        :value="scene.animationPrompt"
        @input="$emit('update:animationPrompt', ($event.target as HTMLTextAreaElement)?.value ?? '')"
        rows="2"
        class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-vertical mb-2"
        placeholder="Describe how you want the image to animate (e.g., 'camera slowly pans across the scene')"/>

      <div class="flex items-center gap-2">
        <Button
          @click="$emit('animate-scene')"
          :disabled="!scene.animationPrompt?.trim() || isAnimating"
          class="px-2 py-1 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm">
          {{ isAnimating ? 'Animating...' : 'Animate to Video' }}
        </Button>
        <span v-if="isAnimating" class="text-xs text-blue-600">
          This may take 30-60 seconds
        </span>
      </div>

      <div v-if="isAnimating" class="mt-2">
        <div class="flex items-center gap-2 mb-1">
          <div class="animate-spin rounded-full h-3 w-3 border-b-2 border-blue-600"></div>
          <span class="text-blue-800 text-xs">Generating video animation...</span>
        </div>
        <div class="w-full bg-blue-200 rounded-full h-1.5">
          <div class="bg-blue-600 h-1.5 rounded-full transition-all duration-500 animate-pulse"
            style="width: 50%"></div>
        </div>
      </div>

      <div v-if="scene.animatedVideo" class="mt-3 bg-gray-50 p-3 rounded border">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-medium text-gray-700">Animated Video</span>
          <span class="text-xs text-green-600">✓ Generated</span>
        </div>
        <video
          :src="scene.animatedVideo.url"
          controls
          class="w-full rounded border border-gray-200"
          style="max-height: 200px">
        </video>
        <div class="mt-2 space-y-2">
          <div class="flex justify-between items-center text-xs text-gray-500">
            <span>Duration: {{ scene.animatedVideo.duration }}s</span>
            <button @click="$emit('copy-video-url', scene.animatedVideo.url)"
              class="text-blue-600 hover:text-blue-700 hover:underline">
              Copy URL
            </button>
          </div>
          <button
            @click="$emit('add-video-to-timeline')"
            class="w-full px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium transition-colors">
            Add to Timeline
          </button>
        </div>
      </div>
    </div> -->
  </div>
</template>

<script setup lang="ts">
import { computed, ref, nextTick } from 'vue'
import { Button } from '@/components/ui/button'

interface Scene {
  description?: string
  prompt: string
  start_time?: number
  end_time?: number
  character_ids?: string[]
  generatedImage?: {
    url: string
    width: number
    height: number
  }
  animationPrompt?: string
  animationModel?: string
  animatedVideo?: {
    id: string
    url: string
    duration: number
    thumbnailUrl?: string
  }
  camera_movement?: string
  transition_type?: string
  transition_duration?: number
  greenscreen_effect?: string
}

interface Props {
  scene: Scene
  sceneNumber: number
  isGenerating?: boolean
  generationProgress?: number
  isAnimating?: boolean
  imageAspectRatio?: string
  showAnimation?: boolean
  characters?: Array<{ id: string; name: string }>
  greenscreenEffects?: Array<{ value: string; label: string }>
}

const props = withDefaults(defineProps<Props>(), {
  isGenerating: false,
  generationProgress: 0,
  isAnimating: false,
  imageAspectRatio: '16:9',
  showAnimation: false,
  characters: () => [],
  greenscreenEffects: () => [{ value: '', label: '🎬 No Effect' }]
})

const emit = defineEmits<{
  'open-image-modal': [url: string, title: string]
  'open-edit-modal': []
  'open-character-selector': []
  'generate-image': [prompt: string]
  'open-gallery-replacement': []
  'update:prompt': [value: string]
  'update:animationPrompt': [value: string]
  'update:animation-model': [value: string]
  'update-characters': []
  'animate-scene': []
  'copy-video-url': [url: string]
  'add-video-to-timeline': []
  'delete-scene': []
  'update-media': []
  'update:camera-movement': [value: string]
  'update:transition-type': [value: string]
  'update:transition-duration': [value: number]
  'update:greenscreen-effect': [value: string]
  'update:time-range': [startTime: number, endTime: number]
}>()

const getCharacterName = (charId: string) => {
  return props.characters.find(c => c.id === charId)?.name || 'Unknown'
}

// Time editing state
const isEditingTime = ref(false)
const editStartTime = ref(0)
const editEndTime = ref(0)
const startTimeInput = ref<HTMLInputElement | null>(null)
const endTimeInput = ref<HTMLInputElement | null>(null)
const timeEditContainer = ref<HTMLDivElement | null>(null)

const startEditingTime = () => {
  editStartTime.value = props.scene.start_time || 0
  editEndTime.value = props.scene.end_time || 0
  isEditingTime.value = true
  nextTick(() => {
    startTimeInput.value?.focus()
    startTimeInput.value?.select()
  })
}

const handleBlur = (event: FocusEvent) => {
  // Use setTimeout to allow the relatedTarget to be set
  setTimeout(() => {
    // Check if the new focus target is still within our time edit container
    const newFocusTarget = event.relatedTarget as HTMLElement
    if (timeEditContainer.value && !timeEditContainer.value.contains(newFocusTarget)) {
      // Focus moved outside the container, save the edit
      saveTimeEdit()
    }
  }, 0)
}

const saveTimeEdit = () => {
  if (!isEditingTime.value) return

  // Validate times
  if (editStartTime.value < 0) editStartTime.value = 0
  if (editEndTime.value < 0) editEndTime.value = 0
  if (editEndTime.value <= editStartTime.value) {
    editEndTime.value = editStartTime.value + 0.1
  }

  // Emit the update
  emit('update:time-range', editStartTime.value, editEndTime.value)
  isEditingTime.value = false
}

const cancelTimeEdit = () => {
  isEditingTime.value = false
}

// Animation models configuration (Replicate models only)
const animationModels = [
  {
    value: 'wan-video/wan-2.2-i2v-fast',
    label: 'Wan 2.2 i2v Fast',
    recommended: false,
    description: 'Wan 2.2 Image to Video Fast',
    params: { frames_per_second: 6, resolution: '480p'}
  },
  {
    value: 'gemini-omni-flash-preview',
    label: 'Gemini Omni Flash',
    recommended: false,
    description: 'Gemini Omni Flash image-to-video with native audio',
    params: { duration: 8, resolution: '720p', aspect_ratio: '16:9' }
  },
  {
    value: 'bytedance/seedance-2.0',
    label: 'Seedance 2.0',
    recommended: false,
    description: 'Multimodal video with native audio support',
    params: { fps: 24, duration: 5, resolution: '480p', aspect_ratio: '9:16', camera_fixed: false }
  },
  {
    value: 'kwaivgi/kling-v2.1',
    label: 'Kling 2.1',
    recommended: false,
    description: 'Kling 2.1 standard image-to-video',
    params: { duration: 5, resolution: '720p', mode: 'standard' }
  },
  {
    value: 'kwaivgi/kling-v2.6',
    label: 'Kling 2.6',
    recommended: false,
    description: 'Kling 2.6 image-to-video with audio disabled',
    params: { duration: 5, resolution: '720p', generate_audio: false }
  },
  {
    value: 'kwaivgi/kling-v3-video',
    label: 'Kling 3',
    recommended: false,
    description: 'Kling 3 standard image-to-video',
    params: { duration: 3, resolution: '720p', mode: 'standard', generate_audio: false }
  }
]

// Get selected animation model (default to first model if not set)
const selectedAnimationModel = computed(() => {
  return props.scene.animationModel || animationModels[0].value
})

// Get model description for display
const getModelDescription = (modelValue: string) => {
  const model = animationModels.find(m => m.value === modelValue)
  return model?.description || ''
}

// Check if the media is a video by looking at the URL
const isVideo = computed(() => {
  // First check if there's a dedicated animatedVideo
  if (props.scene.animatedVideo?.url) {
    return { isVideo: true, url: props.scene.animatedVideo.url }
  }

  // Then check if generatedImage URL is actually a video
  if (props.scene.generatedImage?.url) {
    const url = props.scene.generatedImage.url.toLowerCase()
    const isVideoFile = url.includes('.mp4') || url.includes('.webm') || url.includes('.mov') || url.includes('.avi')
    return { isVideo: isVideoFile, url: props.scene.generatedImage.url }
  }

  return { isVideo: false, url: null }
})

// Check if transition duration input should be shown
const shouldShowTransitionDuration = (transitionType: string | undefined) => {
  if (!transitionType) return false
  // Don't show duration for 'cut' transition
  return transitionType !== 'cut'
}
</script>

<style scoped>
/* Add any additional styles if needed */

.glass-effect {
  background: rgba(255, 255, 255, 0.03);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
</style>
