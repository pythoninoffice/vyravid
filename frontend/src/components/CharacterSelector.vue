<template>
  <div class="character-selector">
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold text-gray-900">Select Characters</h3>
      <button
        v-if="showEditButton && selectedCharactersList.length > 0"
        @click="$emit('edit-character', selectedCharactersList[0])"
        class="text-sm text-blue-600 hover:text-blue-700 flex items-center gap-1"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
          />
        </svg>
        Edit Character
      </button>
    </div>

    <!-- Search -->
    <div class="relative mb-4">
      <input
        v-model="searchQuery"
        type="text"
        placeholder="Search characters..."
        class="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
      />
      <svg
        class="absolute left-3 top-2.5 w-5 h-5 text-gray-400"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
        />
      </svg>
    </div>

    <!-- Selected Characters Summary -->
    <div v-if="selectedCharactersList.length > 0" class="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm font-medium text-blue-900">
          {{ selectedCharactersList.length }} selected
        </span>
        <button
          @click="clearSelection"
          class="text-sm text-blue-600 hover:text-blue-700"
        >
          Clear all
        </button>
      </div>
      <div class="flex flex-wrap gap-2">
        <span
          v-for="char in selectedCharactersList"
          :key="char.id"
          class="inline-flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-800 rounded text-sm"
        >
          {{ char.name }}
          <button
            @click="toggleCharacter(char.id)"
            class="hover:text-blue-900"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </span>
      </div>
    </div>

    <!-- Character List -->
    <div class="space-y-2 max-h-96 overflow-y-auto">
      <!-- Loading -->
      <div v-if="loading" class="text-center py-8">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2"></div>
        <p class="text-sm text-gray-600">Loading characters...</p>
      </div>

      <!-- Empty State -->
      <div v-else-if="filteredCharacters.length === 0" class="text-center py-8">
        <p class="text-gray-600 text-sm">
          {{ searchQuery ? 'No characters found' : 'No characters available' }}
        </p>
        <button
          v-if="!searchQuery"
          @click="$emit('create-character')"
          class="mt-2 text-sm text-blue-600 hover:text-blue-700"
        >
          Create your first character
        </button>
      </div>

      <!-- Characters -->
      <label
        v-for="character in filteredCharacters"
        :key="character.id"
        class="flex items-center gap-3 p-3 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors"
        :class="{ 'ring-2 ring-blue-500 border-blue-500': isSelected(character.id) }"
      >
        <!-- Checkbox -->
        <input
          type="checkbox"
          :checked="isSelected(character.id)"
          @change="toggleCharacter(character.id)"
          class="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
        />

        <!-- Thumbnail -->
        <div class="w-12 h-12 bg-gray-100 rounded overflow-hidden flex-shrink-0">
          <img
            v-if="character.thumbnail_url"
            :src="character.thumbnail_url"
            :alt="character.name"
            class="w-full h-full object-cover"
            loading="lazy"
          />
          <div v-else class="w-full h-full flex items-center justify-center bg-gray-200">
            <svg class="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
              />
            </svg>
          </div>
        </div>

        <!-- Info -->
        <div class="flex-1 min-w-0">
          <p class="font-medium text-gray-900 truncate">{{ character.name }}</p>
          <p v-if="character.description" class="text-sm text-gray-600 truncate">
            {{ character.description }}
          </p>
          <div class="flex items-center gap-2 mt-1">
            <span
              v-if="character.tags && character.tags.length > 0"
              class="text-xs text-gray-500"
            >
              {{ character.tags[0] }}
            </span>
            <span
              v-if="character.reference_images && character.reference_images.length > 0"
              class="text-xs text-gray-500"
            >
              • {{ character.reference_images.length }} ref{{ character.reference_images.length !== 1 ? 's' : '' }}
            </span>
          </div>
        </div>
      </label>
    </div>

    <!-- Footer Actions -->
    <div v-if="showActions" class="mt-4 pt-4 border-t border-gray-200 flex justify-end gap-2">
      <button
        @click="$emit('cancel')"
        class="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
      >
        Cancel
      </button>
      <button
        @click="confirmSelection"
        :disabled="selectedCharactersList.length === 0"
        class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed"
      >
        Confirm ({{ selectedCharactersList.length }})
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useCharactersStore } from '@/stores/characters'
import type { CharacterDesign } from '@/api/characterService'

interface Props {
  modelValue?: string[] // Selected character IDs
  multiple?: boolean
  showActions?: boolean
  showEditButton?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => [],
  multiple: true,
  showActions: true,
  showEditButton: true
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
  confirm: [characters: CharacterDesign[]]
  cancel: []
  'create-character': []
  'edit-character': [character: CharacterDesign]
}>()

const charactersStore = useCharactersStore()

const searchQuery = ref('')
const selectedIds = ref<string[]>([...props.modelValue])

// Computed
const characters = computed(() => charactersStore.characters)
const loading = computed(() => charactersStore.charactersLoading)

const filteredCharacters = computed(() => {
  let filtered = characters.value

  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(
      (c) =>
        c.name.toLowerCase().includes(query) ||
        c.description?.toLowerCase().includes(query) ||
        c.tags.some((tag) => tag.toLowerCase().includes(query))
    )
  }

  return filtered
})

const selectedCharactersList = computed(() => {
  return characters.value.filter((c) => selectedIds.value.includes(c.id))
})

// Methods
function isSelected(characterId: string): boolean {
  return selectedIds.value.includes(characterId)
}

function toggleCharacter(characterId: string) {
  const index = selectedIds.value.indexOf(characterId)

  if (index === -1) {
    // Add
    if (props.multiple) {
      selectedIds.value.push(characterId)
    } else {
      selectedIds.value = [characterId]
    }
  } else {
    // Remove
    selectedIds.value.splice(index, 1)
  }

  emit('update:modelValue', selectedIds.value)
}

function clearSelection() {
  selectedIds.value = []
  emit('update:modelValue', [])
}

function confirmSelection() {
  emit('confirm', selectedCharactersList.value)
}

// Lifecycle
onMounted(async () => {
  if (characters.value.length === 0) {
    await charactersStore.fetchCharacters()
  }
})
</script>

<style scoped>
.character-selector {
  /* Custom styles if needed */
}
</style>
