<template>
  <div class="project-manager h-full flex flex-col">
    <!-- Header with controls -->
    <div class="bg-white border-b border-gray-200 p-4 flex-shrink-0">
      <div class="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        <!-- Title and view toggle -->
        <div class="flex items-center gap-4">
          <h2 class="text-xl font-semibold text-gray-900">Project Manager</h2>
          <div class="flex items-center bg-gray-100 rounded-lg p-1">
            <button @click="viewMode = 'grid'" :class="[
              'px-3 py-1 rounded-md text-sm font-medium transition-colors',
              viewMode === 'grid'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            ]">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
              </svg>
            </button>
            <button @click="viewMode = 'list'" :class="[
              'px-3 py-1 rounded-md text-sm font-medium transition-colors',
              viewMode === 'list'
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            ]">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M4 6h16M4 10h16M4 14h16M4 18h16" />
              </svg>
            </button>
          </div>
        </div>

        <!-- Search and filters -->
        <div class="flex flex-col sm:flex-row gap-3 flex-1 max-w-2xl">
          <div class="relative flex-1">
            <input v-model="searchQuery" type="text" placeholder="Search projects..."
              class="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent" />
            <svg class="absolute left-3 top-2.5 h-5 w-5 text-gray-400" fill="none" stroke="currentColor"
              viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>

          <select v-model="statusFilter"
            class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent">
            <option value="">All Status</option>
            <option value="completed">Completed</option>
            <option value="processing">Processing</option>
            <option value="failed">Failed</option>
            <option value="draft">Draft</option>
          </select>

          <select v-model="dateFilter"
            class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent">
            <option value="">All Time</option>
            <option value="today">Today</option>
            <option value="week">This Week</option>
            <option value="month">This Month</option>
            <option value="year">This Year</option>
          </select>
        </div>

        <!-- Selection and bulk actions -->
        <div class="flex items-center gap-3">
          <!-- Select all filtered -->
          <div v-if="filteredProjects.length > 0" class="flex items-center gap-2">
            <label class="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
              <input
                type="checkbox"
                :checked="isAllFilteredSelected"
                @change="toggleSelectAllFiltered"
                class="select-all-checkbox h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
              />
              <span v-if="selectedProjects.size === 0">Select all</span>
              <span v-else-if="isAllFilteredSelected">All selected ({{ selectedProjects.size }})</span>
              <span v-else>{{ selectedProjects.size }} selected</span>
            </label>
          </div>

          <!-- Bulk action buttons -->
          <div v-if="selectedProjects.size > 0" class="flex items-center gap-2 border-l border-gray-300 pl-3">
            <button @click="bulkDelete"
              class="px-3 py-2 text-red-600 hover:text-red-700 text-sm font-medium border border-red-200 rounded-lg hover:bg-red-50 transition-colors">
              Delete Selected ({{ selectedProjects.size }})
            </button>
            <button @click="bulkExport"
              class="px-3 py-2 text-blue-600 hover:text-blue-700 text-sm font-medium border border-blue-200 rounded-lg hover:bg-blue-50 transition-colors">
              Export Selected
            </button>
          </div>

          <!-- Delete all filtered (when nothing selected but filters applied) -->
          <div v-else-if="filteredProjects.length > 0 && (searchQuery || statusFilter || dateFilter)" class="flex items-center">
            <button @click="deleteAllFiltered"
              class="px-3 py-2 text-red-600 hover:text-red-700 text-sm font-medium border border-red-200 rounded-lg hover:bg-red-50 transition-colors">
              Delete All Filtered ({{ filteredProjects.length }})
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <div class="text-center">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-orange-600 mx-auto mb-4"></div>
        <p class="text-gray-600">Loading projects...</p>
      </div>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="flex-1 flex items-center justify-center">
      <div class="text-center">
        <div class="text-red-500 mb-4">
          <svg class="h-12 w-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <p class="text-gray-800 font-medium mb-2">Error loading projects</p>
        <p class="text-gray-600 mb-4">{{ error }}</p>
        <button @click="loadProjects" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
          Try Again
        </button>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="filteredProjects.length === 0 && !searchQuery && !statusFilter && !dateFilter"
      class="flex-1 flex items-center justify-center">
      <div class="text-center">
        <div class="text-gray-400 mb-4">
          <svg class="h-16 w-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        </div>
        <h3 class="text-lg font-medium text-gray-900 mb-2">No projects yet</h3>
        <p class="text-gray-600 mb-4">Create your first video project to see it here</p>
        <button @click="createNewVideo" class="glow-default px-4 py-2">
          Create First Project
        </button>
      </div>
    </div>

    <!-- No results state -->
    <div v-else-if="filteredProjects.length === 0" class="flex-1 flex items-center justify-center">
      <div class="text-center">
        <div class="text-gray-400 mb-4">
          <svg class="h-12 w-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <p class="text-gray-600 mb-4">No projects match your filters</p>
        <button @click="clearFilters" class="px-4 py-2 text-blue-600 hover:text-blue-700">
          Clear Filters
        </button>
      </div>
    </div>

    <!-- Projects grid/list -->
    <div v-else class="flex-1 overflow-auto p-4">
      <!-- Grid view -->
      <div v-if="viewMode === 'grid'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-6">
        <div v-for="project in filteredProjects" :key="project.id"
          class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow cursor-pointer"
          @click="openProjectDetails(project)">
          <!-- Video Preview -->
          <div class="aspect-video bg-gray-100 relative group">
            <!-- Show actual video preview if available -->
            <video v-if="project.videoUrl" :src="project.videoUrl" class="w-full h-full object-cover" muted
              preload="metadata" @mouseenter="handleVideoMouseEnter"
              @mouseleave="handleVideoMouseLeave" @click.stop>
              Your browser does not support the video tag.
            </video>

            <!-- Fallback to thumbnail image -->
            <img v-else-if="project.thumbnail" :src="project.thumbnail" :alt="project.title"
              class="w-full h-full object-cover" />

            <!-- Final fallback to icon -->
            <div v-else class="w-full h-full flex items-center justify-center">
              <svg class="h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            </div>

            <!-- Play overlay for video preview -->
            <div v-if="project.videoUrl"
              class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
              <div class="bg-white bg-opacity-90 rounded-full p-3">
                <svg class="h-8 w-8 text-gray-800" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z" />
                </svg>
              </div>
            </div>

            <!-- Selection checkbox -->
            <div class="absolute top-2 left-2">
              <input type="checkbox" :checked="selectedProjects.has(project.id)"
                @click.stop="toggleProjectSelection(project.id)"
                class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded" />
            </div>

            <!-- Duration badge -->
            <div v-if="project.duration"
              class="absolute top-2 right-2 bg-black bg-opacity-75 text-white text-xs px-2 py-1 rounded">
              {{ formatDuration(project.duration) }}
            </div>

            <!-- Status badge -->
            <div class="absolute bottom-2 left-2">
              <span :class="getStatusClass(project.status)" class="text-xs px-2 py-1 rounded-full">
                {{ project.status }}
              </span>
            </div>
          </div>

          <!-- Project info -->
          <div class="p-4">
            <h3 class="font-semibold text-gray-900 mb-1 truncate">{{ project.title }}</h3>
            <p class="text-sm text-gray-600 mb-2">{{ formatDate(project.createdAt) }}</p>
            <div class="flex items-center justify-between">
              <div class="text-xs text-gray-500">
                {{ formatFileSize(project.size || 0) }}
              </div>
              <div class="flex items-center gap-1">
                <button @click.stop="editProject(project)" class="text-gray-400 hover:text-blue-600 p-1"
                  title="Edit Project">
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                <button @click.stop="duplicateProject(project)" class="text-gray-400 hover:text-gray-600 p-1"
                  title="Duplicate">
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                </button>
                <button @click.stop="shareProject(project)" class="text-gray-400 hover:text-gray-600 p-1" title="Share">
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.367 2.684 3 3 0 00-5.367-2.684z" />
                  </svg>
                </button>
                <button @click.stop="deleteProject(project)" class="text-gray-400 hover:text-red-600 p-1"
                  title="Delete">
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- List view -->
      <div v-else class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <div class="divide-y divide-gray-200">
          <div v-for="project in filteredProjects" :key="project.id"
            class="p-4 hover:bg-gray-50 transition-colors cursor-pointer" @click="openProjectDetails(project)">
            <div class="flex items-center gap-4">
              <!-- Selection checkbox -->
              <input type="checkbox" :checked="selectedProjects.has(project.id)"
                @click.stop="toggleProjectSelection(project.id)"
                class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded" />

              <!-- Video Preview -->
              <div
                class="w-16 h-12 bg-gray-100 rounded flex-shrink-0 flex items-center justify-center relative group overflow-hidden">
                <!-- Show actual video preview if available -->
                <video v-if="project.videoUrl" :src="project.videoUrl" class="w-full h-full object-cover rounded" muted
                  preload="metadata" @mouseenter="handleVideoMouseEnter"
                  @mouseleave="handleVideoMouseLeave" @click.stop>
                  Your browser does not support the video tag.
                </video>

                <!-- Fallback to thumbnail image -->
                <img v-else-if="project.thumbnail" :src="project.thumbnail" :alt="project.title"
                  class="w-full h-full object-cover rounded" />

                <!-- Final fallback to icon -->
                <svg v-else class="h-6 w-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>

                <!-- Small play indicator for list view -->
                <div v-if="project.videoUrl"
                  class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black bg-opacity-30 rounded">
                  <svg class="h-4 w-4 text-white" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </div>
              </div>

              <!-- Project info -->
              <div class="flex-1 min-w-0">
                <h3 class="font-semibold text-gray-900 truncate">{{ project.title }}</h3>
                <div class="flex items-center gap-4 text-sm text-gray-500 mt-1">
                  <span>{{ formatDate(project.createdAt) }}</span>
                  <span v-if="project.duration">{{ formatDuration(project.duration) }}</span>
                  <span>{{ formatFileSize(project.size || 0) }}</span>
                </div>
              </div>

              <!-- Status -->
              <div class="flex-shrink-0">
                <span :class="getStatusClass(project.status)" class="text-xs px-2 py-1 rounded-full">
                  {{ project.status }}
                </span>
              </div>

              <!-- Actions -->
              <div class="flex items-center gap-1 flex-shrink-0">
                <button @click.stop="editProject(project)" class="text-gray-400 hover:text-blue-600 p-2"
                  title="Edit Project">
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                <button @click.stop="duplicateProject(project)" class="text-gray-400 hover:text-gray-600 p-2"
                  title="Duplicate">
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                </button>
                <button @click.stop="shareProject(project)" class="text-gray-400 hover:text-gray-600 p-2" title="Share">
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.367 2.684 3 3 0 00-5.367-2.684z" />
                  </svg>
                </button>
                <button @click.stop="deleteProject(project)" class="text-gray-400 hover:text-red-600 p-2"
                  title="Delete">
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>


  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { dashboardService, type Project } from '@/api/dashboardService'
import { formatDistanceToNow } from 'date-fns'
import apiClient from '@/api/apiClient'
import { toast } from 'vue-sonner'
import { getProjectEditorRoute } from '@/utils/projectRouting'

const router = useRouter()

// State
const projects = ref<Project[]>([])
const selectedProjects = ref<Set<string>>(new Set())

const loading = ref(true)
const error = ref<string | null>(null)

// Filters and view
const viewMode = ref<'grid' | 'list'>('grid')
const searchQuery = ref('')
const statusFilter = ref('')
const dateFilter = ref('')

// Computed
const filteredProjects = computed(() => {
  let filtered = projects.value

  // Search filter
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    filtered = filtered.filter(project =>
      project.title.toLowerCase().includes(query)
    )
  }

  // Status filter
  if (statusFilter.value) {
    filtered = filtered.filter(project => project.status === statusFilter.value)
  }

  // Date filter
  if (dateFilter.value) {
    const now = new Date()
    const filterDate = new Date()

    switch (dateFilter.value) {
      case 'today':
        filterDate.setHours(0, 0, 0, 0)
        break
      case 'week':
        filterDate.setDate(now.getDate() - 7)
        break
      case 'month':
        filterDate.setMonth(now.getMonth() - 1)
        break
      case 'year':
        filterDate.setFullYear(now.getFullYear() - 1)
        break
    }

    filtered = filtered.filter(project =>
      new Date(project.createdAt) >= filterDate
    )
  }

  return filtered.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
})

// Selection computed properties
const filteredProjectIds = computed(() => filteredProjects.value.map(p => p.id))

const isAllFilteredSelected = computed(() => {
  return filteredProjects.value.length > 0 &&
         filteredProjects.value.every(project => selectedProjects.value.has(project.id))
})

const isSomeFilteredSelected = computed(() => {
  return filteredProjects.value.some(project => selectedProjects.value.has(project.id))
})

// Methods
const loadProjects = async () => {
  loading.value = true
  error.value = null

  try {

    projects.value = await dashboardService.getAllProjects()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load projects'
    console.error('❌ ProjectManager: Error loading projects:', err)
  } finally {
    loading.value = false
  }
}

const toggleProjectSelection = (projectId: string) => {
  if (selectedProjects.value.has(projectId)) {
    selectedProjects.value.delete(projectId)
  } else {
    selectedProjects.value.add(projectId)
  }
}

const toggleSelectAllFiltered = (event: Event) => {
  const target = event.target as HTMLInputElement

  if (target.checked) {
    // Select all filtered projects
    filteredProjects.value.forEach(project => {
      selectedProjects.value.add(project.id)
    })
  } else {
    // Deselect all filtered projects
    filteredProjects.value.forEach(project => {
      selectedProjects.value.delete(project.id)
    })
  }
}

const openProjectDetails = (project: Project) => {
  router.push(getProjectEditorRoute(project))
}

const editProject = (project: Project) => {
  router.push(getProjectEditorRoute(project))
}


const duplicateProject = async (project: Project) => {
  try {
    const duplicatedProject = await dashboardService.duplicateProject(project.id)
    projects.value.unshift(duplicatedProject)
    // Show success message
    console.log('Project duplicated successfully')
  } catch (err) {
    console.error('Failed to duplicate project:', err)
    // Show error message
  }
}

const deleteProject = async (project: Project) => {
  if (!confirm(`Are you sure you want to delete "${project.title}"?`)) {
    return
  }

  try {
    await dashboardService.deleteProject(project.id)
    projects.value = projects.value.filter(p => p.id !== project.id)
    selectedProjects.value.delete(project.id)

    console.log('Project deleted successfully')
  } catch (err) {
    console.error('Failed to delete project:', err)
    // Show error message
  }
}

const shareProject = (project: Project) => {
  if (navigator.share && project.videoUrl) {
    navigator.share({
      title: project.title,
      url: project.videoUrl
    })
  } else if (project.videoUrl) {
    // Fallback: copy to clipboard
    navigator.clipboard.writeText(project.videoUrl)
    alert('Video URL copied to clipboard!')
  } else {
    alert('No video URL available for sharing')
  }
}

const downloadProject = (project: Project) => {
  if (project.videoUrl) {
    const link = document.createElement('a')
    link.href = project.videoUrl
    link.download = `${project.title}.mp4`
    link.click()
  } else {
    alert('No video available for download')
  }
}

const bulkDelete = async () => {
  const selectedIds = Array.from(selectedProjects.value)
  if (!confirm(`Are you sure you want to delete ${selectedIds.length} projects?`)) {
    return
  }

  try {
    await Promise.all(selectedIds.map(id => dashboardService.deleteProject(id)))
    projects.value = projects.value.filter(p => !selectedProjects.value.has(p.id))
    selectedProjects.value.clear()
    console.log('Projects deleted successfully')
  } catch (err) {
    console.error('Failed to delete projects:', err)
    // Show error message
  }
}

const deleteAllFiltered = async () => {
  const filteredIds = filteredProjects.value.map(p => p.id)
  const filterDescription = getFilterDescription()

  if (!confirm(`Are you sure you want to delete all ${filteredIds.length} projects${filterDescription}? This action cannot be undone.`)) {
    return
  }

  try {
    await Promise.all(filteredIds.map(id => dashboardService.deleteProject(id)))
    projects.value = projects.value.filter(p => !filteredIds.includes(p.id))
    selectedProjects.value.clear()
    console.log(`Deleted ${filteredIds.length} projects successfully`)
  } catch (err) {
    console.error('Failed to delete filtered projects:', err)
    // Show error message
  }
}

const getFilterDescription = () => {
  const filters = []
  if (searchQuery.value) filters.push(`matching "${searchQuery.value}"`)
  if (statusFilter.value) filters.push(`with status "${statusFilter.value}"`)
  if (dateFilter.value) filters.push(`from ${dateFilter.value}`)

  return filters.length > 0 ? ` (${filters.join(', ')})` : ''
}

const bulkExport = () => {
  const selectedProjectsList = projects.value.filter(p => selectedProjects.value.has(p.id))

  // Create a simple CSV export
  const csvContent = [
    'Title,Status,Created,Duration,Size',
    ...selectedProjectsList.map(p =>
      `"${p.title}","${p.status}","${p.createdAt}","${p.duration}","${p.size || 0}"`
    )
  ].join('\n')

  const blob = new Blob([csvContent], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'projects-export.csv'
  link.click()
  URL.revokeObjectURL(url)
}

const clearFilters = () => {
  searchQuery.value = ''
  statusFilter.value = ''
  dateFilter.value = ''
  selectedProjects.value.clear()
}

const createNewVideo = async () => {
  try {
    console.log('🎬 Creating new video project...')

    const response = await apiClient.post('/api/video/projects/create-empty', {
      title: 'Untitled Project'
    })

    const projectId = response.data.project_id
    console.log('✅ New project created:', projectId)

    router.push(`/app/projects/${projectId}`)
  } catch (error: any) {
    console.error('❌ Failed to create new project:', error)
    toast.error('Failed to create new project', {
      description: error.response?.data?.detail || 'Please try again'
    })
  }
}

// Utility functions
const formatDate = (dateString: string) => {
  return formatDistanceToNow(new Date(dateString), { addSuffix: true })
}

const formatDuration = (seconds: number) => {
  if (!seconds) return '0:00'
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = Math.floor(seconds) % 60
  console.log(seconds % 60)
  console.log(remainingSeconds)
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const getStatusClass = (status: string) => {
  switch (status) {
    case 'completed':
      return 'bg-green-100 text-green-800'
    case 'processing':
      return 'bg-blue-100 text-blue-800'
    case 'failed':
      return 'bg-red-100 text-red-800'
    case 'draft':
      return 'bg-gray-100 text-gray-800'
    default:
      return 'bg-gray-100 text-gray-800'
  }
}

// Video event handlers
const handleVideoMouseEnter = (event: Event) => {
  const video = event.target as HTMLVideoElement
  if (video) {
    video.play()
  }
}

const handleVideoMouseLeave = (event: Event) => {
  const video = event.target as HTMLVideoElement
  if (video) {
    video.pause()
    video.currentTime = 0
  }
}

// Watchers
watch([isSomeFilteredSelected, isAllFilteredSelected], () => {
  nextTick(() => {
    const selectAllCheckbox = document.querySelector('.select-all-checkbox') as HTMLInputElement
    if (selectAllCheckbox) {
      selectAllCheckbox.indeterminate = isSomeFilteredSelected.value && !isAllFilteredSelected.value
    }
  })
})

// Clear selections when filters change (optional - can be removed if too aggressive)
watch([searchQuery, statusFilter, dateFilter], () => {
  // Only clear if no filtered projects are selected anymore
  const currentFilteredIds = filteredProjects.value.map(p => p.id)
  const selectedFilteredIds = Array.from(selectedProjects.value).filter(id => currentFilteredIds.includes(id))

  if (selectedFilteredIds.length === 0 && selectedProjects.value.size > 0) {
    selectedProjects.value.clear()
  }
})

// Lifecycle
onMounted(() => {
  loadProjects()
})
</script>

<style scoped>
.aspect-video {
  aspect-ratio: 16 / 9;
}

/* Video preview enhancements */
video {
  transition: transform 0.2s ease;
}

.group:hover video {
  transform: scale(1.02);
}

/* Ensure video previews don't interfere with click events */
video:hover {
  cursor: pointer;
}

/* Smooth play overlay transitions */
.group .absolute {
  transition: opacity 0.3s ease;
}
</style>
