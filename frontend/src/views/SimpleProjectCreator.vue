<template>
  <div class="simple-creator">
    <!-- Toast notifications -->
    <!-- <Toaster position="top-right" /> -->

    <!-- Project Selector Modal (shown when no project ID and there are recent projects) -->
    <div v-if="!projectId && !isLoadingProjects && !hasDissmissedSelector && recentProjects.length > 0" class="project-selector-overlay">
      <div class="project-selector-modal">
        <div class="modal-header">
          <h2>Select a Project</h2>
          <p>Choose a recent project to edit or start a new one</p>
        </div>

        <div class="modal-actions">
          <button @click="startNewProject" class="new-project-btn">
            <i class="fa-solid fa-plus"></i>
            Start New Project
          </button>
        </div>

        <div v-if="recentProjects.length > 0" class="projects-list">
          <h3>Recent Projects</h3>
          <div class="project-items">
            <div
              v-for="project in recentProjects"
              :key="project.id"
              @click="selectProject(project)"
              class="project-item"
            >
              <div class="project-info">
                <h4>{{ project.title }}</h4>
                <p class="project-meta">
                  <span class="project-status" :class="`status-${project.status}`">
                    {{ project.status }}
                  </span>
                  <span class="project-date">
                    {{ formatDate(project.last_edited_at || project.created_at) }}
                  </span>
                </p>
              </div>
              <i class="fa-solid fa-chevron-right"></i>
            </div>
          </div>
        </div>

        <div v-else class="no-projects">
          <i class="fa-regular fa-folder-open"></i>
          <p>No recent projects</p>
          <p class="hint">Click "Start New Project" to begin</p>
        </div>
      </div>
    </div>

    <!-- Loading overlay -->
    <div v-if="isLoadingProjects || isLoadingProject || isGeneratingAnimalHaircutPrompts" class="loading-overlay">
      <div class="loading-spinner">
        <i class="fa-solid fa-spinner fa-spin"></i>
        <p class="font-orange-600">
          {{ isGeneratingAnimalHaircutPrompts ? 'Cooking magic...' : (isLoadingProject ? 'Loading project...' : 'Loading projects...') }}
        </p>
      </div>
    </div>

    <header>
      <div class="header-title-section">
        <div class="logo">
          <button
            @click="goBackToProjects"
            class="title-back-button"
            title="Back to Projects"
            aria-label="Back to Projects"
          >
            <i class="fa-solid fa-arrow-left"></i>
          </button>
          <!-- Editable Title -->
          <h1 v-if="!isEditingTitle" class="text-lg font-semibold text-gray-900 truncate">{{ projectTitle }}</h1>
          <input
            v-else
            v-model="editingTitle"
            @blur="saveTitle"
            @keydown.enter="saveTitle"
            @keydown.escape="cancelEdit"
            ref="titleInput"
            class="text-lg font-semibold text-gray-900 bg-transparent border-b-2 border-blue-500 outline-none"
            :style="{ width: Math.max(200, editingTitle.length * 14) + 'px' }"
          />
          <button
            @click="toggleTitleEdit"
            :disabled="isSavingTitle"
            class="text-gray-400 hover:text-gray-600 disabled:opacity-50 transition-colors flex-shrink-0"
            :title="isEditingTitle ? 'Save title' : 'Edit title'"
          >
            <svg v-if="!isEditingTitle" class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
          </button>
          <div v-if="isSavingTitle" class="animate-spin rounded-full h-3 w-3 border-b-2 border-blue-500 flex-shrink-0"></div>
        </div>

        <div class="header-actions header-actions-mobile">
          <Button @click="saveDraft" :disabled="isSavingDraft" class="!bg-orange-500 !text-white hover:!bg-orange-600 disabled:opacity-50" title="Save Draft">
            <i v-if="!isSavingDraft" class="fa-solid fa-save"></i>
            <i v-else class="fa-solid fa-spinner fa-spin"></i>
            <span class="ml-1 button-label">{{ isSavingDraft ? 'Saving...' : 'Save' }}</span>
          </Button>
          <Button title="Settings"><i class="fa-solid fa-gear"></i></Button>
          <Button title="Profile" @click="router.push({ name: 'profile' })"><i class="fa-solid fa-user-circle"></i></Button>
        </div>
      </div>

      <!-- Navigation Tabs (separate row on mobile) -->
      <nav class="header-nav-tabs" aria-label="Project sections">
        <button
          @click="showStoryboardLayout = false; showingFinalVideo = false; showingGallery = false; showingPreview = false; showingThumbnail = false"
          class="top-nav-item"
          :class="{ 'top-nav-item-active': !showStoryboardLayout && !showingFinalVideo && !showingGallery && !showingPreview && !showingThumbnail }"
          :aria-current="!showStoryboardLayout && !showingFinalVideo && !showingGallery && !showingPreview && !showingThumbnail ? 'page' : undefined"
          title="Script editor"
        >
          <i class="fa-solid fa-file-lines"></i>
          <span class="top-nav-label">Script</span>
        </button>
        <button
          @click="showStoryboardLayout = true; showingFinalVideo = false; showingGallery = false; showingPreview = false; showingThumbnail = false"
          class="top-nav-item"
          :class="{ 'top-nav-item-active': showStoryboardLayout && !showingFinalVideo && !showingGallery && !showingPreview && !showingThumbnail }"
          :aria-current="showStoryboardLayout && !showingFinalVideo && !showingGallery && !showingPreview && !showingThumbnail ? 'page' : undefined"
          title="Storyboard view"
        >
          <i class="fa-solid fa-images"></i>
          <span class="top-nav-label">Storyboard</span>
        </button>
        <!-- comment out preview button for now, will add it back later -->
        <!-- <button
          @click="showStoryboardLayout = true; showingPreview = true; showingFinalVideo = false; showingGallery = false; showingThumbnail = false"
          class="top-nav-item"
          :class="{ 'top-nav-item-active': showingPreview }"
          title="Remotion preview"
          :disabled="scenes.length === 0"
        >
          <i class="fa-solid fa-play-circle"></i>
          <span class="top-nav-label">Preview</span>
        </button> -->
        <button
          @click="showGalleryView"
          class="top-nav-item"
          :class="{ 'top-nav-item-active': showingGallery }"
          :aria-current="showingGallery ? 'page' : undefined"
          title="Gallery view"
        >
          <i class="fa-solid fa-border-all"></i>
          <span class="top-nav-label">Gallery</span>
        </button>
        <button
          @click="showThumbnailView"
          class="top-nav-item"
          :class="{ 'top-nav-item-active': showingThumbnail }"
          :aria-current="showingThumbnail ? 'page' : undefined"
          title="Thumbnail view"
        >
          <i class="fa-solid fa-image-portrait"></i>
          <span class="top-nav-label">Thumbnail</span>
        </button>
        <button
          @click="showFinalVideoPreview"
          class="top-nav-item"
          :class="{ 'top-nav-item-active': showingFinalVideo }"
          :aria-current="showingFinalVideo ? 'page' : undefined"
          title="Final video preview"
        >
          <i class="fa-solid fa-video"></i>
          <span class="top-nav-label">Video</span>
        </button>
      </nav>

      <!-- Action buttons for large screens -->
      <div class="header-actions header-actions-desktop">
        <Button @click="saveDraft" :disabled="isSavingDraft" class="bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-50" title="Save Draft">
          <i v-if="!isSavingDraft" class="fa-solid fa-save"></i>
          <i v-else class="fa-solid fa-spinner fa-spin"></i>
          <span class="ml-1">{{ isSavingDraft ? 'Saving...' : 'Save' }}</span>
        </Button>
        <Button title="Settings"><i class="fa-solid fa-gear"></i></Button>
        <Button title="Profile" @click="router.push({ name: 'profile' })"><i class="fa-solid fa-user-circle"></i></Button>
      </div>
    </header>

    <div class="main-container">
      <div class="workspace">
      <!-- LEFT PANEL - INPUTS -->
      <aside class="input-panel">
        <!-- INITIAL MODE: Script/Audio Inputs -->
        <div v-if="!showStoryboardLayout">
          <!-- Go to Storyboard Button (only show if scenes exist) -->
          <!-- <Button
            v-if="scenes.length > 0"
            @click="showStoryboardLayout = true"
            variant="ghost"
            class="w-fit px-3 py-2 mb-3 text-gray-600 hover:text-gray-900 hover:bg-gray-100"
            title="Go to storyboard view"
          >
            <i class="fa-solid fa-images"></i>
            <span>Go to Storyboard</span>
          </Button> -->

          <!-- Tab System - HIDDEN (moved to preview area) -->
          <div class="creation-mode-tabs" style="display: none;">



          <!-- Idea to vide / Repurpose -->
          <DropdownMenu>啊啊啊啊
            <DropdownMenuTrigger as-child>
              <Button
                class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg cursor-pointer transition-all duration-200"
                :class="creationMode === 'ideaToVideo' ? 'bg-orange-500 text-white' : 'bg-black text-white hover:bg-orange-500/10 hover:text-orange-500'"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-4">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 0 0 1.5-.189m-1.5.189a6.01 6.01 0 0 1-1.5-.189m3.75 7.478a12.06 12.06 0 0 1-4.5 0m3.75 2.383a14.406 14.406 0 0 1-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 1 0-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                </svg>
                Idea to Video
                <svg class="w-3 h-3 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem @click="creationMode = 'ideaToVideo'; ideaSubMode = 'ideas'">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4 mr-2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 0 0 1.5-.189m-1.5.189a6.01 6.01 0 0 1-1.5-.189m3.75 7.478a12.06 12.06 0 0 1-4.5 0m3.75 2.383a14.406 14.406 0 0 1-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 1 0-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                </svg>
                Ideas
              </DropdownMenuItem>
              <DropdownMenuItem @click="creationMode = 'ideaToVideo'; ideaSubMode = 'repurpose'">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4 mr-2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
                Repurpose
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <!-- Script to video -->
          <Button
            class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg cursor-pointer transition-all duration-200"
            :class="creationMode === 'scriptToVideo' ? 'bg-orange-500 text-white' : 'bg-black text-white hover:bg-orange-500/10 hover:text-orange-500'"
            @click="creationMode = 'scriptToVideo'"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Script to Video
          </Button>



          <!-- AUdio to video -->
          <Button
            class="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg cursor-pointer transition-all duration-200"
            :class="creationMode === 'audioToVideo' ? 'bg-orange-500 text-white' : 'bg-black text-white hover:bg-orange-500/10 hover:text-orange-500'"
            @click="creationMode = 'audioToVideo'"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            Audio to Video
          </Button>
        </div>

        <!-- Script to Video Mode - HIDDEN (moved to preview area) -->
        <div v-if="false && creationMode === 'scriptToVideo'">
          <div class="section-label">The Script</div>
          <div class="script-box">
            <textarea
              v-model="script"
              placeholder="Once upon a time in a futuristic city..."
              class="w-full h-[250px] border-2 rounded-lg p-4 text-base resize-none outline-none transition-colors duration-200 focus:border-blue-500"
              rows="50"
            ></textarea>
            <!-- Voice Settings Button (Bottom Left) -->
            <button class="absolute bottom-3 left-3 bg-orange-500 text-white border-0 p-2 rounded-md w-20 h-8 gap-1 cursor-pointer flex items-center justify-center transition-all duration-200 shadow-md hover:bg-gray-700 hover:scale-105 hover:shadow-lg" @click="isVoiceModalOpen = !isVoiceModalOpen" title="Voice Settings">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="2" y="8" width="2" height="8" rx="1" fill="currentColor"/>
                <rect x="6" y="4" width="2" height="16" rx="1" fill="currentColor"/>
                <rect x="10" y="10" width="2" height="4" rx="1" fill="currentColor"/>
                <rect x="14" y="6" width="2" height="12" rx="1" fill="currentColor"/>
                <rect x="18" y="9" width="2" height="6" rx="1" fill="currentColor"/>
              </svg>
              <span class='font-semibold'>Voice</span>
            </button>
            <span v-if="selectedVoiceObject" class="absolute bottom-3 left-24 text-sm text-gray-700 bg-gray-100 px-3 py-1 rounded-md font-medium">{{ selectedVoiceObject?.name }}</span>
            <!-- <button class="ai-assist-btn text-white" @click="improveScript">
              <i class="fa-solid fa-pen-nib"></i> Improve
            </button> -->
          </div>

          <!-- Script Stats -->
          <div v-if="script.length > 0" class="mt-2 text-xs text-gray-600 space-y-1">
            <div class="flex justify-between">
              <span>{{ sentenceCount }} sentence{{ sentenceCount !== 1 ? 's' : '' }} • {{ wordCount }} words • ~{{ estimatedDuration }} min</span>
              <span class="font-semibold">{{ characterCount.toLocaleString() }} characters</span>
            </div>
          </div>

          <!-- Voice Settings Modal -->
          <div v-if="isVoiceModalOpen" class="voice-modal-overlay" @click="isVoiceModalOpen = false">
            <div class="voice-modal" @click.stop>
              <div class="voice-modal-header">
                <h3>Voice Settings</h3>
                <button @click="isVoiceModalOpen = false" class="modal-close-btn">
                  <i class="fa-solid fa-times"></i>
                </button>
              </div>

              <div class="voice-modal-content">
                <!-- Custom Voices Section -->
                <div class="voice-section custom-voices-section">
                  <div class="custom-voices-header">
                    <h4 class="voice-section-label">My Custom Voices ({{ customVoices.length }}/5)</h4>
                    <button
                      @click="showCustomVoiceUpload = true"
                      class="btn-add-voice"
                      :disabled="customVoices.length >= 5"
                    >
                      <i class="fa-solid fa-plus"></i>
                      <span>Add Voice</span>
                    </button>
                  </div>

                  <div v-if="isLoadingCustomVoices" class="custom-voices-loading">
                    <i class="fa-solid fa-spinner fa-spin"></i>
                    <span>Loading custom voices...</span>
                  </div>

                  <div v-else-if="customVoices.length > 0" class="custom-voices-list">
                    <div
                      v-for="voice in customVoices"
                      :key="voice.id"
                      class="custom-voice-item"
                      :class="{ 'custom-voice-selected': selectedVoice === getCustomVoiceId(voice) }"
                    >
                      <div class="voice-info" @click="handleVoiceSelection({ id: getCustomVoiceId(voice), provider: getCustomVoiceProvider(voice) })">
                        <span class="voice-name">{{ voice.voice_name }} ⭐</span>
                        <span v-if="voice.description" class="voice-description">{{ voice.description }}</span>
                      </div>
                      <div class="voice-actions">
                        <button
                          v-if="voice.preview_url"
                          @click.stop="toggleAudioPlayback({ id: getCustomVoiceId(voice), sampleUrl: voice.preview_url })"
                          :class="[
                            'play-button',
                            isAudioPlaying(getCustomVoiceId(voice)) ? 'play-button-stop' : 'play-button-play'
                          ]"
                          :title="isAudioPlaying(getCustomVoiceId(voice)) ? 'Stop preview' : 'Play preview'"
                        >
                          <i v-if="!isAudioPlaying(getCustomVoiceId(voice))" class="fa-solid fa-play"></i>
                          <i v-else class="fa-solid fa-stop"></i>
                        </button>
                        <button
                          @click.stop="deleteCustomVoice(voice.id, voice.voice_name)"
                          class="btn-delete"
                          title="Delete voice"
                        >
                          <i class="fa-solid fa-trash"></i>
                        </button>
                      </div>
                    </div>
                  </div>

                  <p v-else class="no-voices">No custom voices yet. Upload your first voice!</p>
                </div>

                <!-- Voice Selection -->
                <div class="voice-section">
                  <label class="voice-section-label">Select Narrator Voice</label>
                  <div class="relative" ref="voiceDropdownRef">
                    <!-- Dropdown Button -->
                    <button
                      @click="isVoiceDropdownOpen = !isVoiceDropdownOpen"
                      class="voice-dropdown-button"
                    >
                      <div class="flex items-center gap-2">
                        <span v-if="selectedVoiceObject" class="voice-display">
                          <span :class="[
                            'provider-badge',
                            selectedVoiceObject?.provider === 'minimax' ? 'provider-minimax' :
                            selectedVoiceObject?.provider === 'deepgram' ? 'provider-deepgram' :
                            selectedVoiceObject?.provider === 'google' ? 'provider-google' :
                            selectedVoiceObject?.provider === 'elevenlabs' ? 'provider-elevenlabs' :
                            'provider-default'
                          ]">
                            {{ getProviderLabel(selectedVoiceObject?.provider || '').replace('[', '').replace(']', '') }}
                          </span>
                          {{ selectedVoiceObject?.name }} - {{ selectedVoiceObject?.description }}
                        </span>
                        <span v-else class="text-gray-500">Select a voice...</span>
                      </div>
                      <i class="fa-solid fa-chevron-down dropdown-icon" :class="{ 'rotate-180': isVoiceDropdownOpen }"></i>
                    </button>

                    <!-- Dropdown Menu -->
                    <div
                      v-if="isVoiceDropdownOpen"
                      class="voice-dropdown-menu"
                    >
                      <div
                        v-for="voice in voiceOptions"
                        :key="voice.id"
                        class="voice-dropdown-item"
                        :class="{ 'voice-selected': selectedVoice === voice.id }"
                      >
                        <!-- Voice Info (clickable to select) -->
                        <div
                          @click="handleVoiceSelection(voice)"
                          class="voice-info"
                        >
                          <div class="voice-header">
                            <span :class="[
                              'provider-badge',
                              voice.provider === 'minimax' ? 'provider-minimax' :
                              voice.provider === 'deepgram' ? 'provider-deepgram' :
                              voice.provider === 'google' ? 'provider-google' :
                              voice.provider === 'elevenlabs' ? 'provider-elevenlabs' :
                              'provider-default'
                            ]">
                              {{ getProviderLabel(voice.provider).replace('[', '').replace(']', '') }}
                            </span>
                            <h5 class="voice-name">{{ voice.name }}</h5>
                          </div>
                          <p class="voice-description">{{ voice.description }}</p>
                          <div class="voice-tags">
                            <span v-for="tag in voice.tags.slice(0, 3)" :key="tag" class="voice-tag">
                              {{ tag }}
                            </span>
                          </div>
                        </div>

                        <!-- Play Button (show for voices with sampleUrl OR ElevenLabs voices) -->
                        <button
                          v-if="voice.sampleUrl || voice.provider === 'elevenlabs'"
                          @click.stop="toggleAudioPlayback(voice)"
                          :class="[
                            'play-button',
                            isAudioPlaying(voice.id) ? 'play-button-stop' : 'play-button-play',
                            isLoadingVoicePreview(voice.id) ? 'play-button-loading' : ''
                          ]"
                          :title="isAudioPlaying(voice.id) ? 'Stop preview' : 'Play preview'"
                          :disabled="isLoadingVoicePreview(voice.id)"
                        >
                          <i v-if="isLoadingVoicePreview(voice.id)" class="fa-solid fa-spinner fa-spin"></i>
                          <i v-else-if="!isAudioPlaying(voice.id)" class="fa-solid fa-play"></i>
                          <i v-else class="fa-solid fa-stop"></i>
                        </button>
                        <div v-else class="no-sample">No sample</div>
                      </div>
                    </div>

                    <!-- Hidden Audio Elements -->
                    <audio
                      v-for="voice in voiceOptions.filter(v => v.sampleUrl)"
                      :key="voice.id"
                      :src="voice.sampleUrl"
                      preload="metadata"
                      @ended="onAudioEnded(voice.id)"
                      @error="onAudioError(voice)"
                      class="hidden"
                    ></audio>
                  </div>
                </div>

                <!-- Audio Speed Control -->
                <div class="voice-section">
                  <label class="voice-section-label">Audio Speed</label>
                  <div class="speed-slider-container">
                    <span class="speed-marker">0.5x</span>
                    <input
                      type="range"
                      v-model.number="audioSpeed"
                      min="0.5"
                      max="2"
                      step="0.01"
                      class="speed-slider"
                    >
                    <span class="speed-marker">2.0x</span>
                    <span class="speed-value">{{ audioSpeed.toFixed(2) }}x</span>
                  </div>
                  <div
                    v-if="hasPendingGeneratedAudioSpeedChange"
                    class="mt-3 flex items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800"
                  >
                    <span>
                      Generated audio is {{ appliedAudioSpeed.toFixed(2) }}x. Apply {{ audioSpeed.toFixed(2) }}x and rescale scene timestamps.
                    </span>
                    <button
                      type="button"
                      class="shrink-0 rounded-md bg-blue-600 px-3 py-1.5 font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                      :disabled="isAdjustingAudioSpeed"
                      @click="applyAudioSpeedToGeneratedAudio"
                    >
                      <i v-if="isAdjustingAudioSpeed" class="fa-solid fa-spinner fa-spin mr-1"></i>
                      {{ isAdjustingAudioSpeed ? 'Applying...' : 'Apply' }}
                    </button>
                  </div>
                </div>
              </div>

              <!-- Confirm Button -->
              <div class="voice-modal-footer">
                <button @click="isVoiceModalOpen = false" class="voice-confirm-btn">
                  <i class="fa-solid fa-check"></i>
                  Confirm
                </button>
              </div>
            </div>
          </div>

          <!-- Style Settings Modal -->
          <div v-if="isStyleModalOpen" class="voice-modal-overlay" @click="isStyleModalOpen = false">
            <div class="style-modal" @click.stop>
              <div class="voice-modal-header">
                <h3>Visual Style Templates</h3>
                <button @click="isStyleModalOpen = false" class="modal-close-btn">
                  <i class="fa-solid fa-times"></i>
                </button>
              </div>

              <div class="style-modal-content">
                <div class="style-templates-grid">
                  <button
                    v-for="template in styleTemplates"
                    :key="template.id"
                    @click="selectStyleTemplate(template.id)"
                    :class="[
                      'style-template-card-modal',
                      selectedStyleTemplate === template.id ? 'style-template-selected' : ''
                    ]"
                  >
                    <div class="template-icon">
                      <div class="template-initials">
                        {{ template.name.slice(0, 2).toUpperCase() }}
                      </div>
                    </div>
                    <div class="template-name">{{ template.name }}</div>
                    <div class="template-description">{{ template.description }}</div>
                  </button>
                </div>
              </div>

              <!-- Confirm Button -->
              <div class="voice-modal-footer">
                <button @click="isStyleModalOpen = false" class="voice-confirm-btn">
                  <i class="fa-solid fa-check"></i>
                  Confirm
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Audio to Video Mode - HIDDEN (moved to preview area) -->
        <div v-if="false && creationMode === 'audioToVideo'">
          <div class="section-label">1. Upload Audio</div>
          <div class="audio-upload-box">
            <input
              type="file"
              ref="audioFileInput"
              accept="audio/*"
              @change="handleAudioFileSelect"
              class="hidden"
            />

            <div
              v-if="!generatedAudio"
              class="audio-upload-dropzone"
              :class="{
                'audio-upload-zone-dragging': isDraggingAudio,
                'audio-upload-zone-disabled': isUploadingAudio
              }"
              @dragover.prevent="isDraggingAudio = true"
              @dragleave.prevent="isDraggingAudio = false"
              @drop.prevent="handleAudioFileDrop"
              @click="audioFileInput?.click()"
            >
              <svg class="upload-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <p class="upload-text">
                {{ isUploadingAudio ? 'Uploading...' : 'Drop your audio file here or click to browse' }}
              </p>
              <p class="upload-hint">MP3, WAV, M4A, or OGG (max 50MB)</p>
            </div>

            <div v-else class="audio-preview">
              <audio
                :key="audioPlayerKey"
                :src="generatedAudio?.url"
                controls
                class="audio-player"
                @timeupdate="handleAudioTimeUpdate"
              ></audio>
              <div class="audio-info">
                <span class="text-xs text-gray-600">Duration: {{ formatDuration(generatedAudio?.duration || 0) }}</span>
              </div>
              <button @click="removeUploadedAudio" class="remove-audio-btn">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
                Remove
              </button>
            </div>

            <!-- Audio Upload Error -->
            <div v-if="audioUploadError" class="text-sm text-red-600 bg-red-50 p-2 rounded mt-2">
              {{ audioUploadError }}
            </div>

            <!-- Audio Upload Progress -->
            <div v-if="isUploadingAudio" class="mt-4">
              <div class="flex items-center gap-3 mb-2">
                <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-orange-500"></div>
                <span class="text-orange-700 text-sm font-medium">Uploading audio file...</span>
              </div>
              <div class="w-full bg-orange-200 rounded-full h-2">
                <div class="bg-orange-500 h-2 rounded-full transition-all duration-500" :style="{ width: `${audioUploadProgress}%` }"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- Idea to Video Mode - HIDDEN (moved to preview area) -->
        <div v-if="false && creationMode === 'ideaToVideo'">
          <div class="section-label">{{ ideaSubMode === 'ideas' ? 'YOUR IDEA' : 'CONTENT TO REPURPOSE' }}</div>

          <!-- Trend Analysis Section -->
          <div v-if="ideaSubMode === 'ideas'" class="mb-4">
            <div class="flex gap-2">
              <input
                v-model="trendKeyword"
                @keydown.enter="fetchTrendingTopics"
                type="text"
                placeholder="Enter a topic to find trending videos (e.g., 'finance tips', 'fitness')"
                class="flex-1 px-4 py-2 border-2 border-gray-300 rounded-lg outline-none focus:border-orange-500 transition-colors text-sm"
              />
              <button
                @click="fetchTrendingTopics"
                :disabled="isFetchingTrends || !trendKeyword.trim()"
                class="px-6 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 text-sm font-medium whitespace-nowrap"
              >
                <i v-if="!isFetchingTrends" class="fa-solid fa-fire"></i>
                <i v-else class="fa-solid fa-spinner fa-spin"></i>
                {{ isFetchingTrends ? 'Searching...' : 'Find Trending Topics' }}
              </button>
            </div>
          </div>

          <div class="script-box relative">
            <textarea
              v-model="ideaText"
              :placeholder="ideaSubMode === 'ideas'
                ? 'Describe your video idea... (e.g., \'I want to make a video about the benefits of morning routines\')'
                : 'Paste the content you want to repurpose into a video... (e.g., blog post, article, script from another video)'"
              class="w-full h-[250px] border-2 rounded-lg p-4 text-base resize-none outline-none transition-colors duration-200 focus:border-purple-500"
            ></textarea>

            <!-- Video Length Slider (only for 'ideas' mode) -->
            <div v-if="ideaSubMode === 'ideas'" class="absolute bottom-3 left-3 right-20">
              <div class="flex items-center justify-between gap-2 mb-2">
                <div class="flex items-center gap-2">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="flex-shrink-0 text-gray-600">
                    <circle cx="12" cy="12" r="10"></circle>
                    <polyline points="12 6 12 12 16 14"></polyline>
                  </svg>
                  <span class="text-xs font-medium text-gray-600">Video Length: <span class="text-xs font-semibold text-orange-500">{{ videoLength[0] }} min</span></span>
                </div>

              </div>
              <Slider
                v-model="videoLength"
                :min="1"
                :max="10"
                :step="1"
                class="w-[33%]"
              />
            </div>

            <button
              class="ai-assist-btn"
              @click="ideaSubMode === 'ideas' ? generateScriptFromIdea() : improveIdea()"
              :disabled="(ideaSubMode === 'ideas' ? isGeneratingScript : isImprovingIdea) || ideaText.trim().length < 50"
            >
              <i v-if="!(ideaSubMode === 'ideas' ? isGeneratingScript : isImprovingIdea)" class="fa-solid fa-wand-magic-sparkles"></i>
              <i v-else class="fa-solid fa-spinner fa-spin"></i>
              {{ (ideaSubMode === 'ideas' ? isGeneratingScript : isImprovingIdea)
                 ? 'Processing...'
                 : (ideaSubMode === 'ideas' ? 'Generate Script' : 'Repurpose Content') }}
            </button>
          </div>

          <!-- Character count validation -->
          <div v-if="ideaText.length > 0" class="mt-2 text-xs text-gray-600">
            <div class="flex justify-between">
              <span>{{ ideaText.length }} characters</span>
              <span v-if="ideaText.trim().length < 50" class="text-orange-600">
                (minimum 50 characters required)
              </span>
            </div>
          </div>
        </div>

        <div class="flex flex-col flex-1 min-h-0">
          <div class="section-label">Select A Style</div>

          <!-- Custom Keywords Input Section -->
          <div class="mt-3 mb-4 flex-shrink-0">

            <div class="">
              <!-- Tags Display -->
              <div class="flex flex-wrap gap-1.5 mb-2" v-if="selectedImageStyles.length > 0">
                <span
                  v-for="style in selectedImageStyles"
                  :key="style"
                  class="inline-flex items-center gap-1.5 px-2.5 py-1 bg-orange-500 text-white text-xs rounded-md"
                >
                  {{ style }}
                  <button @click="selectedImageStyles = selectedImageStyles.filter(s => s !== style)" class="hover:bg-orange-600 rounded">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                      <line x1="18" y1="6" x2="6" y2="18"></line>
                      <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                  </button>
                </span>
              </div>
              <!-- Input Field -->
              <input
                v-model="newStyleKeyword"
                @keydown.enter="addCustomKeyword"
                type="text"
                placeholder="Type a modifier keyword and press Enter (e.g., cinematic, anime, vintage)..."
                class="w-full text-sm px-3 py-2 border border-gray-300 rounded-md outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
              />
              <!-- Quick Suggestions -->
              <!-- <div class="flex flex-wrap gap-1.5 mt-2">
                <span class="text-xs text-gray-500">Quick add:</span>
                <button
                  v-for="suggestion in imageStyleSuggestions.slice(0, 8)"
                  :key="suggestion"
                  @click="addStyleSuggestion(suggestion)"
                  :disabled="selectedImageStyles.includes(suggestion)"
                  class="px-2 py-0.5 text-xs bg-gray-100 text-gray-700 rounded hover:bg-orange-100 hover:text-orange-600 border border-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {{ suggestion }}
                </button>
              </div> -->
            </div>
          </div>

          <!-- Style Cards Grid -->
          <div class="grid grid-cols-3 gap-3 mt-3 flex-1 overflow-y-auto pr-2 min-h-0">
            <!-- No Style Card -->
            <button
              @click="selectedStyleTemplate = null"
              :class="[
                'relative rounded-xl overflow-hidden cursor-pointer transition-all duration-200 text-left p-0 w-full flex flex-col',
                selectedStyleTemplate === null ? 'border-[#FB3333] border-2 shadow-lg shadow-[#FB3333]/20' : 'border-gray-200'
              ]"
            >
              <div class="w-full h-24 sm:h-32 md:h-[140px] bg-gradient-to-br from-gray-800 to-gray-700 flex items-center justify-center">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="text-gray-500">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </div>
              <div class=" flex-1">
                <div class="text-sm text-gray-800">No Style</div>

              </div>
              <!-- <div v-if="selectedStyleTemplate === null" class="absolute top-2 right-2 w-8 h-8 bg-green-500 rounded-full flex items-center justify-center text-white shadow-lg shadow-green-500/40">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </div> -->
            </button>

            <!-- Style Template Cards -->
            <button
              v-for="template in styleTemplates"
              :key="template.id"
              @click="selectStyleTemplate(template.id)"
              :class="[
                'relative  rounded-xl overflow-hidden cursor-pointer transition-all duration-200 text-left p-0 w-full flex flex-col hover:border-[#FB3333]',
                selectedStyleTemplate === template.id ? 'border-[#FB3333] border-2 shadow-lg shadow-[#FB3333]/20' : 'border-gray-200'
              ]"
            >
              <div class="w-full h-24 sm:h-32 md:h-[140px] bg-gradient-to-br from-gray-800 to-gray-700 flex items-center justify-center overflow-hidden">
                <div class="text-white text-xl font-semibold tracking-normal">
                  {{ template.name.slice(0, 2).toUpperCase() }}
                </div>
              </div>
              <div class="pb-1 pl-1 flex-1">

                <div class="text-xs text-gray-800">{{ template.name }}</div>

              </div>
              <!-- <div v-if="selectedStyleTemplate === template.id" class="absolute top-2 right-2 w-8 h-8 bg-green-500 rounded-full flex items-center justify-center text-white shadow-lg shadow-green-500/40">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </div> -->
            </button>
          </div>

          <!-- Next Button with Scene Count Selection - HIDDEN (moved to preview area) -->
          <div class="flex justify-end items-center gap-2 mt-4 flex-shrink-0" style="display: none;">
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button class="h-9 px-3 text-sm shadow-sm cursor-pointer">
                  <span style="display: flex; align-items: center; gap: 4px;">
                    {{ sceneAggregationMode === 'much less' ? 'Much Less Scenes' :
                       sceneAggregationMode === 'less' ? 'Less Scenes' :
                       sceneAggregationMode === 'more' ? 'More Scenes' :
                       sceneAggregationMode === 'most' ? 'Most Scenes' : 'Regular Scenes' }}
                  </span>
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="6 9 12 15 18 9"></polyline>
                  </svg>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent class="bg-black" align="start">
                <DropdownMenuItem
                  @click="sceneAggregationMode = 'much less'"
                  class="text-white"
                >
                  <span style="display: flex; align-items: center; gap: 6px;">
                    Much Less Scenes
                  </span>
                  <svg v-if="sceneAggregationMode === 'much less'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
                <DropdownMenuItem
                  @click="sceneAggregationMode = 'less'"
                  class="text-white"
                >
                  <span style="display: flex; align-items: center; gap: 6px;">
                    Less Scenes
                  </span>
                  <svg v-if="sceneAggregationMode === 'less'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
                <DropdownMenuItem
                  @click="sceneAggregationMode = 'regular'"
                  class="text-white"
                >
                  <span style="display: flex; align-items: center; gap: 6px;">
                    Regular Scenes
                  </span>
                  <svg v-if="sceneAggregationMode === 'regular'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
                <DropdownMenuItem
                  @click="sceneAggregationMode = 'more'"
                  class="text-white"
                >
                  <span style="display: flex; align-items: center; gap: 6px;">
                    More Scenes
                  </span>
                  <svg v-if="sceneAggregationMode === 'more'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
                <DropdownMenuItem
                  @click="sceneAggregationMode = 'most'"
                  class="text-white"
                >
                  <span style="display: flex; align-items: center; gap: 6px;">
                    Most Scenes
                  </span>
                  <svg v-if="sceneAggregationMode === 'most'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <Button
              class="bg-linear-to-r from-yellow-400 to-red-500 cursor-pointer"
              @click="handleGenerateScenes"
              :disabled="!script || isGeneratingAudio || isGeneratingScenes || creationMode === 'ideaToVideo'"
              :title="scenes.length > 0 ? 're-generate audio and scenes' : 'Generate audio and scenes'"
            >
              <i v-if="!isGeneratingAudio && !isGeneratingScenes" class="fa-solid fa-wand-magic-sparkles"></i>
              <i v-else class="fa-solid fa-spinner fa-spin"></i>
              {{ isGeneratingAudio || isGeneratingScenes ? 'Generating...' : (scenes.length > 0 ? 'Re-generate All' : 'Next') }}
            </Button>

            <!-- Regenerate Scenes Only Button (without regenerating audio) -->
            <Button
              v-if="generatedAudio || scenes.length > 0"
              class="bg-blue-500 hover:bg-blue-600 cursor-pointer ml-2"
              @click="generateScenes"
              :disabled="!script || isGeneratingAudio || isGeneratingScenes || creationMode === 'ideaToVideo'"
              title="regenerate scenes only"
            >
              <i v-if="!isGeneratingScenes" class="fa-solid fa-film"></i>
              <i v-else class="fa-solid fa-spinner fa-spin"></i>
              {{ isGeneratingScenes ? 'Generating...' : 'Regenerate Scenes' }}
            </Button>
          </div>
        </div>

        <div class="mt-2">
          <!-- <div class="section-label">3. Generate Storyboard</div> -->

          <!-- Generate Buttons Row -->
          <div class="generate-buttons-row" style="display: none;">
            <!-- <Button
              class=""
              @click="generateAudio"
              :disabled="!script || isGeneratingAudio || isGeneratingScenes"
            >
              <i v-if="!isGeneratingAudio" class="fa-solid fa-volume-up"></i>
              <i v-else class="fa-solid fa-spinner fa-spin"></i>
              {{ isGeneratingAudio ? 'Generating...' : 'Audio Only' }}
            </Button> -->

            <!-- Moved to bottom right of styles panel -->
          </div>

          <!-- Audio Player (shown when audio is generated) -->
          <!-- <div v-if="generatedAudio" class="audio-player-container">
            <audio
              :key="audioPlayerKey"
              :src="generatedAudio.url"
              controls
              class="audio-player"
              @timeupdate="handleAudioTimeUpdate"
            ></audio>
            <div class="audio-info">
              <span class="text-xs text-gray-600">Duration: {{ formatDuration(generatedAudio.duration) }}</span>
            </div>
          </div> -->
        </div>

        <!-- <div>
          <div class="section-label">4. Background Music (coming soon)</div>

        </div> -->
        </div>
        <!-- End INITIAL MODE -->

        <!-- STORYBOARD MODE: Scene Cards -->
        <div v-if="showStoryboardLayout && !editingScene && !showingPreview" class="flex flex-col h-18/19">
          <!-- Back Button -->
          <!-- <Button
            @click="showStoryboardLayout = false"
            variant="ghost"
            class="w-fit px-3 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100"
            title="Back to script editor"
          >
            <i class="fa-solid fa-arrow-left"></i>
            <span>Back to Scripts</span>
          </Button> -->

          <div class="mb-2 lg:mb-4 flex flex-row items-center justify-between gap-1 lg:gap-2">
            <div>
              <h2 class="text-sm sm:text-base lg:text-xl font-bold text-gray-900">Storyboard</h2>
            </div>

            <div class="flex flex-wrap gap-1 lg:gap-2 storyboard-actions">
            <!-- Add Scene Button (when not editing) -->
            <Button
              v-if="!editingScene"
              @click="addNewScene"
              title="Add a new scene"
              class="px-0.5 md:px-1 lg:px-2 py-0 md:py-0.5 lg:py-1 text-[10px] lg:text-xs cursor-pointer"
            >
              <i class="fa-solid fa-plus text-[10px] lg:text-xs"></i>
              <span class="!hidden md:!inline">Add Scene</span>
              <span class="md:!hidden">Add</span>
            </Button>

            <!-- Upload Files Button -->
            <Button
              v-if="!editingScene"
              @click="mediaFileInput?.click()"
              title="Upload images or videos"
              class="px-0.5 md:px-1 lg:px-2 py-0 md:py-0.5 lg:py-1 text-[10px] lg:text-xs cursor-pointer"
            >
              <i class="fa-solid fa-upload text-[10px] lg:text-xs"></i>
              <span class="!hidden md:!inline">Upload</span>
              <span class="md:!hidden">Up</span>
            </Button>

            <!-- Hidden file input for media upload -->
            <input
              ref="mediaFileInput"
              type="file"
              accept="image/jpeg,image/png,image/webp,video/mp4"
              multiple
              style="display: none"
              @change="handleMediaFileSelect"
            />

            <!-- Add Scene from Gallery Button -->
            <!-- <Button
              v-if="!editingScene"
              @click="openGalleryForNewScene"
              title="Add scene from gallery"
              class="px-2 text-xs cursor-pointer"
            >
              <i class="fa-regular fa-images"></i>
              <span>Add from Gallery</span>
            </Button> -->

            <!-- Generate Scenes Button -->
            <Button
              v-if="!editingScene && generatedAudio && scenes.length === 0 && projectMode === 'narrated_broll'"
              @click="generateScenes"
              :disabled="isGeneratingScenes"
              class="px-1 lg:px-2 py-0.5 lg:py-1 text-[10px] lg:text-xs cursor-pointer"
            >
              <i v-if="!isGeneratingScenes" class="fa-solid fa-wand-magic-sparkles text-[10px] lg:text-xs"></i>
              <i v-else class="fa-solid fa-spinner fa-spin text-[10px] lg:text-xs"></i>
              <span class="!hidden md:!inline">{{ isGeneratingScenes ? 'Generating...' : 'Generate Scenes' }}</span>
              <span class="md:!hidden">{{ isGeneratingScenes ? 'Gen...' : 'Gen' }}</span>
            </Button>

            <Button
              v-if="!editingScene && projectMode === 'talking_scenes' && scenes.length > 0"
              @click="generateTalkingSceneAudio"
              :disabled="isGeneratingSceneAudio || !canGenerateTalkingSceneAudio"
              class="px-1 lg:px-2 py-0.5 lg:py-1 text-[10px] lg:text-xs cursor-pointer"
            >
              <i v-if="!isGeneratingSceneAudio" class="fa-solid fa-volume-high text-[10px] lg:text-xs"></i>
              <i v-else class="fa-solid fa-spinner fa-spin text-[10px] lg:text-xs"></i>
              <span class="!hidden md:!inline">{{ isGeneratingSceneAudio ? 'Generating audio...' : 'Generate Scene Audio' }}</span>
              <span class="md:!hidden">{{ isGeneratingSceneAudio ? 'Audio...' : 'Audio' }}</span>
            </Button>

            <!-- Generate Images with Settings Dropdown -->
            <DropdownMenu v-if="!editingScene && scenes.length > 0 && !hasAllImages">
              <DropdownMenuTrigger as-child>
                <Button
                  :disabled="isGeneratingImages"
                  class="px-1 lg:px-2 py-0.5 lg:py-1 text-[10px] lg:text-xs cursor-pointer"
                  :title="isGeneratingImages ? 'Generating images...' : 'Configure and generate images'"
                >
                  <span style="display: flex; align-items: center; gap: 2px;">
                    <i v-if="!isGeneratingImages" class="fa-solid fa-images text-[10px] lg:text-base"></i>
                    <i v-else class="fa-solid fa-spinner fa-spin text-[10px] lg:text-base"></i>
                    <span class="!hidden md:!inline">{{ isGeneratingImages ? `Generating ${currentImageIndex}/${scenes.length}...` : 'Generate Images' }}</span>
                    <span class="md:!hidden">{{ isGeneratingImages ? `${currentImageIndex}/${scenes.length}` : 'Gen' }}</span>
                  </span>
                  <svg width="10" height="10" class="lg:w-3 lg:h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="6 9 12 15 18 9"></polyline>
                  </svg>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent class="w-64 bg-black" align="start">
                <!-- Image Generation Model -->
                <div class="px-3 py-2 border-b border-gray-700">
                  <label class="text-xs font-semibold text-gray-300 mb-2 block">Image Model</label>
                  <div class="space-y-1">
                    <button
                      v-for="model in imageGenerationModels"
                      :key="model.value"
                      @click="imageGenerationModel = model.value"
                      class="w-full text-left px-2 py-1.5 text-xs rounded flex items-center justify-between transition-colors"
                      :class="{
                        'bg-orange-900/50 text-orange-300': imageGenerationModel === model.value,
                        'hover:bg-gray-800 text-white cursor-pointer': true
                      }"
                    >
                      <span class="flex items-center gap-2">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                        </svg>
                        {{ model.label }}
                      </span>
                      <svg v-if="imageGenerationModel === model.value" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" class="text-orange-400">
                        <polyline points="20 6 9 17 4 12"></polyline>
                      </svg>
                    </button>
                  </div>
                </div>

                <!-- Image Aspect Ratio -->
                <div class="px-3 py-2 border-b border-gray-700">
                  <label class="text-xs font-semibold text-gray-300 mb-2 block">Aspect Ratio</label>
                  <div class="grid grid-cols-3 gap-1">
                    <button
                      v-for="ratio in imageAspectRatios"
                      :key="ratio.value"
                      @click="imageAspectRatio = ratio.value"
                      class="px-2 py-1.5 text-xs rounded hover:bg-gray-800 flex items-center justify-center transition-colors text-white"
                      :class="{ 'bg-orange-900/50 text-orange-300 font-medium': imageAspectRatio === ratio.value }"
                    >
                      {{ ratio.value }}
                    </button>
                  </div>
                </div>

                <!-- Generate Action -->
                <div class="px-3 py-2">
                  <button
                    @click="generateAllImages"
                    :disabled="!imageGenerationModel || !imageAspectRatio || isGeneratingImages"
                    class="w-full px-3 py-2 text-sm rounded transition-colors flex items-center justify-center gap-2"
                    :class="imageGenerationModel && imageAspectRatio && !isGeneratingImages
                      ? 'bg-gradient-to-r from-yellow-500 to-red-500 hover:from-yellow-600 hover:to-red-600 text-white cursor-pointer'
                      : 'bg-gray-700 text-gray-400 cursor-not-allowed'"
                  >
                    <i v-if="!isGeneratingImages" class="fa-solid fa-wand-magic-sparkles"></i>
                    <i v-else class="fa-solid fa-spinner fa-spin"></i>
                    <span v-if="isGeneratingImages">Generating...</span>
                    <span v-else class="flex items-center gap-1">
                      Generate All Images
                    </span>
                  </button>
                  <p v-if="!imageGenerationModel || !imageAspectRatio" class="text-xs text-yellow-400 mt-2 text-center">
                    ⚠️ Select model & ratio first
                  </p>
                </div>
              </DropdownMenuContent>
            </DropdownMenu>

            <!-- Effects Presets Dropdown (shown when there are scenes) -->
            <DropdownMenu v-if="!editingScene && scenes.length > 0">
              <DropdownMenuTrigger as-child>
                <Button title="Apply effects presets to all scenes" class='!px-0.5 md:!px-1 lg:!px-2 !py-0 md:!py-0.5 lg:!py-1 text-[10px] lg:text-xs bg-linear-to-r from-yellow-400 to-red-500 cursor-pointer'>
                  <span class="flex items-center gap-0.5 md:gap-1">
                    <span class="text-[10px] lg:text-base">✨</span>
                    <span class="!hidden md:!inline">Effects Presets</span>
                    <span class="md:!hidden">Effects</span>
                  </span>
                  <svg width="10" height="10" class="lg:w-3 lg:h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="6 9 12 15 18 9"></polyline>
                  </svg>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                class="bg-black"
                align="end"

              >
                <DropdownMenuItem
                  @click="randomizeAllEffects"
                class="text-white text-xs"              >
                  <span class="text-purple-400 text-base">🎲</span>
                  <span>Randomize All Effects</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  @click="applyWhiteboardDoodle"
                  class="text-white text-xs"
                >
                  <span class="text-blue-400 text-base">✏️</span>
                  <span>Whiteboard Doodle</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  @click="applyOldFilmBlack"
                  class="text-white text-xs"
                >
                  <span class="text-gray-400 text-base">🎞️</span>
                  <span>Old Film Black</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  @click="applyFireEffect"
                  class="text-white text-xs"
                >
                  <span class="text-orange-400 text-base">🔥</span>
                  <span>Fire Effect</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  @click="applyZoomInAll"
                  class="text-white text-xs"
                >
                  <span class="text-green-400 text-base">🔍</span>
                  <span>Zoom In All</span>
                </DropdownMenuItem>
                <DropdownMenuItem
                  @click="removeAllEffects"
                  class="text-white text-xs"
                >
                  <span class="text-red-400 text-base">🚫</span>
                  <span>Remove All Effects</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
	            </div>
	            <!-- End storyboard-actions -->
	          </div>
	          <!-- End header with title and actions -->

            <div
              v-if="projectMode === 'talking_scenes' && scenes.length > 0"
              class="mb-3 rounded-lg border border-orange-200 bg-orange-50/70 p-3"
            >
              <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div class="text-[11px] font-semibold uppercase tracking-wide text-orange-700">Cast Voices</div>
                  <p class="mt-1 text-xs text-gray-600">
                    <span v-if="hasSpeakingCharacters">
                      {{ speakingCharacters.length }} speaking character{{ speakingCharacters.length !== 1 ? 's' : '' }} detected.
                    </span>
                    <span v-else>
                      No dialogue speakers detected yet. Scene audio will use the project default voice if needed.
                    </span>
                    <span v-if="missingCharacterVoiceAssignments > 0" class="text-red-600">
                      {{ missingCharacterVoiceAssignments }} assignment{{ missingCharacterVoiceAssignments !== 1 ? 's' : '' }} need a valid voice.
                    </span>
                  </p>
                </div>
                <button
                  type="button"
                  @click="autoAssignCharacterVoices({ preserveExisting: false })"
                  class="inline-flex items-center justify-center rounded-md border border-orange-300 bg-white px-3 py-1.5 text-xs font-semibold text-orange-700 transition-colors hover:bg-orange-100"
                >
                  Auto Assign Voices
                </button>
              </div>

              <div v-if="hasSpeakingCharacters" class="mt-3 space-y-2">
                <div
                  v-for="character in speakingCharacters"
                  :key="character.character_id"
                  class="rounded-md border border-orange-100 bg-white px-3 py-2"
                >
                  <div class="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                    <div class="min-w-0">
                      <div class="text-sm font-semibold text-gray-900">{{ character.character_name }}</div>
                      <div class="text-xs text-gray-500">
                        {{ character.scene_count }} scene{{ character.scene_count !== 1 ? 's' : '' }} • {{ character.line_count }} line{{ character.line_count !== 1 ? 's' : '' }}
                      </div>
                    </div>

	                    <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
	                      <select
	                        :value="characterVoiceMap[character.character_id]?.voice_id || ''"
	                        @change="handleCharacterVoiceSelection(character.character_id, $event)"
	                        class="min-w-[220px] rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700"
                      >
                        <option value="">
                          Use Project Default{{ selectedVoiceObject ? ` (${selectedVoiceObject.name})` : '' }}
                        </option>
                        <option v-for="voice in voiceOptions" :key="voice.id" :value="voice.id">
                          {{ voice.name }}
                        </option>
                      </select>

                      <button
                        type="button"
                        @click="previewCharacterVoice(character.character_id)"
                        class="inline-flex items-center justify-center rounded-md border border-gray-300 bg-white px-3 py-2 text-xs font-semibold text-gray-700 transition-colors hover:bg-gray-50"
	                      >
	                        Preview
	                      </button>
	                    </div>
	                  </div>

                    <div class="mt-3">
                      <div class="mb-1 flex items-center justify-between text-[11px] font-medium text-gray-600">
                        <span>Voice Speed</span>
                        <span>{{ (characterVoiceMap[character.character_id]?.audio_speed ?? audioSpeed).toFixed(2) }}x</span>
                      </div>
                      <div class="flex items-center gap-2">
                        <span class="text-[10px] text-gray-400">0.50x</span>
                        <input
                          type="range"
                          min="0.5"
                          max="2"
                          step="0.01"
                          :value="characterVoiceMap[character.character_id]?.audio_speed ?? audioSpeed"
                          @input="handleCharacterVoiceSpeedChange(character.character_id, $event)"
                          class="flex-1 accent-orange-500"
                        >
                        <span class="text-[10px] text-gray-400">2.00x</span>
                      </div>
                    </div>
	                </div>
	              </div>
	            </div>

	          <!-- Scene Cards Grid (Scrollable) -->
	          <div class="overflow-auto lg:overflow-y-auto scene-cards-container" style="max-height: 95vh;">
            <!-- Loading Skeletons (when generating audio or scenes) -->
            <div v-if="scenes.length === 0 && (isGeneratingAudio || isGeneratingScenes)" class="grid grid-cols-2 gap-4">
              <div
                v-for="i in 4"
                :key="`skeleton-${i}`"
                class="relative rounded-lg overflow-hidden shadow-md bg-gray-100 animate-pulse"
              >
                <div class="aspect-video bg-gray-200"></div>
                <div class="p-3 space-y-2">
                  <div class="h-4 bg-gray-200 rounded w-3/4"></div>
                  <div class="h-3 bg-gray-200 rounded w-full"></div>
                  <div class="h-3 bg-gray-200 rounded w-5/6"></div>
                </div>
              </div>
            </div>

            <!-- Scene Cards (when scenes exist) -->
            <draggable
              v-else
              v-model="scenes"
              item-key="id"
              tag="div"
              class="flex lg:grid overflow-x-auto lg:overflow-x-visible lg:grid-cols-2 gap-4 pb-2 lg:pb-0 storyboard-grid"
              handle=".scene-drag-handle"
              ghost-class="scene-drag-ghost"
              chosen-class="scene-drag-chosen"
              drag-class="scene-drag-active"
              :animation="180"
              :disabled="isSceneReorderDisabled"
              @start="isReorderingScenes = true"
              @end="handleSceneDragEnd"
            >
              <template #item="{ element: scene, index }">
              <div
                :key="scene.id || index"
                @click="handleSceneClick(index)"
                :class="[
                  'relative rounded-lg overflow-hidden shadow-md transition-all duration-200 cursor-pointer flex-shrink-0 w-[33vw] sm:w-[23vw] lg:w-auto lg:h-fit lg:self-start',
                  selectedSceneForPreview === index ? 'ring-2 ring-orange-500' : 'hover:shadow-lg hover:-translate-y-1'
                ]"
              >
                <button
                  type="button"
                  class="scene-drag-handle"
                  title="Drag to reorder scene"
                  aria-label="Drag to reorder scene"
                  @click.stop
                >
                  <i class="fa-solid fa-grip-vertical"></i>
                </button>
                <SceneCard
                  :scene="scene"
                  :scene-number="index + 1"
                  :is-generating="scene.isGenerating || generatingSceneIndices.has(index)"
                  :generation-progress="scene.generationProgress"
                  :is-animating="isAnimatingImage[index]"
                  :animation-progress="animationProgress[index]"
                  :image-aspect-ratio="imageAspectRatio"
                  :show-animation="authStore.user?.type === 'admin' || authStore.user?.type === 'tester'"
                  :characters="charactersStore.characters"
                  :greenscreen-effects="greenscreenEffects"
                  @open-edit-modal="openSceneEditModal(index)"
                  @open-character-selector="openCharacterSelector(index)"
                  @generate-image="generateSceneImage(index, scene.prompt)"
                  @open-gallery-replacement="openGalleryReplacement(index)"
                  @update-media="openGalleryReplacement(index)"
                  @update:prompt="updateScenePrompt(index, $event)"
                  @update:animationPrompt="scene.animationPrompt = $event"
                  @update:animation-model="scene.animationModel = $event"
                  @update-characters="updateSceneCharacters(index)"
                  @animate-scene="animateSceneImage(index)"
                  @copy-video-url="copyImageUrl"
                  @add-video-to-timeline="addAnimatedVideoToTimeline(index)"
                  @delete-scene="deleteScene(index)"
                  @update:camera-movement="updateSceneCameraMovement(index, $event)"
                  @update:transition-type="updateSceneTransitionType(index, $event)"
                  @update:transition-duration="updateSceneTransitionDuration(index, $event)"
                  @update:greenscreen-effect="updateSceneGreenscreenEffect(index, $event)"
                  @update:time-range="(startTime, endTime) => updateSceneTimeRange(index, startTime, endTime)"
                />
              </div>
              </template>
            </draggable>
          </div>

          
        </div>
        <!-- End STORYBOARD MODE -->

        <!-- PREVIEW MODE: Scene list with transition + text layer controls -->
        <div v-else-if="showingPreview" class="flex flex-col h-18/19 overflow-y-auto gap-2 pr-1">
          <!-- Text Layer Settings (shown when a text layer is selected) -->
          <div v-if="selectedTextLayerId" class="flex-shrink-0 border border-orange-200 rounded-lg bg-orange-50 text-xs overflow-hidden flex flex-col max-h-[65vh]">
            <div class="flex items-center justify-between p-2 pb-1 flex-shrink-0">
              <span class="font-semibold text-orange-700 text-[11px]">Text Layer</span>
              <div class="flex items-center gap-1">
                <button @click="removeTextLayer(textLayers.find(l=>l.id===selectedTextLayerId)!.id); selectedTextLayerId = null" class="text-red-400 hover:text-red-600" title="Delete layer">
                  <i class="fa-solid fa-trash-can text-[10px]"></i>
                </button>
                <button @click="selectedTextLayerId = null" class="text-gray-400 hover:text-gray-600 text-[10px]">✕</button>
              </div>
            </div>
            <div class="overflow-y-auto flex-1 min-h-0 p-2 pt-0">
            <template v-for="tl in textLayers.filter(l => l.id === selectedTextLayerId)" :key="tl.id">

              <!-- Text content -->
              <textarea v-model="tl.text" rows="2" class="w-full text-[10px] border border-orange-200 rounded px-1 py-0.5 mb-2 bg-white resize-none" placeholder="Text content" />

              <!-- Font family -->
              <div class="mb-1.5">
                <label class="block text-[9px] text-gray-500 mb-0.5 uppercase tracking-wide">Font</label>
                <select v-model="tl.fontFamily" @change="loadGoogleFont(tl.fontFamily)" class="w-full text-[10px] border border-gray-200 rounded px-1 py-0.5 bg-white">
                  <optgroup label="System">
                    <option value="sans-serif">Sans-serif</option>
                    <option value="serif">Serif</option>
                    <option value="monospace">Monospace</option>
                  </optgroup>
                  <optgroup label="Web Safe">
                    <option value="Arial, sans-serif">Arial</option>
                    <option value="'Arial Black', sans-serif">Arial Black</option>
                    <option value="Verdana, sans-serif">Verdana</option>
                    <option value="Impact, sans-serif">Impact</option>
                    <option value="Georgia, serif">Georgia</option>
                    <option value="'Times New Roman', serif">Times New Roman</option>
                    <option value="'Courier New', monospace">Courier New</option>
                  </optgroup>
                  <optgroup label="Google — Sans Serif">
                    <option value="Inter, sans-serif">Inter</option>
                    <option value="Roboto, sans-serif">Roboto</option>
                    <option value="'Open Sans', sans-serif">Open Sans</option>
                    <option value="Lato, sans-serif">Lato</option>
                    <option value="Montserrat, sans-serif">Montserrat</option>
                    <option value="Oswald, sans-serif">Oswald</option>
                    <option value="Raleway, sans-serif">Raleway</option>
                    <option value="Poppins, sans-serif">Poppins</option>
                    <option value="Nunito, sans-serif">Nunito</option>
                    <option value="Outfit, sans-serif">Outfit</option>
                    <option value="Rubik, sans-serif">Rubik</option>
                    <option value="Manrope, sans-serif">Manrope</option>
                    <option value="'DM Sans', sans-serif">DM Sans</option>
                    <option value="Jost, sans-serif">Jost</option>
                    <option value="Barlow, sans-serif">Barlow</option>
                    <option value="Figtree, sans-serif">Figtree</option>
                    <option value="'Plus Jakarta Sans', sans-serif">Plus Jakarta Sans</option>
                    <option value="'Exo 2', sans-serif">Exo 2</option>
                    <option value="Ubuntu, sans-serif">Ubuntu</option>
                    <option value="'Source Sans 3', sans-serif">Source Sans 3</option>
                  </optgroup>
                  <optgroup label="Google — Serif">
                    <option value="'Playfair Display', serif">Playfair Display</option>
                    <option value="Merriweather, serif">Merriweather</option>
                    <option value="Lora, serif">Lora</option>
                    <option value="'Libre Baskerville', serif">Libre Baskerville</option>
                    <option value="'EB Garamond', serif">EB Garamond</option>
                    <option value="'Cormorant Garamond', serif">Cormorant Garamond</option>
                    <option value="'Crimson Text', serif">Crimson Text</option>
                  </optgroup>
                  <optgroup label="Google — Display">
                    <option value="'Bebas Neue', cursive">Bebas Neue</option>
                    <option value="Anton, sans-serif">Anton</option>
                    <option value="Bangers, cursive">Bangers</option>
                    <option value="Righteous, cursive">Righteous</option>
                    <option value="'Passion One', cursive">Passion One</option>
                    <option value="Staatliches, cursive">Staatliches</option>
                    <option value="'Fredoka One', cursive">Fredoka One</option>
                    <option value="'Luckiest Guy', cursive">Luckiest Guy</option>
                    <option value="Boogaloo, cursive">Boogaloo</option>
                    <option value="'Lilita One', cursive">Lilita One</option>
                    <option value="'Black Han Sans', sans-serif">Black Han Sans</option>
                  </optgroup>
                  <optgroup label="Google — Handwriting">
                    <option value="Pacifico, cursive">Pacifico</option>
                    <option value="'Dancing Script', cursive">Dancing Script</option>
                    <option value="Lobster, cursive">Lobster</option>
                    <option value="Caveat, cursive">Caveat</option>
                    <option value="Sacramento, cursive">Sacramento</option>
                    <option value="'Great Vibes', cursive">Great Vibes</option>
                    <option value="Satisfy, cursive">Satisfy</option>
                    <option value="'Architects Daughter', cursive">Architects Daughter</option>
                    <option value="Kalam, cursive">Kalam</option>
                  </optgroup>
                  <optgroup label="Google — Monospace">
                    <option value="'Source Code Pro', monospace">Source Code Pro</option>
                    <option value="'Space Mono', monospace">Space Mono</option>
                    <option value="'Fira Code', monospace">Fira Code</option>
                    <option value="'JetBrains Mono', monospace">JetBrains Mono</option>
                  </optgroup>
                </select>
              </div>

              <!-- Size + style -->
              <div class="flex items-center gap-1 mb-1.5">
                <div class="flex flex-col flex-1">
                  <label class="text-[9px] text-gray-500 mb-0.5 uppercase tracking-wide">Size</label>
                  <input v-model.number="tl.fontSize" type="number" min="8" max="400" class="w-full text-[10px] border border-gray-200 rounded px-1 py-0.5 bg-white" />
                </div>
                <div class="flex flex-col items-center">
                  <label class="text-[9px] text-gray-500 mb-0.5 uppercase tracking-wide">Bold</label>
                  <button
                    @click="tl.fontWeight = tl.fontWeight === 'bold' ? 'normal' : 'bold'"
                    class="w-6 h-6 rounded border text-[11px] font-bold"
                    :class="tl.fontWeight === 'bold' ? 'bg-orange-500 border-orange-500 text-white' : 'bg-white border-gray-200 text-gray-600'"
                  >B</button>
                </div>
                <div class="flex flex-col items-center">
                  <label class="text-[9px] text-gray-500 mb-0.5 uppercase tracking-wide">Italic</label>
                  <button
                    @click="tl.fontStyle = tl.fontStyle === 'italic' ? 'normal' : 'italic'"
                    class="w-6 h-6 rounded border text-[11px] italic"
                    :class="tl.fontStyle === 'italic' ? 'bg-orange-500 border-orange-500 text-white' : 'bg-white border-gray-200 text-gray-600'"
                  >I</button>
                </div>
                <div class="flex flex-col items-center">
                  <label class="text-[9px] text-gray-500 mb-0.5 uppercase tracking-wide">Align</label>
                  <div class="flex">
                    <button v-for="align in ['left','center','right']" :key="align"
                      @click="tl.textAlign = align as any"
                      class="w-5 h-6 border text-[9px] first:rounded-l last:rounded-r"
                      :class="(tl.textAlign || 'center') === align ? 'bg-orange-500 border-orange-500 text-white' : 'bg-white border-gray-200 text-gray-600'"
                    >{{ align === 'left' ? '≡' : align === 'center' ? '≡' : '≡' }}</button>
                  </div>
                </div>
              </div>

              <!-- Text Color -->
              <div class="mb-1.5">
                <label class="block text-[9px] text-gray-500 mb-0.5 uppercase tracking-wide">Text Color</label>
                <input v-model="tl.fontColor" type="color" class="w-full h-7 p-0.5 border border-gray-200 rounded bg-white cursor-pointer" />
              </div>

              <!-- ── Box ── -->
              <div class="border border-gray-200 rounded p-1.5 mb-1.5 bg-white">
                <div class="text-[9px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Box Background</div>

                <!-- BG Color + Opacity -->
                <div class="grid grid-cols-2 gap-1 mb-1.5">
                  <div>
                    <label class="block text-[9px] text-gray-500 mb-0.5">Color</label>
                    <input :value="tl.backgroundColor || '#000000'" @input="tl.backgroundColor = ($event.target as HTMLInputElement).value" type="color" class="w-full h-7 p-0.5 border border-gray-200 rounded bg-white cursor-pointer" />
                  </div>
                  <div>
                    <label class="block text-[9px] text-gray-500 mb-0.5">Opacity <span class="text-orange-600">{{ Math.round((tl.backgroundOpacity ?? 0) * 100) }}%</span></label>
                    <input type="range" min="0" max="1" step="0.05" :value="tl.backgroundOpacity ?? 0" @input="tl.backgroundOpacity = parseFloat(($event.target as HTMLInputElement).value)" class="w-full h-1 accent-orange-500 mt-2" />
                  </div>
                </div>

                <!-- Padding + Radius -->
                <div class="grid grid-cols-3 gap-1">
                  <div>
                    <label class="block text-[9px] text-gray-500 mb-0.5">Pad X <span class="text-orange-600">{{ tl.boxPaddingX ?? 12 }}px</span></label>
                    <input type="range" min="0" max="80" step="1" :value="tl.boxPaddingX ?? 12" @input="tl.boxPaddingX = parseInt(($event.target as HTMLInputElement).value)" class="w-full h-1 accent-orange-500 mt-1" />
                  </div>
                  <div>
                    <label class="block text-[9px] text-gray-500 mb-0.5">Pad Y <span class="text-orange-600">{{ tl.boxPaddingY ?? 4 }}px</span></label>
                    <input type="range" min="0" max="60" step="1" :value="tl.boxPaddingY ?? 4" @input="tl.boxPaddingY = parseInt(($event.target as HTMLInputElement).value)" class="w-full h-1 accent-orange-500 mt-1" />
                  </div>
                  <div>
                    <label class="block text-[9px] text-gray-500 mb-0.5">Radius <span class="text-orange-600">{{ tl.boxBorderRadius ?? 4 }}px</span></label>
                    <input type="range" min="0" max="60" step="1" :value="tl.boxBorderRadius ?? 4" @input="tl.boxBorderRadius = parseInt(($event.target as HTMLInputElement).value)" class="w-full h-1 accent-orange-500 mt-1" />
                  </div>
                </div>
              </div>

              <!-- Stroke -->
              <div class="grid grid-cols-2 gap-1 mb-1.5">
                <div>
                  <label class="block text-[9px] text-gray-500 mb-0.5 uppercase tracking-wide">Stroke Color</label>
                  <input :value="tl.strokeColor || '#000000'" @input="tl.strokeColor = ($event.target as HTMLInputElement).value" type="color" class="w-full h-7 p-0.5 border border-gray-200 rounded bg-white cursor-pointer" />
                </div>
                <div>
                  <label class="block text-[9px] text-gray-500 mb-0.5 uppercase tracking-wide">Stroke Width <span class="text-orange-600">{{ tl.strokeWidth ?? 0 }}px</span></label>
                  <input type="range" min="0" max="20" step="1" :value="tl.strokeWidth ?? 0" @input="tl.strokeWidth = parseInt(($event.target as HTMLInputElement).value)" class="w-full h-1 accent-orange-500 mt-2" />
                </div>
              </div>

              <!-- Opacity + Letter spacing -->
              <div class="grid grid-cols-2 gap-1 mb-1.5">
                <div>
                  <label class="block text-[9px] text-gray-500 mb-0.5 uppercase tracking-wide">Opacity <span class="text-orange-600">{{ Math.round((tl.opacity ?? 1) * 100) }}%</span></label>
                  <input type="range" min="0" max="1" step="0.05" :value="tl.opacity ?? 1" @input="tl.opacity = parseFloat(($event.target as HTMLInputElement).value)" class="w-full h-1 accent-orange-500 mt-1" />
                </div>
                <div>
                  <label class="block text-[9px] text-gray-500 mb-0.5 uppercase tracking-wide">Spacing <span class="text-orange-600">{{ tl.letterSpacing ?? 0 }}px</span></label>
                  <input type="range" min="-5" max="30" step="0.5" :value="tl.letterSpacing ?? 0" @input="tl.letterSpacing = parseFloat(($event.target as HTMLInputElement).value)" class="w-full h-1 accent-orange-500 mt-1" />
                </div>
              </div>

              <!-- Animation -->
              <div class="mb-1.5">
                <label class="block text-[9px] text-gray-500 mb-0.5 uppercase tracking-wide">Animation</label>
                <select v-model="tl.animation" class="w-full text-[10px] border border-gray-200 rounded px-1 py-0.5 bg-white">
                  <option value="none">None</option>
                  <option value="fade-in">Fade In</option>
                  <option value="slide-up">Slide Up</option>
                  <option value="slide-down">Slide Down</option>
                </select>
              </div>

              <div class="text-[9px] text-orange-500">Drag on player to reposition</div>
            </template>
            </div>
          </div>
          <h2 class="text-sm font-bold text-gray-800 px-1 pt-1 flex-shrink-0">Scenes</h2>
          <div v-for="(scene, i) in scenes" :key="scene.id" class="flex flex-col gap-1 border border-gray-200 rounded-lg p-2 bg-white text-xs">
            <!-- Scene header: thumbnail + label -->
            <div class="flex items-center gap-2">
              <div class="w-14 h-10 rounded overflow-hidden bg-gray-200 flex-shrink-0">
                <img
                  v-if="scene.generatedImage?.url || scene.animatedVideo?.thumbnailUrl"
                  :src="scene.generatedImage?.url || scene.animatedVideo?.thumbnailUrl"
                  class="w-full h-full object-cover"
                />
                <video
                  v-else-if="scene.animatedVideo?.url"
                  :src="scene.animatedVideo.url"
                  class="w-full h-full object-cover"
                  muted
                />
                <div v-else class="w-full h-full bg-gray-300 flex items-center justify-center text-gray-500 text-[10px]">No img</div>
              </div>
              <span class="font-semibold text-gray-700">Scene {{ i + 1 }}</span>
            </div>

            <!-- Transition to next scene -->
            <div v-if="i < scenes.length - 1" class="flex flex-col gap-1 border-t pt-1 mt-1">
              <span class="text-[10px] text-gray-500 font-medium">Transition →</span>
              <div class="flex items-center gap-1">
                <select
                  v-model="scene.transition_type"
                  class="flex-1 text-[10px] border border-gray-200 rounded px-1 py-0.5 bg-white"
                >
                  <option value="none">None</option>
                  <option value="">Fade</option>
                  <option value="slide">Slide</option>
                  <option value="wipe">Wipe</option>
                  <option value="flip">Flip</option>
                  <option value="clock-wipe">Clock Wipe</option>
                  <option value="iris">Iris</option>
                </select>
                <span class="text-[10px] text-gray-400 whitespace-nowrap">{{ (scene.transition_duration ?? 1).toFixed(1) }}s</span>
              </div>
              <input
                type="range"
                min="0.1"
                max="2"
                step="0.1"
                :value="scene.transition_duration ?? 1"
                @input="scene.transition_duration = parseFloat(($event.target as HTMLInputElement).value)"
                class="w-full h-1 accent-orange-500"
              />
            </div>

          </div>
        </div>
        <!-- End PREVIEW MODE -->

        <!-- Video Controls Section (Shared across all views) -->

        <div v-if="showStoryboardLayout" class="flex flex-col gap-2 border-gray-200 bg-gray-50" style="margin-top: auto;">
          <div class="flex items-center gap-2 overflow-x-auto pb-1">
            <!-- Video Aspect Ratio -->
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button class="h-9 w-16 flex-shrink-0 text-xs">
                <span style="display: flex; align-items: center; gap: 4px;">
                  {{ videoAspectRatio }}
                </span>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              class="bg-black"
              align="start"
            >
              <DropdownMenuItem
                v-for="ratio in videoAspectRatios"
                :key="ratio.value"
                @click="videoAspectRatio = ratio.value"
                class="text-white"
              >
                <span style="display: flex; align-items: center; gap: 6px;">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                  </svg>
                  {{ ratio.label }}
                </span>
                <svg v-if="videoAspectRatio === ratio.value" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <!-- Video Resolution -->
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button class="h-9 w-28 flex-shrink-0 gap-1 overflow-hidden px-2 text-xs" :title="selectedVideoResolutionLabel">
                <span class="min-w-0 flex-1 truncate text-left">
                  {{ selectedVideoResolutionLabel }}
                </span>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              class="w-40 bg-black"
              align="start"
            >
              <DropdownMenuItem
                v-for="resolution in videoResolutions"
                :key="resolution.value"
                @click="videoResolution = resolution.value"
                class="text-white"
              >
                <span style="display: flex; align-items: center; gap: 6px;">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                  </svg>
                  {{ resolution.label }}
                </span>
                <svg v-if="videoResolution === resolution.value" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <!-- Caption Settings -->
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button class="h-9 w-20 flex-shrink-0 text-xs">
                <span style="display: flex; align-items: center; gap: 4px;">
                  Caption
                </span>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              class="w-48 bg-black"
              align="start"
            >
              <div class="px-2 py-2 border-b border-gray-700">
                <label class="flex items-center gap-2 text-white text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    v-model="captionEnabled"
                    class="w-4 h-4"
                  />
                  Enable Captions
                </label>
              </div>
              <div v-if="captionEnabled" class="py-1">
                <DropdownMenuItem
                  @click="openCaptionEditor"
                  class="text-white border-b border-gray-700 mb-1"
                >
                  <span>Edit caption</span>
                </DropdownMenuItem>
                <div class="px-2 py-1 text-xs text-gray-400 font-semibold">Position</div>
                <DropdownMenuItem
                  v-for="position in captionPositions"
                  :key="position.value"
                  @click="captionPosition = position.value"
                  class="text-white"
                >
                  <span>{{ position.label }}</span>
                  <svg v-if="captionPosition === position.value" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
                <div class="px-2 py-1 text-xs text-gray-400 font-semibold border-t border-gray-700 mt-1">Style</div>
                <DropdownMenuItem
                  v-for="style in captionStyles"
                  :key="style.value"
                  @click="captionStyle = style.value; hideStylePreview()"
                  @mouseenter="showStylePreview(style.previewGif, $event)"
                  @mousemove="updateStylePreviewPosition($event)"
                  @mouseleave="hideStylePreview"
                  class="text-white"
                >
                  <span>{{ style.label }}</span>
                  <svg v-if="captionStyle === style.value" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
                <div class="px-2 py-1 text-xs text-gray-400 font-semibold border-t border-gray-700 mt-1">Font</div>
                <DropdownMenuItem
                  v-for="font in availableFonts"
                  :key="font.value"
                  @click="captionFont = font.value"
                  class="text-white"
                >
                  <span :style="{ fontFamily: font.value }">{{ font.label }}</span>
                  <svg v-if="captionFont === font.value" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
                <div class="px-2 py-1 text-xs text-gray-400 font-semibold border-t border-gray-700 mt-1">Font Size</div>
                <DropdownMenuItem
                  v-for="size in fontSizes"
                  :key="size.value"
                  @click="captionFontSize = size.value"
                  class="text-white"
                >
                  <span>{{ size.label }}</span>
                  <svg v-if="captionFontSize === size.value" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          <!-- Logo Branding Settings -->
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button
                class="h-9 w-20 flex-shrink-0 text-xs"
                :class="{ 'opacity-50': !hasProfileWatermarkLogo }"
                :title="hasProfileWatermarkLogo ? 'Logo/watermark settings' : 'Upload a logo on your profile to enable this option'"
              >
                <span class="flex items-center gap-1">
                  Logo
                  <i v-if="includeWatermarkLogo && hasProfileWatermarkLogo" class="fa-solid fa-check text-[0.6rem]"></i>
                </span>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent class="w-56 bg-black" align="start">
              <div class="px-2 py-2 border-b border-gray-700" @click.stop>
                <label class="flex items-center gap-2 text-white text-sm cursor-pointer" :class="{ 'opacity-50 cursor-not-allowed': !hasProfileWatermarkLogo }">
                  <input
                    v-model="includeWatermarkLogo"
                    type="checkbox"
                    :disabled="!hasProfileWatermarkLogo || isGeneratingVideo"
                    class="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>Include logo</span>
                </label>
                <p v-if="!hasProfileWatermarkLogo" class="mt-1 text-[11px] leading-4 text-gray-400">Upload a profile logo to enable this.</p>
              </div>
              <div class="px-2 py-1 text-xs text-gray-400 font-semibold">Position</div>
              <DropdownMenuItem
                v-for="position in watermarkLogoPositions"
                :key="position.value"
                @click="watermarkLogoPosition = position.value"
                class="text-white"
                :class="{ 'opacity-50 pointer-events-none': !includeWatermarkLogo || !hasProfileWatermarkLogo }"
              >
                <span>{{ position.label }}</span>
                <svg v-if="watermarkLogoPosition === position.value" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          </div>

          <!-- Generate Video Button -->
          <TooltipProvider :delay-duration="150">
            <Tooltip>
              <TooltipTrigger as-child>
                <span class="inline-flex w-full">
                  <Button
                    class="w-full justify-center bg-linear-to-r from-yellow-400 to-red-500 cursor-pointer"
                    @click="generateVideo"
                    :disabled="!hasAllImages || isGeneratingVideo || scenes.length === 0"
                    :title="!hasAllImages && scenes.length > 0 ? 'Please generate all scene images first' : 'Render video'"
                  >
                    <i v-if="!isGeneratingVideo" class="fa-solid fa-video"></i>
                    <i v-else class="fa-solid fa-spinner fa-spin"></i>
                    {{ isGeneratingVideo ? 'Generating...' : 'Generate Video' }}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent side="bottom" class="max-w-60 text-center">
                <span v-if="!hasAllImages && scenes.length > 0">Generate all scene images first.</span>
                <span v-else>Render video</span>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>



          <!-- Small Video Preview (only shows when video is ready) -->
          <!-- <div
            v-if="finalGeneratedVideo"
            @click="showFinalVideoPreview"
            class="w-8 h-8 cursor-pointer rounded-md overflow-hidden border-2 border-green-500 hover:border-green-600 transition-all hover:shadow-lg relative group flex-shrink-0"
            title="Click to preview final video"
          >
            <video
              :src="finalGeneratedVideo.url"
              class="w-full h-full object-cover bg-black"
              muted
            >
              Your browser does not support the video tag.
            </video>

            <div class="absolute inset-0 bg-black bg-opacity-40 group-hover:bg-opacity-50 transition-opacity flex items-center justify-center">
              <div class= "bg-opacity-90 rounded-full p-1">
                <i class="fa-solid fa-play text-green-600 text-xs"></i>
              </div>
            </div>
          </div> -->
          
        </div>
      </aside>

      <!-- RIGHT PANEL - PREVIEW -->
      <main class="preview-panel" :class="{ 'preview-panel--fullfit': showingPreview }">
        <!-- Preview Content Wrapper (for mobile reordering) -->
        <div class="preview-content" :class="{ 'preview-content--fullfit': showingPreview }">

        <!-- Idea Processing Loading State -->
        <div v-if="!showStoryboardLayout && !showingFinalVideo && !showingGallery && creationMode === 'ideaToVideo' && isImprovingIdea" class="w-full h-full flex items-center justify-center">
          <div class="text-center text-gray-400 p-8">
            <div class="animate-spin rounded-full h-24 w-24 border-b-4 border-orange-600 mx-auto mb-4"></div>
            <p class="text-2xl font-medium text-gray-700">
              Processing Your Idea
            </p>
            <p class="text-sm mt-2 text-gray-500">
              AI is analyzing and improving your video idea...
            </p>
            <p class="text-sm mt-2 text-gray-500">
              This may take a few moments.
            </p>
          </div>
        </div>

        <!-- Idea Results Display (only show in Script section AND Idea to Video mode AND repurpose sub-mode) -->
        <div v-else-if="!showStoryboardLayout && !showingFinalVideo && !showingGallery && creationMode === 'ideaToVideo' && showingIdeaResults && improvedIdeaResults && ideaSubMode === 'repurpose'" class="w-full h-full flex flex-col p-6 overflow-y-auto">

            <!-- Header -->
            <div class="flex items-center justify-between mb-4">
              <h3 class="text-xl font-bold flex items-center gap-2">
                Improved Video Scripts
              </h3>
            </div>

            <!-- Analysis Section (hook + content) -->
            <div class="mb-6 rounded-lg border-0 border-orange-200">

              <div class="space-y-3">
                <div>
                  <label class="block text-sm font-semibold text-orange-600 mb-1">Hook Analysis:</label>
                  <div class="bg-white rounded-lg p-3 border border-orange-200 text-gray-700 text-sm leading-relaxed">
                    {{ improvedIdeaResults.analysis.hook }}
                  </div>
                </div>
                <div>
                  <label class="block text-sm font-semibold text-orange-600 mb-1">Content Analysis:</label>
                  <div class="bg-white rounded-lg p-3 border border-orange-200 text-gray-700 text-sm leading-relaxed">
                    {{ improvedIdeaResults.analysis.content }}
                  </div>
                </div>
              </div>
            </div>

            <!-- Version Selector Buttons and Apply Button -->
            <div class="mb-4 flex gap-3 items-center justify-between">
              <div class="flex gap-2">
                <button
                  @click="selectedIdeaVersion = 1"
                  :class="[
                    'py-2 px-3 rounded-lg font-medium text-xs transition-all',
                    selectedIdeaVersion === 1
                    ? 'bg-orange-500 text-white shadow-md'
                    : 'bg-gray-200 text-gray-700 hover:bg-gray-300']"
                >
                  Version 1
                </button>
                <button
                  @click="selectedIdeaVersion = 2"
                  :class="[
                    'py-2 px-3 rounded-lg font-medium text-xs transition-all',
                    selectedIdeaVersion === 2
                       ? 'bg-orange-500 text-white shadow-md'
                    : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  ]"
                >
                  Version 2
                </button>
              </div>

              <button
                @click="applyImprovedIdea"
                class="px-4 py-2 bg-gradient-to-r from-yellow-400 to-red-500 text-white rounded-lg hover:from-yellow-300 hover:to-red-400 transition-all text-xs font-semibold shadow-md flex items-center gap-2"
              >
                <i class="fa-solid fa-check"></i>
                Apply Version {{ selectedIdeaVersion }} to Script
              </button>
            </div>

            <!-- Version Content Display -->
            <div class="space-y-4">
              <!-- Improved Script -->
              <div>
                <label class="block text-sm font-semibold text-orange-600 mb-2">
                  Improved Script (Version {{ selectedIdeaVersion }}):
                </label>
                <div class="bg-white rounded-lg p-4 border border-orange-200 text-gray-800 text-sm leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto">
                  {{ selectedIdeaVersion === 1 ? improvedIdeaResults.version_1.improved_script : improvedIdeaResults.version_2.improved_script }}
                </div>
              </div>

              <!-- Title -->
              <div>
                <label class="block text-sm font-semibold text-orange-600 mb-1">
                  Title (Version {{ selectedIdeaVersion }}):
                </label>
                <div class="bg-white rounded-lg p-3 border border-orange-200 text-gray-800 text-sm font-medium">
                  {{ selectedIdeaVersion === 1 ? improvedIdeaResults.version_1.title : improvedIdeaResults.version_2.title }}
                </div>
              </div>

              <!-- Description -->
              <div>
                <label class="block text-sm font-semibold text-orange-600 mb-1">Description:</label>
                <div class="bg-white rounded-lg p-3 border border-orange-200 text-gray-700 text-sm">
                  {{ improvedIdeaResults.description }}
                </div>
              </div>

              <!-- Tags with Copy Button -->
              <div>
                <div class="flex items-center justify-between mb-1">
                  <label class="block text-sm font-semibold text-orange-600">Tags:</label>
                  <button
                    @click="copyToClipboard(improvedIdeaResults.tags.join(', '), 'Tags')"
                    class="p-1 text-gray-500 hover:text-orange-500 transition-colors"
                    title="Copy Tags"
                  >
                    <i class="fa-solid fa-copy"></i>
                  </button>
                </div>
                <div class="bg-white rounded-lg p-3 border border-orange-200 text-gray-700 text-sm">
                  {{ improvedIdeaResults.tags.join(', ') }}
                </div>
              </div>

              <!-- Hashtags with Copy Button -->
              <div>
                <div class="flex items-center justify-between mb-1">
                  <label class="block text-sm font-semibold text-orange-600">Hashtags:</label>
                  <button
                    @click="copyToClipboard(improvedIdeaResults.hashtags.join(' '), 'Hashtags')"
                    class="p-1 text-gray-500 hover:text-orange-500 transition-colors"
                    title="Copy Hashtags"
                  >
                    <i class="fa-solid fa-copy"></i>
                  </button>
                </div>
                <div class="bg-white rounded-lg p-3 border border-orange-200 text-gray-700 text-sm">
                  {{ improvedIdeaResults.hashtags.join(' ') }}
                </div>
              </div>
            </div>

        </div>

        <!-- Trending Topics Results Panel -->
        <div
          v-else-if="!showStoryboardLayout && !showingFinalVideo && !showingGallery && creationMode === 'ideaToVideo' && showingTrendingResults && trendingTopics.length > 0"
          class="w-full h-full flex flex-col p-6 overflow-y-auto bg-gray-50"
        >
          <div class="mb-4">
            <h3 class="text-xl font-bold text-gray-900 flex items-center gap-2">
              <i class="fa-solid fa-fire text-orange-500"></i>
              Trending: {{ trendKeyword }}
            </h3>
            <p class="text-sm text-gray-600 mt-1">
              Found {{ trendingTopics.length }} high-performing videos. Click to use as inspiration.
            </p>

            <!-- Back button -->
            <button
              @click="showingTrendingResults = false"
              class="mt-3 px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300 transition-colors"
            >
              ← Back to Idea Input
            </button>
          </div>

          <div class="grid gap-4">
            <div
              v-for="topic in trendingTopics"
              :key="topic.url"
              class="bg-white border-2 border-orange-200 rounded-lg p-4 hover:shadow-lg transition-all"
            >
              <div class="flex gap-3">
                <!-- Thumbnail -->
                <img
                  :src="topic.thumbnail"
                  :alt="topic.title"
                  class="w-32 h-20 object-cover rounded flex-shrink-0"
                />

                <!-- Content -->
                <div class="flex-1 min-w-0">
                  <h4 class="font-semibold text-gray-900 mb-1 line-clamp-2">
                    {{ topic.title }}
                  </h4>

                  <p class="text-xs text-gray-600 mb-2">
                    {{ topic.channel_name }} • {{ topic.subscriber_count.toLocaleString() }} subscribers
                  </p>

                  <div class="flex flex-wrap gap-2">
                    <span
                      :class="[
                        'text-xs px-2 py-1 rounded font-medium',
                        topic.content_type === 'Short'
                          ? 'bg-purple-100 text-purple-700'
                          : 'bg-gray-100 text-gray-700'
                      ]"
                    >
                      {{ topic.content_type === 'Short' ? '🎬 Short' : '📹 Video' }}
                    </span>
                    <span class="text-xs bg-green-100 text-green-700 px-2 py-1 rounded font-medium">
                      🔥 Viral Score: {{ topic.viral_score }}
                    </span>
                    <span class="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">
                      👁️ {{ (topic.views / 1000).toFixed(2) }}K views
                    </span>
                  </div>

                  <!-- Action Buttons -->
                  <div class="flex gap-2 mt-3">
                    <button
                      @click="selectTrendingTopic(topic)"
                      class="px-3 py-1.5 bg-orange-500 text-white text-sm rounded hover:bg-orange-600 transition-colors"
                    >
                      <i class="fa-solid fa-wand-magic-sparkles mr-1"></i>
                      Use This Idea
                    </button>
                    <a
                      :href="topic.url"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="px-3 py-1.5 border border-orange-500 text-orange-500 text-sm rounded hover:bg-orange-50 transition-colors inline-flex items-center"
                    >
                      <i class="fa-brands fa-youtube mr-1"></i>
                      Watch Video
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Generated Script Results Display (only show in Script section AND Idea to Video mode AND ideas sub-mode) -->
        <div v-else-if="!showStoryboardLayout && !showingFinalVideo && !showingGallery && creationMode === 'ideaToVideo' && showingIdeaResults && generatedScriptResults && ideaSubMode === 'ideas'" class="w-full h-full flex flex-col p-6 overflow-y-auto">

          <!-- Header -->
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-xl font-bold flex items-center gap-2">
              Generated Script
              <span class="text-sm font-normal text-gray-500">
                (≈{{ selectedGeneratedVersion === 1 ? generatedScriptResults.version_1.estimated_duration : generatedScriptResults.version_2.estimated_duration }})
              </span>
            </h3>
          </div>

          <!-- Version Selector -->
          <!-- Version Selector and Apply Button on Same Line -->
          <div class="mb-4 flex items-center justify-between gap-3">
            <div class="flex items-center gap-3">
              <label class="text-sm font-semibold text-gray-700">Select Version:</label>
              <button
                @click="selectedGeneratedVersion = 1"
                :class="[
                  'px-3 py-1.5 rounded-lg text-sm font-medium transition-all',
                  selectedGeneratedVersion === 1
                    ? 'bg-orange-500 text-white shadow-md'
                    : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                ]"
              >
                Version 1
              </button>
              <button
                @click="selectedGeneratedVersion = 2"
                :class="[
                  'px-3 py-1.5 rounded-lg text-sm font-medium transition-all',
                  selectedGeneratedVersion === 2
                    ? 'bg-orange-500 text-white shadow-md'
                    : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                ]"
              >
                Version 2
              </button>
            </div>
            <button
              @click="applyGeneratedScript"
              class="px-4 py-2 bg-gradient-to-r from-yellow-400 to-red-500 text-white rounded-lg hover:from-yellow-300 hover:to-red-400 transition-all text-xs font-semibold shadow-md flex items-center gap-2"
            >
              <i class="fa-solid fa-check"></i>
              Apply Version {{ selectedGeneratedVersion }}
            </button>
          </div>

          <!-- Script Content -->
          <div class="space-y-4">
            <!-- Generated Script -->
            <div>
              <div class="flex items-center justify-between mb-2">
                <label class="block text-sm font-semibold text-orange-600">
                  Full Script:
                  <span class="font-normal text-gray-500">
                    ({{ selectedGeneratedVersion === 1 ? generatedScriptResults.version_1.word_count : generatedScriptResults.version_2.word_count }} words)
                  </span>
                </label>
                <button
                  @click="copyToClipboard(selectedGeneratedVersion === 1 ? generatedScriptResults.version_1.script : generatedScriptResults.version_2.script, 'Script')"
                  class="p-1 text-gray-500 hover:text-orange-500 transition-colors"
                  title="Copy Script"
                >
                  <i class="fa-solid fa-copy"></i>
                </button>
              </div>
              <div class="bg-white rounded-lg p-4 border border-orange-200 text-gray-800 text-sm leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto">
                {{ selectedGeneratedVersion === 1 ? generatedScriptResults.version_1.script : generatedScriptResults.version_2.script }}
              </div>
            </div>

            <!-- Title -->
            <div>
              <div class="flex items-center justify-between mb-1">
                <label class="block text-sm font-semibold text-orange-600">Title:</label>
                <button
                  @click="copyToClipboard(selectedGeneratedVersion === 1 ? generatedScriptResults.version_1.title : generatedScriptResults.version_2.title, 'Title')"
                  class="p-1 text-gray-500 hover:text-orange-500 transition-colors"
                  title="Copy Title"
                >
                  <i class="fa-solid fa-copy"></i>
                </button>
              </div>
              <div class="bg-white rounded-lg p-3 border border-orange-200 text-gray-800 text-sm font-medium">
                {{ selectedGeneratedVersion === 1 ? generatedScriptResults.version_1.title : generatedScriptResults.version_2.title }}
              </div>
            </div>

            <!-- Description -->
            <div>
              <div class="flex items-center justify-between mb-1">
                <label class="block text-sm font-semibold text-orange-600">Description:</label>
                <button
                  @click="copyToClipboard(generatedScriptResults.description, 'Description')"
                  class="p-1 text-gray-500 hover:text-orange-500 transition-colors"
                  title="Copy Description"
                >
                  <i class="fa-solid fa-copy"></i>
                </button>
              </div>
              <div class="bg-white rounded-lg p-3 border border-orange-200 text-gray-700 text-sm">
                {{ generatedScriptResults.description }}
              </div>
            </div>

            <!-- Tags -->
            <div>
              <div class="flex items-center justify-between mb-1">
                <label class="block text-sm font-semibold text-orange-600">Tags:</label>
                <button
                  @click="copyToClipboard(generatedScriptResults.tags.join(', '), 'Tags')"
                  class="p-1 text-gray-500 hover:text-orange-500 transition-colors"
                  title="Copy Tags"
                >
                  <i class="fa-solid fa-copy"></i>
                </button>
              </div>
              <div class="bg-white rounded-lg p-3 border border-orange-200 text-gray-700 text-sm">
                {{ generatedScriptResults.tags.join(', ') }}
              </div>
            </div>

            <!-- Hashtags -->
            <div>
              <div class="flex items-center justify-between mb-1">
                <label class="block text-sm font-semibold text-orange-600">Hashtags:</label>
                <button
                  @click="copyToClipboard(generatedScriptResults.hashtags.join(' '), 'Hashtags')"
                  class="p-1 text-gray-500 hover:text-orange-500 transition-colors"
                  title="Copy Hashtags"
                >
                  <i class="fa-solid fa-copy"></i>
                </button>
              </div>
              <div class="bg-white rounded-lg p-3 border border-orange-200 text-gray-700 text-sm">
                {{ generatedScriptResults.hashtags.join(' ') }}
              </div>
            </div>
          </div>

        </div>

        <!-- DEFAULT SCRIPT TAB VIEW (when not showing special results) -->
        <div v-else-if="!showStoryboardLayout && !showingFinalVideo && !showingGallery" class="w-full h-full flex flex-col p-6 overflow-y-auto">
          <!-- Creation Mode Tabs -->
          <div class="creation-mode-tabs preview-mode-buttons mb-6">
            <!-- Idea to vide / Repurpose -->
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button
                  class="preview-mode-btn cursor-pointer"
                  :class="creationMode === 'ideaToVideo' ? 'bg-orange-500 text-white' : 'bg-black text-white hover:bg-orange-500/10 hover:text-orange-500'"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-4">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 0 0 1.5-.189m-1.5.189a6.01 6.01 0 0 1-1.5-.189m3.75 7.478a12.06 12.06 0 0 1-4.5 0m3.75 2.383a14.406 14.406 0 0 1-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 1 0-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                  </svg>
                  Idea to Video
                  <svg class="w-3 h-3 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                  </svg>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuItem @click="creationMode = 'ideaToVideo'; ideaSubMode = 'ideas'">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4 mr-2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 0 0 1.5-.189m-1.5.189a6.01 6.01 0 0 1-1.5-.189m3.75 7.478a12.06 12.06 0 0 1-4.5 0m3.75 2.383a14.406 14.406 0 0 1-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 1 0-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                  </svg>
                  Ideas
                </DropdownMenuItem>
                <DropdownMenuItem @click="creationMode = 'ideaToVideo'; ideaSubMode = 'repurpose'">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4 mr-2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
                  </svg>
                  Repurpose
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <!-- Script to video -->
            <Button
              class="preview-mode-btn cursor-pointer"
              :class="creationMode === 'scriptToVideo' ? 'bg-orange-500 text-white' : 'bg-black text-white hover:bg-orange-500/10 hover:text-orange-500'"
              @click="creationMode = 'scriptToVideo'"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Script to Video
            </Button>

            <!-- AUdio to video -->
            <Button
              class="preview-mode-btn cursor-pointer"
              :class="creationMode === 'audioToVideo' ? 'bg-orange-500 text-white' : 'bg-black text-white hover:bg-orange-500/10 hover:text-orange-500'"
              @click="creationMode = 'audioToVideo'"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              Audio to Video
            </Button>
          </div>

          <!-- Script to Video Input Section (only show when in scriptToVideo mode) -->
          <div v-if="creationMode === 'scriptToVideo'">
            <div class="section-label">The Script</div>
            <div class="mb-3 rounded-lg border border-gray-200 bg-white p-2">
              <div class="text-[11px] font-semibold uppercase tracking-wide text-gray-500 mb-2">Pipeline Mode</div>
              <div class="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  @click="projectMode = 'narrated_broll'"
                  class="rounded-md border px-3 py-2 text-left transition-colors"
                  :class="projectMode === 'narrated_broll' ? 'border-orange-500 bg-orange-50 text-orange-700' : 'border-gray-200 text-gray-700 hover:border-gray-300'"
                >
                  <div class="text-sm font-semibold">Narrated B-Roll</div>
                  <div class="text-[11px] text-gray-500">Full audio first, transcript timing, then scenes and visuals.</div>
                </button>
                <button
                  type="button"
                  @click="projectMode = 'talking_scenes'"
                  class="rounded-md border px-3 py-2 text-left transition-colors"
                  :class="projectMode === 'talking_scenes' ? 'border-orange-500 bg-orange-50 text-orange-700' : 'border-gray-200 text-gray-700 hover:border-gray-300'"
                >
                  <div class="text-sm font-semibold">Talking Scenes</div>
                  <div class="text-[11px] text-gray-500">Plan standalone scene clips, then generate scene-local audio.</div>
                </button>
              </div>
            </div>
            <div class="script-box">
              <textarea
                v-model="script"
                :placeholder="projectMode === 'talking_scenes'
                  ? 'Use blank lines to separate scenes. Dialogue format: Alice: We need to leave now. Bob: Wait, I forgot the keys.'
                  : 'Once upon a time in a futuristic city...'"
                rows="30"
                class="w-full h-[250px] border-2 rounded-lg p-4 text-base resize-none outline-none transition-colors duration-200 focus:border-blue-500"
              ></textarea>
              <!-- Voice Settings Button (Bottom Left) -->
              <button class="absolute bottom-3 left-3 bg-orange-500 text-white border-0 p-2 rounded-md w-20 h-8 gap-1 cursor-pointer flex items-center justify-center transition-all duration-200 shadow-md hover:bg-gray-700 hover:scale-105 hover:shadow-lg" @click="isVoiceModalOpen = !isVoiceModalOpen" title="Voice Settings">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <rect x="2" y="8" width="2" height="8" rx="1" fill="currentColor"/>
                  <rect x="6" y="4" width="2" height="16" rx="1" fill="currentColor"/>
                  <rect x="10" y="10" width="2" height="4" rx="1" fill="currentColor"/>
                  <rect x="14" y="6" width="2" height="12" rx="1" fill="currentColor"/>
                  <rect x="18" y="9" width="2" height="6" rx="1" fill="currentColor"/>
                </svg>
                <span class='font-semibold'>Voice</span>
              </button>
              <span v-if="selectedVoiceObject" class="absolute bottom-3 left-24 text-sm text-gray-700 bg-gray-100 px-3 py-1 rounded-md font-medium">{{ selectedVoiceObject?.name }}</span>
            </div>

            <!-- Script Stats -->
            <div v-if="script.length > 0" class="mt-2 text-xs text-gray-600 space-y-1">
              <div class="flex justify-between">
                <span>{{ sentenceCount }} sentence{{ sentenceCount !== 1 ? 's' : '' }} • {{ wordCount }} words • ~{{ estimatedDuration }} min</span>
                <span class="font-semibold">{{ characterCount.toLocaleString() }} characters</span>
              </div>
            </div>

            <!-- Voice Settings Modal -->
            <div v-if="isVoiceModalOpen" class="voice-modal-overlay" @click="isVoiceModalOpen = false">
              <div class="voice-modal" @click.stop>
                <div class="voice-modal-header">
                  <h3>Voice Settings</h3>
                  <button @click="isVoiceModalOpen = false" class="modal-close-btn">
                    <i class="fa-solid fa-times"></i>
                  </button>
                </div>

                <div class="voice-modal-content">
                  <!-- Custom Voices Section -->
                  <div class="voice-section custom-voices-section">
                    <div class="custom-voices-header">
                      <h4 class="voice-section-label">My Custom Voices ({{ customVoices.length }}/5)</h4>
                      <button
                        @click="console.log('Add Voice clicked!'); showCustomVoiceUpload = true; console.log('showCustomVoiceUpload:', showCustomVoiceUpload)"
                        class="btn-add-voice"
                        :disabled="customVoices.length >= 5"
                      >
                        <i class="fa-solid fa-plus"></i>
                        <span>Add Voice</span>
                      </button>
                    </div>

                    <div v-if="isLoadingCustomVoices" class="custom-voices-loading">
                      <i class="fa-solid fa-spinner fa-spin"></i>
                      <span>Loading custom voices...</span>
                    </div>

                    <div v-else-if="customVoices.length > 0" class="custom-voices-list">
                      <div
                        v-for="voice in customVoices"
                        :key="voice.id"
                        class="custom-voice-item"
                        :class="{ 'custom-voice-selected': selectedVoice === getCustomVoiceId(voice) }"
                      >
                        <div class="voice-info" @click="handleVoiceSelection({ id: getCustomVoiceId(voice), provider: getCustomVoiceProvider(voice) })">
                          <span class="voice-name">{{ voice.voice_name }} ⭐</span>
                          <span v-if="voice.description" class="voice-description">{{ voice.description }}</span>
                        </div>
                        <div class="voice-actions">
                          <button
                            v-if="voice.preview_url"
                            @click.stop="toggleAudioPlayback({ id: getCustomVoiceId(voice), sampleUrl: voice.preview_url })"
                            :class="[
                              'play-button',
                              isAudioPlaying(getCustomVoiceId(voice)) ? 'play-button-stop' : 'play-button-play'
                            ]"
                            :title="isAudioPlaying(getCustomVoiceId(voice)) ? 'Stop preview' : 'Play preview'"
                          >
                            <i v-if="!isAudioPlaying(getCustomVoiceId(voice))" class="fa-solid fa-play"></i>
                            <i v-else class="fa-solid fa-stop"></i>
                          </button>
                          <button
                            @click.stop="deleteCustomVoice(voice.id, voice.voice_name)"
                            class="btn-delete"
                            title="Delete voice"
                          >
                            <i class="fa-solid fa-trash"></i>
                          </button>
                        </div>
                      </div>
                    </div>

                    <p v-else class="no-voices">No custom voices yet. Upload your first voice!</p>
                  </div>

                  <!-- Voice Selection -->
                  <div class="voice-section">
                    <label class="voice-section-label">Select Narrator Voice</label>
                    <div class="relative" ref="voiceDropdownRef">
                      <!-- Dropdown Button -->
                      <button
                        @click="isVoiceDropdownOpen = !isVoiceDropdownOpen"
                        class="voice-dropdown-button"
                      >
                        <div class="flex items-center gap-2">
                          <span v-if="selectedVoiceObject" class="voice-display">
                            <span :class="[
                              'provider-badge',
                              selectedVoiceObject.provider === 'minimax' ? 'provider-minimax' :
                              selectedVoiceObject.provider === 'deepgram' ? 'provider-deepgram' :
                              selectedVoiceObject.provider === 'google' ? 'provider-google' :
                              selectedVoiceObject.provider === 'elevenlabs' ? 'provider-elevenlabs' :
                              'provider-default'
                            ]">
                              {{ getProviderLabel(selectedVoiceObject.provider).replace('[', '').replace(']', '') }}
                            </span>
                            {{ selectedVoiceObject.name }} - {{ selectedVoiceObject.description }}
                          </span>
                          <span v-else class="text-gray-500">Select a voice...</span>
                        </div>
                        <i class="fa-solid fa-chevron-down dropdown-icon" :class="{ 'rotate-180': isVoiceDropdownOpen }"></i>
                      </button>

                      <!-- Dropdown Menu -->
                      <div
                        v-if="isVoiceDropdownOpen"
                        class="voice-dropdown-menu"
                      >
                        <div
                          v-for="voice in voiceOptions"
                          :key="voice.id"
                          class="voice-dropdown-item"
                          :class="{ 'voice-selected': selectedVoice === voice.id }"
                        >
                          <!-- Voice Info (clickable to select) -->
                          <div
                            @click="handleVoiceSelection(voice)"
                            class="voice-info"
                          >
                            <div class="voice-header">
                              <span :class="[
                                'provider-badge',
                                voice.provider === 'minimax' ? 'provider-minimax' :
                                voice.provider === 'deepgram' ? 'provider-deepgram' :
                                voice.provider === 'google' ? 'provider-google' :
                                voice.provider === 'elevenlabs' ? 'provider-elevenlabs' :
                                'provider-default'
                              ]">
                                {{ getProviderLabel(voice.provider).replace('[', '').replace(']', '') }}
                              </span>
                              <h5 class="voice-name">{{ voice.name }}</h5>
                            </div>
                            <p class="voice-description">{{ voice.description }}</p>
                            <div class="voice-tags">
                              <span v-for="tag in voice.tags.slice(0, 3)" :key="tag" class="voice-tag">
                                {{ tag }}
                              </span>
                            </div>
                          </div>

                          <!-- Play Button (show for voices with sampleUrl OR ElevenLabs voices) -->
                          <button
                            v-if="voice.sampleUrl || voice.provider === 'elevenlabs'"
                            @click.stop="toggleAudioPlayback(voice)"
                            :class="[
                              'play-button',
                              isAudioPlaying(voice.id) ? 'play-button-stop' : 'play-button-play',
                              isLoadingVoicePreview(voice.id) ? 'play-button-loading' : ''
                            ]"
                            :title="isAudioPlaying(voice.id) ? 'Stop preview' : 'Play preview'"
                            :disabled="isLoadingVoicePreview(voice.id)"
                          >
                            <i v-if="isLoadingVoicePreview(voice.id)" class="fa-solid fa-spinner fa-spin"></i>
                            <i v-else-if="!isAudioPlaying(voice.id)" class="fa-solid fa-play"></i>
                            <i v-else class="fa-solid fa-stop"></i>
                          </button>
                          <div v-else class="no-sample">No sample</div>
                        </div>
                      </div>

                      <!-- Hidden Audio Elements -->
                      <audio
                        v-for="voice in voiceOptions.filter(v => v.sampleUrl)"
                        :key="voice.id"
                        :src="voice.sampleUrl"
                        preload="metadata"
                        @ended="onAudioEnded(voice.id)"
                        @error="onAudioError(voice)"
                        class="hidden"
                      ></audio>
                    </div>
                  </div>

                  <!-- Audio Speed Control -->
                  <div class="voice-section">
                    <label class="voice-section-label">Audio Speed</label>
                    <div class="speed-slider-container">
                      <span class="speed-marker">0.5x</span>
                      <input
                        type="range"
                        v-model.number="audioSpeed"
                        min="0.5"
                        max="2"
                        step="0.01"
                        class="speed-slider"
                      >
                      <span class="speed-marker">2.0x</span>
                      <span class="speed-value">{{ audioSpeed.toFixed(2) }}x</span>
                    </div>
                    <div
                      v-if="hasPendingGeneratedAudioSpeedChange"
                      class="mt-3 flex items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800"
                    >
                      <span>
                        Generated audio is {{ appliedAudioSpeed.toFixed(2) }}x. Apply {{ audioSpeed.toFixed(2) }}x and rescale scene timestamps.
                      </span>
                      <button
                        type="button"
                        class="shrink-0 rounded-md bg-blue-600 px-3 py-1.5 font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                        :disabled="isAdjustingAudioSpeed"
                        @click="applyAudioSpeedToGeneratedAudio"
                      >
                        <i v-if="isAdjustingAudioSpeed" class="fa-solid fa-spinner fa-spin mr-1"></i>
                        {{ isAdjustingAudioSpeed ? 'Applying...' : 'Apply' }}
                      </button>
                    </div>
                  </div>
                </div>

                <!-- Confirm Button -->
                <div class="voice-modal-footer">
                  <button @click="isVoiceModalOpen = false" class="voice-confirm-btn">
                    <i class="fa-solid fa-check"></i>
                    Confirm
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Audio to Video Input Section (only show when in audioToVideo mode) -->
          <div v-if="creationMode === 'audioToVideo'">
            <div class="section-label">Upload Audio</div>
            <div class="audio-upload-box">
              <input
                type="file"
                ref="audioFileInput"
                accept="audio/*"
                @change="handleAudioFileSelect"
                class="hidden"
              />

              <div
                v-if="!generatedAudio"
                class="audio-upload-dropzone"
                :class="{
                  'audio-upload-zone-dragging': isDraggingAudio,
                  'audio-upload-zone-disabled': isUploadingAudio
                }"
                @dragover.prevent="isDraggingAudio = true"
                @dragleave.prevent="isDraggingAudio = false"
                @drop.prevent="handleAudioFileDrop"
                @click="audioFileInput?.click()"
              >
                <svg class="upload-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p class="upload-text">
                  {{ isUploadingAudio ? 'Uploading...' : 'Drop your audio file here or click to browse' }}
                </p>
                <p class="upload-hint">MP3, WAV, M4A, or OGG (max 50MB)</p>
              </div>

              <div v-else class="audio-preview">
                <audio
                  :key="audioPlayerKey"
                  :src="generatedAudio.url"
                  controls
                  class="audio-player"
                  @timeupdate="handleAudioTimeUpdate"
                ></audio>
                <div class="audio-info">
                  <span class="text-xs text-gray-600">Duration: {{ formatDuration(generatedAudio.duration) }}</span>
                </div>
                <button @click="removeUploadedAudio" class="remove-audio-btn">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  Remove
                </button>
              </div>

              <!-- Audio Upload Error -->
              <div v-if="audioUploadError" class="text-sm text-red-600 bg-red-50 p-2 rounded mt-2">
                {{ audioUploadError }}
              </div>

              <!-- Audio Upload Progress -->
              <div v-if="isUploadingAudio" class="mt-4">
                <div class="flex items-center gap-3 mb-2">
                  <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-orange-500"></div>
                  <span class="text-orange-700 text-sm font-medium">Uploading audio file...</span>
                </div>
                <div class="w-full bg-orange-200 rounded-full h-2">
                  <div class="bg-orange-500 h-2 rounded-full transition-all duration-500" :style="{ width: `${audioUploadProgress}%` }"></div>
                </div>
              </div>
            </div>
          </div>

          <!-- Idea to Video Input Section (only show when in ideaToVideo mode) -->
          <div v-if="creationMode === 'ideaToVideo'">
            <div class="section-label">{{ ideaSubMode === 'ideas' ? 'YOUR IDEA' : 'CONTENT TO REPURPOSE' }}</div>

            <!-- Trend Analysis Section -->
            <div v-if="ideaSubMode === 'ideas'" class="mb-4">
              <div class="flex gap-2">
                <input
                  v-model="trendKeyword"
                  @keydown.enter="fetchTrendingTopics"
                  type="text"
                  placeholder="Enter a topic to find trending videos (e.g., 'finance tips', 'fitness')"
                  class="trending-input flex-1 px-4 py-2 border-2 border-gray-300 rounded-lg outline-none focus:border-orange-500 transition-colors text-sm"
                />
                <button
                  @click="fetchTrendingTopics"
                  :disabled="isFetchingTrends || !trendKeyword.trim()"
                  class="trending-button px-6 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2 text-sm font-medium whitespace-nowrap"
                >
                  <i v-if="!isFetchingTrends" class="fa-solid fa-fire"></i>
                  <i v-else class="fa-solid fa-spinner fa-spin"></i>
                  {{ isFetchingTrends ? 'Searching...' : 'Find Trending Topics' }}
                </button>
              </div>
            </div>

            <div class="script-box relative">
              <textarea
                v-model="ideaText"
                :placeholder="ideaSubMode === 'ideas'
                  ? 'Describe your video idea... (e.g., \'I want to make a video about the benefits of morning routines\')'
                  : 'Paste the content you want to repurpose into a video... (e.g., blog post, article, script from another video)'"
                class="w-full h-[250px] border-2 rounded-lg p-4 text-base resize-none outline-none transition-colors duration-200 focus:border-purple-500"
              ></textarea>

              <!-- Video Length Slider (only for 'ideas' mode) -->
              <div v-if="ideaSubMode === 'ideas'" class="absolute bottom-3 left-3 right-20">
                <div class="flex items-center justify-between gap-2 mb-2">
                  <div class="flex items-center gap-2">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="flex-shrink-0 text-gray-600">
                      <circle cx="12" cy="12" r="10"></circle>
                      <polyline points="12 6 12 12 16 14"></polyline>
                    </svg>
                    <span class="text-xs font-medium text-gray-600">Video Length:
                      <span class="text-xs font-semibold text-orange-500">{{ videoLength[0] }} min</span>
                    </span>
                  </div>

                </div>
                <Slider
                  v-model="videoLength"
                  :min="1"
                  :max="10"
                  :step="1"
                  class="w-[20%]"
                />
              </div>

              <button
                class="ai-assist-btn"
                @click="ideaSubMode === 'ideas' ? generateScriptFromIdea() : improveIdea()"
                :disabled="(ideaSubMode === 'ideas' ? isGeneratingScript : isImprovingIdea) || ideaText.trim().length < 50"
              >
                <i v-if="!(ideaSubMode === 'ideas' ? isGeneratingScript : isImprovingIdea)" class="fa-solid fa-wand-magic-sparkles"></i>
                <i v-else class="fa-solid fa-spinner fa-spin"></i>
                {{ (ideaSubMode === 'ideas' ? isGeneratingScript : isImprovingIdea)
                   ? 'Processing...'
                   : (ideaSubMode === 'ideas' ? 'Generate Script' : 'Repurpose Content') }}
              </button>
            </div>

            <!-- Character count validation -->
            <div v-if="ideaText.length > 0" class="mt-2 text-xs text-gray-600">
              <div class="flex justify-between">
                <span>{{ ideaText.length }} characters</span>
                <span v-if="ideaText.trim().length < 50" class="text-orange-600">
                  (minimum 50 characters required)
                </span>
              </div>
            </div>
          </div>

          <!-- Next Button with Scene Count Selection -->
          <div class="preview-action-buttons flex justify-end items-center gap-2 mt-4">
            <DropdownMenu v-if="projectMode === 'narrated_broll'">
              <DropdownMenuTrigger as-child>
                <Button class="preview-action-btn h-9 px-3 text-sm shadow-sm cursor-pointer">
                  <span style="display: flex; align-items: center; gap: 4px;">
                    {{ sceneAggregationMode === 'much less' ? 'Much Less Scenes' :
                       sceneAggregationMode === 'less' ? 'Less Scenes' :
                       sceneAggregationMode === 'more' ? 'More Scenes' :
                       sceneAggregationMode === 'most' ? 'Most Scenes' : 'Regular Scenes' }}
                  </span>
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="6 9 12 15 18 9"></polyline>
                  </svg>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent class="bg-black" align="start">
                <DropdownMenuItem
                  @click="sceneAggregationMode = 'much less'"
                  class="text-white"
                >
                  <span style="display: flex; align-items: center; gap: 6px;">
                    Much Less Scenes
                  </span>
                  <svg v-if="sceneAggregationMode === 'much less'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
                <DropdownMenuItem
                  @click="sceneAggregationMode = 'less'"
                  class="text-white"
                >
                  <span style="display: flex; align-items: center; gap: 6px;">
                    Less Scenes
                  </span>
                  <svg v-if="sceneAggregationMode === 'less'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
                <DropdownMenuItem
                  @click="sceneAggregationMode = 'regular'"
                  class="text-white"
                >
                  <span style="display: flex; align-items: center; gap: 6px;">
                    Regular Scenes
                  </span>
                  <svg v-if="sceneAggregationMode === 'regular'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
                <DropdownMenuItem
                  @click="sceneAggregationMode = 'more'"
                  class="text-white"
                >
                  <span style="display: flex; align-items: center; gap: 6px;">
                    More Scenes
                  </span>
                  <svg v-if="sceneAggregationMode === 'more'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
                <DropdownMenuItem
                  @click="sceneAggregationMode = 'most'"
                  class="text-white"
                >
                  <span style="display: flex; align-items: center; gap: 6px;">
                    Most Scenes
                  </span>
                  <svg v-if="sceneAggregationMode === 'most'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <Button
              class="preview-action-btn bg-linear-to-r from-yellow-400 to-red-500 cursor-pointer"
              @click="handleGenerateScenes"
              :disabled="!script || isGeneratingAudio || isGeneratingScenes || creationMode === 'ideaToVideo'"
              :title="projectMode === 'talking_scenes' ? (scenes.length > 0 ? 'Re-plan scenes' : 'Plan scenes') : (scenes.length > 0 ? 're-generate audio and scenes' : 'Generate audio and scenes')"
            >
              <i v-if="!isGeneratingAudio && !isGeneratingScenes" class="fa-solid fa-wand-magic-sparkles"></i>
              <i v-else class="fa-solid fa-spinner fa-spin"></i>
              {{
                isGeneratingAudio || isGeneratingScenes
                  ? 'Generating...'
                  : projectMode === 'talking_scenes'
                    ? (scenes.length > 0 ? 'Re-plan Scenes' : 'Plan Scenes')
                    : (scenes.length > 0 ? 'Re-generate All' : 'Next')
              }}
            </Button>

            <!-- Regenerate Scenes Only Button (without regenerating audio) -->
            <Button
              v-if="projectMode === 'narrated_broll' && (generatedAudio || scenes.length > 0)"
              class="preview-action-btn bg-blue-500 hover:bg-blue-600 cursor-pointer ml-2"
              @click="generateScenes"
              :disabled="!script || isGeneratingAudio || isGeneratingScenes || creationMode === 'ideaToVideo'"
              title="regenerate scenes only"
            >
              <i v-if="!isGeneratingScenes" class="fa-solid fa-film"></i>
              <i v-else class="fa-solid fa-spinner fa-spin"></i>
              {{ isGeneratingScenes ? 'Generating...' : 'Regenerate Scenes' }}
            </Button>

            <Button
              v-if="projectMode === 'talking_scenes' && scenes.length > 0"
              class="preview-action-btn bg-blue-500 hover:bg-blue-600 cursor-pointer ml-2"
              @click="generateTalkingSceneAudio"
              :disabled="isGeneratingSceneAudio || !canGenerateTalkingSceneAudio"
            >
              <i v-if="!isGeneratingSceneAudio" class="fa-solid fa-volume-high"></i>
              <i v-else class="fa-solid fa-spinner fa-spin"></i>
              {{ isGeneratingSceneAudio ? 'Generating Audio...' : (hasGeneratedSceneAudio ? 'Re-generate Scene Audio' : 'Generate Scene Audio') }}
            </Button>
          </div>
        </div>

        <!-- REMOTION PREVIEW (shown when Preview tab is active) -->
        <div v-else-if="showingPreview" class="w-full h-full flex flex-col" style="min-height:0;">
          <div
            v-if="remotionPreviewCode"
            ref="previewContainerRef"
            class="relative"
            style="flex:1; min-height:0; overflow:hidden;"
          >
            <RemotionPlayer
              ref="previewRemotionPlayerRef"
              :code="remotionPreviewCode"
              :current-frame="remotionCurrentFrame"
              style="width:100%; height:100%;"
              @update:current-frame="handlePreviewCurrentFrame"
              @player-play="handlePreviewPlayerPlay"
              @player-pause="handlePreviewPlayerPause"
            />
            <!-- Draggable text layer overlay -->
            <div class="absolute inset-0" style="pointer-events:none; overflow:hidden;">
              <!-- Inner div scaled to match the Remotion composition -->
              <div
                class="absolute"
                :style="{
                  width: previewCompW + 'px',
                  height: previewCompH + 'px',
                  left: '50%',
                  top: '50%',
                  transformOrigin: 'center center',
                  transform: `translate(-50%, -50%) scale(${previewScale})`,
                }"
              >
                <img
                  v-if="shouldShowWatermarkLogoPreview"
                  :src="watermarkLogoPreviewUrl"
                  alt=""
                  class="absolute select-none"
                  :style="watermarkLogoPreviewStyle"
                />
                <div
                  v-for="(tl, ti) in textLayers"
                  :key="tl.id"
                  v-show="(currentTime ?? 0) >= tl.startTime && (currentTime ?? 0) <= tl.endTime"
                  class="absolute cursor-move"
                  :style="{
                    left: tl.x + '%',
                    top: tl.y + '%',
                    transform: 'translate(-50%, -50%)',
                    fontSize: tl.fontSize + 'px',
                    color: tl.fontColor,
                    fontWeight: tl.fontWeight,
                    fontFamily: tl.fontFamily,
                    background: hexToRgba(tl.backgroundColor, tl.backgroundOpacity ?? 0),
                    padding: `${tl.boxPaddingY ?? 4}px ${tl.boxPaddingX ?? 12}px`,
                    borderRadius: `${tl.boxBorderRadius ?? 4}px`,
                    border: selectedTextLayerId === tl.id ? '2px solid #f97316' : '2px dashed rgba(255,255,255,0.5)',
                    boxShadow: selectedTextLayerId === tl.id ? '0 0 0 1px rgba(249,115,22,0.5)' : 'none',
                    pointerEvents: 'auto',
                    userSelect: 'none',
                    whiteSpace: 'nowrap',
                    lineHeight: '1.2',
                    zIndex: 20,
                  }"
                  @mousedown.prevent="startTextLayerDrag($event, ti)"
                  @click.stop="selectedTextLayerId = tl.id"
                >{{ tl.text }}</div>
              </div>
            </div>
          </div>
          <div v-else class="flex-1 flex items-center justify-center text-gray-400 text-sm">
            No scenes to preview
          </div>
          <!-- Full Timeline (replaces mini text track) -->
          <SimpleTimeline
            v-if="(scenes.length > 0 && hasAllImages) || generatedAudio"
            ref="previewTimelineRef"
            :scenes="scenes"
            :audio-duration="generatedAudio?.duration"
            :audio-url="generatedAudio?.url"
            :current-time="currentTime"
            :text-layers="textLayers"
            :selected-text-layer-id="selectedTextLayerId"
            class="flex-shrink-0"
            @update:scenes="handleScenesUpdate"
            @seek="handleSeek"
            @delete-scene="handleTimelineSceneDelete"
            @add-text-layer="addTextLayer"
            @update-text-layer="handleTimelineTextLayerUpdate"
            @select-text-layer="(id) => { selectedTextLayerId = id }"
            @play="handlePreviewTimelinePlay"
            @pause="handlePreviewTimelinePause"
          />
        </div>
        <!-- End REMOTION PREVIEW -->

        <!-- LARGE PREVIEW AREA (shown in storyboard layout mode when not editing) -->
        <div v-else-if="showStoryboardLayout && !editingScene" class="w-full h-full flex flex-col overflow-y-auto">
            <!-- Loading State (when generating audio or scenes) -->
            <div v-if="(isGeneratingAudio || isGeneratingScenes) && scenes.length === 0" class="text-center text-gray-400 p-2 lg:p-8">
              <div class="animate-spin rounded-full h-12 w-12 lg:h-24 lg:w-24 border-b-2 lg:border-b-4 border-orange-600 mx-auto mb-2 lg:mb-4"></div>
              <p class="text-base lg:text-2xl font-medium text-gray-700">
                {{ isGeneratingAudio ? 'Generating Voiceover' : 'Generating Scenes' }}
              </p>
              <p class="text-xs lg:text-sm mt-1 lg:mt-2 text-gray-500">
                {{ isGeneratingAudio ? 'Creating narration from your script...' : 'Please wait while we create your storyboard...' }}
              </p>
              <p class="text-xs lg:text-sm mt-1 lg:mt-2 text-gray-500">
                {{ 'Please do not refresh page.' }}
              </p>

              <!-- Progress bar (show for both audio and scenes) -->
              <div class="w-full max-w-xs bg-gray-200 rounded-full h-2 mt-4 mx-auto">
                <div
                  class="h-2 rounded-full transition-all duration-500 bg-orange-600"
                  :style="{ width: `${isGeneratingAudio ? audioGenerationProgress : sceneGenerationProgress}%` }"
                ></div>
              </div>
              <span class="text-xs text-gray-500 mt-2 block">{{ isGeneratingAudio ? audioGenerationProgress : sceneGenerationProgress }}%</span>
            </div>

            <!-- Gallery View -->
            <div v-else-if="showingGallery" class="w-full h-full flex flex-col">
              <ImageGallery
                ref="galleryViewRef"
                :images="imageGenerationStore.gallery.images"
                :loading="imageGenerationStore.gallery.loading"
                :folders="imageGenerationStore.folders.folders"
                :selected-folder-id="imageGenerationStore.folders.selectedFolderId"
                :uncategorized-count="imageGenerationStore.getUncategorizedCount"
                :folders-loading="imageGenerationStore.folders.loading"
                :show-folders="true"
                @select-folder="imageGenerationStore.setSelectedFolder"
                @create-folder="handleCreateFolder"
                @rename-folder="handleRenameFolder"
                @delete-folder="handleDeleteFolder"
                @move-image-to-folder="handleMoveImage"
                @move-images-to-folder="handleMoveImages"
                @image-click="handleGalleryViewImageClick"
                @image-error="handleGalleryMediaError"
                @load-more="loadMoreGalleryImages"
                @delete-image="handleDeleteImage"
                @batch-delete-images="handleBatchDeleteImages"
              />
            </div>

            <!-- Video Loading State -->
            <div v-else-if="showingFinalVideo && isGeneratingVideo && !finalGeneratedVideo" class="w-full h-full flex items-center justify-center">
              <div class="text-center text-gray-400 p-2 lg:p-8">
                <div class="animate-spin rounded-full h-12 w-12 lg:h-24 lg:w-24 border-b-2 lg:border-b-4 border-orange-600 mx-auto mb-2 lg:mb-4"></div>
                <p class="text-base lg:text-2xl font-medium text-gray-700">Generating Video</p>
                <p class="text-xs lg:text-sm mt-1 lg:mt-2 text-gray-500">Please wait while we render your video...</p>
                <p class="text-xs lg:text-sm mt-1 lg:mt-2 text-gray-500">This may take several minutes</p>
              </div>
            </div>

            <!-- Final Generated Video Preview -->
            <div v-else-if="showingFinalVideo && finalGeneratedVideo" class="w-full h-full flex flex-col p-2 lg:p-3">
              <div class="flex items-center justify-between mb-2 lg:mb-4">
                <div class="flex items-center gap-2 lg:gap-3">
                  <span class="text-base lg:text-2xl font-bold text-gray-800">Generated Video</span>
                </div>
                <button
                  @click="downloadVideo"
                  :disabled="isDownloadingVideo"
                  class="px-2 py-1 lg:px-4 lg:py-2 bg-orange-300 hover:bg-orange-400 text-white rounded-md transition-colors flex items-center gap-1 lg:gap-2 text-xs lg:text-base disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <i v-if="!isDownloadingVideo" class="fa-solid fa-download"></i>
                  <i v-else class="fa-solid fa-spinner fa-spin"></i>
                  <span>{{ isDownloadingVideo ? 'Downloading...' : 'Download' }}</span>
                </button>
              </div>

              <div class="rounded-lg relative lg:max-h-[65vh] bg-black overflow-hidden flex items-center justify-center">
                <!-- Blurred background -->
                <video
                  :src="finalGeneratedVideo.url"
                  class="absolute inset-0 w-full h-full object-cover blur-2xl opacity-50"
                  muted
                  loop
                  autoplay
                ></video>
                <!-- Sharp foreground video -->
                  <video
                    :src="finalGeneratedVideo.url"
                    controls
                    autoplay
                    class="relative z-10 w-auto h-full object-contain"
                    style="max-height: 65vh;"
                  >
                    Your browser does not support the video tag.
                  </video>
              </div>

              <div class="mt-1">
                <div class="text-sm text-gray-600">
                  <span v-if="finalGeneratedVideo.duration">Duration: {{ finalGeneratedVideo.duration }}s</span>
                </div>
              </div>
            </div>

            <div v-else-if="showingFinalVideo" class="w-full h-full flex items-center justify-center">
              <div class="text-center text-gray-500 p-4 lg:p-8 max-w-md">
                <i class="fa-solid fa-video-slash text-4xl lg:text-6xl text-gray-300 mb-4"></i>
                <p class="text-base lg:text-xl font-semibold text-gray-700">No final video found</p>
                <p class="text-xs lg:text-sm mt-2 text-gray-500">
                  This project has audio and storyboard data, but no completed render is linked to it yet.
                </p>
                <button
                  @click="generateVideo"
                  :disabled="isGeneratingVideo || !hasAllImages"
                  class="mt-4 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-md text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {{ isGeneratingVideo ? 'Generating...' : 'Generate Video' }}
                </button>
              </div>
            </div>

            <!-- Thumbnail View -->
            <div v-else-if="showingThumbnail" class="w-full h-full flex flex-col p-2 lg:p-3">
              <div class="flex items-center justify-between mb-2 lg:mb-4">
                <div class="flex items-center gap-2 lg:gap-3">
                  <span class="text-base lg:text-2xl font-bold text-gray-800">Project Thumbnail</span>
                  <span v-if="thumbnailImages.length" class="text-xs lg:text-sm text-gray-500">{{ thumbnailImages.length }} generated</span>
                </div>
              </div>

              <div class="flex-1 flex flex-col lg:flex-row gap-2 lg:gap-4 min-h-0 lg:items-start">
                <!-- LEFT: Thumbnail Preview Area -->
                <div class="flex-1 flex flex-col min-w-0 bg-gray-100 rounded-lg relative min-h-[220px] lg:min-h-0 overflow-hidden lg:max-h-[65vh]">
                  <div v-if="isGeneratingThumbnail" class="w-full h-full flex flex-col items-center justify-center text-gray-400 p-2">
                    <div class="animate-spin rounded-full h-10 w-10 lg:h-20 lg:w-20 border-b-2 lg:border-b-4 border-orange-600 mb-2 lg:mb-4"></div>
                    <p class="text-sm lg:text-xl font-medium text-gray-700">Generating Thumbnail</p>
                    <p class="text-xs lg:text-sm mt-1 lg:mt-2 text-gray-500">Creating a thumbnail image for this project...</p>
                  </div>

                  <div v-else-if="selectedThumbnail?.url" class="w-full h-full flex flex-col">
                    <div class="flex-1 flex items-center justify-center min-h-0 rounded-lg overflow-hidden relative">
                      <div
                        class="absolute inset-0 w-full h-full bg-cover bg-center blur-2xl opacity-50"
                        :style="{ backgroundImage: `url(${selectedThumbnail.url})` }"
                      ></div>
                      <img
                        :src="selectedThumbnail.url"
                        alt="Project thumbnail preview"
                        class="max-w-full relative z-10"
                        style="object-fit: contain; max-height: 60vh;"
                      />
                    </div>
                    <div class="mt-1 lg:mt-2 px-1">
                      <p class="text-sm text-gray-700 line-clamp-2">{{ selectedThumbnail.prompt }}</p>
                    </div>
                  </div>

                  <div v-else class="w-full h-full flex flex-col items-center justify-center text-gray-400 p-2">
                    <svg class="w-12 h-12 lg:w-20 lg:h-20 mb-2 lg:mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    <p class="text-sm lg:text-xl font-medium">No Thumbnail Generated</p>
                    <p class="text-xs lg:text-sm mt-1 lg:mt-2">Generate a thumbnail image for this project</p>
                  </div>
                </div>

                <!-- RIGHT: Thumbnail Generation + Generated Thumbnails -->
                <div class="max-lg:w-full lg:block w-120 flex-shrink-0">
                  <div class="flex flex-col h-full rounded-lg border-0 border-gray-200 overflow-hidden">
                    <div class="flex-1 overflow-y-auto pl-0 lg:pl-4 pt-0">
                      <div class="space-y-3 text-sm">
                        <div>
                          <label class="text-md font-semibold text-black mb-2">Image Generation</label>
                          <div style="position: relative;">
                            <textarea
                              v-model="thumbnailPrompt"
                              class="w-full p-2 pb-14 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-orange-500 focus:border-transparent resize-none bg-gray-100 opacity-70"
                              rows="8"
                              placeholder="Describe the project thumbnail..."
                            />
                            <div class="absolute bottom-3 right-2 flex flex-wrap gap-1 justify-end">
                              <DropdownMenu>
                                <DropdownMenuTrigger as-child>
                                  <Button class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0">
                                    <span class="flex items-center truncate max-w-[70px]">
                                      {{ imageGenerationModels.find(m => m.value === imageGenerationModel)?.label }}
                                    </span>
                                    <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                      <polyline points="6 9 12 15 18 9"></polyline>
                                    </svg>
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent class="w-56 bg-black" align="start">
                                  <DropdownMenuItem
                                    v-for="model in imageGenerationModels"
                                    :key="model.value"
                                    @click="imageGenerationModel = model.value"
                                    class="text-white cursor-pointer"
                                  >
                                    {{ model.label }}
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                              <DropdownMenu>
                                <DropdownMenuTrigger as-child>
                                  <Button class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0">
                                    <span class="flex items-center truncate max-w-[42px]">
                                      {{ imageAspectRatio }}
                                    </span>
                                    <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                      <polyline points="6 9 12 15 18 9"></polyline>
                                    </svg>
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent class="bg-black" align="start">
                                  <DropdownMenuItem
                                    v-for="ratio in imageAspectRatios"
                                    :key="ratio.value"
                                    @click="imageAspectRatio = ratio.value"
                                    class="text-white"
                                  >
                                    <span>{{ ratio.label }}</span>
                                    <svg v-if="imageAspectRatio === ratio.value" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                      <polyline points="20 6 9 17 4 12"></polyline>
                                    </svg>
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                              <Button
                                @click="handleGenerateThumbnail"
                                :disabled="isGeneratingThumbnail || !thumbnailPrompt.trim()"
                                class="h-7 px-1.5 text-[0.7rem] shadow-sm bg-linear-to-r from-yellow-400 to-red-500 cursor-pointer flex-shrink-0 hover:-translate-y-1"
                              >
                                <span v-if="isGeneratingThumbnail" class="flex items-center gap-0.5">
                                  <i class="fa-solid fa-spinner fa-spin text-[0.65rem]"></i>
                                  Generating...
                                </span>
                                <span v-else class="flex items-center gap-0.5">
                                  <i class="fa-solid fa-wand-magic-sparkles text-[0.65rem]"></i>
                                  Generate
                                </span>
                              </Button>
                            </div>
                          </div>
                        </div>

                        <div class="pt-2 border-t border-gray-200">
                          <div class="flex items-center justify-between mb-2">
                            <label class="text-md font-semibold text-black">Generated Thumbnails</label>
                            <span class="text-xs text-gray-500">{{ thumbnailImages.length }}</span>
                          </div>
                          <div v-if="thumbnailImages.length" class="grid grid-cols-2 gap-2">
                            <button
                              v-for="(thumbnail, index) in thumbnailImages"
                              :key="thumbnail.id"
                              type="button"
                              @click="handleSelectThumbnail(index)"
                              class="group overflow-hidden rounded-lg border bg-gray-100 text-left transition-all hover:border-orange-300"
                              :class="selectedThumbnailIndex === index ? 'ring-2 ring-orange-500 border-orange-400' : 'border-gray-200'"
                            >
                              <div class="w-full overflow-hidden bg-gray-100" :class="getAspectRatioFrameClass(thumbnail.aspectRatio)">
                                <img :src="thumbnail.url" :alt="`Thumbnail ${index + 1}`" class="h-full w-full object-cover transition-transform group-hover:scale-105" />
                              </div>
                              <div class="p-2">
                                <p class="line-clamp-2 text-[11px] text-gray-600">{{ thumbnail.prompt }}</p>
                              </div>
                            </button>
                          </div>
                          <div v-else class="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 text-center text-xs text-gray-500">
                            No thumbnails yet. Generate one above.
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- No Scene Selected -->
            <div v-else-if="selectedSceneForPreview === null && scenes.length > 0" class="text-center text-gray-400 p-2 lg:p-8">
              <svg class="mx-auto h-12 w-12 lg:h-24 lg:w-24 mb-2 lg:mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <p class="text-base lg:text-2xl font-medium">No Scene Selected</p>
              <p class="text-xs lg:text-sm mt-1 lg:mt-2">Click on a scene in the storyboard to view it here</p>
            </div>

            <!-- Selected Scene Preview -->
            <div v-else-if="selectedSceneForPreview !== null && scenes[selectedSceneForPreview]" class="w-full h-full flex flex-col p-2 lg:p-3">
              

              <!-- Preview Content -->
              <div class="flex-1 flex flex-col lg:flex-row gap-2 lg:gap-4 min-h-0 lg:items-start">
              <!-- LEFT: Media Preview Area -->
              <div class="flex-1 flex flex-col min-w-0 bg-gray-100 rounded-lg relative min-h-[180px] lg:min-h-0 overflow-visible lg:max-h-[65vh]">
                <!-- Action Buttons (Top-right corner) -->
                <div class="absolute top-1 right-1 lg:top-2 lg:right-2 z-50 flex items-center gap-1 lg:gap-2">
                  <!-- Edit Button (Mobile only) -->
                  <button
                    @click="showSceneDetailsModal = true"
                    class="max-lg:flex lg:!hidden bg-orange-600 hover:bg-orange-700 text-white rounded-md px-1.5 py-0.5 shadow-md transition-all duration-200 hover:scale-105 items-center gap-0.5 text-[10px]"
                    title="Edit scene details"
                  >
                    <svg class="w-3 h-3 lg:w-3.5 lg:h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                    <span class="font-medium">Edit</span>
                  </button>

                  <!-- Update Button -->
                  <button
                    v-if="selectedSceneForPreview !== null && (scenes[selectedSceneForPreview]?.generatedImage || scenes[selectedSceneForPreview]?.animatedVideo)"
                    @click="openGalleryReplacement(selectedSceneForPreview)"
                    class="bg-linear-to-r from-yellow-400 to-red-500 cursor-pointer text-white rounded-md px-1.5 py-0.5 lg:px-2 lg:py-1 shadow-md transition-all duration-200 hover:scale-105 flex items-center gap-0.5 lg:gap-1 text-[10px] lg:text-lg"
                    title="Replace image/video"
                  >
                    <svg class="w-3 h-3 lg:w-3.5 lg:h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    <span class="font-medium">Replace</span>
                  </button>
                </div>

                <!-- Loading State (Priority 1 - highest priority) -->
                <div v-if="scenes[selectedSceneForPreview]?.isGenerating || isGeneratingSceneDetailsImage || isGeneratingSceneDetailsVideo || isAnimatingImage[selectedSceneForPreview]" class="w-full h-full flex flex-col items-center justify-center text-gray-400 p-2">
                  <div class="animate-spin rounded-full h-10 w-10 lg:h-20 lg:w-20 border-b-2 lg:border-b-4 border-orange-600 mb-2 lg:mb-4"></div>
                  <p class="text-sm lg:text-xl font-medium text-gray-700">
                    {{ (scenes[selectedSceneForPreview]?.isGenerating || isGeneratingSceneDetailsImage) ? 'Generating Image' : 'Generating Video' }}
                  </p>
                  <p class="text-xs lg:text-sm mt-1 lg:mt-2 text-gray-500">
                    {{ (scenes[selectedSceneForPreview]?.isGenerating || isGeneratingSceneDetailsImage) ? 'Creating your scene image...' : 'Creating your animated video...' }}
                  </p>
                  <!-- Progress bar for image generation -->
                  <div v-if="scenes[selectedSceneForPreview]?.isGenerating && scenes[selectedSceneForPreview]?.generationProgress !== undefined" class="w-full max-w-xs bg-gray-200 rounded-full h-1.5 lg:h-2 mt-2 lg:mt-4">
                    <div
                      class="bg-blue-600 h-1.5 lg:h-2 rounded-full transition-all duration-300"
                      :style="{ width: `${scenes[selectedSceneForPreview].generationProgress}%` }"
                    ></div>
                  </div>
                  <span v-if="scenes[selectedSceneForPreview]?.isGenerating && scenes[selectedSceneForPreview]?.generationProgress !== undefined" class="text-[10px] lg:text-xs text-gray-500 mt-1 lg:mt-2">
                    {{ scenes[selectedSceneForPreview].generationProgress }}%
                  </span>
                </div>

                <!-- Animated Video (Priority 2) -->
                <div v-else-if="selectedSceneForPreview !== null && scenes[selectedSceneForPreview].animatedVideo?.url" class="w-full h-full flex flex-col">
                <div class="flex items-center justify-between mb-2 lg:mb-4">
                  <!-- <div class="flex items-center gap-3">
                    <svg class="w-6 h-6 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                      <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                    </svg>
                    <span class="text-lg font-semibold text-gray-700">Animated Video</span>
                  </div> -->
                  <div class="flex items-center gap-2">
                    <!-- <span class="text-sm text-gray-500 bg-gray-200 px-3 py-1 rounded-full">
                      {{ scenes[selectedSceneForPreview].animatedVideo?.duration }}s
                    </span> -->
                    <!-- Replace Base Image Actions -->
                    <!-- <button
                      @click="openGalleryReplacement(selectedSceneForPreview)"
                      class="px-3 py-1 text-xs bg-gray-600 hover:bg-gray-700 text-white rounded-md transition-colors flex items-center gap-1 cursor-pointer"
                      title="Replace base image from gallery"
                    >
                      <i class="fa-regular fa-images"></i>
                      Gallery
                    </button>
                    <button
                      @click="sceneIndexForImageReplacement = selectedSceneForPreview; previewUploadInput?.click()"
                      class="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors flex items-center gap-1 cursor-pointer"
                      title="Replace base image from computer"
                    >
                      <i class="fa-solid fa-upload"></i>
                      Upload
                    </button> -->
                  </div>
                </div>
                <div class="flex-1 flex items-center justify-center min-h-0 rounded-lg overflow-hidden relative">
                  <!-- Blurred background -->
                  <video
                    :src="scenes[selectedSceneForPreview].animatedVideo?.url"
                    class="absolute inset-0 w-full h-full object-cover blur-2xl opacity-50"
                    muted
                    loop
                    autoplay
                  ></video>
                  <!-- Sharp foreground video -->
                  <div
                    class="relative z-10 inline-flex max-w-full"
                    :style="{
                      maxHeight: (scenes[selectedSceneForPreview].generatedImage?.height || 0) > (scenes[selectedSceneForPreview].generatedImage?.width || 0) ? '60vh' : '100%'
                    }"
                  >
                    <video
                      :src="scenes[selectedSceneForPreview].animatedVideo?.url"
                      controls
                      autoplay
                      loop
                      class="max-w-full"
                      :style="{
                        objectFit: 'contain',
                        maxHeight: 'inherit'
                      }"
                    ></video>
                    <img
                      v-if="shouldShowWatermarkLogoPreview"
                      :src="watermarkLogoPreviewUrl"
                      alt=""
                      class="absolute select-none"
                      :style="watermarkLogoPreviewStyle"
                    />
                  </div>
                </div>
              </div>

              <!-- Generated Image (Priority 2) -->
              <div v-else-if="selectedSceneForPreview !== null && scenes[selectedSceneForPreview].generatedImage?.url" class="w-full h-full flex flex-col ">
                
                <div class="flex-1 flex items-center justify-center min-h-0 rounded-lg overflow-hidden relative ">
                  <!-- Blurred background -->
                  <div
                    class="absolute inset-0 w-full h-full bg-cover bg-center blur-2xl opacity-50"
                    :style="{ backgroundImage: `url(${scenes[selectedSceneForPreview].generatedImage?.url})` }"
                  ></div>
                  <!-- Sharp foreground image -->
                  <div
                    class="relative z-10 inline-flex max-w-full"
                    :style="{
                      maxHeight: (scenes[selectedSceneForPreview].generatedImage?.height || 0) > (scenes[selectedSceneForPreview].generatedImage?.width || 0) ? '60vh' : '100%'
                    }"
                  >
                    <img
                      :src="scenes[selectedSceneForPreview].generatedImage?.url"
                      alt="Scene preview"
                      class="max-w-full"
                      :style="{
                        objectFit: 'contain',
                        maxHeight: 'inherit'
                      }"
                    />
                    <img
                      v-if="shouldShowWatermarkLogoPreview"
                      :src="watermarkLogoPreviewUrl"
                      alt=""
                      class="absolute select-none"
                      :style="watermarkLogoPreviewStyle"
                    />
                  </div>
                </div>

                <!-- Scene Description Header -->
                <div class="mt-1 lg:mt-2">
                  <p class="text-md lg:text-md text-black">
                    {{ scenes[selectedSceneForPreview]?.description || 'No description' }}
                  </p>
                </div>


                
              </div>

              
              

              <!-- No Media Generated -->
              <div v-else class="w-full h-full flex flex-col items-center justify-center text-gray-400 p-2">
                <svg class="w-12 h-12 lg:w-20 lg:h-20 mb-2 lg:mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                <p class="text-sm lg:text-xl font-medium">No Media Generated</p>
                <p class="text-xs lg:text-sm mt-1 lg:mt-2 mb-2 lg:mb-4">Get started by adding an image to this scene</p>

                <!-- Action Buttons -->
                <div class="flex flex-col sm:flex-row gap-2 lg:gap-3 mt-2 lg:mt-4">
                  <button
                    @click="openGalleryReplacement(selectedSceneForPreview)"
                    class="px-2 py-1 lg:px-4 lg:py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md transition-colors flex items-center gap-1 lg:gap-2 text-xs lg:text-sm"
                  >
                    <i class="fa-regular fa-images"></i>
                    <span class="hidden sm:inline">Select from Gallery</span>
                    <span class="sm:hidden">Gallery</span>
                  </button>
                  <button
                    @click="sceneIndexForImageReplacement = selectedSceneForPreview; previewUploadInput?.click()"
                    class="px-2 py-1 lg:px-4 lg:py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors flex items-center gap-1 lg:gap-2 text-xs lg:text-sm"
                  >
                    <i class="fa-solid fa-upload"></i>
                    <span class="hidden sm:inline">Upload from Computer</span>
                    <span class="sm:hidden">Upload</span>
                  </button>
                </div>
              </div>
              </div>
              <!-- End LEFT: Media Preview Area -->

              <!-- RIGHT: Scene Details Sidebar (Desktop Only) -->
              <div class="max-lg:hidden lg:block w-120 flex-shrink-0">
                <div class="flex flex-col h-full rounded-lg border-0 border-gray-200 overflow-hidden">
                <!-- <div class="p-2 lg:p-4 border-b border-gray-200 bg-gray-50">
                  <h3 class="text-xs lg:text-sm font-semibold text-gray-700">Scene Details</h3>
                </div> -->
                <div class="flex-1 overflow-y-auto pl-2 lg:pl-4 pt-0">
                <div class="space-y-2 lg:space-y-3 text-sm">
                  <!-- Editable Prompt -->
                  <div class="">
                    <label class="text-md font-semibold text-black mb-2">Image Generation</label>
                    <div style="position: relative;">
                      <textarea
                        v-model="sceneDetailsPrompt"
                        class="w-full p-2 pb-20 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-orange-500 focus:border-transparent resize-none bg-gray-100 opacity-70"
                        rows="12"
                        placeholder="Enter scene description..."
                      />
                      <!-- Reference Image Card (Bottom-left corner) -->
                      <div class="absolute bottom-2 left-2 z-10 w-20">
                        <label class="text-black text-[9px] mb-0.5 block">Reference</label>
                        <div
                          class="relative w-full aspect-video bg-gray-50 rounded border-dashed border cursor-pointer hover:border-orange-400"
                          @click="openImageReferenceSelector"
                        >
                          <img v-if="imageReferenceImage" :src="imageReferenceImage.url" class="w-full h-full object-cover rounded" />
                          <div v-else class="flex flex-col items-center justify-center h-full text-gray-400 text-[8px]">
                            <i class="fa-solid fa-plus text-[8px] mb-0.5"></i>
                            <span>Select</span>
                          </div>
                          <button
                            v-if="imageReferenceImage"
                            @click.stop="clearImageReference"
                            class="absolute top-0.5 right-0.5 w-3 h-3 bg-black/50 rounded-full text-white flex items-center justify-center"
                            title="Clear reference image"
                          >
                            <i class="fa-solid fa-times text-[6px]"></i>
                          </button>
                        </div>
                      </div>
                      <!-- Floating Buttons Container -->
                      <div class="absolute bottom-3 left-24 right-2 flex flex-wrap gap-1 justify-end">
                        <!-- Model Dropdown -->
                        <DropdownMenu>
                          <DropdownMenuTrigger as-child>
                            <Button class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0">
                              <span class="flex items-center truncate max-w-[45px]">
                                {{ imageGenerationModels.find(m => m.value === imageGenerationModel)?.label }}
                              </span>
                              <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="6 9 12 15 18 9"></polyline>
                              </svg>
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent
                          class="w-56 bg-black"
                            align="start"
                          >
                            <DropdownMenuItem
                              v-for="model in imageGenerationModels"
                              :key="model.value"
                              @click="imageGenerationModel = model.value"
                              :class="{
                                'text-white cursor-pointer': true
                              }"
                            >
                              <span style="display: flex; align-items: center; gap: 6px;">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                                  <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
                                  <line x1="12" y1="22.08" x2="12" y2="12"></line>
                                </svg>
                                {{ model.label }}
                              </span>
                              <svg v-if="imageGenerationModel === model.value" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                <polyline points="20 6 9 17 4 12"></polyline>
                              </svg>
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>

                        <!-- Aspect Ratio Dropdown -->
                        <DropdownMenu>
                          <DropdownMenuTrigger as-child>
                            <Button class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0">
                              <span class="flex items-center gap-0.5">
                                {{ imageAspectRatio }}
                              </span>
                              <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="6 9 12 15 18 9"></polyline>
                              </svg>
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent
                            class="bg-black"
                            align="start"
                          >
                            <DropdownMenuItem
                              v-for="ratio in imageAspectRatios"
                              :key="ratio.value"
                              @click="imageAspectRatio = ratio.value"
                              class="text-white"
                            >
                              <span style="display: flex; align-items: center; gap: 6px;">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                                </svg>
                                {{ ratio.value }}
                              </span>
                              <svg v-if="imageAspectRatio === ratio.value" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                <polyline points="20 6 9 17 4 12"></polyline>
                              </svg>
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>

                        <!-- Generate Image Button -->
                        <Button
                          @click="handleGenerateImageFromSceneDetails"
                          :disabled="isGeneratingSceneDetailsImage || !sceneDetailsPrompt.trim()"
                          class="h-7 px-1.5 text-[0.7rem] shadow-sm bg-linear-to-r from-yellow-400 to-red-500 cursor-pointer flex-shrink-0 hover:-translate-y-1"
                        >
                          <span v-if="isGeneratingSceneDetailsImage" class="flex items-center gap-0.5">
                            <i class="fa-solid fa-spinner fa-spin text-[0.65rem]"></i>
                            <span class="hidden sm:inline">Generating...</span>
                            <span class="sm:hidden">Gen...</span>
                          </span>
                          <span v-else class="flex items-center gap-0.5">
                            <i class="fa-solid fa-wand-magic-sparkles text-[0.65rem]"></i>
                            <span class="flex items-center gap-1">
                              Generate
                            </span>
                          </span>
                        </Button>
                      </div>
                    </div>
                  </div>

                  <!-- Reference Characters Section -->
                  <div v-if="selectedSceneCharacters.length > 0" class="pt-1 border-t border-gray-200">
                    <h4 class="text-xs font-semibold text-gray-700 mb-2">Reference Characters</h4>
                    <div class="flex flex-wrap gap-2">
                      <div
                        v-for="character in selectedSceneCharacters"
                        :key="character.id"
                        class="group relative inline-flex items-center gap-2 px-3 py-2 pr-8 rounded-lg bg-purple-50 border border-purple-200 hover:bg-purple-100 transition-colors"
                      >
                        <div class="flex items-center gap-2">
                          <div v-if="character.reference_images && character.reference_images.length > 0" class="flex-shrink-0">
                            <img
                              :src="character.reference_images[0].image_url"
                              :alt="character.name"
                              class="w-8 h-8 rounded-full object-cover border border-purple-300"
                            />
                          </div>
                          <div v-else class="flex-shrink-0 w-8 h-8 rounded-full bg-purple-200 flex items-center justify-center border border-purple-300">
                            <svg class="w-4 h-4 text-purple-600" fill="currentColor" viewBox="0 0 24 24">
                              <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                            </svg>
                          </div>
                          <div class="flex flex-col">
                            <span class="text-xs font-medium text-purple-900">{{ character.name }}</span>
                            <span v-if="character.reference_images && character.reference_images.length > 0" class="text-[10px] text-purple-600">
                              {{ character.reference_images.length }} reference{{ character.reference_images.length > 1 ? 's' : '' }}
                            </span>
                          </div>
                        </div>
                        <!-- Remove Button -->
                        <button
                          @click="removeCharacterFromScene(character.id)"
                          class="absolute top-1 right-1 w-5 h-5 flex items-center justify-center rounded-full bg-red-500 text-white opacity-0 group-hover:opacity-100 hover:bg-red-600 transition-all"
                          title="Remove character"
                        >
                          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    </div>
                    <p class="text-[10px] text-gray-500 mt-2">
                      These characters will be included in image generation
                    </p>
                  </div>

                  <!-- Video Generation Section -->
                  <div class="pt-1">
                    <!-- <h4 class="text-md font-semibold text-black mb-2">Video Generation</h4> -->

                    <!-- Animation Prompt -->
                    <div>
                      <label class="text-md font-semibold text-black mb-2">Scene to Video</label>
                      <div style="position: relative;">
                        <textarea
                          v-model="sceneDetailsAnimationPrompt"
                          class="w-full p-2 pb-20 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none bg-gray-100 opacity-70"
                          rows="7"
                          placeholder="Describe the animation (e.g., camera slowly zooms in...)"
                        />

                        <!-- Start/End Frame Cards (Bottom-left corner) -->
                        <div class="absolute bottom-2 left-2 flex gap-2 z-10">
                          <!-- Start Frame (interactive) -->
                          <div class="w-20">
                            <label class="text-black text-[9px] mb-0.5 block">Start Frame</label>
                            <div class="relative w-full aspect-video bg-gray-50 rounded border-dashed border cursor-pointer hover:border-blue-400"
                                 @click="openStartFrameSelector">
                              <img v-if="startFrameImage" :src="startFrameImage.url" class="w-full h-full object-cover rounded" />
                              <img v-else-if="scenes[selectedSceneForPreview]?.generatedImage?.url"
                                   :src="scenes[selectedSceneForPreview]?.generatedImage?.url"
                                   class="w-full h-full object-cover rounded opacity-70" />
                              <div v-else class="flex flex-col items-center justify-center h-full text-gray-400 text-[8px]">
                                <i class="fa-solid fa-plus text-[8px] mb-0.5"></i>
                                <span>Select</span>
                              </div>
                              <!-- Clear button -->
                              <button v-if="startFrameImage" @click.stop="clearStartFrame"
                                      class="absolute top-0.5 right-0.5 w-3 h-3 bg-black/50 rounded-full text-white flex items-center justify-center">
                                <i class="fa-solid fa-times text-[6px]"></i>
                              </button>
                              <!-- Indicator -->
                              <div v-if="!startFrameImage && scenes[selectedSceneForPreview]?.generatedImage?.url"
                                   class="absolute bottom-0.5 left-0.5 bg-black/50 rounded px-0.5 text-white text-[7px]">
                                Gen
                              </div>
                            </div>
                          </div>

                          <!-- End Frame (interactive) -->
                          <div class="w-20">
                            <label class="text-black text-[9px] mb-0.5 block whitespace-nowrap">End Frame (optional)</label>
                            <div class="relative w-full aspect-video bg-gray-50 rounded border-dashed border cursor-pointer hover:border-blue-400"
                                 @click="openEndFrameSelector">
                              <img v-if="endFrameImage" :src="endFrameImage.url" class="w-full h-full object-cover rounded" />
                              <div v-else class="flex flex-col items-center justify-center h-full text-gray-400 text-[8px]">
                                <i class="fa-solid fa-plus text-[8px] mb-0.5"></i>
                                <span>Add</span>
                              </div>
                              <!-- Clear button -->
                              <button v-if="endFrameImage" @click.stop="clearEndFrame"
                                      class="absolute top-0.5 right-0.5 w-3 h-3 bg-black/50 rounded-full text-white flex items-center justify-center">
                                <i class="fa-solid fa-times text-[6px]"></i>
                              </button>
                            </div>
	                            <p v-if="endFrameImage && !supportsEndFrameVideoModel(sceneDetailsVideoModel)"
	                               class="text-[7px] text-amber-600 mt-0.5">
	                              Wan, Veo, Seedance 2 or Kling 3 only
	                            </p>
                          </div>
                        </div>

                        <!-- Floating Buttons Container (Bottom-right corner) -->
                        <div class="absolute bottom-3 right-2 flex flex-wrap gap-1 justify-end">
                          <!-- Video Model Dropdown -->
                          <DropdownMenu>
                            <DropdownMenuTrigger as-child>
                              <Button
                                class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0"
                              >
                                <span class="flex items-center gap-0.5 truncate max-w-[50px]">
                                  {{ getVideoModelLabel(sceneDetailsVideoModel) }}
                                </span>
                                <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                  <polyline points="6 9 12 15 18 9"></polyline>
                                </svg>
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent class="bg-black" align="start">
	                              <DropdownMenuItem
	                                @click="sceneDetailsVideoModel = 'wan-video/wan-2.2-i2v-fast'"
	                                class="text-white"
	                              >
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M23 7l-7 5 7 5V7z"></path>
                                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                                  </svg>
                                  Wan Video (Fast)
                                </span>
                                <svg v-if="sceneDetailsVideoModel === 'wan-video/wan-2.2-i2v-fast'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
	                                  <polyline points="20 6 9 17 4 12"></polyline>
	                                </svg>
	                              </DropdownMenuItem>
                              <DropdownMenuItem
                                @click="sceneDetailsVideoModel = 'gemini-omni-flash-preview'; sceneDetailsVideoDuration = 8; sceneDetailsVideoResolution = '720p'"
                                class="text-white"
                              >
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M23 7l-7 5 7 5V7z"></path>
                                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                                    <path d="M12 2l1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5L12 2z" transform="translate(8 -1) scale(.55)"></path>
                                  </svg>
                                  Gemini Omni Flash
                                </span>
                                <svg v-if="sceneDetailsVideoModel === 'gemini-omni-flash-preview'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                @click="sceneDetailsVideoModel = 'veo-3.1-fast-generate-preview'; sceneDetailsVideoDuration = 4"
                                class="text-white"
                              >
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M23 7l-7 5 7 5V7z"></path>
                                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                                    <path d="M4 4l2 4 4 2-4 2-2 4-2-4-4-2 4-2 2-4z" transform="translate(12 -2) scale(.45)"></path>
                                  </svg>
                                  Google Veo 3.1 Fast
                                </span>
                                <svg v-if="sceneDetailsVideoModel === 'veo-3.1-fast-generate-preview'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                @click="sceneDetailsVideoModel = 'kwaivgi/kling-v2.1'; sceneDetailsVideoDuration = 5; sceneDetailsVideoResolution = '720p'"
                                class="text-white"
                              >
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M23 7l-7 5 7 5V7z"></path>
                                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                                  </svg>
                                  Kling 2.1
                                </span>
                                <svg v-if="sceneDetailsVideoModel === 'kwaivgi/kling-v2.1'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                @click="sceneDetailsVideoModel = 'kwaivgi/kling-v2.6'; sceneDetailsVideoDuration = 5; sceneDetailsVideoResolution = '720p'"
                                class="text-white"
                              >
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M23 7l-7 5 7 5V7z"></path>
                                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                                  </svg>
                                  Kling 2.6
                                </span>
                                <svg v-if="sceneDetailsVideoModel === 'kwaivgi/kling-v2.6'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                @click="sceneDetailsVideoModel = 'kwaivgi/kling-v3-video'; sceneDetailsVideoDuration = 3; sceneDetailsVideoResolution = '720p'"
                                class="text-white"
                              >
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M23 7l-7 5 7 5V7z"></path>
                                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                                    <path d="M12 2l1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5L12 2z" transform="translate(8 -1) scale(.55)"></path>
                                  </svg>
                                  Kling 3
                                </span>
                                <svg v-if="sceneDetailsVideoModel === 'kwaivgi/kling-v3-video'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
	                              <DropdownMenuSub>
                                <DropdownMenuSubTrigger class="text-white">
                                  <span style="display: flex; align-items: center; gap: 6px;">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                      <path d="M23 7l-7 5 7 5V7z"></path>
                                      <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                                    </svg>
                                    Seedance 2.0
                                  </span>
                                  <svg v-if="sceneDetailsVideoModel === 'bytedance/seedance-2.0'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" class="ml-auto">
                                    <polyline points="20 6 9 17 4 12"></polyline>
                                  </svg>
                                </DropdownMenuSubTrigger>
                                <DropdownMenuSubContent class="bg-black">
                                  <DropdownMenuItem
                                    v-for="d in [3, 5, 7, 10]"
                                    :key="d"
                                    @click="sceneDetailsVideoModel = 'bytedance/seedance-2.0'; sceneDetailsVideoDuration = d"
                                    class="text-white"
                                  >
                                    <span style="display: flex; align-items: center; gap: 6px;">
                                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <circle cx="12" cy="12" r="10"></circle>
                                        <polyline points="12 6 12 12 16 14"></polyline>
                                      </svg>
                                      {{ d }} seconds
                                    </span>
                                    <svg v-if="sceneDetailsVideoModel === 'bytedance/seedance-2.0' && sceneDetailsVideoDuration === d" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                      <polyline points="20 6 9 17 4 12"></polyline>
                                    </svg>
                                  </DropdownMenuItem>
                                </DropdownMenuSubContent>
                              </DropdownMenuSub>
                              <DropdownMenuItem
                                v-if="authStore.user?.type === 'admin'"
                                @click="sceneDetailsVideoModel = 'kwaivgi/kling-avatar-v2'"
                                class="text-white"
                              >
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"></path>
                                    <circle cx="9" cy="7" r="4"></circle>
                                    <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"></path>
                                  </svg>
                                  Kling Avatar
                                </span>
                                <svg v-if="sceneDetailsVideoModel === 'kwaivgi/kling-avatar-v2'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
                              <!-- <DropdownMenuItem
                                @click="sceneDetailsVideoModel = 'manim'"
                                class="text-white"
                              >
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="12" r="10"></circle>
                                    <polygon points="10 8 16 12 10 16 10 8"></polygon>
                                  </svg>
                                  Manim Animation
                                </span>
                                <svg v-if="sceneDetailsVideoModel === 'manim'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem> -->
                            </DropdownMenuContent>
                          </DropdownMenu>

                          <!-- Manim Mode Dropdown (only visible when manim is selected) -->
                          <DropdownMenu v-if="sceneDetailsVideoModel === 'manim'">
                            <DropdownMenuTrigger as-child>
                              <Button class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0">
                                <span class="flex items-center gap-0.5 truncate max-w-[50px]">
                                  {{ manimMode === 'creative' ? 'Creative' : 'Strict' }}
                                </span>
                                <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                  <polyline points="6 9 12 15 18 9"></polyline>
                                </svg>
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent class="bg-black" align="start">
                              <DropdownMenuItem @click="manimMode = 'creative'" class="text-white">
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                                    <path d="M2 17l10 5 10-5"></path>
                                    <path d="M2 12l10 5 10-5"></path>
                                  </svg>
                                  Creative (AI enhanced)
                                </span>
                                <svg v-if="manimMode === 'creative'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
                              <DropdownMenuItem @click="manimMode = 'strict'" class="text-white">
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                                    <line x1="9" y1="9" x2="15" y2="15"></line>
                                    <line x1="15" y1="9" x2="9" y2="15"></line>
                                  </svg>
                                  Strict (exact prompt)
                                </span>
                                <svg v-if="manimMode === 'strict'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>

                          <!-- Manim Aspect Ratio Dropdown (only visible when manim is selected) -->
                          <DropdownMenu v-if="sceneDetailsVideoModel === 'manim'">
                            <DropdownMenuTrigger as-child>
                              <Button class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0">
                                <span class="flex items-center gap-0.5 truncate max-w-[50px]">
                                  {{ manimAspectRatio }}
                                </span>
                                <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                  <polyline points="6 9 12 15 18 9"></polyline>
                                </svg>
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent class="bg-black" align="start">
                              <DropdownMenuItem @click="manimAspectRatio = '16:9'" class="text-white">
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="2" y="5" width="20" height="14" rx="2" ry="2"></rect>
                                  </svg>
                                  16:9 (Landscape)
                                </span>
                                <svg v-if="manimAspectRatio === '16:9'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
                              <DropdownMenuItem @click="manimAspectRatio = '9:16'" class="text-white">
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="5" y="2" width="14" height="20" rx="2" ry="2"></rect>
                                  </svg>
                                  9:16 (Portrait)
                                </span>
                                <svg v-if="manimAspectRatio === '9:16'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
                              <DropdownMenuItem @click="manimAspectRatio = '1:1'" class="text-white">
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                                  </svg>
                                  1:1 (Square)
                                </span>
                                <svg v-if="manimAspectRatio === '1:1'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>

                          <!-- Resolution Dropdown -->
                          <DropdownMenu>
                            <DropdownMenuTrigger as-child>
                              <Button
                                class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0"
                              >
                                <span class="flex items-center gap-0.5 truncate max-w-[50px]">
                                  {{ sceneDetailsVideoResolution }}
                                </span>
                                <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                  <polyline points="6 9 12 15 18 9"></polyline>
                                </svg>
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent class="bg-black" align="start">
                              <DropdownMenuItem
                                @click="sceneDetailsVideoResolution = '480p'"
                                class="text-white"
                              >
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                                  </svg>
                                  480p
                                </span>
                                <svg v-if="sceneDetailsVideoResolution === '480p'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                v-if="!isForced480pVideoModel(sceneDetailsVideoModel)"
                                @click="sceneDetailsVideoResolution = '720p'"
                                class="text-white"
                              >
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                                  </svg>
                                  720p
                                </span>
                                <svg v-if="sceneDetailsVideoResolution === '720p'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
	                              <!-- 1080p only available for Seedance 1 and Veo models -->
	                              <DropdownMenuItem
	                                v-if="supports1080pVideoModel(sceneDetailsVideoModel)"
	                                @click="sceneDetailsVideoResolution = '1080p'"
	                                class="text-white"
	                              >
                                <span style="display: flex; align-items: center; gap: 6px;">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                                  </svg>
                                  1080p
                                </span>
                                <svg v-if="sceneDetailsVideoResolution === '1080p'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                  <polyline points="20 6 9 17 4 12"></polyline>
                                </svg>
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>

                          <!-- Generate Video Button -->
                          <Button
                            @click="handleGenerateVideoFromSceneDetails"
                            :disabled="isGeneratingSceneDetailsVideo || !sceneDetailsAnimationPrompt.trim() || (sceneDetailsVideoModel !== 'manim' && !isGeminiOmniVideoModel(sceneDetailsVideoModel) && !startFrameImage && !scenes[selectedSceneForPreview]?.generatedImage) || (sceneDetailsVideoModel === 'kwaivgi/kling-avatar-v2' && !selectedSceneHasKlingAvatarAudio)"
                            class="h-7 px-1.5 text-[0.7rem] shadow-sm bg-linear-to-r from-yellow-400 to-red-500 cursor-pointer flex-shrink-0 hover:-translate-y-1"
                          >
                            <span v-if="isGeneratingSceneDetailsVideo || isAnimatingImage[selectedSceneForPreview]" class="flex items-center gap-0.5">
                              <i class="fa-solid fa-spinner fa-spin text-[0.65rem]"></i>
                              <span class="hidden sm:inline">Generating...</span>
                              <span class="sm:hidden">Gen...</span>
                            </span>
                            <span v-else class="flex items-center gap-0.5">
                              <i class="fa-solid fa-video text-[0.65rem]"></i>
                              <span class="flex items-center gap-1">
                                Generate
                              </span>
                            </span>
                          </Button>
                        </div>
                      </div>
                      <div
                        v-if="projectMode === 'talking_scenes' && getSceneAudioUrl(selectedScene)"
                        class="mt-3 rounded-md border border-orange-200 bg-orange-50/70 p-3"
                      >
                        <div class="mb-2 flex items-center justify-between gap-2">
                          <span class="text-xs font-semibold uppercase tracking-[0.08em] text-orange-700">Scene Audio</span>
                          <span class="text-[11px] text-orange-700/80">{{ formatDuration(getSceneAudioDuration(selectedScene)) }}</span>
                        </div>
                        <audio
                          :key="getSceneAudioUrl(selectedScene)"
                          :src="getSceneAudioUrl(selectedScene)"
                          controls
                          preload="metadata"
                          class="w-full"
                        ></audio>
                      </div>
                      <p v-if="sceneDetailsVideoModel !== 'manim' && !isGeminiOmniVideoModel(sceneDetailsVideoModel) && !startFrameImage && !scenes[selectedSceneForPreview]?.generatedImage" class="text-xs text-gray-500 mt-2">
                        Add an image first to create a video (or use Manim/Gemini Omni for text-based video)
                      </p>
                      <p v-if="sceneDetailsVideoModel === 'kwaivgi/kling-avatar-v2' && !selectedSceneHasKlingAvatarAudio" class="text-xs text-amber-600 mt-2">
                        Kling Avatar requires scene audio or project audio first
                      </p>
                    </div>
                  </div>

                  <!-- <div class="flex gap-4 pt-2 border-t border-gray-200">
                    <div v-if="scenes[selectedSceneForPreview].camera_movement">
                      <span class="text-gray-500">Camera:</span>
                      <span class="text-gray-800 ml-1">{{ scenes[selectedSceneForPreview].camera_movement }}</span>
                    </div>
                    <div v-if="scenes[selectedSceneForPreview].greenscreen_effect">
                      <span class="text-gray-500">Effect:</span>
                      <span class="text-gray-800 ml-1">{{ scenes[selectedSceneForPreview].greenscreen_effect }}</span>
                    </div>
                  </div> -->
                </div>
                </div>
                <!-- End scrollable content area -->
              </div>
              </div>
              <!-- End RIGHT: Scene Details Sidebar -->
              </div>
              <!-- End Preview Content -->
            </div>
            <!-- End Selected Scene Preview -->
        </div>
        <!-- End LARGE PREVIEW AREA -->
      </div>
        <!-- End Preview Content Wrapper -->

        <!-- Timeline Section (hidden when Preview tab is active, which has its own timeline) -->
        <div class="timeline-section">
          <SimpleTimeline
            v-if="!showingPreview && ((scenes.length > 0 && hasAllImages) || generatedAudio)"
            :scenes="scenes"
            :audio-duration="generatedAudio?.duration"
            :audio-url="generatedAudio?.url"
            :current-time="currentTime"
            :text-layers="textLayers"
            :selected-text-layer-id="selectedTextLayerId"
            @update:scenes="handleScenesUpdate"
            @seek="handleSeek"
            @delete-scene="handleTimelineSceneDelete"
            @add-text-layer="addTextLayer"
            @update-text-layer="handleTimelineTextLayerUpdate"
            @select-text-layer="(id) => { selectedTextLayerId = id }"
          />
        </div>
      </main>
    </div>

    <!-- Animal Haircut Modal -->
    <div
      v-if="showAnimalHaircutModal"
      class="voice-modal-overlay"
      @click="!isGeneratingAnimalHaircutPrompts && (showAnimalHaircutModal = false)"
    >
      <div class="upload-modal" @click.stop>
        <div class="voice-modal-header">
          <h3>Animal Haircut</h3>
          <button
            @click="showAnimalHaircutModal = false"
            class="modal-close-btn"
            :disabled="isGeneratingAnimalHaircutPrompts"
          >
            <i class="fa-solid fa-times"></i>
          </button>
        </div>

        <div class="upload-modal-content">
          <p class="upload-info">
            <i class="fa-solid fa-scissors"></i>
            We’ll generate a before image, an after image, and a matching grooming video prompt.
          </p>

          <div class="form-group">
            <label>Animal *</label>
            <input
              v-model="animalHaircutAnimal"
              type="text"
              placeholder="tiger, lion, dog..."
              maxlength="80"
              class="form-input"
              :disabled="isGeneratingAnimalHaircutPrompts"
            />
          </div>

          <div class="form-group">
            <label>Haircut Style *</label>
            <input
              v-model="animalHaircutStyle"
              type="text"
              placeholder="mohawk, undercut..."
              maxlength="80"
              class="form-input"
              :disabled="isGeneratingAnimalHaircutPrompts"
            />
          </div>
        </div>

        <div class="voice-modal-footer">
          <button
            @click="showAnimalHaircutModal = false"
            class="btn-cancel"
            :disabled="isGeneratingAnimalHaircutPrompts"
          >
            Cancel
          </button>
          <button
            @click="confirmAnimalHaircutStoryboard"
            :disabled="isGeneratingAnimalHaircutPrompts || !animalHaircutAnimal.trim() || !animalHaircutStyle.trim()"
            :class="['voice-confirm-btn', { 'opacity-60 cursor-not-allowed': isGeneratingAnimalHaircutPrompts || !animalHaircutAnimal.trim() || !animalHaircutStyle.trim() }]"
          >
            <i v-if="isGeneratingAnimalHaircutPrompts" class="fa-solid fa-spinner fa-spin"></i>
            <i v-else class="fa-solid fa-wand-magic-sparkles"></i>
            {{ isGeneratingAnimalHaircutPrompts ? 'Cooking magic...' : 'Confirm' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Custom Voice Upload Modal -->
    <div v-if="showCustomVoiceUpload" class="voice-modal-overlay" @click="showCustomVoiceUpload = false">
      <div class="upload-modal" @click.stop>
        <div class="voice-modal-header">
          <h3>Clone Your Voice</h3>
          <button @click="showCustomVoiceUpload = false" class="modal-close-btn">
            <i class="fa-solid fa-times"></i>
          </button>
        </div>

        <div class="upload-modal-content">
          <p class="upload-info">
            <i class="fa-solid fa-info-circle"></i>
            Cost: FREE | MiniMax clone | Duration: 10 sec - 5 min | Formats: MP3, WAV, M4A
          </p>

          <div class="form-group">
            <label>Voice Name *</label>
            <input
              v-model="newVoiceName"
              type="text"
              placeholder="e.g., My Professional Voice"
              maxlength="100"
              class="form-input"
            />
          </div>

          <div class="form-group">
            <label>Description (optional)</label>
            <textarea
              v-model="newVoiceDescription"
              placeholder="Brief description of this voice"
              maxlength="500"
              rows="3"
              class="form-textarea"
            ></textarea>
          </div>

          <div class="form-group">
            <label>Audio File *</label>
            <input
              type="file"
              @change="handleFileSelect"
              accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/mp4,audio/m4a,.mp3,.wav,.m4a"
              class="form-file-input"
            />
            <p class="form-hint">Upload a clear audio sample (10s-5m) of the voice you want to clone with MiniMax</p>
          </div>

          <div v-if="voiceUploadError" class="upload-error">
            <i class="fa-solid fa-exclamation-triangle"></i>
            {{ voiceUploadError }}
          </div>
        </div>

        <div class="voice-modal-footer">
          <button @click="showCustomVoiceUpload = false" class="btn-cancel">
            Cancel
          </button>
          <button
            @click="uploadCustomVoice"
            :disabled="uploadingVoice || !newVoiceName.trim() || !selectedVoiceFile"
            :class="['voice-confirm-btn', { 'opacity-60 cursor-not-allowed': uploadingVoice || !newVoiceName.trim() || !selectedVoiceFile }]"
          >
            <i v-if="uploadingVoice" class="fa-solid fa-spinner fa-spin"></i>
            <i v-else class="fa-solid fa-wand-magic-sparkles"></i>
            {{ uploadingVoice ? 'Cloning...' : 'Clone Voice' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Character Selector Modal -->
    <div v-if="showCharacterSelector" class="fixed inset-0 z-50 bg-black bg-opacity-50 flex items-center justify-center p-4" @click.self="closeCharacterSelector">
      <div class="bg-white rounded-lg p-6 max-w-2xl w-full max-h-[80vh] overflow-y-auto" @click.stop>
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-gray-900">
            Select Characters for Scene {{ (currentSceneIndex ?? 0) + 1 }}
          </h3>
          <button @click="closeCharacterSelector" class="text-gray-400 hover:text-gray-600">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <CharacterSelector
          :model-value="selectedCharacterIds"
          @update:model-value="selectedCharacterIds = $event"
          @confirm="confirmCharacterSelection"
          @cancel="closeCharacterSelector"
        />
      </div>
    </div>

    <!-- Scene Edit Modal - Replaced with inline editor -->
    <!-- <SceneEditModal
      ref="sceneEditModalRef"
      :is-open="showSceneEditModal"
      :scene="editingScene"
      :scene-number="editingSceneNumber"
      :image-models="imageGenerationStore.models.models"
      @close="closeSceneEditModal"
      @generate-image="handleGenerateImageFromModal"
      @generate-video="handleGenerateVideoFromModal"
      @add-video-to-timeline="handleAddVideoToTimelineFromModal"
    /> -->

    <!-- Scene Details Modal (Mobile Only) -->
    <div v-if="showSceneDetailsModal" class="lg:hidden fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" @click.self="showSceneDetailsModal = false">
      <div class="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] flex flex-col shadow-lg overflow-hidden" @click.stop>
        <!-- Header -->
        <div class="p-4 border-b border-gray-200 bg-gray-50 flex items-center justify-between">
          <h3 class="text-sm font-semibold text-gray-700">Scene Details</h3>
          <button @click="showSceneDetailsModal = false" class="text-gray-400 hover:text-gray-600">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Scrollable Content -->
        <div class="flex-1 overflow-y-auto p-4">
          <div class="space-y-3 text-sm">
            <!-- Editable Prompt -->
            <div class="">
              <label class="text-gray-500 text-xs mb-1 block">Prompt:</label>
              <div style="position: relative;">
                <textarea
                  v-model="sceneDetailsPrompt"
                  class="w-full p-2 pb-20 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                  rows="10"
                  placeholder="Enter scene description..."
                />
                <!-- Reference Image Card (Bottom-left corner) -->
                <div class="absolute bottom-2 left-2 z-10 w-20">
                  <label class="text-gray-700 text-[9px] mb-0.5 block">Reference</label>
                  <div
                    class="relative w-full aspect-video bg-gray-50 rounded border-dashed border cursor-pointer hover:border-orange-400"
                    @click="openImageReferenceSelector"
                  >
                    <img v-if="imageReferenceImage" :src="imageReferenceImage.url" class="w-full h-full object-cover rounded" />
                    <div v-else class="flex flex-col items-center justify-center h-full text-gray-400 text-[8px]">
                      <i class="fa-solid fa-plus text-[8px] mb-0.5"></i>
                      <span>Select</span>
                    </div>
                    <button
                      v-if="imageReferenceImage"
                      @click.stop="clearImageReference"
                      class="absolute top-0.5 right-0.5 w-3 h-3 bg-black/50 rounded-full text-white flex items-center justify-center"
                      title="Clear reference image"
                    >
                      <i class="fa-solid fa-times text-[6px]"></i>
                    </button>
                  </div>
                </div>
                <!-- Floating Buttons Container -->
                <div class="absolute bottom-2 left-24 right-2 flex flex-wrap gap-1 justify-end">
                  <!-- Model Dropdown -->
                  <DropdownMenu>
                    <DropdownMenuTrigger as-child>
                      <Button class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0">
                        <span class="flex items-center truncate max-w-[45px]">
                          {{ imageGenerationModels.find(m => m.value === imageGenerationModel)?.label }}
                        </span>
                        <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                    class="w-56 bg-black"
                      align="start"
                    >
                      <DropdownMenuItem
                        v-for="model in imageGenerationModels"
                        :key="model.value"
                        @click="imageGenerationModel = model.value"
                        :class="{
                          'text-white cursor-pointer': true
                        }"
                      >
                        <span style="display: flex; align-items: center; gap: 6px;">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                            <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
                            <line x1="12" y1="22.08" x2="12" y2="12"></line>
                          </svg>
                          {{ model.label }}
                        </span>
                        <svg v-if="imageGenerationModel === model.value" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                          <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>

                  <!-- Aspect Ratio Dropdown -->
                  <DropdownMenu>
                    <DropdownMenuTrigger as-child>
                      <Button class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0">
                        <span class="flex items-center gap-0.5">
                          {{ imageAspectRatio }}
                        </span>
                        <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                      class="bg-black"
                      align="start"
                    >
                      <DropdownMenuItem
                        v-for="ratio in imageAspectRatios"
                        :key="ratio.value"
                        @click="imageAspectRatio = ratio.value"
                        class="text-white"
                      >
                        <span style="display: flex; align-items: center; gap: 6px;">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                          </svg>
                          {{ ratio.value }}
                        </span>
                        <svg v-if="imageAspectRatio === ratio.value" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                          <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>

                  <!-- Generate Image Button -->
                  <Button
                    @click="handleGenerateImageFromSceneDetails"
                    :disabled="isGeneratingSceneDetailsImage || !sceneDetailsPrompt.trim()"
                    class="h-7 px-1.5 text-[0.7rem] shadow-sm bg-linear-to-r from-yellow-400 to-red-500 cursor-pointer flex-shrink-0"
                  >
                    <span v-if="isGeneratingSceneDetailsImage" class="flex items-center gap-0.5">
                      <i class="fa-solid fa-spinner fa-spin text-[0.65rem]"></i>
                      <span class="hidden sm:inline">Generating...</span>
                      <span class="sm:hidden">Gen...</span>
                    </span>
                    <span v-else class="flex items-center gap-0.5">
                      <i class="fa-solid fa-wand-magic-sparkles text-[0.65rem]"></i>
                      <span class="flex items-center gap-1">
                        Generate
                      </span>
                    </span>
                  </Button>
                </div>
              </div>
            </div>

            <!-- Reference Characters Section -->
            <div v-if="selectedSceneCharacters.length > 0" class="pt-3 border-t border-gray-200">
              <h4 class="text-xs font-semibold text-gray-700 mb-2">Reference Characters</h4>
              <div class="flex flex-wrap gap-2">
                <div
                  v-for="character in selectedSceneCharacters"
                  :key="character.id"
                  class="group relative inline-flex items-center gap-2 px-3 py-2 pr-8 rounded-lg bg-purple-50 border border-purple-200 hover:bg-purple-100 transition-colors"
                >
                  <div class="flex items-center gap-2">
                    <div v-if="character.reference_images && character.reference_images.length > 0" class="flex-shrink-0">
                      <img
                        :src="character.reference_images[0].image_url"
                        :alt="character.name"
                        class="w-8 h-8 rounded-full object-cover border border-purple-300"
                      />
                    </div>
                    <div v-else class="flex-shrink-0 w-8 h-8 rounded-full bg-purple-200 flex items-center justify-center border border-purple-300">
                      <svg class="w-4 h-4 text-purple-600" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                      </svg>
                    </div>
                    <div class="flex flex-col">
                      <span class="text-xs font-medium text-purple-900">{{ character.name }}</span>
                      <span v-if="character.reference_images && character.reference_images.length > 0" class="text-[10px] text-purple-600">
                        {{ character.reference_images.length }} reference{{ character.reference_images.length > 1 ? 's' : '' }}
                      </span>
                    </div>
                  </div>
                  <!-- Remove Button -->
                  <button
                    @click="removeCharacterFromScene(character.id)"
                    class="absolute top-1 right-1 w-5 h-5 flex items-center justify-center rounded-full bg-red-500 text-white opacity-0 group-hover:opacity-100 hover:bg-red-600 transition-all"
                    title="Remove character"
                  >
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>
              <p class="text-[10px] text-gray-500 mt-2">
                These characters will be included in image generation
              </p>
            </div>

            <!-- Video Generation Section -->
            <div class="pt-3 border-t border-gray-200">
              <h4 class="text-xs font-semibold text-gray-700 mb-2">Video Generation</h4>

              <!-- Animation Prompt -->
              <div>
                <label class="text-gray-500 text-xs mb-1 block">Animation Prompt:</label>
                <div style="position: relative;">
                  <textarea
                    v-model="sceneDetailsAnimationPrompt"
                    class="w-full p-2 pb-20 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                    rows="8"
                    placeholder="Describe the animation (e.g., camera slowly zooms in...)"
                  />

                  <!-- Start/End Frame Cards (Bottom-left corner) -->
                  <div class="absolute bottom-2 left-2 flex gap-2 z-10">
                    <!-- Start Frame (interactive) -->
                    <div class="w-20">
                      <label class="text-gray-700 text-[9px] mb-0.5 block">Start Frame</label>
                      <div class="relative w-full aspect-video bg-gray-50 rounded border-dashed border cursor-pointer hover:border-blue-400"
                           @click="openStartFrameSelector">
                        <img v-if="startFrameImage" :src="startFrameImage.url" class="w-full h-full object-cover rounded" />
                        <img v-else-if="selectedSceneForPreview !== null && scenes[selectedSceneForPreview]?.generatedImage?.url"
                             :src="selectedSceneForPreview !== null ? scenes[selectedSceneForPreview]?.generatedImage?.url : ''"
                             class="w-full h-full object-cover rounded opacity-70" />
                        <div v-else class="flex flex-col items-center justify-center h-full text-gray-400 text-[8px]">
                          <i class="fa-solid fa-plus text-[8px] mb-0.5"></i>
                          <span>Select</span>
                        </div>
                        <!-- Clear button -->
                        <button v-if="startFrameImage" @click.stop="clearStartFrame"
                                class="absolute top-0.5 right-0.5 w-3 h-3 bg-black/50 rounded-full text-white flex items-center justify-center">
                          <i class="fa-solid fa-times text-[6px]"></i>
                        </button>
                        <!-- Indicator -->
                        <div v-if="!startFrameImage && selectedSceneForPreview !== null && scenes[selectedSceneForPreview]?.generatedImage?.url"
                             class="absolute bottom-0.5 left-0.5 bg-black/50 rounded px-0.5 text-white text-[7px]">
                          Gen
                        </div>
                      </div>
                    </div>

                    <!-- End Frame (interactive) -->
                    <div class="w-20">
                      <label class="text-gray-700 text-[9px] mb-0.5 block">End Frame (optional)</label>
                      <div class="relative w-full aspect-video bg-gray-50 rounded border-dashed border cursor-pointer hover:border-blue-400"
                           @click="openEndFrameSelector">
                        <img v-if="endFrameImage" :src="endFrameImage.url" class="w-full h-full object-cover rounded" />
                        <div v-else class="flex flex-col items-center justify-center h-full text-gray-400 text-[8px]">
                          <i class="fa-solid fa-plus text-[8px] mb-0.5"></i>
                          <span>Add</span>
                        </div>
                        <!-- Clear button -->
                        <button v-if="endFrameImage" @click.stop="clearEndFrame"
                                class="absolute top-0.5 right-0.5 w-3 h-3 bg-black/50 rounded-full text-white flex items-center justify-center">
                          <i class="fa-solid fa-times text-[6px]"></i>
                        </button>
                      </div>
	                      <p v-if="endFrameImage && !supportsEndFrameVideoModel(sceneDetailsVideoModel)"
	                         class="text-[7px] text-amber-600 mt-0.5">
	                        Wan, Veo, Seedance 2 or Kling 3 only
	                      </p>
                    </div>
                  </div>

                  <!-- Floating Buttons Container (Bottom-right corner) -->
                  <div class="absolute bottom-2 right-2 flex flex-wrap gap-1 justify-end">
                    <!-- Video Model Dropdown -->
                    <DropdownMenu>
                      <DropdownMenuTrigger as-child>
                        <Button
                          class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0"
                        >
                          <span class="flex items-center gap-0.5 truncate max-w-[50px]">
                            {{ getVideoModelLabel(sceneDetailsVideoModel) }}
                          </span>
                          <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6 9 12 15 18 9"></polyline>
                          </svg>
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent class="bg-black" align="start">
	                        <DropdownMenuItem
	                          @click="sceneDetailsVideoModel = 'wan-video/wan-2.2-i2v-fast'"
	                          class="text-white"
	                        >
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <path d="M23 7l-7 5 7 5V7z"></path>
                              <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                            </svg>
                            Wan Video (Fast)
                          </span>
                          <svg v-if="sceneDetailsVideoModel === 'wan-video/wan-2.2-i2v-fast'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
	                            <polyline points="20 6 9 17 4 12"></polyline>
	                          </svg>
	                        </DropdownMenuItem>
                        <DropdownMenuItem
                          @click="sceneDetailsVideoModel = 'gemini-omni-flash-preview'; sceneDetailsVideoDuration = 8; sceneDetailsVideoResolution = '720p'"
                          class="text-white"
                        >
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <path d="M23 7l-7 5 7 5V7z"></path>
                              <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                              <path d="M12 2l1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5L12 2z" transform="translate(8 -1) scale(.55)"></path>
                            </svg>
                            Gemini Omni Flash
                          </span>
                          <svg v-if="sceneDetailsVideoModel === 'gemini-omni-flash-preview'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          @click="sceneDetailsVideoModel = 'veo-3.1-fast-generate-preview'; sceneDetailsVideoDuration = 4"
                          class="text-white"
                        >
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <path d="M23 7l-7 5 7 5V7z"></path>
                              <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                              <path d="M4 4l2 4 4 2-4 2-2 4-2-4-4-2 4-2 2-4z" transform="translate(12 -2) scale(.45)"></path>
                            </svg>
                            Google Veo 3.1 Fast
                          </span>
                          <svg v-if="sceneDetailsVideoModel === 'veo-3.1-fast-generate-preview'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          @click="sceneDetailsVideoModel = 'kwaivgi/kling-v2.1'; sceneDetailsVideoDuration = 5; sceneDetailsVideoResolution = '720p'"
                          class="text-white"
                        >
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <path d="M23 7l-7 5 7 5V7z"></path>
                              <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                            </svg>
                            Kling 2.1
                          </span>
                          <svg v-if="sceneDetailsVideoModel === 'kwaivgi/kling-v2.1'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          @click="sceneDetailsVideoModel = 'kwaivgi/kling-v2.6'; sceneDetailsVideoDuration = 5; sceneDetailsVideoResolution = '720p'"
                          class="text-white"
                        >
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <path d="M23 7l-7 5 7 5V7z"></path>
                              <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                            </svg>
                            Kling 2.6
                          </span>
                          <svg v-if="sceneDetailsVideoModel === 'kwaivgi/kling-v2.6'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          @click="sceneDetailsVideoModel = 'kwaivgi/kling-v3-video'; sceneDetailsVideoDuration = 3; sceneDetailsVideoResolution = '720p'"
                          class="text-white"
                        >
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <path d="M23 7l-7 5 7 5V7z"></path>
                              <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                              <path d="M12 2l1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5L12 2z" transform="translate(8 -1) scale(.55)"></path>
                            </svg>
                            Kling 3
                          </span>
                          <svg v-if="sceneDetailsVideoModel === 'kwaivgi/kling-v3-video'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
	                        <DropdownMenuSub>
                          <DropdownMenuSubTrigger class="text-white">
                            <span style="display: flex; align-items: center; gap: 6px;">
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M23 7l-7 5 7 5V7z"></path>
                                <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
                              </svg>
                              Seedance 2.0
                            </span>
                            <svg v-if="sceneDetailsVideoModel === 'bytedance/seedance-2.0'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" class="ml-auto">
                              <polyline points="20 6 9 17 4 12"></polyline>
                            </svg>
                          </DropdownMenuSubTrigger>
                          <DropdownMenuSubContent class="bg-black">
                            <DropdownMenuItem
                              v-for="d in [3, 5, 7, 10]"
                              :key="d"
                              @click="sceneDetailsVideoModel = 'bytedance/seedance-2.0'; sceneDetailsVideoDuration = d"
                              class="text-white"
                            >
                              <span style="display: flex; align-items: center; gap: 6px;">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                  <circle cx="12" cy="12" r="10"></circle>
                                  <polyline points="12 6 12 12 16 14"></polyline>
                                </svg>
                                {{ d }} seconds
                              </span>
                              <svg v-if="sceneDetailsVideoModel === 'bytedance/seedance-2.0' && sceneDetailsVideoDuration === d" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                                <polyline points="20 6 9 17 4 12"></polyline>
                              </svg>
                            </DropdownMenuItem>
                          </DropdownMenuSubContent>
                        </DropdownMenuSub>
                        <DropdownMenuItem
                          v-if="authStore.user?.type === 'admin'"
                          @click="sceneDetailsVideoModel = 'kwaivgi/kling-avatar-v2'"
                          class="text-white"
                        >
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"></path>
                              <circle cx="9" cy="7" r="4"></circle>
                              <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"></path>
                            </svg>
                            Kling Avatar
                          </span>
                          <svg v-if="sceneDetailsVideoModel === 'kwaivgi/kling-avatar-v2'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
                        <!-- <DropdownMenuItem
                          @click="sceneDetailsVideoModel = 'manim'"
                          class="text-white"
                        >
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <circle cx="12" cy="12" r="10"></circle>
                              <polygon points="10 8 16 12 10 16 10 8"></polygon>
                            </svg>
                            Manim Animation
                          </span>
                          <svg v-if="sceneDetailsVideoModel === 'manim'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem> -->
                      </DropdownMenuContent>
                    </DropdownMenu>

                    <!-- Manim Mode Dropdown (only visible when manim is selected) -->
                    <DropdownMenu v-if="sceneDetailsVideoModel === 'manim'">
                      <DropdownMenuTrigger as-child>
                        <Button class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0">
                          <span class="flex items-center gap-0.5 truncate max-w-[50px]">
                            {{ manimMode === 'creative' ? 'Creative' : 'Strict' }}
                          </span>
                          <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6 9 12 15 18 9"></polyline>
                          </svg>
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent class="bg-black" align="start">
                        <DropdownMenuItem @click="manimMode = 'creative'" class="text-white">
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                              <path d="M2 17l10 5 10-5"></path>
                              <path d="M2 12l10 5 10-5"></path>
                            </svg>
                            Creative (AI enhanced)
                          </span>
                          <svg v-if="manimMode === 'creative'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
                        <DropdownMenuItem @click="manimMode = 'strict'" class="text-white">
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                              <line x1="9" y1="9" x2="15" y2="15"></line>
                              <line x1="15" y1="9" x2="9" y2="15"></line>
                            </svg>
                            Strict (exact prompt)
                          </span>
                          <svg v-if="manimMode === 'strict'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>

                    <!-- Manim Aspect Ratio Dropdown (only visible when manim is selected) -->
                    <DropdownMenu v-if="sceneDetailsVideoModel === 'manim'">
                      <DropdownMenuTrigger as-child>
                        <Button class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0">
                          <span class="flex items-center gap-0.5 truncate max-w-[50px]">
                            {{ manimAspectRatio }}
                          </span>
                          <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6 9 12 15 18 9"></polyline>
                          </svg>
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent class="bg-black" align="start">
                        <DropdownMenuItem @click="manimAspectRatio = '16:9'" class="text-white">
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <rect x="2" y="5" width="20" height="14" rx="2" ry="2"></rect>
                            </svg>
                            16:9 (Landscape)
                          </span>
                          <svg v-if="manimAspectRatio === '16:9'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
                        <DropdownMenuItem @click="manimAspectRatio = '9:16'" class="text-white">
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <rect x="5" y="2" width="14" height="20" rx="2" ry="2"></rect>
                            </svg>
                            9:16 (Portrait)
                          </span>
                          <svg v-if="manimAspectRatio === '9:16'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
                        <DropdownMenuItem @click="manimAspectRatio = '1:1'" class="text-white">
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                            </svg>
                            1:1 (Square)
                          </span>
                          <svg v-if="manimAspectRatio === '1:1'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>

                    <!-- Resolution Dropdown -->
                    <DropdownMenu>
                      <DropdownMenuTrigger as-child>
                        <Button
                          class="h-7 px-1 text-[0.7rem] shadow-sm flex-shrink-0"
                        >
                          <span class="flex items-center gap-0.5 truncate max-w-[50px]">
                            {{ sceneDetailsVideoResolution }}
                          </span>
                          <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="6 9 12 15 18 9"></polyline>
                          </svg>
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent class="bg-black" align="start">
                        <DropdownMenuItem
                          @click="sceneDetailsVideoResolution = '480p'"
                          class="text-white"
                        >
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                            </svg>
                            480p
                          </span>
                          <svg v-if="sceneDetailsVideoResolution === '480p'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          v-if="!isForced480pVideoModel(sceneDetailsVideoModel)"
                          @click="sceneDetailsVideoResolution = '720p'"
                          class="text-white"
                        >
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                            </svg>
                            720p
                          </span>
                          <svg v-if="sceneDetailsVideoResolution === '720p'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
	                        <!-- 1080p only available for Seedance 1 and Veo models -->
	                        <DropdownMenuItem
	                          v-if="supports1080pVideoModel(sceneDetailsVideoModel)"
	                          @click="sceneDetailsVideoResolution = '1080p'"
	                          class="text-white"
	                        >
                          <span style="display: flex; align-items: center; gap: 6px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                            </svg>
                            1080p
                          </span>
                          <svg v-if="sceneDetailsVideoResolution === '1080p'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>

                    <!-- Generate Video Button -->
                    <Button
                      @click="handleGenerateVideoFromSceneDetails"
                      :disabled="isGeneratingSceneDetailsVideo || !sceneDetailsAnimationPrompt.trim() || (sceneDetailsVideoModel !== 'manim' && !isGeminiOmniVideoModel(sceneDetailsVideoModel) && !startFrameImage && (selectedSceneForPreview === null || !scenes[selectedSceneForPreview]?.generatedImage)) || (sceneDetailsVideoModel === 'kwaivgi/kling-avatar-v2' && !selectedSceneHasKlingAvatarAudio)"
                      class="h-7 px-1.5 text-[0.7rem] shadow-sm cursor-pointer flex-shrink-0"
                    >
                      <span v-if="isGeneratingSceneDetailsVideo || (selectedSceneForPreview !== null && isAnimatingImage[selectedSceneForPreview])" class="flex items-center gap-0.5">
                        <i class="fa-solid fa-spinner fa-spin text-[0.65rem]"></i>
                        <span class="hidden sm:inline">Generating...</span>
                        <span class="sm:hidden">Gen...</span>
                      </span>
                      <span v-else class="flex items-center gap-0.5">
                        <i class="fa-solid fa-video text-[0.65rem]"></i>
                        <span class="flex items-center gap-1">
                          Generate
                        </span>
                      </span>
                    </Button>
                  </div>
                </div>
                <p v-if="sceneDetailsVideoModel !== 'manim' && !isGeminiOmniVideoModel(sceneDetailsVideoModel) && !startFrameImage && (selectedSceneForPreview === null || !scenes[selectedSceneForPreview]?.generatedImage)" class="text-xs text-gray-500 mt-2">
                  Add an image first to create a video (or use Manim/Gemini Omni for text-based video)
                </p>
                <p v-if="sceneDetailsVideoModel === 'kwaivgi/kling-avatar-v2' && !selectedSceneHasKlingAvatarAudio" class="text-xs text-amber-600 mt-2">
                  Kling Avatar requires scene audio or project audio first
                </p>
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>

    <!-- Gallery Image Selector Modal -->
    <div v-if="showGallerySelector" class="fixed inset-0 z-50 bg-black/30 bg-opacity-20 flex items-center justify-center p-4" @click.self="closeGallerySelector">
      <div class="bg-white rounded-lg max-w-7xl w-full h-[92vh] flex flex-col shadow-lg overflow-hidden" @click.stop>
        <!-- Header -->
        <div class="flex items-center justify-between p-6 border-b border-gray-200">
          <h3 class="text-lg font-semibold text-gray-900">
            {{
              galleryMode === 'addNew'
                ? 'Select Media to Create New Scenes'
                : imageReferenceGalleryMode
                  ? 'Select Reference Image'
                  : startFrameGalleryMode
                    ? 'Select Start Frame'
                    : endFrameGalleryMode
                      ? 'Select End Frame'
                      : `Select Media for Scene ${(sceneIndexForImageReplacement ?? 0) + 1}`
            }}
          </h3>
          <div class="flex items-center gap-3">
            <!-- Upload from Computer Button -->
            <input
              ref="galleryUploadInput"
              type="file"
              accept="image/*,video/*"
              :multiple="galleryMode === 'addNew'"
              class="hidden"
              @change="handleGalleryImageUpload"
            />
            <Button
              @click="galleryUploadInput?.click()"
              :disabled="isUploadingGalleryImage"
              variant="outline"
              class="text-sm"
            >
              <i v-if="!isUploadingGalleryImage" class="fa-solid fa-upload mr-2"></i>
              <i v-else class="fa-solid fa-spinner fa-spin mr-2"></i>
              {{ isUploadingGalleryImage ? 'Uploading...' : 'Upload' }}
            </Button>
            <button @click="closeGallerySelector" class="text-gray-400 hover:text-gray-600">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <!-- ImageGallery Component with Folder Support -->
        <div class="flex-1 min-h-0">
          <ImageGallery
            ref="gallerySelectorRef"
            :images="imageGenerationStore.gallery.images"
            :loading="imageGenerationStore.gallery.loading"
            :folders="imageGenerationStore.folders.folders"
            :selected-folder-id="imageGenerationStore.folders.selectedFolderId"
            :uncategorized-count="imageGenerationStore.getUncategorizedCount"
            :folders-loading="imageGenerationStore.folders.loading"
            :show-folders="true"
            @select-folder="imageGenerationStore.setSelectedFolder"
            @create-folder="handleCreateFolder"
            @rename-folder="handleRenameFolder"
            @delete-folder="handleDeleteFolder"
            @move-image-to-folder="handleMoveImage"
            @move-images-to-folder="handleMoveImages"
            @image-click="confirmGalleryImageSelection"
            @image-error="handleGalleryMediaError"
            @load-more="loadMoreGalleryImages"
            @delete-image="handleDeleteImage"
            @batch-delete-images="handleBatchDeleteImages"
          />
        </div>
      </div>
    </div>

    <!-- Caption Editor Modal -->
    <div
      v-if="isCaptionEditorOpen"
      class="fixed inset-0 z-[9999] bg-black/50 flex items-center justify-center p-4"
      @click.self="closeCaptionEditor"
    >
      <div class="bg-white rounded-lg shadow-xl w-full max-w-3xl flex flex-col max-h-[90vh]">
        <div class="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
          <div class="flex items-center gap-3 min-w-0">
            <h3 class="text-base font-semibold text-gray-900 whitespace-nowrap">Edit caption</h3>
            <p class="text-xs text-gray-500 truncate">
              Update caption text that will be used for subtitle burning on the next video render.
            </p>
          </div>
          <button @click="closeCaptionEditor" class="text-gray-400 hover:text-gray-600">
            <i class="fa-solid fa-times"></i>
          </button>
        </div>
        <div class="p-5 flex-1 overflow-y-auto">
          <div class="mt-4">
            <p class="text-xs font-semibold text-gray-700 mb-2">Caption Timestamps</p>
            <div class="border border-gray-200 rounded-md max-h-52 overflow-y-auto bg-gray-50">
              <div v-if="captionTimestampRows.length === 0" class="px-3 py-2 text-xs text-gray-500">
                No timestamp data available.
              </div>
              <div
                v-for="(row, index) in captionTimestampRows"
                :key="`${index}-${row.start}-${row.end}`"
                class="px-3 py-2 border-b border-gray-200 last:border-b-0"
              >
                <p class="text-[11px] text-gray-500 font-mono">
                  {{ formatCaptionTime(row.start) }} → {{ formatCaptionTime(row.end) }}
                </p>
                <textarea
                  v-model="row.text"
                  class="w-full mt-1 border border-gray-300 rounded px-2 py-1 text-xs text-gray-800 outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500 resize-y min-h-12"
                ></textarea>
              </div>
            </div>
          </div>
        </div>
        <div class="px-5 py-4 border-t border-gray-200 flex items-center justify-end gap-2">
          <Button
            variant="outline"
            @click="closeCaptionEditor"
            :disabled="isSavingCaptionText"
          >
            Cancel
          </Button>
          <Button
            class="bg-orange-500 text-white hover:bg-orange-600"
            @click="saveCaptionEdits"
            :disabled="isSavingCaptionText || isLoadingCaptionText"
          >
            <i v-if="isSavingCaptionText" class="fa-solid fa-spinner fa-spin"></i>
            <span>{{ isSavingCaptionText ? 'Saving...' : 'Save caption' }}</span>
          </Button>
        </div>
      </div>
    </div>
    </div> <!-- Close main-container -->

    <!-- Hidden file input for direct uploads from preview section -->
    <input
      ref="previewUploadInput"
      type="file"
      accept="image/*,video/*"
      :multiple="galleryMode === 'addNew'"
      class="hidden"
      @change="handleGalleryImageUpload"
    />

    <!-- Caption style preview tooltip -->
    <Teleport to="body">
      <div
        v-if="stylePreviewVisible"
        class="fixed z-[9999] pointer-events-none rounded-lg overflow-hidden shadow-2xl border border-gray-600"
        :style="{
          left: stylePreviewPosition.x + 'px',
          top: stylePreviewPosition.y + 'px'
        }"
      >
        <img
          :src="stylePreviewGif"
          alt="Style preview"
          class="w-80 h-auto"
        />
      </div>
    </Teleport>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import apiClient from '@/api/apiClient'
import { toast, Toaster } from 'vue-sonner'
import { logger } from '@/utils/logger'
import SceneCard from '@/components/SceneCardNew.vue'
import {
  saveProjectScenes,
  loadProjectScenes,
  saveProjectTextLayers,
  loadProjectTextLayers,
  generateProjectSceneAudio,
  adjustProjectSceneAudioSpeed,
  generateTalkingScenePrompts,
  generateAnimalHaircutPrompts,
  type SceneData,
} from '@/api/scenes'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
} from '@/components/ui/dropdown-menu'
import { Slider } from '@/components/ui/slider'
import { SimpleTimeline } from '@/components/timeline'
import RemotionPlayer from '@/components/RemotionPlayer.vue'
import { videoGenerationService, type VideoGenerationRequest, type GenerationProgress } from '@/api/videoGenerationService'
import { useUserPreferencesStore, type StoryboardVideoResolution } from '@/stores/userPreferences'
import { useCharactersStore } from '@/stores/characters'
import { useImageGenerationStore } from '@/stores/imageGeneration'
import { useAuthStore } from '@/stores/auth'
import imageService from '@/api/imageService'
import audioService from '@/api/audioService'
import CharacterSelector from '@/components/CharacterSelector.vue'
import ImageGallery from '@/components/ImageGallery.vue'
// import SceneEditModal from '@/components/SceneEditModal.vue' // Replaced with inline editor
import draggable from 'vuedraggable'

// Caption style preview GIFs
import karaokeStyleGif from '@/assets/custom-fonts/karaoke_style.gif'
import wordByWordStyleGif from '@/assets/custom-fonts/word_by_word_style.gif'
import sentenceStyleGif from '@/assets/custom-fonts/sentence_style.gif'

// Custom directive for click outside
const vClickOutside = {
  mounted(el: any, binding: any) {
    el.clickOutsideEvent = (event: Event) => {
      if (!(el === event.target || el.contains(event.target as Node))) {
        binding.value(event)
      }
    }
    setTimeout(() => {
      document.addEventListener('click', el.clickOutsideEvent)
    }, 0)
  },
  unmounted(el: any) {
    document.removeEventListener('click', el.clickOutsideEvent)
  }
}

const editingSceneFalse = false
const route = useRoute()
const router = useRouter()
const preferencesStore = useUserPreferencesStore()
const charactersStore = useCharactersStore()
const imageGenerationStore = useImageGenerationStore()
const authStore = useAuthStore()

// Project state
// Using ref instead of computed to avoid component remount when updating URL
const projectId = ref<string | undefined>(route.params.id as string | undefined)
const projectTitle = ref('My Video Project')
const projectStatus = ref<'draft' | 'processing' | 'completed' | 'failed'>('draft')
const isLoadingProject = ref(false) // True while loading existing project data

// Title editing state
const isEditingTitle = ref(false)
const editingTitle = ref('')
const isSavingTitle = ref(false)
const titleInput = ref<HTMLInputElement | null>(null)

// Creation mode
const creationMode = ref<'scriptToVideo' | 'ideaToVideo' | 'audioToVideo'>('ideaToVideo')
const ideaSubMode = ref<'ideas' | 'repurpose'>('ideas')
const projectMode = ref<'narrated_broll' | 'talking_scenes'>('narrated_broll')

// Idea to Video state
const ideaText = ref('')
const videoLength = ref<number[]>([1])
const isImprovingIdea = ref(false)
const selectedIdeaVersion = ref<1 | 2>(1)
const improvedIdeaResults = ref<{
  analysis: { hook: string; content: string }
  version_1: { improved_script: string; title: string }
  version_2: { improved_script: string; title: string }
  description: string
  tags: string[]
  hashtags: string[]
} | null>(null)
const showingIdeaResults = ref(false)

// Trending topics state
const trendKeyword = ref('')
const trendingTopics = ref<any[]>([])
const isFetchingTrends = ref(false)
const showingTrendingResults = ref(false)

// Generated script results (for 'ideas' mode)
const generatedScriptResults = ref<{
  version_1: { script: string; title: string; word_count: number; estimated_duration: string }
  version_2: { script: string; title: string; word_count: number; estimated_duration: string }
  description: string
  tags: string[]
  hashtags: string[]
} | null>(null)
const isGeneratingScript = ref(false)
const selectedGeneratedVersion = ref<1 | 2>(1)

// Form data
const script = ref('')
const uploadedAudioFile = ref<File | null>(null)
const uploadedAudioUrl = ref<string | null>(null)
type VoiceProvider = 'minimax' | 'deepgram' | 'google' | 'elevenlabs'

interface CharacterVoiceAssignment {
  character_id: string
  character_name: string
  voice_id: string
  provider: VoiceProvider
  audio_speed?: number
  preview_text?: string
  locked?: boolean
}

interface SpeakingCharacterSummary {
  character_id: string
  character_name: string
  scene_count: number
  line_count: number
  sample_line: string
  assigned_voice_id?: string
  assigned_provider?: VoiceProvider
}

const selectedVoice = ref('English_MatureBoss')
const autoMatchMusic = ref(true)
const ttsProvider = ref<VoiceProvider>('minimax')
const characterVoiceMap = ref<Record<string, CharacterVoiceAssignment>>({})

// Custom voice cloning state
interface CustomVoice {
  id: string
  voice_name: string
  description?: string
  provider?: VoiceProvider
  voice_id?: string
  elevenlabs_voice_id: string
  status: string
  preview_url?: string
  created_at: string
}

const customVoices = ref<CustomVoice[]>([])
const isLoadingCustomVoices = ref(false)
const showCustomVoiceUpload = ref(false)
const uploadingVoice = ref(false)
const voiceUploadError = ref('')
const newVoiceName = ref('')
const newVoiceDescription = ref('')
const selectedVoiceFile = ref<File | null>(null)

const getCustomVoiceId = (voice: CustomVoice) => voice.voice_id || voice.elevenlabs_voice_id

const getCustomVoiceProvider = (voice: CustomVoice): VoiceProvider => {
  return voice.provider && isSupportedVoiceProvider(voice.provider) ? voice.provider : 'minimax'
}

// Generated assets
const generatedAudio = ref<{ url: string; duration: number; fileId?: string; projectId?: string } | null>(null)
const timelineSegments = ref<any[]>([])
const audioPlayerKey = ref(0) // Counter to force audio player refresh

// Audio upload state
const isUploadingAudio = ref(false)
const audioUploadProgress = ref(0)
const audioUploadError = ref('')
const isDraggingAudio = ref(false)

const currentTime = ref(0) // Track audio playback position for timeline playhead

// Loading states
const isGeneratingAudio = ref(false)
const isGeneratingScenes = ref(false)
const audioGenerationProgress = ref(0)
const sceneGenerationProgress = ref(0)
const sceneGenerationError = ref('')
const sceneAggregationMode = ref<string>(
  sessionStorage.getItem('sceneAggregationMode') || 'regular'
)
const isGeneratingImages = ref(false)
const currentImageIndex = ref(0)
const isGeneratingVideo = ref(false)
const includeWatermarkLogo = ref(true)
const watermarkLogoPosition = ref('bottom_right')
const watermarkLogoPositions = [
  { value: 'top_left', label: 'Top left' },
  { value: 'top_right', label: 'Top right' },
  { value: 'bottom_left', label: 'Bottom left' },
  { value: 'bottom_right', label: 'Bottom right' }
]
const hasProfileWatermarkLogo = computed(() => Boolean(authStore.user?.watermark_logo_url))
const watermarkLogoPreviewUrl = computed(() => authStore.user?.watermark_logo_url || '')
const shouldShowWatermarkLogoPreview = computed(() =>
  includeWatermarkLogo.value &&
  hasProfileWatermarkLogo.value &&
  Boolean(watermarkLogoPreviewUrl.value)
)
const watermarkLogoPreviewStyle = computed(() => {
  const margin = '3.5%'
  const style: Record<string, string | number> = {
    width: '18%',
    minWidth: '42px',
    maxWidth: '180px',
    height: 'auto',
    opacity: 0.82,
    pointerEvents: 'none',
    zIndex: 30,
    objectFit: 'contain',
    filter: 'drop-shadow(0 6px 14px rgba(0, 0, 0, 0.35))'
  }

  if (watermarkLogoPosition.value.includes('top')) {
    style.top = margin
  } else {
    style.bottom = margin
  }

  if (watermarkLogoPosition.value.includes('left')) {
    style.left = margin
  } else {
    style.right = margin
  }

  return style
})
const isGeneratingSceneAudio = ref(false)
const isReorderingScenes = ref(false)
const isSavingDraft = ref(false)
const isLoadingInitialPreferences = ref(true) // Flag to prevent auto-save during initial load
const finalGeneratedVideo = ref<{ url: string; duration?: number } | null>(null) // Store final video output
const isCheckingFinalVideo = ref(false)
const finalVideoExists = ref(false)
const currentUserId = ref<string | null>(null) // Store user ID for video file path construction
const isDownloadingVideo = ref(false) // Track download progress

// Animation states (for image-to-video)
const isAnimatingImage = ref<Record<number, boolean>>({})
const animationProgress = ref<Record<number, number>>({})

// Modal states
const showCharacterSelector = ref(false)
const currentSceneIndex = ref<number | null>(null)
const selectedCharacterIds = ref<string[]>([])
const showSceneEditModal = ref(false)
const editingSceneIndex = ref<number | null>(null)
const editingScene = ref<Scene | null>(null)
const editingSceneNumber = ref(0)
const sceneEditModalRef = ref<any>(null)
const showAnimalHaircutModal = ref(false)
const isGeneratingAnimalHaircutPrompts = ref(false)
const animalHaircutAnimal = ref('')
const animalHaircutStyle = ref('')
const showGallerySelector = ref(false)
const sceneIndexForImageReplacement = ref<number | null>(null)
const isLoadingMoreGalleryImages = ref(false)
const showSceneDetailsModal = ref(false)
const isCaptionEditorOpen = ref(false)
const isLoadingCaptionText = ref(false)
const isSavingCaptionText = ref(false)
const captionEditorSourceFile = ref('')
const captionTimestampRows = ref<{ start: number; end: number; text: string }[]>([])
const galleryViewRef = ref<any>(null)
const gallerySelectorRef = ref<any>(null)
const galleryUploadInput = ref<HTMLInputElement | null>(null)
const previewUploadInput = ref<HTMLInputElement | null>(null)
const isUploadingGalleryImage = ref(false)
const galleryMode = ref<'replace' | 'addNew'>('replace') // Track if we're replacing or adding new scenes

// Inline scene editor states
const localPrompt = ref('')
const localAnimationPrompt = ref('')
const selectedImageModel = ref('')
const selectedVideoModel = ref('wan-video/wan-2.2-i2v-fast')
const isGeneratingImageInEditor = ref(false)
const isGeneratingVideoInEditor = ref(false)
const generatedImageUrl = ref('')
const generatedVideoUrl = ref('')

// Scene details editing (for storyboard review section)
const sceneDetailsPrompt = ref('')
type SelectedReferenceImage = {
  id: string
  url: string
  width?: number
  height?: number
  aspectRatio?: '16:9' | '9:16' | '1:1'
}

const imageReferenceImage = ref<SelectedReferenceImage | null>(null)
const imageReferenceGalleryMode = ref(false)
// Note: Model and aspect ratio now use the same refs as script to video section for consistency
// Track which scenes are currently generating images (by scene index)
const generatingSceneIndices = ref(new Set<number>())
const sceneDetailsAnimationPrompt = ref('')
const sceneDetailsVideoModel = ref(
  normalizeVideoModelSelection(sessionStorage.getItem('sceneDetailsVideoModel'))
)
const sceneDetailsVideoResolution = ref(
  sessionStorage.getItem('sceneDetailsVideoResolution') || '720p'
)
const sceneDetailsVideoDuration = ref(5)

// Computed property to check if current scene is generating video
const isGeneratingSceneDetailsVideo = computed(() => {
  return selectedSceneForPreview.value !== null && isAnimatingImage.value[selectedSceneForPreview.value]
})

// Start frame for video generation (allows override of generated image)
const startFrameImage = ref<SelectedReferenceImage | null>(null)
const startFrameGalleryMode = ref(false)

// End frame for video generation
const endFrameImage = ref<SelectedReferenceImage | null>(null)
const endFrameGalleryMode = ref(false)

// Manim animation options
const manimMode = ref<'creative' | 'strict'>(
  (sessionStorage.getItem('manimMode') as 'creative' | 'strict') || 'creative'
)
const manimQuality = ref<'l' | 'm' | 'h' | 'k'>(
  (sessionStorage.getItem('manimQuality') as 'l' | 'm' | 'h' | 'k') || 'm'
)
const manimAspectRatio = ref<'16:9' | '9:16' | '1:1'>(
  (sessionStorage.getItem('manimAspectRatio') as '16:9' | '9:16' | '1:1') || '16:9'
)

// Audio speed control
const audioSpeed = ref<number>(1.0)
const appliedAudioSpeed = ref<number>(1.0)
const isAdjustingAudioSpeed = ref(false)
const hasPendingGeneratedAudioSpeedChange = computed(() => (
  !!generatedAudio.value &&
  !!(projectId.value || generatedAudio.value?.projectId) &&
  scenes.value.length > 0 &&
  Math.abs(audioSpeed.value - appliedAudioSpeed.value) > 0.005
))

// Voice option type
interface VoiceOption {
  id: string
  name: string
  description: string
  language: string
  tags: string[]
  provider: VoiceProvider | string
  sampleUrl?: string
}

// Voice options - complete list from VideoGenerator with sample URLs
const defaultVoiceOptions = ref<VoiceOption[]>([
  // Minimax voices
  { id: 'English_MatureBoss', name: 'Charlotte', description: 'Professional Female', language: 'English (US)', tags: ['American', 'Female'], provider: 'minimax' },
  { id: 'English_Upbeat_Woman', name: 'Emma', description: 'Upbeat Female', language: 'English (US)', tags: ['American', 'Young'], provider: 'minimax' },
  { id: 'English_Debator', name: 'David', description: 'Tough Male', language: 'English (US)', tags: ['American', 'Formal'], provider: 'minimax' },
  { id: 'English_magnetic_voiced_man', name: 'Charlie', description: 'Magnetic Voice Male', language: 'English (US)', tags: ['American', 'Confident'], provider: 'minimax' },
  { id: 'English_Comedian', name: 'Comedian', description: 'Humorous', language: 'English', tags: ['English', 'Confident'], provider: 'minimax' },
  { id: 'English_expressive_narrator', name: 'Expressive Narrator', description: 'Expressive narration', language: 'English', tags: ['English', 'Narration'], provider: 'minimax' },
  { id: 'English_Insightful_Speaker', name: 'Insightful Speaker', description: 'Thoughtful voice', language: 'English', tags: ['English', 'Confident'], provider: 'minimax' },
  { id: 'English_Steady_Female_5', name: 'Female Actor', description: 'Professional actress', language: 'English', tags: ['English', 'Confident'], provider: 'minimax' },
  { id: 'English_AnimeCharacter', name: 'Female Narrator', description: 'Energetic narrator', language: 'English', tags: ['English', 'Confident'], provider: 'minimax' },
  { id: 'English_Whispering_girl_v3', name: 'Whispering Girl', description: 'Soft whisper', language: 'English', tags: ['English', 'Gentle'], provider: 'minimax' },
  { id: 'whisper_man', name: 'Whisper Man', description: 'Male whisper', language: 'English', tags: ['English', 'Gentle'], provider: 'minimax' },
  { id: 'moss_audio_ad5baf92-735f-11f0-8263-fe5a2fe98ec8', name: 'Chill Bestie', description: 'Casual friend', language: 'English', tags: ['English', 'Casual'], provider: 'minimax' },
  { id: 'English_witty_female_1', name: 'Witty Female', description: 'Clever and witty', language: 'English', tags: ['English', 'Witty'], provider: 'minimax' },
  { id: 'English_ManWithDeepVoice', name: 'Deep Voice Man', description: 'Very deep male', language: 'English', tags: ['English', 'Deep'], provider: 'minimax' },
  { id: 'English_Sharp_Commentator', name: 'Sharp Commentator', description: 'Critical analyst', language: 'English', tags: ['English', 'Narration'], provider: 'minimax' },
  { id: 'socialmedia_female_1_v1', name: 'Upbeat Ashley', description: 'Social media voice', language: 'English', tags: ['English', 'Upbeat'], provider: 'minimax' },
  { id: 'socialmedia_female_2_v1', name: 'Cheerful Chloe', description: 'Happy and cheerful', language: 'English', tags: ['English', 'Cheerful'], provider: 'minimax' },
  { id: 'moss_audio_7c7e7ae2-7356-11f0-9540-7ef9b4b62566', name: 'Chatter Zoe', description: 'Talkative voice', language: 'English', tags: ['English', 'Energetic'], provider: 'minimax' },
  { id: 'English_StressedLady', name: 'Stressed Lady', description: 'Anxious voice', language: 'English', tags: ['English', 'Dramatic'], provider: 'minimax' },

  // Deepgram voices (premium)
  // { id: 'aura-2-jupiter-en', name: 'Jupiter', description: 'Clear, professional neutral', language: 'English', tags: ['Male', 'Professional'], provider: 'deepgram' },
  // { id: 'aura-2-odysseus-en', name: 'Odysseus', description: 'Calm, smooth, comfortable', language: 'English', tags: ['Male', 'Professional'], provider: 'deepgram' },
  // { id: 'aura-2-draco-en', name: 'Draco', description: 'Approachable, trustworthy', language: 'English', tags: ['Male', 'Professional'], provider: 'deepgram' },
  // { id: 'aura-2-phoebe-en', name: 'Phoebe', description: 'Feminine, energetic, warm', language: 'English', tags: ['Female', 'Energetic'], provider: 'deepgram' },
  // { id: 'aura-2-athena-en', name: 'Athena', description: 'Confident, authoritative', language: 'English', tags: ['Female', 'Authoritative'], provider: 'deepgram' },
  // { id: 'aura-2-hera-en', name: 'Hera', description: 'Elegant, sophisticated', language: 'English', tags: ['Female', 'Elegant'], provider: 'deepgram' },
  // { id: 'aura-2-luna-en', name: 'Luna', description: 'Gentle, soothing', language: 'English', tags: ['Female', 'Gentle'], provider: 'deepgram' },
  // { id: 'aura-2-arcas-en', name: 'Arcas', description: 'Strong, dependable', language: 'English', tags: ['Male', 'Strong'], provider: 'deepgram' },
  // { id: 'aura-2-orion-en', name: 'Orion', description: 'Deep, commanding', language: 'English', tags: ['Male', 'Deep'], provider: 'deepgram' },
  // { id: 'aura-2-orpheus-en', name: 'Orpheus', description: 'Melodic, expressive', language: 'English', tags: ['Male', 'Melodic'], provider: 'deepgram' },
  // { id: 'aura-2-aries-en', name: 'Aries', description: 'Energetic, dynamic', language: 'English', tags: ['Male', 'Energetic'], provider: 'deepgram' },
 
  // Google voices (admin only)
  { id: 'Despina', name: 'Despina', description: 'Google Gemini voice', language: 'English', tags: ['Google', 'Versatile'], provider: 'google' },
  { id: 'Puck', name: 'Puck', description: 'Google Gemini voice', language: 'English', tags: ['Google', 'Versatile'], provider: 'google' },
  { id: 'Algieba', name: 'Algieba', description: 'Google Gemini voice', language: 'English', tags: ['Google', 'Deep'], provider: 'google' },
  { id: 'Charon', name: 'Charon', description: 'Google Gemini voice', language: 'English', tags: ['Google', 'Deep'], provider: 'google' },
  { id: 'Fenrir', name: 'Fenrir', description: 'Google Gemini voice', language: 'English', tags: ['Google', 'Strong'], provider: 'google' },
  { id: 'Aoede', name: 'Aoede', description: 'Female, Breezy, Middle Pitch', language: 'English', tags: ['Google', 'Melodic'], provider: 'google' },
  { id: 'Callirrhoe', name: 'Callirrhoe', description: 'Google Gemini voice', language: 'English', tags: ['Google', 'Elegant'], provider: 'google' },
  { id: 'Enceladus', name: 'Enceladus', description: 'Google Gemini voice', language: 'English', tags: ['Google', 'Dynamic'], provider: 'google' },
  { id: 'Iapetus', name: 'Iapetus', description: 'Google Gemini voice', language: 'English', tags: ['Google', 'Calm'], provider: 'google' },
  { id: 'Achernar', name: 'Achernar', description: 'Google Gemini voice', language: 'English', tags: ['Google', 'Bright'], provider: 'google' },
  { id: 'Alnilam', name: 'Alnilam', description: 'Google Gemini voice', language: 'English', tags: ['Google', 'Professional'], provider: 'google' },
  { id: 'Schedar', name: 'Schedar', description: 'Google Gemini voice', language: 'English', tags: ['Google', 'Warm'], provider: 'google' },
  { id: 'Erinome', name: 'Erinome', description: 'Female, Clear, Middle pitch', language: 'English', tags: ['Google', 'Warm'], provider: 'google' },
  { id: 'Sulafat', name: 'Sulafat', description: 'Female, Warm, Middle pitch', language: 'English', tags: ['Google', 'Warm'], provider: 'google' },
  { id: 'Zephyr', name: 'Zephyr', description: 'Female, ', language: 'English', tags: ['Google', 'Warm'], provider: 'google' },
  { id: 'Leda', name: 'Leda', description: 'Female, Youthful, Higher Pitcher', language: 'English', tags: ['Google', 'Warm'], provider: 'google' },

  // ElevenLabs voices (premium)
  { id: 'q0IMILNRPxOgtBTS4taI', name: 'Drew', description:'Casual, Curious & Fun', language: 'English', tags: ['Male', 'Social Media'], provider: 'elevenlabs' },
  { id: '15CVCzDByBinCIoCblXo', name: 'Lucan', description: 'Middle-aged male with an energetic voice', language: 'English', tags:['Male', 'Social Media'], provider: 'elevenlabs'},
  { id: '21m00Tcm4TlvDq8ikWAM', name: 'Rachel', description: 'Calm, narrative American voice', language: 'English', tags: ['Female', 'Narrative'], provider: 'elevenlabs' },
  { id: 'EXAVITQu4vr4xnSDxMaL', name: 'Bella', description: 'Soft, warm American voice', language: 'English', tags: ['Female', 'Soft'], provider: 'elevenlabs' },
  { id: 'ErXwobaYiN019PkySvjV', name: 'Antoni', description: 'Well-rounded, versatile American voice', language: 'English', tags: ['Male', 'Versatile'], provider: 'elevenlabs' },
  { id: 'MF3mGyEYCl7XYWbV9V6O', name: 'Elli', description: 'Young, friendly American voice', language: 'English', tags: ['Female', 'Young'], provider: 'elevenlabs' },
  { id: 'TxGEqnHWrfWFTfGW9XjX', name: 'Josh', description: 'Deep, authoritative American voice', language: 'English', tags: ['Male', 'Deep'], provider: 'elevenlabs' },
  { id: 'pNInz6obpgDQGcFmaJgB', name: 'Adam', description: 'Deep, narrator-style American voice', language: 'English', tags: ['Male', 'Narrator'], provider: 'elevenlabs' },
  { id: 'VR6AewLTigWG4xSOukaG', name: 'Arnold', description: 'Strong, crisp American voice', language: 'English', tags: ['Male', 'Strong'], provider: 'elevenlabs' },
  { id: '2EiwWnXFnvU5JabPnv8n', name: 'Clyde', description: 'Middle-aged, war veteran voice', language: 'English', tags: ['Male', 'Character'], provider: 'elevenlabs' },
  { id: 'D38z5RcWu1voky8WS1ja', name: 'Domi', description: 'Strong, confident American voice', language: 'English', tags: ['Female', 'Confident'], provider: 'elevenlabs' },
  { id: 'ThT5KcBeYPX3keUQqHPh', name: 'Dorothy', description: 'Pleasant, British voice', language: 'English', tags: ['Female', 'British'], provider: 'elevenlabs' },
  { id: 'AZnzlk1XvdvUeBnXmlld', name: 'Emily', description: 'Calm, soothing American voice', language: 'English', tags: ['Female', 'Calm'], provider: 'elevenlabs' },
  { id: 'LcfcDJNUP1GQjkzn1xUU', name: 'Ethan', description: 'Young, energetic American voice', language: 'English', tags: ['Male', 'Energetic'], provider: 'elevenlabs' },
  { id: 'XrExE9yKIg1WjnnlVkGX', name: 'Lily', description: 'Warm, British accent voice', language: 'English', tags: ['Female', 'British'], provider: 'elevenlabs' },
  { id: 'ZQe5CZNOzWyzPSCn5a3c', name: 'James', description: 'Deep, Australian accent voice', language: 'English', tags: ['Male', 'Australian'], provider: 'elevenlabs' },
  { id: 'Xb7hH8MSUJpSbSDYk0k2', name: 'Alice', description: 'Confident, British accent voice', language: 'English', tags: ['Female', 'British'], provider: 'elevenlabs' },


 
 
])

// Merge custom voices with default voices
const voiceOptions = computed(() => {
  const customOptions = customVoices.value
    .filter(v => v.status === 'completed')
    .map(v => ({
      id: getCustomVoiceId(v),
      name: `${v.voice_name} ⭐`,
      description: v.description || 'Your custom voice',
      language: 'English',
      tags: ['Custom'],
      provider: getCustomVoiceProvider(v),
      isCustom: true,
      customVoiceId: v.id,
      sampleUrl: v.preview_url
    }))

  // Custom voices first, then defaults
  return [...customOptions, ...defaultVoiceOptions.value]
})

// Voice dropdown state
const isVoiceDropdownOpen = ref(false)
const isVoiceModalOpen = ref(false)
const isStyleModalOpen = ref(false)
const voiceDropdownRef = ref<HTMLElement | null>(null)
const audioFileInput = ref<HTMLInputElement | null>(null)
const mediaFileInput = ref<HTMLInputElement | null>(null)
const playingAudios = ref<Set<string>>(new Set())
const loadingVoicePreviews = ref<Set<string>>(new Set())
const elevenlabsPreviewUrls = ref<Map<string, string>>(new Map())
const genericVoicePreviewElement = ref<HTMLAudioElement | null>(null)
const elevenlabsAudioElement = ref<HTMLAudioElement | null>(null)

// Computed property for selected voice object
const selectedVoiceObject = computed(() => {
  return voiceOptions.value.find(v => v.id === selectedVoice.value) || null
})

const isSupportedVoiceProvider = (provider: string | undefined): provider is VoiceProvider => {
  return provider === 'minimax' || provider === 'deepgram' || provider === 'google' || provider === 'elevenlabs'
}

const getVoiceOptionById = (voiceId?: string | null) => {
  if (!voiceId) return null
  return voiceOptions.value.find(voice => voice.id === voiceId) || null
}

const humanizeSpeakerId = (speakerId: string) =>
  speakerId
    .split(/[-_]+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')

const resolveSpeakerDisplayName = (speakerId?: string, speakerLabel?: string) => {
  if (speakerLabel?.trim()) return speakerLabel.trim()
  if (speakerId) {
    const character = charactersStore.characters.find(c => c.id === speakerId)
    if (character?.name) return character.name
    return humanizeSpeakerId(speakerId)
  }
  return 'Speaker'
}

const collectSpeakingCharacters = (sceneList: Scene[]): SpeakingCharacterSummary[] => {
  const characterMap = new Map<string, SpeakingCharacterSummary & { scene_ids: Set<string> }>()

  sceneList.forEach((scene, sceneIndex) => {
    ;(scene.dialogue_turns || []).forEach((turn, turnIndex) => {
      const text = (turn.text || '').trim()
      if (!text) return

      const fallbackLabel = turn.speaker_label?.trim() || `speaker-${turnIndex + 1}`
      const speakerId = (turn.speaker_id || slugifySpeakerLabel(fallbackLabel)).trim()
      const speakerName = resolveSpeakerDisplayName(speakerId, turn.speaker_label)
      const sceneKey = scene.id || `scene-${sceneIndex}`
      const existing = characterMap.get(speakerId)

      if (existing) {
        existing.line_count += 1
        existing.scene_ids.add(sceneKey)
        if (!existing.sample_line) {
          existing.sample_line = text
        }
        return
      }

      characterMap.set(speakerId, {
        character_id: speakerId,
        character_name: speakerName,
        scene_count: 1,
        line_count: 1,
        sample_line: text,
        scene_ids: new Set([sceneKey]),
      })
    })
  })

  return Array.from(characterMap.values())
    .map(({ scene_ids, ...character }) => ({
      ...character,
      scene_count: scene_ids.size,
      assigned_voice_id: characterVoiceMap.value[character.character_id]?.voice_id,
      assigned_provider: characterVoiceMap.value[character.character_id]?.provider,
    }))
    .sort((a, b) => {
      if (b.scene_count !== a.scene_count) return b.scene_count - a.scene_count
      if (b.line_count !== a.line_count) return b.line_count - a.line_count
      return a.character_name.localeCompare(b.character_name)
    })
}

const speakingCharacters = computed(() => collectSpeakingCharacters(scenes.value))
const hasSpeakingCharacters = computed(() => speakingCharacters.value.length > 0)

const missingCharacterVoiceAssignments = computed(() =>
  speakingCharacters.value.filter(character => {
    const assignment = characterVoiceMap.value[character.character_id]
    return !!assignment?.voice_id && !getVoiceOptionById(assignment.voice_id)
  }).length
)

const canGenerateTalkingSceneAudio = computed(() =>
  projectMode.value !== 'talking_scenes' || missingCharacterVoiceAssignments.value === 0
)

const syncCharacterVoiceAssignments = (options: { autoAssignMissing?: boolean, preserveExisting?: boolean } = {}) => {
  const { autoAssignMissing = true, preserveExisting = true } = options
  const activeCharacters = collectSpeakingCharacters(scenes.value)
  const activeIds = new Set(activeCharacters.map(character => character.character_id))
  const nextMap: Record<string, CharacterVoiceAssignment> = {}

  Object.entries(characterVoiceMap.value).forEach(([characterId, assignment]) => {
    if (activeIds.has(characterId)) {
      nextMap[characterId] = assignment
    }
  })

  characterVoiceMap.value = nextMap

  if (autoAssignMissing) {
    autoAssignCharacterVoices({ preserveExisting })
  }
}

const autoAssignCharacterVoices = (options: { preserveExisting?: boolean } = {}) => {
  const { preserveExisting = true } = options
  const availableVoices = voiceOptions.value.filter(voice => isSupportedVoiceProvider(voice.provider)) as VoiceOption[]
  if (availableVoices.length === 0) return

  const preferredVoice = selectedVoiceObject.value && isSupportedVoiceProvider(selectedVoiceObject.value.provider)
    ? [selectedVoiceObject.value as VoiceOption]
    : []
  const orderedVoices = [...preferredVoice, ...availableVoices.filter(voice => voice.id !== selectedVoice.value)]
  const usedVoiceIds = new Set<string>()
  const nextMap: Record<string, CharacterVoiceAssignment> = preserveExisting ? { ...characterVoiceMap.value } : {}

  speakingCharacters.value.forEach((character) => {
    const existingAssignment = nextMap[character.character_id]
    const existingVoice = getVoiceOptionById(existingAssignment?.voice_id)
    const shouldKeepExisting = preserveExisting && existingAssignment?.voice_id && existingVoice

    if (shouldKeepExisting) {
      usedVoiceIds.add(existingAssignment.voice_id)
      nextMap[character.character_id] = {
        ...existingAssignment,
        character_name: character.character_name,
        preview_text: character.sample_line,
        audio_speed: existingAssignment.audio_speed ?? audioSpeed.value,
      }
      return
    }

    const selectedVoiceOption =
      orderedVoices.find(voice => !usedVoiceIds.has(voice.id))
      || orderedVoices[0]

    if (!selectedVoiceOption || !isSupportedVoiceProvider(selectedVoiceOption.provider)) {
      return
    }

    usedVoiceIds.add(selectedVoiceOption.id)
    nextMap[character.character_id] = {
      character_id: character.character_id,
      character_name: character.character_name,
      voice_id: selectedVoiceOption.id,
      provider: selectedVoiceOption.provider,
      audio_speed: existingAssignment?.audio_speed ?? audioSpeed.value,
      preview_text: character.sample_line,
      locked: existingAssignment?.locked ?? false,
    }
  })

  characterVoiceMap.value = nextMap
}

const updateCharacterVoiceAssignment = (characterId: string, voiceId: string) => {
  const character = speakingCharacters.value.find(item => item.character_id === characterId)
  if (!character) return

  if (!voiceId) {
    const nextMap = { ...characterVoiceMap.value }
    delete nextMap[characterId]
    characterVoiceMap.value = nextMap
    return
  }

  const voice = getVoiceOptionById(voiceId)
  if (!voice || !isSupportedVoiceProvider(voice.provider)) return

  characterVoiceMap.value = {
    ...characterVoiceMap.value,
    [characterId]: {
      character_id: characterId,
      character_name: character.character_name,
      voice_id: voice.id,
      provider: voice.provider,
      audio_speed: characterVoiceMap.value[characterId]?.audio_speed ?? audioSpeed.value,
      preview_text: character.sample_line,
      locked: characterVoiceMap.value[characterId]?.locked ?? false,
    },
  }
}

const handleCharacterVoiceSelection = (characterId: string, event: Event) => {
  const target = event.target as HTMLSelectElement | null
  updateCharacterVoiceAssignment(characterId, target?.value || '')
}

const updateCharacterVoiceSpeed = (characterId: string, nextSpeed: number) => {
  const character = speakingCharacters.value.find(item => item.character_id === characterId)
  if (!character) return

  const existingAssignment = characterVoiceMap.value[characterId]
  const fallbackVoice = getVoiceOptionById(existingAssignment?.voice_id) || selectedVoiceObject.value
  if (!fallbackVoice || !isSupportedVoiceProvider(fallbackVoice.provider)) return

  const normalizedSpeed = Number(nextSpeed.toFixed(2))
  characterVoiceMap.value = {
    ...characterVoiceMap.value,
    [characterId]: {
      character_id: characterId,
      character_name: character.character_name,
      voice_id: existingAssignment?.voice_id || fallbackVoice.id,
      provider: existingAssignment?.provider || fallbackVoice.provider,
      audio_speed: normalizedSpeed,
      preview_text: existingAssignment?.preview_text || character.sample_line,
      locked: existingAssignment?.locked ?? false,
    },
  }
}

const handleCharacterVoiceSpeedChange = (characterId: string, event: Event) => {
  const target = event.target as HTMLInputElement | null
  if (!target) return
  updateCharacterVoiceSpeed(characterId, Number(target.value))
}

const previewCharacterVoice = async (characterId: string) => {
  const assignment = characterVoiceMap.value[characterId]
  const voice = getVoiceOptionById(assignment?.voice_id) || selectedVoiceObject.value
  if (!voice) {
    toast.error('No voice available to preview')
    return
  }
  await toggleAudioPlayback(voice)
}

// Image Generation Settings
const imageAspectRatio = ref<'9:16' | '16:9' | '1:1'>(
  (sessionStorage.getItem('imageAspectRatio') as '9:16' | '16:9' | '1:1') || '9:16'
)
const imageAspectRatios = ref<{ value: '9:16' | '16:9' | '1:1', label: string }[]>([
  { value: '16:9', label: 'Horizontal' },
  { value: '1:1', label: 'Square' },
  { value: '9:16', label: 'Vertical' },
])

// All available image generation models
const STANDARD_IMAGE_MODEL = 'prunaai/z-image-turbo:7ea16386290ff5977c7812e66e462d7ec3954d8e007a8cd18ded3e7d41f5d7cf'
const LEGACY_STANDARD_1_IMAGE_MODEL = 'black-forest-labs/flux-schnell'
const allImageGenerationModels = [
  {value: STANDARD_IMAGE_MODEL, label: 'Standard'},
  {value:'gemini-3.1-flash-image-preview', label: 'Plus Quality'}, // Gemini image (GOOGLE_API_KEY)
  {value:'openai/gpt-image-2', label: 'Plus Quality 2'}, // Replicate openai/gpt-image-2
]

const imageGenerationModels = computed(() => allImageGenerationModels)

const storedImageGenerationModel = sessionStorage.getItem('imageGenerationModel')
const imageGenerationModel = ref(
  storedImageGenerationModel === LEGACY_STANDARD_1_IMAGE_MODEL
    ? STANDARD_IMAGE_MODEL
    : (storedImageGenerationModel || STANDARD_IMAGE_MODEL)
)

const getModelCompatibleImageAspectRatio = (
  model: string,
  aspectRatio: '9:16' | '16:9' | '1:1'
): string => {
  if (model === 'openai/gpt-image-2') {
    if (aspectRatio === '16:9') return '3:2'
    if (aspectRatio === '9:16') return '2:3'
  }
  return aspectRatio
}

const getImageDimensionsForAspectRatio = (aspectRatio: '9:16' | '16:9' | '1:1') => {
  if (aspectRatio === '9:16') return { width: 720, height: 1280 }
  if (aspectRatio === '1:1') return { width: 1024, height: 1024 }
  return { width: 1280, height: 720 }
}

const getAspectRatioFrameClass = (aspectRatio?: string) => {
  if (aspectRatio === '9:16') return 'aspect-[9/16]'
  if (aspectRatio === '1:1') return 'aspect-square'
  return 'aspect-video'
}

// Image Style Keywords
const selectedImageStyles = ref<string[]>([])
const newStyleKeyword = ref('')
const imageStyleSuggestions = ref([
  'cinematic', 'anime', 'oil painting', 'watercolor', 'photorealistic', 'fantasy',
  'cyberpunk', 'vintage', 'minimalist', 'gothic', 'impressionist', 'cartoon',
  'realistic', 'abstract', 'surreal', 'noir', 'pastel', 'neon', 'chinese watercolor'
])

// Video Settings
const videoAspectRatio = ref<'9:16' | '16:9' | '1:1'>(
  (sessionStorage.getItem('videoAspectRatio') as '9:16' | '16:9' | '1:1') || '9:16'
)
const videoAspectRatios = ref<{ value: '9:16' | '16:9' | '1:1', label: string }[]>([
  { value: '16:9', label: 'Horizontal (16:9)' },
  { value: '1:1', label: 'Square (1:1)' },
  { value: '9:16', label: 'Vertical (9:16)' },
])

// Video format indicator (v = vertical, h = horizontal, s = square)
const videoFormat = computed(() => {
  if (videoAspectRatio.value === '9:16') return 'v'
  if (videoAspectRatio.value === '16:9') return 'h'
  return 's'
})

const videoResolution = ref<StoryboardVideoResolution>('1080p')
const videoResolutions = ref<{ value: StoryboardVideoResolution, label: string }[]>([
  { value: '720p', label: '720p (HD)' },
  { value: '1080p', label: '1080p (Full HD)' },
  { value: '2k_option_1', label: '2K (Quad HD)' },
])
const selectedVideoResolutionLabel = computed(() => {
  return videoResolutions.value.find((resolution) => resolution.value === videoResolution.value)?.label || videoResolution.value
})

const captionEnabled = ref(true)
const captionPosition = ref<'top' | 'center' | 'bottom'>('bottom')
const captionPositions = ref<{ value: 'top' | 'center' | 'bottom', label: string }[]>([
  { value: 'top', label: 'Top' },
  { value: 'center', label: 'Center' },
  { value: 'bottom', label: 'Bottom' },
])
const captionStyle = ref<'karaoke' | 'word_by_word' | 'sentence'>('karaoke')
const captionStyles = ref<{ value: 'karaoke' | 'word_by_word' | 'sentence', label: string, previewGif: string }[]>([
  { value: 'karaoke', label: 'Karaoke', previewGif: karaokeStyleGif },
  { value: 'word_by_word', label: 'Word by Word', previewGif: wordByWordStyleGif },
  { value: 'sentence', label: 'Sentence', previewGif: sentenceStyleGif },
])

// Caption style hover preview state
const stylePreviewVisible = ref(false)
const stylePreviewGif = ref('')
const stylePreviewPosition = ref({ x: 0, y: 0 })

const showStylePreview = (gif: string, event: MouseEvent) => {
  stylePreviewGif.value = gif
  stylePreviewPosition.value = { x: event.clientX + 15, y: event.clientY + 15 }
  stylePreviewVisible.value = true
}

const updateStylePreviewPosition = (event: MouseEvent) => {
  stylePreviewPosition.value = { x: event.clientX + 15, y: event.clientY + 15 }
}

const hideStylePreview = () => {
  stylePreviewVisible.value = false
}
const captionFont = ref('Luckiest Guy')
const captionFontSize = ref(60)

// Available font sizes
const fontSizes = [
  { value: 40, label: 'Small' },
  { value: 60, label: 'Medium' },
  { value: 80, label: 'Large' },
]

// All available fonts
const allFonts = [
  { value: 'Luckiest Guy', label: 'Luckiest Guy', isChinese: false },
  {value: 'Story Script', label: 'Story Script', isChinese: false},
  {value: 'Macondo', label: 'Macondo', isChinese: false},
  {value: 'Popins', label: 'Popins', isChinese: false},
  {value: 'Chewy', label: 'Chewy', isChinese: false},
  { value: 'nishiki-teki-2', label: 'Marker', isChinese: false },
  
  // { value: 'qingsong', label: '清松手写体', isChinese: true },
  // { value: 'laihu', label: '濑户体', isChinese: true },
  // { value: 'yangrendongzhushi', label: '杨任东竹石', isChinese: true },
  // { value: 'zhankukuaile', label: '站酷快乐', isChinese: true },
  { value: 'yousheyufeitejiankangti', label: 'Shark', isChinese: true }
]

// Font file mappings
const fontMappings: Record<string, string> = {
  'Luckiest Guy': 'fonts/LuckiestGuy-Regular.ttf',
  'nishiki-teki-2': 'fonts/nishikie-teki-2.ttf',
  'qingsong': 'fonts/qingsong.ttf',
  'laihu': 'fonts/laihu.ttf',
  'yangrendongzhushi': 'fonts/yangrendongzhushi.ttf',
  'zhankukuaile': 'fonts/zhankukuaile.ttf',
  'yousheyufeitejiankangti': 'fonts/yousheyufeitejiankangti.ttf'
}

// Filter fonts based on user type
const availableFonts = computed(() => {
  const userType = authStore.user?.type
  // If user is not admin, filter out Chinese fonts
  if (userType !== 'admin') {
    return allFonts.filter(font => !font.isChinese)
  }
  // Admin users see all fonts
  return allFonts
})

// Visual Style Templates
const selectedStyleTemplate = ref<string | null>(null)
const VOX_ANIMATION_PROMPT = 'Generate a keyframe in an encyclopedic collage style, suitable for an educational video. The visual style should resemble a page from a historical encyclopedia, a scrapbook collage or paper-cutout explainer, composed of various figures, objects, maps, buildings, artifacts, text cards, labels, arrows, route lines, and stickers. Requirements: Avoid a single-poster layout or a composition dominated by one large object; ensure the image is information-rich yet clearly layered. Utilize elements such as paper cutouts, objects with white borders, paper drop shadows, adhesive tape, labels, stamps, and map fragments. Ensure each key element has distinct edges and slightly bold outlines to facilitate recognition as an independently movable asset for video animation. Maintain a collage aesthetic featuring paper textures and qualities. The image should look like an interactive encyclopedia page ready for animation, not a static PowerPoint slide. Avoid photorealistic cinematic styles, 3D rendering, or the look of a polished commercial poster.'
const VOX_SCENE_TO_VIDEO_PROMPT = `animation requirement:

Maintain a paper-cutout, scrapbook, or stop-motion collage style.

All elements (characters, maps, text cards, coins, tracks, arrows, etc.) should move as independent cut-out assets.
Animations should feature: a "frame-skipping" (stop-motion) feel, slight paper-like jitter, stepped movement, and sticker-style bouncing.

Potential small actions to include:

Arrows advancing, routes extending, coins spinning, stamps pressing down, bamboo scrolls unrolling, weights being calibrated, carriages moving forward with a stop-motion effect, and modules activating one by one.

Note:
Avoid aimless camera movement.
Keep the main composition and key text steady.
No voice, no sound effects, no music.
Ensure each shot features a "distinct, specific action" rather than just aimless floating.`
const styleTemplates = [

  {
    id: 'realistic',
    name: 'Realistic',
    description: 'Realistic Images',
    prompt: 'generate photorealistic image. the photo should have the candid, natural feel.'
  },
  {
    id: 'handdrawn-simple',
    name: 'Handrawn Illustration',
    description: 'Hand drawn Illustration',
    prompt: 'The background is a warm, textured beige paper, creating an inviting atmosphere. all objects should be drawn with bold black lines, and vibrant color. creating an inviting atmosphere. The illustration style is clean, modern, and inspiring, with a focus on the simple beauty of the objects. '
  },
  {
    id: 'oil-painting',
    name: 'Oil Painting',
    description: 'Oil Painting',
    prompt: 'create image in oil painting style, thick impasto, rugged brushwork, distinct bold strokes. **no signatures**'
  },
  {
    id: 'handdrawn-infographic',
    name: 'Handrawn Infographic',
    description: 'Hand drawn Illustration',
    prompt: 'Please create an infographic based on the input content, highlighting key themes and essential points: - Simplify information, emphasizing keywords and core concepts, leaving ample whitespace for clarity. - Include minimalistic cartoon elements, icons, or simple portraits of famous figures to enhance engagement and visual recall. - All text and images should strictly have hand-drawn black ink outline, and use colored chalk style without realistic illustrations. - Unless specifically requested, maintain the original language of the input content. - The background is a warm, textured beige paper, creating an inviting atmosphere.The illustration style is clean, modern, and inspiring, with a focus on the simple beauty of the objects.'
  },
  {
    id: 'vox-animation',
    name: 'Vox Animation',
    description: 'Encyclopedic collage explainer style',
    prompt: VOX_ANIMATION_PROMPT
  },
  {
    id: 'cinematic',
    name: 'Cinematic',
    description: 'Hollywood movie style with dramatic lighting',
    prompt: 'Create scenes with cinematic composition, dramatic lighting, and film-like depth of field. Use Hollywood movie aesthetics with professional color grading.'
  },
  {
    id: 'anime',
    name: 'Anime',
    description: 'Japanese anime art style',
    prompt: 'Generate scenes in Japanese anime art style with vibrant colors, expressive characters, and dynamic compositions typical of high-quality anime productions.'
  },
  {
    id: 'watercolor',
    name: 'Watercolor',
    description: 'Soft watercolor painting style',
    prompt: 'Create scenes that look like beautiful watercolor paintings with soft edges, flowing colors, and artistic brushstrokes. Use gentle color transitions and dreamy atmospheres.'
  },
  {
    id: 'cyberpunk',
    name: 'Cyberpunk',
    description: 'Futuristic neon-lit cyberpunk aesthetic',
    prompt: 'Generate scenes in cyberpunk style with neon lights, futuristic technology, dark urban environments, and vibrant pink/blue/purple color schemes. Include sci-fi elements and high-tech details.'
  },
  {
    id: 'fantasy',
    name: 'Fantasy',
    description: 'Magical fantasy world aesthetic',
    prompt: 'Create scenes in a magical fantasy style with enchanted environments, mystical lighting, and dreamlike qualities. Include fantasy elements like magic, mythical creatures, and otherworldly landscapes.'
  },
  {
    id: "kids-Story",
    name: "Kids' Story",
    description: "Kids' story style",
    prompt: "Generate an illustration in a whimsical, childlike style, typical of children's book illustrations. Style/Technique: Outline the contours with loose black ink sketch lines (hand-drawn quality). Details should not be overly realistic. Layer gentle watercolor washes and stippling/dots for color. The colors should be clean, warm, and show a slight paper texture. Mood/Application: The atmosphere should be genuine, comforting/healing, and slightly nostalgic. Suitable for a postcard, children's picture book, Christmas advertising campaign, or emotional editorial illustration. Composition: Simple composition. Comfortable negative space (or white space). The main subject should be clearly prominent/highlighted. Exclusions (Negative Prompts): NO photorealism/photographic quality. NO 3D render feel. NO overly sharp details. NO watermarks or logos."
  },
  {
    id: "pixar-style",
    name: "Pixar Style",
    description: "Pixar style, 3D",
    prompt: "Generate in Pixar studio style"
  },
  {
    id: "3d-cartoon",
    name: "3D Cartoon Style",
    description: "Pixar style, 3D",
    prompt: "Full-body 3D caricature in Pixar/DreamWorks style, featuring expressive large eyes, slightly oversized head, and subtly exaggerated facial features. Realistic skin with soft subsurface scattering, detailed hair, and a gentle warm smile. Smooth polished surfaces with subtle fabric texture on clothing. Dynamic pose showing personality, with full body visible and balanced proportions. Soft ambient lighting, warm reddish-orange gradient background. Cinematic quality, high detail, vibrant yet natural colors, stylized charm with balanced realism."
  },
  {
    id: 'animal-haircut',
    name: 'Animal Haircut',
    description: 'Before/after grooming storyboard',
    prompt: 'Generate an animal haircut makeover storyboard prompt package.'
  },
  {
    id: 'viral-skeleton',
    name: 'Viral Skeleton',
    description: '3D medical animation skeleton style',
    prompt: 'create an image with main character being a skeleton, A high-quality 3D medical animation style render of a realistic beige human skeleton encased inside a transparent, clear, glass-like human body silhouette. The character has large, wide, expressive eyes that convey emotion. The texture of the skin is like clear jelly or glass. Soft, cinematic studio lighting. Ultra-realistic materials, subsurface scattering, volumetric light. High definition, 8K resolution,UunrealEengine 5 render style'
  },
  
  {
    id: 'blackboard',
    name: 'Blackboard',
    description: 'Clean and simple minimalist design drawn on a blackboard',
    prompt: 'Please create an infographic based on the input content, highlighting key themes and essential points: - Simplify information, emphasizing keywords and core concepts, leaving ample whitespace for clarity. - Include minimalistic cartoon elements, icons, or simple portraits of famous figures to enhance engagement and visual recall. - All text and images should strictly use colored chalk style without realistic illustrations. - Unless specifically requested, maintain the original language of the input content. - Use a black chalkboard background and colorful chalk drawing style.'
  },
  {
    id: 'whiteboard',
    name: 'Whiteboard',
    description: 'Clean and simple minimalist design drawn on a whiteboard',
    prompt: 'Please create an infographic based on the input content, highlighting key themes and essential points: - Simplify information, emphasizing keywords and core concepts, leaving ample whitespace for clarity. - Include minimalistic cartoon elements, icons, or simple portraits of famous figures to enhance engagement and visual recall. - All text and images should strictly have hand-drawn black ink outline, and use colored chalk style without realistic illustrations. - Unless specifically requested, maintain the original language of the input content. - Use a white background and colorful chalk drawing style.'
  },
  {
    id: 'vintage',
    name: 'Vintage',
    description: 'Retro nostalgic photography style',
    prompt: 'Create scenes with vintage photography aesthetic, warm nostalgic tones, slight grain, and retro color grading. Evoke feelings of nostalgia with classic composition styles.'
  },
  {
    id: 'stick-figure',
    name: 'Stick Figure',
    description: 'Retro nostalgic photography style',
    prompt: 'Generate image with stickfigure style, use the @stickfigure character to generate the image.'
  },
  {
    id: 'comic',
    name: 'Comic Book',
    description: 'Bold comic book illustration style',
    prompt: 'Generate scenes in comic book illustration style with bold lines, vibrant colors, dynamic angles, and dramatic compositions. Include halftone effects and comic-style action.'
  }
]

// Scenes data
interface TextLayer {
  id: string
  text: string
  startTime: number      // seconds
  endTime: number        // seconds
  x: number              // 0-100%
  y: number              // 0-100%
  fontSize: number
  fontColor: string
  fontWeight: 'normal' | 'bold'
  fontStyle?: 'normal' | 'italic'
  fontFamily: string
  textAlign?: 'left' | 'center' | 'right'
  backgroundColor: string
  backgroundOpacity?: number  // 0-1
  boxPaddingX?: number        // horizontal padding px
  boxPaddingY?: number        // vertical padding px
  boxBorderRadius?: number    // border radius px
  strokeColor?: string
  strokeWidth?: number
  opacity?: number        // 0-1, whole layer
  letterSpacing?: number  // px
  animation: 'none' | 'fade-in' | 'slide-up' | 'slide-down'
}

// Google Font base names — used to auto-inject <link> tags at runtime
const GOOGLE_FONTS = new Set([
  // Sans-serif
  'Roboto', 'Open Sans', 'Lato', 'Montserrat', 'Oswald', 'Raleway', 'Nunito', 'Inter',
  'Poppins', 'Jost', 'Barlow', 'Source Sans 3', 'Rubik', 'Manrope', 'DM Sans', 'Outfit',
  'Figtree', 'Plus Jakarta Sans', 'Exo 2',
  // Serif
  'Playfair Display', 'Merriweather', 'Lora', 'Libre Baskerville', 'EB Garamond',
  'Cormorant Garamond', 'Crimson Text',
  // Display / Impact
  'Bebas Neue', 'Anton', 'Bangers', 'Righteous', 'Passion One', 'Staatliches',
  'Fredoka One', 'Luckiest Guy', 'Black Han Sans', 'Boogaloo', 'Lilita One',
  // Handwriting / Script
  'Pacifico', 'Dancing Script', 'Lobster', 'Caveat', 'Sacramento', 'Great Vibes',
  'Satisfy', 'Architects Daughter', 'Kalam',
  // Monospace
  'Source Code Pro', 'Space Mono', 'Fira Code', 'JetBrains Mono',
])

/** Convert a hex color + opacity (0-1) to a CSS rgba() string */
function hexToRgba(hex: string, opacity: number): string {
  if (!hex || hex === 'transparent' || opacity === 0) return 'transparent'
  const h = hex.replace('#', '')
  const r = parseInt(h.substring(0, 2), 16)
  const g = parseInt(h.substring(2, 4), 16)
  const b = parseInt(h.substring(4, 6), 16)
  return `rgba(${r},${g},${b},${opacity})`
}

/** Inject a Google Font <link> tag into <head> if not already loaded */
function loadGoogleFont(family: string) {
  const base = family.split(',')[0].trim().replace(/['"]/g, '')
  if (!GOOGLE_FONTS.has(base)) return
  const sel = `link[data-gf="${CSS.escape(base)}"]`
  if (document.querySelector(sel)) return
  const l = document.createElement('link')
  l.rel = 'stylesheet'
  l.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(base)}:wght@400;700&display=swap`
  l.setAttribute('data-gf', base)
  document.head.appendChild(l)
}

interface Scene {
  id: string
  description: string  // Original sentence from script
  prompt: string       // AI-generated image prompt
  scene_type?: 'dialogue' | 'monologue' | 'broll' | 'mixed'
  scene_script?: string
  layout_type?: 'single' | 'two_shot' | 'group' | 'speaker_focus'
  target_duration?: number
  start_time?: number
  end_time?: number
  character_ids?: string[]
  dialogue_turns?: Array<{
    id?: string
    speaker_id?: string
    speaker_label?: string
    text: string
    voice_id?: string
    voice_override?: boolean
    provider?: VoiceProvider
    audio_speed?: number
    start_time?: number
    end_time?: number
    duration?: number
    visual_state?: string
  }>
  character_layout?: Array<{
    character_id?: string
    slot?: string
    x?: number
    y?: number
    scale?: number
    z_index?: number
  }>
  generatedImage?: {
    id?: string
    url: string
    width: number
    height: number
    aspectRatio: string
  }
  animationPrompt?: string
  animationModel?: string
  animationResolution?: string
  animationDuration?: number
  animatedVideo?: {
    id: string
    url: string
    duration: number
    thumbnailUrl?: string
  }
  isGenerating: boolean
  generationProgress: number
  camera_movement?: string
  transition_type?: string
  transition_duration?: number
  greenscreen_effect?: string
  sceneAudio?: {
    fileId?: string
    url: string
    duration: number
    transcript?: string
  }
}

interface ProjectThumbnail {
  id: string
  imageId?: string
  url: string
  width: number
  height: number
  aspectRatio: string
  prompt: string
  createdAt: string
}

const scenes = ref<Scene[]>([])

function normalizeVideoModelSelection(model?: string | null): string {
  if (!model) return 'wan-video/wan-2.2-i2v-fast'
  const legacyVideoModelMap: Record<string, string> = {
    'bytedance/seedance-1-pro-fast': 'bytedance/seedance-2.0',
  }
  return legacyVideoModelMap[model] || model
}

function isSeedance1Model(model?: string | null): boolean {
  return (model || '').toLowerCase().includes('seedance-1')
}

function supports1080pVideoModel(model?: string | null): boolean {
  return model === 'veo-3.1-fast-generate-preview' || isSeedance1Model(model)
}

function isSeedance2Model(model?: string | null): boolean {
  return (model || '').toLowerCase().includes('seedance-2')
}

function isForced480pVideoModel(model?: string | null): boolean {
  return false
}

function isKling3VideoModel(model?: string | null): boolean {
  return (model || '').toLowerCase() === 'kwaivgi/kling-v3-video'
}

function isKling21VideoModel(model?: string | null): boolean {
  const normalizedModel = (model || '').toLowerCase()
  return normalizedModel === 'kwaivgi/kling-v2.1' || normalizedModel === 'kling-video/kling2.1'
}

function isKling26VideoModel(model?: string | null): boolean {
  return (model || '').toLowerCase() === 'kwaivgi/kling-v2.6'
}

function isGeminiOmniVideoModel(model?: string | null): boolean {
  return (model || '').toLowerCase() === 'gemini-omni-flash-preview'
}

function supportsEndFrameVideoModel(model?: string | null): boolean {
  return (model || '').startsWith('wan-video/')
    || model === 'veo-3.1-fast-generate-preview'
    || isSeedance2Model(model)
    || isKling3VideoModel(model)
}

function getVideoModelLabel(model?: string | null): string {
  if (model === 'wan-video/wan-2.2-i2v-fast') return 'Wan Video'
  if (isGeminiOmniVideoModel(model)) return 'Gemini Omni Flash'
  if (model === 'veo-3.1-fast-generate-preview') return 'Veo 3.1 Fast'
  if (isKling21VideoModel(model)) return 'Kling 2.1'
  if (isKling26VideoModel(model)) return 'Kling 2.6'
  if (model === 'kwaivgi/kling-v3-video') return 'Kling 3'
  if (model === 'kwaivgi/kling-avatar-v2') return 'Kling Avatar'
  if (model === 'manim') return 'Manim'
  return 'Seedance 2'
}

const normalizeSceneAudio = (sceneLike: any): Scene['sceneAudio'] | undefined => {
  const audio = sceneLike?.sceneAudio || sceneLike?.scene_audio || sceneLike?.audio || sceneLike?.audio_file
  const url = audio?.url || audio?.file_url || sceneLike?.audioUrl || sceneLike?.audio_url || sceneLike?.file_url
  if (!url) return undefined

  return {
    fileId: audio?.fileId || audio?.file_id || audio?.id || sceneLike?.audioFileId || sceneLike?.audio_file_id || sceneLike?.audio_id,
    url,
    duration: Number(audio?.duration || sceneLike?.audioDuration || sceneLike?.audio_duration || 0),
    transcript: audio?.transcript || sceneLike?.transcript,
  }
}

const mapApiSceneToUiScene = (scene: any, index: number): Scene => ({
  id: scene.id || crypto.randomUUID(),
  description: scene.description || `Scene ${index + 1}`,
  prompt: scene.prompt || scene.description || `Scene ${index + 1}`,
  scene_type: scene.scene_type || 'dialogue',
  scene_script: scene.scene_script || scene.description || '',
  layout_type: scene.layout_type || 'single',
  target_duration: scene.target_duration,
  start_time: scene.start_time,
  end_time: scene.end_time,
  character_ids: scene.character_ids || [],
  dialogue_turns: (scene.dialogue_turns || []).map((turn: any) => ({
    ...turn,
    provider: turn.provider,
    audio_speed: turn.audio_speed,
    voice_override: turn.voice_override,
  })),
  character_layout: scene.character_layout || [],
  generatedImage: scene.generated_image ? {
    id: scene.generated_image.id,
    url: scene.generated_image.url,
    width: scene.generated_image.width || 1024,
    height: scene.generated_image.height || 1024,
    aspectRatio: scene.generated_image.aspect_ratio || scene.generated_image.aspectRatio || '1:1',
  } : undefined,
  animationPrompt: scene.animation_prompt || scene.animationPrompt || buildTalkingAnimationPrompt(scene),
  animatedVideo: scene.animated_video ? {
    id: scene.animated_video.id,
    url: scene.animated_video.url,
    duration: scene.animated_video.duration || 0,
    thumbnailUrl: scene.animated_video.url,
  } : undefined,
  isGenerating: false,
  generationProgress: 0,
  camera_movement: scene.camera_movement || 'static',
  transition_type: scene.transition_type || 'fade',
  transition_duration: scene.transition_duration || 0.5,
  greenscreen_effect: scene.greenscreen_effect || '',
  sceneAudio: normalizeSceneAudio(scene),
})

const getSceneAudioUrl = (scene?: Scene | null): string => {
  return normalizeSceneAudio(scene)?.url || ''
}

const getSceneAudioDuration = (scene?: Scene | null): number => {
  return normalizeSceneAudio(scene)?.duration || 0
}

const getKlingAvatarAudioUrl = (scene?: Scene | null): string => {
  return getSceneAudioUrl(scene) || generatedAudio.value?.url || ''
}

const selectedScene = computed(() => (
  selectedSceneForPreview.value !== null
    ? scenes.value[selectedSceneForPreview.value] || null
    : null
))

const selectedSceneHasKlingAvatarAudio = computed(() => Boolean(getKlingAvatarAudioUrl(selectedScene.value)))
const hasGeneratedSceneAudio = computed(() => scenes.value.length > 0 && scenes.value.every(scene => !!getSceneAudioUrl(scene)))

// Layout state - switches to storyboard layout after generating scenes
const showStoryboardLayout = ref(false)

// Selected scene for preview in large preview area (when in storyboard layout)
const selectedSceneForPreview = ref<number | null>(null)
const showingFinalVideo = ref(false) // Track if showing final video instead of scene
const showingGallery = ref(false) // Track if showing gallery view
const showingPreview = ref(false) // Track if showing Remotion preview tab
const showingThumbnail = ref(false) // Track if showing thumbnail generation view
const thumbnailPrompt = ref('')
const thumbnailImages = ref<ProjectThumbnail[]>([])
const selectedThumbnailIndex = ref<number | null>(null)
const isGeneratingThumbnail = ref(false)
const selectedThumbnail = computed(() => (
  selectedThumbnailIndex.value !== null
    ? thumbnailImages.value[selectedThumbnailIndex.value] || null
    : thumbnailImages.value[0] || null
))
const isSceneReorderDisabled = computed(() => (
  isGeneratingAudio.value
  || isGeneratingScenes.value
  || isGeneratingImages.value
  || isGeneratingVideo.value
  || isGeneratingSceneAudio.value
))

// Remotion frame position derived from timeline currentTime
const remotionCurrentFrame = computed(() => Math.round((currentTime.value ?? 0) * 30))

const textLayers = ref<TextLayer[]>([])

// Draggable text layer state
const selectedTextLayerId = ref<string | null>(null)
const previewContainerRef = ref<HTMLDivElement | null>(null)
const previewContainerW = ref(0)
const previewContainerH = ref(0)
const previewRemotionPlayerRef = ref<any>(null)
const previewTimelineRef = ref<any>(null)

// Sync: prevent infinite play/pause loops when the two players call each other
let _syncingPlayback = false

function handlePreviewCurrentFrame(frame: number) {
  currentTime.value = frame / 30
}

function handlePreviewPlayerPlay() {
  if (_syncingPlayback) return
  _syncingPlayback = true
  try { previewTimelineRef.value?.play() } finally { _syncingPlayback = false }
}

function handlePreviewPlayerPause() {
  if (_syncingPlayback) return
  _syncingPlayback = true
  try { previewTimelineRef.value?.pause() } finally { _syncingPlayback = false }
}

function handlePreviewTimelinePlay() {
  if (_syncingPlayback) return
  _syncingPlayback = true
  try { previewRemotionPlayerRef.value?.play() } finally { _syncingPlayback = false }
}

function handlePreviewTimelinePause() {
  if (_syncingPlayback) return
  _syncingPlayback = true
  try { previewRemotionPlayerRef.value?.pause() } finally { _syncingPlayback = false }
}

const previewCompW = computed(() => imageAspectRatio.value === '9:16' ? 1080 : 1920)
const previewCompH = computed(() => imageAspectRatio.value === '9:16' ? 1920 : 1080)
const previewScale = computed(() => {
  if (!previewContainerW.value || !previewContainerH.value) return 1
  return Math.min(previewContainerW.value / previewCompW.value, previewContainerH.value / previewCompH.value)
})

// Which scene is currently showing based on timeline position
const activeSceneIndex = computed(() => {
  if (scenes.value.length === 0) return 0
  const fps = 30
  const transitionFrames = scenes.value.map(s => Math.round((s.transition_duration ?? 1) * fps))
  const sceneDurations = scenes.value.map((s, i) => {
    let d = 90
    if (s.start_time != null && s.end_time != null)
      d = Math.max(1, Math.round((s.end_time - s.start_time) * fps))
    const nextTrans = i < scenes.value.length - 1 ? transitionFrames[i] : 0
    const prevTrans = i > 0 ? transitionFrames[i - 1] : 0
    return Math.max(d, nextTrans, prevTrans)
  })
  const frame = remotionCurrentFrame.value
  let elapsed = 0
  for (let i = 0; i < scenes.value.length; i++) {
    if (frame < elapsed + sceneDurations[i]) return i
    elapsed += sceneDurations[i] + (i < scenes.value.length - 1 ? transitionFrames[i] : 0)
  }
  return scenes.value.length - 1
})

// Session storage persistence for user preferences
watch(imageGenerationModel, (newValue) => {
  if (newValue === LEGACY_STANDARD_1_IMAGE_MODEL) {
    imageGenerationModel.value = STANDARD_IMAGE_MODEL
    sessionStorage.setItem('imageGenerationModel', STANDARD_IMAGE_MODEL)
    return
  }
  sessionStorage.setItem('imageGenerationModel', newValue)
}, { immediate: true })

watch(imageAspectRatio, (newValue) => {
  sessionStorage.setItem('imageAspectRatio', newValue)
})

watch(sceneDetailsVideoModel, (newValue) => {
  sessionStorage.setItem('sceneDetailsVideoModel', newValue)
  if (isKling21VideoModel(newValue)) {
    sceneDetailsVideoDuration.value = 5
    sceneDetailsVideoResolution.value = '720p'
  }
  if (isKling26VideoModel(newValue)) {
    sceneDetailsVideoDuration.value = 5
    sceneDetailsVideoResolution.value = '720p'
  }
  if (isKling3VideoModel(newValue)) {
    sceneDetailsVideoDuration.value = 3
    sceneDetailsVideoResolution.value = '720p'
  }
  if (isGeminiOmniVideoModel(newValue)) {
    sceneDetailsVideoDuration.value = 8
    sceneDetailsVideoResolution.value = '720p'
  }
  if (isForced480pVideoModel(newValue) && sceneDetailsVideoResolution.value !== '480p') {
    sceneDetailsVideoResolution.value = '480p'
  }
  // Reset resolution to 720p if switching to a model that does not support 1080p.
  if (
    !supports1080pVideoModel(newValue) &&
    sceneDetailsVideoResolution.value === '1080p'
  ) {
    sceneDetailsVideoResolution.value = '720p'
  }
  if (newValue === 'veo-3.1-fast-generate-preview' && ![4, 6, 8].includes(sceneDetailsVideoDuration.value)) {
    sceneDetailsVideoDuration.value = 4
  }
})

watch(sceneDetailsVideoResolution, (newValue) => {
  sessionStorage.setItem('sceneDetailsVideoResolution', newValue)
})

// Clear start/end frames when switching scenes
watch(selectedSceneForPreview, () => {
  imageReferenceImage.value = null
  startFrameImage.value = null
  endFrameImage.value = null
})

watch(manimMode, (newValue) => {
  sessionStorage.setItem('manimMode', newValue)
})

watch(manimQuality, (newValue) => {
  sessionStorage.setItem('manimQuality', newValue)
})

watch(manimAspectRatio, (newValue) => {
  sessionStorage.setItem('manimAspectRatio', newValue)
})

watch(videoAspectRatio, (newValue) => {
  sessionStorage.setItem('videoAspectRatio', newValue)
})

watch(sceneAggregationMode, (newValue) => {
  sessionStorage.setItem('sceneAggregationMode', newValue)
})

// Load Google Fonts for text layers whenever they change
watch(textLayers, (layers) => {
  layers.forEach(tl => loadGoogleFont(tl.fontFamily))
}, { deep: true, immediate: true })

// Sync projectId with route params (for browser navigation)
watch(() => route.params.id, (newId) => {
  projectId.value = newId as string | undefined
})

// Watch for scene changes (debugging)
watch(scenes, (newScenes) => {
  logger.log('Scenes updated:', newScenes.map(s => ({
    id: s.id,
    hasImage: !!s.generatedImage,
    imageUrl: s.generatedImage?.url ? s.generatedImage.url.substring(0, 50) + '...' : null
  })))
}, { deep: true })

// Watch for storyboard layout changes - auto-select first scene
watch(showStoryboardLayout, (newValue) => {
  if (newValue && scenes.value.length > 0 && !showingFinalVideo.value && !showingGallery.value && !showingThumbnail.value) {
    selectedSceneForPreview.value = 0
  } else if (!newValue) {
    selectedSceneForPreview.value = null
  }
})

// Watch for gallery view - load gallery images and folders
watch(showingGallery, async (newValue) => {
  if (newValue) {
    try {
      await Promise.all([
        imageGenerationStore.fetchGallery(true),
        imageGenerationStore.fetchFolders()
      ])
      // Note: Don't batch refresh URLs here - fetchGallery returns fresh URLs from the API
      // URLs will be refreshed on-demand if needed (when images are actually used)
    } catch (error) {
      console.error('Failed to load gallery:', error)
      toast.error('Failed to load gallery images')
    }
  }
})

// Sync hasMore state with store pagination for both gallery components
watch(() => imageGenerationStore.gallery.pagination.hasMore, (hasMore) => {
  if (galleryViewRef.value) {
    galleryViewRef.value.setHasMore(hasMore)
  }
  if (gallerySelectorRef.value) {
    gallerySelectorRef.value.setHasMore(hasMore)
  }
})

// Watch scene details prompt to auto-update character references when @ mentions change
watch(sceneDetailsPrompt, (newPrompt) => {
  // Use selectedSceneForPreview since that's the scene being edited in the details panel
  if (selectedSceneForPreview.value !== null && scenes.value[selectedSceneForPreview.value]) {
    const scene = scenes.value[selectedSceneForPreview.value]

    // Only update if the prompt actually changed (prevents running during programmatic scene switching)
    if (scene.prompt !== newPrompt) {
      // Update the scene's prompt
      scene.prompt = newPrompt
      // Re-detect characters from the updated prompt (will remove characters if @ mentions are removed)
      updateSceneCharacters(selectedSceneForPreview.value)
    }
  }
})

const syncSelectedSceneDetails = () => {
  if (selectedSceneForPreview.value === null || !scenes.value[selectedSceneForPreview.value]) {
    return
  }

  const scene = scenes.value[selectedSceneForPreview.value]
  sceneDetailsPrompt.value = scene.prompt || scene.description || ''
  sceneDetailsAnimationPrompt.value = scene.animationPrompt || ''
}

// Sync scene details when selected scene changes
watch(selectedSceneForPreview, (newIndex, oldIndex) => {
  // Save the previous scene's prompt changes before switching
  if (oldIndex !== null && scenes.value[oldIndex] && sceneDetailsPrompt.value.trim()) {
    const oldScene = scenes.value[oldIndex]
    oldScene.prompt = sceneDetailsPrompt.value
    // Re-detect characters after saving prompt changes
    updateSceneCharacters(oldIndex)
  }

  if (newIndex !== null && scenes.value[newIndex]) {
    // When a scene is selected, hide final video preview
    showingFinalVideo.value = false

    // Note: imageAspectRatio and sceneDetailsVideoModel are persisted via session storage
    // and should not be overridden when switching scenes
    syncSelectedSceneDetails()
  }
})

// Computed properties
const isGeneratingSceneDetailsImage = computed(() => {
  return selectedSceneForPreview.value !== null && generatingSceneIndices.value.has(selectedSceneForPreview.value)
})

const characterCount = computed(() => script.value.length)
const wordCount = computed(() => script.value.trim().split(/\s+/).filter(Boolean).length)
const sentenceCount = computed(() => {
  const sentences = script.value.split(/[.!?]+/).filter(s => s.trim().length > 0)
  return sentences.length
})
const estimatedDuration = computed(() => {
  // Rough estimate: 150 words per minute
  return Math.ceil(wordCount.value / 150)
})
const hasAllImages = computed(() => {
  return scenes.value.length > 0 && scenes.value.every(scene =>
    (scene.generatedImage?.url && scene.generatedImage?.id) ||
    (scene.animatedVideo?.url && scene.animatedVideo?.id)
  )
})

// Get characters for the currently selected scene
const selectedSceneCharacters = computed(() => {
  if (selectedSceneForPreview.value === null) return []
  const scene = scenes.value[selectedSceneForPreview.value]
  if (!scene || !scene.character_ids || scene.character_ids.length === 0) return []

  // Get character objects from the character IDs
  return scene.character_ids
    .map(charId => charactersStore.characters.find(c => c.id === charId))
    .filter((char): char is NonNullable<typeof char> => char !== undefined && char !== null) // Remove any undefined values (characters not found)
})

// DEBUG: Watch timeline rendering conditions
watch([() => scenes.value.length, hasAllImages, generatedAudio], ([sceneCount, allImages, audio]) => {
  console.log('📊 [Timeline Debug] Rendering conditions:')
  console.log('  - scenes.length:', sceneCount)
  console.log('  - hasAllImages:', allImages)
  console.log('  - generatedAudio exists:', !!audio)
  console.log('  - Timeline will render:', sceneCount > 0 && allImages)
  if (audio) {
    console.log('  - Audio URL:', audio.url || '(empty)')
    console.log('  - Audio duration:', audio.duration || 0)
  }
}, { immediate: true, deep: true })

// Computed greenscreen effect options based on aspect ratio
const greenscreenEffects = computed(() => {
  const suffix = imageAspectRatio.value === '16:9' ? '_h' : '_v'

  return [
    { value: '', label: '🎬 No Effect' },
    { value: `fire1${suffix}`, label: '🔥 Fire 1' },
    { value: `fire2${suffix}`, label: '🔥 Fire 2' },
    { value: `rain1${suffix}`, label: '🌧️ Rain' },
    { value: `pink_particle${suffix}`, label: '✨ Pink Particle' },
    { value: `white_particle${suffix}`, label: '❄️ White Particle' },
    { value: `stars${suffix}`, label: '⭐ Stars' },
    // { value: `electric${suffix}`, label: '⭐ Electric' },
    // { value: `speed${suffix}`, label: '⭐ Speed' },
    { value: `thunder${suffix}`, label: '⚡ Thunder' },
    { value: `old_film_white${suffix}`, label: '🎥 Old Film White' },
    { value: `old_film_black${suffix}`, label: '🎥 Old Film Black' }
  ]
})

// Methods
const selectStyleTemplate = (templateId: string) => {
  if (templateId === 'animal-haircut') {
    showAnimalHaircutModal.value = true
    return
  }

  if (selectedStyleTemplate.value === templateId) {
    // Deselect if clicking the same template
    selectedStyleTemplate.value = null
  } else {
    selectedStyleTemplate.value = templateId
  }
}

const createAnimalHaircutScene = (
  description: string,
  prompt: string,
  options: { animationPrompt?: string; startTime: number; endTime: number }
): Scene => ({
  id: crypto.randomUUID(),
  description,
  prompt,
  target_duration: options.endTime - options.startTime,
  start_time: options.startTime,
  end_time: options.endTime,
  generatedImage: undefined,
  animationPrompt: options.animationPrompt || '',
  isGenerating: false,
  generationProgress: 0,
  camera_movement: 'static',
  transition_type: 'fade',
  transition_duration: 0.5,
  greenscreen_effect: '',
  sceneAudio: undefined,
})

const confirmAnimalHaircutStoryboard = async () => {
  const animal = animalHaircutAnimal.value.trim()
  const haircutStyle = animalHaircutStyle.value.trim()

  if (!animal || !haircutStyle) {
    toast.error('Animal and haircut style are required')
    return
  }

  try {
    isGeneratingAnimalHaircutPrompts.value = true

    const promptPackage = await generateAnimalHaircutPrompts({
      animal,
      haircut_style: haircutStyle,
    })

    selectedStyleTemplate.value = 'animal-haircut'

    let effectiveProjectId = projectId.value
    const draft = await saveDraft({ skipToast: true })
    if (!effectiveProjectId) {
      effectiveProjectId = draft?.project_id || projectId.value
    }
    if (effectiveProjectId && !projectId.value) {
      projectId.value = effectiveProjectId
    }

    scenes.value = [
      createAnimalHaircutScene(
        `${promptPackage.animal_name} before grooming`,
        promptPackage.first_image_prompt,
        { startTime: 0, endTime: 3 }
      ),
      createAnimalHaircutScene(
        `${promptPackage.animal_name} with ${promptPackage.haircut_style}`,
        promptPackage.second_image_prompt,
        {
          animationPrompt: promptPackage.video_prompt,
          startTime: 3,
          endTime: 6,
        }
      ),
    ]

    showAnimalHaircutModal.value = false
    showStoryboardLayout.value = true
    showingFinalVideo.value = false
    showingGallery.value = false
    showingThumbnail.value = false
    showingPreview.value = false
    selectedSceneForPreview.value = scenes.value.length > 0 ? 0 : null
    sceneGenerationError.value = ''
    finalGeneratedVideo.value = null
    finalVideoExists.value = false
    syncSelectedSceneDetails()

    if (effectiveProjectId) {
      await saveScenes(effectiveProjectId)
    }

    toast.success('Animal haircut storyboard ready', {
      description: 'Two scenes were added. Tweak the prompts or settings before generating.'
    })
  } catch (error: any) {
    console.error('Failed to generate animal haircut storyboard:', error)
    toast.error('Failed to build animal haircut storyboard', {
      description: error?.message || 'Please try again'
    })
  } finally {
    isGeneratingAnimalHaircutPrompts.value = false
  }
}

const improveScript = () => {
  // TODO: Implement AI script improvement
  toast.info('AI script improvement coming soon!')
  console.log('Improving script...')
}

const improveIdea = async () => {
  // Validation
  if (!ideaText.value.trim()) {
    toast.error('Idea is empty', {
      description: 'Please describe your video idea first.'
    })
    return
  }

  if (ideaText.value.trim().length < 50) {
    toast.error('Idea too short', {
      description: 'Please provide at least 50 characters to describe your idea.'
    })
    return
  }

  isImprovingIdea.value = true
  improvedIdeaResults.value = null

  try {
    console.log('🚀 Processing idea with AI...')

    // Same endpoint as StoryEditor.vue
    const response = await apiClient.post('/api/improve-script', {
      script: ideaText.value.trim()
    })

    console.log('✅ Idea improvement completed:', response.data)

    improvedIdeaResults.value = response.data

    // Show results in preview panel (stay on current tab)
    showingIdeaResults.value = true
    showingFinalVideo.value = false
    showingGallery.value = false

    toast.success('Idea processed successfully! 💡', {
      description: 'Review the improved scripts in the preview panel. Select a version to continue.'
    })

  } catch (err: any) {
    console.error('❌ Idea improvement failed:', err)

    const errorMessage = err.response?.data?.detail || err.message || 'Failed to process idea'

    toast.error('Failed to process idea', {
      description: errorMessage
    })

  } finally {
    isImprovingIdea.value = false
  }
}

const generateScriptFromIdea = async () => {
  // Validation
  if (!ideaText.value.trim()) {
    toast.error('Idea is empty', {
      description: 'Please describe your video idea first.'
    })
    return
  }

  if (ideaText.value.trim().length < 50) {
    toast.error('Idea too short', {
      description: 'Please provide at least 50 characters to describe your idea.'
    })
    return
  }

  isGeneratingScript.value = true
  generatedScriptResults.value = null

  try {
    console.log('🚀 Generating script from idea with AI...')

    const response = await apiClient.post('/api/generate-script-from-idea', {
      idea: ideaText.value.trim(),
      video_length: `${videoLength.value[0]}min`
    })

    console.log('✅ Script generation completed:', response.data)

    generatedScriptResults.value = response.data

    // Show results in preview panel
    showingIdeaResults.value = true
    showingFinalVideo.value = false
    showingGallery.value = false

    toast.success('Script generated successfully! 💡', {
      description: 'Review the generated script in the preview panel.'
    })

  } catch (err: any) {
    console.error('❌ Script generation failed:', err)

    const errorMessage = err.response?.data?.detail || err.message || 'Failed to generate script'

    toast.error('Failed to generate script', {
      description: errorMessage
    })

  } finally {
    isGeneratingScript.value = false
  }
}

const fetchTrendingTopics = async () => {
  // Validation
  if (!trendKeyword.value.trim()) {
    toast.error('Please enter a topic', {
      description: 'Enter a keyword to search for trending videos'
    })
    return
  }

  isFetchingTrends.value = true
  trendingTopics.value = []

  try {
    console.log('🚀 Fetching YouTube trending topics for:', trendKeyword.value)

    const response = await apiClient.get('/api/youtube/trends', {
      params: {
        keyword: trendKeyword.value.trim(),
        max_results: 20
      }
    })

    console.log('✅ Trending topics fetched:', response.data)

    trendingTopics.value = response.data
    showingTrendingResults.value = true
    showingIdeaResults.value = false
    showingFinalVideo.value = false
    showingGallery.value = false

    toast.success(`Found ${response.data.length} trending topics! 🔥`, {
      description: 'Click on a video to use it as inspiration or watch it on YouTube'
    })

  } catch (err: any) {
    console.error('❌ Failed to fetch trending topics:', err)

    const errorMessage = err.response?.data?.detail || err.message || 'Failed to fetch trending topics'

    toast.error('Failed to fetch trending topics', {
      description: errorMessage
    })

  } finally {
    isFetchingTrends.value = false
  }
}

const selectTrendingTopic = (topic: any) => {
  // Auto-fill idea textarea with video topic
  ideaText.value = `Create a video about: ${topic.title}`
  showingTrendingResults.value = false

  toast.success('Idea populated! 💡', {
    description: 'You can now generate a script or edit the idea further'
  })

  console.log('✅ Selected trending topic:', topic.title)
}

const applyImprovedIdea = () => {
  if (!improvedIdeaResults.value) {
    console.error('No improved results to apply')
    return
  }

  const selectedVersionData = selectedIdeaVersion.value === 1
    ? improvedIdeaResults.value.version_1
    : improvedIdeaResults.value.version_2

  // Populate script field with selected version
  script.value = selectedVersionData.improved_script

  // Switch to scriptToVideo mode (keep results in memory for later access)
  creationMode.value = 'scriptToVideo'

  toast.success(`Version ${selectedIdeaVersion.value} applied! ✨`, {
    description: 'Script has been applied. You can switch back to "Idea to Video" to review the analysis.'
  })

  console.log('✅ Applied improved idea to script, switched to scriptToVideo mode (results preserved)')
}

const applyGeneratedScript = () => {
  if (!generatedScriptResults.value) {
    console.error('No generated script to apply')
    return
  }

  const selectedVersionData = selectedGeneratedVersion.value === 1
    ? generatedScriptResults.value.version_1
    : generatedScriptResults.value.version_2

  // Populate script field with selected version
  script.value = selectedVersionData.script

  // Switch to scriptToVideo mode
  creationMode.value = 'scriptToVideo'

  toast.success(`Version ${selectedGeneratedVersion.value} applied! ✨`, {
    description: 'Script has been applied. You can switch back to "Idea to Video" to review it again.'
  })

  console.log('✅ Applied generated script to editor, switched to scriptToVideo mode')
}

const copyToClipboard = async (text: string, label: string) => {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(`${label} copied! 📋`, {
      description: 'Copied to clipboard successfully.'
    })
  } catch (err) {
    console.error('Failed to copy:', err)
    toast.error('Failed to copy', {
      description: 'Please try again or copy manually.'
    })
  }
}

const playVoicePreview = () => {
  // TODO: Implement voice preview playback
  toast.info('Voice preview coming soon!')
  console.log('Playing voice preview for:', selectedVoice.value)
}

// Voice selection and preview methods
const handleVoiceSelection = (voice: any) => {
  selectedVoice.value = voice.id
  isVoiceDropdownOpen.value = false

  // Automatically set the TTS provider based on the selected voice's provider
  if (isSupportedVoiceProvider(voice.provider)) {
    ttsProvider.value = voice.provider
  }
}

const getProviderLabel = (provider: string | undefined) => {
  if (!provider || provider === 'minimax') return '[Minimax]'
  if (provider === 'deepgram') return '[Deepgram]'
  if (provider === 'google') return '[Google]'
  if (provider === 'elevenlabs') return '[ElevenLabs]'
  return ''
}

// Custom Voice Functions
const fetchCustomVoices = async () => {
  isLoadingCustomVoices.value = true
  try {
    const response = await fetch('/api/generate/minimax/custom-voices', {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
      }
    })

    if (!response.ok) {
      console.error('Failed to fetch custom voices')
      return
    }

    const data = await response.json()
    customVoices.value = data.voices
    logger.log(`✅ Loaded ${data.voices.length} custom voices`)
  } catch (error) {
    console.error('Error fetching custom voices:', error)
  } finally {
    isLoadingCustomVoices.value = false
  }
}

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    const file = target.files[0]
    const extension = file.name.split('.').pop()?.toLowerCase()

    if (!extension || !['mp3', 'wav', 'm4a'].includes(extension)) {
      selectedVoiceFile.value = null
      voiceUploadError.value = 'MiniMax supports MP3, WAV, and M4A audio files'
      target.value = ''
      return
    }

    if (file.size > 20 * 1024 * 1024) {
      selectedVoiceFile.value = null
      voiceUploadError.value = 'MiniMax voice clone files must be 20MB or smaller'
      target.value = ''
      return
    }

    voiceUploadError.value = ''
    selectedVoiceFile.value = file
  }
}

const uploadCustomVoice = async () => {
  if (!newVoiceName.value.trim()) {
    voiceUploadError.value = 'Please enter a voice name'
    return
  }

  if (!selectedVoiceFile.value) {
    voiceUploadError.value = 'Please select an audio file'
    return
  }

  uploadingVoice.value = true
  voiceUploadError.value = ''

  try {
    const formData = new FormData()
    formData.append('voice_name', newVoiceName.value.trim())
    if (newVoiceDescription.value.trim()) {
      formData.append('description', newVoiceDescription.value.trim())
    }
    formData.append('file', selectedVoiceFile.value)

    const response = await fetch('/api/generate/minimax/clone-voice', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
      },
      body: formData
    })

    if (!response.ok) {
      const error = await response.json()
      console.error('Clone voice error response:', error)
      const errorMsg = typeof error.detail === 'string'
        ? error.detail
        : JSON.stringify(error.detail || error)
      throw new Error(errorMsg || 'Voice cloning failed')
    }

    const newVoice = await response.json()

    // Refresh voice list
    await fetchCustomVoices()

    // Auto-select the new voice
    selectedVoice.value = newVoice.voice_id || newVoice.elevenlabs_voice_id
    ttsProvider.value = 'minimax'

    // Close modal and reset form
    showCustomVoiceUpload.value = false
    newVoiceName.value = ''
    newVoiceDescription.value = ''
    selectedVoiceFile.value = null

    // Show success message
    alert(`MiniMax voice "${newVoice.voice_name}" cloned successfully! (FREE)`)

  } catch (error: any) {
    voiceUploadError.value = error.message
    console.error('Voice upload error:', error)
  } finally {
    uploadingVoice.value = false
  }
}

const deleteCustomVoice = async (voiceId: string, voiceName: string) => {
  if (!confirm(`Are you sure you want to delete the voice "${voiceName}"?`)) {
    return
  }

  try {
    const response = await fetch(`/api/generate/minimax/custom-voices/${voiceId}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
      }
    })

    if (!response.ok) {
      throw new Error('Failed to delete voice')
    }

    // Refresh voice list
    await fetchCustomVoices()

    alert(`Voice "${voiceName}" deleted successfully`)

  } catch (error: any) {
    alert(`Error deleting voice: ${error.message}`)
    console.error('Voice deletion error:', error)
  }
}

const isVideoFile = (url: string) => {
  return /\.(mp4|mov|webm|avi|mkv)(\?|$)/i.test(url)
}

const handleVideoMouseEnter = (event: Event) => {
  const target = event.target as HTMLVideoElement
  if (target && target.play) {
    target.play().catch(() => {
      // Ignore play errors (e.g., if video isn't loaded yet)
    })
  }
}

const handleVideoMouseLeave = (event: Event) => {
  const target = event.target as HTMLVideoElement
  if (target && target.pause) {
    target.pause()
  }
}

const isAudioPlaying = (voiceId: string) => {
  return playingAudios.value.has(voiceId)
}

const isLoadingVoicePreview = (voiceId: string) => {
  return loadingVoicePreviews.value.has(voiceId)
}

const stopAllAudioPlayback = () => {
  if (genericVoicePreviewElement.value) {
    genericVoicePreviewElement.value.pause()
    genericVoicePreviewElement.value.currentTime = 0
  }
  // Stop ElevenLabs audio element
  if (elevenlabsAudioElement.value) {
    elevenlabsAudioElement.value.pause()
    elevenlabsAudioElement.value.currentTime = 0
  }
  playingAudios.value.clear()
}

const toggleAudioPlayback = async (voice: any) => {
  // Stop all other audio first and reset their state
  voiceOptions.value.forEach(v => {
    if (v.id !== voice.id && playingAudios.value.has(v.id)) {
      const audioElement = document.querySelector(`audio[src="${(v as any).sampleUrl}"]`) as HTMLAudioElement
      if (audioElement) {
        audioElement.pause()
        audioElement.currentTime = 0
      }
      playingAudios.value.delete(v.id)
    }
  })
  // Also stop ElevenLabs audio if playing different voice
  if (elevenlabsAudioElement.value) {
    elevenlabsAudioElement.value.pause()
    elevenlabsAudioElement.value.currentTime = 0
    // Clear all playing states except for the voice we're about to play
    const currentlyPlaying = Array.from(playingAudios.value)
    currentlyPlaying.forEach(id => {
      if (id !== voice.id) {
        playingAudios.value.delete(id)
      }
    })
  }

  // Handle ElevenLabs voices separately
  if (voice.provider === 'elevenlabs') {
    await toggleElevenlabsAudioPlayback(voice)
    return
  }

  if (!voice.sampleUrl) {
    toast.error('No preview available for this voice')
    return
  }

  if (!genericVoicePreviewElement.value) {
    genericVoicePreviewElement.value = new Audio()
    genericVoicePreviewElement.value.addEventListener('ended', () => {
      playingAudios.value.clear()
    })
    genericVoicePreviewElement.value.addEventListener('error', (error) => {
      console.error('Voice preview playback error:', error)
      playingAudios.value.clear()
    })
  }

  const audioElement = genericVoicePreviewElement.value

  try {
    if (playingAudios.value.has(voice.id)) {
      // Currently playing - pause it
      audioElement.pause()
      audioElement.currentTime = 0
      playingAudios.value.delete(voice.id)
    } else {
      // Not playing - start playback
      if (audioElement.src !== voice.sampleUrl) {
        audioElement.src = voice.sampleUrl
      }
      audioElement.currentTime = 0
      await audioElement.play()
      playingAudios.value.add(voice.id)
    }
  } catch (error) {
    console.error('Error playing audio for voice:', voice.name, error)
  }
}

const toggleElevenlabsAudioPlayback = async (voice: any) => {
  // If already playing this voice, stop it
  if (playingAudios.value.has(voice.id)) {
    if (elevenlabsAudioElement.value) {
      elevenlabsAudioElement.value.pause()
      elevenlabsAudioElement.value.currentTime = 0
    }
    playingAudios.value.delete(voice.id)
    return
  }

  try {
    // Check if we already have the preview URL cached
    let previewUrl = elevenlabsPreviewUrls.value.get(voice.id)

    if (!previewUrl) {
      // Fetch the preview URL from our backend
      loadingVoicePreviews.value.add(voice.id)

      const response = await apiClient.get(`/api/generate/elevenlabs/voice-preview/${voice.id}`)
      previewUrl = response.data.preview_url as string

      // Cache the URL for future use
      if (previewUrl) {
        elevenlabsPreviewUrls.value.set(voice.id, previewUrl)
      }
      loadingVoicePreviews.value.delete(voice.id)
    }

    if (!previewUrl) {
      throw new Error('No preview URL available')
    }

    // Create or reuse audio element
    if (!elevenlabsAudioElement.value) {
      elevenlabsAudioElement.value = new Audio()
      elevenlabsAudioElement.value.addEventListener('ended', () => {
        playingAudios.value.clear()
      })
      elevenlabsAudioElement.value.addEventListener('error', (e) => {
        console.error('ElevenLabs audio playback error:', e)
        playingAudios.value.clear()
      })
    }

    // Set source and play
    elevenlabsAudioElement.value.src = previewUrl
    await elevenlabsAudioElement.value.play()
    playingAudios.value.add(voice.id)

  } catch (error) {
    console.error('Error playing ElevenLabs voice preview:', voice.name, error)
    loadingVoicePreviews.value.delete(voice.id)
    toast.error('Failed to load voice preview')
  }
}

const onAudioEnded = (voiceId: string) => {
  playingAudios.value.delete(voiceId)
}

const onAudioError = (voice: any) => {
  console.error('Audio failed to load for voice:', voice.name)
  playingAudios.value.delete(voice.id)
}

// Handle audio player timeupdate for timeline playhead sync
const handleAudioTimeUpdate = (event: Event) => {
  const audio = event.target as HTMLAudioElement
  currentTime.value = audio.currentTime
}

const handleClickOutsideVoiceDropdown = (event: MouseEvent) => {
  if (voiceDropdownRef.value && !voiceDropdownRef.value.contains(event.target as Node)) {
    isVoiceDropdownOpen.value = false
  }
}

// Audio upload handlers
const handleAudioUpload = (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]

  if (!file) return

  // Validate file size (max 50MB)
  const maxSize = 50 * 1024 * 1024
  if (file.size > maxSize) {
    toast.error('File too large', {
      description: 'Maximum file size is 50MB'
    })
    return
  }

  // Validate file type
  if (!file.type.startsWith('audio/')) {
    toast.error('Invalid file type', {
      description: 'Please upload an audio file (MP3, WAV, or M4A)'
    })
    return
  }

  uploadedAudioFile.value = file
  uploadedAudioUrl.value = URL.createObjectURL(file)
  toast.success('Audio uploaded', {
    description: file.name
  })
}

const removeAudio = () => {
  if (uploadedAudioUrl.value) {
    URL.revokeObjectURL(uploadedAudioUrl.value)
  }
  uploadedAudioFile.value = null
  uploadedAudioUrl.value = null
  if (audioFileInput.value) {
    audioFileInput.value.value = ''
  }
  toast.info('Audio removed')
}

const regenerateScene = (sceneId: string) => {
  // TODO: Implement scene regeneration
  toast.info('Scene regeneration coming soon!')
  console.log('Regenerating scene:', sceneId)
}

// SceneCard event handlers (updated for inline editor)
const openSceneEditModal = (index: number) => {
  editingSceneIndex.value = index
  editingScene.value = scenes.value[index]
  editingSceneNumber.value = index + 1

  // Populate inline editor fields
  localPrompt.value = editingScene.value.prompt || ''
  localAnimationPrompt.value = editingScene.value.animationPrompt || ''
  generatedImageUrl.value = editingScene.value.generatedImage?.url || ''
  generatedVideoUrl.value = ''
  isGeneratingImageInEditor.value = false
  isGeneratingVideoInEditor.value = false
}

const closeSceneEditModal = () => {
  editingScene.value = null
  editingSceneNumber.value = 0
  editingSceneIndex.value = null

  // Clear inline editor fields
  localPrompt.value = ''
  localAnimationPrompt.value = ''
  generatedImageUrl.value = ''
  generatedVideoUrl.value = ''
  isGeneratingImageInEditor.value = false
  isGeneratingVideoInEditor.value = false
}

const handleGenerateImageFromModal = async (prompt: string, model: string) => {
  if (editingSceneIndex.value === null) return

  try {
    sceneEditModalRef.value?.setGeneratingImage(true)

    let promptToSend = withSelectedVisualStylePrompt(prompt)

    const result = await imageGenerationStore.generateImage({
      prompt: promptToSend,
      model,
      num_outputs: 1
    })

    if (result?.signed_url) {
      // Update the scene with the new generated image
      const scene = scenes.value[editingSceneIndex.value]
      const width = result.width || 1024
      const height = result.height || 1024
      const aspectRatio = width > height ? '16:9' : height > width ? '9:16' : '1:1'

      scene.generatedImage = {
        id: result.id,
        url: result.signed_url,
        width,
        height,
        aspectRatio
      }

      toast.success('Image generated successfully!')
    }
  } catch (error: any) {
    console.error('Failed to generate image:', error)
    toast.error((error.code === 'CONTENT_BLOCKED' || error.code === 'content_blocked') ? 'Update prompt needed' : 'Failed to generate image', {
      description: error.message || 'Please try again',
      duration: (error.code === 'CONTENT_BLOCKED' || error.code === 'content_blocked') ? 9000 : 6000
    })
  } finally {
    sceneEditModalRef.value?.setGeneratingImage(false)
  }
}

const handleGenerateVideoFromModal = async (prompt: string, imageUrl: string) => {
  if (editingSceneIndex.value === null) return

  try {
    sceneEditModalRef.value?.setGeneratingVideo(true)
    toast.info('Video generation from modal coming soon!')
  } catch (error) {
    console.error('Failed to generate video:', error)
    sceneEditModalRef.value?.setGeneratingVideo(false)
  }
}

const handleAddVideoToTimelineFromModal = (videoUrl: string) => {
  if (editingSceneIndex.value !== null) {
    addAnimatedVideoToTimeline(editingSceneIndex.value)
    toast.success('Video added to timeline!')
  }
}

// Inline editor handler functions
const handleGenerateImageFromInlineEditor = async () => {
  if (editingSceneIndex.value === null || !localPrompt.value.trim() || !imageGenerationModel.value) return

  try {
    isGeneratingImageInEditor.value = true

    let promptToSend = withSelectedVisualStylePrompt(localPrompt.value)

    const result = await imageGenerationStore.generateImage({
      prompt: promptToSend,
      model: imageGenerationModel.value,
      width: imageAspectRatio.value === '9:16' ? 720 : imageAspectRatio.value === '1:1' ? 1024 : 1280,
      height: imageAspectRatio.value === '9:16' ? 1280 : imageAspectRatio.value === '1:1' ? 1024 : 720,
      aspect_ratio: imageAspectRatio.value,
      num_outputs: 1
    })

    if (result?.signed_url) {
      // Update the generated image URL for preview
      generatedImageUrl.value = result.signed_url

      // Update the scene with the new generated image
      const scene = scenes.value[editingSceneIndex.value]
      const width = result.width || 1024
      const height = result.height || 1024
      const aspectRatio = `${width}:${height}`

      scene.generatedImage = {
        url: result.signed_url,
        width,
        height,
        aspectRatio
      }

      // Update the prompt in the scene
      scene.prompt = localPrompt.value

      toast.success('Image generated successfully!')
    }
  } catch (error: any) {
    console.error('Failed to generate image:', error)
    toast.error((error.code === 'CONTENT_BLOCKED' || error.code === 'content_blocked') ? 'Update prompt needed' : 'Failed to generate image', {
      description: error.message || 'Please try again',
      duration: (error.code === 'CONTENT_BLOCKED' || error.code === 'content_blocked') ? 9000 : 6000
    })
  } finally {
    isGeneratingImageInEditor.value = false
  }
}

// Generate image from scene details in storyboard review
const handleGenerateImageFromSceneDetails = async () => {
  if (selectedSceneForPreview.value === null || !sceneDetailsPrompt.value.trim() || !imageGenerationModel.value) return

  // Capture the scene index and prompt at the start to avoid race conditions
  // (in case user selects a different scene while generation is in progress)
  const targetSceneIndex = selectedSceneForPreview.value
  const capturedPrompt = sceneDetailsPrompt.value
  const capturedImageReference = imageReferenceImage.value ? { ...imageReferenceImage.value } : null
  const scene = scenes.value[targetSceneIndex]

  try {
    // Mark this specific scene as generating
    generatingSceneIndices.value.add(targetSceneIndex)

    const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:8000')

    logger.log(`🎬 Generating image for scene ${targetSceneIndex + 1} (from details)`)
    logger.log(`📝 Prompt: "${capturedPrompt}"`)
    logger.log(`👥 Character IDs in scene:`, scene.character_ids)
    logger.log(`📚 Total characters in store:`, charactersStore.characters?.length || 0)

    // Get character reference images if characters are selected for this scene
    const referenceImages: string[] = []
    const referenceImageUrls: string[] = [] // URLs for models that support input_images (e.g., openai/gpt-image-2)

    if (scene.character_ids && scene.character_ids.length > 0) {
      // Fetch character data for each character
      for (const characterId of scene.character_ids) {
        try {
          const character = await charactersStore.getCharacter(characterId)

          // Get reference image URLs from character and convert to base64
          if (character.reference_images && character.reference_images.length > 0) {
            for (const refImage of character.reference_images) {
              if (refImage.image_url) {
                // Store the URL for models that support input_images
                referenceImageUrls.push(refImage.image_url)
                try {
                  // Fetch the image and convert to base64
                  const base64Image = await urlToBase64(refImage.image_url)
                  referenceImages.push(base64Image)
                } catch (error) {
                  console.error(`Failed to convert image URL to base64:`, error)
                  // Continue with other images even if one fails
                }
              }
            }
          }
        } catch (error) {
          console.error(`Failed to fetch character ${characterId}:`, error)
          // Continue with other characters even if one fails
        }
      }

      if (referenceImages.length > 0) {
        logger.log(`📷 Total reference images to send: ${referenceImages.length}`)
      }
    }

    if (capturedImageReference?.url) {
      referenceImageUrls.push(capturedImageReference.url)
      try {
        const base64Image = await urlToBase64(capturedImageReference.url)
        referenceImages.push(base64Image)
      } catch (error) {
        console.error('Failed to convert selected reference image URL to base64:', error)
      }
      logger.log('📷 Added selected content library reference image')
    }

    // Clean prompt from @mentions and enhance with character descriptions
    let enhancedPrompt = capturedPrompt
    if (scene.character_ids && scene.character_ids.length > 0) {
      enhancedPrompt = cleanPromptFromMentions(capturedPrompt, scene.character_ids)
      logger.log(`🔄 Cleaned prompt: "${enhancedPrompt}"`)
    }
    enhancedPrompt = withSelectedVisualStylePrompt(enhancedPrompt)

    // Generate image with user's selected settings
    const requestBody: any = {
      prompt: enhancedPrompt,
      model: imageGenerationModel.value,
      width: imageAspectRatio.value === '9:16' ? 720 : (imageAspectRatio.value === '1:1' ? 1024 : 1280),
      height: imageAspectRatio.value === '9:16' ? 1280 : (imageAspectRatio.value === '1:1' ? 1024 : 720),
      num_outputs: 1,
      aspect_ratio: getModelCompatibleImageAspectRatio(imageGenerationModel.value, imageAspectRatio.value)
    }

    // Add Replicate input parameters for Plus Quality 2 model (openai/gpt-image-2)
    if (imageGenerationModel.value === 'openai/gpt-image-2') {
      const mappedAspectRatio = getModelCompatibleImageAspectRatio(imageGenerationModel.value, imageAspectRatio.value)

      // Replicate input parameters for openai/gpt-image-2
      requestBody.input = {
        prompt: requestBody.prompt,
        quality: 'low',
        background: 'auto',
        moderation: 'auto',
        aspect_ratio: mappedAspectRatio,
        output_format: 'webp',
        input_fidelity: 'low',
        number_of_images: 1,
        output_compression: 90
      }
      // Include reference images (from @ tagged characters) as input_images for openai/gpt-image-2
      if (referenceImageUrls.length > 0) {
        requestBody.input.input_images = referenceImageUrls
        logger.log(`📷 Including ${referenceImageUrls.length} reference image(s) in input_images for openai/gpt-image-2`)
      }
      console.log('[Plus Quality 2] UI aspect ratio:', imageAspectRatio.value, '→ API aspect ratio:', mappedAspectRatio)
      console.log('[Plus Quality 2] Full requestBody:', JSON.stringify(requestBody, null, 2))
    }

    // Include reference images if available
    if (referenceImages.length > 0) {
      requestBody.referenceImages = referenceImages
    }

    // Create AbortController with 5 minute timeout for image generation
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 300000) // 5 minutes

    try {
      const response = await fetch(`${API_BASE_URL}/api/image-generation/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal
      })

      clearTimeout(timeoutId)

      if (!response.ok) {
        const errorDetail = await response.json()
        throw new Error(errorDetail?.message || errorDetail?.detail || 'Image generation failed')
      }

      const result = await response.json()

      // Fetch the generated image with 2 minute timeout
      const imageController = new AbortController()
      const imageTimeoutId = setTimeout(() => imageController.abort(), 120000) // 2 minutes

      const imageResponse = await fetch(`${API_BASE_URL}/api/image-generation/generations/${result.id}`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        signal: imageController.signal
      })

      clearTimeout(imageTimeoutId)

      if (!imageResponse.ok) {
        throw new Error('Failed to fetch generated image')
      }

      const imageData = await imageResponse.json()

      // Update scene with generated image
      if (imageData.signed_url) {
        const scene = scenes.value[targetSceneIndex]
        const width = imageData.width || (imageAspectRatio.value === '9:16' ? 720 : (imageAspectRatio.value === '1:1' ? 1024 : 1280))
        const height = imageData.height || (imageAspectRatio.value === '9:16' ? 1280 : (imageAspectRatio.value === '1:1' ? 1024 : 720))

        scene.generatedImage = {
          id: result.id,
          url: imageData.signed_url,
          width,
          height,
          aspectRatio: imageAspectRatio.value
        }

        // Clear animated video when generating new image so preview shows new image
        delete scene.animatedVideo

        // Update the prompt in the scene (use captured prompt to avoid race conditions)
        scene.prompt = capturedPrompt

        logger.log(`✅ Scene ${targetSceneIndex + 1} image generated successfully`)
        logger.log(`📍 Image ID: ${result.id}`)
        logger.log(`🔗 Image URL: ${imageData.signed_url}`)

        toast.success('Image generated successfully!')

        // Save the updated scenes
        await saveScenes()

        // Refresh the image generation store's gallery
        await imageGenerationStore.fetchGallery(true)
      }
    } catch (error: any) {
      clearTimeout(timeoutId)
      if (error.name === 'AbortError') {
        console.error('Image generation request timed out')
        toast.error('Image generation timed out', { description: 'Please try again' })
      } else {
        console.error('Failed to generate image:', error)
        toast.error(error.message || 'Failed to generate image')
      }
    }
  } catch (error: any) {
    console.error('Failed to generate image:', error)
    toast.error(error.message || 'Failed to generate image')
  } finally {
    // Remove this scene from the generating set
    generatingSceneIndices.value.delete(targetSceneIndex)
  }
}

const buildDefaultThumbnailPrompt = (): string => {
  const title = projectTitle.value?.trim() || 'Untitled video'
  const scriptSnippet = script.value.trim().replace(/\s+/g, ' ').slice(0, 260)
  return [
    `Create a high-impact YouTube/TikTok video thumbnail for: ${title}.`,
    scriptSnippet ? `Video topic/script context: ${scriptSnippet}.` : '',
    'Bold cinematic composition, clear focal subject, strong contrast, vibrant colors, dramatic lighting, no tiny unreadable text, compose cleanly for the selected output aspect ratio, eye-catching social media style.'
  ].filter(Boolean).join(' ')
}

const parseRecord = (value: unknown): Record<string, any> | null => {
  if (!value) return null
  if (typeof value === 'object' && !Array.isArray(value)) return value as Record<string, any>
  if (typeof value !== 'string') return null

  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, any>
      : null
  } catch (error) {
    logger.warn('Failed to parse JSON project data:', error)
    return null
  }
}

const getProjectUiPreferences = (project: any): Record<string, any> | null => {
  return parseRecord(project?.ui_preferences)
    || parseRecord(parseRecord(project?.draft_data)?.ui_preferences)
}

const serializeThumbnailImages = (thumbnails: ProjectThumbnail[]): ProjectThumbnail[] => {
  return thumbnails
    .filter((thumbnail) => Boolean(thumbnail?.url))
    .map((thumbnail) => {
      const aspectRatio = (thumbnail.aspectRatio === '9:16' || thumbnail.aspectRatio === '1:1' || thumbnail.aspectRatio === '16:9')
        ? thumbnail.aspectRatio
        : '16:9'
      const fallbackDimensions = getImageDimensionsForAspectRatio(aspectRatio)
      return {
        id: thumbnail.id,
        imageId: thumbnail.imageId,
        url: thumbnail.url,
        width: thumbnail.width || fallbackDimensions.width,
        height: thumbnail.height || fallbackDimensions.height,
        aspectRatio,
        prompt: thumbnail.prompt || '',
        createdAt: thumbnail.createdAt || new Date().toISOString()
      }
    })
}

const refreshSavedThumbnailUrls = async (thumbnails: ProjectThumbnail[]): Promise<ProjectThumbnail[]> => {
  const normalizedThumbnails = serializeThumbnailImages(thumbnails)
  const refreshed = await Promise.all(normalizedThumbnails.map(async (thumbnail) => {
    if (!thumbnail.imageId && !thumbnail.id) return thumbnail
    try {
      const response = await apiClient.post(`/api/image-generation/refresh-urls/${thumbnail.imageId || thumbnail.id}`, {
        current_url: thumbnail.url
      })
      if (!response.data?.signed_url) return thumbnail
      return { ...thumbnail, url: response.data.signed_url }
    } catch (error) {
      logger.warn('Failed to refresh thumbnail URL:', error)
      return thumbnail
    }
  }))
  return refreshed.filter((thumbnail) => Boolean(thumbnail?.url))
}

const persistThumbnailState = async () => {
  try {
    await saveDraft({ skipToast: true })
  } catch (error) {
    logger.warn('Failed to persist thumbnail state:', error)
  }
}

const handleSelectThumbnail = async (index: number) => {
  selectedThumbnailIndex.value = index
  await persistThumbnailState()
}

const handleGenerateThumbnail = async () => {
  const prompt = thumbnailPrompt.value.trim()
  if (!prompt || !imageGenerationModel.value) return

  try {
    isGeneratingThumbnail.value = true
    const thumbnailAspectRatio = imageAspectRatio.value
    const thumbnailDimensions = getImageDimensionsForAspectRatio(thumbnailAspectRatio)
    const mappedAspectRatio = getModelCompatibleImageAspectRatio(imageGenerationModel.value, thumbnailAspectRatio)

    const requestBody: any = {
      prompt,
      model: imageGenerationModel.value,
      width: thumbnailDimensions.width,
      height: thumbnailDimensions.height,
      num_outputs: 1,
      aspect_ratio: mappedAspectRatio
    }

    if (imageGenerationModel.value === 'openai/gpt-image-2') {
      requestBody.input = {
        prompt,
        quality: 'low',
        background: 'auto',
        moderation: 'auto',
        aspect_ratio: mappedAspectRatio,
        output_format: 'webp',
        input_fidelity: 'low',
        number_of_images: 1,
        output_compression: 90
      }
    }

    const generateResponse = await apiClient.post('/api/image-generation/generate', requestBody, {
      timeout: 300000
    })
    const generationId = generateResponse.data?.id
    if (!generationId) throw new Error('Image generation did not return an ID')

    const imageResponse = await apiClient.get(`/api/image-generation/generations/${generationId}`, {
      timeout: 120000
    })
    const imageData = imageResponse.data
    const imageUrl = imageData?.signed_url || imageData?.gcs_signed_url
    if (!imageUrl) throw new Error('Generated thumbnail did not return an accessible URL')

    const thumbnail: ProjectThumbnail = {
      id: crypto.randomUUID(),
      imageId: generationId,
      url: imageUrl,
      width: imageData.width || thumbnailDimensions.width,
      height: imageData.height || thumbnailDimensions.height,
      aspectRatio: thumbnailAspectRatio,
      prompt,
      createdAt: new Date().toISOString()
    }

    thumbnailImages.value = [thumbnail, ...thumbnailImages.value]
    selectedThumbnailIndex.value = 0
    toast.success('Thumbnail generated successfully!')

    await persistThumbnailState()
    await imageGenerationStore.fetchGallery(true)
  } catch (error: any) {
    console.error('Failed to generate thumbnail:', error)
  } finally {
    isGeneratingThumbnail.value = false
  }
}

// Generate Manim animation video
const generateManimVideo = async (sceneIndex: number) => {
  const scene = scenes.value[sceneIndex]
  // Priority: user's textbox input > saved animation prompt > scene description > scene prompt
  const prompt = sceneDetailsAnimationPrompt.value || scene.animationPrompt || scene.description || scene.prompt

  if (!prompt || !prompt.trim()) {
    toast.error('Please provide a description or animation prompt')
    return
  }

  try {
    // Set per-scene generating state
    isAnimatingImage.value[sceneIndex] = true
    animationProgress.value[sceneIndex] = 0

    // Save scene to database BEFORE calling manim generation
    // This ensures the scene exists in video_project_backgrounds when generated media updates it.
    await saveScenes()

    toast.info('Generating Manim animation... This may take a few minutes.')

    const token = localStorage.getItem('access_token')
    const response = await fetch('/api/manim/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        prompt: prompt,
        mode: manimMode.value,
        quality: manimQuality.value,
        aspect_ratio: manimAspectRatio.value,
        project_id: projectId.value,
        scene_id: scene.id
      })
    })

    const data = await response.json()

    if (!response.ok) {
      throw new Error(data.detail || 'Failed to generate Manim animation')
    }

    if (data.success && data.video_url) {
      // Update scene with generated video
      // Use generated_id (the ID from generated_images table) for proper linking
      const videoId = data.generated_id || data.job_id
      scene.animatedVideo = {
        id: videoId,
        url: data.video_url,
        duration: 8 // Default Manim video duration
      }
      // Only set generatedImage if there's no existing image
      // Don't overwrite existing image - the video is stored in animatedVideo
      if (!scene.generatedImage) {
        // For Manim-only scenes, create a generatedImage entry for display
        // Only use generated_id if it's valid (not job_id fallback)
        if (data.generated_id) {
          scene.generatedImage = {
            id: data.generated_id,
            url: data.video_url,
            width: 1280,
            height: 720,
            aspectRatio: manimAspectRatio.value
          }
        }
      }
      // Note: If scene already has a generatedImage, keep it - don't overwrite with video ID
      // The original image is preserved, video is in animatedVideo

      // Mark that this was generated with Manim
      scene.animationModel = 'manim'

      toast.success('Manim animation generated successfully!')

      // Save the updated scenes
      await saveScenes()
    } else {
      throw new Error(data.error || 'Manim generation failed')
    }
  } catch (error: any) {
    console.error('Failed to generate Manim video:', error)
    toast.error(error.message || 'Failed to generate Manim animation')
  } finally {
    // Clear per-scene generating state
    isAnimatingImage.value[sceneIndex] = false
  }
}

// Generate video from scene details in storyboard review
const handleGenerateVideoFromSceneDetails = async () => {
  if (selectedSceneForPreview.value === null || !sceneDetailsAnimationPrompt.value.trim()) return

  // Capture values at the start to avoid race conditions
  const targetSceneIndex = selectedSceneForPreview.value
  const capturedAnimationPrompt = sceneDetailsAnimationPrompt.value
  const capturedVideoModel = sceneDetailsVideoModel.value
  const capturedResolution = sceneDetailsVideoResolution.value
  const capturedDuration = sceneDetailsVideoDuration.value
  const scene = scenes.value[targetSceneIndex]

  // Handle Manim animation separately (doesn't require an image)
  if (capturedVideoModel === 'manim') {
    await generateManimVideo(targetSceneIndex)
    return
  }

  const sceneAudioUrl = getKlingAvatarAudioUrl(scene)

  // Kling Avatar requires scene or project audio from this page
  if (capturedVideoModel === 'kwaivgi/kling-avatar-v2' && !sceneAudioUrl) {
    toast.error('Kling Avatar requires audio. Generate scene audio or project audio first.')
    return
  }

  // Check if we have either a custom start frame, a generated image, or a text-to-video model.
  if (!isGeminiOmniVideoModel(capturedVideoModel) && !startFrameImage.value?.id && (!scene.generatedImage || !scene.generatedImage.id)) {
    toast.error('Please generate an image first before creating a video')
    return
  }

  try {
    // Update the scene with the animation prompt, model, resolution, and duration (use captured values to avoid race conditions)
    scene.animationPrompt = capturedAnimationPrompt
    scene.animationModel = capturedVideoModel
    scene.animationResolution = capturedResolution
    scene.animationDuration = capturedDuration

    // Call the animation function (this sets isAnimatingImage per-scene)
    await animateSceneImage(targetSceneIndex)

    // Save the updated scenes
    await saveScenes()
  } catch (error: any) {
    console.error('Failed to generate video:', error)
    toast.error(error.message || 'Failed to generate video')
  }
}

const handleGenerateVideoFromInlineEditor = async () => {
  if (editingSceneIndex.value === null || !localAnimationPrompt.value.trim()) return

  try {
    isGeneratingVideoInEditor.value = true
    toast.info('Video generation from inline editor coming soon!')
  } catch (error) {
    console.error('Failed to generate video:', error)
  } finally {
    isGeneratingVideoInEditor.value = false
  }
}

const handleAnimateSceneFromInlineEditor = async () => {
  if (editingSceneIndex.value === null || !localAnimationPrompt.value.trim()) return

  // Sync the local animation prompt, model, and resolution with the scene
  const scene = scenes.value[editingSceneIndex.value]
  scene.animationPrompt = localAnimationPrompt.value
  scene.animationModel = selectedVideoModel.value
  scene.animationResolution = sceneDetailsVideoResolution.value

  // Call the animation function
  await animateSceneImage(editingSceneIndex.value)
}

const handleAddVideoToTimelineFromInlineEditor = () => {
  if (editingSceneIndex.value !== null) {
    addAnimatedVideoToTimeline(editingSceneIndex.value)
    toast.success('Video added to timeline!')
  }
}

// Character detection helper functions
const extractCharacterMentions = (prompt: string): string[] => {
  // Match @word or @{phrase with spaces}
  const mentionPattern = /@(\w+)|@\{([^}]+)\}/g
  const mentions: string[] = []
  let match

  while ((match = mentionPattern.exec(prompt)) !== null) {
    // match[1] is for @word format, match[2] is for @{phrase} format
    const mentionName = match[1] || match[2]
    if (mentionName) {
      mentions.push(mentionName.trim())
    }
  }

  return mentions
}

const findCharacterByName = (characterName: string): any | null => {
  if (!characterName || charactersStore.characters.length === 0) {
    return null
  }

  const normalizedName = characterName.toLowerCase().trim()

  // Try exact match first
  const exactMatch = charactersStore.characters.find(
    char => char.name.toLowerCase() === normalizedName
  )

  if (exactMatch) {
    return exactMatch
  }

  // Try partial match
  const partialMatch = charactersStore.characters.find(
    char => char.name.toLowerCase().includes(normalizedName)
  )

  return partialMatch || null
}

const extractCharacterIdsFromPrompt = (prompt: string): string[] => {
  const mentions = extractCharacterMentions(prompt)
  const characterIds: string[] = []
  const notFoundCharacters: string[] = []

  for (const mention of mentions) {
    const character = findCharacterByName(mention)
    if (character) {
      // Avoid duplicates
      if (!characterIds.includes(character.id)) {
        characterIds.push(character.id)
        logger.log(`✅ Detected character: @${mention} → ${character.name} (${character.id})`)
      }
    } else {
      notFoundCharacters.push(mention)
      console.warn(`⚠️ Character not found: @${mention}`)
    }
  }

  if (notFoundCharacters.length > 0) {
    logger.log(`⚠️ Characters not found: ${notFoundCharacters.join(', ')}`)
  }

  return characterIds
}

// Helper function to convert image URL to base64
const urlToBase64 = async (url: string): Promise<string> => {
  try {
    const response = await fetch(url)
    if (!response.ok) {
      throw new Error(`Failed to fetch image: ${response.statusText}`)
    }
    const blob = await response.blob()
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onloadend = () => resolve(reader.result as string)
      reader.onerror = reject
      reader.readAsDataURL(blob)
    })
  } catch (error) {
    console.error('Error converting URL to base64:', error)
    throw error
  }
}

const cleanPromptFromMentions = (prompt: string, characterIds: string[]): string => {
  if (!characterIds || characterIds.length === 0) {
    return prompt
  }

  let cleanedPrompt = prompt

  // Get character descriptions to enhance the prompt
  const characterDescriptions = new Map<string, string>()

  for (const characterId of characterIds) {
    const character = charactersStore.characters.find(c => c.id === characterId)
    if (character) {
      const normalizedName = character.name.toLowerCase()
      // Extract key visual details from description if available
      let visualNotes = ''
      if (character.visual_style_notes && character.visual_style_notes.trim()) {
        visualNotes = character.visual_style_notes.trim()
      } else if (character.description && character.description.trim()) {
        // Use first sentence of description as fallback
        const firstSentence = character.description.split(/[.。]/)[0]
        visualNotes = firstSentence.trim()
      }

      if (visualNotes) {
        characterDescriptions.set(normalizedName, visualNotes)
      }
    }
  }

  // Replace @mentions with character name + description
  const mentionPattern = /@(\w+)|@\{([^}]+)\}/g

  cleanedPrompt = cleanedPrompt.replace(mentionPattern, (match, word, phrase) => {
    const mentionName = (word || phrase).trim().toLowerCase()

    // Find matching character description
    for (const [charName, description] of characterDescriptions.entries()) {
      if (charName === mentionName || charName.includes(mentionName)) {
        // Replace with name (description)
        const actualCharacter = charactersStore.characters.find(c => c.name.toLowerCase() === charName)
        if (actualCharacter && description) {
          return `${actualCharacter.name} (${description})`
        }
        return actualCharacter?.name || mentionName
      }
    }

    // If no description found, just remove the @ symbol
    return word || phrase
  })

  return cleanedPrompt
}

const updateSceneCharacters = (sceneIndex: number) => {
  const scene = scenes.value[sceneIndex]
  if (!scene || !scene.prompt) return

  // Re-detect characters from the edited prompt
  const detectedCharacterIds = extractCharacterIdsFromPrompt(scene.prompt)

  // Update character_ids
  scene.character_ids = detectedCharacterIds

  if (detectedCharacterIds.length > 0) {
    logger.log(`🔄 Re-detected ${detectedCharacterIds.length} character(s) in scene ${sceneIndex + 1}`)
  }
}

const removeCharacterFromScene = (characterId: string) => {
  if (selectedSceneForPreview.value === null) return

  const scene = scenes.value[selectedSceneForPreview.value]
  if (!scene) return

  // Find the character to get its name
  const character = charactersStore.characters.find(c => c.id === characterId)
  if (!character) return

  // Remove character ID from the array
  scene.character_ids = scene.character_ids?.filter(id => id !== characterId) || []

  // Remove @ mention from the prompt
  const characterNameLower = character.name.toLowerCase()

  // Pattern to match @charactername or @{character name}
  const mentionPattern = new RegExp(
    `@${character.name}\\b|@\\{${character.name}\\}`,
    'gi'
  )

  scene.prompt = scene.prompt.replace(mentionPattern, '').trim()

  // Update the scene details prompt to reflect the change
  sceneDetailsPrompt.value = scene.prompt

  logger.log(`🗑️ Removed character ${character.name} from scene ${selectedSceneForPreview.value + 1}`)
  toast.success(`Removed ${character.name} from scene`)
}

const openCharacterSelector = async (index: number) => {
  currentSceneIndex.value = index
  const scene = scenes.value[index]
  selectedCharacterIds.value = scene.character_ids || []

  // Open modal immediately for instant feedback
  showCharacterSelector.value = true

  // Then fetch characters in the background
  try {
    await charactersStore.fetchCharacters(true) // force refresh
  } catch (error) {
    console.error('Failed to fetch characters:', error)
    toast.error('Failed to load characters')
  }
}

const closeCharacterSelector = () => {
  showCharacterSelector.value = false
  currentSceneIndex.value = null
  selectedCharacterIds.value = []
}

const confirmCharacterSelection = async (characters: any[]) => {
  if (currentSceneIndex.value !== null) {
    const scene = scenes.value[currentSceneIndex.value]
    scene.character_ids = characters.map(c => c.id)

    toast.success(`${characters.length} character${characters.length !== 1 ? 's' : ''} selected for scene ${currentSceneIndex.value + 1}`)
  }
  closeCharacterSelector()
}

const getImageGenerationErrorInfo = (payload: any, fallback = 'Image generation failed') => {
  const detail = payload?.detail
  const errorCode = detail?.error || detail?.code || payload?.error || payload?.code
  const message = (
    detail?.message ||
    (typeof detail === 'string' ? detail : undefined) ||
    payload?.message ||
    fallback
  )

  if (errorCode === 'content_blocked' || errorCode === 'CONTENT_BLOCKED') {
    return {
      title: 'Update prompt needed',
      message: message || 'The prompt or generated output was flagged as sensitive. Please revise the prompt and try again.',
      code: 'content_blocked'
    }
  }

  return {
    title: 'Failed to generate image',
    message,
    code: errorCode
  }
}

const generateSceneImage = async (index: number, prompt: string) => {
  if (!prompt.trim()) {
    toast.error('Please provide a prompt first')
    return
  }

  const scene = scenes.value[index]
  scene.isGenerating = true
  scene.generationProgress = 0

  try {
    const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:8000')

    logger.log(`🎬 Generating image for scene ${index + 1}`)
    logger.log(`📝 Prompt: "${prompt}"`)
    logger.log(`👥 Character IDs in scene:`, scene.character_ids)
    logger.log(`📚 Total characters in store:`, charactersStore.characters?.length || 0)

    // Get character reference images if characters are selected for this scene
    const referenceImages: string[] = []
    const referenceImageUrls: string[] = [] // URLs for models that support input_images (e.g., openai/gpt-image-2)

    if (scene.character_ids && scene.character_ids.length > 0) {
      // Fetch character data for each character
      for (const characterId of scene.character_ids) {
        try {
          const character = await charactersStore.getCharacter(characterId)

          // Get reference image URLs from character and convert to base64
          if (character.reference_images && character.reference_images.length > 0) {
            for (const refImage of character.reference_images) {
              if (refImage.image_url) {
                // Store the URL for models that support input_images
                referenceImageUrls.push(refImage.image_url)
                try {
                  // Fetch the image and convert to base64
                  const base64Image = await urlToBase64(refImage.image_url)
                  referenceImages.push(base64Image)
                } catch (error) {
                  console.error(`Failed to convert image URL to base64:`, error)
                  // Continue with other images even if one fails
                }
              }
            }
          }
        } catch (error) {
          console.error(`Failed to fetch character ${characterId}:`, error)
          // Continue with other characters even if one fails
        }
      }

      if (referenceImages.length > 0) {
        logger.log(`📷 Total reference images to send: ${referenceImages.length}`)
      }
    }

    // Clean prompt from @mentions and enhance with character descriptions
    let enhancedPrompt = prompt
    if (scene.character_ids && scene.character_ids.length > 0) {
      enhancedPrompt = cleanPromptFromMentions(prompt, scene.character_ids)
      logger.log(`🔄 Cleaned prompt: "${enhancedPrompt}"`)
    }
    enhancedPrompt = withSelectedVisualStylePrompt(enhancedPrompt)

    // Update progress: Starting generation
    scene.generationProgress = 10

    // Generate image with user-selected settings
    const requestBody: any = {
      prompt: enhancedPrompt,
      model: imageGenerationModel.value,
      width: imageAspectRatio.value === '9:16' ? 720 : 1280,
      height: imageAspectRatio.value === '9:16' ? 1280 : 720,
      num_outputs: 1,
      aspect_ratio: getModelCompatibleImageAspectRatio(imageGenerationModel.value, imageAspectRatio.value),
      output_format: 'jpg'
    }

    // Add Replicate input parameters for Plus Quality 2 model (openai/gpt-image-2)
    if (imageGenerationModel.value === 'openai/gpt-image-2') {
      const mappedAspectRatio = getModelCompatibleImageAspectRatio(imageGenerationModel.value, imageAspectRatio.value)

      // Replicate input parameters for openai/gpt-image-2
      requestBody.input = {
        prompt: requestBody.prompt,
        quality: 'low',
        background: 'auto',
        moderation: 'auto',
        aspect_ratio: mappedAspectRatio,
        output_format: 'webp',
        input_fidelity: 'low',
        number_of_images: 1,
        output_compression: 90
      }
      // Include reference images (from @ tagged characters) as input_images for openai/gpt-image-2
      if (referenceImageUrls.length > 0) {
        requestBody.input.input_images = referenceImageUrls
        logger.log(`📷 Including ${referenceImageUrls.length} reference image(s) in input_images for openai/gpt-image-2`)
      }
      console.log('[Plus Quality 2] UI aspect ratio:', imageAspectRatio.value, '→ API aspect ratio:', mappedAspectRatio)
      console.log('[Plus Quality 2] Full requestBody:', JSON.stringify(requestBody, null, 2))
    }

    // Include reference images if available
    if (referenceImages.length > 0) {
      requestBody.referenceImages = referenceImages
    }

    // Create AbortController with 5 minute timeout for image generation
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 300000) // 5 minutes

    const response = await fetch(`${API_BASE_URL}/api/image-generation/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
      },
      body: JSON.stringify(requestBody),
      signal: controller.signal
    })

    clearTimeout(timeoutId)

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}))
      const errorInfo = getImageGenerationErrorInfo(errorPayload)
      const error = new Error(errorInfo.message) as Error & { code?: string; title?: string; detail?: any }
      error.code = errorInfo.code
      error.title = errorInfo.title
      error.detail = errorPayload
      throw error
    }

    const result = await response.json()

    // Update progress: Generation request sent
    scene.generationProgress = 50

    // Fetch the generated image with 2 minute timeout
    const imageController = new AbortController()
    const imageTimeoutId = setTimeout(() => imageController.abort(), 120000) // 2 minutes

    const imageResponse = await fetch(`${API_BASE_URL}/api/image-generation/generations/${result.id}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
      },
      signal: imageController.signal
    })

    clearTimeout(imageTimeoutId)

    if (!imageResponse.ok) {
      throw new Error('Failed to fetch generated image')
    }

    // Update progress: Fetching result
    scene.generationProgress = 90

    const imageData = await imageResponse.json()

    logger.log('Image response data:', imageData)

    // Update scene with generated image - handle different response formats
    let generatedImageUrl = null
    let generatedImageData = null

    // Try different response structures
    if (imageData.generated_images && imageData.generated_images.length > 0) {
      generatedImageData = imageData.generated_images[0]
      generatedImageUrl = generatedImageData.signed_url
    } else if (imageData.signed_url) {
      // Direct signed URL in response
      generatedImageData = imageData
      generatedImageUrl = imageData.signed_url
    } else if (imageData.url) {
      // URL field in response
      generatedImageData = imageData
      generatedImageUrl = imageData.url
    }

    if (generatedImageUrl) {
      const imageWidth = generatedImageData.width || (imageAspectRatio.value === '9:16' ? 720 : 1280)
      const imageHeight = generatedImageData.height || (imageAspectRatio.value === '9:16' ? 1280 : 720)

      scene.generatedImage = {
        id: generatedImageData.id || result.id,
        url: generatedImageUrl,
        width: imageWidth,
        height: imageHeight,
        aspectRatio: generatedImageData.aspect_ratio || imageAspectRatio.value
      }

      // Update progress: Complete
      scene.generationProgress = 100

      logger.log(`✅ Image set for scene ${index + 1}:`, scene.generatedImage)
      toast.success(`Scene ${index + 1} image generated!`)
    } else {
      logger.error('❌ Could not find image URL in response:', imageData)
      throw new Error('Image URL not found in response')
    }
  } catch (error: any) {
    if (error.name === 'AbortError') {
      console.error(`Image generation timed out for scene ${index + 1}`)
      toast.error(`Scene ${index + 1} generation timed out`, {
        description: 'The request took too long. Please try again.'
      })
    } else {
      console.error(`Failed to generate image for scene ${index + 1}:`, error)
      const title = error.code === 'content_blocked' ? 'Update prompt needed' : (error.title || 'Failed to generate image')
      toast.error(title, {
        description: error.message || 'Please try again',
        duration: error.code === 'content_blocked' ? 9000 : 6000
      })
    }
  } finally {
    scene.isGenerating = false
    scene.generationProgress = 0
  }
}

const openGalleryReplacement = async (index: number) => {
  sceneIndexForImageReplacement.value = index
  galleryMode.value = 'replace'

  // Open modal immediately for instant feedback
  showGallerySelector.value = true

  // Then fetch gallery images and folders in the background
  try {
    await Promise.all([
      imageGenerationStore.fetchGallery(true),
      imageGenerationStore.fetchFolders()
    ])
    // Refresh any expired URLs
    await imageGenerationStore.batchRefreshGalleryUrls()
  } catch (error) {
    console.error('Failed to fetch gallery images:', error)
    toast.error('Failed to load gallery images')
  }
}

const openGalleryForNewScene = async () => {
  galleryMode.value = 'addNew'
  sceneIndexForImageReplacement.value = null

  // Open modal immediately for instant feedback
  showGallerySelector.value = true

  // Then fetch gallery images and folders in the background
  try {
    await Promise.all([
      imageGenerationStore.fetchGallery(true),
      imageGenerationStore.fetchFolders()
    ])
    // Refresh any expired URLs
    await imageGenerationStore.batchRefreshGalleryUrls()
  } catch (error) {
    console.error('Failed to fetch gallery images:', error)
    toast.error('Failed to load gallery images')
  }
}

const closeGallerySelector = () => {
  showGallerySelector.value = false
  sceneIndexForImageReplacement.value = null
  galleryMode.value = 'replace' // Reset to default
  imageReferenceGalleryMode.value = false // Reset image reference mode
  startFrameGalleryMode.value = false // Reset start frame mode
  endFrameGalleryMode.value = false // Reset end frame mode
  refreshedImageIds.clear() // Clear refresh tracking when closing modal
}

const openGalleryAssetSelector = async () => {
  galleryMode.value = 'replace'
  showGallerySelector.value = true

  try {
    await Promise.all([
      imageGenerationStore.fetchGallery(true),
      imageGenerationStore.fetchFolders()
    ])
    await imageGenerationStore.batchRefreshGalleryUrls()
  } catch (error) {
    console.error('Failed to fetch gallery images:', error)
    toast.error('Failed to load gallery images')
  }
}

const openImageReferenceSelector = async () => {
  imageReferenceGalleryMode.value = true
  startFrameGalleryMode.value = false
  endFrameGalleryMode.value = false
  await openGalleryAssetSelector()
}

const clearImageReference = () => {
  imageReferenceImage.value = null
}

const getCanonicalVideoAspectRatio = (aspectRatio?: string): '16:9' | '9:16' | '1:1' | undefined => {
  if (!aspectRatio) return undefined

  const normalized = aspectRatio.trim().toLowerCase()
  if (['16:9', '3:2', '4:3'].includes(normalized)) return '16:9'
  if (['9:16', '2:3', '3:4'].includes(normalized)) return '9:16'
  if (normalized === '1:1') return '1:1'

  const [widthText, heightText] = normalized.split(':')
  const width = Number(widthText)
  const height = Number(heightText)
  if (width > 0 && height > 0) {
    const ratio = width / height
    if (ratio > 1.15) return '16:9'
    if (ratio < 0.87) return '9:16'
    return '1:1'
  }

  return undefined
}

const getImageAspectRatio = (width?: number, height?: number, fallback?: string): '16:9' | '9:16' | '1:1' | undefined => {
  if (width && height) {
    const ratio = width / height
    if (ratio > 1.15) return '16:9'
    if (ratio < 0.87) return '9:16'
    return '1:1'
  }

  return getCanonicalVideoAspectRatio(fallback)
}

const buildSelectedReferenceImage = (image: any, url: string): SelectedReferenceImage => {
  const width = image.width || image.metadata?.width
  const height = image.height || image.metadata?.height

  return {
    id: image.id,
    url,
    width,
    height,
    aspectRatio: getImageAspectRatio(width, height, image.aspectRatio || image.aspect_ratio)
  }
}

// Start frame selection functions
const openStartFrameSelector = async () => {
  startFrameGalleryMode.value = true
  imageReferenceGalleryMode.value = false
  endFrameGalleryMode.value = false
  await openGalleryAssetSelector()
}

const clearStartFrame = () => {
  startFrameImage.value = null
}

// End frame selection functions
const openEndFrameSelector = async () => {
  endFrameGalleryMode.value = true
  imageReferenceGalleryMode.value = false
  startFrameGalleryMode.value = false
  await openGalleryAssetSelector()
}

const clearEndFrame = () => {
  endFrameImage.value = null
}

const loadMoreGalleryImages = async () => {
  isLoadingMoreGalleryImages.value = true
  try {
    await imageGenerationStore.loadMoreImages()
    // Update both gallery components' hasMore state based on store pagination
    const hasMore = imageGenerationStore.gallery.pagination.hasMore
    if (galleryViewRef.value) {
      galleryViewRef.value.setHasMore(hasMore)
    }
    if (gallerySelectorRef.value) {
      gallerySelectorRef.value.setHasMore(hasMore)
    }
  } catch (error) {
    console.error('Failed to load more gallery images:', error)
    toast.error('Failed to load more images')
  } finally {
    isLoadingMoreGalleryImages.value = false
    // Reset both gallery components' loading state
    if (galleryViewRef.value) {
      galleryViewRef.value.setLoadingMore(false)
    }
    if (gallerySelectorRef.value) {
      gallerySelectorRef.value.setLoadingMore(false)
    }
  }
}

// Folder handlers
const handleCreateFolder = async (name: string, color: string) => {
  try {
    await imageGenerationStore.createFolder({ name, color })
    toast.success(`Folder "${name}" created`)
  } catch (error: any) {
    console.error('Failed to create folder:', error)
    toast.error(error.message || 'Failed to create folder')
  }
}

const handleRenameFolder = async (folderId: string, name: string, color: string) => {
  try {
    await imageGenerationStore.updateFolder(folderId, { name, color })
    toast.success('Folder updated')
  } catch (error: any) {
    console.error('Failed to update folder:', error)
    toast.error(error.message || 'Failed to update folder')
  }
}

const handleDeleteFolder = async (folderId: string) => {
  try {
    await imageGenerationStore.deleteFolder(folderId)
    toast.success('Folder deleted')
  } catch (error: any) {
    console.error('Failed to delete folder:', error)
    toast.error(error.message || 'Failed to delete folder')
  }
}

const handleDeleteImage = async (image: any) => {
  try {
    await imageGenerationStore.deleteImage(image.id)
    toast.success('Image deleted')
  } catch (error: any) {
    console.error('Failed to delete image:', error)
    toast.error(error.message || 'Failed to delete image')
  }
}

const handleBatchDeleteImages = async (imageIds: string[]) => {
  try {
    const count = imageIds.length
    toast.info(`Deleting ${count} image${count !== 1 ? 's' : ''}...`)

    // Delete all images
    await Promise.all(imageIds.map(id => imageGenerationStore.deleteImage(id)))

    toast.success(`${count} image${count !== 1 ? 's' : ''} deleted`)
  } catch (error: any) {
    console.error('Failed to delete images:', error)
    toast.error(error.message || 'Failed to delete images')
  }
}

const handleMoveImage = async (imageId: string, folderId: string | null) => {
  try {
    await imageGenerationStore.moveImageToFolder(imageId, folderId)
    const folderName = folderId
      ? imageGenerationStore.folders.folders.find(f => f.id === folderId)?.name || 'folder'
      : 'Uncategorized'
    toast.success(`Image moved to ${folderName}`)
  } catch (error: any) {
    console.error('Failed to move image:', error)
    toast.error(error.message || 'Failed to move image')
  }
}

const handleMoveImages = async (imageIds: string[], folderId: string | null) => {
  try {
    await imageGenerationStore.moveImagesToFolder(imageIds, folderId)
    const folderName = folderId
      ? imageGenerationStore.folders.folders.find(f => f.id === folderId)?.name || 'folder'
      : 'Uncategorized'
    const count = imageIds.length
    toast.success(`${count} image${count !== 1 ? 's' : ''} moved to ${folderName}`)
  } catch (error: any) {
    console.error('Failed to move images:', error)
    toast.error(error.message || 'Failed to move images')
  }
}

// Track which images we've already tried to refresh to avoid infinite loops
const refreshedImageIds = new Set<string>()

const handleGalleryMediaError = async (image: any) => {
  // Prevent infinite refresh loops
  if (refreshedImageIds.has(image.id)) {
    console.warn(`Image ${image.id} failed to load after refresh attempt`)
    return
  }

  try {
    console.log(`Refreshing URL for image ${image.id} due to load error`)
    refreshedImageIds.add(image.id)

    // Refresh the signed URL for this specific image
    await imageGenerationStore.refreshImageUrls(image.id)

    // Reset the image load state in both gallery components so they retry loading
    if (galleryViewRef.value) {
      galleryViewRef.value.resetImageLoadState(image.id)
    }
    if (gallerySelectorRef.value) {
      gallerySelectorRef.value.resetImageLoadState(image.id)
    }

    // Clear the refresh tracking after a delay to allow future refreshes if needed
    setTimeout(() => {
      refreshedImageIds.delete(image.id)
    }, 60000) // Clear after 1 minute
  } catch (error) {
    console.error(`Failed to refresh URL for image ${image.id}:`, error)
  }
}

const confirmGalleryImageSelection = async (image: any) => {
  const url = image.signed_url || image.url
  if (!url) {
    toast.error('Selected media URL is unavailable')
    return
  }

  const isVideo = image.media_type === 'video' || /\.(mp4|mov|webm|avi|mkv)(\?|$)/i.test(url)

  if (imageReferenceGalleryMode.value || startFrameGalleryMode.value || endFrameGalleryMode.value) {
    if (isVideo) {
      toast.error('Please select an image, not a video')
      return
    }

    if (imageReferenceGalleryMode.value) {
      imageReferenceImage.value = buildSelectedReferenceImage(image, url)
      imageReferenceGalleryMode.value = false
      closeGallerySelector()
      return
    }

    if (startFrameGalleryMode.value) {
      startFrameImage.value = buildSelectedReferenceImage(image, url)
      startFrameGalleryMode.value = false
      closeGallerySelector()
      return
    }

    if (endFrameGalleryMode.value) {
      endFrameImage.value = buildSelectedReferenceImage(image, url)
      endFrameGalleryMode.value = false
      closeGallerySelector()
      return
    }
  }

  const width = image.width || 1024
  const height = image.height || 1024
  const aspectRatio = width > height ? '16:9' : height > width ? '9:16' : '1:1'

  if (galleryMode.value === 'addNew') {
    // Create a new scene with the selected image
    let start_time = 0
    let end_time = 5

    if (scenes.value.length > 0) {
      const lastScene = scenes.value[scenes.value.length - 1]
      start_time = lastScene.end_time || 0
      end_time = start_time + 5
    }

    const newScene: Scene = {
      id: crypto.randomUUID(),
      description: 'Scene from gallery',
      prompt: 'Image loaded from gallery',
      start_time: start_time,
      end_time: end_time,
      character_ids: [],
      isGenerating: false,
      generationProgress: 0,
      camera_movement: 'static',
      transition_type: 'fade',
      transition_duration: 1,
      greenscreen_effect: ''
    }

    if (isVideo) {
      newScene.animatedVideo = {
        id: image.id,
        url: url,
        duration: image.duration || 5,
        thumbnailUrl: url
      }
      toast.success('New scene created with video')
    } else {
      newScene.generatedImage = {
        id: image.id,
        url: url,
        width,
        height,
        aspectRatio
      }
      toast.success('New scene created with image')
    }

    scenes.value.push(newScene)
    await saveScenes()
    // Don't close modal when adding new scenes - allow multiple selections
  } else if (sceneIndexForImageReplacement.value !== null) {
    // Replace mode - existing behavior
    const scene = scenes.value[sceneIndexForImageReplacement.value]

    if (isVideo) {
      scene.animatedVideo = {
        id: image.id,
        url: url,
        duration: image.duration || 5,
        thumbnailUrl: url
      }
      delete scene.generatedImage
      toast.success(`Video replaced for scene ${sceneIndexForImageReplacement.value + 1}`)
    } else {
      scene.generatedImage = {
        id: image.id,
        url: url,
        width,
        height,
        aspectRatio
      }
      delete scene.animatedVideo
      toast.success(`Image replaced for scene ${sceneIndexForImageReplacement.value + 1}`)
    }

    await saveScenes()
    closeGallerySelector()
  }
}

// Handle image click from gallery view - creates a new scene with the image
const handleGalleryViewImageClick = async (image: any) => {
  const width = image.width || 1024
  const height = image.height || 1024
  const aspectRatio = width > height ? '16:9' : height > width ? '9:16' : '1:1'
  const url = image.signed_url || image.url
  const isVideo = /\.(mp4|mov|webm|avi|mkv)(\?|$)/i.test(url)

  // Calculate start and end times
  let start_time = 0
  let end_time = 5

  if (scenes.value.length > 0) {
    const lastScene = scenes.value[scenes.value.length - 1]
    start_time = lastScene.end_time || 0
    end_time = start_time + 5
  }

  // Create a new scene
  const newScene: Scene = {
    id: crypto.randomUUID(),
    description: 'Scene from gallery',
    prompt: image.prompt || 'Image loaded from gallery',
    start_time: start_time,
    end_time: end_time,
    character_ids: [],
    isGenerating: false,
    generationProgress: 0,
    camera_movement: 'static',
    transition_type: 'fade',
    transition_duration: 1,
    greenscreen_effect: ''
  }

  if (isVideo) {
    newScene.animatedVideo = {
      id: image.id,
      url: url,
      duration: image.duration || 5,
      thumbnailUrl: url
    }
    toast.success('New scene created with video')
  } else {
    newScene.generatedImage = {
      id: image.id,
      url: url,
      width,
      height,
      aspectRatio
    }
    toast.success('New scene created with image')
  }

  scenes.value.push(newScene)
  await saveScenes()

  // Stay in gallery view to allow adding more images
}

// Handle image upload from computer for gallery replacement
const handleGalleryImageUpload = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const files = input.files

  if (!files || files.length === 0) return

  try {
    isUploadingGalleryImage.value = true

    // Upload all selected files
    const uploadedImages = await imageService.uploadImages(Array.from(files))

    if (uploadedImages && uploadedImages.length > 0) {
      if (imageReferenceGalleryMode.value || startFrameGalleryMode.value || endFrameGalleryMode.value) {
        const uploadedImage = uploadedImages[0]
        const url = uploadedImage.signed_url || (uploadedImage as any).url
        const isVideoFile = (uploadedImage as any).media_type === 'video' || /\.(mp4|mov|webm|avi|mkv)(\?|$)/i.test(url)

        if (!url) {
          toast.error('Uploaded image URL is unavailable')
          return
        }

        if (isVideoFile) {
          toast.error('Please upload an image, not a video')
          return
        }

        if (imageReferenceGalleryMode.value) {
          imageReferenceImage.value = buildSelectedReferenceImage(uploadedImage, url)
          toast.success('Reference image selected')
        } else if (startFrameGalleryMode.value) {
          startFrameImage.value = buildSelectedReferenceImage(uploadedImage, url)
          toast.success('Start frame selected')
        } else {
          endFrameImage.value = buildSelectedReferenceImage(uploadedImage, url)
          toast.success('End frame selected')
        }

        await imageGenerationStore.fetchGallery(true)
        closeGallerySelector()
        return
      }

      // Mode 1: Replace existing scene (single file only)
      if (galleryMode.value === 'replace' && sceneIndexForImageReplacement.value !== null) {
        const uploadedImage = uploadedImages[0]
        const scene = scenes.value[sceneIndexForImageReplacement.value]

        // Check if uploaded file is a video based on URL
        const url = uploadedImage.signed_url
        const isVideoFile = /\.(mp4|mov|webm|avi|mkv)(\?|$)/i.test(url)

        if (isVideoFile) {
          // Store as animated video
          scene.animatedVideo = {
            id: uploadedImage.id,
            url: url,
            duration: (uploadedImage as any).duration || 5,
            thumbnailUrl: url
          }
          // Clear generated image
          delete scene.generatedImage
          toast.success(`Scene ${sceneIndexForImageReplacement.value + 1} video uploaded and replaced successfully`)
        } else {
          // Replace the scene's generated image with the uploaded one
          scene.generatedImage = {
            id: uploadedImage.id,
            url: url,
            width: uploadedImage.width,
            height: uploadedImage.height,
            aspectRatio: `${uploadedImage.width}:${uploadedImage.height}`
          }
          // Clear animated video when replacing with image
          delete scene.animatedVideo
          toast.success(`Scene ${sceneIndexForImageReplacement.value + 1} image uploaded and replaced successfully`)
        }

        // Save the updated scene
        await saveScenes()

        // Refresh the gallery to show the newly uploaded file
        await imageGenerationStore.fetchGallery(true)

        // Close the modal
        closeGallerySelector()
      }
      // Mode 2: Add new scenes (multiple files supported)
      else if (galleryMode.value === 'addNew') {
        // Calculate starting time for new scenes
        let start_time = 0
        if (scenes.value.length > 0) {
          const lastScene = scenes.value[scenes.value.length - 1]
          start_time = lastScene.end_time || 0
        }

        // Create a new scene for each uploaded file
        for (const uploadedImage of uploadedImages) {
          const url = uploadedImage.signed_url
          const isVideoFile = /\.(mp4|mov|webm|avi|mkv)(\?|$)/i.test(url)
          const width = uploadedImage.width || 1024
          const height = uploadedImage.height || 1024
          const aspectRatio = width > height ? '16:9' : height > width ? '9:16' : '1:1'
          const duration = (uploadedImage as any).duration || 5

          const end_time = start_time + duration

          const newScene: Scene = {
            id: crypto.randomUUID(),
            description: 'Scene from uploaded file',
            prompt: 'Uploaded from computer',
            start_time: start_time,
            end_time: end_time,
            character_ids: [],
            isGenerating: false,
            generationProgress: 0,
            camera_movement: 'static',
            transition_type: 'fade',
            transition_duration: 1,
            greenscreen_effect: ''
          }

          if (isVideoFile) {
            newScene.animatedVideo = {
              id: uploadedImage.id,
              url: url,
              duration: duration,
              thumbnailUrl: url
            }
          } else {
            newScene.generatedImage = {
              id: uploadedImage.id,
              url: url,
              width: width,
              height: height,
              aspectRatio: aspectRatio
            }
          }

          scenes.value.push(newScene)

          // Update start_time for next scene
          start_time = end_time
        }

        // Save all new scenes
        await saveScenes()

        // Refresh the gallery to show the newly uploaded files
        await imageGenerationStore.fetchGallery(true)

        // Close the modal
        closeGallerySelector()

        // Show success message
        toast.success(`${uploadedImages.length} scene${uploadedImages.length > 1 ? 's' : ''} created successfully!`)
      }
    }
  } catch (error) {
    console.error('Failed to upload file:', error)
    const message = error instanceof Error ? error.message : 'Unknown error'
    toast.error(`Failed to upload file: ${message}`)
  } finally {
    isUploadingGalleryImage.value = false
    // Reset the input so the same file can be selected again
    if (input) {
      input.value = ''
    }
  }
}

const updateScenePrompt = (index: number, newPrompt: string) => {
  scenes.value[index].prompt = newPrompt
}

const deleteScene = (index: number) => {
  if (confirm(`Are you sure you want to delete Scene ${index + 1}?`)) {
    scenes.value.splice(index, 1)
    syncTimelineSegmentsFromScenes()
    toast.success('Scene deleted')
  }
}

const getFiniteSceneNumber = (value?: number | string | null) => {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }

  if (typeof value === 'string' && value.trim() !== '') {
    const parsedValue = Number(value)
    return Number.isFinite(parsedValue) ? parsedValue : null
  }

  return null
}

const getSceneTimeUnitScale = (sceneList: Scene[]) => (
  sceneList.some(scene =>
    (getFiniteSceneNumber(scene.start_time) ?? 0) > 1000
    || (getFiniteSceneNumber(scene.end_time) ?? 0) > 1000
  ) ? 1000 : 1
)

const getSceneTimelineDuration = (scene: Scene, unitScale = 1) => {
  const startTime = getFiniteSceneNumber(scene.start_time)
  const endTime = getFiniteSceneNumber(scene.end_time)
  if (startTime !== null && endTime !== null && endTime > startTime) {
    return endTime - startTime
  }

  const audioDuration = getSceneAudioDuration(scene)
  if (audioDuration > 0) {
    return audioDuration * unitScale
  }

  const targetDuration = getFiniteSceneNumber(scene.target_duration)
  if (targetDuration !== null && targetDuration > 0) {
    return unitScale === 1000 && targetDuration < 60 ? targetDuration * 1000 : targetDuration
  }

  return 3 * unitScale
}

const resequenceSceneTimelineByOrder = () => {
  const unitScale = getSceneTimeUnitScale(scenes.value)
  let cursor = 0

  scenes.value = scenes.value.map(scene => {
    const duration = Math.max(getSceneTimelineDuration(scene, unitScale), 0.1 * unitScale)
    const updatedScene: Scene = {
      ...scene,
      start_time: cursor,
      end_time: cursor + duration,
      target_duration: unitScale === 1000 ? duration / 1000 : duration,
    }
    cursor += duration
    return updatedScene
  })
}

const syncTimelineSegmentsFromScenes = () => {
  timelineSegments.value = scenes.value
    .filter(scene => scene.animatedVideo?.id || scene.generatedImage?.id)
    .map((scene, index) => ({
      image_id: scene.animatedVideo?.id || scene.generatedImage?.id,
      scene_description: scene.description || scene.prompt,
      prompt: scene.prompt,
      start_time: scene.start_time || 0,
      end_time: scene.end_time || 0,
      transition_type: scene.transition_type || 'fade',
      transition_duration: scene.transition_duration ?? 0.5,
      camera_movement: scene.camera_movement || 'zoom_in',
      greenscreen_effect: scene.greenscreen_effect || null,
      sort_order: index,
      character_ids: scene.character_ids || []
    }))
}

const sortTimelineSegmentsByOrder = (segments: any[]) => {
  return [...segments].sort((a, b) => {
    const aOrder = getFiniteSceneNumber(a?.sort_order) ?? getFiniteSceneNumber(a?.scene_index) ?? 0
    const bOrder = getFiniteSceneNumber(b?.sort_order) ?? getFiniteSceneNumber(b?.scene_index) ?? 0
    return aOrder - bOrder
  })
}

const handleSceneDragEnd = async (event?: { oldIndex?: number; newIndex?: number }) => {
  isReorderingScenes.value = false

  const oldIndex = event?.oldIndex
  const newIndex = event?.newIndex

  if (
    typeof oldIndex !== 'number'
    || typeof newIndex !== 'number'
    || oldIndex === newIndex
  ) {
    return
  }

  const selectedIndex = selectedSceneForPreview.value
  if (selectedIndex !== null) {
    if (selectedIndex === oldIndex) {
      selectedSceneForPreview.value = newIndex
    } else if (oldIndex < newIndex && selectedIndex > oldIndex && selectedIndex <= newIndex) {
      selectedSceneForPreview.value = selectedIndex - 1
    } else if (oldIndex > newIndex && selectedIndex >= newIndex && selectedIndex < oldIndex) {
      selectedSceneForPreview.value = selectedIndex + 1
    }
  }

  resequenceSceneTimelineByOrder()
  syncTimelineSegmentsFromScenes()

  try {
    if (projectId.value || generatedAudio.value?.projectId) {
      await saveScenes()
      toast.success('Scene order updated and saved')
    } else {
      toast.success('Scene order updated')
    }
  } catch (error) {
    console.error('Failed to save reordered scenes:', error)
    toast.error('Scene order changed locally, but saving failed')
  }
}

// Add a new blank scene
const addNewScene = () => {
  // Calculate start and end times based on existing scenes
  let start_time = 0
  let end_time = 5 // 5 seconds

  if (scenes.value.length > 0) {
    const lastScene = scenes.value[scenes.value.length - 1]
    start_time = lastScene.end_time || 0
    end_time = start_time + 5 // Add 5 seconds
  }

  const newScene: Scene = {
    id: crypto.randomUUID(),
    description: 'New scene description',
    prompt: 'Enter your image generation prompt here',
    start_time: start_time,
    end_time: end_time,
    character_ids: [],
    isGenerating: false,
    generationProgress: 0,
    camera_movement: 'static',
    transition_type: 'fade',
    transition_duration: 1,
    greenscreen_effect: ''
  }

  scenes.value.push(newScene)
  toast.success('New scene added', {
    description: 'Edit the prompt and generate an image'
  })

  logger.log('New scene added:', newScene)
}

// Animate scene image to video (exact copy from VideoGenerator.vue)
const animateSceneImage = async (sceneIndex: number) => {
  const scene = scenes.value[sceneIndex]

  if (!scene.animationPrompt || !scene.animationPrompt.trim()) {
    console.error('❌ Animation prompt is required')
    toast.error('Please enter an animation prompt')
    return
  }

  // Get the selected model or default to first model
  const selectedModel = normalizeVideoModelSelection(scene.animationModel || 'stability-ai/stable-video-diffusion')
  const isTextToVideo = isGeminiOmniVideoModel(selectedModel) && !startFrameImage.value?.id && !scene.generatedImage?.id

  // Check if we have either a custom start frame, a generated image, or a text-to-video model
  const hasStartFrame = startFrameImage.value?.id || (scene.generatedImage && scene.generatedImage.id)
  if (!hasStartFrame && !isTextToVideo) {
    console.error('❌ No image available for animation')
    toast.error('No image available to animate. Select a start frame or use Gemini Omni Flash for text-to-video.')
    return
  }

  // Get the selected resolution or default to 480p
  const selectedResolution = scene.animationResolution || '480p'

  // Get start frame ID - use custom selection if provided, otherwise use generated image
  const startFrameId = startFrameImage.value?.id || scene.generatedImage?.id

  if (!startFrameId && !isTextToVideo) {
    console.error('❌ No valid start frame ID')
    toast.error('No valid image ID found')
    return
  }

  // Get end frame ID if provided and using WAN model
  const endFrameId = (
    endFrameImage.value?.id &&
    supportsEndFrameVideoModel(selectedModel)
  ) ? endFrameImage.value.id : undefined

  const klingAvatarAudioUrl = selectedModel === 'kwaivgi/kling-avatar-v2'
    ? getKlingAvatarAudioUrl(scene)
    : undefined
  if (selectedModel === 'kwaivgi/kling-avatar-v2' && !klingAvatarAudioUrl) {
    toast.error('Kling Avatar requires audio. Generate scene audio or project audio first.')
    return
  }

  const seedanceSceneAudioUrl = selectedModel.startsWith('bytedance/seedance')
    ? getSceneAudioUrl(scene)
    : undefined

  const audioUrl = klingAvatarAudioUrl || seedanceSceneAudioUrl

  const duration = selectedModel === 'kwaivgi/kling-avatar-v2'
    ? Math.ceil(getSceneAudioDuration(scene) || generatedAudio.value?.duration || scene.animationDuration || 0) || undefined
    : scene.animationDuration
  const sourceAspectRatio = getCanonicalVideoAspectRatio(startFrameImage.value?.aspectRatio)
    || getImageAspectRatio(
      scene.generatedImage?.width,
      scene.generatedImage?.height,
      scene.generatedImage?.aspectRatio
    )
    || getCanonicalVideoAspectRatio(imageAspectRatio.value)
    || '16:9'

  isAnimatingImage.value[sceneIndex] = true
  animationProgress.value[sceneIndex] = 0

  try {
    // Show progress
    const progressInterval = setInterval(() => {
      if (animationProgress.value[sceneIndex] < 90) {
        animationProgress.value[sceneIndex] += Math.random() * 10
      }
    }, 1000)

    // Call the animation API. Gemini Omni Flash can generate from text alone.
    const result = isTextToVideo
      ? await imageService.generateTextVideo(
        scene.animationPrompt,
        selectedModel,
        selectedResolution,
        duration,
        sourceAspectRatio
      )
      : await imageService.animateImage(
        startFrameId!,
        scene.animationPrompt,
        selectedModel,
        selectedResolution,
        endFrameId,
        audioUrl,
        duration,
        sourceAspectRatio
      )

    clearInterval(progressInterval)
    animationProgress.value[sceneIndex] = 100

    // Update the scene with the animated video
    scenes.value[sceneIndex].animatedVideo = {
      id: result.video_id,
      url: result.signed_url,
      duration: result.duration,
      thumbnailUrl: startFrameImage.value?.url || scene.generatedImage?.url || result.signed_url // Use the source image as thumbnail
    }

    toast.success(`Scene ${sceneIndex + 1} image animated successfully! (${result.duration}s video)`)

  } catch (error: any) {
    console.error(`❌ Animation failed for scene ${sceneIndex + 1}:`, error)
    toast.error(error.message || 'Animation failed. Please try again.')
    animationProgress.value[sceneIndex] = 0
  } finally {
    isAnimatingImage.value[sceneIndex] = false
  }
}

// Add animated video to timeline (exact copy from VideoGenerator.vue)
const addAnimatedVideoToTimeline = (sceneIndex: number) => {
  const scene = scenes.value[sceneIndex]

  if (!scene.animatedVideo || !scene.animatedVideo.id) {
    console.error('❌ No animated video available')
    toast.error('No animated video available to add to timeline')
    return
  }

  toast.info('Timeline integration coming soon!', {
    description: 'This feature will be available in the video editor'
  })

  logger.log('Animated video ready for timeline:', scene.animatedVideo)
}

// Copy image URL to clipboard (exact copy from VideoGenerator.vue)
const copyImageUrl = async (imageUrl: string) => {
  try {
    await navigator.clipboard.writeText(imageUrl)
    toast.success('Video URL copied to clipboard')
  } catch (err) {
    console.error('❌ Failed to copy video URL:', err)
    toast.error('Failed to copy URL')
  }
}

// Update scene video effects
const updateSceneCameraMovement = (index: number, value: string) => {
  scenes.value[index].camera_movement = value
}

const updateSceneTransitionType = (index: number, value: string) => {
  scenes.value[index].transition_type = value
}

const updateSceneTransitionDuration = (index: number, value: number) => {
  scenes.value[index].transition_duration = value
}

const updateSceneGreenscreenEffect = (index: number, value: string) => {
  console.log(`🎬 Updating greenscreen effect for scene ${index + 1}:`, value)
  scenes.value[index].greenscreen_effect = value
  console.log(`✅ Scene ${index + 1} greenscreen_effect set to:`, scenes.value[index].greenscreen_effect)
}

const updateSceneTimeRange = (index: number, startTime: number, endTime: number) => {
  scenes.value[index].start_time = startTime
  scenes.value[index].end_time = endTime
  toast.success(`Scene ${index + 1} time updated: ${startTime.toFixed(1)}s - ${endTime.toFixed(1)}s`)
}

// Show final generated video in preview
const showFinalVideoPreview = () => {
  // Set showingFinalVideo BEFORE showStoryboardLayout to prevent watch from selecting first scene
  showingFinalVideo.value = true
  showingGallery.value = false
  showingPreview.value = false
  showingThumbnail.value = false
  selectedSceneForPreview.value = null
  showStoryboardLayout.value = true
  // toast.success('Showing final video', { description: 'Preview of your generated video' })
}

// Show gallery view
const showGalleryView = () => {
  showingGallery.value = true
  showingFinalVideo.value = false
  showingPreview.value = false
  showingThumbnail.value = false
  selectedSceneForPreview.value = null
  showStoryboardLayout.value = true
}

// Show thumbnail generation view
const showThumbnailView = () => {
  showingThumbnail.value = true
  showingGallery.value = false
  showingFinalVideo.value = false
  showingPreview.value = false
  selectedSceneForPreview.value = null
  showStoryboardLayout.value = true

  if (!thumbnailPrompt.value.trim()) {
    thumbnailPrompt.value = buildDefaultThumbnailPrompt()
  }
}

// Handle scene card click - switch to preview
const handleSceneClick = (index: number) => {
  selectedSceneForPreview.value = index
  showStoryboardLayout.value = true
  showingGallery.value = false
  showingFinalVideo.value = false
  showingPreview.value = false
  showingThumbnail.value = false
}

// Check and load final generated video (similar to ProjectGeneratorView)
const checkAndLoadFinalVideo = async () => {
  if (!projectId.value || !currentUserId.value) {
    finalGeneratedVideo.value = null
    finalVideoExists.value = false
    if (!currentUserId.value) {
      logger.log('⏭️ Cannot check video - user ID not available yet')
    }
    return
  }

  isCheckingFinalVideo.value = true

  try {
    const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:8000')
    const token = localStorage.getItem('access_token')
    let resolvedVideo = false

    // First source of truth: project details endpoint (handles any backend naming scheme).
    const detailsResponse = await fetch(`${API_BASE_URL}/api/video/projects/${projectId.value}/details-full`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })

    if (detailsResponse.ok) {
      const detailsData = await detailsResponse.json()
      const detailsVideoUrl = detailsData?.project?.gcs_signed_url
      const detailsDuration = detailsData?.project?.duration || 0
      const detailsStatus = detailsData?.project?.status

      if (detailsVideoUrl) {
        finalGeneratedVideo.value = {
          url: detailsVideoUrl,
          duration: detailsDuration
        }
        finalVideoExists.value = true
        resolvedVideo = true
        logger.log('✅ Loaded final generated video from project details:', finalGeneratedVideo.value)
      } else if (detailsStatus !== 'completed') {
        finalGeneratedVideo.value = null
        finalVideoExists.value = false
        return
      }
    }

    // Fallback: direct file lookup with multiple naming variants.
    if (!resolvedVideo) {
      const candidateVideoFileIds = [
        `output/${currentUserId.value}/${projectId.value}/final_video_${projectId.value}_en.mp4`,
        `output/${currentUserId.value}/${projectId.value}/multi_scene_concat_${projectId.value}.mp4`,
        `videos/${currentUserId.value}/${projectId.value}_en.mp4`,
        `videos/${currentUserId.value}/${projectId.value}.mp4`
      ]

      for (const videoFileId of candidateVideoFileIds) {
        const apiUrl = `${API_BASE_URL}/api/video/projects/video/${videoFileId}`
        logger.log('🎬 Checking for final video at:', apiUrl)

        const response = await fetch(apiUrl, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })

        logger.log('📡 Video check response status:', response.status, 'for', videoFileId)

        if (!response.ok) {
          continue
        }

        const contentType = response.headers.get('content-type') || ''
        if (!contentType.includes('application/json')) {
          continue
        }

        const videoData = await response.json()
        if (!videoData?.url) {
          continue
        }

        finalGeneratedVideo.value = {
          url: videoData.url,
          duration: videoData.duration || 0
        }
        finalVideoExists.value = true
        resolvedVideo = true
        logger.log('✅ Loaded final generated video from file lookup:', finalGeneratedVideo.value)
        break
      }
    }

    if (!resolvedVideo) {
      finalGeneratedVideo.value = null
      finalVideoExists.value = false
      logger.log('⏭️ No final video found from details or file lookup')
    }
  } catch (err) {
    console.error('❌ Error checking final video:', err)
    finalGeneratedVideo.value = null
    finalVideoExists.value = false
  } finally {
    isCheckingFinalVideo.value = false
  }
}

// Effects Presets
const randomizeAllEffects = () => {
  const format = videoFormat.value // v = vertical, h = horizontal, s = square
  const cameraMovements = ['static', 'pan_right', 'pan_left', 'pan_up', 'pan_down', 'zoom_in', 'zoom_out', 'doodle_slow', 'doodle_fast']
  const transitions = ['cut', 'fade', 'fadeblack', 'fadewhite', 'distance', 'wipeleft', 'wiperight', 'wipeup', 'wipedown', 'slideleft', 'slideright', 'slideup', 'slidedown', 'smoothleft', 'smoothright', 'smoothup', 'smoothdown', 'circlecrop', 'rectcrop', 'circleclose', 'circleopen', 'dissolve', 'pixelize', 'radial']

  console.log(`Applying random effects for ${format === 'v' ? 'vertical' : format === 'h' ? 'horizontal' : 'square'} video`)

  scenes.value.forEach(scene => {
    scene.camera_movement = cameraMovements[Math.floor(Math.random() * cameraMovements.length)]
    scene.transition_type = transitions[Math.floor(Math.random() * transitions.length)]
    scene.transition_duration = 0.5

    // Randomize greenscreen effect (50% chance of having one)
    const effects = greenscreenEffects.value
    if (Math.random() > 0.5 && effects.length > 1) {
      // Skip the first option which is "No Effect"
      const randomEffect = effects[Math.floor(Math.random() * (effects.length - 1)) + 1]
      scene.greenscreen_effect = randomEffect.value
    } else {
      scene.greenscreen_effect = ''
    }
  })

  // Add visual flash effect to scene cards
  highlightSceneCards()
  toast.success('Applied random effects to all scenes!')
}

const applyWhiteboardDoodle = () => {
  const format = videoFormat.value // v = vertical, h = horizontal, s = square
  const transitions = ['cut', 'fade', 'fadeblack', 'fadewhite', 'distance', 'wipeleft', 'wiperight', 'wipeup', 'wipedown', 'slideleft', 'slideright', 'slideup', 'slidedown', 'smoothleft', 'smoothright', 'smoothup', 'smoothdown', 'circlecrop', 'rectcrop', 'circleclose', 'circleopen', 'dissolve', 'pixelize', 'radial']

  console.log(`Applying Whiteboard Doodle for ${format === 'v' ? 'vertical' : format === 'h' ? 'horizontal' : 'square'} video`)

  scenes.value.forEach(scene => {
    scene.camera_movement = 'doodle_fast'
    scene.transition_type = transitions[Math.floor(Math.random() * transitions.length)]
    scene.transition_duration = 0.5
    scene.greenscreen_effect = '' // No greenscreen effect
  })

  // Add visual flash effect to scene cards
  highlightSceneCards()
  toast.success('Applied Whiteboard Doodle preset to all scenes!')
}

const applyOldFilmBlack = () => {
  const format = videoFormat.value // v = vertical, h = horizontal, s = square
  const suffix = videoAspectRatio.value === '16:9' ? '_h' : '_v'
  console.log(`Applying Old Film Black for ${format === 'v' ? 'vertical' : format === 'h' ? 'horizontal' : 'square'} video`)

  scenes.value.forEach(scene => {
    scene.greenscreen_effect = `old_film_black${suffix}`
  })

  // Add visual flash effect to scene cards
  highlightSceneCards()
  toast.success('Applied Old Film Black effect to all scenes!')
}

const applyFireEffect = () => {
  const format = videoFormat.value // v = vertical, h = horizontal, s = square
  const suffix = videoAspectRatio.value === '16:9' ? '_h' : '_v'
  console.log(`Applying Fire effect for ${format === 'v' ? 'vertical' : format === 'h' ? 'horizontal' : 'square'} video`)

  scenes.value.forEach(scene => {
    scene.greenscreen_effect = `fire1${suffix}`
  })

  // Add visual flash effect to scene cards
  highlightSceneCards()
  toast.success('Applied Fire effect to all scenes!')
}

const applyZoomInAll = () => {
  const format = videoFormat.value // v = vertical, h = horizontal, s = square
  console.log(`Applying Zoom In for ${format === 'v' ? 'vertical' : format === 'h' ? 'horizontal' : 'square'} video`)

  scenes.value.forEach(scene => {
    scene.camera_movement = 'zoom_in'
  })

  // Add visual flash effect to scene cards
  highlightSceneCards()
  toast.success('Applied Zoom In to all scenes!')
}

const removeAllEffects = () => {
  console.log('Removing all effects from all scenes')

  scenes.value.forEach(scene => {
    scene.camera_movement = 'static'
    scene.transition_type = 'cut'
    scene.transition_duration = 0.5
    scene.greenscreen_effect = ''
  })

  // Add visual flash effect to scene cards
  highlightSceneCards()
  toast.success('Removed all effects from all scenes!')
}

// Visual highlight for effect input boxes when presets are applied
const highlightSceneCards = () => {
  nextTick(() => {
    // Target all select inputs in scene cards
    const sceneCards = document.querySelectorAll('.scene-card')
    console.log('Found scene cards:', sceneCards.length)
    sceneCards.forEach(card => {
      // Find the select inputs for camera, transition, and greenscreen
      const selectInputs = card.querySelectorAll('select')
      console.log('Found select inputs in card:', selectInputs.length)
      selectInputs.forEach(select => {
        console.log('Adding flash to select:', select)
        select.classList.add('effect-input-flash')
        // Remove the class after animation completes
        setTimeout(() => {
          select.classList.remove('effect-input-flash')
        }, 2000)
      })
    })
  })
}

// Handle timeline scene updates
const handleScenesUpdate = (updatedScenes: Scene[]) => {
  // Log the time changes for debugging
  updatedScenes.forEach((scene, index) => {
    const oldScene = scenes.value[index]
    if (oldScene && (oldScene.start_time !== scene.start_time || oldScene.end_time !== scene.end_time)) {
      console.log(`🔄 Scene ${index + 1} times updated:`, {
        old: { start: oldScene.start_time, end: oldScene.end_time },
        new: { start: scene.start_time, end: scene.end_time }
      })
    }
  })

  scenes.value = updatedScenes
  syncTimelineSegmentsFromScenes()
  logger.log('Scenes updated from timeline', updatedScenes)
}

// Handle timeline seek
const handleSeek = (time: number) => {
  currentTime.value = time
}

// Handle scene deletion from timeline
const handleTimelineSceneDelete = (sceneId: string) => {
  const index = scenes.value.findIndex(s => s.id === sceneId)
  if (index !== -1) {
    deleteScene(index)
  }
}

// Text layer CRUD
function addTextLayer() {
  // Default to first 3 seconds, or audio duration / num scenes if available
  const defaultEnd = generatedAudio.value?.duration
    ? Math.min(3, generatedAudio.value.duration)
    : 3
  textLayers.value.push({
    id: crypto.randomUUID(),
    text: 'Your text here',
    startTime: 0,
    endTime: defaultEnd,
    x: 50,
    y: 80,
    fontSize: 48,
    fontColor: '#ffffff',
    fontWeight: 'bold',
    fontStyle: 'normal',
    fontFamily: 'sans-serif',
    textAlign: 'center',
    backgroundColor: '#000000',
    backgroundOpacity: 0,
    boxPaddingX: 12,
    boxPaddingY: 4,
    boxBorderRadius: 4,
    strokeColor: '#000000',
    strokeWidth: 0,
    opacity: 1,
    letterSpacing: 0,
    animation: 'fade-in',
  })
}

function removeTextLayer(id: string) {
  textLayers.value = textLayers.value.filter(l => l.id !== id)
}

function handleTimelineTextLayerUpdate(id: string, updates: { startTime?: number; endTime?: number }) {
  const tl = textLayers.value.find(l => l.id === id)
  if (!tl) return
  if (updates.startTime !== undefined) tl.startTime = updates.startTime
  if (updates.endTime !== undefined) tl.endTime = updates.endTime
}

let _dragState: { si: number; ti: number; startX: number; startY: number; startTlX: number; startTlY: number } | null = null

function startTextLayerDrag(e: MouseEvent, ti: number) {
  e.preventDefault()
  const tl = textLayers.value[ti]
  selectedTextLayerId.value = tl.id
  _dragState = { si: 0, ti, startX: e.clientX, startY: e.clientY, startTlX: tl.x, startTlY: tl.y }
  function onMove(e: MouseEvent) {
    if (!_dragState) return
    const dx = (e.clientX - _dragState.startX) / previewScale.value / previewCompW.value * 100
    const dy = (e.clientY - _dragState.startY) / previewScale.value / previewCompH.value * 100
    const layer = textLayers.value[_dragState.ti]
    layer.x = Math.max(0, Math.min(100, _dragState.startTlX + dx))
    layer.y = Math.max(0, Math.min(100, _dragState.startTlY + dy))
  }
  function onUp() {
    _dragState = null
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

watch(previewContainerRef, (el) => {
  if (!el) return
  const ro = new ResizeObserver(() => {
    previewContainerW.value = el.clientWidth
    previewContainerH.value = el.clientHeight
  })
  ro.observe(el)
  previewContainerW.value = el.clientWidth
  previewContainerH.value = el.clientHeight
})

// Build Remotion TSX code from current scenes
function buildRemotionCode(): string {
  const fps = 30
  const [w, h] = imageAspectRatio.value === '9:16' ? [1080, 1920] : [1920, 1080]

  // Compute transition durations first so we can clamp scene durations
  const transitionFrames = scenes.value.map(s =>
    Math.round((s.transition_duration ?? 1) * fps)
  )

  // Each sequence must be >= both its preceding and following transition durations
  const sceneDurations = scenes.value.map((s, i) => {
    let d = 90 // default 3s
    if (s.start_time != null && s.end_time != null)
      d = Math.max(1, Math.round((s.end_time - s.start_time) * fps))
    const nextTrans = i < scenes.value.length - 1 ? transitionFrames[i] : 0
    const prevTrans = i > 0 ? transitionFrames[i - 1] : 0
    return Math.max(d, nextTrans, prevTrans)
  })

  const totalFrames = sceneDurations.reduce((a, b) => a + b, 0)
    + transitionFrames.slice(0, -1).reduce((a: number, b: number) => a + b, 0)

  const presentationFor = (type?: string) => {
    if (type === 'slide') return 'slide()'
    if (type === 'wipe') return 'wipe()'
    if (type === 'flip') return 'flip()'
    if (type === 'clock-wipe' || type === 'clockWipe') return `clockWipe({width:${w},height:${h}})`
    if (type === 'iris') return `iris({width:${w},height:${h}})`
    if (type === 'none' || type === 'cut') return 'none()'
    return 'fade()'
  }

  const sceneJSX = scenes.value.map((scene, i) => {
    const mediaUrl = scene.animatedVideo?.url || scene.generatedImage?.url || ''
    // Use JSON.stringify to safely embed URLs (handles all special chars)
    const mediaEl = scene.animatedVideo?.url
      ? `<Video src={${JSON.stringify(scene.animatedVideo.url)}} style={{width:'100%',height:'100%',objectFit:'cover'}} muted />`
      : mediaUrl
        ? `<Img src={${JSON.stringify(mediaUrl)}} style={{width:'100%',height:'100%',objectFit:'cover'}} />`
        : `<div style={{width:'100%',height:'100%',background:'#222'}} />`

    const seq = `
    <TransitionSeries.Sequence durationInFrames={${sceneDurations[i]}}>
      <AbsoluteFill>
        ${mediaEl}
      </AbsoluteFill>
    </TransitionSeries.Sequence>`

    const transition = i < scenes.value.length - 1 ? `
    <TransitionSeries.Transition
      timing={linearTiming({durationInFrames:${transitionFrames[i]}})}
      presentation={${presentationFor(scene.transition_type)}}
    />` : ''

    return seq + transition
  }).join('\n')

  const globalTextLayersJSX = textLayers.value.map(tl => {
    const startFrame = Math.round(tl.startTime * fps)
    const durationFrames = Math.max(1, Math.round((tl.endTime - tl.startTime) * fps))

    // Animation extras — applied to the inner text div
    let animExtras = ''
    if (tl.animation === 'fade-in')
      animExtras = `,opacity:interpolate(frame,[0,20],[0,1],{extrapolateRight:'clamp'})`
    else if (tl.animation === 'slide-up')
      animExtras = `,transform:'translateY('+interpolate(frame,[0,20],[30,0],{extrapolateRight:'clamp'})+'px) translate(-50%,-50%)'`
    else if (tl.animation === 'slide-down')
      animExtras = `,transform:'translateY('+interpolate(frame,[0,20],[-30,0],{extrapolateRight:'clamp'})+'px) translate(-50%,-50%)'`

    // Background color with opacity
    const bgOpacity = tl.backgroundOpacity ?? 0
    const bgRgba = hexToRgba(tl.backgroundColor, bgOpacity)
    const padX = tl.boxPaddingX ?? 12
    const padY = tl.boxPaddingY ?? 4
    const radius = tl.boxBorderRadius ?? 4
    const bgStyle = bgRgba !== 'transparent'
      ? `,background:'${bgRgba}',padding:'${padY}px ${padX}px',borderRadius:${radius}`
      : ''

    // Stroke / text border
    const strokeStyle = (tl.strokeWidth && tl.strokeWidth > 0 && tl.strokeColor)
      ? `,WebkitTextStroke:'${tl.strokeWidth}px ${tl.strokeColor}'`
      : ''

    // Optional extras
    const fontStyleProp = tl.fontStyle === 'italic' ? `,fontStyle:'italic'` : ''
    const textAlignProp = tl.textAlign ? `,textAlign:'${tl.textAlign}'` : `,textAlign:'center'`
    const letterSpacingProp = tl.letterSpacing ? `,letterSpacing:${tl.letterSpacing}` : ''
    const outerOpacity = tl.opacity != null && tl.opacity < 1 ? tl.opacity : 1

    const safeText = JSON.stringify(tl.text)
    return `<Sequence from={${startFrame}} durationInFrames={${durationFrames}} style={{pointerEvents:'none',zIndex:10,opacity:${outerOpacity}}}>
  {(() => { const frame = useCurrentFrame(); return (
    <div style={{position:'absolute',left:'${tl.x}%',top:'${tl.y}%',transform:'translate(-50%,-50%)',
      fontSize:${tl.fontSize},color:${JSON.stringify(tl.fontColor)},
      fontWeight:'${tl.fontWeight}'${fontStyleProp}${textAlignProp},fontFamily:${JSON.stringify(tl.fontFamily)}${letterSpacingProp}${strokeStyle}${bgStyle}${animExtras}}}>
      {${safeText}}
    </div>
  ); })()}
</Sequence>`
  }).join('\n')

  // Collect unique Google Fonts used by text layers and inject them in the generated component
  const usedGoogleFonts = [...new Set(
    textLayers.value
      .map(tl => {
        const base = tl.fontFamily.split(',')[0].trim().replace(/['"]/g, '')
        return GOOGLE_FONTS.has(base) ? base : null
      })
      .filter(Boolean) as string[]
  )]
  const fontInjectCode = usedGoogleFonts.length > 0 ? `
  useEffect(() => {
    ${usedGoogleFonts.map(f => `if (!document.querySelector('link[data-gf="${f}"]')) { const l=document.createElement('link'); l.rel='stylesheet'; l.href='https://fonts.googleapis.com/css2?family=${encodeURIComponent(f)}:wght@400;700&display=swap'; l.setAttribute('data-gf','${f}'); document.head.appendChild(l); }`).join('\n    ')}
  }, []);` : ''

  return `
const metadata = { width: ${w}, height: ${h}, fps: 30, durationInFrames: ${totalFrames} };
const MyVideo = () => {
${fontInjectCode}
  return (
  <AbsoluteFill style={{background:'#000'}}>
    <TransitionSeries>
      ${sceneJSX}
    </TransitionSeries>
    ${globalTextLayersJSX}
  </AbsoluteFill>
  );
};
const GeneratedVideo = MyVideo;
`
}

const remotionPreviewCode = computed(() => {
  if (!showingPreview.value || scenes.value.length === 0) return ''
  return buildRemotionCode()
})

const slugifySpeakerLabel = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'speaker'

const inferSceneType = (block: string, dialogueTurns: Scene['dialogue_turns']) => {
  const normalized = block.toLowerCase()
  if (normalized.includes('[broll]') || normalized.includes('(b-roll)')) return 'broll' as const
  if ((dialogueTurns?.length || 0) > 1) return 'dialogue' as const
  if ((dialogueTurns?.length || 0) === 1) return 'monologue' as const
  return 'broll' as const
}

const buildTalkingAnimationPrompt = (scene: Scene) => {
  const turns = scene.dialogue_turns || []
  if (turns.length === 0) {
    return `Subtle cinematic motion for ${scene.description}. Keep framing stable for ${Math.max(scene.target_duration || 3, 2).toFixed(1)} seconds.`
  }

  const timeline = turns.map((turn, index) => {
    const start = typeof turn.start_time === 'number' ? turn.start_time : 0
    const end = typeof turn.end_time === 'number'
      ? turn.end_time
      : start + (turn.duration || Math.max((turn.text || '').split(/\s+/).filter(Boolean).length * 0.32, 1.2))
    const speaker = turn.speaker_label || turn.speaker_id || `speaker ${index + 1}`
    return `${start.toFixed(1)}s-${end.toFixed(1)}s: ${speaker} speaks while the other characters stay idle and listening`
  }).join('; ')

  return `Locked ${scene.layout_type === 'two_shot' ? 'two-shot' : 'medium talking shot'}, stable character identity, realistic talking performance without lip sync. ${timeline}.`
}

const cleanTalkingPromptText = (value?: string) =>
  (value || '')
    .replace(/\[broll\]|\(b-roll\)/gi, '')
    .replace(/\s+/g, ' ')
    .trim()

const normalizeTalkingPromptText = (value?: string) =>
  cleanTalkingPromptText(value).toLowerCase()

const stripStageDirections = (value?: string) =>
  (value || '')
    .replace(/\[[^\]]+\]/g, ' ')
    .replace(/\([^)]*\)/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

const extractStageDirections = (value?: string) => {
  const matches = (value || '').match(/\[[^\]]+\]|\([^)]*\)/g) || []
  return matches
    .map(match => match.slice(1, -1).trim())
    .filter(Boolean)
}

const hasDialogueFormatting = (value?: string) =>
  (value || '')
    .split('\n')
    .some(line => /^([^:]{1,80}):\s*(.+)$/.test(line.trim()))

const inferSettingDescription = (sceneScript?: string, description?: string) => {
  const scriptLines = (sceneScript || '')
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
  const narrativeLines = scriptLines.filter(line => !/^([^:]{1,80}):\s*(.+)$/.test(line))
  const narrativeText = cleanTalkingPromptText(narrativeLines.join(' '))
  if (narrativeText) return narrativeText

  const stageDirectionText = cleanTalkingPromptText(extractStageDirections(sceneScript).join(', '))
  if (stageDirectionText) return `a setting that supports ${stageDirectionText}`

  const fallback = cleanTalkingPromptText(description)
  if (fallback && !hasDialogueFormatting(description)) return fallback

  return 'a believable location that matches the scene context'
}

const inferSpeakerActionDescription = (turns: NonNullable<Scene['dialogue_turns']>) => {
  if (turns.length === 0) {
    return 'natural conversational posture and subtle body language'
  }

  const firstTurn = turns[0]
  const firstSpeaker = firstTurn.speaker_label || firstTurn.speaker_id || 'the speaker'
  const stageDirections = turns.flatMap(turn => extractStageDirections(turn.text)).slice(0, 4)
  const hasQuestion = turns.some(turn => (turn.text || '').includes('?'))
  const hasExclamation = turns.some(turn => (turn.text || '').includes('!'))

  const directionText = stageDirections.length > 0
    ? `Use gesture and expression cues from the script such as ${stageDirections.join(', ')}.`
    : `Show ${firstSpeaker} mid-conversation with expressive hand gestures, engaged posture, and facial expression that matches the line delivery.`

  const listenerText = turns.length > 1
    ? 'Other visible characters should react naturally, listen attentively, and hold believable idle poses.'
    : 'Keep the performance grounded and realistic rather than theatrical.'

  const energyText = hasExclamation
    ? 'The moment should feel energetic and emphatic.'
    : hasQuestion
      ? 'The moment should feel responsive and conversational.'
      : 'The moment should feel natural and grounded.'

  return `${directionText} ${listenerText} ${energyText}`.trim()
}

const hashTalkingSceneSignature = (value?: string) =>
  (value || '').split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)

const getCharacterNameFromId = (characterId?: string) => {
  if (!characterId) return ''
  return charactersStore.characters.find(character => character.id === characterId)?.name || humanizeSpeakerId(characterId)
}

const collectOnScreenCharacterNames = (scene: Pick<Scene, 'dialogue_turns' | 'character_ids'>) => {
  const turnNames = (scene.dialogue_turns || [])
    .map(turn => resolveSpeakerDisplayName(turn.speaker_id, turn.speaker_label))
    .filter(Boolean)
  const assignedNames = (scene.character_ids || [])
    .map(characterId => getCharacterNameFromId(characterId))
    .filter(Boolean)

  return Array.from(new Set([...turnNames, ...assignedNames]))
}

const inferConversationMood = (turns: NonNullable<Scene['dialogue_turns']>) => {
  const combinedText = turns.map(turn => turn.text || '').join(' ')
  const lowerCombinedText = combinedText.toLowerCase()

  if (combinedText.includes('!') || /\b(run|hurry|now|stop|wait)\b/.test(lowerCombinedText)) {
    return 'urgent conversational energy'
  }
  if (combinedText.includes('?') || /\bwhy|how|what|when|where\b/.test(lowerCombinedText)) {
    return 'curious back-and-forth energy'
  }
  if (/\bremember|feel|think|wish|hope|sorry\b/.test(lowerCombinedText)) {
    return 'reflective emotional tone'
  }
  return 'natural conversational tone'
}

const buildTalkingShotDescription = (
  scene: Pick<Scene, 'scene_script' | 'layout_type' | 'dialogue_turns' | 'character_ids'>,
  onScreenNames: string[],
) => {
  const shotSeed = hashTalkingSceneSignature(scene.scene_script || onScreenNames.join(' '))
  const mood = inferConversationMood(scene.dialogue_turns || [])

  if (onScreenNames.length >= 3 || scene.layout_type === 'group') {
    const groupShots = [
      `cinematic group shot with layered blocking and clear foreground/background depth, tuned for ${mood}`,
      `medium-wide ensemble frame with multiple characters visible at once, tuned for ${mood}`,
      `conversational wide shot that keeps the full group in frame with distinct spacing, tuned for ${mood}`,
    ]
    return groupShots[shotSeed % groupShots.length]
  }

  if (onScreenNames.length === 2 || scene.layout_type === 'two_shot') {
    const twoShots = [
      `balanced two-shot with both characters visible in the same frame, tuned for ${mood}`,
      `cinematic over-the-shoulder conversation setup that still keeps both characters readable, tuned for ${mood}`,
      `medium-wide dialogue shot with one active speaker and one attentive listener sharing the frame, tuned for ${mood}`,
      `profile-angled two-shot with strong eye-lines and shared screen presence, tuned for ${mood}`,
    ]
    return twoShots[shotSeed % twoShots.length]
  }

  const soloShots = [
    `cinematic medium shot tuned for ${mood}`,
    `subtle close-medium portrait shot tuned for ${mood}`,
    `medium-wide single-character talking shot with environmental context tuned for ${mood}`,
  ]
  return soloShots[shotSeed % soloShots.length]
}

const buildTalkingImagePrompt = (scene: Pick<Scene, 'scene_type' | 'scene_script' | 'description' | 'layout_type' | 'dialogue_turns' | 'character_ids'>) => {
  const turns = scene.dialogue_turns || []
  const onScreenNames = collectOnScreenCharacterNames(scene)
  const primarySpeaker = turns[0]
    ? resolveSpeakerDisplayName(turns[0].speaker_id, turns[0].speaker_label)
    : onScreenNames[0]
  const settingDescription = inferSettingDescription(scene.scene_script, scene.description)
  const actionDescription = inferSpeakerActionDescription(turns)
  const shotDescription = buildTalkingShotDescription(scene, onScreenNames)
  const castDescription = onScreenNames.length > 0
    ? `Characters on screen: ${onScreenNames.join(', ')}.`
    : ''
  const listenerDescription = onScreenNames.length > 1
    ? 'Keep multiple characters visible in the same scene with natural spacing, clear eye-lines, and believable shared staging.'
    : ''

  if (scene.scene_type === 'broll' || turns.length === 0) {
    return `Cinematic b-roll frame set in ${settingDescription}. Show clear subject focus, specific environmental detail, believable background elements, and realistic lighting. Use composition and production design that support the story context without rendering on-screen dialogue text.`
  }

  if (onScreenNames.length <= 1) {
    const speaker = primarySpeaker || 'the speaker'
    return `${shotDescription} of ${speaker} in ${settingDescription}. ${castDescription} Show ${speaker} speaking on camera with realistic gesture, expressive face, natural posture, and wardrobe appropriate to the setting. Background should clearly establish the location and mood from the script. ${actionDescription} Stable composition, high detail, realistic lighting.`
  }

  return `${shotDescription} in ${settingDescription}. ${castDescription} ${listenerDescription} One character should read as the active speaker while the others remain present in frame with natural listening reactions, posture, and eye contact. ${actionDescription} Stable composition, high detail, realistic lighting, cinematic production design.`
}

const hasScriptLeakInTalkingPrompt = (prompt?: string, sceneScript?: string, description?: string) => {
  const normalizedPrompt = normalizeTalkingPromptText(prompt)
  if (!normalizedPrompt) return false

  if (normalizedPrompt.includes('the moment should visually reflect the context of the conversation:')) {
    return true
  }

  if (hasDialogueFormatting(prompt)) {
    return true
  }

  const normalizedScript = normalizeTalkingPromptText(sceneScript)
  const normalizedDescription = normalizeTalkingPromptText(description)
  const scriptSample = normalizedScript.slice(0, 80)
  const descriptionSample = normalizedDescription.slice(0, 80)

  return (!!scriptSample && normalizedPrompt.includes(scriptSample))
    || (!!descriptionSample && normalizedPrompt.includes(descriptionSample) && hasDialogueFormatting(description))
}

const shouldAutofillTalkingImagePrompt = (prompt?: string, sceneScript?: string, description?: string) => {
  const normalizedPrompt = normalizeTalkingPromptText(prompt)
  if (!normalizedPrompt) return true

  const normalizedScript = normalizeTalkingPromptText(sceneScript)
  const normalizedDescription = normalizeTalkingPromptText(description)
  return normalizedPrompt === normalizedScript
    || normalizedPrompt === normalizedDescription
    || hasScriptLeakInTalkingPrompt(prompt, sceneScript, description)
}

const recalculateTalkingSceneTimeline = () => {
  let elapsed = 0
  scenes.value = scenes.value.map((scene) => {
    const duration = getSceneAudioDuration(scene)
      || scene.target_duration
      || (scene.end_time != null && scene.start_time != null ? scene.end_time - scene.start_time : 3)
    const updated: Scene = {
      ...scene,
      start_time: elapsed,
      end_time: elapsed + duration,
      target_duration: duration,
    }
    updated.animationPrompt = buildTalkingAnimationPrompt(updated)
    elapsed += duration
    return updated
  })
}

const planTalkingScenes = async () => {
  if (!script.value.trim()) {
    toast.error('Please enter a script first')
    return
  }

  isGeneratingScenes.value = true
  sceneGenerationProgress.value = 5
  sceneGenerationError.value = ''

  try {
    let effectiveProjectId = projectId.value
    const draft = await saveDraft({ skipToast: true })
    if (!effectiveProjectId) {
      effectiveProjectId = draft?.project_id || projectId.value
    }

    const blocks = script.value
      .split(/\n\s*\n/)
      .map(block => block.trim())
      .filter(Boolean)

    const sourceBlocks = blocks.length > 0
      ? blocks
      : script.value
          .split(/(?<=[.!?])\s+/)
          .map(block => block.trim())
          .filter(Boolean)

    const plannedScenes = sourceBlocks.map((block, index) => {
      const lines = block
        .split('\n')
        .map(line => line.trim())
        .filter(Boolean)
      const dialogueTurns = lines
        .map((line, turnIndex) => {
          const match = line.match(/^([^:]{1,80}):\s*(.+)$/)
          if (!match) return null
          const speakerLabel = match[1].trim()
          const text = match[2].trim()
          const character = findCharacterByName(speakerLabel)
          const characterId = character?.id
          return {
            id: crypto.randomUUID(),
            speaker_id: characterId || slugifySpeakerLabel(speakerLabel),
            speaker_label: speakerLabel,
            text,
            visual_state: turnIndex === 0 ? 'talking' : 'reaction',
          }
        })
        .filter(Boolean) as NonNullable<Scene['dialogue_turns']>[number][]

      const sceneType = inferSceneType(block, dialogueTurns)
      const mentionedCharacterIds = dialogueTurns
        .map(turn => turn.speaker_id)
        .filter(Boolean) as string[]
      const durationEstimate = dialogueTurns.length > 0
        ? dialogueTurns.reduce((total, turn) => total + Math.max((turn.text || '').split(/\s+/).filter(Boolean).length * 0.32, 1.2), 0)
        : Math.max(block.split(/\s+/).filter(Boolean).length * 0.2, 3)

      const scene: Scene = {
        id: crypto.randomUUID(),
        description: block.replace(/\s+/g, ' ').slice(0, 180),
        prompt: '',
        scene_type: sceneType,
        scene_script: block,
        layout_type: dialogueTurns.length > 1 ? 'two_shot' : 'single',
        target_duration: durationEstimate,
        start_time: 0,
        end_time: 0,
        character_ids: Array.from(new Set(mentionedCharacterIds)),
        dialogue_turns: dialogueTurns,
        character_layout: [],
        generatedImage: undefined,
        animationPrompt: '',
        isGenerating: false,
        generationProgress: 0,
        camera_movement: 'static',
        transition_type: 'fade',
        transition_duration: 0.5,
        greenscreen_effect: '',
        sceneAudio: undefined,
      }

      scene.animationPrompt = buildTalkingAnimationPrompt(scene)
      return scene
    })

    sceneGenerationProgress.value = 35
    const promptResponse = await generateTalkingScenePrompts({
      language_code: 'en',
      scenes: plannedScenes.map((scene, index) => ({
        scene_id: scene.id,
        scene_index: index,
        scene_type: scene.scene_type,
        scene_script: scene.scene_script || scene.description,
        description: scene.description,
        layout_type: scene.layout_type,
        character_names: collectOnScreenCharacterNames(scene),
        dialogue_turns: (scene.dialogue_turns || []).map(turn => ({
          speaker_id: turn.speaker_id,
          speaker_label: turn.speaker_label,
          text: turn.text,
        })),
      })),
    })
    const promptsBySceneId = new Map(promptResponse.scenes.map(scene => [scene.scene_id, scene.prompt]))
    plannedScenes.forEach((scene) => {
      const generatedPrompt = promptsBySceneId.get(scene.id)?.trim()
      if (!generatedPrompt) {
        throw new Error(`Missing generated prompt for scene ${scene.id}`)
      }
      scene.prompt = generatedPrompt
    })

    scenes.value = plannedScenes
    sceneGenerationProgress.value = 75
    recalculateTalkingSceneTimeline()
    syncCharacterVoiceAssignments()
    showStoryboardLayout.value = true
    showingFinalVideo.value = false
    showingGallery.value = false
    selectedSceneForPreview.value = scenes.value.length > 0 ? 0 : null
    syncSelectedSceneDetails()

    if (effectiveProjectId) {
      await saveScenes(effectiveProjectId)
    }

    sceneGenerationProgress.value = 100
    toast.success('Talking scenes planned', {
      description: `${scenes.value.length} scene${scenes.value.length === 1 ? '' : 's'} ready for scene audio generation`
    })
  } catch (error: any) {
    console.error('Failed to plan talking scenes:', error)
    sceneGenerationError.value = error?.message || 'Failed to plan talking scenes'
    toast.error('Failed to plan scenes', {
      description: error?.message || 'Please try again'
    })
  } finally {
    isGeneratingScenes.value = false
  }
}

const generateTalkingSceneAudio = async () => {
  if (!projectId.value) {
    const draft = await saveDraft({ skipToast: true })
    if (draft?.project_id && !projectId.value) {
      projectId.value = draft.project_id
    }
  }

  if (!projectId.value || scenes.value.length === 0) {
    toast.error('Plan scenes first')
    return
  }

  try {
    isGeneratingSceneAudio.value = true
    await saveScenes()

    const response = await generateProjectSceneAudio(projectId.value, {
      tts_provider: ttsProvider.value,
      default_voice_id: selectedVoice.value,
      audio_speed: audioSpeed.value,
      language_code: 'en',
      character_voice_map: Object.fromEntries(
        Object.entries(characterVoiceMap.value)
          .filter(([, assignment]) => !!assignment.voice_id)
          .map(([characterId, assignment]) => [
            characterId,
            {
              voice_id: assignment.voice_id,
              provider: assignment.provider,
              audio_speed: assignment.audio_speed ?? audioSpeed.value,
            },
          ])
      ),
    })

    scenes.value = (response.scenes || []).map((scene: any, index: number) => ({
      id: scene.id || crypto.randomUUID(),
      description: scene.description || `Scene ${index + 1}`,
      prompt: shouldAutofillTalkingImagePrompt(scene.prompt, scene.scene_script, scene.description)
        ? buildTalkingImagePrompt({
            scene_type: scene.scene_type || 'dialogue',
            scene_script: scene.scene_script || scene.description || '',
            description: scene.description || `Scene ${index + 1}`,
            layout_type: scene.layout_type || 'single',
            dialogue_turns: scene.dialogue_turns || [],
            character_ids: scene.character_ids || [],
          })
        : (scene.prompt || scene.description || `Scene ${index + 1}`),
      scene_type: scene.scene_type || 'dialogue',
      scene_script: scene.scene_script || scene.description || '',
      layout_type: scene.layout_type || 'single',
      target_duration: scene.target_duration,
      start_time: scene.start_time,
      end_time: scene.end_time,
      character_ids: scene.character_ids || [],
      dialogue_turns: (scene.dialogue_turns || []).map((turn: any) => ({
        ...turn,
        provider: turn.provider,
        audio_speed: turn.audio_speed,
        voice_override: turn.voice_override,
      })),
      character_layout: scene.character_layout || [],
      generatedImage: scene.generated_image ? {
        id: scene.generated_image.id,
        url: scene.generated_image.url,
        width: scene.generated_image.width || 1024,
        height: scene.generated_image.height || 1024,
        aspectRatio: scene.generated_image.aspect_ratio || scene.generated_image.aspectRatio || '1:1',
      } : undefined,
      animationPrompt: scene.animation_prompt || buildTalkingAnimationPrompt(scene),
      animatedVideo: scene.animated_video ? {
        id: scene.animated_video.id,
        url: scene.animated_video.url,
        duration: scene.animated_video.duration || 0,
        thumbnailUrl: scene.animated_video.url,
      } : undefined,
      isGenerating: false,
      generationProgress: 0,
      camera_movement: scene.camera_movement || 'static',
      transition_type: scene.transition_type || 'fade',
      transition_duration: scene.transition_duration || 0.5,
      greenscreen_effect: scene.greenscreen_effect || '',
      sceneAudio: normalizeSceneAudio(scene),
    }))

    if (response.combined_audio?.url) {
      generatedAudio.value = {
        url: response.combined_audio.url,
        duration: response.combined_audio.duration || 0,
        fileId: response.combined_audio.file_id,
        projectId: projectId.value,
      }
      appliedAudioSpeed.value = audioSpeed.value
      audioPlayerKey.value++
    }

    recalculateTalkingSceneTimeline()
    syncCharacterVoiceAssignments({ autoAssignMissing: false })
    await saveScenes()

    toast.success('Scene audio generated', {
      description: response.message,
    })
  } catch (error: any) {
    console.error('Failed to generate talking scene audio:', error)
    toast.error('Failed to generate scene audio', {
      description: error.message || 'Please try again',
    })
  } finally {
    isGeneratingSceneAudio.value = false
  }
}

const applyAudioSpeedToGeneratedAudio = async () => {
  const effectiveProjectId = projectId.value || generatedAudio.value?.projectId
  if (!effectiveProjectId || !generatedAudio.value) {
    toast.error('Generate audio before adjusting speed')
    return
  }
  if (!hasPendingGeneratedAudioSpeedChange.value) {
    toast.info('Audio speed is already applied')
    return
  }

  try {
    isAdjustingAudioSpeed.value = true
    toast.info('Adjusting generated audio...', {
      description: 'Scene and caption timestamps will be scaled to match',
    })

    const response = await adjustProjectSceneAudioSpeed(effectiveProjectId, {
      audio_speed: audioSpeed.value,
      current_audio_speed: appliedAudioSpeed.value,
      language_code: 'en',
    })

    if (response.combined_audio?.url) {
      generatedAudio.value = {
        url: response.combined_audio.url,
        duration: response.combined_audio.duration || generatedAudio.value.duration,
        fileId: response.combined_audio.file_id,
        projectId: effectiveProjectId,
      }
      audioPlayerKey.value++
    }

    if (Array.isArray(response.scenes) && response.scenes.length > 0) {
      scenes.value = response.scenes.map(mapApiSceneToUiScene)
      syncCharacterVoiceAssignments({ autoAssignMissing: false })
      syncSelectedSceneDetails()
    }

    appliedAudioSpeed.value = response.audio_speed || audioSpeed.value
    await saveDraft({ skipToast: true })

    toast.success('Audio speed applied', {
      description: `Adjusted to ${appliedAudioSpeed.value.toFixed(2)}x and scaled timestamps`,
    })
  } catch (error: any) {
    console.error('Failed to adjust generated audio speed:', error)
    toast.error('Failed to adjust audio speed', {
      description: error?.message || 'Please try again',
    })
  } finally {
    isAdjustingAudioSpeed.value = false
  }
}

// Combined Audio + Scenes generation (matches VideoGenerator.vue logic)
const handleGenerateScenes = async () => {
  // If scenes already exist, show confirmation dialog
  if (scenes.value.length > 0) {
    const confirmed = confirm(
      `You have ${scenes.value.length} existing scene${scenes.value.length > 1 ? 's' : ''}. ` +
      'Re-generating will replace all current scenes. Do you want to continue?'
    )
    if (!confirmed) {
      return // User cancelled
    }
  }

  // Proceed with generation
  if (projectMode.value === 'talking_scenes') {
    await planTalkingScenes()
    return
  }
  await generateAudioAndScenes()
}

const generateAudioAndScenes = async () => {
  try {
    logger.log('🎬 Starting Audio + Scenes generation...')

    // Switch to storyboard layout immediately to show loading state
    showStoryboardLayout.value = true
    showingFinalVideo.value = false
    showingGallery.value = false

    // Clear existing scenes to show loading screen
    scenes.value = []
    selectedSceneForPreview.value = null

    // Set loading state immediately at the start
    isGeneratingAudio.value = true
    audioGenerationProgress.value = 0

    // Track if we created a new project during this flow
    const hadProjectIdBefore = !!projectId.value

    // Step 0: Create project and update URL first (if no project exists yet)
    if (!projectId.value) {
      logger.log('📝 Step 0: Creating project and updating URL...')
      const result = await saveDraft({ skipRouteUpdate: true, skipToast: true }) // Create project without route update
      const newProjectId = result.project_id
      logger.log('✅ Project created with ID:', newProjectId)

      if (!newProjectId) {
        console.error('❌ Failed to create project')
        toast.error('Failed to create project')
        isGeneratingAudio.value = false
        return
      }

      // Set projectId directly (no component remount)
      projectId.value = newProjectId

      // Update URL in browser without causing component remount
      logger.log('📍 Updating URL to show project ID...')
      window.history.replaceState({}, '', `/app/simple-creator/${newProjectId}`)
      logger.log('✅ URL updated to:', window.location.pathname)
    }

    // First, generate audio (skip route update to prevent component remount)
    logger.log('🔊 Step 1: Generating audio...')
    await generateAudio(true) // Pass true to skip router.replace

    // Check if audio generation was successful (matches VideoGenerator.vue pattern)
    const effectiveProjectId = projectId.value || generatedAudio.value?.projectId
    logger.log('🔍 Audio generation complete. Project ID:', effectiveProjectId)
    logger.log('🔍 generatedAudio:', generatedAudio.value)

    if (!generatedAudio.value || !effectiveProjectId) {
      console.error('❌ Audio generation did not produce a project ID')
      toast.error('Failed to generate audio', {
        description: 'No project ID found after audio generation'
      })
      isGeneratingAudio.value = false
      isGeneratingScenes.value = false
      return
    }

    // Audio is now ready and should be visible in the UI
    logger.log('✅ Audio player should now be visible with:', generatedAudio.value.url)

    // Then, generate scenes from transcript (backend handles transcription timing)
    logger.log('🎬 Step 2: Generating scenes...')
    logger.log('🔍 Current scenes.length before generateScenes:', scenes.value.length)
    await generateScenes()
    logger.log('🔍 Current scenes.length after generateScenes:', scenes.value.length)
    logger.log('✅ Audio + Scenes generation complete!')

    // Save the updated project state (audio and scenes)
    await saveDraft()
    logger.log('💾 Project saved with audio and scenes')
  } catch (err: any) {
    console.error('❌ Error in combined audio and scene generation:', err)
    toast.error('Generation failed', {
      description: err.message || 'Please try again'
    })
    // Reset loading states on error
    isGeneratingAudio.value = false
    isGeneratingScenes.value = false
  }
}

// Audio generation
const generateAudio = async (skipRouterReplace = false) => {
  if (!script.value.trim()) {
    toast.error('Please enter a script first')
    return
  }

  try {
    isGeneratingAudio.value = true
    audioGenerationProgress.value = 0
    toast.info('Generating voiceover...', { description: 'This may take a moment' })

    const requestData = {
      text: script.value,
      voice_id: selectedVoice.value,
      project_title: projectTitle.value,
      tts_provider: ttsProvider.value,
      language_code: 'en',
      audio_speed: audioSpeed.value,
      user_input_text: script.value  // Pass the user's input text
    }

    let response

    if (projectId.value) {
      // Regenerate audio for existing project (background job)
      const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:8000')
      const fetchResponse = await fetch(`${API_BASE_URL}/api/video/projects/${projectId.value}/regenerate-audio`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify(requestData)
      })

      if (!fetchResponse.ok) {
        throw new Error(`HTTP ${fetchResponse.status}: ${fetchResponse.statusText}`)
      }

      const jobStatus = await fetchResponse.json()
      logger.log('Audio regeneration job started:', jobStatus)

      // Poll for completion
      const maxAttempts = 240 // 20 minutes max (5 second intervals)
      let attempts = 0
      let completed = false
      let audioData = null

      // Set initial progress
      audioGenerationProgress.value = 5

      while (attempts < maxAttempts && !completed) {
        await new Promise(resolve => setTimeout(resolve, 5000)) // Wait 5 seconds
        attempts++

        // Update progress based on elapsed time (cap at 90% until complete)
        const progressPercent = Math.min(90, 5 + (attempts / maxAttempts) * 85)
        audioGenerationProgress.value = Math.round(progressPercent)

        logger.log(`Polling for audio completion (${attempts * 5}s elapsed)...`)

        // Fetch updated project to check status
        const projectResponse = await fetch(`${API_BASE_URL}/api/projects/${projectId.value}`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
          }
        })

        if (projectResponse.ok) {
          const responseData = await projectResponse.json()
          const projectData = responseData.project || responseData

          if (projectData.status === 'audio_ready' && projectData.audio_file_id) {
            // Fetch the audio file details
            const audioResponse = await fetch(`${API_BASE_URL}/api/audio/${projectData.audio_file_id}`, {
              headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
              }
            })

            if (audioResponse.ok) {
              const audioFileData = await audioResponse.json()
              audioData = {
                audio_file: {
                  id: audioFileData.id,
                  url: audioFileData.file_url || audioFileData.url,
                  duration: audioFileData.duration
                },
                project_id: projectId.value
              }
              completed = true
            }
          } else if (projectData.status === 'error') {
            throw new Error('Audio generation failed on server')
          }
        }
      }

      if (!completed) {
        throw new Error('Audio generation timed out after 20 minutes')
      }

      response = { data: audioData }

      // Set progress to 100% when complete
      audioGenerationProgress.value = 100
    } else {
      // Create new audio for timeline (use same service as VideoGenerator.vue)
      audioGenerationProgress.value = 5

      const { videoGenerationService } = await import('@/api/videoGenerationService')

      const result = await videoGenerationService.generateAudioForTimeline(requestData)

      // Convert to the expected response format
      response = { data: result }

      // Set progress to 100% when complete
      audioGenerationProgress.value = 100
    }

    console.log('🎵 Audio API Response:', response.data)
    if (response.data) {
      console.log('📋 Response keys:', Object.keys(response.data))
      console.log('🔍 Full response structure:', JSON.stringify(response.data, null, 2))
    }

    // Handle both response formats (polling vs direct response)
    const resultAny = response.data as any
    const audioUrl = response.data?.audio_file?.url || resultAny?.audio_url || resultAny?.file_url || resultAny?.url

    let audioDuration = response.data?.audio_file?.duration || resultAny?.duration || 0

    // If duration is missing or 0, try to fetch it from the audio file
    if (!audioDuration && audioUrl) {
      console.warn('⚠️ Duration missing from response, attempting to fetch audio metadata...')
      try {
        const audio = new Audio(audioUrl)
        audioDuration = await new Promise<number>((resolve) => {
          audio.addEventListener('loadedmetadata', () => {
            resolve(audio.duration)
          })
          audio.addEventListener('error', () => {
            console.warn('Failed to load audio metadata, using default duration')
            resolve(60) // Default to 60 seconds if we can't get the duration
          })
          // Timeout after 10 seconds
          setTimeout(() => {
            console.warn('Audio metadata timeout, using default duration')
            resolve(60)
          }, 10000)
        })
        console.log('✅ Fetched audio duration:', audioDuration)
      } catch (error) {
        console.error('Failed to fetch audio duration:', error)
        audioDuration = 60 // Default fallback
      }
    }

    const audioData = {
      url: audioUrl,
      duration: audioDuration,
      fileId: response.data?.audio_file?.id || resultAny?.audio_id || resultAny?.id,
      projectId: response.data?.project_id || resultAny?.project_id || projectId.value || ''
    }

    if (!audioData.fileId || !audioData.url) {
      console.error('❌ Invalid audio data - missing id or url:', audioData)
      throw new Error('Invalid audio data received - missing required fields')
    }

    if (!audioData.duration || audioData.duration <= 0) {
      console.error('❌ Invalid audio data - missing or invalid duration:', audioData)
      throw new Error('Invalid audio data received - missing duration')
    }

    generatedAudio.value = audioData
    appliedAudioSpeed.value = audioSpeed.value
    console.log('✅ Set generatedAudio.value:', generatedAudio.value)
    console.log('  - URL:', audioData.url)
    console.log('  - Duration:', audioData.duration)
    console.log('  - File ID:', audioData.fileId)

    // Force audio player refresh
    audioPlayerKey.value++
    console.log('🔄 Audio player key incremented to:', audioPlayerKey.value)

    // Store the project ID if we just created it
    const newProjectId = response.data?.project_id || resultAny?.project_id
    if (newProjectId && !projectId.value && !skipRouterReplace) {
      console.log('📍 Updating route to project ID:', newProjectId)

      // Cache the audio data in sessionStorage so it persists through component remount
      sessionStorage.setItem('simple-creator-temp-audio', JSON.stringify({
        ...audioData,
        appliedAudioSpeed: appliedAudioSpeed.value,
      }))

      await router.replace({
        name: 'simple-creator',
        params: { id: newProjectId }
      })
      console.log('✅ Route updated')
    } else if (newProjectId && !projectId.value && skipRouterReplace) {
      console.log('⏭️ Skipping route update (will update after combined generation)')
    }

    toast.success('Voiceover generated!', {
      description: `Duration: ${formatDuration(audioData.duration || 0)}`
    })

    logger.log('Audio generated:', generatedAudio.value)
  } catch (error: any) {
    console.error('Audio generation failed:', error)

    // Reset progress on error
    audioGenerationProgress.value = 0

    toast.error('Failed to generate audio', {
      description: error.response?.data?.detail || error.message || 'Please try again'
    })
  } finally {
    isGeneratingAudio.value = false
  }
}

// Audio upload methods
const handleAudioFileSelect = (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    uploadAudioFile(file)
  }
}

const handleAudioFileDrop = (event: DragEvent) => {
  isDraggingAudio.value = false
  const files = event.dataTransfer?.files
  const file = files?.[0]
  if (file && file.type.startsWith('audio/')) {
    uploadAudioFile(file)
  }
}

// Media upload methods (images/videos)
const handleMediaFileSelect = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const files = input.files

  if (!files || files.length === 0) {
    return
  }

  // Convert FileList to Array
  const fileArray = Array.from(files)

  // Validate files using imageService
  const validation = imageService.validateImages(fileArray)
  if (!validation.valid) {
    toast.error(validation.errors[0])
    // Reset input
    input.value = ''
    return
  }

  try {
    toast.info(`Uploading ${fileArray.length} file(s) to gallery...`)

    // Upload files to gallery only
    const uploadedImages = await imageService.uploadImages(fileArray)

    toast.success(`${uploadedImages.length} file(s) uploaded to gallery`, {
      description: 'You can now add them to your storyboard from the gallery'
    })

    // Reset input
    input.value = ''

    // Refresh gallery to show uploaded images
    await imageGenerationStore.fetchGallery(true)
  } catch (error: any) {
    console.error('Failed to upload files:', error)
    toast.error(error.message || 'Failed to upload files')
    // Reset input
    input.value = ''
  }
}

const uploadAudioFile = async (file: File) => {
  isUploadingAudio.value = true
  audioUploadProgress.value = 0
  audioUploadError.value = ''

  logger.log(`🎤 Uploading audio file`)

  // Simulate upload progress
  const progressInterval = setInterval(() => {
    if (audioUploadProgress.value < 80) {
      audioUploadProgress.value += 5
    }
  }, 200)

  try {
    const result = await audioService.uploadAudio(file, projectId.value || '', 'en')

    clearInterval(progressInterval)
    audioUploadProgress.value = 100

    // Create audio element to get duration
    const audio = new Audio()
    audio.src = result.signed_url

    // Wait for metadata to load to get duration
    const duration = await new Promise<number>((resolve) => {
      audio.addEventListener('loadedmetadata', () => {
        resolve(audio.duration || 0)
      })
      audio.addEventListener('error', () => {
        console.warn('Failed to load audio metadata, using default duration')
        resolve(60) // Default fallback duration
      })
      // Timeout fallback
      setTimeout(() => resolve(60), 180000)
    })

    // Set up the audio data to match the generate flow
    generatedAudio.value = {
      url: result.signed_url,
      duration: duration,
      fileId: result.id,
      projectId: result.project_id || projectId.value || undefined
    }
    appliedAudioSpeed.value = 1.0

    // Increment audio player key to force re-render
    audioPlayerKey.value++

    // Store the project ID if we just created it
    const newProjectId = result.project_id
    if (newProjectId && !projectId.value) {
      projectId.value = newProjectId
      window.history.replaceState({}, '', `/app/simple-creator/${newProjectId}`)
      console.log('✅ URL updated to:', window.location.pathname)
    }

    toast.success('Audio uploaded successfully!', {
      description: `Duration: ${formatDuration(duration || 0)}`
    })

    // Auto-start scene generation for Audio-to-Video uploads
    if (
      creationMode.value === 'audioToVideo' &&
      !isGeneratingScenes.value &&
      (projectId.value || generatedAudio.value?.projectId)
    ) {
      if (scenes.value.length > 0) {
        toast.info('Regenerating scenes...', {
          description: 'Existing scenes will be replaced by scenes from the new audio transcript'
        })
      }
      toast.info('Starting scene generation...', {
        description: 'Generating scenes from your transcript'
      })
      await generateScenes()
    }

  } catch (err: any) {
    clearInterval(progressInterval)
    console.error('❌ Audio upload failed:', err)
    audioUploadError.value = err.response?.data?.detail || err.message || 'Failed to upload audio file'
    audioUploadProgress.value = 0
  } finally {
    isUploadingAudio.value = false
  }
}

const removeUploadedAudio = () => {
  generatedAudio.value = null
  appliedAudioSpeed.value = 1.0
  audioPlayerKey.value++
  if (audioFileInput.value) {
    audioFileInput.value.value = ''
  }
  toast.info('Audio removed')
}

const openCaptionEditor = async () => {
  if (!projectId.value) {
    toast.error('Create a project and generate audio first')
    return
  }

  try {
    isLoadingCaptionText.value = true
    const response = await apiClient.get(`/api/video/projects/${projectId.value}/caption-text`, {
      params: { language_code: 'en' }
    })

    captionEditorSourceFile.value = response.data?.source_file || ''
    captionTimestampRows.value = buildCaptionTimestampRows(response.data?.word_timestamps || [])
    isCaptionEditorOpen.value = true
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    toast.error('Failed to load caption text', {
      description: typeof detail === 'string' ? detail : 'Transcription may not be ready yet'
    })
  } finally {
    isLoadingCaptionText.value = false
  }
}

const closeCaptionEditor = () => {
  if (isSavingCaptionText.value) return
  isCaptionEditorOpen.value = false
}

const saveCaptionEdits = async () => {
  if (!projectId.value) return

  const normalizedText = captionTimestampRows.value
    .map(row => row.text.trim())
    .filter(Boolean)
    .join(' ')
  if (!normalizedText) {
    toast.error('Caption text cannot be empty')
    return
  }

  try {
    isSavingCaptionText.value = true
    const response = await apiClient.put(`/api/video/projects/${projectId.value}/caption-text`, {
      caption_text: normalizedText,
      language_code: 'en'
    })
    captionTimestampRows.value = buildCaptionTimestampRows(response.data?.word_timestamps || [])

    toast.success('Caption updated', {
      description: 'New subtitle text will be used on next render'
    })
    isCaptionEditorOpen.value = false
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    toast.error('Failed to save caption text', {
      description: typeof detail === 'string' ? detail : 'Please try again'
    })
  } finally {
    isSavingCaptionText.value = false
  }
}

const formatCaptionTime = (seconds: number) => {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0
  const mins = Math.floor(safe / 60)
  const secs = Math.floor(safe % 60)
  const centis = Math.floor((safe - Math.floor(safe)) * 100)
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(centis).padStart(2, '0')}`
}

const buildCaptionTimestampRows = (wordTimestamps: Array<{ text?: string; start?: number; end?: number }>) => {
  if (!Array.isArray(wordTimestamps) || wordTimestamps.length === 0) return []

  const rows: Array<{ start: number; end: number; text: string }> = []
  let currentWords: string[] = []
  let currentStart: number | null = null
  let currentEnd: number | null = null

  const flush = () => {
    if (!currentWords.length || currentStart === null || currentEnd === null) return
    rows.push({
      start: currentStart,
      end: currentEnd,
      text: currentWords.join(' ')
    })
    currentWords = []
    currentStart = null
    currentEnd = null
  }

  for (const word of wordTimestamps) {
    const text = (word?.text || '').trim()
    if (!text) continue

    const start = typeof word?.start === 'number' ? word.start : 0
    const end = typeof word?.end === 'number' ? word.end : start

    if (currentStart === null) currentStart = start
    currentEnd = end
    currentWords.push(text)

    const endsSentence = /[.!?]$/.test(text)
    if (endsSentence || currentWords.length >= 10) {
      flush()
    }
  }

  flush()
  return rows
}

// Scene generation
const generateScenes = async () => {
  // Use projectId from route, or fallback to generatedAudio's projectId
  const effectiveProjectId = projectId.value || generatedAudio.value?.projectId

  if (!effectiveProjectId) {
    toast.error('Please generate audio first')
    return
  }

  try {
    // Switch to storyboard layout and clear scenes to show loading state
    showStoryboardLayout.value = true
    showingFinalVideo.value = false
    showingGallery.value = false
    scenes.value = []
    selectedSceneForPreview.value = null

    isGeneratingScenes.value = true
    sceneGenerationProgress.value = 0
    sceneGenerationError.value = ''
    toast.info('Generating scenes...', { description: 'Analyzing script and creating scenes' })

    const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:8000')

    // Get custom prompt instructions from selected style template
    const customPromptInstructions = selectedStyleTemplate.value
      ? styleTemplates.find(t => t.id === selectedStyleTemplate.value)?.prompt || null
      : null

    // Map aggregation mode to backend parameters
    let aggFirstHalf = 2
    let aggSecondHalf = 3
    let cutOff = 0.5

    if (sceneAggregationMode.value === 'less') {
      // Less scenes = more aggregation (combine more sentences)
      aggFirstHalf = 3
      aggSecondHalf = 4
      cutOff = 0.5
    } else if (sceneAggregationMode.value === 'more') {
      // More scenes = less aggregation (combine fewer sentences)
      aggFirstHalf = 1
      aggSecondHalf = 2
      cutOff = 0.5
    } else if (sceneAggregationMode.value === 'much less') {
      // Much less scenes = even more aggregation (combine even more sentences)
      aggFirstHalf = 5
      aggSecondHalf = 6
      cutOff = 0.5
    } else if (sceneAggregationMode.value === 'most') {
      // Most scenes = no aggregation (one scene per sentence)
      aggFirstHalf = 1
      aggSecondHalf = 1
      cutOff = 0.5
    }
    // 'regular' mode uses default values (2, 3, 0.5)

    // Retry logic for transcript not ready errors
    let retryCount = 0
    const maxRetries = 12
    let response: Response | null = null
    let taskInitResponse: any = null

    while (retryCount <= maxRetries) {
      try {
        // Start async scene generation task
        response = await fetch(`${API_BASE_URL}/api/scene-generation/generate-from-transcript`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
          },
          body: JSON.stringify({
            project_id: effectiveProjectId,
            agg_first_half: aggFirstHalf,
            agg_second_half: aggSecondHalf,
            cut_off: cutOff,
            language_code: 'en',
            custom_prompt_instructions: customPromptInstructions
          })
        })

        if (!response.ok) {
          const errorData = await response.json()

          // Check if error is due to transcript not ready
          if (errorData.detail && errorData.detail.includes('Transcript file not found') && retryCount < maxRetries) {
            retryCount++
            logger.log(`Transcript not ready, retrying in 10 seconds (attempt ${retryCount}/${maxRetries})...`)
            toast.info('Waiting for transcription...', {
              description: `Retry ${retryCount}/${maxRetries}`
            })
            await new Promise(resolve => setTimeout(resolve, 10000))
            continue
          }

          throw new Error(errorData.detail || 'Failed to generate scenes')
        }

        taskInitResponse = await response.json()
        break // Success, exit retry loop
      } catch (error) {
        if (retryCount >= maxRetries) {
          throw error
        }
      }
    }

    if (!taskInitResponse) {
      throw new Error('Failed to start scene generation after retries')
    }

    const taskId = taskInitResponse.task_id

    logger.log(`✅ Task started with ID: ${taskId}`)
    sceneGenerationProgress.value = 5

    // Poll for task status
    const pollInterval = 2000
    const maxAttempts = 150
    let attempts = 0

    const pollForStatus = async (): Promise<any> => {
      attempts++

      logger.log(`📊 Polling task status (attempt ${attempts}/${maxAttempts})...`)

      const statusResponse = await fetch(`${API_BASE_URL}/api/scene-generation/task-status/${taskId}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        }
      })

      if (!statusResponse.ok) {
        throw new Error(`Failed to get task status: ${statusResponse.statusText}`)
      }

      const status = await statusResponse.json()

      // Update progress bar from backend progress
      sceneGenerationProgress.value = status.progress

      logger.log(`📈 Task status: ${status.status}, progress: ${status.progress}%, message: ${status.message}`)

      if (status.status === 'completed') {
        logger.log('✅ Task completed successfully!')
        return status.result
      }

      if (status.status === 'failed') {
        const errorMsg = status.error || 'Scene generation failed'

        // If it's a transcript file error, provide a helpful message
        if (errorMsg.includes('Failed to download transcript file') || errorMsg.includes('Transcript file not found')) {
          throw new Error('Transcription is still processing. Please wait a moment and try again.')
        }

        throw new Error(errorMsg)
      }

      if (attempts >= maxAttempts) {
        throw new Error('Scene generation timeout')
      }

      // Continue polling
      await new Promise(resolve => setTimeout(resolve, pollInterval))
      return pollForStatus()
    }

    // Start polling
    const result = await pollForStatus()

    logger.log('🔍 Poll result:', result)
    logger.log('🔍 Result.scenes:', result.scenes)
    logger.log('🔍 Result.scenes length:', result.scenes?.length || 0)

    // Complete the progress
    sceneGenerationProgress.value = 100

    // Populate scenes with timing data included
    scenes.value = result.scenes || []
    logger.log('🔍 After first assignment, scenes.value.length:', scenes.value.length)

    // Auto-detect characters from @mentions in scene prompts
    scenes.value = scenes.value.map((scene: any) => {
      const detectedCharacterIds = extractCharacterIdsFromPrompt(scene.prompt)
      if (detectedCharacterIds.length > 0) {
        logger.log(`📌 Scene: "${scene.prompt.substring(0, 50)}..." → ${detectedCharacterIds.length} character(s) detected`)
      }

      // Add custom style keywords to the front of the prompt
      let enhancedPrompt = scene.prompt
      if (selectedImageStyles.value.length > 0) {
        enhancedPrompt = `${selectedImageStyles.value.join(', ')} style, ${scene.prompt}`
        logger.log(`🎨 Enhanced scene prompt with custom keywords: ${enhancedPrompt}`)
      }

      return {
        ...scene,
        id: scene.id || crypto.randomUUID(),
        prompt: enhancedPrompt,
        character_ids: detectedCharacterIds,
        animationPrompt: withSelectedSceneToVideoPrompt(scene.animation_prompt || scene.animationPrompt)  // Map snake_case to camelCase
      }
    })
    logger.log('🔍 After map, scenes.value.length:', scenes.value.length)
    logger.log('🔍 Final scenes.value:', scenes.value)

    // Show success toast notification
    toast.success('Scene Generation Complete', {
      description: `Successfully generated ${scenes.value.length} scene prompts from transcript`,
      duration: 4000
    })

    // Auto-save scenes to database after generation
    try {
      await saveScenes()
      logger.log('✅ Scenes auto-saved to database')
    } catch (saveError) {
      console.error('Failed to auto-save scenes:', saveError)
      // Non-critical error, don't block the UI
    }

    // Auto-select first scene to show preview section
    if (scenes.value.length > 0) {
      selectedSceneForPreview.value = 0
      logger.log('✅ Auto-selected first scene for preview')
    }

    // Switch to storyboard view after successful scene generation
    showStoryboardLayout.value = true
    logger.log('🎬 Switched to storyboard view')
  } catch (error: any) {
    console.error('❌ Scene generation failed:', error)
    const errorMessage = error.message || 'Failed to generate scenes from transcript'
    sceneGenerationError.value = errorMessage
    sceneGenerationProgress.value = 0

    // Show error toast notification
    toast.error('Scene Generation Failed', {
      description: errorMessage,
      duration: 5000
    })
  } finally {
    isGeneratingScenes.value = false
  }
}

// Image style selection methods
const addStyleSuggestion = (suggestion: string) => {
  if (!selectedImageStyles.value.includes(suggestion)) {
    selectedImageStyles.value.push(suggestion)
  }
}

const addCustomKeyword = () => {
  const keyword = newStyleKeyword.value.trim()
  if (keyword && !selectedImageStyles.value.includes(keyword)) {
    selectedImageStyles.value.push(keyword)
    newStyleKeyword.value = ''
  }
}

const withSelectedVisualStylePrompt = (prompt: string): string => {
  if (selectedStyleTemplate.value !== 'vox-animation') return prompt

  const normalizedPrompt = prompt.toLowerCase()
  if (normalizedPrompt.includes('encyclopedic collage style') || normalizedPrompt.includes('historical encyclopedia')) {
    return prompt
  }

  return `${prompt}\n\nVisual style requirement: ${VOX_ANIMATION_PROMPT}`
}

const withSelectedSceneToVideoPrompt = (prompt?: string): string => {
  const basePrompt = (prompt || '').trim()
  if (selectedStyleTemplate.value !== 'vox-animation') return basePrompt

  const normalizedPrompt = basePrompt.toLowerCase()
  if (normalizedPrompt.includes('paper-cutout') || normalizedPrompt.includes('stop-motion collage style')) {
    return basePrompt
  }

  return [basePrompt, VOX_SCENE_TO_VIDEO_PROMPT].filter(Boolean).join('\n\n')
}

// Image generation for all scenes
const generateAllImages = async () => {
  if (scenes.value.length === 0) {
    toast.error('No scenes to generate images for')
    return
  }

  try {
    isGeneratingImages.value = true
    currentImageIndex.value = 0

    const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:8000')

    // Get scenes that need images
    const scenesToGenerate = scenes.value
      .map((scene, index) => ({ scene, index }))
      .filter(({ scene }) => {
        // Skip if already has image
        if (scene.generatedImage && scene.generatedImage.id) return false
        // Skip if prompt is empty
        if (!scene.prompt || !scene.prompt.trim()) {
          logger.warn(`⚠️ Skipping scene with empty prompt`)
          return false
        }
        return true
      })

    if (scenesToGenerate.length === 0) {
      toast.info('All scenes already have images')
      return
    }

    logger.log(`🎨 Generating images for ${scenesToGenerate.length} scenes in batches of 5...`)

    // Process scenes in batches of 5
    const BATCH_SIZE = 5
    for (let batchStart = 0; batchStart < scenesToGenerate.length; batchStart += BATCH_SIZE) {
      const batch = scenesToGenerate.slice(batchStart, batchStart + BATCH_SIZE)
      const batchNumber = Math.floor(batchStart / BATCH_SIZE) + 1
      const totalBatches = Math.ceil(scenesToGenerate.length / BATCH_SIZE)

      logger.log(`📦 Processing batch ${batchNumber}/${totalBatches} (${batch.length} scenes)`)

      // Generate all images in this batch concurrently
      await Promise.all(batch.map(async ({ scene, index: i }) => {
        currentImageIndex.value = i + 1

        // Set loading state for this scene
        generatingSceneIndices.value.add(i)
        scenes.value[i].isGenerating = true
        scenes.value[i].generationProgress = 0

        try {
          logger.log(`Generating image ${i + 1}/${scenes.value.length}:`, scene.prompt)

        // Get character reference image URLs for models that support input_images (e.g., openai/gpt-image-2)
        const referenceImageUrls: string[] = []
        if (scene.character_ids && scene.character_ids.length > 0) {
          for (const characterId of scene.character_ids) {
            try {
              const character = await charactersStore.getCharacter(characterId)
              if (character.reference_images && character.reference_images.length > 0) {
                for (const refImage of character.reference_images) {
                  if (refImage.image_url) {
                    referenceImageUrls.push(refImage.image_url)
                  }
                }
              }
            } catch (error) {
              console.error(`Failed to fetch character ${characterId}:`, error)
            }
          }
          if (referenceImageUrls.length > 0) {
            logger.log(`📷 Scene ${i + 1}: Found ${referenceImageUrls.length} reference image(s) from @ tagged characters`)
          }
        }

        let promptToSend = withSelectedVisualStylePrompt(scene.prompt)

        // Generate image with user's selected settings
        const requestBody: any = {
          prompt: promptToSend,
          model: imageGenerationModel.value,  // Use selected model
          width: imageAspectRatio.value === '9:16' ? 720 : (imageAspectRatio.value === '1:1' ? 1024 : 1280),
          height: imageAspectRatio.value === '9:16' ? 1280 : (imageAspectRatio.value === '1:1' ? 1024 : 720),
          num_outputs: 1,
          aspect_ratio: getModelCompatibleImageAspectRatio(imageGenerationModel.value, imageAspectRatio.value)
        }

        // Add Replicate input parameters for Plus Quality 2 model (openai/gpt-image-2)
        if (imageGenerationModel.value === 'openai/gpt-image-2') {
          const mappedAspectRatio = getModelCompatibleImageAspectRatio(imageGenerationModel.value, imageAspectRatio.value)

          // Replicate input parameters for openai/gpt-image-2
          requestBody.input = {
            prompt: requestBody.prompt,
            quality: 'low',
            background: 'auto',
            moderation: 'auto',
            aspect_ratio: mappedAspectRatio,
            output_format: 'webp',
            input_fidelity: 'low',
            number_of_images: 1,
            output_compression: 90
          }
          // Include reference images (from @ tagged characters) as input_images for openai/gpt-image-2
          if (referenceImageUrls.length > 0) {
            requestBody.input.input_images = referenceImageUrls
            logger.log(`📷 Scene ${i + 1}: Including ${referenceImageUrls.length} reference image(s) in input_images for openai/gpt-image-2`)
          }
          console.log('[Plus Quality 2] UI aspect ratio:', imageAspectRatio.value, '→ API aspect ratio:', mappedAspectRatio)
          console.log('[Plus Quality 2] Full requestBody:', JSON.stringify(requestBody, null, 2))
        }

        // Simulate progress
        scenes.value[i].generationProgress = 20

        const response = await fetch(`${API_BASE_URL}/api/image-generation/generate`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
          },
          body: JSON.stringify(requestBody)
        })

        scenes.value[i].generationProgress = 50

        if (!response.ok) {
          const errorDetail = await response.json()
          logger.error(`❌ Image generation failed for scene ${i + 1}:`, errorDetail)
          logger.error(`Request body:`, requestBody)
          throw new Error(errorDetail?.message || errorDetail?.detail || 'Image generation failed')
        }

        const result = await response.json()
        scenes.value[i].generationProgress = 70

        // Fetch the generated image
        const imageResponse = await fetch(`${API_BASE_URL}/api/image-generation/generations/${result.id}`, {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
          }
        })

        if (!imageResponse.ok) {
          throw new Error('Failed to fetch generated image')
        }

        const imageData = await imageResponse.json()
        scenes.value[i].generationProgress = 90

        // Update scene with generated image (matching VideoGenerator.vue structure)
        if (imageData.signed_url) {
          const imageWidth = imageData.width || (imageAspectRatio.value === '9:16' ? 720 : (imageAspectRatio.value === '1:1' ? 1024 : 1280))
          const imageHeight = imageData.height || (imageAspectRatio.value === '9:16' ? 1280 : (imageAspectRatio.value === '1:1' ? 1024 : 720))

          // Directly update the scene's generatedImage property (matching VideoGenerator.vue)
          scenes.value[i].generatedImage = {
            id: result.id, // Use the generation ID from the initial response
            url: imageData.signed_url,
            width: imageWidth,
            height: imageHeight,
            aspectRatio: imageAspectRatio.value
          }

          logger.log(`✅ Image ${i + 1} generated successfully`)
          logger.log(`📍 Image ID: ${result.id}`)
          logger.log(`🔗 Image URL: ${imageData.signed_url}`)
          logger.log(`📐 Dimensions: ${imageWidth}x${imageHeight}`)

          scenes.value[i].generationProgress = 100

          // Show success notification
          toast.success(`Image ${i + 1} generated!`, {
            description: `Scene ${i + 1} image ready`,
            duration: 2000
          })
        } else {
          throw new Error('No image URL returned from generation service')
        }
      } catch (error: any) {
        console.error(`Failed to generate image for scene ${i + 1}:`, error)
        // Continue with next scene even if one fails
        toast.error(`Failed to generate image ${i + 1}`, {
          description: error.message || 'Continuing with next scene...'
        })
      } finally {
        // Clear loading state for this scene
        generatingSceneIndices.value.delete(i)
        scenes.value[i].isGenerating = false
        scenes.value[i].generationProgress = 0
      }
      })) // Close Promise.all and map

      // Log batch completion
      logger.log(`✅ Batch ${batchNumber}/${totalBatches} complete`)

      // Show batch completion notification (except for last batch - will show final message)
      if (batchNumber < totalBatches) {
        const imagesCompleted = batchStart + batch.length
        toast.info(`Batch ${batchNumber}/${totalBatches} complete`, {
          description: `${imagesCompleted} of ${scenesToGenerate.length} images generated`,
          duration: 2000
        })
      }
    } // Close batch for loop

    // Count how many scenes now have images
    const totalWithImages = scenes.value.filter(s => s.generatedImage).length
    const totalScenes = scenes.value.length

    toast.success('Image generation complete!', {
      description: `${totalWithImages} of ${totalScenes} scenes have images`
    })
  } catch (error: any) {
    console.error('Image generation failed:', error)
    toast.error('Image generation failed', {
      description: error.message || 'Please try again'
    })
  } finally {
    isGeneratingImages.value = false
    currentImageIndex.value = 0
  }
}

// Video generation
const generateVideo = async () => {
  if (!hasAllImages.value || !projectId.value) {
    toast.error('Cannot generate video', {
      description: 'Please ensure all scene images are generated first'
    })
    return
  }

  if (projectMode.value === 'talking_scenes' && !generatedAudio.value?.fileId) {
    toast.error('Cannot generate video', {
      description: 'Generate scene audio first so the talking-scenes timeline has a combined audio track.'
    })
    return
  }

  try {
    // Set loading state and switch to video tab IMMEDIATELY for instant UI feedback
    isGeneratingVideo.value = true
    finalGeneratedVideo.value = null  // Clear existing video to show loading screen
    showingFinalVideo.value = true
    showStoryboardLayout.value = true  // Keep storyboard layout true to show preview area
    showingGallery.value = false
    selectedSceneForPreview.value = null
    projectStatus.value = 'processing'

    const hasAudio = !!generatedAudio.value
    toast.info('Generating video...', {
      description: hasAudio ? 'This may take several minutes' : 'Generating video without audio'
    })

    // Save current scene data (including any edited prompts) before generating video
    await saveScenes()
    logger.log('✅ Saved current scene data before video generation')

    // Create timeline segments from scenes
    // Use audio duration if available, otherwise calculate from timeline
    let audioDuration: number

    // Check if scenes have manually set times (in milliseconds) - convert to seconds
    const hasManualTimes = scenes.value.every(scene =>
      scene.start_time !== undefined && scene.end_time !== undefined
    )

    if (hasAudio && generatedAudio.value) {
      audioDuration = generatedAudio.value.duration
    } else if (hasManualTimes) {
      // Calculate total duration from timeline segments
      const maxEndTime = Math.max(...scenes.value.map(scene => scene.end_time || 0))
      audioDuration = maxEndTime
      logger.log(`📊 Calculated video duration from timeline: ${audioDuration}s`)
    } else {
      // Default duration if no audio and no manual times (e.g., 3 seconds per scene)
      audioDuration = scenes.value.length * 3
      logger.log(`📊 Using default duration: ${audioDuration}s (${scenes.value.length} scenes × 3s)`)
    }

    const timeline = scenes.value.map((scene, index) => {
      let startTime: number
      let endTime: number

      if (hasManualTimes && scene.start_time !== undefined && scene.end_time !== undefined) {
        // Use manually set times (convert from milliseconds to seconds)
        startTime = scene.start_time
        endTime = scene.end_time
        console.log(`🎬 Scene ${index + 1}: Using manual times - ${startTime.toFixed(1)}s to ${endTime.toFixed(1)}s`)
      } else {
        // Auto-calculate based on audio duration
        const segmentDuration = audioDuration / scenes.value.length
        startTime = index * segmentDuration
        endTime = (index + 1) * segmentDuration
        console.log(`🎬 Scene ${index + 1}: Auto-calculated times - ${startTime.toFixed(1)}s to ${endTime.toFixed(1)}s`)
      }

      return {
        // Use video ID if available, otherwise use image ID
        image_id: scene.animatedVideo?.id || scene.generatedImage?.id!,
        // Include URL as fallback in case refresh fails
        image_url: scene.animatedVideo?.url || scene.generatedImage?.url,
        description: scene.description || '',
        prompt: scene.prompt || '',
        start_time: startTime,
        end_time: endTime,
        transition_type: (scene.transition_type || 'fade') as any,
        transition_duration: scene.transition_duration || 0.5,
        camera_movement: (scene.camera_movement || 'static') as any,
        greenscreen_effect: scene.greenscreen_effect || '',
        sort_order: index
      }
    })

    // Build video generation request
    const request: VideoGenerationRequest = {
      text: script.value,
      background_type: 'image_timeline',
      voice_id: selectedVoice.value,
      project_title: projectTitle.value,
      project_id: projectId.value,
      language_code: 'en',
      image_timeline: timeline,
      use_xfade_transitions: true,
      video_settings: {
        aspect_ratio: videoAspectRatio.value,
        resolution: videoResolution.value
      },
      caption_settings: {
        position: captionEnabled.value ? captionPosition.value : 'bottom',
        subtitle_style: captionEnabled.value ? captionStyle.value : 'none',
        font_size: captionEnabled.value ? captionFontSize.value : 0,
        font_family: captionEnabled.value ? captionFont.value : 'Arial',
        font_file_path: captionEnabled.value ? fontMappings[captionFont.value] || '' : undefined
      },
      include_watermark_logo: includeWatermarkLogo.value && hasProfileWatermarkLogo.value,
      watermark_logo_position: watermarkLogoPosition.value,
      watermark_logo_url: includeWatermarkLogo.value && hasProfileWatermarkLogo.value ? authStore.user?.watermark_logo_url : undefined
    }

    // Add existing audio information if available (like VideoGenerator.vue)
    const existingAudioId = generatedAudio.value?.fileId || generatedAudio.value?.projectId || projectId.value || ''
    if (existingAudioId) {
      request.existing_audio_id = existingAudioId
    }

    // In audio-to-video mode we expect to reuse uploaded audio; fail fast if we cannot reference it.
    if (creationMode.value === 'audioToVideo' && !request.existing_audio_id) {
      isGeneratingVideo.value = false
      showingFinalVideo.value = false
      showStoryboardLayout.value = true
      projectStatus.value = 'draft'
      toast.error('Cannot generate video', {
        description: 'Uploaded audio reference is missing. Please re-upload audio and try again.'
      })
      return
    }

    // Add music if enabled
    if (autoMatchMusic.value) {
      // TODO: Auto-match music based on script sentiment
      // For now, skip music or add a default track
    }

    logger.log('Video generation request:', request)

    // Use videoGenerationService with progress tracking
    const result = await videoGenerationService.generateVideoWithProgress(
      request,
      (progressUpdate: GenerationProgress) => {
        // Update progress UI
        logger.log('Progress update:', progressUpdate)

        if (progressUpdate.status === 'failed') {
          projectStatus.value = 'failed'
          toast.error('Video generation failed', {
            description: progressUpdate.message
          })
        }
      }
    )

    logger.log('Video generation result:', result)

    // Handle different result statuses
    const pollingProjectId = result.project_id || projectId.value

    if (result.status === 'processing' && result.job_id && pollingProjectId) {
      toast.info('Video is processing', {
        description: 'Your video is being rendered. This may take a few minutes.',
        duration: 5000
      })

      // Poll until the backend reports completion or failure.
      let hasShownPollingError = false
      const pollInterval = setInterval(async () => {
        try {
          const statusResponse = await apiClient.get(`/api/video/projects/${pollingProjectId}/details-full`)
          const statusData = statusResponse.data
          const project = statusData.project || {}

          if (project.status === 'completed') {
              clearInterval(pollInterval)
              projectStatus.value = 'completed'
              isGeneratingVideo.value = false

              toast.success('Video generated successfully!', {
                description: 'Your video is ready to view',
                duration: 5000
              })

	              // Reload project to get video URL
	              await loadProject()
          } else if (project.status === 'failed') {
            clearInterval(pollInterval)
            projectStatus.value = 'failed'
            isGeneratingVideo.value = false

            // Revert to storyboard view on failure
            showingFinalVideo.value = false
            showStoryboardLayout.value = true

            let failureMessage = project.error_message || project.error || statusData.error
            const processingOptions = project.processing_options
            if (!failureMessage && processingOptions) {
              try {
                const parsedOptions = typeof processingOptions === 'string'
                  ? JSON.parse(processingOptions)
                  : processingOptions
                failureMessage = parsedOptions?.error || parsedOptions?.error_message || parsedOptions?.details?.error
              } catch {
                failureMessage = undefined
              }
            }

            toast.error('Video generation failed', {
              description: failureMessage || 'Please try again or contact support'
            })
          }
        } catch (err) {
          console.error('Error polling video status:', err)
          if (!hasShownPollingError) {
            hasShownPollingError = true
            toast.error('Unable to check video status', {
              description: err instanceof Error ? err.message : 'The backend status check failed.'
            })
          }
        }
      }, 5000) // Poll every 5 seconds

    } else if (result.videoUrl) {
      // Video completed immediately
      projectStatus.value = 'completed'
      isGeneratingVideo.value = false

      toast.success('Video generated successfully!', {
        description: 'Your video is ready to view',
        duration: 5000
      })

      await loadProject()
    }

  } catch (error: any) {
    console.error('Video generation failed:', error)
    isGeneratingVideo.value = false
    projectStatus.value = 'failed'

    // Revert to storyboard view on error
    showingFinalVideo.value = false
    showStoryboardLayout.value = true

    toast.error('Failed to generate video', {
      description: error.message || 'Please try again'
    })
  }
}

// Utility functions
const formatDuration = (seconds: number): string => {
  if (!seconds || seconds === 0) return '0:00'
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = Math.floor(seconds % 60)
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
}

// Hybrid download approach: native first, blob fallback
const downloadVideo = async () => {
  if (!finalGeneratedVideo.value?.url) {
    toast.error('No video available to download')
    return
  }

  if (isDownloadingVideo.value) {
    return // Prevent multiple simultaneous downloads
  }

  const filename = `${projectTitle.value || 'video'}_${projectId.value || 'generated'}.mp4`

  // Detect iOS/Safari (download attribute often doesn't work there)
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
  const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent)

  try {
    isDownloadingVideo.value = true

    // If iOS or Safari, go straight to blob method (more reliable)
    if (isIOS || isSafari) {
      await downloadViaBlob(finalGeneratedVideo.value.url, filename)
      return
    }

    // Try native download first (shows browser progress)
    try {
      const link = document.createElement('a')
      link.href = finalGeneratedVideo.value.url
      link.download = filename
      link.target = '_blank'

      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)

      toast.success('Download started!', { description: 'Check your browser downloads' })

      // Reset loading state after brief delay
      setTimeout(() => {
        isDownloadingVideo.value = false
      }, 1000)
    } catch (nativeError) {
      // Native method failed, try blob fallback
      console.log('Native download failed, trying blob method...', nativeError)
      await downloadViaBlob(finalGeneratedVideo.value.url, filename)
    }
  } catch (error) {
    console.error('Download failed:', error)
    toast.error('Download failed', { description: 'Please try again or right-click the video to save' })
    isDownloadingVideo.value = false
  }
}

// Blob download method (reliable but no progress bar)
const downloadViaBlob = async (url: string, filename: string) => {
  try {
    toast.info('Preparing download...', { description: 'This may take a moment' })

    // Fetch the video as a blob
    const response = await fetch(url)
    if (!response.ok) {
      throw new Error('Failed to fetch video')
    }

    const blob = await response.blob()

    // Create a download link
    const blobUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = filename

    // Trigger download
    document.body.appendChild(link)
    link.click()

    // Cleanup
    document.body.removeChild(link)
    window.URL.revokeObjectURL(blobUrl)

    toast.success('Download started!', { description: 'Check your downloads folder' })
  } finally {
    isDownloadingVideo.value = false
  }
}

// Check if a signed URL is expired or expiring soon
const isUrlExpiredOrExpiring = (url: string | undefined, bufferHours: number = 1): boolean => {
  if (!url) return true

  try {
    // Parse URL to extract expiration timestamp
    const urlObj = new URL(url)
    const expiresParam = urlObj.searchParams.get('Expires') || urlObj.searchParams.get('X-Goog-Expires')

    if (!expiresParam) {
      // No expiration info, assume it's expired (better safe than sorry)
      return true
    }

    const expiresTimestamp = parseInt(expiresParam, 10)
    const now = Math.floor(Date.now() / 1000) // Current time in seconds
    const bufferSeconds = bufferHours * 3600

    // Check if expired or expiring within buffer time
    return expiresTimestamp - now < bufferSeconds
  } catch (error) {
    console.error('Error checking URL expiration:', error)
    return true // Assume expired if we can't parse
  }
}

// Refresh scene image/video URLs that are expired
const refreshSceneUrls = async () => {
  if (!scenes.value || scenes.value.length === 0) {
    return
  }

  logger.log('🔄 Checking scene URLs for expiration...')
  let refreshedCount = 0

  for (const scene of scenes.value) {
    try {
      // Check and refresh generated image URL
      if (scene.generatedImage?.url) {
        if (isUrlExpiredOrExpiring(scene.generatedImage.url)) {
          logger.log(`🔄 Refreshing expired image URL for scene: ${scene.description}`)
          try {
            const imageRefreshId = scene.generatedImage.id || scene.id
            const response = await apiClient.post(`/api/image-generation/refresh-urls/${imageRefreshId}`, {
              current_url: scene.generatedImage.url
            })
            if (response.data?.signed_url) {
              scene.generatedImage.url = response.data.signed_url
              refreshedCount++
              logger.log(`✅ Refreshed image URL for scene: ${scene.description}`)
            }
          } catch (error) {
            logger.error(`Failed to refresh image URL for scene ${scene.description}:`, error)
          }
        }
      }

      // Check and refresh animated video URL
      if (scene.animatedVideo?.url) {
        if (isUrlExpiredOrExpiring(scene.animatedVideo.url)) {
          logger.log(`🔄 Refreshing expired video URL for scene: ${scene.description}`)
          try {
            const videoRefreshId = scene.animatedVideo.id || scene.generatedImage?.id || scene.id
            const response = await apiClient.post(`/api/image-generation/refresh-urls/${videoRefreshId}`, {
              current_url: scene.animatedVideo.url
            })
            if (response.data?.signed_url) {
              scene.animatedVideo.url = response.data.signed_url
              scene.animatedVideo.thumbnailUrl = response.data.signed_url
              refreshedCount++
              logger.log(`✅ Refreshed video URL for scene: ${scene.description}`)
            }
          } catch (error) {
            logger.error(`Failed to refresh video URL for scene ${scene.description}:`, error)
          }
        }
      }
    } catch (error) {
      logger.error(`Error processing scene ${scene.description}:`, error)
    }
  }

  if (refreshedCount > 0) {
    logger.log(`✅ Refreshed ${refreshedCount} expired scene URLs`)
  } else {
    logger.log('✅ All scene URLs are up to date')
  }
}

const formatDate = (dateString: string): string => {
  if (!dateString) return 'Unknown'
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins} min ago`
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`

  return date.toLocaleDateString()
}

// Recent projects for selection
const recentProjects = ref<any[]>([])
const isLoadingProjects = ref(false)
const hasDissmissedSelector = ref(false)

// Load recent projects
const loadRecentProjects = async () => {
  try {
    isLoadingProjects.value = true
    const response = await apiClient.get('/api/video/projects?limit=10&sort=last_edited')

    if (response.data.projects) {
      recentProjects.value = response.data.projects
      logger.log('Loaded recent projects:', recentProjects.value.length)
    }
  } catch (error) {
    console.error('Failed to load recent projects:', error)
  } finally {
    isLoadingProjects.value = false
  }
}

// Select a project to edit
const selectProject = (project: any) => {
  router.push(`/app/simple-creator/${project.id}`)
}

// Go back to projects list
const goBackToProjects = () => {
  router.push('/app')
}

// Start a new project
const startNewProject = () => {
  // Reset all state
  script.value = ''
  generatedAudio.value = null
  appliedAudioSpeed.value = 1.0
  scenes.value = []
  timelineSegments.value = []
  projectTitle.value = 'My Video Project'
  projectStatus.value = 'draft'
  creationMode.value = 'scriptToVideo'
  uploadedAudioFile.value = null
  uploadedAudioUrl.value = null
  selectedStyleTemplate.value = null

  // Dismiss the project selector modal
  hasDissmissedSelector.value = true

  logger.log('Starting new project - modal dismissed')
}

// Create new project from navbar
const createNewProject = async () => {
  if (projectId.value) {
    // If we're currently viewing a project, confirm before creating new
    const confirmed = confirm('Are you sure you want to create a new project? Any unsaved changes will be lost.')
    if (!confirmed) return
  }

  // Reset all state
  startNewProject()

  // Reset the dismissed flag to allow modal to show again if needed
  hasDissmissedSelector.value = false

  // Navigate to simple-creator without ID
  await router.push('/app/simple-creator')

  // After navigation, dismiss the selector so user can start working
  hasDissmissedSelector.value = true

  toast.success('New project started', {
    description: 'Start creating your video'
  })
}

// Auto-save selected voice as default when user changes it
// This watch will automatically save the last selected voice as the default
watch(selectedVoice, (newVoice, oldVoice) => {
  logger.log('🔍 Voice watch triggered:', {
    newVoice,
    oldVoice,
    isLoadingInitialPreferences: isLoadingInitialPreferences.value,
    willSave: newVoice && !isLoadingInitialPreferences.value && newVoice !== oldVoice
  })

  // Only auto-save if:
  // 1. We have a new voice selected
  // 2. We're not loading initial data (to prevent saving during component mount)
  // 3. The voice actually changed (not just a re-assignment)
  if (newVoice && !isLoadingInitialPreferences.value && newVoice !== oldVoice) {
    try {
      const voiceObj = voiceOptions.value.find(v => v.id === newVoice)
      if (voiceObj) {
        logger.log('💾 Attempting to save voice:', newVoice, voiceObj.provider)
        preferencesStore.setDefaultVoice(newVoice, voiceObj.provider || 'minimax')
        logger.log('✅ Auto-saved voice as default:', voiceObj.name)

        // Verify it was saved
        const stored = localStorage.getItem('userPreferences')
        logger.log('📦 localStorage after save:', stored)
      }
    } catch (error) {
      console.error('❌ Failed to auto-save voice as default:', error)
    }
  }
})

// Auto-save audio speed as default when user changes it
watch(audioSpeed, (newSpeed, oldSpeed) => {
  logger.log('🔍 Audio speed watch triggered:', {
    newSpeed,
    oldSpeed,
    isLoadingInitialPreferences: isLoadingInitialPreferences.value,
    willSave: newSpeed && !isLoadingInitialPreferences.value && newSpeed !== oldSpeed
  })

  // Only auto-save if we're not loading initial data and the speed actually changed
  if (newSpeed && !isLoadingInitialPreferences.value && newSpeed !== oldSpeed) {
    try {
      logger.log('💾 Attempting to save audio speed:', newSpeed)
      preferencesStore.setDefaultAudioSpeed(newSpeed)
      logger.log('✅ Auto-saved audio speed as default:', newSpeed)
    } catch (error) {
      console.error('❌ Failed to auto-save audio speed as default:', error)
    }
  }
})

// Auto-save selected style template as default when user changes it
watch(selectedStyleTemplate, (newStyle, oldStyle) => {
  logger.log('🔍 Style template watch triggered:', {
    newStyle,
    oldStyle,
    isLoadingInitialPreferences: isLoadingInitialPreferences.value,
    willSave: !isLoadingInitialPreferences.value && newStyle !== oldStyle
  })

  // Only auto-save if we're not loading initial data and the style actually changed
  if (!isLoadingInitialPreferences.value && newStyle !== oldStyle) {
    try {
      logger.log('💾 Attempting to save style template:', newStyle)
      preferencesStore.setDefaultStyleTemplate(newStyle)
      logger.log('✅ Auto-saved style template as default:', newStyle)
    } catch (error) {
      console.error('❌ Failed to auto-save style template as default:', error)
    }
  }
})

// Auto-save video settings as default when user changes them
watch([videoAspectRatio, videoResolution, captionEnabled, captionPosition, captionStyle, captionFont, captionFontSize], ([newAspectRatio, newResolution, newCaptionEnabled, newCaptionPosition, newCaptionStyle, newCaptionFont, newCaptionFontSize], [oldAspectRatio, oldResolution, oldCaptionEnabled, oldCaptionPosition, oldCaptionStyle, oldCaptionFont, oldCaptionFontSize]) => {
  logger.log('🔍 Video settings watch triggered:', {
    newAspectRatio,
    newResolution,
    newCaptionEnabled,
    newCaptionPosition,
    newCaptionStyle,
    newCaptionFont,
    newCaptionFontSize,
    isLoadingInitialPreferences: isLoadingInitialPreferences.value
  })

  // Only auto-save if we're not loading initial data and at least one value changed
  if (!isLoadingInitialPreferences.value && (
    newAspectRatio !== oldAspectRatio ||
    newResolution !== oldResolution ||
    newCaptionEnabled !== oldCaptionEnabled ||
    newCaptionPosition !== oldCaptionPosition ||
    newCaptionStyle !== oldCaptionStyle ||
    newCaptionFont !== oldCaptionFont ||
    newCaptionFontSize !== oldCaptionFontSize
  )) {
    try {
      logger.log('💾 Attempting to save video settings')
      preferencesStore.setDefaultVideoSettings(
        newAspectRatio,
        newResolution,
        newCaptionEnabled,
        newCaptionPosition,
        newCaptionStyle,
        newCaptionFont,
        newCaptionFontSize
      )
      logger.log('✅ Auto-saved video settings as default')
    } catch (error) {
      console.error('❌ Failed to auto-save video settings as default:', error)
    }
  }
})

// Watch for project status changes - reload video when status becomes 'completed'
watch(() => projectStatus.value, (newStatus, oldStatus) => {
  if (newStatus && oldStatus && newStatus !== oldStatus) {
    logger.log(`📊 Project status changed: ${oldStatus} -> ${newStatus}`)
    // If status changed to completed, refresh final video
    if (newStatus === 'completed') {
      logger.log('✅ Project completed, checking for final video...')
      setTimeout(() => {
        checkAndLoadFinalVideo()
      }, 2000) // Wait 2 seconds for backend to finish processing
    }
  }
})

// Lifecycle
onMounted(async () => {
  logger.log('SimpleProjectCreator mounted', { projectId: projectId.value })

  // Load custom voices
  await fetchCustomVoices()

  // Set loading state immediately if we have a projectId to prevent flash of Script tab
  if (projectId.value) {
    isLoadingProject.value = true
  }


  // Load saved preferences (voice and audio speed)
  try {
    logger.log('🔵 Loading user preferences...')

    // Load saved voice preference
    if (preferencesStore.preferences.defaultVoiceId) {
      const savedVoice = preferencesStore.preferences.defaultVoiceId
      const savedProvider = preferencesStore.preferences.defaultTtsProvider || 'minimax'

      logger.log('🔵 Found saved voice preference:', { savedVoice, savedProvider })
      selectedVoice.value = savedVoice
      ttsProvider.value = savedProvider as 'minimax' | 'deepgram' | 'google' | 'elevenlabs'
    }

    // Load saved audio speed preference
    if (preferencesStore.preferences.defaultAudioSpeed !== undefined) {
      const savedSpeed = preferencesStore.preferences.defaultAudioSpeed
      logger.log('🔵 Found saved audio speed preference:', savedSpeed)
      audioSpeed.value = savedSpeed
    }

    // Load saved style template preference
    if (preferencesStore.preferences.defaultStyleTemplate !== undefined) {
      const savedStyle = preferencesStore.preferences.defaultStyleTemplate
      logger.log('🔵 Found saved style template preference:', savedStyle)
      selectedStyleTemplate.value = savedStyle
    }

    // Load saved video settings preferences
    if (preferencesStore.preferences.defaultVideoAspectRatio) {
      videoAspectRatio.value = preferencesStore.preferences.defaultVideoAspectRatio
      logger.log('🔵 Found saved video aspect ratio:', videoAspectRatio.value)
    }
    if (preferencesStore.preferences.defaultVideoResolution) {
      videoResolution.value = preferencesStore.preferences.defaultVideoResolution
      logger.log('🔵 Found saved video resolution:', videoResolution.value)
    }
    if (preferencesStore.preferences.defaultCaptionEnabled !== undefined) {
      captionEnabled.value = preferencesStore.preferences.defaultCaptionEnabled
      logger.log('🔵 Found saved caption enabled:', captionEnabled.value)
    }
    if (preferencesStore.preferences.defaultCaptionPosition) {
      captionPosition.value = preferencesStore.preferences.defaultCaptionPosition
      logger.log('🔵 Found saved caption position:', captionPosition.value)
    }
    if (preferencesStore.preferences.defaultCaptionStyle) {
      captionStyle.value = preferencesStore.preferences.defaultCaptionStyle
      logger.log('🔵 Found saved caption style:', captionStyle.value)
    }
    if (preferencesStore.preferences.defaultCaptionFont) {
      captionFont.value = preferencesStore.preferences.defaultCaptionFont
      logger.log('🔵 Found saved caption font:', captionFont.value)
    }
    if (preferencesStore.preferences.defaultCaptionFontSize) {
      captionFontSize.value = preferencesStore.preferences.defaultCaptionFontSize
      logger.log('🔵 Found saved caption font size:', captionFontSize.value)
    }

    logger.log('✅ User preferences loaded successfully')
  } catch (error) {
    console.error('❌ Failed to load user preferences:', error)
  } finally {
    // Set loading flag to false after initial load to enable auto-save
    isLoadingInitialPreferences.value = false
    logger.log('🔵 Initial preferences loading complete, auto-save enabled')
  }

  // Add click outside listener for voice dropdown
  document.addEventListener('click', handleClickOutsideVoiceDropdown)

  // Initialize ttsProvider based on default voice (if not already set from preferences)
  if (!preferencesStore.preferences.defaultVoiceId) {
    const defaultVoice = voiceOptions.value.find(v => v.id === selectedVoice.value)
    if (defaultVoice?.provider && (defaultVoice.provider === 'minimax' || defaultVoice.provider === 'deepgram' || defaultVoice.provider === 'google' || defaultVoice.provider === 'elevenlabs')) {
      ttsProvider.value = defaultVoice.provider
    }
  }

  // Check for cached data from recent generation (prevents loss during route change).
  // Existing project routes still load from the backend below so stale session cache
  // cannot leave the editor blank after a restart or failed generation.

  const cachedAudio = sessionStorage.getItem('simple-creator-temp-audio')
  if (cachedAudio) {
    try {
      const audioData = JSON.parse(cachedAudio)
      generatedAudio.value = audioData
      appliedAudioSpeed.value = Number(audioData.appliedAudioSpeed || audioData.audioSpeed || audioSpeed.value || 1.0)
      audioPlayerKey.value++
      logger.log('✅ Restored cached audio from sessionStorage:', audioData)
      // Clear the cache after using it
      sessionStorage.removeItem('simple-creator-temp-audio')
    } catch (e) {
      console.error('Failed to parse cached audio:', e)
      sessionStorage.removeItem('simple-creator-temp-audio')
    }
  }

  const cachedScenes = sessionStorage.getItem('simple-creator-temp-scenes')
  if (cachedScenes) {
    try {
      const scenesData = JSON.parse(cachedScenes)
      if (Array.isArray(scenesData) && scenesData.length > 0) {
        scenes.value = scenesData
        logger.log(`✅ Restored ${scenesData.length} cached scenes from sessionStorage`)
      } else {
        logger.log('⏭️ Ignored empty cached scenes from sessionStorage')
      }
      // Clear the cache after using it
      sessionStorage.removeItem('simple-creator-temp-scenes')
    } catch (e) {
      console.error('Failed to parse cached scenes:', e)
      sessionStorage.removeItem('simple-creator-temp-scenes')
    }
  }

  // Restore layout state from cache
  const cachedLayoutState = sessionStorage.getItem('simple-creator-show-storyboard-layout')
  if (cachedLayoutState === 'true') {
    showStoryboardLayout.value = true
    logger.log('✅ Restored storyboard layout state from sessionStorage')
    // Clear the cache after using it
    sessionStorage.removeItem('simple-creator-show-storyboard-layout')
  }

  // Load characters for @mention detection
  try {
    logger.log('👥 Loading characters for @mention detection...')
    await charactersStore.fetchCharacters(true)
    logger.log(`✅ Loaded ${charactersStore.characters?.length || 0} characters`)
  } catch (error) {
    console.error('❌ Failed to load characters:', error)
  }

  if (projectId.value) {
    loadProject()
  } else {
    // No project ID - load recent projects for selection
    loadRecentProjects()
  }
})

onBeforeUnmount(() => {
  // Remove click outside listener
  document.removeEventListener('click', handleClickOutsideVoiceDropdown)
})

// Load existing project
const loadProject = async () => {
  if (!projectId.value) return

  isLoadingProject.value = true

  try {
    logger.log('Loading project:', projectId.value)
    const response = await apiClient.get(`/api/video/projects/${projectId.value}/details-full`)

    // Debug: Log the full response structure
    console.log('🔍 Full project response:', {
      assets: response.data.assets,
      project: response.data.project,
      audio_url: response.data.audio_url,
      audio_duration: response.data.audio_duration
    })

    if (response.data.project) {
      projectTitle.value = response.data.project.title || 'My Video Project'
      projectStatus.value = response.data.project.status || 'draft'
      script.value = response.data.assets?.original_text_content || ''
      currentUserId.value = response.data.project.user_id || null
      logger.log('✅ Loaded user ID:', currentUserId.value)

      // Load audio if available (skip if we already have cached audio to avoid overwriting)
      if (!generatedAudio.value) {
        // Try multiple possible audio data sources
        const audioUrl = response.data.assets?.audio_signed_url ||
                        response.data.assets?.audio_url ||
                        response.data.assets?.audio_file?.url ||
                        response.data.audio_url ||
                        response.data.project?.audio_url

        const audioDuration = response.data.assets?.audio_duration_seconds ||
                             response.data.assets?.audio_file?.duration ||
                             response.data.audio_duration ||
                             response.data.project?.audio_duration ||
                             0

        const audioFileId = response.data.assets?.audio_file_id ||
                           response.data.project?.audio_file_id ||
                           response.data.assets?.audio_file?.id ||
                           response.data.audio_file_id ||
                           response.data.audio_id

        if (audioUrl) {
          // If duration is 0 or null, try to fetch it from the audio file
          let finalDuration = audioDuration
          if (!finalDuration || finalDuration === 0) {
            try {
              const audio = new Audio()
              audio.src = audioUrl
              finalDuration = await new Promise<number>((resolve) => {
                audio.addEventListener('loadedmetadata', () => {
                  resolve(audio.duration || 0)
                })
                audio.addEventListener('error', () => {
                  console.warn('Failed to load audio metadata for duration')
                  resolve(0)
                })
                // Timeout fallback
                setTimeout(() => resolve(0), 5000)
              })
              console.log('📊 Fetched audio duration from file:', finalDuration)
            } catch (e) {
              console.warn('Could not fetch audio duration:', e)
              finalDuration = 0
            }
          }

          generatedAudio.value = {
            url: audioUrl,
            duration: finalDuration,
            fileId: audioFileId,
            projectId: projectId.value
          }
          const projectAppliedSpeed = Number(
            response.data.project?.processing_options?.audio_speed ||
            response.data.project?.draft_data?.ui_preferences?.audio_speed ||
            audioSpeed.value ||
            1.0
          )
          appliedAudioSpeed.value = Number.isFinite(projectAppliedSpeed) ? projectAppliedSpeed : 1.0
          // Force audio player refresh
          audioPlayerKey.value++
          logger.log('✅ Loaded existing audio:', generatedAudio.value)
        } else {
          logger.log('⏭️ No audio found in project data')
        }
      } else {
        logger.log('⏭️ Skipped loading audio - already have cached version')
      }

      // Check and load final video using the video file API
      // This is done separately to match ProjectGeneratorView's approach
      await checkAndLoadFinalVideo()

      // Load timeline segments if available
      if (response.data.timeline_segments?.length > 0) {
        timelineSegments.value = sortTimelineSegmentsByOrder(response.data.timeline_segments)
        logger.log('✅ Loaded timeline segments:', timelineSegments.value.length)
      }

      // Load scenes from project_scenes table (primary source)
      try {
        logger.log('🔍 Attempting to load scenes from project_scenes for project:', projectId.value)
        const scenesResponse = await loadProjectScenes(projectId.value)
        logger.log('🔍 project_scenes response:', scenesResponse)
        if (scenesResponse.scenes && scenesResponse.scenes.length > 0) {
          scenes.value = scenesResponse.scenes.map((scene: any, index: number) => {
            // Check if generated_image URL is actually a video (legacy handling)
            const imageUrl = scene.generated_image?.url
            const isVideoFile = imageUrl && /\.(mp4|mov|webm|avi|mkv)(\?|$)/i.test(imageUrl)

            // Determine animatedVideo: prefer explicit animated_video, fallback to video in generated_image
            let animatedVideo = undefined
            if (scene.animated_video?.url) {
              // Use explicit animated_video from backend
              animatedVideo = {
                id: scene.animated_video.id,
                url: scene.animated_video.url,
                duration: scene.animated_video.duration || 8,
                thumbnailUrl: scene.animated_video.url
              }
            } else if (isVideoFile) {
              // Legacy: generated_image URL is actually a video
              animatedVideo = {
                id: scene.generated_image.id,
                url: imageUrl,
                duration: scene.generated_image.duration || 5,
                thumbnailUrl: imageUrl
              }
            }

            // Determine generatedImage: only use if it's not a video file
            let generatedImage = undefined
            if (scene.generated_image && !isVideoFile) {
              generatedImage = {
                id: scene.generated_image.id,
                url: scene.generated_image.url,
                width: scene.generated_image.width || 1024,
                height: scene.generated_image.height || 1024,
                aspectRatio: scene.generated_image.aspectRatio || scene.generated_image.aspect_ratio || '1:1'
              }
            }

            const loadedScene = {
              id: scene.id || crypto.randomUUID(),
              description: scene.description || `Scene ${index + 1}`,
              prompt: shouldAutofillTalkingImagePrompt(scene.prompt, scene.scene_script, scene.description)
                ? buildTalkingImagePrompt({
                    scene_type: scene.scene_type || 'dialogue',
                    scene_script: scene.scene_script || scene.description || '',
                    description: scene.description || `Scene ${index + 1}`,
                    layout_type: scene.layout_type || 'single',
                    dialogue_turns: scene.dialogue_turns || [],
                    character_ids: scene.character_ids || [],
                  })
                : (scene.prompt || scene.description || `Scene ${index + 1}`),
              scene_type: scene.scene_type || undefined,
              scene_script: scene.scene_script || undefined,
              layout_type: scene.layout_type || undefined,
              target_duration: scene.target_duration || undefined,
              start_time: scene.start_time,
              end_time: scene.end_time,
              character_ids: scene.character_ids || [],
              dialogue_turns: (scene.dialogue_turns || []).map((turn: any) => ({
                ...turn,
                provider: turn.provider,
                audio_speed: turn.audio_speed,
                voice_override: turn.voice_override,
              })),
              character_layout: scene.character_layout || [],
              generatedImage,
              animatedVideo,
              animationPrompt: scene.animation_prompt,  // Map snake_case to camelCase
              isGenerating: false,
              generationProgress: 0,
              camera_movement: scene.camera_movement || 'static',
              transition_type: scene.transition_type || 'fade',
              transition_duration: scene.transition_duration || 0.5,
              greenscreen_effect: scene.greenscreen_effect || '',
              sceneAudio: normalizeSceneAudio(scene),
            }

            // Debug log the loaded greenscreen effect
            console.log(`🔍 Loaded scene ${index + 1} greenscreen_effect:`, scene.greenscreen_effect, '→', loadedScene.greenscreen_effect)

            return loadedScene
          })
          logger.log(`✅ Loaded ${scenesResponse.scenes_count} scenes from project_scenes table`)

          // Sync character_ids with actual @ mentions in prompts to remove stale data
          let needsSync = false
          scenes.value.forEach((scene, index) => {
            if (scene.prompt) {
              const actualCharacterIds = extractCharacterIdsFromPrompt(scene.prompt)
              if (JSON.stringify(scene.character_ids) !== JSON.stringify(actualCharacterIds)) {
                logger.log(`🔄 Syncing character_ids for scene ${index + 1}: ${scene.character_ids?.length || 0} → ${actualCharacterIds.length}`)
                scene.character_ids = actualCharacterIds
                needsSync = true
              }
            }
          })

          // Save synced character_ids back to database
          if (needsSync) {
            try {
              await saveScenes()
              logger.log('✅ Saved synced character_ids to database')
            } catch (error) {
              logger.error('Failed to save synced character_ids:', error)
            }
          }
        } else {
          // Fallback: Load scenes from timeline segments if no scenes in project_scenes
          if (response.data.timeline_segments?.length > 0) {
            scenes.value = sortTimelineSegmentsByOrder(response.data.timeline_segments).map((segment: any, index: number) => {
              // Check if image_info URL is actually a video
              const imageUrl = segment.image_info?.signed_url
              const isVideoFile = imageUrl && /\.(mp4|mov|webm|avi|mkv)(\?|$)/i.test(imageUrl)
              const sceneDescription = segment.scene_description || segment.description || `Scene ${index + 1}`
              const scenePrompt = segment.prompt || sceneDescription

              return {
                id: segment.id || crypto.randomUUID(),
                description: sceneDescription,
                prompt: scenePrompt,
                scene_type: undefined,
                scene_script: sceneDescription,
                layout_type: undefined,
                target_duration: (segment.end_time || 0) - (segment.start_time || 0),
                start_time: segment.start_time,
                end_time: segment.end_time,
                character_ids: [],
                dialogue_turns: [],
                character_layout: [],
                generatedImage: (imageUrl && !isVideoFile) ? {
                  id: segment.image_id,
                  url: imageUrl,
                  width: segment.image_info?.width || 1024,
                  height: segment.image_info?.height || 1024,
                  aspectRatio: segment.image_info?.aspect_ratio || '1:1'
                } : undefined,
                animatedVideo: isVideoFile ? {
                  id: segment.image_id,
                  url: imageUrl,
                  duration: segment.image_info?.duration || 5,
                  thumbnailUrl: imageUrl
                } : undefined,
                isGenerating: false,
                generationProgress: 0,
                camera_movement: segment.camera_movement || 'static',
                transition_type: segment.transition_type || 'fade',
                transition_duration: segment.transition_duration || 0.5,
                greenscreen_effect: segment.greenscreen_effect || '',
                sceneAudio: undefined,
              }
            })
            logger.log('✅ Loaded scenes from timeline segments (fallback):', scenes.value.length)
          }
        }
      } catch (scenesError) {
        logger.warn('Could not load scenes from project_scenes table:', scenesError)
        // Fallback: Load scenes from timeline segments
        if (response.data.timeline_segments?.length > 0) {
          scenes.value = sortTimelineSegmentsByOrder(response.data.timeline_segments).map((segment: any, index: number) => {
            // Check if image_info URL is actually a video
            const imageUrl = segment.image_info?.signed_url
            const isVideoFile = imageUrl && /\.(mp4|mov|webm|avi|mkv)(\?|$)/i.test(imageUrl)
            const sceneDescription = segment.scene_description || segment.description || `Scene ${index + 1}`
            const scenePrompt = segment.prompt || sceneDescription

            return {
              id: segment.id || crypto.randomUUID(),
              description: sceneDescription,
              prompt: scenePrompt,
              scene_type: undefined,
              scene_script: sceneDescription,
              layout_type: undefined,
              target_duration: (segment.end_time || 0) - (segment.start_time || 0),
              start_time: segment.start_time,
              end_time: segment.end_time,
              character_ids: [],
              dialogue_turns: [],
              character_layout: [],
              generatedImage: (imageUrl && !isVideoFile) ? {
                id: segment.image_id,
                url: imageUrl,
                width: segment.image_info?.width || 1024,
                height: segment.image_info?.height || 1024,
                aspectRatio: segment.image_info?.aspect_ratio || '1:1'
              } : undefined,
              animatedVideo: isVideoFile ? {
                id: segment.image_id,
                url: imageUrl,
                duration: segment.image_info?.duration || 5,
                thumbnailUrl: imageUrl
              } : undefined,
              isGenerating: false,
              generationProgress: 0,
              camera_movement: segment.camera_movement || 'static',
              transition_type: segment.transition_type || 'fade',
              transition_duration: segment.transition_duration || 0.5,
              greenscreen_effect: segment.greenscreen_effect || '',
              sceneAudio: undefined,
            }
          })
          logger.log('✅ Loaded scenes from timeline segments (fallback):', scenes.value.length)
        }
      }

      // Show storyboard layout if scenes were loaded
      if (scenes.value.length > 0) {
        showStoryboardLayout.value = true
        logger.log('✅ Showing storyboard layout - loaded scenes:', scenes.value.length)

        // Refresh any expired scene URLs
        await refreshSceneUrls()
      }

      // Load UI preferences if available. Draft saves persist preferences under
      // project.draft_data.ui_preferences; keep top-level ui_preferences as a
      // fallback for older/alternate project responses.
      const prefs = getProjectUiPreferences(response.data.project)
      if (prefs) {
        if (prefs.voice_id) {
          selectedVoice.value = prefs.voice_id
          // Set ttsProvider based on loaded voice
          const loadedVoice = voiceOptions.value.find(v => v.id === prefs.voice_id)
          if (loadedVoice?.provider && (loadedVoice.provider === 'minimax' || loadedVoice.provider === 'deepgram' || loadedVoice.provider === 'google' || loadedVoice.provider === 'elevenlabs')) {
            ttsProvider.value = loadedVoice.provider
          }
        }
        if (prefs.visual_style) selectedStyleTemplate.value = prefs.visual_style
        if (prefs.auto_match_music !== undefined) autoMatchMusic.value = prefs.auto_match_music
        if (prefs.audio_speed !== undefined) audioSpeed.value = prefs.audio_speed
        if (prefs.project_mode === 'talking_scenes' || prefs.project_mode === 'narrated_broll') {
          projectMode.value = prefs.project_mode
        }
        if (prefs.character_voice_map && typeof prefs.character_voice_map === 'object') {
          characterVoiceMap.value = prefs.character_voice_map
        }
        thumbnailPrompt.value = typeof prefs.thumbnail_prompt === 'string' ? prefs.thumbnail_prompt : thumbnailPrompt.value
        thumbnailImages.value = await refreshSavedThumbnailUrls(Array.isArray(prefs.thumbnail_images) ? prefs.thumbnail_images : [])
        selectedThumbnailIndex.value = typeof prefs.selected_thumbnail_index === 'number' && thumbnailImages.value[prefs.selected_thumbnail_index]
          ? prefs.selected_thumbnail_index
          : (thumbnailImages.value.length > 0 ? 0 : null)
        logger.log('✅ Loaded UI preferences')
      }

      if (projectMode.value === 'talking_scenes' && scenes.value.length > 0) {
        syncCharacterVoiceAssignments()
      }

      // Load global text layers from dedicated endpoint
      if (projectId.value) {
        try {
          const tlResponse = await loadProjectTextLayers(projectId.value)
          if (tlResponse.text_layers && tlResponse.text_layers.length > 0) {
            textLayers.value = tlResponse.text_layers as any[]
            logger.log('✅ Loaded text layers:', tlResponse.text_layers_count)
          }
        } catch (tlError) {
          logger.warn('Could not load text layers:', tlError)
        }
      }

      logger.log('Project loaded successfully')
    }
  } catch (error) {
    console.error('Failed to load project:', error)
    toast.error('Failed to load project')
  } finally {
    isLoadingProject.value = false
  }
}

// Save scenes to project_scenes table
const saveScenes = async (overrideProjectId?: string) => {
  // Use override if provided, otherwise use projectId from route or generatedAudio
  const effectiveProjectId = overrideProjectId || projectId.value || generatedAudio.value?.projectId

  if (!effectiveProjectId) {
    logger.log('⚠️ No project ID, skipping scene save')
    return
  }

  if (scenes.value.length === 0) {
    logger.log('⚠️ No scenes to save')
    return
  }

  // Save current prompt changes from Scene Details if a scene is selected
  if (selectedSceneForPreview.value !== null) {
    const scene = scenes.value[selectedSceneForPreview.value]
    if (scene) {
      if (sceneDetailsPrompt.value.trim()) {
        scene.prompt = sceneDetailsPrompt.value
      }
      if (sceneDetailsAnimationPrompt.value.trim()) {
        scene.animationPrompt = sceneDetailsAnimationPrompt.value
      }
    }
  }

  try {
    // Debug: Log what we're about to save
    scenes.value.forEach((scene, index) => {
      logger.log(`💾 Saving scene ${index + 1}:`, {
        description: scene.description,
        prompt: scene.prompt,
        hasPrompt: !!scene.prompt,
        promptLength: scene.prompt?.length || 0,
        camera_movement: scene.camera_movement,
        transition_type: scene.transition_type,
        greenscreen_effect: scene.greenscreen_effect
      })
    })

    const scenesData: SceneData[] = scenes.value.map((scene, index) => ({
      id: scene.id,  // Preserve scene UUID for database row ID
      scene_index: index,
      description: scene.description || '',
      prompt: scene.prompt || '',
      scene_type: scene.scene_type,
      scene_script: scene.scene_script,
      layout_type: scene.layout_type,
      target_duration: scene.target_duration,
      start_time: scene.start_time,
      end_time: scene.end_time,
      character_ids: scene.character_ids,
      dialogue_turns: scene.dialogue_turns,
      character_layout: scene.character_layout,
      // Save generated_image separately
      generated_image: scene.generatedImage,
      // Save animated_video separately for video_url in video_project_backgrounds
      animated_video: scene.animatedVideo ? {
        id: scene.animatedVideo.id,
        url: scene.animatedVideo.url,
        duration: scene.animatedVideo.duration || 8
      } : undefined,
      animation_prompt: scene.animationPrompt,
      camera_movement: scene.camera_movement,
      transition_type: scene.transition_type,
      transition_duration: scene.transition_duration,
      greenscreen_effect: scene.greenscreen_effect,
      scene_audio: scene.sceneAudio ? {
        file_id: scene.sceneAudio.fileId,
        url: scene.sceneAudio.url,
        duration: scene.sceneAudio.duration,
        transcript: scene.sceneAudio.transcript,
      } : undefined,
    }))

    const response = await saveProjectScenes(effectiveProjectId, scenesData)
    logger.log(`✅ Saved ${response.scenes_count} scenes to project_scenes table`)
  } catch (error: any) {
    console.error('Failed to save scenes:', error)
    throw error
  }
}

// Save draft functionality
const saveDraft = async (options: { skipRouteUpdate?: boolean, skipToast?: boolean } = {}) => {
  if (isSavingDraft.value) return

  try {
    isSavingDraft.value = true

    // First, save scenes to project_scenes table (if project exists)
    if (projectId.value && scenes.value.length > 0) {
      logger.log('💾 Saving scenes to project_scenes table...')
      await saveScenes()
    }

    // Convert scenes to timeline_segments format (similar to ProjectGeneratorView.vue)
    syncTimelineSegmentsFromScenes()
    const convertedTimelineSegments = timelineSegments.value

    const draftData = {
      title: projectTitle.value,
      script_content: script.value,
      ui_preferences: {
        voice_id: selectedVoice.value,
        visual_style: selectedStyleTemplate.value,
        auto_match_music: autoMatchMusic.value,
        audio_speed: audioSpeed.value,
        image_aspect_ratio: imageAspectRatio.value,
        image_generation_model: imageGenerationModel.value,
        project_mode: projectMode.value,
        character_voice_map: characterVoiceMap.value,
        thumbnail_images: serializeThumbnailImages(thumbnailImages.value),
        selected_thumbnail_index: selectedThumbnailIndex.value !== null && thumbnailImages.value[selectedThumbnailIndex.value]
          ? selectedThumbnailIndex.value
          : (thumbnailImages.value.length > 0 ? 0 : null),
        thumbnail_prompt: thumbnailPrompt.value,
      },
      timeline_segments: convertedTimelineSegments.length > 0 ? convertedTimelineSegments : timelineSegments.value,
      status: projectStatus.value,
    }

    logger.log('💾 Saving draft with timeline segments:', draftData.timeline_segments)

    let response
    if (projectId.value) {
      // Update existing project
      response = await apiClient.put(`/api/video/projects/${projectId.value}/save-draft`, draftData)
      if (!options.skipToast) {
        toast.success('Draft saved!', { description: 'Your changes have been saved' })
      }
    } else {
      // Create new project
      response = await apiClient.post('/api/video/projects/create-draft', draftData)

      // Get the new project ID from response
      const newProjectId = response.data.project_id

      // Update route with new project ID (unless skipped)
      // Note: projectId is a computed property from route.params.id, so it will update automatically
      if (!options.skipRouteUpdate) {
        router.replace(`/app/simple-creator/${newProjectId}`)
      }

      if (!options.skipToast) {
        toast.success('Project created!', { description: 'Your draft has been saved' })
      }
    }

    logger.log('Draft saved successfully:', response.data)

    // Save text layers to dedicated endpoint
    const effectivePid = projectId.value || response.data.project_id
    if (effectivePid) {
      try {
        await saveProjectTextLayers(effectivePid, textLayers.value)
        logger.log('✅ Text layers saved:', textLayers.value.length)
      } catch (tlError) {
        logger.warn('Failed to save text layers:', tlError)
      }
    }

    return response.data
  } catch (error: any) {
    console.error('Failed to save draft:', error)
    if (!options.skipToast) {
      toast.error('Failed to save draft', {
        description: error.response?.data?.detail || 'Please try again'
      })
    }
    throw error
  } finally {
    isSavingDraft.value = false
  }
}

// Title editing functions
const toggleTitleEdit = async () => {
  if (isEditingTitle.value) {
    // Save the title
    await saveTitle()
  } else {
    // Enter edit mode
    editingTitle.value = projectTitle.value
    isEditingTitle.value = true

    // Focus the input after Vue updates the DOM
    await nextTick()
    titleInput.value?.focus()
    titleInput.value?.select()
  }
}

const saveTitle = async () => {
  if (!editingTitle.value.trim() || !projectId.value) {
    cancelEdit()
    return
  }

  if (editingTitle.value === projectTitle.value) {
    isEditingTitle.value = false
    return
  }

  try {
    isSavingTitle.value = true

    const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:8000')

    const response = await fetch(`${API_BASE_URL}/api/video/projects/${projectId.value}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('access_token')}`
      },
      body: JSON.stringify({
        title: editingTitle.value.trim()
      })
    })

    if (!response.ok) {
      throw new Error(`Failed to update title: ${response.statusText}`)
    }

    // Update local state
    projectTitle.value = editingTitle.value.trim()
    isEditingTitle.value = false

    toast.success('Title updated! 💾', {
      description: 'Project title has been saved'
    })
  } catch (err) {
    console.error('Error saving title:', err)
    toast.error('Failed to save title', {
      description: err instanceof Error ? err.message : 'Please try again'
    })
    // Revert the editing title to original
    editingTitle.value = projectTitle.value
  } finally {
    isSavingTitle.value = false
  }
}

const cancelEdit = () => {
  editingTitle.value = projectTitle.value
  isEditingTitle.value = false
}
</script>

<style scoped>
:root {
  --primary: #6366f1;
  --primary-hover: #313131;
  --bg-body: #f3f4f6;
  --bg-panel: #ffffff;
  --text-main: #1f2937;
  --text-muted: #6b7280;
  --border: #e5e7eb;
  --radius: 12px;
}

.simple-creator {
  background-color: var(--bg-body);
  color: var(--text-main);
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* HEADER */
header {
  background: var(--bg-panel);
  min-height: 60px;
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--border);
  position: relative;
  z-index: 100;
  flex-shrink: 0;
}

/* Make header sticky on mobile to prevent content overlap */
@media (max-width: 900px) {
  header {
    position: sticky;
    top: 0;
    background-color: #ffffff;
  }
}

.header-title-section {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 24px;
  flex-shrink: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  margin-left: auto;
}

/* Hide desktop actions on mobile, show mobile actions */
.header-actions-desktop {
  display: none;
}

.header-actions-mobile {
  display: flex;
}

.header-nav-tabs {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  width: 100%;
  padding: 0 24px;
  border-top: 1px solid #eef2f7;
  position: relative;
  z-index: 10;
  background: #f8fafc;
  box-shadow: inset 0 -1px 0 var(--border);
  overflow-x: auto;
  scrollbar-width: none;
}

.header-nav-tabs::-webkit-scrollbar {
  display: none;
}

@media (min-width: 1024px) {
  header {
    flex-direction: row;
    align-items: center;
    flex-wrap: wrap;
    padding: 0;
  }

  .header-title-section {
    padding: 12px 24px;
    flex: 0 0 auto;
    width: auto;
    order: 1; /* Title first */
  }

  .header-nav-tabs {
    flex: 0 0 100%;
    order: 3; /* Tabs below the toolbar */
  }

  .header-actions-desktop {
    display: flex; /* Show desktop actions */
    order: 2; /* Actions in toolbar row */
    margin-left: auto; /* Push to far right */
    padding-right: 24px;
  }

  .header-actions-mobile {
    display: none; /* Hide mobile actions */
  }
}

@media (max-width: 1023px) {
  .header-title-section {
    width: 100%;
    padding: 10px 16px;
  }

  .logo {
    font-size: 1rem;
    flex: 0 0 auto;
  }

  .header-nav-tabs {
    padding: 0 16px;
  }

  .header-actions {
    gap: 4px;
  }

  .header-actions button,
  .header-actions .cursor-pointer {
    padding: 6px;
    font-size: 0.875rem;
  }

  /* Hide button label text on mobile, keep icons only */
  .header-actions-mobile .button-label {
    display: none;
  }
}

.logo {
  font-weight: 700;
  font-size: 1.2rem;
  display: flex;
  align-items: center;
  gap: 8px;
}

.logo i {
  color: var(--primary);
}

.title-back-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease;
  flex: 0 0 auto;
}

.title-back-button:hover {
  background: #f1f5f9;
  color: #111827;
}

.title-back-button i {
  color: currentColor;
  font-size: 0.85rem;
}

.header-actions button {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  color: var(--text-muted);
  font-size: 1.1rem;
  transition: color 0.2s;
}

.header-actions button:hover:not(:disabled) {
  color: var(--text-main);
}

.new-project-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  background: #10b981 !important;
  color: white !important;
  padding: 8px 16px !important;
  border-radius: 8px;
  font-size: 0.9rem !important;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: background 0.2s;
}

.new-project-btn:hover {
  background: #059669 !important;
}

.save-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--primary) !important;
  color: rgb(255, 255, 255) !important;
  padding: 8px 16px !important;
  border-radius: 8px;
  font-size: 0.9rem !important;
  font-weight: 600;
}

.save-btn:hover:not(:disabled) {
  background: var(--primary-hover) !important;
}

.save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ml-1 {
  margin-left: 4px;
}

/* TOP NAVIGATION TABS */
.top-nav-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 16px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  height: 50px;
  flex-shrink: 0;
}

.top-nav-item {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 42px;
  padding: 0 16px;
  background: transparent;
  border: 1px solid transparent;
  border-bottom: none;
  border-radius: 8px 8px 0 0;
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease, border-color 0.16s ease;
  color: #64748b;
  font-size: 0.875rem;
  font-weight: 600;
  white-space: nowrap;
  margin-top: 6px;
  margin-bottom: 0;
  position: relative;
}

.top-nav-item:hover:not(:disabled) {
  background: #fff7ed;
  color: #c2410c;
}

.top-nav-item-active {
  background: #ffffff !important;
  color: #111827 !important;
  border-color: var(--border);
  box-shadow: 0 -1px 0 rgba(15, 23, 42, 0.03);
}

.top-nav-item-active::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 1px;
  background: #ffffff;
}

.top-nav-item:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.top-nav-item i {
  font-size: 0.95rem;
}

.top-nav-label {
  font-weight: 500;
}

/* MAIN CONTAINER - SIDEBAR + WORKSPACE */
.main-container {
  display: flex;
  height: calc(100vh - 110px); /* Subtract combined header height (60px + 50px nav) */
}

/* LEFT SIDEBAR NAVIGATION - HIDDEN (moved to top) */
.left-sidebar {
  display: none;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 8px;
}

.nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 12px 8px;
  background: transparent;
  color: #9ca3af;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  text-decoration: none;
  width: 100%;
  min-height: 60px;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #e5e7eb;
}

.nav-item-active {
  background: rgba(251, 51, 51, 0.1);
  color: #FB3A34;
}

.nav-item:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.nav-item:disabled:hover {
  background: transparent;
  color: #9ca3af;
}

.nav-item i {
  font-size: 20px;
  flex-shrink: 0;
}

.nav-label {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.3px;
  text-align: center;
  line-height: 1.2;
  white-space: nowrap;
}

/* MAIN LAYOUT - SPLIT SCREEN */
.workspace {
  display: grid;
  grid-template-columns: 500px 1fr;
  height: 100%;
  flex: 1;
}

/* LEFT PANEL - INPUTS */
.input-panel {
  background: var(--bg-panel);
  padding: 12px;
  border-right: 1px solid var(--border);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* CREATION MODE TABS */
.creation-mode-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.mode-tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
  background: #f3f4f6;
  color: #4b5563;
  border: 2px solid transparent;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.mode-tab:hover {
  background: #e5e7eb;
}

.mode-tab-active {
  border-color: #FB3333 !important;
  background: #f5d1a0 !important;
  color: #FB3333 !important;
}

.mode-tab svg {
  width: 16px;
  height: 16px;
}

.section-label {
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-bottom: 12px;
  font-weight: 600;
}

/* SCRIPT INPUT */
.script-box {
  position: relative;
}

textarea {
  width: 100%;
  /* height: 150px; */
  border: 2px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  font-size: 1rem;
  resize: none;
  outline: none;
  transition: border-color 0.2s;
}

textarea:focus {
  border-color: var(--primary);
}

.ai-assist-btn {
  position: absolute;
  bottom: 12px;
  right: 12px;
  background: oklch(70.5% 0.213 47.604);
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: opacity 0.2s, cursor 0.2s;
}

.ai-assist-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.style-settings-btn {
  position: absolute;
  bottom: 12px;
  left: 56px;
  background: #fef3c7;
  color: #d97706;
  border: none;
  padding: 8px;
  border-radius: 50%;
  width: 36px;
  height: 36px;
  font-size: 1rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.style-settings-btn:hover {
  background: #fde68a;
  transform: scale(1.05);
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.15);
}

/* AUDIO UPLOAD */
.audio-upload-box {
  width: 100%;
}

.audio-upload-dropzone {
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  padding: 48px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: #f9fafb;
}

.audio-upload-dropzone:hover {
  border-color: var(--primary);
  background: #f3f4f6;
}

.upload-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto 16px;
  color: var(--text-muted);
}

.upload-text {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 8px;
}

.upload-hint {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.audio-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: #f9fafb;
  border-radius: var(--radius);
  border: 1px solid var(--border);
}

.audio-preview .audio-player {
  width: 100%;
}

.remove-audio-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  background: #fee2e2;
  color: #dc2626;
  border: none;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.remove-audio-btn:hover {
  background: #fecaca;
}

/* VOICE DROPDOWN */
.relative {
  position: relative;
}

.voice-dropdown-button {
  width: 100%;
  padding: 12px 16px;
  background: white;
  border: 2px solid var(--border);
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s;
}

.voice-dropdown-button:hover {
  border-color: var(--primary);
  background: #f9fafb;
}

.voice-display {
  font-weight: 500;
  color: var(--text-main);
}

.dropdown-icon {
  color: #9ca3af;
  font-size: 0.875rem;
  transition: transform 0.2s;
}

.dropdown-icon.rotate-180 {
  transform: rotate(180deg);
}

.voice-dropdown-menu {
  position: absolute;
  z-index: 50;
  width: 100%;
  margin-top: 4px;
  background: white;
  border: 2px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
  max-height: 384px;
  overflow-y: auto;
}

.voice-dropdown-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  cursor: pointer;
  border-bottom: 1px solid #f3f4f6;
  transition: background 0.2s;
}

.voice-dropdown-item:last-child {
  border-bottom: none;
}

.voice-dropdown-item:hover {
  background: #f9fafb;
}

.voice-dropdown-item.voice-selected {
  background: #eff6ff;
}

.voice-info {
  flex: 1;
  min-width: 0;
  padding-right: 8px;
}

.voice-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.provider-badge {
  padding: 2px 8px;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 12px;
  flex-shrink: 0;
}

.provider-minimax {
  background: #f3e8ff;
  color: #7c3aed;
}

.provider-deepgram {
  background: #dbeafe;
  color: #2563eb;
}

.provider-google {
  background: #d1fae5;
  color: #059669;
}

.provider-elevenlabs {
  background: #fef3c7;
  color: #d97706;
}

.provider-default {
  background: #f3f4f6;
  color: #6b7280;
}

.voice-name {
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--text-main);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.voice-description {
  font-size: 0.75rem;
  color: #6b7280;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 4px;
}

.voice-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.voice-tag {
  padding: 2px 6px;
  background: #f3f4f6;
  color: #6b7280;
  font-size: 0.75rem;
  border-radius: 4px;
}

.play-button {
  flex-shrink: 0;
  padding: 8px;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  width: 40px;
  height: 40px;
}

.play-button-play {
  background: var(--primary);
  color: white;
}

.play-button-play:hover {
  background: var(--primary-hover);
}

.play-button-stop {
  background: #ef4444;
  color: white;
}

.play-button-stop:hover {
  background: #dc2626;
}

.play-button-loading {
  background: #9ca3af;
  cursor: wait;
}

.play-button-loading:hover {
  background: #9ca3af;
}

.play-button:disabled {
  opacity: 0.7;
  cursor: wait;
}

.play-button i {
  font-size: 0.875rem;
}

.no-sample {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  color: #9ca3af;
}

.hidden {
  display: none;
}

.flex {
  display: flex;
}

.items-center {
  align-items: center;
}

.gap-2 {
  gap: 8px;
}

.text-gray-500 {
  color: #6b7280;
}

/* VOICE MODAL */
.voice-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.voice-modal {
  background: white;
  border-radius: 16px;
  width: 90%;
  max-width: 800px;
  height: 65vh;
  max-height: 95vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  animation: slideUp 0.3s ease-out;
}

@keyframes slideUp {
  from {
    transform: translateY(20px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

.voice-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border);
}

.voice-modal-header h3 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-main);
  margin: 0;
}

.modal-close-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 1.25rem;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  transition: all 0.2s;
}

.modal-close-btn:hover {
  background: #f3f4f6;
  color: var(--text-main);
}

.voice-modal-content {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.voice-section {
  margin-bottom: 24px;
}

.voice-section:last-child {
  margin-bottom: 0;
}

.voice-section-label {
  display: block;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 12px;
}

.voice-modal-footer {
  padding: 16px 24px;
  border-top: 1px solid var(--border);
  background: #f9fafb;
}

.voice-confirm-btn {
  width: 100%;
  padding: 12px 24px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s;
}

.voice-confirm-btn:hover {
  background: var(--primary-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 6px rgba(99, 102, 241, 0.2);
}

.voice-confirm-btn:active {
  transform: translateY(0);
}

/* STYLE MODAL */
.style-modal {
  background: white;
  border-radius: 16px;
  width: 90%;
  max-width: 700px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  animation: slideUp 0.3s ease-out;
}

.style-modal-content {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.style-templates-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 16px;
}

.style-template-card-modal {
  padding: 16px;
  background: white;
  border: 2px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
}

.style-template-card-modal:hover {
  border-color: #10b981;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.style-template-card-modal.style-template-selected {
  border-color: #10b981 !important;
  background: #d1fae5 !important;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

/* AUDIO SPEED CONTROL */
.speed-control {
  margin-top: 12px;
}

.speed-label {
  display: block;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.speed-slider-container {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid var(--border);
}

.speed-marker {
  font-size: 0.75rem;
  color: var(--text-muted);
  min-width: 30px;
  text-align: center;
}

.speed-slider {
  flex: 1;
  height: 8px;
  background: linear-gradient(to right, #dbeafe, #3b82f6);
  border-radius: 4px;
  outline: none;
  -webkit-appearance: none;
  appearance: none;
  cursor: pointer;
}

.speed-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--primary);
  cursor: pointer;
  border: 3px solid white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: transform 0.2s;
}

.speed-slider::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}

.speed-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--primary);
  cursor: pointer;
  border: 3px solid white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: transform 0.2s;
}

.speed-slider::-moz-range-thumb:hover {
  transform: scale(1.1);
}

.speed-value {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--primary);
  min-width: 3rem;
  text-align: right;
}

/* STYLE TEMPLATES */
.style-templates-container {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 8px;
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 #f1f5f9;
}

.style-templates-container::-webkit-scrollbar {
  height: 6px;
}

.style-templates-container::-webkit-scrollbar-track {
  background: #f1f5f9;
  border-radius: 1px;
}

.style-templates-container::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 1px;
}

.style-templates-container::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

.style-template-card {
  flex-shrink: 0;
  width: 160px;
  padding: 12px;
  background: white;
  border: 2px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.style-template-card:hover {
  border-color: #10b981;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.style-template-selected {
  border-color: #10b981 !important;
  background: #d1fae5 !important;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.template-icon {
  margin-bottom: 4px;
}

.template-initials {
  width: 100%;
  aspect-ratio: 16 / 9;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: linear-gradient(135deg, #1f2937, #4b5563);
  color: white;
  font-size: 1.25rem;
  font-weight: 700;
}

.template-name {
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--text-main);
  margin-bottom: 4px;
}

.template-description {
  font-size: 0.75rem;
  color: var(--text-muted);
  line-height: 1.3;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
}

/* MUSIC TOGGLE */
.music-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #f9fafb;
  padding: 12px;
  border-radius: var(--radius);
}

.switch {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 24px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  border-radius: 24px;
  transition: .4s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  border-radius: 50%;
  transition: .4s;
}

input:checked + .slider {
  background-color: var(--primary);
}

input:checked + .slider:before {
  transform: translateX(16px);
}

/* AUDIO UPLOAD */
.audio-upload-zone {
  border: 2px dashed #d1d5db;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 12px;
}

.audio-upload-zone:hover {
  border-color: #3b82f6;
  background: #eff6ff;
}

.audio-upload-zone-dragging {
  border-color: #3b82f6;
  background: #eff6ff;
}

.audio-upload-zone-disabled {
  pointer-events: none;
  opacity: 0.5;
}

.audio-upload-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.audio-upload-icon {
  width: 24px;
  height: 24px;
  color: #3b82f6;
}

.audio-upload-title {
  font-size: 0.875rem;
  font-weight: 500;
  color: #6b7280;
}

.audio-upload-subtitle {
  font-size: 0.875rem;
  color: #6b7280;
}

.audio-upload-hint {
  font-size: 0.75rem;
  color: #9ca3af;
  margin-top: 4px;
}

.audio-upload-error {
  font-size: 0.875rem;
  color: #dc2626;
  background: #fef2f2;
  padding: 8px;
  border-radius: 4px;
  margin-top: 8px;
}

.audio-upload-progress {
  margin-top: 16px;
}

.audio-upload-progress-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.audio-upload-progress-text {
  color: #1e40af;
  font-size: 0.875rem;
  font-weight: 500;
}

.audio-upload-progress-bar-container {
  width: 100%;
  background: #bfdbfe;
  border-radius: 9999px;
  height: 8px;
}

.audio-upload-progress-bar {
  background: #2563eb;
  height: 8px;
  border-radius: 9999px;
  transition: width 0.5s;
}

/* AUDIO GENERATION BUTTONS */
.generate-buttons-row {
  display: flex;
  gap: 8px;
  width: 100%;
}

.audio-gen-btn {
  flex: 1;
  padding: 12px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: var(--radius);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: background 0.2s;
}

.audio-gen-btn:hover:not(:disabled) {
  background: #2563eb;
}

.audio-gen-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.audio-scenes-btn {
  flex: 1;
  padding: 12px;
  background: #10b981;
  color: white;
  border: none;
  border-radius: var(--radius);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: background 0.2s;
}

.audio-scenes-btn:hover:not(:disabled) {
  background: #059669;
}

.audio-scenes-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.audio-player-container {
  margin-top: 12px;
  background: #f9fafb;
  padding: 12px;
  border-radius: var(--radius);
}

.audio-player {
  width: 100%;
  height: 40px;
  margin-bottom: 8px;
}

.audio-info {
  text-align: center;
}

/* MAIN BUTTON */
.generate-btn {
  background: var(--primary);
  color: white;
  border: none;
  width: 100%;
  padding: 16px;
  border-radius: var(--radius);
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  box-shadow: 0 4px 6px -1px rgba(99, 102, 241, 0.3);
  transition: background 0.2s;
}

.generate-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

.generate-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}



/* RIGHT PANEL - PREVIEW */
.preview-panel {
  padding: 8px;
  overflow-y: auto;
  background-color: #f8fafc;
  background-image: radial-gradient(#e2e8f0 1px, transparent 1px);
  background-size: 20px 20px;
}

/* When showing Remotion preview, lock to viewport height so player scales to fit */
.preview-panel--fullfit {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 0;
}

.preview-content--fullfit {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
}

@media (min-width: 1024px) {
  .preview-panel {
    padding: 12px 16px;
  }
}

.preview-content {
  /* Wrapper for preview content - no special styling on desktop */
  height: auto;
}

@media (min-width: 1024px) {
  .preview-content {
    padding-bottom: 0;
  }
}

/* .timeline-section: Default desktop - no special ordering */

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
  gap: 16px;
}

.preview-title h2 {
  font-size: 1.2rem;
  margin-bottom: 4px;
}

.preview-title p {
  color: var(--text-muted);
  font-size: 0.9rem;
}

.generate-scenes-btn, .generate-images-btn {
  background: var(--primary);
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: var(--radius);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  transition: background 0.2s;
}

.generate-scenes-btn:hover:not(:disabled), .generate-images-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

.generate-scenes-btn:disabled, .generate-images-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.generate-images-btn {
  background: #10b981;
}

.generate-images-btn:hover:not(:disabled) {
  background: #059669;
}

.add-scene-btn {
  background: #3b82f6;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: var(--radius);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  transition: background 0.2s;
}

.add-scene-btn:hover {
  background: #2563eb;
}

.effects-presets-btn {
  background: #8b5cf6;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: var(--radius);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  transition: background 0.2s;
}

.effects-presets-btn:hover {
  background: #7c3aed;
}

/* STORYBOARD GRID */
.storyboard {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 24px;
  min-height: 300px;
}

.empty-storyboard {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.empty-icon {
  font-size: 4rem;
  color: #cbd5e1;
  margin-bottom: 16px;
}

.empty-text {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 8px;
}

.empty-hint {
  font-size: 0.9rem;
  color: var(--text-muted);
}

.scenes-container {
  display: contents;
}

.scene-card {
  position: relative;
  background: white;
  border-radius: var(--radius);
  overflow: visible;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
  transition: transform 0.2s;
}

.scene-card:hover {
  transform: translateY(-4px);
}

/* Drag Handle Styles */
.drag-handle {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 10;
  cursor: move;
  cursor: grab;
  background: rgba(0, 0, 0, 0.7);
  color: white;
  padding: 6px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s;
}

.scene-card:hover .drag-handle {
  opacity: 1;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-handle:hover {
  background: rgba(0, 0, 0, 0.85);
}

.scene-drag-handle {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 9999px;
  background: rgba(17, 24, 39, 0.82);
  color: #fff;
  cursor: grab;
  opacity: 0;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.18);
  backdrop-filter: blur(8px);
  transition: opacity 0.16s ease, transform 0.16s ease, background 0.16s ease;
}

.storyboard-grid > div:hover .scene-drag-handle,
.scene-drag-handle:focus-visible {
  opacity: 1;
}

.scene-drag-handle:hover {
  background: rgba(249, 115, 22, 0.95);
  transform: scale(1.04);
}

.scene-drag-handle:active {
  cursor: grabbing;
}

.scene-drag-ghost {
  opacity: 0.45;
}

.scene-drag-chosen {
  transform: scale(0.98);
}

.scene-drag-active {
  cursor: grabbing;
}

@media (hover: none) {
  .scene-drag-handle {
    opacity: 1;
  }
}

.scene-img-placeholder {
  height: 140px;
  background: #e2e8f0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 2rem;
  position: relative;
  overflow: hidden;
}

.scene-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.scene-overlay-btn {
  position: absolute;
  background: rgba(0, 0, 0, 0.6);
  color: white;
  border: none;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
}

.scene-img-placeholder:hover .scene-overlay-btn {
  opacity: 1;
}

.scene-text {
  padding: 12px;
  font-size: 0.85rem;
  color: var(--text-muted);
  line-height: 1.4;
  border-top: 1px solid #f1f5f9;
}

/* TIMELINE SECTION */
.timeline-section {
  margin-top: 0;
  padding-top: 0;
  border-top: none;
}

@media (min-width: 1024px) {
  .timeline-section {
    margin-top: 1px;
    padding-top: 1px;
    /* border-top: 2px solid var(--border); */
  }
}

.timeline-header {
  margin-bottom: 20px;
}

.timeline-header h3 {
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 4px;
}

.timeline-hint {
  font-size: 0.9rem;
  color: var(--text-muted);
}

.timeline-placeholder {
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border: 2px dashed #cbd5e1;
  border-radius: var(--radius);
  padding: 48px 32px;
  text-align: center;
  position: relative;
  overflow: hidden;
}

.timeline-placeholder::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image:
    repeating-linear-gradient(90deg, transparent, transparent 10px, rgba(203, 213, 225, 0.3) 10px, rgba(203, 213, 225, 0.3) 11px),
    repeating-linear-gradient(0deg, transparent, transparent 10px, rgba(203, 213, 225, 0.3) 10px, rgba(203, 213, 225, 0.3) 11px);
  pointer-events: none;
}

.timeline-icon {
  font-size: 3rem;
  color: #94a3b8;
  margin-bottom: 16px;
  position: relative;
  z-index: 1;
}

.timeline-placeholder-text {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 8px;
  position: relative;
  z-index: 1;
}

.timeline-placeholder-hint {
  font-size: 0.9rem;
  color: var(--text-muted);
  margin-bottom: 24px;
  position: relative;
  z-index: 1;
}

.timeline-preview-info {
  display: flex;
  justify-content: center;
  gap: 32px;
  position: relative;
  z-index: 1;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9rem;
  color: var(--text-main);
  background: white;
  padding: 8px 16px;
  border-radius: 20px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.info-item i {
  color: var(--primary);
}

/* PROJECT SELECTOR MODAL */
.project-selector-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.project-selector-modal {
  background: white;
  border-radius: 16px;
  padding: 32px;
  max-width: 600px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
}

.modal-header {
  margin-bottom: 24px;
}

.modal-header h2 {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-main);
  margin-bottom: 8px;
}

.modal-header p {
  color: var(--text-muted);
  font-size: 0.95rem;
}

.modal-actions {
  margin-bottom: 32px;
}

.new-project-btn {
  width: 100%;
  padding: 16px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: var(--radius);
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  transition: background 0.2s;
}

.new-project-btn:hover {
  background: var(--primary-hover);
}

.projects-list h3 {
  font-size: 0.9rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-bottom: 16px;
  font-weight: 600;
}

.project-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.project-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.2s;
}

.project-item:hover {
  border-color: var(--primary);
  background: #f8fafc;
  transform: translateX(4px);
}

.project-info {
  flex: 1;
}

.project-info h4 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-main);
  margin-bottom: 4px;
}

.project-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.85rem;
}

.project-status {
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: 500;
  font-size: 0.75rem;
}

.status-draft {
  background: #e5e7eb;
  color: #4b5563;
}

.status-processing {
  background: #dbeafe;
  color: #1e40af;
}

.status-completed {
  background: #d1fae5;
  color: #065f46;
}

.status-failed {
  background: #fee2e2;
  color: #991b1b;
}

.project-date {
  color: var(--text-muted);
}

.project-item i {
  color: var(--text-muted);
  font-size: 0.9rem;
}

.no-projects {
  text-align: center;
  padding: 48px 24px;
}

.no-projects i {
  font-size: 4rem;
  color: #cbd5e1;
  margin-bottom: 16px;
}

.no-projects p {
  color: var(--text-main);
  font-size: 1rem;
  margin-bottom: 4px;
}

.no-projects .hint {
  color: var(--text-muted);
  font-size: 0.9rem;
}

/* LOADING OVERLAY */
.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.95);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.loading-spinner {
  text-align: center;
}

.loading-spinner i {
  font-size: 3rem;
  color: orange;
  margin-bottom: 16px;
}

.loading-spinner p {
  color: orange;
  font-size: 1rem;
}

/* Responsive Breakpoint */
/* Responsive for tablets and smaller */
@media (max-width: 900px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .project-selector-modal {
    padding: 24px;
    width: 95%;
  }

  /* Keep sidebar but make it narrower */
  .left-sidebar {
    width: 60px;
  }

  .nav-label {
    font-size: 10px;
  }

  .nav-item {
    padding: 10px 6px;
  }
}

/* Responsive for mobile */
/* Desktop - ensure normal layout */
@media (min-width: 1024px) {
  .preview-panel {
    display: block;
  }

  .preview-panel--fullfit {
    display: flex;
  }

  .preview-content {
    display: block;
    height: auto;
  }

  .preview-content--fullfit {
    display: flex;
    height: 100%;
  }

  /* Scene cards container - prevent flex stretching */
  .scene-cards-container {
    display: block !important;
    height: auto !important;
  }

  /* Storyboard grid - prevent stretching */
  .storyboard-grid {
    display: grid !important;
    align-items: start !important;
    grid-auto-rows: min-content !important;
    align-content: start !important;
    height: auto !important;
  }

  .storyboard-grid > div {
    align-self: start !important;
    height: auto !important;
    max-height: none !important;
  }

  /* Force SceneCard to not stretch */
  .storyboard-grid > div > * {
    height: auto !important;
    min-height: 0 !important;
  }
}

@media (max-width: 640px) {
  .simple-creator {
    overflow: auto; /* Allow scrolling on mobile */
  }

  .header-nav-tabs {
    padding: 0 8px;
  }

  .top-nav-tabs {
    height: 44px;
    gap: 2px;
  }

  .top-nav-item {
    min-height: 38px;
    padding: 0 12px;
    font-size: 0.75rem;
    gap: 5px;
    border-radius: 7px 7px 0 0;
  }

  .top-nav-item i {
    font-size: 0.875rem;
  }

  .main-container {
    flex-direction: column;
    height: auto; /* Allow content to extend beyond viewport */
    min-height: calc(100vh - 120px); /* Subtract header height including nav tabs */
    overflow-y: visible; /* Don't create nested scroll */
    margin-top: 0; /* Ensure no overlap */
  }

  .left-sidebar {
    width: 100%;
    height: auto;
    flex-direction: row;
    padding: 8px 12px;
    border-right: none;
    border-bottom: 1px solid #5a5a5a;
  }

  .sidebar-nav {
    flex-direction: row;
    justify-content: center;
    width: 100%;
    padding: 0;
  }

  .nav-item {
    flex: 0 0 auto;
    padding: 8px 12px;
    width: 60px;
    min-width: 60px;
    max-width: 60px;
  }

  .nav-item i {
    font-size: 18px;
  }

  .nav-label {
    display: none;
  }

  /* Storyboard header and actions */
  .storyboard-actions {
    flex: 1;
    justify-content: flex-end;
  }

  .storyboard-actions button,
  .storyboard-actions .cursor-pointer {
    font-size: 0.65rem;
    padding: 0.25rem 0.5rem;
    min-height: 28px;
  }

  .storyboard-actions i {
    font-size: 0.75rem;
  }

  .workspace {
    min-height: calc(100vh - 60px - 50px); /* Allow content to extend beyond viewport */
    height: auto;
    display: flex;
    flex-direction: column;
    overflow-y: visible; /* Scrolling happens at parent level */
    gap: 0; /* Remove gap between sections */
    padding-top: 8px; /* Add small padding to prevent content from touching sticky header */
  }

  .input-panel {
    order: 1;  /* Storyboard at top */
    height: auto;
    min-height: auto; /* Let content determine height */
    overflow-y: visible; /* Don't create nested scroll */
    flex-shrink: 0;
    padding-bottom: 12px; /* Add spacing at bottom of storyboard */
  }

  .preview-panel {
    /* Use display: contents to make children act as flex items of workspace */
    display: contents;
  }

  .preview-content {
    order: 2;  /* Preview content in middle */
    flex: 0 0 auto;
    min-height: auto; /* Let content determine height */
    overflow-y: visible;
    padding: 12px; /* Consistent padding all around */
    background-color: #f8fafc;
    background-image: radial-gradient(#e2e8f0 1px, transparent 1px);
    background-size: 20px 20px;
  }

  .timeline-section {
    order: 3;  /* Timeline at bottom */
    flex-shrink: 0;
  }

  /* Make preview area buttons smaller on mobile */
  .preview-action-buttons {
    gap: 0.25rem !important;
    margin-top: 0.5rem !important;
  }

  .preview-action-btn {
    height: 2rem !important;
    padding-left: 0.5rem !important;
    padding-right: 0.5rem !important;
    font-size: 0.75rem !important;
  }

  .preview-action-btn i {
    font-size: 0.7rem;
  }

  /* Make mode selection buttons smaller on mobile */
  .preview-mode-buttons {
    gap: 0.25rem !important;
    margin-bottom: 1rem !important;
  }

  .preview-mode-btn {
    height: 2rem !important;
    padding-left: 0.5rem !important;
    padding-right: 0.5rem !important;
    font-size: 0.75rem !important;
  }

  .preview-mode-btn svg {
    width: 0.875rem !important;
    height: 0.875rem !important;
  }

  /* Make trending button and input smaller on mobile */
  .trending-input {
    padding: 0.375rem 0.5rem !important;
    font-size: 0.75rem !important;
  }

  .trending-button {
    padding: 0.375rem 0.75rem !important;
    font-size: 0.75rem !important;
    gap: 0.25rem !important;
  }

  .trending-button i {
    font-size: 0.7rem !important;
  }
}

/* Aspect Ratio Dropdown Styles */
.aspect-ratio-dropdown [role="menuitem"]:hover {
  background: #374151 !important;
}

.aspect-ratio-dropdown [role="menuitem"].aspect-ratio-selected {
  background: #22c55e !important;
  border: 1px solid #16a34a;
}

.aspect-ratio-dropdown [role="menuitem"].aspect-ratio-selected:hover {
  background: #22c55e !important;
}

.aspect-ratio-trigger:hover {
  background: #374151;
}

/* Setting Dropdown Styles (Model & Visual Style) */
.setting-dropdown [role="menuitem"]:hover {
  background: #374151 !important;
}

.setting-dropdown [role="menuitem"].setting-selected {
  background: #22c55e !important;
  border: 1px solid #16a34a;
}

.setting-dropdown [role="menuitem"].setting-selected:hover {
  background: #22c55e !important;
}

.setting-dropdown-trigger:hover {
  background: #374151;
}

/* Effects Preset Dropdown Styles */
.effects-preset-dropdown [role="menuitem"]:hover {
  background: #374151 !important;
}

.effects-preset-trigger:hover {
  background: #374151;
}

/* Effect Input Flash Animation - Targets select dropdowns */
@keyframes effectInputFlash {
  0%, 100% {
    background-color: white;
    border-color: #d1d5db;
    box-shadow: none;
  }
  10%, 30%, 50%, 70%, 90% {
    background-color: #d1fae5;
    border-color: #22c55e;
    box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.2), 0 0 12px rgba(34, 197, 94, 0.4);
  }
  20%, 40%, 60%, 80% {
    background-color: white;
    border-color: #86efac;
    box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.1);
  }
}

:deep(select.effect-input-flash) {
  animation: effectInputFlash 2s ease-in-out !important;
  animation-iteration-count: 1;
}

/* Custom Range Slider Styles */
input[type="range"].slider {
  -webkit-appearance: none;
  appearance: none;
  background: transparent;
}

input[type="range"].slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: white;
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: transform 0.2s;
}

input[type="range"].slider::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}

input[type="range"].slider::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: white;
  cursor: pointer;
  border: none;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: transform 0.2s;
}

input[type="range"].slider::-moz-range-thumb:hover {
  transform: scale(1.1);
}

input[type="range"].slider::-webkit-slider-runnable-track {
  background: rgba(255, 255, 255, 0.3);
  border-radius: 4px;
}

input[type="range"].slider::-moz-range-track {
  background: rgba(255, 255, 255, 0.3);
  border-radius: 4px;
}

/* Custom Voice Cloning Styles */
.custom-voices-section {
  margin-bottom: 24px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border);
}

.custom-voices-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.custom-voices-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.btn-add-voice {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-add-voice:hover:not(:disabled) {
  background: var(--primary-dark);
  transform: translateY(-1px);
}

.btn-add-voice:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.custom-voices-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  color: var(--text-muted);
  font-size: 14px;
}

.custom-voices-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.custom-voice-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  background: white;
  border: 1px solid var(--border);
  border-radius: 8px;
  transition: all 0.2s;
  cursor: pointer;
}

.custom-voice-item:hover {
  border-color: var(--primary);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.custom-voice-selected {
  border-color: var(--primary);
  background: #f0f9ff;
}

.custom-voice-item .voice-info {
  flex: 1;
  min-width: 0;
}

.custom-voice-item .voice-name {
  display: block;
  font-weight: 600;
  color: var(--text-primary);
  font-size: 14px;
  margin-bottom: 4px;
}

.custom-voice-item .voice-description {
  display: block;
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.voice-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-delete {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid #ef4444;
  border-radius: 6px;
  color: #ef4444;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-delete:hover {
  background: #ef4444;
  color: white;
}

.no-voices {
  text-align: center;
  padding: 24px;
  color: var(--text-muted);
  font-size: 14px;
  font-style: italic;
}

/* Upload Modal Styles */
.upload-modal {
  background: white;
  border-radius: 12px;
  padding: 0;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.upload-modal-content {
  padding: 24px;
}

.upload-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #f0f9ff;
  border: 1px solid #3b82f6;
  border-radius: 8px;
  color: #1e40af;
  font-size: 13px;
  margin-bottom: 20px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--text-primary);
  font-size: 14px;
}

.form-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 14px;
  transition: all 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  transition: all 0.2s;
}

.form-textarea:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-file-input {
  width: 100%;
  padding: 10px;
  border: 2px dashed var(--border);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.form-file-input:hover {
  border-color: var(--primary);
  background: #f9fafb;
}

.form-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-muted);
}

.upload-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #fef2f2;
  border: 1px solid #ef4444;
  border-radius: 8px;
  color: #dc2626;
  font-size: 13px;
}

.btn-cancel {
  padding: 10px 20px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-primary);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.btn-cancel:hover {
  background: #f9fafb;
  border-color: var(--text-primary);
}

</style>
