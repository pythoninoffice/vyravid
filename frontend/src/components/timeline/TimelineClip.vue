<template>
  <div
    class="clip"
    :class="[
      `${clip.type}-clip`,
      { selected: selected, interactive: interactive }
    ]"
    :data-clip-id="clip.id"
    :style="{
      left: `${clip.startTime * pixelsPerSecond}px`,
      width: `${clip.duration * pixelsPerSecond}px`,
      backgroundImage: (clip.type !== 'video' && hasBackground) ? `url(${getBackgroundImage()})` : 'none'
    }"
    @click="handleClick"
  >
    <!-- Video Preview (for video clips) -->
    <video
      v-if="clip.type === 'video' && clip.src"
      :src="clip.src"
      class="video-preview"
      preload="metadata"
      muted
      playsinline
      @loadeddata="handleVideoLoaded"
    />

    <!-- Audio Waveform Visualization -->
    <AudioWaveform
      v-if="clip.type === 'audio' && clip.src"
      :audio-url="clip.src"
      :width="clip.duration * pixelsPerSecond"
      :height="60"
      wave-color="#60a5fa"
      background-color="#0f172a"
      class="waveform-overlay"
    />

    <span class="clip-name">{{ displayName }}</span>

    <!-- Video Indicator Icon -->
    <div v-if="clip.type === 'video'" class="video-indicator">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="white">
        <path d="M8 5v14l11-7z"/>
      </svg>
    </div>

    <!-- Delete Button (only for image/video clips) -->
    <button
      v-if="interactive && (clip.type === 'image' || clip.type === 'video')"
      class="delete-btn"
      @click.stop="handleDelete"
      title="Delete scene"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="18" y1="6" x2="6" y2="18"></line>
        <line x1="6" y1="6" x2="18" y2="18"></line>
      </svg>
    </button>

    <template v-if="interactive">
      <div class="resize-handle resize-left"></div>
      <div class="resize-handle resize-right"></div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AudioWaveform from './AudioWaveform.vue'

export interface TimelineClip {
  id: string | number
  type: 'video' | 'image' | 'audio' | 'text' | 'shape'
  name: string
  startTime: number
  duration: number
  src?: string
  thumbnail?: string
  image_id?: string
  text?: string
}

interface Props {
  clip: TimelineClip
  pixelsPerSecond: number
  selected?: boolean
  interactive?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  selected: false,
  interactive: true
})

const emit = defineEmits<{
  click: [clip: TimelineClip, event: MouseEvent]
  'update:startTime': [startTime: number]
  'update:duration': [duration: number]
  delete: [clipId: string | number]
}>()

const displayName = computed(() => {
  if (props.clip.type === 'text' && props.clip.text) {
    return props.clip.text
  }
  return props.clip.name
})

const hasBackground = computed(() => {
  return (props.clip.type === 'image' || props.clip.type === 'video') &&
         (props.clip.src || props.clip.thumbnail)
})

const getBackgroundImage = () => {
  // For videos, use thumbnail (which should be the source image)
  if (props.clip.type === 'video') {
    return props.clip.thumbnail || props.clip.src || ''
  }
  // For images, use src or fall back to thumbnail
  return props.clip.src || props.clip.thumbnail || ''
}

const handleClick = (event: MouseEvent) => {
  emit('click', props.clip, event)
}

const handleDelete = () => {
  emit('delete', props.clip.id)
}

const handleVideoLoaded = (event: Event) => {
  const video = event.target as HTMLVideoElement
  // Seek to first frame to show preview
  video.currentTime = 0.1
}
</script>

<style scoped>
.clip {
  position: absolute;
  height: 100%;
  border-radius: 4px;
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  padding: 0 8px;
  background-size: auto 100%;
  background-position: left center;
  background-repeat: repeat-x;
  border: 1px solid rgba(255, 255, 255, 0.1);
  transition: all 0.15s ease;
  overflow: hidden;
}

.clip.interactive {
  cursor: grab;
}

.clip.interactive:active {
  cursor: grabbing;
}

.image-clip {
  background-color: #3b82f6;
  border-color: #60a5fa;
}

.video-clip {
  background-color: #8b5cf6;
  border-color: #a78bfa;
}

.audio-clip {
  background-color: #10b981;
  border-color: #34d399;
}

.text-clip {
  background-color: #f59e0b;
  border-color: #fbbf24;
}

.shape-clip {
  background-color: #ef4444;
  border-color: #f87171;
}

.clip.selected {
  border-color: #60a5fa;
  border-width: 2px;
  box-shadow: 0 0 0 2px rgba(96, 165, 250, 0.3);
}

.clip-name {
  font-size: 12px;
  font-weight: 500;
  color: white;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
  pointer-events: none;
  position: relative;
  z-index: 2;
}

.video-indicator {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(0, 0, 0, 0.6);
  border-radius: 50%;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  z-index: 3;
}

.video-indicator svg {
  margin-left: 2px; /* Slight offset to center the play triangle */
}

.delete-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(239, 68, 68, 0.9);
  border: 1px solid rgba(248, 113, 113, 0.8);
  border-radius: 3px;
  color: white;
  cursor: pointer;
  opacity: 0;
  transition: all 0.2s ease;
  z-index: 20;
  padding: 0;
}

.clip:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  background: rgba(220, 38, 38, 1);
  border-color: rgba(248, 113, 113, 1);
  transform: scale(1.1);
}

.delete-btn:active {
  transform: scale(0.95);
}

.resize-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 8px;
  cursor: ew-resize;
  z-index: 10;
}

.resize-handle:hover {
  background: rgba(96, 165, 250, 0.5);
}

.resize-left {
  left: 0;
  cursor: w-resize;
}

.resize-right {
  right: 0;
  cursor: e-resize;
}

.video-preview {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  pointer-events: none;
  z-index: 1;
  opacity: 1;
}

.waveform-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 1;
}

.audio-clip {
  background: #1e293b !important; /* Dark background so waveform is visible */
}
</style>
