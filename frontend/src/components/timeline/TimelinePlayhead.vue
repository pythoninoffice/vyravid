<template>
  <div
    class="playhead"
    :style="{ left: `${leftPosition}px` }"
  >
    <div
      class="playhead-handle"
      :class="{ dragging: isDragging }"
      @mousedown="handleMouseDown"
    ></div>
    <div class="playhead-line"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

interface Props {
  currentTime: number
  pixelsPerSecond: number
  offsetLeft?: number
  maxDuration?: number
}

const props = withDefaults(defineProps<Props>(), {
  offsetLeft: 72,
  maxDuration: Infinity
})

const emit = defineEmits<{
  'update:currentTime': [time: number]
  'seek': [time: number]
}>()

const isDragging = ref(false)

const leftPosition = computed(() => {
  return props.offsetLeft + props.currentTime * props.pixelsPerSecond
})

const handleMouseDown = (e: MouseEvent) => {
  e.preventDefault()
  e.stopPropagation()
  isDragging.value = true

  const container = (e.target as HTMLElement).closest('.timeline-container')
  if (!container) return

  const handleMouseMove = (moveEvent: MouseEvent) => {
    if (!container) return

    // Get mouse position relative to container
    const containerRect = container.getBoundingClientRect()
    const mouseX = moveEvent.clientX - containerRect.left

    // Subtract the offset (track label width) and add scroll position
    const timelineX = Math.max(0, mouseX - props.offsetLeft + container.scrollLeft)

    // Calculate new time from position
    let newTime = timelineX / props.pixelsPerSecond

    // Clamp to valid range
    newTime = Math.max(0, Math.min(newTime, props.maxDuration))

    emit('update:currentTime', newTime)
    emit('seek', newTime)
  }

  const handleMouseUp = () => {
    isDragging.value = false
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleMouseUp)
  }

  document.addEventListener('mousemove', handleMouseMove)
  document.addEventListener('mouseup', handleMouseUp)

  // Trigger initial position update
  handleMouseMove(e)
}
</script>

<style scoped>
.playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  pointer-events: none;
  z-index: 50;
}

.playhead-handle {
  position: absolute;
  top: 0;
  left: -6px;
  width: 14px;
  height: 14px;
  background: #ef4444;
  border: 2px solid #ffffff;
  border-radius: 2px;
  pointer-events: auto;
  cursor: grab;
  transition: transform 0.1s ease;
}

.playhead-handle:hover {
  transform: scale(1.2);
}

.playhead-handle.dragging {
  cursor: grabbing;
  transform: scale(1.15);
}

.playhead-line {
  position: absolute;
  top: 14px;
  left: 0;
  width: 2px;
  height: calc(100% - 14px);
  background: #ef4444;
  opacity: 0.8;
}
</style>
