/**
 * Character Design Store
 * Manages state for character designs, collections, and reference images
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import characterService, {
  type CharacterDesign,
  type CharacterDesignCreate,
  type CharacterDesignUpdate,
  type CharacterCollection,
  type CharacterCollectionCreate,
  type CharacterReferenceImage,
  type CharacterReferenceImageCreate,
  CharacterServiceError
} from '@/api/characterService'
import { toast } from 'vue-sonner'

export const useCharactersStore = defineStore('characters', () => {
  // =============================================
  // State
  // =============================================

  // Characters
  const characters = ref<CharacterDesign[]>([])
  const currentCharacter = ref<CharacterDesign | null>(null)
  const charactersLoading = ref(false)
  const charactersError = ref<string | null>(null)

  // Pagination
  const currentPage = ref(1)
  const itemsPerPage = ref(50)
  const totalCharacters = ref(0)
  const hasMoreCharacters = ref(false)

  // Filters
  const searchQuery = ref('')
  const selectedCollectionId = ref<string | null>(null)
  const selectedTags = ref<string[]>([])

  // Collections
  const collections = ref<CharacterCollection[]>([])
  const collectionsLoading = ref(false)
  const collectionsError = ref<string | null>(null)

  // UI State
  const viewMode = ref<'grid' | 'list'>('grid')
  const selectedCharacterIds = ref<string[]>([])

  // =============================================
  // Computed
  // =============================================

  const filteredCharacters = computed(() => {
    let filtered = characters.value

    // Filter by collection
    if (selectedCollectionId.value) {
      filtered = filtered.filter((c) => c.collection_id === selectedCollectionId.value)
    }

    // Filter by search query
    if (searchQuery.value.trim()) {
      const query = searchQuery.value.toLowerCase()
      filtered = filtered.filter(
        (c) =>
          c.name.toLowerCase().includes(query) ||
          c.description?.toLowerCase().includes(query) ||
          c.tags.some((tag) => tag.toLowerCase().includes(query))
      )
    }

    // Filter by tags
    if (selectedTags.value.length > 0) {
      filtered = filtered.filter((c) =>
        selectedTags.value.some((tag) => c.tags.includes(tag))
      )
    }

    return filtered
  })

  const characterCount = computed(() => characters.value.length)

  const collectionCount = computed(() => collections.value.length)

  const selectedCharacters = computed(() =>
    characters.value.filter((c) => selectedCharacterIds.value.includes(c.id))
  )

  // Get all unique tags across all characters
  const allTags = computed(() => {
    const tags = new Set<string>()
    characters.value.forEach((c) => {
      c.tags.forEach((tag) => tags.add(tag))
    })
    return Array.from(tags).sort()
  })

  // =============================================
  // Character Actions
  // =============================================

  /**
   * Fetch characters with optional filters
   */
  async function fetchCharacters(resetPage = false) {
    if (resetPage) {
      currentPage.value = 1
    }

    charactersLoading.value = true
    charactersError.value = null

    try {
      const response = await characterService.listCharacters({
        page: currentPage.value,
        limit: itemsPerPage.value,
        collection_id: selectedCollectionId.value || undefined,
        search: searchQuery.value.trim() || undefined,
        tags: selectedTags.value.length > 0 ? selectedTags.value : undefined
      })

      if (resetPage) {
        characters.value = response.characters
      } else {
        // Append for pagination
        characters.value = [...characters.value, ...response.characters]
      }

      totalCharacters.value = response.total
      hasMoreCharacters.value = response.has_more
    } catch (error) {
      const errorMessage =
        error instanceof CharacterServiceError
          ? error.message
          : 'Failed to fetch characters'
      charactersError.value = errorMessage
      toast.error('Failed to load characters', {
        description: errorMessage
      })
    } finally {
      charactersLoading.value = false
    }
  }

  /**
   * Load more characters (pagination)
   */
  async function loadMore() {
    if (!hasMoreCharacters.value || charactersLoading.value) return

    currentPage.value++
    await fetchCharacters(false)
  }

  /**
   * Get a specific character by ID
   */
  async function getCharacter(characterId: string) {
    try {
      const character = await characterService.getCharacter(characterId)
      currentCharacter.value = character
      return character
    } catch (error) {
      const errorMessage =
        error instanceof CharacterServiceError ? error.message : 'Failed to fetch character'
      toast.error('Failed to load character', {
        description: errorMessage
      })
      throw error
    }
  }

  /**
   * Create a new character
   */
  async function createCharacter(data: CharacterDesignCreate): Promise<CharacterDesign> {
    try {
      const character = await characterService.createCharacter(data)

      // Add to local state
      characters.value.unshift(character)
      totalCharacters.value++

      toast.success('Character created successfully')
      return character
    } catch (error) {
      const errorMessage =
        error instanceof CharacterServiceError ? error.message : 'Failed to create character'
      toast.error('Failed to create character', {
        description: errorMessage
      })
      throw error
    }
  }

  /**
   * Update a character
   */
  async function updateCharacter(
    characterId: string,
    data: CharacterDesignUpdate
  ): Promise<CharacterDesign> {
    try {
      const updatedCharacter = await characterService.updateCharacter(characterId, data)

      // Update in local state
      const index = characters.value.findIndex((c) => c.id === characterId)
      if (index !== -1) {
        characters.value[index] = updatedCharacter
      }

      if (currentCharacter.value?.id === characterId) {
        currentCharacter.value = updatedCharacter
      }

      toast.success('Character updated successfully')
      return updatedCharacter
    } catch (error) {
      const errorMessage =
        error instanceof CharacterServiceError ? error.message : 'Failed to update character'
      toast.error('Failed to update character', {
        description: errorMessage
      })
      throw error
    }
  }

  /**
   * Delete a character
   */
  async function deleteCharacter(characterId: string) {
    try {
      await characterService.deleteCharacter(characterId)

      // Remove from local state
      characters.value = characters.value.filter((c) => c.id !== characterId)
      totalCharacters.value--

      if (currentCharacter.value?.id === characterId) {
        currentCharacter.value = null
      }

      toast.success('Character deleted successfully')
    } catch (error) {
      const errorMessage =
        error instanceof CharacterServiceError ? error.message : 'Failed to delete character'
      toast.error('Failed to delete character', {
        description: errorMessage
      })
      throw error
    }
  }

  // =============================================
  // Reference Image Actions
  // =============================================

  /**
   * Add a reference image to a character
   */
  async function addReferenceImage(
    characterId: string,
    data: CharacterReferenceImageCreate
  ): Promise<CharacterReferenceImage> {
    try {
      const reference = await characterService.addReferenceImage(characterId, data)

      // Update character in local state
      const character = characters.value.find((c) => c.id === characterId)
      if (character) {
        if (!character.reference_images) {
          character.reference_images = []
        }
        character.reference_images.push(reference)

        // Update thumbnail if this is primary
        if (data.is_primary) {
          character.thumbnail_image_id = data.generated_image_id
          character.thumbnail_url = reference.thumbnail_url
        }
      }

      if (currentCharacter.value?.id === characterId) {
        if (!currentCharacter.value.reference_images) {
          currentCharacter.value.reference_images = []
        }
        currentCharacter.value.reference_images.push(reference)

        if (data.is_primary) {
          currentCharacter.value.thumbnail_image_id = data.generated_image_id
          currentCharacter.value.thumbnail_url = reference.thumbnail_url
        }
      }

      toast.success('Reference image added successfully')
      return reference
    } catch (error) {
      const errorMessage =
        error instanceof CharacterServiceError
          ? error.message
          : 'Failed to add reference image'
      toast.error('Failed to add reference image', {
        description: errorMessage
      })
      throw error
    }
  }

  /**
   * Remove a reference image from a character
   */
  async function removeReferenceImage(characterId: string, referenceId: string) {
    try {
      await characterService.removeReferenceImage(characterId, referenceId)

      // Update character in local state
      const character = characters.value.find((c) => c.id === characterId)
      if (character && character.reference_images) {
        character.reference_images = character.reference_images.filter(
          (r) => r.id !== referenceId
        )
      }

      if (currentCharacter.value?.id === characterId && currentCharacter.value.reference_images) {
        currentCharacter.value.reference_images = currentCharacter.value.reference_images.filter(
          (r) => r.id !== referenceId
        )
      }

      toast.success('Reference image removed successfully')
    } catch (error) {
      const errorMessage =
        error instanceof CharacterServiceError
          ? error.message
          : 'Failed to remove reference image'
      toast.error('Failed to remove reference image', {
        description: errorMessage
      })
      throw error
    }
  }

  /**
   * Set a reference image as primary
   */
  async function setPrimaryImage(characterId: string, imageId: string) {
    try {
      await characterService.setPrimaryImage(characterId, imageId)

      // Update character in local state
      const character = characters.value.find((c) => c.id === characterId)
      if (character) {
        character.thumbnail_image_id = imageId

        // Update is_primary flags
        if (character.reference_images) {
          character.reference_images.forEach((ref) => {
            ref.is_primary = ref.generated_image_id === imageId
            if (ref.is_primary) {
              character.thumbnail_url = ref.thumbnail_url
            }
          })
        }
      }

      if (currentCharacter.value?.id === characterId) {
        currentCharacter.value.thumbnail_image_id = imageId

        if (currentCharacter.value.reference_images) {
          currentCharacter.value.reference_images.forEach((ref) => {
            ref.is_primary = ref.generated_image_id === imageId
            if (ref.is_primary && currentCharacter.value) {
              currentCharacter.value.thumbnail_url = ref.thumbnail_url
            }
          })
        }
      }

      toast.success('Primary image updated successfully')
    } catch (error) {
      const errorMessage =
        error instanceof CharacterServiceError ? error.message : 'Failed to set primary image'
      toast.error('Failed to set primary image', {
        description: errorMessage
      })
      throw error
    }
  }

  /**
   * Reorder reference images
   */
  async function reorderReferenceImages(
    characterId: string,
    imageOrders: Array<{ id: string; display_order: number }>
  ) {
    try {
      await characterService.reorderReferenceImages(characterId, { image_orders: imageOrders })

      // Update local state
      const character = characters.value.find((c) => c.id === characterId)
      if (character && character.reference_images) {
        imageOrders.forEach((order) => {
          const ref = character.reference_images?.find((r) => r.id === order.id)
          if (ref) {
            ref.display_order = order.display_order
          }
        })
        // Re-sort
        character.reference_images.sort((a, b) => a.display_order - b.display_order)
      }

      if (currentCharacter.value?.id === characterId && currentCharacter.value.reference_images) {
        imageOrders.forEach((order) => {
          const ref = currentCharacter.value?.reference_images?.find((r) => r.id === order.id)
          if (ref) {
            ref.display_order = order.display_order
          }
        })
        currentCharacter.value.reference_images.sort((a, b) => a.display_order - b.display_order)
      }

      toast.success('Reference images reordered successfully')
    } catch (error) {
      const errorMessage =
        error instanceof CharacterServiceError
          ? error.message
          : 'Failed to reorder reference images'
      toast.error('Failed to reorder images', {
        description: errorMessage
      })
      throw error
    }
  }

  // =============================================
  // Collection Actions
  // =============================================

  /**
   * Fetch collections
   */
  async function fetchCollections() {
    collectionsLoading.value = true
    collectionsError.value = null

    try {
      const response = await characterService.listCollections()
      collections.value = response.collections
    } catch (error) {
      const errorMessage =
        error instanceof CharacterServiceError ? error.message : 'Failed to fetch collections'
      collectionsError.value = errorMessage
      toast.error('Failed to load collections', {
        description: errorMessage
      })
    } finally {
      collectionsLoading.value = false
    }
  }

  /**
   * Create a collection
   */
  async function createCollection(data: CharacterCollectionCreate): Promise<CharacterCollection> {
    try {
      const collection = await characterService.createCollection(data)

      // Add to local state
      collections.value.push(collection)

      toast.success('Collection created successfully')
      return collection
    } catch (error) {
      const errorMessage =
        error instanceof CharacterServiceError ? error.message : 'Failed to create collection'
      toast.error('Failed to create collection', {
        description: errorMessage
      })
      throw error
    }
  }

  /**
   * Delete a collection
   */
  async function deleteCollection(collectionId: string) {
    try {
      await characterService.deleteCollection(collectionId)

      // Remove from local state
      collections.value = collections.value.filter((c) => c.id !== collectionId)

      // Unset collection_id for characters in this collection
      characters.value.forEach((c) => {
        if (c.collection_id === collectionId) {
          c.collection_id = undefined
          c.collection_name = undefined
        }
      })

      toast.success('Collection deleted successfully')
    } catch (error) {
      const errorMessage =
        error instanceof CharacterServiceError ? error.message : 'Failed to delete collection'
      toast.error('Failed to delete collection', {
        description: errorMessage
      })
      throw error
    }
  }

  // =============================================
  // Scene Integration Actions
  // =============================================

  /**
   * Generate a scene prompt with selected characters
   */
  async function generateScenePrompt(
    scenePrompt: string,
    characterIds: string[],
    includeVisualNotes = true
  ) {
    try {
      const response = await characterService.generateScenePrompt({
        scene_prompt: scenePrompt,
        character_ids: characterIds,
        include_visual_notes: includeVisualNotes
      })

      return response
    } catch (error) {
      const errorMessage =
        error instanceof CharacterServiceError ? error.message : 'Failed to generate scene prompt'
      toast.error('Failed to generate prompt', {
        description: errorMessage
      })
      throw error
    }
  }

  // =============================================
  // UI Helper Actions
  // =============================================

  function setViewMode(mode: 'grid' | 'list') {
    viewMode.value = mode
  }

  function setSearchQuery(query: string) {
    searchQuery.value = query
    fetchCharacters(true)
  }

  function setSelectedCollection(collectionId: string | null) {
    selectedCollectionId.value = collectionId
    fetchCharacters(true)
  }

  function setSelectedTags(tags: string[]) {
    selectedTags.value = tags
    fetchCharacters(true)
  }

  function toggleCharacterSelection(characterId: string) {
    const index = selectedCharacterIds.value.indexOf(characterId)
    if (index === -1) {
      selectedCharacterIds.value.push(characterId)
    } else {
      selectedCharacterIds.value.splice(index, 1)
    }
  }

  function clearCharacterSelection() {
    selectedCharacterIds.value = []
  }

  function selectAllCharacters() {
    selectedCharacterIds.value = filteredCharacters.value.map((c) => c.id)
  }

  /**
   * Refresh thumbnail URL for a character by refreshing the underlying image signed URL
   */
  async function refreshCharacterThumbnail(characterId: string): Promise<boolean> {
    try {
      const character = characters.value.find(c => c.id === characterId)
      if (!character || !character.thumbnail_image_id) {
        console.warn(`Character ${characterId} not found or has no thumbnail`)
        return false
      }

      // Import the image generation service to refresh the image URL
      const imageGenerationService = await import('@/api/imageGenerationService')
      const refreshedUrls = await imageGenerationService.default.refreshImageUrls(character.thumbnail_image_id)

      // Update the character's thumbnail URL
      character.thumbnail_url = refreshedUrls.thumbnail_signed_url || refreshedUrls.signed_url

      console.log(`✅ Successfully refreshed thumbnail URL for character ${characterId}`)
      return true
    } catch (error) {
      console.error(`❌ Failed to refresh thumbnail for character ${characterId}:`, error)
      return false
    }
  }

  function reset() {
    characters.value = []
    currentCharacter.value = null
    charactersLoading.value = false
    charactersError.value = null
    currentPage.value = 1
    totalCharacters.value = 0
    hasMoreCharacters.value = false
    searchQuery.value = ''
    selectedCollectionId.value = null
    selectedTags.value = []
    collections.value = []
    selectedCharacterIds.value = []
  }

  return {
    // State
    characters,
    currentCharacter,
    charactersLoading,
    charactersError,
    currentPage,
    itemsPerPage,
    totalCharacters,
    hasMoreCharacters,
    searchQuery,
    selectedCollectionId,
    selectedTags,
    collections,
    collectionsLoading,
    collectionsError,
    viewMode,
    selectedCharacterIds,

    // Computed
    filteredCharacters,
    characterCount,
    collectionCount,
    selectedCharacters,
    allTags,

    // Actions
    fetchCharacters,
    loadMore,
    getCharacter,
    createCharacter,
    updateCharacter,
    deleteCharacter,
    addReferenceImage,
    removeReferenceImage,
    setPrimaryImage,
    reorderReferenceImages,
    fetchCollections,
    createCollection,
    deleteCollection,
    generateScenePrompt,
    refreshCharacterThumbnail,
    setViewMode,
    setSearchQuery,
    setSelectedCollection,
    setSelectedTags,
    toggleCharacterSelection,
    clearCharacterSelection,
    selectAllCharacters,
    reset
  }
})
