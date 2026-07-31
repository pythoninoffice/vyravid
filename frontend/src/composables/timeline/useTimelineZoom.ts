import { ref, computed } from 'vue'

export interface TimelineZoomOptions {
  initialZoom?: number
  basePixelsPerSecond?: number
  minZoom?: number
  maxZoom?: number
}

export function useTimelineZoom(options: TimelineZoomOptions = {}) {
  const {
    initialZoom = 1.0,
    basePixelsPerSecond = 100,
    minZoom = 0.1,
    maxZoom = 4
  } = options

  const zoomLevel = ref(initialZoom)

  const pixelsPerSecond = computed(() => basePixelsPerSecond * zoomLevel.value)

  const effectivePixelsPerSecond = computed(() => pixelsPerSecond.value)

  const setZoom = (newZoom: number) => {
    zoomLevel.value = Math.max(minZoom, Math.min(maxZoom, newZoom))
  }

  const zoomIn = (step = 0.1) => {
    setZoom(zoomLevel.value + step)
  }

  const zoomOut = (step = 0.1) => {
    setZoom(zoomLevel.value - step)
  }

  const resetZoom = () => {
    zoomLevel.value = initialZoom
  }

  return {
    zoomLevel,
    pixelsPerSecond,
    effectivePixelsPerSecond,
    basePixelsPerSecond,
    setZoom,
    zoomIn,
    zoomOut,
    resetZoom,
    minZoom,
    maxZoom
  }
}
