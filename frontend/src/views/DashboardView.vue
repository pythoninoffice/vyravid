<template>
  <div class="dashboard-view min-h-screen relative">
    <!-- New Video Button - Top Right Corner -->
    <button
      @click="navigateToStoryGenerator"
      class="fixed top-4 right-4 z-50 flex items-center gap-2 px-4 py-2 bg-orange-400 text-white rounded-lg hover:bg-orange-500 hover:scale-101 transition-colors font-medium shadow-lg cursor-pointer"
    >
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
      </svg>
      <span>New Video</span>
    </button>

    <div class="mx-1 px-4 sm:px-6 lg:px-8 py-8">
      <!-- Quick Actions -->
      <!-- <section class="mb-8 max-w-7xl mx-1">
        <h2 class="text-2xl font-bold text-gray-900 mb-6">Quick Actions</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6"> -->
          <!-- Reddit Stories -->
          <!-- <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow cursor-pointer"
               @click="navigateToStoryGenerator">
            <div class="flex items-center mb-4">
              <div class="bg-orange-100 p-3 rounded-lg">
                <svg class="h-6 w-6 text-orange-600" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z"/>
                </svg>
              </div>
              <div class="ml-4">
                <h3 class="text-lg font-semibold text-gray-900">Reddit Stories</h3>
                <p class="text-sm text-gray-600">Browse and transform Reddit stories</p>
              </div>
            </div>
            <div class="text-sm text-gray-500">
              Most popular workflow
            </div>
          </div> -->

          <!-- Custom Text -->
          <!-- <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow cursor-pointer"
               @click="navigateToCustomText">
            <div class="flex items-center mb-4">
              <div class="bg-blue-100 p-3 rounded-lg">
                <svg class="h-6 w-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </div>
              <div class="ml-4">
                <h3 class="text-lg font-semibold text-gray-900">Custom Text</h3>
                <p class="text-sm text-gray-600">Create videos from your own text</p>
              </div>
            </div>
            <div class="text-sm text-gray-500">
              Write your own content
            </div>
          </div> -->

          <!-- Public Gallery -->
          <!-- <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow cursor-pointer"
               @click="navigateToPublicGallery">
            <div class="flex items-center mb-4">
              <div class="bg-purple-100 p-3 rounded-lg">
                <svg class="h-6 w-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              </div>
              <div class="ml-4">
                <h3 class="text-lg font-semibold text-gray-900">Public Gallery</h3>
                <p class="text-sm text-gray-600">Discover amazing AI images shared by the community</p>
              </div>
            </div>
            <div class="text-sm text-gray-500">
              Community showcase
            </div>
          </div> -->

          <!-- Image Generator -->
          <!-- <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow cursor-pointer"
               @click="navigateToImageGenerator">
            <div class="flex items-center mb-4">
              <div class="bg-green-100 p-3 rounded-lg">
                <svg class="h-6 w-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              </div>
              <div class="ml-4">
                <h3 class="text-lg font-semibold text-gray-900">AI Image Generator</h3>
                <p class="text-sm text-gray-600">Create stunning images with AI</p>
              </div>
            </div>
            <div class="text-sm text-gray-500">
              Generate & share
            </div>
          </div> -->


          <!-- Templates -->
          <!-- <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow cursor-pointer opacity-75"
               @click="showComingSoon('Templates')">
            <div class="flex items-center mb-4">
              <div class="bg-purple-100 p-3 rounded-lg">
                <svg class="h-6 w-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
                </svg>
              </div>
              <div class="ml-4">
                <h3 class="text-lg font-semibold text-gray-900">Templates</h3>
                <p class="text-sm text-gray-600">Use pre-made video templates</p>
              </div>
            </div>
            <div class="text-sm text-gray-500">
              Coming soon
            </div>
          </div> -->
        <!-- </div>
      </section> -->

      <!-- Usage Statistics -->
      <!-- <section class="mb-8">
        <h2 class="text-2xl font-bold text-gray-900 mb-6">Your Statistics</h2>
        <div v-if="isLoading" class="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div v-for="i in 4" :key="i" class="bg-white rounded-lg shadow-sm border border-gray-200 p-6 animate-pulse">
            <div class="flex items-center">
              <div class="bg-gray-200 p-3 rounded-lg w-12 h-12"></div>
              <div class="ml-4 flex-1">
                <div class="bg-gray-200 h-8 w-16 rounded mb-2"></div>
                <div class="bg-gray-200 h-4 w-20 rounded"></div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div class="flex items-center">
              <div class="bg-blue-100 p-3 rounded-lg">
                <svg class="h-6 w-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </div>
              <div class="ml-4">
                <div class="text-2xl font-bold text-gray-900">{{ stats.videosCreated }}</div>
                <div class="text-sm text-gray-600">Videos Created</div>
              </div>
            </div>
          </div>

          <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div class="flex items-center">
              <div class="bg-green-100 p-3 rounded-lg">
                <svg class="h-6 w-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div class="ml-4">
                <div class="text-2xl font-bold text-gray-900">{{ formatTime(stats.totalProcessingTime) }}</div>
                <div class="text-sm text-gray-600">Processing Time</div>
              </div>
            </div>
          </div>

          <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div class="flex items-center">
              <div class="bg-yellow-100 p-3 rounded-lg">
                <svg class="h-6 w-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div class="ml-4">
                <div class="text-2xl font-bold text-gray-900">{{ formatStorage(stats.storageUsed) }}</div>
                <div class="text-sm text-gray-600">Storage Used</div>
              </div>
            </div>
          </div>

          <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div class="flex items-center">
              <div class="bg-purple-100 p-3 rounded-lg">
                <svg class="h-6 w-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                </svg>
              </div>
              <div class="ml-4">
                <div class="text-2xl font-bold text-gray-900">{{ stats.successRate }}%</div>
                <div class="text-sm text-gray-600">Success Rate</div>
              </div>
            </div>
          </div>
        </div>
      </section> -->

      <!-- Recent Projects -->
      <section class="mb-8">
        <div class="flex items-center gap-4 mb-6">
          <h2 class="text-xl font-bold text-gray-900">Recent Projects</h2>
          <router-link to="/app/projects" class="text-blue-600 hover:text-blue-700 font-medium text-sm">
            View All
          </router-link>
        </div>
        
        <div v-if="isLoading" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-6">
          <div v-for="i in 3" :key="i" class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden animate-pulse">
            <div class="aspect-video bg-gray-200"></div>
            <div class="p-4">
              <div class="bg-gray-200 h-5 w-3/4 rounded mb-2"></div>
              <div class="bg-gray-200 h-4 w-1/2 rounded mb-2"></div>
              <div class="flex items-center justify-between">
                <div class="bg-gray-200 h-6 w-16 rounded-full"></div>
                <div class="flex items-center gap-2">
                  <div class="bg-gray-200 h-4 w-4 rounded"></div>
                  <div class="bg-gray-200 h-4 w-4 rounded"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <div v-else-if="recentProjects.length === 0" class="bg-white rounded-lg shadow-sm border border-gray-200 p-8 text-center">
          <div class="text-gray-400 mb-4">
            <svg class="h-16 w-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </div>
          <h3 class="text-lg font-medium text-gray-900 mb-2">No projects yet</h3>
          <p class="text-gray-600 mb-4">Create your first video to see it here</p>
          <button @click="navigateToStoryGenerator" 
                  class="glow-default hover:scale-101">
            Create Your First Video
          </button>
        </div>

        <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6  gap-6">
          <div v-for="project in recentProjects" :key="project.id" 
               class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow cursor-pointer"
               @click="openProjectDetails(project)">
            <div class="aspect-video bg-gray-100 relative group">
              <!-- Video preview with hover to play -->
              <video
                v-if="project.videoUrl"
                :src="project.videoUrl"
                class="w-full h-full object-cover group-hover:scale-102 transition duration-150 ease-in-out"
                muted
                preload="metadata"
                @mouseenter="handleVideoMouseEnter"
                @mouseleave="handleVideoMouseLeave"
                @click.stop
              >
                Your browser does not support the video tag.
              </video>
              
              <!-- Fallback to thumbnail image -->
              <img
                v-else-if="project.thumbnail"
                :src="project.thumbnail"
                :alt="project.title"
                class="w-full h-full object-cover"
              />
              
              <!-- Final fallback to icon -->
              <div v-else class="w-full h-full flex items-center justify-center">
                <svg class="h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </div>
              
              <!-- Play overlay for video preview -->
              <div v-if="project.videoUrl" class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                <div class="bg-white bg-opacity-90 rounded-full p-3">
                  <svg class="h-8 w-8 text-gray-800" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z"/>
                  </svg>
                </div>
              </div>
              
              <!-- Duration badge -->
              <div v-if="project.duration" class="absolute top-2 right-2 bg-black bg-opacity-75 text-white text-xs px-2 py-1 rounded">
                {{ formatDuration(project.duration) }}
              </div>
              
              <!-- Status badge -->
              <div class="absolute bottom-2 left-2">
                <span :class="getStatusClass(project.status)" class="text-xs px-2 py-1 rounded-full">
                  {{ project.status }}
                </span>
              </div>
            </div>
            
            <div class="p-4">
              <h3 class="font-semibold text-gray-900 mb-1 truncate">{{ project.title }}</h3>
              <p class="text-sm text-gray-600 mb-2">{{ formatDate(project.createdAt) }}</p>
              <div class="flex items-center justify-between">
                <div class="text-xs text-gray-500">
                  {{ formatFileSize(project.size || 0) }}
                </div>
                <div class="flex items-center gap-1">
                  <button
                    @click.stop="duplicateProject(project)"
                    class="text-gray-400 hover:text-gray-600 p-1"
                    title="Duplicate"
                  >
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  </button>
                  <button
                    @click.stop="shareProject(project)"
                    class="text-gray-400 hover:text-gray-600 p-1"
                    title="Share"
                  >
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.367 2.684 3 3 0 00-5.367-2.684z" />
                    </svg>
                  </button>
                  <button
                    @click.stop="deleteProject(project)"
                    class="text-gray-400 hover:text-red-600 p-1"
                    title="Delete"
                  >
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- How to Use Tutorial -->
      

      <!-- Tips and Best Practices -->
      <!-- <section class="mb-8">
        <h2 class="text-2xl font-bold text-gray-900 mb-6">Tips & Best Practices</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div class="flex items-start">
              <div class="bg-green-100 p-2 rounded-lg mr-4 mt-1">
                <svg class="h-5 w-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div>
                <h3 class="font-semibold text-gray-900 mb-2">Choose Engaging Stories</h3>
                <p class="text-gray-600 text-sm">Look for stories with high upvotes and active comments. These tend to perform better as video content.</p>
              </div>
            </div>
          </div>

          <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div class="flex items-start">
              <div class="bg-blue-100 p-2 rounded-lg mr-4 mt-1">
                <svg class="h-5 w-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </div>
              <div>
                <h3 class="font-semibold text-gray-900 mb-2">Review AI Edits</h3>
                <p class="text-gray-600 text-sm">Always review the AI-processed content. Make adjustments to ensure it flows naturally when spoken.</p>
              </div>
            </div>
          </div>

          <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div class="flex items-start">
              <div class="bg-yellow-100 p-2 rounded-lg mr-4 mt-1">
                <svg class="h-5 w-5 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </div>
              <div>
                <h3 class="font-semibold text-gray-900 mb-2">Choose the Right Background</h3>
                <p class="text-gray-600 text-sm">Select background videos that complement your story. Avoid distracting visuals that compete with captions.</p>
              </div>
            </div>
          </div>

          <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <div class="flex items-start">
              <div class="bg-purple-100 p-2 rounded-lg mr-4 mt-1">
                <svg class="h-5 w-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div>
                <h3 class="font-semibold text-gray-900 mb-2">Optimal Length</h3>
                <p class="text-gray-600 text-sm">Keep stories between 30-90 seconds for best engagement. Longer stories may lose viewer attention.</p>
              </div>
            </div>
          </div>
        </div>
      </section> -->

      <!-- Template Gallery -->
      <!-- <section class="mb-8">
        <div class="flex items-center justify-between mb-6">
          <h2 class="text-2xl font-bold text-gray-900">Template Gallery</h2>
          <span class="text-sm text-gray-500 bg-gray-100 px-3 py-1 rounded-full">Coming Soon</span>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden opacity-75">
            <div class="aspect-video bg-gradient-to-br from-blue-400 to-purple-600 flex items-center justify-center">
              <div class="text-white text-center">
                <div class="text-2xl font-bold mb-2">Gaming</div>
                <div class="text-sm opacity-75">Perfect for gaming stories</div>
              </div>
            </div>
            <div class="p-4">
              <h3 class="font-semibold text-gray-900 mb-1">Gaming Template</h3>
              <p class="text-sm text-gray-600">Minecraft parkour background with gaming-style captions</p>
            </div>
          </div>

          <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden opacity-75">
            <div class="aspect-video bg-gradient-to-br from-green-400 to-blue-600 flex items-center justify-center">
              <div class="text-white text-center">
                <div class="text-2xl font-bold mb-2">Nature</div>
                <div class="text-sm opacity-75">Calming nature scenes</div>
              </div>
            </div>
            <div class="p-4">
              <h3 class="font-semibold text-gray-900 mb-1">Nature Template</h3>
              <p class="text-sm text-gray-600">Peaceful nature backgrounds with clean typography</p>
            </div>
          </div>

          <div class="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden opacity-75">
            <div class="aspect-video bg-gradient-to-br from-red-400 to-pink-600 flex items-center justify-center">
              <div class="text-white text-center">
                <div class="text-2xl font-bold mb-2">Drama</div>
                <div class="text-sm opacity-75">High-impact storytelling</div>
              </div>
            </div>
            <div class="p-4">
              <h3 class="font-semibold text-gray-900 mb-1">Drama Template</h3>
              <p class="text-sm text-gray-600">Dynamic backgrounds with bold, attention-grabbing captions</p>
            </div>
          </div>
        </div>
      </section> -->
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { dashboardService, type UserStats, type Project } from '@/api/dashboardService'
import apiClient from '@/api/apiClient'
import { toast } from 'vue-sonner'
import { getProjectEditorRoute } from '@/utils/projectRouting'

const router = useRouter()

// Data from API
const stats = ref<UserStats>({
  videosCreated: 0,
  totalProcessingTime: 0,
  storageUsed: 0,
  successRate: 100
})

const recentProjects = ref<Project[]>([])
const isLoading = ref(true)


// Methods
const navigateToStoryGenerator = async () => {
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

const navigateToCustomText = async () => {
  try {
    // Create a new empty project
    const response = await apiClient.post('/api/video/projects/create-empty', {
      title: 'Untitled Project'
    })

    const projectId = response.data.project_id

    // Navigate to the new project
    router.push(`/app/projects/${projectId}`)
  } catch (error: any) {
    console.error('Failed to create new project:', error)
    toast.error('Failed to create new project', {
      description: error.response?.data?.detail || 'Please try again'
    })
  }
}

const navigateToPublicGallery = () => {
  router.push('/app/public-gallery')
}

const navigateToImageGenerator = () => {
  router.push('/app/image-generator')
}

const showComingSoon = (feature: string) => {
  alert(`${feature} feature is coming soon! Stay tuned for updates.`)
}

const duplicateProject = async (project: Project) => {
  try {
    const duplicatedProject = await dashboardService.duplicateProject(project.id)
    recentProjects.value.unshift(duplicatedProject)
    // Update stats
    stats.value.videosCreated += 1
  } catch (error) {
    alert('Failed to duplicate project. Please try again.')
  }
}

const deleteProject = async (project: Project) => {
  if (confirm(`Are you sure you want to delete "${project.title}"?`)) {
    try {
      await dashboardService.deleteProject(project.id)
      const index = recentProjects.value.findIndex(p => p.id === project.id)
      if (index > -1) {
        recentProjects.value.splice(index, 1)
      }
      

      
      // Update stats
      stats.value.videosCreated = Math.max(0, stats.value.videosCreated - 1)
    } catch (error) {
      alert('Failed to delete project. Please try again.')
    }
  }
}

const openProjectDetails = (project: Project) => {
  router.push(getProjectEditorRoute(project))
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
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } else {
    alert('No video URL available for download')
  }
}

// Utility functions
const formatDate = (dateString?: string) => {
  if (!dateString) return 'N/A'
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
}

const formatTime = (seconds: number) => {
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
}

const formatStorage = (bytes: number) => {
  if (bytes === 0) return '0 MB'
  const mb = bytes / (1024 * 1024)
  if (mb < 1024) return `${mb.toFixed(1)} MB`
  const gb = mb / 1024
  return `${gb.toFixed(1)} GB`
}

const formatDuration = (seconds: number) => {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds) % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 MB'
  const mb = bytes / (1024 * 1024)
  if (mb < 1024) return `${mb.toFixed(1)} MB`
  const gb = mb / 1024
  return `${gb.toFixed(1)} GB`
}

const getStatusClass = (status: string) => {
  switch (status.toLowerCase()) {
    case 'completed':
      return 'bg-green-100 text-green-800'
    case 'processing':
      return 'bg-yellow-100 text-yellow-800'
    case 'failed':
      return 'bg-red-100 text-red-800'
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

// Load data on mount
onMounted(async () => {
  try {
    isLoading.value = true
    
    // Load user stats and recent projects in parallel
    console.log('🔍 Dashboard: Loading dashboard data...')
    
    const [userStats, projects] = await Promise.all([
      dashboardService.getUserStats(),
      dashboardService.getRecentProjects(6)
    ])
    
    console.log('✅ Dashboard: User stats loaded:', userStats)
    console.log('✅ Dashboard: Recent projects loaded:', projects.length, projects)
    
    stats.value = userStats
    recentProjects.value = projects

  } catch (error) {
    console.error('❌ Dashboard: Failed to load dashboard data:', error)
    // Set empty state
    recentProjects.value = []
  } finally {
    isLoading.value = false
  }
})
</script>

<style scoped>
.prose h4 {
  font-weight: 600;
  color: #111827;
  margin-top: 1rem;
  margin-bottom: 0.5rem;
}

.prose p {
  color: #4b5563;
  margin-bottom: 0.75rem;
}

.prose ul, .prose ol {
  color: #4b5563;
  margin-bottom: 0.75rem;
  padding-left: 1.25rem;
}

.prose li {
  margin-bottom: 0.25rem;
}

/* video {
  transition: transform 0.2s ease;
}

.group:hover video {
  transform: scale(1.02);
} */

/* Ensure video previews don't interfere with click events */
/* video:hover {
  cursor: pointer;
} */

/* Smooth play overlay transitions */
/* .group .absolute {
  transition: opacity 0.3s ease;
} */

</style>
