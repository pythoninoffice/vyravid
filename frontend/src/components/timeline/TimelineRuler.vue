<template>
  <div
    class="time-ruler"
    :style="{ minWidth: `${totalWidth}px` }"
  >
    <!-- 0s marker -->
    <div class="second-marker" :style="{ left: `${offsetLeft}px` }">0s</div>
    <!-- Other time markers at intervals -->
    <div
      v-for="i in markerCount"
      :key="i"
      class="second-marker"
      :style="{ left: `${offsetLeft + i * markerInterval * pixelsPerSecond}px` }"
    >
      {{ i * markerInterval }}s
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  totalDuration: number
  pixelsPerSecond: number
  offsetLeft?: number
}

const props = withDefaults(defineProps<Props>(), {
  offsetLeft: 72
})

const totalWidth = computed(() => {
  return props.offsetLeft + props.totalDuration * props.pixelsPerSecond
})

// Calculate appropriate marker interval based on duration and zoom level
const markerInterval = computed(() => {
  const duration = props.totalDuration
  const pps = props.pixelsPerSecond

  // Calculate minimum spacing we want between markers (in pixels)
  const minSpacing = 60 // pixels

  // Calculate what interval would give us this spacing
  const idealInterval = minSpacing / pps

  // Round to nice intervals: 1, 2, 5, 10, 15, 30, 60
  const intervals = [1, 2, 5, 10, 15, 30, 60]

  // Find the smallest interval that gives us enough spacing
  for (const interval of intervals) {
    if (interval >= idealInterval) {
      return interval
    }
  }

  // For very long durations, use 60s
  return 60
})

// Calculate number of markers to show
const markerCount = computed(() => {
  return Math.floor(props.totalDuration / markerInterval.value)
})
</script>

<style scoped>
.time-ruler {
  position: relative;
  height: 30px;
  background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
  border-bottom: 1px solid #334155;
  overflow: visible;
}

.second-marker {
  position: absolute;
  top: 0;
  font-size: 11px;
  color: #94a3b8;
  padding: 4px 6px;
  white-space: nowrap;
  user-select: none;
}

.second-marker::before {
  content: '';
  position: absolute;
  bottom: 0;
  left: 6px;
  width: 1px;
  height: 8px;
  background: #475569;
}
</style>
