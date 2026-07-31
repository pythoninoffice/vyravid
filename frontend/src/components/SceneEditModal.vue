<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 overflow-y-auto"
    @click.self="handleClose"
  >
    <!-- Backdrop -->
    <div class="fixed inset-0 bg-black bg-opacity-50 transition-opacity"></div>

    <!-- Modal -->
    <div class="flex min-h-screen items-center justify-center p-4">
      <div
        class="relative bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col"
        @click.stop
      >
        <!-- Header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 class="text-xl font-bold text-gray-900">
            Edit Scene {{ sceneNumber }}
          </h2>
          <button
            @click="handleClose"
            class="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 overflow-y-auto p-6 space-y-4">
          <!-- Scene Description -->
          <div v-if="scene.description">
            <label class="block text-sm font-medium text-gray-700 mb-2">Scene Description</label>
            <div class="bg-gray-50 rounded-lg p-4 border border-gray-200">
              <p class="text-sm text-gray-700">{{ scene.description }}</p>
            </div>
          </div>

          <!-- Image Generation Section -->
          <div class="border border-gray-200 rounded-lg p-4 bg-gray-50">
            <h3 class="text-base font-semibold text-gray-900 mb-3">Image Generation</h3>

            <!-- Prompt -->
            <div class="mb-3">
              <label class="block text-sm font-medium text-gray-700 mb-2">Prompt</label>
              <textarea
                v-model="localPrompt"
                rows="4"
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-vertical"
                placeholder="Enter your image generation prompt..."
              ></textarea>
            </div>

            <!-- Image Model Selection -->
            <div class="mb-3">
              <label class="block text-sm font-medium text-gray-700 mb-2">Image Model</label>
              <select
                v-model="selectedImageModel"
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
              >
                <option value="">Select a model...</option>
                <option
                  v-for="model in imageModels"
                  :key="model.id"
                  :value="model.id"
                >
                  {{ model.name }}
                </option>
              </select>
            </div>

            <!-- Generate Image Button -->
            <div class="flex items-center gap-3">
              <Button
                @click="handleGenerateImage"
                :disabled="!localPrompt.trim() || !selectedImageModel || isGeneratingImage"
                class="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm flex items-center gap-2"
              >
                <div v-if="isGeneratingImage" class="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                {{ isGeneratingImage ? 'Generating...' : 'Generate Image' }}
              </Button>
              <span v-if="isGeneratingImage" class="text-xs text-gray-600">
                This may take 10-30 seconds
              </span>
            </div>

            <!-- Generated Image Preview -->
            <div v-if="generatedImageUrl" class="mt-4">
              <label class="block text-sm font-medium text-gray-700 mb-2">Generated Image</label>
              <div class="relative rounded-lg overflow-hidden border border-gray-200">
                <img
                  :src="generatedImageUrl"
                  alt="Generated image"
                  class="w-full h-auto"
                />
              </div>
            </div>
          </div>

          <!-- Video Generation Section -->
          <div class="border border-gray-200 rounded-lg p-4 bg-gray-50">
            <h3 class="text-base font-semibold text-gray-900 mb-3">Video Generation</h3>

            <!-- Video Model Selection -->
            <div class="mb-3">
              <label class="block text-sm font-medium text-gray-700 mb-2">Video Model</label>
              <select
                v-model="selectedVideoModel"
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="wan-video/wan-2.2-i2v-fast">Wan 2.2</option>
                <option value="gemini-omni-flash-preview">Gemini Omni Flash</option>
                <option value="hailuo-video/hailuo2-fast">Hailuo 2 Fast</option>
                <option value="hailuo-video/hailuo2.3">Hailuo 2.3</option>
                <option value="kling-video/kling2.1">Kling 2.1</option>
                <option value="kling-video/kling2.3">Kling 2.3</option>
              </select>
            </div>

            <!-- Animation Prompt -->
            <div class="mb-3">
              <label class="block text-sm font-medium text-gray-700 mb-2">Animation Description</label>
              <textarea
                v-model="localAnimationPrompt"
                rows="3"
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-vertical"
                placeholder="Describe how you want the image to animate (e.g., 'camera slowly pans across the scene')"
              ></textarea>
            </div>

            <!-- Generate Video Button -->
            <div class="flex items-center gap-3">
              <Button
                @click="handleGenerateVideo"
                :disabled="!generatedImageUrl && !scene.generatedImage || !localAnimationPrompt.trim() || isGeneratingVideo"
                class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm flex items-center gap-2"
              >
                <div v-if="isGeneratingVideo" class="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                {{ isGeneratingVideo ? 'Generating...' : 'Generate Video' }}
              </Button>
              <span v-if="isGeneratingVideo" class="text-xs text-gray-600">
                This may take 30-60 seconds
              </span>
            </div>

            <!-- Generated Video Preview -->
            <div v-if="generatedVideoUrl" class="mt-4">
              <label class="block text-sm font-medium text-gray-700 mb-2">Generated Video</label>
              <div class="relative rounded-lg overflow-hidden border border-gray-200 bg-black">
                <video
                  :src="generatedVideoUrl"
                  controls
                  class="w-full h-auto"
                  style="max-height: 400px"
                ></video>
              </div>
              <div class="mt-2 flex gap-2">
                <Button
                  @click="$emit('add-video-to-timeline', generatedVideoUrl)"
                  class="px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm"
                >
                  Add to Timeline
                </Button>
              </div>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
          <Button
            @click="handleClose"
            class="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            Close
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Button } from '@/components/ui/button'

interface Scene {
  description?: string
  prompt: string
  character_ids?: string[]
  generatedImage?: {
    url: string
    width: number
    height: number
  }
  animationPrompt?: string
}

interface ImageModel {
  id: string
  name: string
  description?: string
}

interface Props {
  isOpen: boolean
  scene: Scene
  sceneNumber: number
  imageModels?: ImageModel[]
}

const props = withDefaults(defineProps<Props>(), {
  imageModels: () => []
})

const emit = defineEmits<{
  close: []
  'generate-image': [prompt: string, model: string]
  'generate-video': [animationPrompt: string, model: string]
  'add-video-to-timeline': [videoUrl: string]
}>()

// Local state
const localPrompt = ref('')
const localAnimationPrompt = ref('')
const selectedImageModel = ref('')
const selectedVideoModel = ref('wan-video/wan-2.2-i2v-fast')
const isGeneratingImage = ref(false)
const isGeneratingVideo = ref(false)
const generatedImageUrl = ref('')
const generatedVideoUrl = ref('')

// Watch for scene changes
watch(() => props.scene, (newScene) => {
  if (newScene) {
    localPrompt.value = newScene.prompt || ''
    localAnimationPrompt.value = newScene.animationPrompt || ''
    if (newScene.generatedImage) {
      generatedImageUrl.value = newScene.generatedImage.url
    }
  }
}, { immediate: true })

// Watch for modal open/close
watch(() => props.isOpen, (isOpen) => {
  if (isOpen) {
    // Reset state when opening
    localPrompt.value = props.scene.prompt || ''
    localAnimationPrompt.value = props.scene.animationPrompt || ''
    generatedImageUrl.value = props.scene.generatedImage?.url || ''
    generatedVideoUrl.value = ''
    isGeneratingImage.value = false
    isGeneratingVideo.value = false

    // Set default model if available
    if (props.imageModels.length > 0 && !selectedImageModel.value) {
      selectedImageModel.value = props.imageModels[0].id
    }
  }
})

function handleClose() {
  emit('close')
}

async function handleGenerateImage() {
  if (!localPrompt.value.trim() || !selectedImageModel.value) return

  isGeneratingImage.value = true
  try {
    emit('generate-image', localPrompt.value, selectedImageModel.value)
  } finally {
    // The parent component will handle setting isGeneratingImage to false
  }
}

async function handleGenerateVideo() {
  if (!localAnimationPrompt.value.trim()) return

  isGeneratingVideo.value = true
  try {
    emit('generate-video', localAnimationPrompt.value, selectedVideoModel.value)
  } finally {
    // The parent component will handle setting isGeneratingVideo to false
  }
}

// Expose methods for parent to call
defineExpose({
  setGeneratedImage: (url: string) => {
    generatedImageUrl.value = url
    isGeneratingImage.value = false
  },
  setGeneratedVideo: (url: string) => {
    generatedVideoUrl.value = url
    isGeneratingVideo.value = false
  },
  setGeneratingImage: (value: boolean) => {
    isGeneratingImage.value = value
  },
  setGeneratingVideo: (value: boolean) => {
    isGeneratingVideo.value = value
  }
})
</script>
