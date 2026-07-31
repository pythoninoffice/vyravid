<template>
  <div class="image-gallery flex h-full">
    <!-- Folder Sidebar -->
    <FolderSidebar
      v-if="showFolders"
      :folders="folders"
      :selected-folder-id="selectedFolderId"
      :uncategorized-count="uncategorizedCount"
      :total-count="totalImages"
      :loading="foldersLoading"
      @select-folder="handleSelectFolder"
      @create-folder="openCreateFolderModal"
      @rename-folder="openRenameFolderModal"
      @delete-folder="handleDeleteFolder"
      @drop-image="handleDropImageOnFolder"
    />

    <!-- Main Gallery Area -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <!-- Image Modal -->
    <ImageModal
      :image="selectedImage"
      :is-open="isModalOpen"
      :images="displayedImages"
      :current-index="currentImageIndex"
      @close="closeModal"
      @download="downloadImage"
      @delete="handleDeleteFromModal"
      @navigate="handleNavigate"
      @create-character="handleCreateCharacter"
    />

      <!-- Gallery Header -->
      <div class="flex items-center justify-between mb-2 px-6 pt-3">
        <div>
          <h3 class="text-lg font-medium text-gray-900 dark:text-gray-100">
            {{ currentFolderName }}
          </h3>
          <p class="text-sm text-gray-600 dark:text-gray-400">
            {{ totalImages }} image{{ totalImages !== 1 ? 's' : '' }}
          </p>
        </div>

        <!-- View Options -->
        <div class="flex items-center gap-2">
        <!-- Selection Actions -->
        <button
          v-if="!hasSelection"
          @click="selectAll"
          class="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          title="Select all"
        >
          Select All
        </button>
        <button
          v-if="hasSelection"
          @click="clearSelection"
          class="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          title="Clear selection"
        >
          Clear ({{ selectedCount }})
        </button>
        <button
          v-if="hasSelection"
          @click="confirmBatchDelete"
          class="px-3 py-1.5 text-sm text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors flex items-center gap-1.5"
          title="Delete selected images"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
          Delete ({{ selectedCount }})
        </button>

        <button
          @click="viewMode = 'grid'"
          :class="[
            'p-2 rounded-lg transition-colors',
            viewMode === 'grid' ? 'bg-orange-100 text-orange-600' : 'text-gray-400 hover:text-gray-600'
          ]"
          title="Grid view"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
        </button>
        <button
          @click="viewMode = 'list'"
          :class="[
            'p-2 rounded-lg transition-colors',
            viewMode === 'list' ? 'bg-orange-100 text-orange-600' : 'text-gray-400 hover:text-gray-600'
          ]"
          title="List view"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
          </svg>
        </button>
        </div>
      </div>

      <!-- Selection Hint Banner -->
      <div class="px-6 pb-4">
        <div class="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg px-4 py-2 text-sm text-blue-800 dark:text-blue-300">
          <span class="font-medium">Tip:</span> Click and drag to select multiple images, or use Ctrl+Click. Then drag selected images to folders.
        </div>
      </div>

      <!-- Gallery Content Container -->
      <div
        ref="galleryContainer"
        class="flex-1 overflow-auto px-6 relative select-none"
        @mousedown="handleMouseDown"
        @mousemove="handleMouseMove"
        @mouseup="handleMouseUp"
        @mouseleave="handleMouseUp"
      >
        <!-- Loading State -->
    <div v-if="isLoading" class="flex items-center justify-center py-12">
      <div class="text-center">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-orange-600 mx-auto mb-4"></div>
        <p class="text-gray-600">Loading your images...</p>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else-if="images.length === 0" class="text-center py-12">
      <div class="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
        <svg class="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      </div>
      <h4 class="text-lg font-medium text-gray-900 mb-2">No images generated yet</h4>
      <p class="text-gray-600 mb-4">Start creating amazing images with AI!</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
      <div class="flex items-center gap-3">
        <svg class="h-5 w-5 text-red-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div class="flex-1">
          <h4 class="font-medium text-red-800">Failed to load images</h4>
          <p class="text-red-700 text-sm mt-1">{{ error }}</p>
        </div>
        <button
          @click="loadImages"
          class="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700"
        >
          Retry
        </button>
      </div>
    </div>

        <!-- Gallery Grid View -->
        <div v-else-if="viewMode === 'grid'" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-8 gap-4">
          <div
            v-for="(image, index) in displayedImages.slice().reverse()"
            :key="image.id"
            :data-image-id="image.id"
            :class="[
              'image-item relative group cursor-pointer rounded-lg overflow-hidden bg-gray-100 aspect-square transition-all',
              isImageSelected(image.id) && 'ring-4 ring-blue-500 ring-offset-2'
            ]"
            draggable="true"
            @dragstart="handleDragStart(image, $event)"
            @dragend="handleDragEnd"
            @mouseenter="(event) => {
              const video = (event.currentTarget as HTMLElement).querySelector('video')
              if (video) video.play()
            }"
            @mouseleave="(event) => {
              const video = (event.currentTarget as HTMLElement).querySelector('video')
              if (video) {
                video.pause()
                video.currentTime = 0
              }
            }"
            @click="(event) => {
              if (event.ctrlKey || event.metaKey || event.shiftKey) {
                handleImageSelect(image, displayedImages.length - 1 - index, event)
              } else {
                openImageModal(image)
              }
            }"
          >
        <!-- Loading Skeleton -->
        <div
          v-if="!imageLoadStates[image.id] || imageLoadStates[image.id] === 'loading'"
          class="absolute inset-0"
        >
          <Skeleton class="w-full h-full" />
        </div>

        <!-- Video -->
        <video
          v-if="isVideo(image)"
          :src="image.thumbnail_signed_url || image.signed_url"
          class="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
          @loadeddata="onImageLoad(image.id)"
          @error="onImageError(image.id)"
          muted
          loop
          playsinline
        />

        <!-- Image -->
        <img
          v-else
          :src="image.thumbnail_signed_url || image.gcs_signed_url"
          :alt="image.prompt"
          class="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
          @load="onImageLoad(image.id)"
          @error="onImageError(image.id)"
          loading="lazy"
        />

        <!-- Play Icon for Videos -->
        <div
          v-if="isVideo(image)"
          class="absolute inset-0 flex items-center justify-center pointer-events-none group-hover:opacity-0 transition-opacity duration-200"
        >
          <div class="bg-black/60 backdrop-blur-sm rounded-full p-2 sm:p-3 md:p-4">
            <svg class="w-3 h-3 sm:w-4 sm:h-4 md:w-6 md:h-6 text-white" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z"/>
            </svg>
          </div>
        </div>

        <!-- Hover Overlay -->
        <div class="absolute inset-0 group-hover:bg-opacity-30 transition-all duration-200">
          <!-- Status Indicators -->
          <div class="absolute top-2 left-2 flex flex-col gap-1">
            <!-- Public Status -->
            <div v-if="image.is_public" class="bg-blue-500 bg-opacity-90 text-white text-xs px-2 py-0.5 rounded-full flex items-center gap-1" title="Public">
              <svg class="w-2 h-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.367 2.684 3 3 0 00-5.367-2.684z" />
              </svg>
              Public
            </div>

            <!-- Copied Status -->
            <div v-if="image.copied_from_public_id" class="bg-purple-500 bg-opacity-90 text-white text-xs px-2 py-0.5 rounded-full flex items-center gap-1" title="Copied from public gallery">
              <svg class="w-2 h-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              Copy
            </div>
          </div>

          <!-- Selection Checkbox -->
          <div class="absolute top-2 right-2 z-10">
            <button
              @click.stop="toggleSelection(image.id)"
              :class="[
                'w-6 h-6 rounded-full flex items-center justify-center transition-all',
                isImageSelected(image.id)
                  ? 'bg-blue-500 shadow-lg'
                  : 'bg-white/80 hover:bg-white shadow-sm opacity-0 group-hover:opacity-100'
              ]"
              title="Select image"
            >
              <svg
                v-if="isImageSelected(image.id)"
                class="w-4 h-4 text-white"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
              </svg>
              <div v-else class="w-4 h-4 border-2 border-gray-400 rounded-full"></div>
            </button>
          </div>

          <!-- Action Buttons -->
          <div class="absolute top-2 right-10 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-20">
            <div class="flex gap-1">
              <!-- Delete Button -->
              <button
                @click.stop="confirmDelete(image)"
                class="p-1.5 bg-red-500 bg-opacity-90 hover:bg-opacity-100 rounded-full shadow-sm transition-all"
                title="Delete image"
              >
                <svg class="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>

          <!-- Image Info overlay -->
          <!-- <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black via-black to-transparent p-3 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10">
            <p class="text-white text-xs font-medium truncate mb-1">{{ truncatePrompt(image.prompt) }}</p>
            <div class="flex items-center justify-between text-xs text-gray-300">
              <span>{{ image.model_name }}</span>
              <span>{{ formatDate(image.created_at) }}</span>
            </div>
          </div> -->
        </div>

        <!-- Error State - Show skeleton while refreshing URL -->
        <div
          v-if="imageLoadStates[image.id] === 'error'"
          class="absolute inset-0"
        >
          <Skeleton class="w-full h-full" />
        </div>
      </div>
    </div>

        <!-- Gallery List View -->
        <div v-else-if="viewMode === 'list'" class="space-y-4">
          <div
            v-for="(image, index) in displayedImages"
            :key="image.id"
            :data-image-id="image.id"
            :class="[
              'image-item flex items-center gap-4 p-4 bg-white border-2 rounded-lg hover:shadow-sm transition-all cursor-pointer',
              isImageSelected(image.id) ? 'border-blue-500 bg-blue-50' : 'border-gray-200'
            ]"
            draggable="true"
            @dragstart="handleDragStart(image, $event)"
            @dragend="handleDragEnd"
            @mouseenter="(event) => {
              const video = (event.currentTarget as HTMLElement).querySelector('video')
              if (video) video.play()
            }"
            @mouseleave="(event) => {
              const video = (event.currentTarget as HTMLElement).querySelector('video')
              if (video) {
                video.pause()
                video.currentTime = 0
              }
            }"
            @click="(event) => {
              if (event.ctrlKey || event.metaKey || event.shiftKey) {
                handleImageSelect(image, index, event)
              } else {
                openImageModal(image)
              }
            }"
          >
        <!-- Selection Checkbox -->
        <div class="flex-shrink-0">
          <button
            @click.stop="toggleSelection(image.id)"
            :class="[
              'w-6 h-6 rounded-full flex items-center justify-center transition-all',
              isImageSelected(image.id)
                ? 'bg-blue-500 shadow-lg'
                : 'bg-gray-200 hover:bg-gray-300'
            ]"
            title="Select image"
          >
            <svg
              v-if="isImageSelected(image.id)"
              class="w-4 h-4 text-white"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
            </svg>
            <div v-else class="w-3 h-3 border-2 border-gray-400 rounded-full"></div>
          </button>
        </div>

        <!-- Thumbnail -->
        <div class="w-16 h-16 bg-gray-100 rounded-lg overflow-hidden flex-shrink-0 relative">
          <!-- Loading/Error Skeleton -->
          <div
            v-if="!imageLoadStates[image.id] || imageLoadStates[image.id] === 'loading' || imageLoadStates[image.id] === 'error'"
            class="absolute inset-0"
          >
            <Skeleton class="w-full h-full" />
          </div>
          <!-- Video -->
          <video
            v-if="isVideo(image)"
            :src="image.thumbnail_signed_url || image.gcs_signed_url"
            class="w-full h-full object-cover"
            @loadeddata="onImageLoad(image.id)"
            @error="onImageError(image.id)"
            muted
            loop
            playsinline
          />
          <!-- Image -->
          <img
            v-else
            :src="image.thumbnail_signed_url || image.gcs_signed_url"
            :alt="image.prompt"
            class="w-full h-full object-cover"
            @load="onImageLoad(image.id)"
            @error="onImageError(image.id)"
            loading="lazy"
          />

          <!-- Play Icon for Videos -->
          <div
            v-if="isVideo(image)"
            class="absolute inset-0 flex items-center justify-center pointer-events-none group-hover:opacity-0 transition-opacity duration-200"
          >
            <div class="bg-black/10 backdrop-blur-sm rounded-full p-2">
              <svg class="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z"/>
              </svg>
            </div>
          </div>
        </div>

        <!-- Image Info -->
        <div class="flex-1 min-w-0">
          <h4 class="font-medium text-gray-900 truncate">{{ image.prompt }}</h4>
          <div class="flex items-center gap-4 mt-1 text-sm text-gray-600">
            <span>{{ image.model_name }}</span>
            <span>{{ image.width }}×{{ image.height }}</span>
            <span>{{ formatDate(image.created_at) }}</span>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex items-center gap-2">
          <button
            @click.stop="confirmDelete(image)"
            class="p-2 text-gray-400 hover:text-red-600 transition-colors"
            title="Delete image"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>
          </div>
        </div>

            <!-- Load More Button -->
        <div v-if="hasMore && !isLoading" class="text-center mt-8 pb-6">
      <Button
        @click="loadMore"
        :disabled="isLoadingMore"
        class="px-6 py-2  text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <span v-if="!isLoadingMore">Load More Images</span>
        <span v-else class="flex items-center gap-2">
          <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
          Loading...
        </span>
          </Button>
        </div>

        <!-- Selection Box Overlay -->
        <div
          v-if="isSelecting && selectionBox"
          class="absolute pointer-events-none border-2 border-blue-500 bg-blue-500/30 bg-opacity-20 rounded"
          :style="{
            left: selectionBox.left + 'px',
            top: selectionBox.top + 'px',
            width: selectionBox.width + 'px',
            height: selectionBox.height + 'px'
          }"
        ></div>
      </div>
    </div>

    <!-- Folder Create/Rename Modal -->
    <FolderCreateModal
      :is-open="showFolderModal"
      :mode="folderModalMode"
      :existing-folder="editingFolder"
      :existing-folder-names="folderNames"
      @close="closeFolderModal"
      @create="handleCreateFolder"
      @rename="handleRenameFolder"
    />

    <!-- Image Sharing Modal -->
    <ImageSharingModal
      :is-open="showSharingModal"
      :image="imageToShare"
      @close="closeSharingModal"
      @success="handleSharingSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import ImageModal from './ImageModal.vue'
import ImageSharingModal from './ImageSharingModal.vue'
import FolderSidebar from './FolderSidebar.vue'
import FolderCreateModal from './FolderCreateModal.vue'
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuthStore } from '@/stores/auth'
import publicImagesService from '@/api/publicImagesService'
import { toast } from 'vue-sonner'
import type { GeneratedImage } from '@/api/imageGenerationService'
import type { ImageFolder } from '@/api/imageFoldersService'

// Props
interface Props {
  images?: GeneratedImage[]
  loading?: boolean
  error?: string | null
  folders?: ImageFolder[]
  selectedFolderId?: string | null
  uncategorizedCount?: number
  foldersLoading?: boolean
  showFolders?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  images: () => [],
  loading: false,
  error: null,
  folders: () => [],
  selectedFolderId: null,
  uncategorizedCount: 0,
  foldersLoading: false,
  showFolders: true
})

// Emits
const emit = defineEmits<{
  'load-images': []
  'load-more': []
  'delete-image': [image: GeneratedImage]
  'batch-delete-images': [imageIds: string[]]
  'download-image': [image: GeneratedImage]
  'image-click': [image: GeneratedImage]
  'image-error': [image: GeneratedImage]
  'image-shared': [image: GeneratedImage]
  'image-unshared': [image: GeneratedImage]
  'create-character': [image: GeneratedImage]
  'select-folder': [folderId: string | null]
  'create-folder': [name: string, color: string]
  'rename-folder': [folderId: string, name: string, color: string]
  'delete-folder': [folderId: string]
  'move-image-to-folder': [imageId: string, folderId: string | null]
  'move-images-to-folder': [imageIds: string[], folderId: string | null]
}>()

// Local state
const viewMode = ref<'grid' | 'list'>('grid')
const imageLoadStates = ref<Record<string, 'loading' | 'loaded' | 'error'>>({})
const isLoadingMore = ref(false)
const hasMore = ref(true) // This would be determined by the parent component
const selectedImage = ref<GeneratedImage | null>(null)
const isModalOpen = ref(false)
const currentImageIndex = ref(0)

// Sharing state
const showSharingModal = ref(false)
const imageToShare = ref<GeneratedImage | null>(null)

// Folder state
const showFolderModal = ref(false)
const folderModalMode = ref<'create' | 'rename'>('create')
const editingFolder = ref<ImageFolder | undefined>(undefined)

// Drag & drop state
const draggedImage = ref<GeneratedImage | null>(null)

// Multi-select state
const selectedImageIds = ref<Set<string>>(new Set())
const lastSelectedIndex = ref<number | null>(null)

// Marquee selection state
const isSelecting = ref(false)
const selectionStart = ref<{ x: number; y: number } | null>(null)
const selectionEnd = ref<{ x: number; y: number } | null>(null)
const galleryContainer = ref<HTMLElement | null>(null)
const selectionBeforeDrag = ref<Set<string>>(new Set())
const isAddingToSelection = ref(false)

// Auth store
const authStore = useAuthStore()

// Computed properties
const isLoading = computed(() => props.loading)
const error = computed(() => props.error)
const images = computed(() => props.images || [])
const totalImages = computed(() => images.value.length)
const folders = computed(() => props.folders || [])
const selectedFolderId = computed(() => props.selectedFolderId)

const currentFolderName = computed(() => {
  if (selectedFolderId.value === null) return 'All Images'
  if (selectedFolderId.value === 'uncategorized') return 'Uncategorized'
  const folder = folders.value.find(f => f.id === selectedFolderId.value)
  return folder?.name || 'Your Generated Images'
})

const folderNames = computed(() => folders.value.map(f => f.name))

// For lazy loading, we'll show images in batches
const displayedImages = computed(() => {
  return images.value.slice().reverse() // Show newest first
})

// Selection computed properties
const selectedCount = computed(() => selectedImageIds.value.size)
const hasSelection = computed(() => selectedCount.value > 0)
const isAllSelected = computed(() => {
  return images.value.length > 0 && selectedCount.value === images.value.length
})

// Marquee selection computed
const selectionBox = computed(() => {
  if (!selectionStart.value || !selectionEnd.value) return null

  const x1 = Math.min(selectionStart.value.x, selectionEnd.value.x)
  const y1 = Math.min(selectionStart.value.y, selectionEnd.value.y)
  const x2 = Math.max(selectionStart.value.x, selectionEnd.value.x)
  const y2 = Math.max(selectionStart.value.y, selectionEnd.value.y)

  return {
    left: x1,
    top: y1,
    width: x2 - x1,
    height: y2 - y1
  }
})

// Methods
const loadImages = () => {
  emit('load-images')
}

const loadMore = () => {
  if (!isLoadingMore.value && hasMore.value) {
    isLoadingMore.value = true
    emit('load-more')
    // Parent component should handle setting isLoadingMore back to false
  }
}

const onImageLoad = (imageId: string) => {
  imageLoadStates.value[imageId] = 'loaded'
}

const onImageError = (imageId: string) => {
  imageLoadStates.value[imageId] = 'error'
  // Emit error event so parent can refresh the URL
  const image = images.value.find(img => img.id === imageId)
  if (image) {
    emit('image-error', image)
  }
}

const openImageModal = (image: GeneratedImage) => {
  // Just emit the image click event - don't open modal
  emit('image-click', image)
}

const closeModal = () => {
  isModalOpen.value = false
  selectedImage.value = null
  currentImageIndex.value = 0
}

const handleNavigate = (direction: 'previous' | 'next') => {
  const images = displayedImages.value
  if (images.length === 0) return

  if (direction === 'previous' && currentImageIndex.value > 0) {
    currentImageIndex.value--
  } else if (direction === 'next' && currentImageIndex.value < images.length - 1) {
    currentImageIndex.value++
  }

  // Update selected image
  selectedImage.value = images[currentImageIndex.value]
}

const handleDeleteFromModal = (image: GeneratedImage) => {
  emit('delete-image', image)
  closeModal()
}

const handleCreateCharacter = (image: GeneratedImage) => {
  emit('create-character', image)
  closeModal()
}

const downloadImage = async (image: GeneratedImage) => {
  try {
    // Import the service dynamically to avoid circular dependencies
    const { default: imageGenerationService } = await import('@/api/imageGenerationService')
    await imageGenerationService.downloadImage(image)
  } catch (error) {
    console.error('Download failed:', error)
    // Fallback to emitting the event for parent to handle
    emit('download-image', image)
  }
}

const confirmDelete = (image: GeneratedImage) => {
  if (confirm(`Delete this generated image? This action cannot be undone.`)) {
    emit('delete-image', image)
  }
}

const confirmBatchDelete = () => {
  const count = selectedImageIds.value.size
  if (confirm(`Delete ${count} selected image${count !== 1 ? 's' : ''}? This action cannot be undone.`)) {
    const imageIds = Array.from(selectedImageIds.value)
    emit('batch-delete-images', imageIds)
    // Clear selection after emitting delete event
    clearSelection()
  }
}

// Sharing methods
const toggleImageSharing = (image: GeneratedImage) => {
  if (image.is_public) {
    makeImagePrivate(image)
  } else {
    openSharingModal(image)
  }
}

const openSharingModal = (image: GeneratedImage) => {
  imageToShare.value = image
  showSharingModal.value = true
}

const closeSharingModal = () => {
  showSharingModal.value = false
  imageToShare.value = null
}

const handleSharingSuccess = (sharedImage: any) => {
  // Update the local image object
  const imageIndex = images.value.findIndex(img => img.id === sharedImage.user_image_id)
  if (imageIndex !== -1) {
    const updatedImages = [...images.value]
    updatedImages[imageIndex] = {
      ...updatedImages[imageIndex],
      is_public: true,
      original_public_image_id: sharedImage.id
    }
    // Since images is a computed property from props, we need to emit an event
    // to update the parent component's data
    emit('image-shared', updatedImages[imageIndex])
  }
  // Don't show toast here as the modal already handles it
}

const makeImagePrivate = async (image: GeneratedImage) => {
  if (!authStore.user) {
    toast.error('Please sign in to manage image sharing')
    return
  }

  try {
    await publicImagesService.makeImagePrivate(image.id, authStore.user.id)

    // Update the local image object
    const imageIndex = images.value.findIndex(img => img.id === image.id)
    if (imageIndex !== -1) {
      const updatedImages = [...images.value]
      updatedImages[imageIndex] = {
        ...updatedImages[imageIndex],
        is_public: false,
        original_public_image_id: undefined
      }
      // Emit event to update parent component's data
      emit('image-unshared', updatedImages[imageIndex])
    }

    toast.success('Image made private')
  } catch (error: any) {
    console.error('Error making image private:', error)
    toast.error(error.message || 'Failed to make image private')
  }
}

const truncatePrompt = (prompt: string, maxLength: number = 50): string => {
  if (prompt.length <= maxLength) return prompt
  return prompt.substring(0, maxLength) + '...'
}

// Folder methods
const handleSelectFolder = (folderId: string | null) => {
  emit('select-folder', folderId)
}

const openCreateFolderModal = () => {
  folderModalMode.value = 'create'
  editingFolder.value = undefined
  showFolderModal.value = true
}

const openRenameFolderModal = (folderId: string, currentName: string) => {
  const folder = folders.value.find(f => f.id === folderId)
  if (folder) {
    folderModalMode.value = 'rename'
    editingFolder.value = folder
    showFolderModal.value = true
  }
}

const closeFolderModal = () => {
  showFolderModal.value = false
  editingFolder.value = undefined
}

const handleCreateFolder = (name: string, color: string) => {
  emit('create-folder', name, color)
  closeFolderModal()
}

const handleRenameFolder = (folderId: string, name: string, color: string) => {
  emit('rename-folder', folderId, name, color)
  closeFolderModal()
}

const handleDeleteFolder = (folderId: string) => {
  const folder = folders.value.find(f => f.id === folderId)
  const message = folder && folder.image_count > 0
    ? `Delete "${folder.name}"? ${folder.image_count} image${folder.image_count !== 1 ? 's' : ''} will be moved to Uncategorized.`
    : `Delete this folder?`

  if (confirm(message)) {
    emit('delete-folder', folderId)
  }
}

// Selection methods
const toggleSelection = (imageId: string) => {
  const newSelection = new Set(selectedImageIds.value)
  if (newSelection.has(imageId)) {
    newSelection.delete(imageId)
  } else {
    newSelection.add(imageId)
  }
  selectedImageIds.value = newSelection
}

const handleImageSelect = (image: GeneratedImage, index: number, event: MouseEvent) => {
  if (event.ctrlKey || event.metaKey) {
    // Ctrl/Cmd+Click: Toggle individual selection
    toggleSelection(image.id)
    lastSelectedIndex.value = index
  } else if (event.shiftKey && lastSelectedIndex.value !== null) {
    // Shift+Click: Range selection
    const start = Math.min(lastSelectedIndex.value, index)
    const end = Math.max(lastSelectedIndex.value, index)
    const newSelection = new Set(selectedImageIds.value)
    for (let i = start; i <= end; i++) {
      if (displayedImages.value[i]) {
        newSelection.add(displayedImages.value[i].id)
      }
    }
    selectedImageIds.value = newSelection
  } else {
    // Regular click: Open modal (handled by parent)
    // Don't change selection
  }
}

const selectAll = () => {
  selectedImageIds.value = new Set(images.value.map(img => img.id))
}

const clearSelection = () => {
  selectedImageIds.value = new Set()
  lastSelectedIndex.value = null
}

const isImageSelected = (imageId: string) => {
  return selectedImageIds.value.has(imageId)
}

// Marquee selection methods
const handleMouseDown = (event: MouseEvent) => {
  // Only start selection if clicking on the gallery container (not on images or buttons)
  if ((event.target as HTMLElement).closest('.image-item, button')) {
    return
  }

  // Don't interfere with right-click
  if (event.button !== 0) return

  // Save current selection state
  isAddingToSelection.value = event.ctrlKey || event.metaKey
  selectionBeforeDrag.value = new Set(selectedImageIds.value)

  // If not holding Ctrl/Cmd, clear previous selection
  if (!isAddingToSelection.value) {
    clearSelection()
  }

  isSelecting.value = true
  const rect = galleryContainer.value?.getBoundingClientRect()
  if (rect) {
    selectionStart.value = {
      x: event.clientX - rect.left + (galleryContainer.value?.scrollLeft || 0),
      y: event.clientY - rect.top + (galleryContainer.value?.scrollTop || 0)
    }
    selectionEnd.value = selectionStart.value
  }
}

const handleMouseMove = (event: MouseEvent) => {
  if (!isSelecting.value || !selectionStart.value) return

  const rect = galleryContainer.value?.getBoundingClientRect()
  if (rect) {
    selectionEnd.value = {
      x: event.clientX - rect.left + (galleryContainer.value?.scrollLeft || 0),
      y: event.clientY - rect.top + (galleryContainer.value?.scrollTop || 0)
    }

    // Find images within selection box
    updateSelectionFromBox()
  }
}

const handleMouseUp = () => {
  if (isSelecting.value) {
    isSelecting.value = false
    selectionStart.value = null
    selectionEnd.value = null
  }
}

const updateSelectionFromBox = () => {
  if (!selectionBox.value) return

  const box = selectionBox.value
  const imageElements = galleryContainer.value?.querySelectorAll('.image-item')

  if (!imageElements) return

  // Start fresh - only select images currently in the box
  const currentBoxSelection = new Set<string>()

  imageElements.forEach((element) => {
    const rect = element.getBoundingClientRect()
    const containerRect = galleryContainer.value?.getBoundingClientRect()

    if (!containerRect) return

    const imageBox = {
      left: rect.left - containerRect.left + (galleryContainer.value?.scrollLeft || 0),
      top: rect.top - containerRect.top + (galleryContainer.value?.scrollTop || 0),
      right: rect.right - containerRect.left + (galleryContainer.value?.scrollLeft || 0),
      bottom: rect.bottom - containerRect.top + (galleryContainer.value?.scrollTop || 0)
    }

    // Check if boxes intersect
    const intersects = !(
      box.left + box.width < imageBox.left ||
      box.left > imageBox.right ||
      box.top + box.height < imageBox.top ||
      box.top > imageBox.bottom
    )

    const imageId = element.getAttribute('data-image-id')
    if (imageId && intersects) {
      currentBoxSelection.add(imageId)
    }
  })

  // If Ctrl was held, merge with pre-drag selection; otherwise, use only current box selection
  if (isAddingToSelection.value) {
    const mergedSelection = new Set(selectionBeforeDrag.value)
    currentBoxSelection.forEach(id => mergedSelection.add(id))
    selectedImageIds.value = mergedSelection
  } else {
    selectedImageIds.value = currentBoxSelection
  }
}

// Drag & Drop methods
const handleDragStart = (image: GeneratedImage, event: DragEvent) => {
  draggedImage.value = image
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'

    // If the dragged image is selected, drag all selected images
    if (isImageSelected(image.id) && selectedCount.value > 1) {
      const selectedIds = Array.from(selectedImageIds.value)
      event.dataTransfer.setData('image-ids', JSON.stringify(selectedIds))

      // Create a custom drag image showing the count
      const dragCount = document.createElement('div')
      dragCount.className = 'bg-blue-500 text-white px-3 py-2 rounded-lg shadow-lg font-semibold'
      dragCount.textContent = `${selectedIds.length} images`
      dragCount.style.position = 'absolute'
      dragCount.style.top = '-1000px'
      document.body.appendChild(dragCount)
      event.dataTransfer.setDragImage(dragCount, 0, 0)
      setTimeout(() => document.body.removeChild(dragCount), 0)
    } else {
      event.dataTransfer.setData('image-id', image.id)
    }
  }
}

const handleDragEnd = () => {
  draggedImage.value = null
}

const handleDropImageOnFolder = (imageId: string | string[], folderId: string | null) => {
  // Check if we're dropping multiple images
  if (Array.isArray(imageId)) {
    emit('move-images-to-folder', imageId, folderId)
    // Clear selection after moving
    clearSelection()
  } else {
    emit('move-image-to-folder', imageId, folderId)
  }
}

const formatDate = (dateString: string): string => {
  const date = new Date(dateString)
  const now = new Date()
  const diffInHours = (now.getTime() - date.getTime()) / (1000 * 60 * 60)

  if (diffInHours < 1) {
    const minutes = Math.floor(diffInHours * 60)
    return `${minutes}m ago`
  } else if (diffInHours < 24) {
    const hours = Math.floor(diffInHours)
    return `${hours}h ago`
  } else if (diffInHours < 24 * 7) {
    const days = Math.floor(diffInHours / 24)
    return `${days}d ago`
  } else {
    return date.toLocaleDateString()
  }
}

const isVideo = (image: GeneratedImage): boolean => {
  // Check if the URL contains video file extensions
  const url = image.thumbnail_signed_url || image.signed_url || ''
  const videoExtensions = ['.mp4', '.webm', '.mov', '.avi', '.mkv', '.m4v']
  return videoExtensions.some(ext => url.toLowerCase().includes(ext))
}

// Initialize image load states when images change
watch(images, (newImages) => {
  newImages.forEach(image => {
    if (!(image.id in imageLoadStates.value)) {
      imageLoadStates.value[image.id] = 'loading'
    }
  })
}, { immediate: true })

// Expose methods for parent components
defineExpose({
  setLoadingMore: (loading: boolean) => {
    isLoadingMore.value = loading
  },
  setHasMore: (more: boolean) => {
    hasMore.value = more
  },
  resetImageLoadState: (imageId: string) => {
    imageLoadStates.value[imageId] = 'loading'
  }
})

// Load images on mount
onMounted(() => {
  if (images.value.length === 0) {
    loadImages()
  }
})
</script>