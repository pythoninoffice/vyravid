<template>
  <Teleport to="body">
    <div
      v-if="isOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      @click.self="handleClose"
    >
      <div
        class="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4 overflow-hidden"
        @click.stop
      >
        <!-- Header -->
        <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {{ mode === 'create' ? 'Create Folder' : 'Rename Folder' }}
          </h2>
        </div>

        <!-- Body -->
        <form @submit.prevent="handleSubmit" class="px-6 py-4 space-y-4">
          <!-- Folder Name Input -->
          <div>
            <label for="folder-name" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Folder Name
            </label>
            <input
              id="folder-name"
              v-model="folderName"
              type="text"
              maxlength="100"
              placeholder="Enter folder name"
              class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              :class="{ 'border-red-500 dark:border-red-500': validationError }"
              autofocus
            />
            <p v-if="validationError" class="mt-1 text-sm text-red-600 dark:text-red-400">
              {{ validationError }}
            </p>
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {{ folderName.length }}/100 characters
            </p>
          </div>

          <!-- Color Picker -->
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Folder Color
            </label>
            <div class="flex gap-2 flex-wrap">
              <button
                v-for="color in colorOptions"
                :key="color.value"
                type="button"
                @click="selectedColor = color.value"
                :class="[
                  'w-8 h-8 rounded-full transition-transform hover:scale-110',
                  selectedColor === color.value && 'ring-2 ring-offset-2 ring-indigo-500 dark:ring-offset-gray-800'
                ]"
                :style="{ backgroundColor: color.value }"
                :title="color.name"
              ></button>
            </div>
          </div>
        </form>

        <!-- Footer -->
        <div class="px-6 py-4 bg-gray-50 dark:bg-gray-900 flex justify-end gap-3">
          <button
            type="button"
            @click="handleClose"
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            @click="handleSubmit"
            :disabled="!canSubmit || isSubmitting"
            class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-400 dark:disabled:bg-gray-600 rounded-lg transition-colors disabled:cursor-not-allowed"
          >
            <span v-if="isSubmitting" class="flex items-center gap-2">
              <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              {{ mode === 'create' ? 'Creating...' : 'Saving...' }}
            </span>
            <span v-else>
              {{ mode === 'create' ? 'Create' : 'Save' }}
            </span>
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { ImageFolder } from '@/api/imageFoldersService'

// Props
interface Props {
  isOpen: boolean
  mode: 'create' | 'rename'
  existingFolder?: ImageFolder
  existingFolderNames: string[]
}

const props = defineProps<Props>()

// Emits
interface Emits {
  (e: 'close'): void
  (e: 'create', name: string, color: string): void
  (e: 'rename', folderId: string, name: string, color: string): void
}

const emit = defineEmits<Emits>()

// State
const folderName = ref('')
const selectedColor = ref('#6366f1')
const validationError = ref('')
const isSubmitting = ref(false)

// Color options
const colorOptions = [
  { name: 'Indigo', value: '#6366f1' },
  { name: 'Purple', value: '#8b5cf6' },
  { name: 'Pink', value: '#ec4899' },
  { name: 'Red', value: '#ef4444' },
  { name: 'Orange', value: '#f97316' },
  { name: 'Yellow', value: '#eab308' },
  { name: 'Green', value: '#22c55e' },
  { name: 'Teal', value: '#14b8a6' },
  { name: 'Blue', value: '#3b82f6' },
  { name: 'Cyan', value: '#06b6d4' },
  { name: 'Gray', value: '#6b7280' },
  { name: 'Slate', value: '#64748b' }
]

// Computed
const canSubmit = computed(() => {
  return folderName.value.trim().length > 0 && !validationError.value
})

// Validation
const validateFolderName = (name: string): string | null => {
  const trimmedName = name.trim()

  if (!trimmedName) {
    return 'Folder name cannot be empty'
  }

  if (trimmedName.length > 100) {
    return 'Folder name cannot exceed 100 characters'
  }

  // Reserved names
  const reserved = ['all images', 'uncategorized']
  if (reserved.includes(trimmedName.toLowerCase())) {
    return `"${trimmedName}" is a reserved name`
  }

  // Check for duplicates (case-insensitive)
  const isDuplicate = props.existingFolderNames.some(
    existingName =>
      existingName.toLowerCase() === trimmedName.toLowerCase() &&
      (props.mode === 'create' || existingName !== props.existingFolder?.name)
  )

  if (isDuplicate) {
    return 'A folder with this name already exists'
  }

  // Valid characters check
  const validPattern = /^[a-zA-Z0-9\s\-_]+$/
  if (!validPattern.test(trimmedName)) {
    return 'Folder name can only contain letters, numbers, spaces, hyphens, and underscores'
  }

  return null
}

// Watchers
watch(() => folderName.value, (newName) => {
  validationError.value = validateFolderName(newName) || ''
})

watch(() => props.isOpen, (isOpen) => {
  if (isOpen) {
    // Reset state when modal opens
    if (props.mode === 'rename' && props.existingFolder) {
      folderName.value = props.existingFolder.name
      selectedColor.value = props.existingFolder.color || '#6366f1'
    } else {
      folderName.value = ''
      selectedColor.value = '#6366f1'
    }
    validationError.value = ''
    isSubmitting.value = false
  }
})

// Methods
const handleClose = () => {
  if (!isSubmitting.value) {
    emit('close')
  }
}

const handleSubmit = async () => {
  const trimmedName = folderName.value.trim()
  const error = validateFolderName(trimmedName)

  if (error) {
    validationError.value = error
    return
  }

  isSubmitting.value = true

  try {
    if (props.mode === 'create') {
      emit('create', trimmedName, selectedColor.value)
    } else if (props.existingFolder) {
      emit('rename', props.existingFolder.id, trimmedName, selectedColor.value)
    }
  } finally {
    isSubmitting.value = false
  }
}

// Keyboard shortcut
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && props.isOpen) {
    handleClose()
  }
}

// Add event listener when component mounts
if (typeof window !== 'undefined') {
  window.addEventListener('keydown', handleKeydown)
}
</script>
