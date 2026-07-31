<template>
  <div class="track">
    <div v-if="showLabel" class="track-label">
      <span class="track-name">{{ trackLabel }}</span>
    </div>
    <div
      class="track-content"
      :style="{ width: `${totalDuration * pixelsPerSecond}px` }"
    >
      <TimelineClip
        v-for="clip in clips"
        :key="clip.id"
        :clip="clip"
        :pixels-per-second="pixelsPerSecond"
        :selected="selectedClipId === clip.id"
        :interactive="interactive"
        @click="handleClipClick"
        @update:start-time="(newStartTime) => handleStartTimeUpdate(clip.id, newStartTime)"
        @update:duration="(newDuration) => handleDurationUpdate(clip.id, newDuration)"
        @delete="handleClipDelete"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import TimelineClip, { type TimelineClip as Clip } from './TimelineClip.vue'

interface Props {
  clips: Clip[]
  totalDuration: number
  pixelsPerSecond: number
  trackLabel?: string
  showLabel?: boolean
  interactive?: boolean
  selectedClipId?: string | number | null
}

withDefaults(defineProps<Props>(), {
  trackLabel: 'Track',
  showLabel: false,
  interactive: true,
  selectedClipId: null
})

const emit = defineEmits<{
  'clip-update': [clipId: string | number, updates: { startTime?: number; duration?: number }]
  'clip-click': [clip: Clip, event: MouseEvent]
  'clip-delete': [clipId: string | number]
}>()

const handleStartTimeUpdate = (clipId: string | number, newStartTime: number) => {
  emit('clip-update', clipId, { startTime: newStartTime })
}

const handleDurationUpdate = (clipId: string | number, newDuration: number) => {
  emit('clip-update', clipId, { duration: newDuration })
}

const handleClipClick = (clip: Clip, event: MouseEvent) => {
  emit('clip-click', clip, event)
}

const handleClipDelete = (clipId: string | number) => {
  emit('clip-delete', clipId)
}
</script>

<style scoped>
.track {
  display: flex;
  border-bottom: 1px solid #334155;
  background: #1e293b;
  min-height: 30px;
}

.track-label {
  display: flex;
  align-items: center;
  min-width: 72px;
  padding: 0 12px;
  background: #0f172a;
  border-right: 1px solid #334155;
}

.track-name {
  font-size: 12px;
  font-weight: 600;
  color: #cbd5e1;
  white-space: nowrap;
}

.track-content {
  position: relative;
  flex: 1;
  min-height: 50px;
  background: repeating-linear-gradient(
    90deg,
    transparent,
    transparent 99px,
    rgba(100, 116, 139, 0.1) 99px,
    rgba(100, 116, 139, 0.1) 100px
  );
}
</style>
