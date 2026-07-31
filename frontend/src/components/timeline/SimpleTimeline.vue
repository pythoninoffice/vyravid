<template>
  <div class="simple-timeline" :class="timelineInstanceClass">
    <div class="timeline-header">
      <div class="timeline-header-left">
        <h3>Timeline</h3>
        <button @click="togglePlayPause" class="play-pause-btn" title="Play/Pause (Space)">
          <svg v-if="!isPlaying" xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z"/>
          </svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="currentColor">
            <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/>
          </svg>
        </button>
        <span class="time-display">{{ formatTime(currentTime) }} / {{ formatTime(totalDuration) }}</span>
      </div>
      <div class="timeline-header-right">
        <!-- Volume control -->
        <div class="volume-controls">
          <button class="volume-btn" @click="toggleMute" :title="isMuted ? 'Unmute' : 'Mute'">
            <svg v-if="!isMuted && volume > 0.5" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
            </svg>
            <svg v-else-if="!isMuted && volume > 0" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M18.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z"/>
            </svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>
            </svg>
          </button>
          <input
            type="range"
            v-model.number="volume"
            min="0"
            max="1"
            step="0.01"
            class="volume-slider"
            @input="onVolumeInput"
            title="Volume"
          />
        </div>

        <!-- Zoom control -->
        <div class="zoom-controls">
          <label>Zoom:</label>
          <input
            type="range"
            v-model.number="zoomLevel"
            :min="minZoom"
            :max="maxZoom"
            step="0.1"
            class="zoom-slider"
          />
          <span class="zoom-label">{{ zoomLevel.toFixed(2) }}x</span>
        </div>
      </div>
    </div>

    <div class="timeline-container" ref="timelineContainerRef" @click="handleTimelineClick">
      <TimelineRuler
        :total-duration="extendedDuration"
        :pixels-per-second="pixelsPerSecond"
      />

      <!-- Text Layers Track hidden for now -->

      <!-- Image Scenes Track -->
      <div class="track-with-label">
        <div class="track-label">Images</div>
        <TimelineTrack
          :clips="sceneClips"
          :total-duration="extendedDuration"
          :pixels-per-second="pixelsPerSecond"
          :selected-clip-id="selectedClipId"
          @clip-update="handleClipUpdate"
          @clip-click="handleClipClick"
          @clip-delete="handleClipDelete"
        />
      </div>

      <!-- Audio Track -->
      <div v-if="audioClip" class="track-with-label audio-track-container">
        <div class="track-label">Audio</div>
        <TimelineTrack
          :clips="[audioClip]"
          :total-duration="extendedDuration"
          :pixels-per-second="pixelsPerSecond"
          :selected-clip-id="selectedClipId"
          @clip-update="handleClipUpdate"
          @clip-click="handleClipClick"
          class="audio-track"
        />
      </div>

      <TimelinePlayhead
        v-if="currentTime !== undefined"
        :current-time="currentTime"
        :pixels-per-second="pixelsPerSecond"
        :offset-left="80"
        :max-duration="totalDuration"
        @seek="handlePlayheadSeek"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import TimelineRuler from './TimelineRuler.vue'
import TimelineTrack from './TimelineTrack.vue'
import TimelinePlayhead from './TimelinePlayhead.vue'
import { useTimelineZoom } from '@/composables/timeline/useTimelineZoom'
import { useTimelineInteract } from '@/composables/timeline/useTimelineInteract'
import type { TimelineClip } from './TimelineClip.vue'

export interface SimpleScene {
  id: string
  description: string
  prompt: string
  start_time?: number
  end_time?: number
  generatedImage?: {
    id?: string
    url: string
    width: number
    height: number
    aspectRatio: string
  }
  isGenerating: boolean
  generationProgress: number
  character_ids?: string[]
  [key: string]: any  // Allow additional properties
}

export interface TextLayerItem {
  id: string
  text: string
  startTime: number
  endTime: number
}

interface Props {
  scenes: SimpleScene[]
  audioDuration?: number
  audioUrl?: string
  currentTime?: number
  textLayers?: TextLayerItem[]
  selectedTextLayerId?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  audioDuration: 0,
  audioUrl: '',
  currentTime: undefined
})

const emit = defineEmits<{
  'update:scenes': [scenes: SimpleScene[]]
  'seek': [time: number]
  'delete-scene': [sceneId: string]
  'add-text-layer': []
  'update-text-layer': [id: string, updates: { startTime?: number; endTime?: number }]
  'select-text-layer': [id: string | null]
  'play': []
  'pause': []
}>()

// Timeline zoom
const {
  zoomLevel,
  pixelsPerSecond,
  minZoom,
  maxZoom
} = useTimelineZoom({
  initialZoom: 0.7,
  basePixelsPerSecond: 15, //width of each second on timeline
  minZoom: 0.1,
  maxZoom: 4
})

// Timeline container ref
const timelineContainerRef = ref<HTMLElement | null>(null)
const timelineInstanceClass = `simple-timeline-${Math.random().toString(36).slice(2, 10)}`
const timelineClipSelector = `.${timelineInstanceClass} .clip`

// Selected clip
const selectedClipId = ref<string | number | null>(null)

// Playback state
const isPlaying = ref(false)
const audioElement = ref<HTMLAudioElement | null>(null)
let animationFrameId: number | null = null

// Volume state
const volume = ref(1)
const isMuted = ref(false)
const _volumeBeforeMute = ref(1)

const onVolumeInput = () => {
  isMuted.value = volume.value === 0
  if (audioElement.value) audioElement.value.volume = volume.value
}

const toggleMute = () => {
  if (isMuted.value) {
    volume.value = _volumeBeforeMute.value || 1
    isMuted.value = false
  } else {
    _volumeBeforeMute.value = volume.value
    volume.value = 0
    isMuted.value = true
  }
  if (audioElement.value) audioElement.value.volume = volume.value
}

// Calculate total duration
const totalDuration = computed(() => {
  // Calculate max end time from scenes
  let maxEndTime = 10 // Default minimum duration

  if (props.scenes.length > 0) {
    maxEndTime = Math.max(
      ...props.scenes.map(scene => scene.end_time || 0)
    )

    // Convert milliseconds to seconds if needed
    if (maxEndTime > 1000) {
      maxEndTime = maxEndTime / 1000
    }

    maxEndTime = Math.max(maxEndTime, 10)
  }

  // Return the maximum of audio duration and scenes duration
  // This allows the timeline to extend beyond audio if scenes go further
  if (props.audioDuration && props.audioDuration > 0) {
    return Math.max(props.audioDuration, maxEndTime)
  }

  return maxEndTime
})

// Extended duration for track width - adds 50% extra space for dragging clips beyond current duration
const extendedDuration = computed(() => {
  return totalDuration.value * 1.5
})

// Convert scenes to clips
const sceneClips = computed((): TimelineClip[] => {
  // Detect if timestamps are in milliseconds by checking if ANY scene has large values
  const hasMillisecondTimestamps = props.scenes.some(scene =>
    (scene.start_time && scene.start_time > 1000) ||
    (scene.end_time && scene.end_time > 1000)
  )

  return props.scenes.map((scene, index) => {
    let startTime = scene.start_time ?? index * 3
    let endTime = scene.end_time ?? startTime + 3

    // Convert milliseconds to seconds if detected
    if (hasMillisecondTimestamps) {
      startTime = startTime / 1000
      endTime = endTime / 1000
    }

    const duration = endTime - startTime

    // Check if this scene has a video (animatedVideo property)
    const isVideo = !!scene.animatedVideo?.url
    const mediaUrl = isVideo ? scene.animatedVideo.url : (scene.generatedImage?.url || '')
    // For videos, prefer the generatedImage (source image) as thumbnail over the video URL
    const thumbnailUrl = isVideo
      ? (scene.generatedImage?.url || scene.animatedVideo.thumbnailUrl || '')
      : (scene.generatedImage?.url || '')

    const clipId = scene.id || `scene-${index}`

    return {
      id: clipId,
      type: isVideo ? 'video' : 'image',
      name: `Scene ${index + 1}`,
      startTime: startTime,
      duration: duration,
      src: mediaUrl,
      thumbnail: thumbnailUrl,
      image_id: scene.generatedImage?.id || clipId
    }
  })
})

// Convert audio to clip
const audioClip = computed((): TimelineClip | null => {
  if (!props.audioUrl || !props.audioDuration || props.audioDuration <= 0) {
    return null
  }

  return {
    id: 'audio-track',
    type: 'audio',
    name: 'Audio',
    startTime: 0,
    duration: props.audioDuration,
    src: props.audioUrl,
    thumbnail: '', // Audio doesn't need thumbnail
    image_id: ''
  }
})

// DEBUG: Log audio props and computed result
watch(() => ({ url: props.audioUrl, duration: props.audioDuration }), (newVal) => {
  console.log('🎵 [SimpleTimeline] Audio props:', newVal)
  console.log('🎵 [SimpleTimeline] audioClip computed result:', audioClip.value ? 'VALID ✅' : 'NULL ❌')
  if (!audioClip.value && (newVal.url || newVal.duration)) {
    console.warn('⚠️ Audio props provided but audioClip is null. Check validation logic.')
  }
}, { immediate: true, deep: true })

// Handle clip updates
const handleClipUpdate = (clipId: string | number, updates: { startTime?: number; duration?: number }) => {
  const sceneIndex = props.scenes.findIndex((s, index) => (s.id || `scene-${index}`) === clipId)
  if (sceneIndex === -1) return

  const updatedScenes = [...props.scenes]
  const scene = { ...updatedScenes[sceneIndex] }
  scene.id = scene.id || String(clipId)

  // Check if original timestamps were in milliseconds
  const isInMilliseconds = (scene.start_time ?? 0) > 1000 || (scene.end_time ?? 0) > 1000

  if (updates.startTime !== undefined) {
    // Calculate current duration before updating start time
    const oldStartTime = scene.start_time ?? sceneIndex * 3
    const oldEndTime = scene.end_time ?? (oldStartTime + (scene.target_duration || 3))
    const duration = Math.max(oldEndTime - oldStartTime, 0.1)

    // Convert seconds back to milliseconds if needed
    scene.start_time = isInMilliseconds ? updates.startTime * 1000 : updates.startTime

    // Update end_time to maintain the same duration (only if duration wasn't explicitly updated)
    if (updates.duration === undefined) {
      scene.end_time = scene.start_time + duration
    }
  }

  if (updates.duration !== undefined) {
    let startTime = scene.start_time ?? sceneIndex * 3
    // If working with milliseconds, ensure we're in the right unit
    if (isInMilliseconds && startTime < 1000) {
      startTime = startTime * 1000
      scene.start_time = startTime
    }
    scene.end_time = startTime + (isInMilliseconds ? updates.duration * 1000 : updates.duration)
  }

  updatedScenes[sceneIndex] = scene

  // Automatically re-order scenes by start_time
  updatedScenes.sort((a, b) => {
    const aStart = a.start_time ?? 0
    const bStart = b.start_time ?? 0
    return aStart - bStart
  })

  emit('update:scenes', updatedScenes)
}

// Handle clip click
const handleClipClick = (clip: TimelineClip) => {
  selectedClipId.value = selectedClipId.value === clip.id ? null : clip.id
}

// Handle clip delete
const handleClipDelete = (clipId: string | number) => {
  emit('delete-scene', String(clipId))
}

// Handle playhead seek
const handlePlayheadSeek = (time: number) => {
  emit('seek', time)
}

// Handle timeline click to seek
const handleTimelineClick = (event: MouseEvent) => {
  if (!timelineContainerRef.value) return

  // Don't seek if clicking on clips or interactive elements
  const target = event.target as HTMLElement
  if (target.classList.contains('clip') ||
      target.closest('.clip') ||
      target.classList.contains('playhead-handle') ||
      target.closest('.playhead-handle')) {
    return
  }

  // Get click position relative to timeline container
  const rect = timelineContainerRef.value.getBoundingClientRect()
  const clickX = event.clientX - rect.left

  // Account for track label width (80px) and scroll position
  const trackLabelWidth = 80
  const timelineX = Math.max(0, clickX - trackLabelWidth + timelineContainerRef.value.scrollLeft)

  // Convert to time using pixels per second
  const newTime = timelineX / pixelsPerSecond.value

  // Clamp to valid range
  const clampedTime = Math.max(0, Math.min(newTime, totalDuration.value))

  emit('seek', clampedTime)
}

// Format time for display (MM:SS.ms)
const formatTime = (seconds: number) => {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  const ms = Math.floor((seconds % 1) * 100)
  return `${mins}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(2, '0')}`
}

// ========================================
// PLAYBACK CONTROLS
// ========================================
// NOTE: Video playback/preview functionality will be added in the future
// Currently only supports audio playback

// Sync audio playback during animation
const syncAudioPlayback = () => {
  if (!audioElement.value || !props.audioUrl) return

  const audioTime = props.currentTime ?? 0

  // Check if audio should be playing (within duration range)
  const shouldBePlaying = isPlaying.value && audioTime >= 0 && audioTime < totalDuration.value

  if (shouldBePlaying) {
    // Start playing if not already playing
    if (audioElement.value.paused) {
      audioElement.value.currentTime = Math.max(0, audioTime)
      audioElement.value.play().catch(err => {
        console.warn('Audio play error:', err.message)
      })
    } else {
      // Sync time if drift is more than 0.1 seconds
      const drift = Math.abs(audioElement.value.currentTime - audioTime)
      if (drift > 0.1) {
        audioElement.value.currentTime = Math.max(0, audioTime)
      }
    }
  } else {
    // Pause if playing
    if (!audioElement.value.paused) {
      audioElement.value.pause()
    }
  }
}

// Play function
const play = () => {
  isPlaying.value = true
  emit('play')

  const frameRate = 30
  let lastTime = performance.now()

  const animate = (currentPerformanceTime: number) => {
    if (!isPlaying.value) return

    const deltaTime = (currentPerformanceTime - lastTime) / 1000
    lastTime = currentPerformanceTime

    // Update current time via emit (parent component manages currentTime)
    const newTime = (props.currentTime ?? 0) + deltaTime

    // Sync audio playback
    syncAudioPlayback()

    // Check if reached end
    if (newTime >= totalDuration.value) {
      stop()
      return
    }

    // Emit the new time
    emit('seek', newTime)

    animationFrameId = requestAnimationFrame(animate)
  }

  animationFrameId = requestAnimationFrame(animate)
}

// Pause function
const pause = () => {
  isPlaying.value = false
  emit('pause')

  // Cancel animation frame
  if (animationFrameId !== null) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }

  // Pause audio
  if (audioElement.value) {
    audioElement.value.pause()
  }
}

// Stop function
const stop = () => {
  isPlaying.value = false

  // Cancel animation frame
  if (animationFrameId !== null) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }

  // Stop audio
  if (audioElement.value) {
    audioElement.value.pause()
    audioElement.value.currentTime = 0
  }

  // Reset to beginning
  emit('seek', 0)
}

// Toggle play/pause
const togglePlayPause = () => {
  if (isPlaying.value) {
    pause()
  } else {
    play()
  }
}

// Setup interact.js for drag/resize
const { setupInteract } = useTimelineInteract({
  clipSelector: timelineClipSelector,
  pixelsPerSecond: pixelsPerSecond,
  dragRestriction: 'parent', // Keep clips within their track bounds
  onDragEnd: (clipId, finalStartTime) => {
    handleClipUpdate(clipId, { startTime: finalStartTime })
  },
  onResizeEnd: (clipId, finalDuration, finalStartTime) => {
    handleClipUpdate(clipId, {
      startTime: finalStartTime,
      duration: finalDuration
    })
  }
})

// Watch for zoom changes and re-initialize interact.js
watch(pixelsPerSecond, async () => {
  await nextTick()
  // Re-setup interact.js after clips re-render with new positions
  setupInteract()
})

// Watch for scene changes and re-initialize interact.js
watch(() => props.scenes, async () => {
  await nextTick()

  // Clean up any lingering transforms/attributes from previous drag operations
  document.querySelectorAll(timelineClipSelector).forEach(el => {
    const element = el as HTMLElement
    element.style.transform = ''
    element.removeAttribute('data-x')
    element.removeAttribute('data-resize-x')
    element.removeAttribute('data-resize-width')
    element.removeAttribute('data-dragging')
    element.removeAttribute('data-resizing')
  })

  // Re-setup interact.js after clips re-render
  setupInteract()
}, { deep: true })

// Create audio element when audioUrl is available
watch(() => props.audioUrl, (newUrl) => {
  // Clean up existing audio element
  if (audioElement.value) {
    audioElement.value.pause()
    audioElement.value = null
  }

  // Create new audio element if URL is provided
  if (newUrl) {
    const audio = new Audio()
    audio.src = newUrl
    audio.crossOrigin = 'anonymous'
    audio.preload = 'auto'

    audio.volume = volume.value

    audio.onloadeddata = () => {
      console.log('🔊 Audio loaded for timeline playback')
    }

    audio.onerror = (err) => {
      console.error('🔊 Audio load error:', err)
    }

    audioElement.value = audio
    audio.load()
  }
}, { immediate: true })

// ========================================
// TEXT LAYER DRAG / RESIZE
// ========================================
interface TextLayerDragState {
  id: string
  type: 'move' | 'resize-start' | 'resize-end'
  startClientX: number
  origStart: number
  origEnd: number
}
let _tlDrag: TextLayerDragState | null = null

function startTextLayerBlockDrag(e: MouseEvent, tl: TextLayerItem, type: 'move' | 'resize-start' | 'resize-end') {
  _tlDrag = { id: tl.id, type, startClientX: e.clientX, origStart: tl.startTime, origEnd: tl.endTime }
  const dur = tl.endTime - tl.startTime
  function onMove(ev: MouseEvent) {
    if (!_tlDrag) return
    const dx = (ev.clientX - _tlDrag.startClientX) / pixelsPerSecond.value
    if (_tlDrag.type === 'move') {
      const newStart = Math.max(0, Math.min(totalDuration.value - dur, _tlDrag.origStart + dx))
      emit('update-text-layer', _tlDrag.id, { startTime: newStart, endTime: newStart + dur })
    } else if (_tlDrag.type === 'resize-start') {
      const newStart = Math.max(0, Math.min(_tlDrag.origEnd - 0.25, _tlDrag.origStart + dx))
      emit('update-text-layer', _tlDrag.id, { startTime: newStart })
    } else {
      const newEnd = Math.max(_tlDrag.origStart + 0.25, Math.min(totalDuration.value, _tlDrag.origEnd + dx))
      emit('update-text-layer', _tlDrag.id, { endTime: newEnd })
    }
  }
  function onUp() {
    _tlDrag = null
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

defineExpose({ play, pause, togglePlayPause, isPlaying })

// Cleanup on unmount
onBeforeUnmount(() => {
  // Stop playback
  if (isPlaying.value) {
    stop()
  }

  // Clean up audio element
  if (audioElement.value) {
    audioElement.value.pause()
    audioElement.value = null
  }
})
</script>

<style scoped>
.simple-timeline {
  background: #0f172a;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #334155;
  margin-top: 0;
}

@media (min-width: 1024px) {
  .simple-timeline {
    margin-top: 8px;
  }
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
  border-bottom: 1px solid #334155;
}

@media (min-width: 1024px) {
  .timeline-header {
    padding: 12px 16px;
  }
}

.timeline-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (min-width: 1024px) {
  .timeline-header-left {
    gap: 12px;
  }
}

.timeline-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #f1f5f9;
}

@media (min-width: 1024px) {
  .timeline-header h3 {
    font-size: 16px;
  }
}

.play-pause-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: #334155;
  border: 1px solid #475569;
  border-radius: 4px;
  color: #FB3333;
  cursor: pointer;
  transition: all 0.2s ease;
}

.play-pause-btn:hover {
  background: #475569;
  border-color: #60a5fa;
  transform: translateY(-1px);
}

.play-pause-btn:active {
  transform: translateY(0);
}

.time-display {
  font-size: 13px;
  color: #cbd5e1;
  font-weight: 600;
  font-family: 'Monaco', 'Courier New', monospace;
  min-width: 130px;
}

.timeline-header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.volume-controls {
  display: flex;
  align-items: center;
  gap: 6px;
}

.volume-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  padding: 0;
  border-radius: 4px;
  transition: color 0.15s;
}

.volume-btn:hover {
  color: #f1f5f9;
}

.volume-slider {
  width: 80px;
  height: 4px;
  background: #334155;
  border-radius: 2px;
  outline: none;
  -webkit-appearance: none;
  appearance: none;
}

.volume-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 12px;
  height: 12px;
  background: #94a3b8;
  border-radius: 50%;
  cursor: pointer;
}

.volume-slider::-moz-range-thumb {
  width: 12px;
  height: 12px;
  background: #94a3b8;
  border-radius: 50%;
  cursor: pointer;
  border: none;
}

.zoom-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.zoom-controls label {
  font-size: 16px;
  color: white;
  font-weight: 500;
}

.zoom-slider {
  width: 120px;
  height: 4px;
  background: #334155;
  border-radius: 2px;
  outline: none;
  -webkit-appearance: none;
  appearance: none;
}

.zoom-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  background: #60a5fa;
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid #1e293b;
}

.zoom-slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  background: #60a5fa;
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid #1e293b;
}

.zoom-label {
  font-size: 12px;
  color: #cbd5e1;
  font-weight: 600;
  min-width: 45px;
  text-align: right;
}

.timeline-container {
  position: relative;
  overflow-x: auto;
  overflow-y: visible;
  background: #1e293b;
}

/* Track with label */
.track-with-label {
  display: flex;
  align-items: flex-start;
  border-bottom: 1px solid #334155;
}

.track-label {
  flex-shrink: 0;
  width: 80px;
  padding: 16px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  background: #0f172a;
  border-right: 1px solid #334155;
  display: flex;
  align-items: center;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Audio track specific styling */
.audio-track-container {
  background: #1e293b;
}

.audio-track-container .track-label {
  color: #60a5fa;
}

/* Text layers track */
.text-track-container {
  background: #1e293b;
}

.text-track-label {
  flex-direction: column !important;
  gap: 4px;
  color: #f97316 !important;
  padding: 8px 12px !important;
}

.add-text-btn {
  background: #334155;
  border: 1px solid #475569;
  border-radius: 3px;
  color: #f97316;
  font-size: 14px;
  line-height: 1;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s;
}

.add-text-btn:hover {
  background: #475569;
}

.text-track-content {
  position: relative;
  height: 44px;
  flex: 1;
}

.text-layer-block {
  position: absolute;
  top: 6px;
  bottom: 6px;
  border-radius: 3px;
  display: flex;
  align-items: center;
  overflow: hidden;
  cursor: pointer;
  user-select: none;
}

.tl-label {
  color: #fff;
  font-size: 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  padding: 0 6px;
  pointer-events: none;
}

.tl-resize-handle {
  flex-shrink: 0;
  width: 6px;
  height: 100%;
  background: rgba(0, 0, 0, 0.35);
  cursor: ew-resize;
}

.tl-resize-left {
  border-radius: 3px 0 0 3px;
}

.tl-resize-right {
  border-radius: 0 3px 3px 0;
}

/* Make audio clips visually distinct with a waveform-like appearance */
.audio-track :deep(.clip) {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  border: 1px solid #60a5fa;
  opacity: 0.85;
}

.audio-track :deep(.clip):hover {
  opacity: 1;
  border-color: #93c5fd;
}

.audio-track :deep(.clip.selected) {
  border-color: #60a5fa;
  box-shadow: 0 0 0 2px #3b82f6;
}
</style>

<style>
/* Unscoped scrollbar styles (webkit scrollbar pseudo-elements don't work with scoped styles) */
.simple-timeline .timeline-container::-webkit-scrollbar {
  height: 10px !important;
  width: 10px !important;
}

.simple-timeline .timeline-container::-webkit-scrollbar-track {
  background: #1e293b !important;
}

.simple-timeline .timeline-container::-webkit-scrollbar-thumb {
  background: #334155 !important;
  border-radius: 5px !important;
}

.simple-timeline .timeline-container::-webkit-scrollbar-thumb:hover {
  background: #476959 !important;
}
</style>
