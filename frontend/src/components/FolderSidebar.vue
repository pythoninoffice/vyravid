<template>
  <div
    class="w-42 border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 flex flex-col h-full"
  >
    <!-- Header -->
    <div class="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">
        Folders
      </h3>
      <button
        @click="$emit('create-folder')"
        class="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
        title="Create new folder"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
      </button>
    </div>

    <!-- Folder List -->
    <div class="flex-1 overflow-y-auto">
      <!-- Loading State -->
      <div v-if="loading" class="p-4 space-y-3">
        <div v-for="i in 3" :key="i" class="animate-pulse">
          <div class="h-9 bg-gray-200 dark:bg-gray-700 rounded"></div>
        </div>
      </div>

      <!-- Folders -->
      <div v-else class="py-2">
        <!-- All Images -->
        <button
          @click="$emit('select-folder', null)"
          :class="[
            'w-full px-4 py-2.5 flex items-center justify-between text-left transition-colors',
            selectedFolderId === null
              ? 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400 font-medium'
              : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
          ]"
        >
          <div class="flex items-center gap-2 min-w-0 flex-1">
            <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <span class="text-sm truncate">All Images</span>
          </div>
          <span class="text-xs px-2 py-0.5 rounded-full bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400">
            {{ totalCount }}
          </span>
        </button>

        <!-- Uncategorized -->
        <button
          v-if="uncategorizedCount > 0"
          @click="$emit('select-folder', 'uncategorized')"
          :class="[
            'w-full px-4 py-2.5 flex items-center justify-between text-left transition-colors',
            selectedFolderId === 'uncategorized'
              ? 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400 font-medium'
              : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
          ]"
          @dragover.prevent="handleDragOver($event, 'uncategorized')"
          @dragleave="handleDragLeave"
          @drop.prevent="handleDrop($event, null)"
        >
          <div class="flex items-center gap-2 min-w-0 flex-1">
            <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
            <span class="text-sm italic truncate">Uncategorized</span>
          </div>
          <span class="text-xs px-2 py-0.5 rounded-full bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400">
            {{ uncategorizedCount }}
          </span>
        </button>

        <!-- Divider -->
        <div v-if="folders.length > 0" class="my-2 border-t border-gray-200 dark:border-gray-700"></div>

        <!-- User Folders -->
        <div
          v-for="folder in folders"
          :key="folder.id"
          class="group relative"
          @dragover.prevent="handleDragOver($event, folder.id)"
          @dragleave="handleDragLeave"
          @drop.prevent="handleDrop($event, folder.id)"
        >
          <button
            @click="$emit('select-folder', folder.id)"
            :class="[
              'w-full px-4 py-2.5 flex items-center justify-between text-left transition-colors',
              selectedFolderId === folder.id
                ? 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400 font-medium'
                : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700',
              dragOverFolderId === folder.id && 'ring-2 ring-indigo-500 ring-inset bg-indigo-50 dark:bg-indigo-900/30'
            ]"
          >
            <div class="flex items-center gap-2 min-w-0 flex-1">
              <div
                class="w-3 h-3 rounded-full flex-shrink-0"
                :style="{ backgroundColor: folder.color || '#6366f1' }"
              ></div>
              <span class="text-sm truncate">{{ folder.name }}</span>
            </div>
            <span class="text-xs px-2 py-0.5 rounded-full bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400">
              {{ folder.image_count }}
            </span>
          </button>

          <!-- Folder Actions (on hover) -->
          <div class="absolute right-2 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-1">
            <button
              @click.stop="$emit('rename-folder', folder.id, folder.name)"
              class="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-600 dark:text-gray-400"
              title="Rename folder"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </button>
            <button
              @click.stop="$emit('delete-folder', folder.id)"
              class="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-red-600 dark:text-red-400"
              title="Delete folder"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>

        <!-- Empty State -->
        <div v-if="folders.length === 0" class="px-4 py-8 text-center">
          <svg class="w-12 h-12 mx-auto text-gray-400 dark:text-gray-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
          </svg>
          <p class="text-sm text-gray-600 dark:text-gray-400 mb-3">No folders yet</p>
          <button
            @click="$emit('create-folder')"
            class="text-sm text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 font-medium"
          >
            Create your first folder
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { ImageFolder } from '@/api/imageFoldersService'

// Props
interface Props {
  folders: ImageFolder[]
  selectedFolderId: string | null
  uncategorizedCount: number
  totalCount: number
  loading: boolean
}

defineProps<Props>()

// Emits
interface Emits {
  (e: 'select-folder', folderId: string | null): void
  (e: 'create-folder'): void
  (e: 'rename-folder', folderId: string, currentName: string): void
  (e: 'delete-folder', folderId: string): void
  (e: 'drop-image', imageId: string, folderId: string | null): void
}

const emit = defineEmits<Emits>()

// Drag & Drop State
const dragOverFolderId = ref<string | null>(null)

const handleDragOver = (event: DragEvent, folderId: string) => {
  event.preventDefault()
  dragOverFolderId.value = folderId
}

const handleDragLeave = () => {
  dragOverFolderId.value = null
}

const handleDrop = (event: DragEvent, folderId: string | null) => {
  event.preventDefault()
  dragOverFolderId.value = null

  // Check for multiple images first
  const imageIdsJson = event.dataTransfer?.getData('image-ids')
  if (imageIdsJson) {
    try {
      const imageIds = JSON.parse(imageIdsJson)
      emit('drop-image', imageIds, folderId)
      return
    } catch (e) {
      console.error('Failed to parse image IDs:', e)
    }
  }

  // Fall back to single image
  const imageId = event.dataTransfer?.getData('image-id')
  if (imageId) {
    emit('drop-image', imageId, folderId)
  }
}
</script>
