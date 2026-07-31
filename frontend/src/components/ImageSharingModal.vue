<template>
  <div v-if="isOpen" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" @click="close">
    <div class="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto" @click.stop>
      <div class="p-6">
        <!-- Header -->
        <div class="flex items-center justify-between mb-6">
          <h3 class="text-xl font-bold text-gray-900">Share Image Publicly</h3>
          <button
            @click="close"
            class="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Image Preview -->
        <div v-if="image" class="mb-6">
          <div class="aspect-video bg-gray-100 rounded-lg overflow-hidden mb-4">
            <img
              :src="image.thumbnail_signed_url || image.signed_url"
              :alt="image.prompt"
              class="w-full h-full object-contain"
            />
          </div>
          <div class="text-sm text-gray-600 mb-2">
            <strong>Original Prompt:</strong> {{ image.prompt }}
          </div>
          <div class="text-sm text-gray-600">
            <strong>Model:</strong> {{ image.model_name }}
          </div>
        </div>

        <!-- Form -->
        <form @submit.prevent="handleSubmit">
          <!-- Title -->
          <div class="mb-4">
            <label for="title" class="block text-sm font-medium text-gray-700 mb-1">
              Title <span class="text-gray-400">(optional)</span>
            </label>
            <input
              id="title"
              v-model="form.title"
              type="text"
              placeholder="Give your image a catchy title..."
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              maxlength="100"
            />
            <div class="text-xs text-gray-500 mt-1">{{ form.title.length }}/100 characters</div>
          </div>

          <!-- Description -->
          <div class="mb-4">
            <label for="description" class="block text-sm font-medium text-gray-700 mb-1">
              Description <span class="text-gray-400">(optional)</span>
            </label>
            <textarea
              id="description"
              v-model="form.description"
              rows="3"
              placeholder="Describe your image, the inspiration behind it, or generation tips..."
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              maxlength="500"
            ></textarea>
            <div class="text-xs text-gray-500 mt-1">{{ form.description.length }}/500 characters</div>
          </div>

          <!-- Tags -->
          <div class="mb-6">
            <label for="tags" class="block text-sm font-medium text-gray-700 mb-1">
              Tags <span class="text-gray-400">(optional)</span>
            </label>
            <div class="mb-2">
              <input
                id="tags"
                v-model="currentTag"
                type="text"
                placeholder="Add tags (press Enter to add)"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                @keydown.enter.prevent="addTag"
                @keydown.comma.prevent="addTag"
                maxlength="20"
              />
              <div class="text-xs text-gray-500 mt-1">
                Press Enter or comma to add tags. Max 5 tags, 20 characters each.
              </div>
            </div>

            <!-- Selected Tags -->
            <div v-if="form.tags.length > 0" class="flex flex-wrap gap-2">
              <span
                v-for="tag in form.tags"
                :key="tag"
                class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800"
              >
                {{ tag }}
                <button
                  type="button"
                  @click="removeTag(tag)"
                  class="ml-2 text-blue-600 hover:text-blue-800"
                >
                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </span>
            </div>

            <!-- Popular Tags Suggestions -->
            <div v-if="popularTags.length > 0" class="mt-3">
              <div class="text-xs text-gray-600 mb-2">Popular tags:</div>
              <div class="flex flex-wrap gap-1">
                <button
                  v-for="tag in popularTags.slice(0, 8)"
                  :key="tag"
                  type="button"
                  @click="addPopularTag(tag)"
                  :disabled="form.tags.includes(tag) || form.tags.length >= 5"
                  class="px-2 py-1 text-xs border border-gray-300 rounded-full hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {{ tag }}
                </button>
              </div>
            </div>
          </div>

          <!-- Privacy Notice -->
          <div class="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <div class="flex items-start">
              <svg class="w-5 h-5 text-blue-600 mt-0.5 mr-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div class="text-sm text-blue-800">
                <div class="font-medium mb-1">What happens when you share publicly?</div>
                <ul class="space-y-1 text-blue-700">
                  <li>• Your image will be visible to all users in the public gallery</li>
                  <li>• Other users can copy your image to their personal galleries</li>
                  <li>• You can make your image private again at any time</li>
                  <li>• Users who already copied will keep their copies</li>
                  <li>• View and copy counts will be tracked</li>
                </ul>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center justify-end gap-3">
            <button
              type="button"
              @click="close"
              class="px-4 py-2 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              :disabled="isSubmitting"
              class="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              <svg v-if="isSubmitting" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              {{ isSubmitting ? 'Sharing...' : 'Share Publicly' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import type { GeneratedImage } from '@/api/imageGenerationService'
import publicImagesService from '@/api/publicImagesService'
import { useAuthStore } from '@/stores/auth'
import { toast } from 'vue-sonner'

interface Props {
  isOpen: boolean
  image: GeneratedImage | null
}

interface Emits {
  close: []
  success: [sharedImage: any]
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// Form data
const form = ref({
  title: '',
  description: '',
  tags: [] as string[]
})

const currentTag = ref('')
const isSubmitting = ref(false)
const popularTags = ref<string[]>([])

// Auth store
const authStore = useAuthStore()

// Computed
const isFormValid = computed(() => {
  return props.image !== null
})

// Methods
const addTag = () => {
  const tag = currentTag.value.trim().toLowerCase()
  if (tag && !form.value.tags.includes(tag) && form.value.tags.length < 5) {
    form.value.tags.push(tag)
    currentTag.value = ''
  }
}

const addPopularTag = (tag: string) => {
  if (!form.value.tags.includes(tag) && form.value.tags.length < 5) {
    form.value.tags.push(tag)
  }
}

const removeTag = (tag: string) => {
  form.value.tags = form.value.tags.filter(t => t !== tag)
}

const resetForm = () => {
  form.value = {
    title: '',
    description: '',
    tags: []
  }
  currentTag.value = ''
}

const loadPopularTags = async () => {
  try {
    const tags = await publicImagesService.getAvailableTags()
    popularTags.value = tags
  } catch (error) {
    console.error('Error loading popular tags:', error)
  }
}

const handleSubmit = async () => {
  if (!props.image || !isFormValid.value) {
    return
  }

  if (!authStore.user) {
    toast.error('Please sign in to share images')
    return
  }

  try {
    isSubmitting.value = true

    const sharedImage = await publicImagesService.makeImagePublic(
      props.image.id,
      {
        title: form.value.title || undefined,
        description: form.value.description || undefined,
        tags: form.value.tags.length > 0 ? form.value.tags : undefined
      },
      authStore.user.id
    )

    toast.success('Image shared publicly!')
    emit('success', sharedImage)
    close()
  } catch (error: any) {
    console.error('Error sharing image:', error)
    toast.error(error.message || 'Failed to share image')
  } finally {
    isSubmitting.value = false
  }
}

const close = () => {
  resetForm()
  emit('close')
}

// Auto-populate title from prompt if empty
watch(() => props.image, (newImage) => {
  if (newImage && !form.value.title) {
    // Use first 50 characters of prompt as default title
    const promptTitle = newImage.prompt?.substring(0, 50) || ''
    form.value.title = promptTitle.length === 50 ? promptTitle + '...' : promptTitle
  }
})

// Load popular tags when component mounts
onMounted(() => {
  loadPopularTags()
})

// Reset form when modal closes
watch(() => props.isOpen, (isOpen) => {
  if (!isOpen) {
    resetForm()
  }
})
</script>

<style scoped>
/* Custom scrollbar for modal */
.overflow-y-auto::-webkit-scrollbar {
  width: 8px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

/* Tag input styling */
input:focus {
  outline: none;
}

/* Smooth transitions */
.transition-colors {
  transition: color 0.2s ease, background-color 0.2s ease;
}
</style>