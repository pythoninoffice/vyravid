<template>
  <div
    ref="container"
    style="width: 100%; height: 100%; background: #000; border-radius: 8px; overflow: hidden; display: flex; align-items: center; justify-content: center;"
  >
    <div ref="mountPoint" :style="mountStyle" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, computed } from 'vue'

const props = withDefaults(defineProps<{
  code: string
  currentFrame?: number
  audioUrl?: string
  useAudioDurationForTimeline?: boolean
}>(), {
  useAudioDurationForTimeline: true,
})

const emit = defineEmits<{
  'update:currentFrame': [frame: number]
  'player-play': []
  'player-pause': []
}>()

const container = ref<HTMLDivElement | null>(null)
const mountPoint = ref<HTMLDivElement | null>(null)
let reactRoot: any = null
let remotionPlayerInstance: any = null
let evalCallId = 0 // guard against concurrent async calls
let _playerPlaying = false // true while the Remotion player is playing autonomously

const containerW = ref(0)
const containerH = ref(0)

// Composition dimensions — updated after eval extracts metadata
const compWidth = ref(1920)
const compHeight = ref(1080)
const compFps = ref(30)
const compDurationInFrames = ref(300)
const externalAudioDurationSeconds = ref(0)
const playerDurationInFrames = computed(() => {
  const audioFrames = externalAudioDurationSeconds.value > 0
    ? Math.max(1, Math.ceil(externalAudioDurationSeconds.value * compFps.value))
    : 0
  return props.useAudioDurationForTimeline && audioFrames
    ? audioFrames
    : compDurationInFrames.value
})
const animationFrameScale = computed(() => {
  if (playerDurationInFrames.value <= 0 || compDurationInFrames.value <= 0) return 1
  return compDurationInFrames.value / playerDurationInFrames.value
})

const scale = computed(() => {
  if (!containerW.value || !containerH.value) return 1
  return Math.min(containerW.value / compWidth.value, containerH.value / compHeight.value)
})

const mountStyle = computed(() => ({
  width: Math.max(1, compWidth.value * scale.value) + 'px',
  height: Math.max(1, compHeight.value * scale.value) + 'px',
  flexShrink: 0,
}))

let resizeObserver: ResizeObserver | null = null
let audioProbeId = 0

function measureContainer() {
  if (container.value) {
    const rect = container.value.getBoundingClientRect()
    containerW.value = rect.width
    containerH.value = rect.height
  }
}

async function probeAudioDuration(audioUrl?: string) {
  const myId = ++audioProbeId

  if (!audioUrl || typeof window === 'undefined') {
    externalAudioDurationSeconds.value = 0
    return
  }

  try {
    const durationSeconds = await new Promise<number>((resolve, reject) => {
      const probeEl = new window.Audio()
      const cleanup = () => {
        probeEl.onloadedmetadata = null
        probeEl.onerror = null
        probeEl.removeAttribute('src')
        probeEl.load()
      }

      probeEl.preload = 'metadata'
      probeEl.onloadedmetadata = () => {
        const duration = Number.isFinite(probeEl.duration) ? probeEl.duration : 0
        cleanup()
        resolve(duration > 0 ? duration : 0)
      }
      probeEl.onerror = () => {
        cleanup()
        reject(new Error('Failed to load audio metadata'))
      }
      probeEl.src = audioUrl
      probeEl.load()
    })

    if (myId !== audioProbeId) return
    externalAudioDurationSeconds.value = durationSeconds
  } catch {
    if (myId !== audioProbeId) return
    externalAudioDurationSeconds.value = 0
  }
}

async function evalCode(code: string, audioUrl?: string) {
  if (!mountPoint.value) return
  const myId = ++evalCallId

  try {
    // Dynamic imports
    const React = await import('react')
    const { createRoot } = await import('react-dom/client')
    const { Player } = await import('@remotion/player')
    // Cast to any: TS resolves 'remotion' to local remotion/index.ts re-exports;
    // at runtime vite correctly resolves to the npm package with all members.
    const remotion: any = await import('remotion')
    const transitions: any = await import('@remotion/transitions')
    const transitionsFade: any = await import('@remotion/transitions/fade')
    const transitionsSlide: any = await import('@remotion/transitions/slide')
    const transitionsWipe: any = await import('@remotion/transitions/wipe')
    const transitionsFlip: any = await import('@remotion/transitions/flip')
    const transitionsClockWipe: any = await import('@remotion/transitions/clock-wipe')
    const transitionsIris: any = await import('@remotion/transitions/iris')
    const transitionsNone: any = await import('@remotion/transitions/none')
    const { transform } = await import('sucrase')
    const mapboxglModule = await import('mapbox-gl')
    const mapboxgl = mapboxglModule.default
    const Map = mapboxgl.Map
    const turfModule: any = await import('@turf/turf')
    const turf = turfModule.default || turfModule
    const { ThreeCanvas } = await import('@remotion/three')

    // Shim require() for libraries that use CJS internally
    const moduleCache: Record<string, any> = {
      'react': React,
      'remotion': remotion,
      'mapbox-gl': mapboxglModule,
      '@turf/turf': turf,
      '@remotion/three': { ThreeCanvas },
      '@remotion/transitions': transitions,
      '@remotion/transitions/fade': transitionsFade,
      '@remotion/transitions/slide': transitionsSlide,
      '@remotion/transitions/wipe': transitionsWipe,
      '@remotion/transitions/flip': transitionsFlip,
      '@remotion/transitions/clock-wipe': transitionsClockWipe,
      '@remotion/transitions/iris': transitionsIris,
      '@remotion/transitions/none': transitionsNone,
    }
    const requireShim = (mod: string) => {
      if (moduleCache[mod]) return moduleCache[mod]
      console.warn(`[RemotionPlayer] require('${mod}') not available in preview`)
      return {}
    }

    // Strip import statements (handles single-line and multi-line imports)
    let body = code
      .replace(/^\s*import\s+[\s\S]*?\s+from\s+['"][^'"]+['"]\s*;?\s*$/gm, '')
      .replace(/^\s*import\s+['"][^'"]+['"]\s*;?\s*$/gm, '')

    // Strip export keywords
    body = body.replace(/export\s+default\s+/g, '')
    body = body.replace(/export\s+/g, '')

    // Append return statement
    body += '\nreturn { Component: GeneratedVideo, metadata };'

    // Transpile TSX → JS via sucrase
    const transformed = transform(body, { transforms: ['typescript', 'jsx'] }).code

    // Scope-inject allowed Remotion APIs
    const scopedFn = new Function(
      'React',
      'useCurrentFrame',
      'useVideoConfig',
      'Img',
      'Video',
      'Audio',
      'AbsoluteFill',
      'Sequence',
      'Series',
      'Loop',
      'interpolate',
      'interpolateColors',
      'spring',
      'Easing',
      'staticFile',
      'calculateMetadata',
      'TransitionSeries',
      'linearTiming',
      'springTiming',
      'fade',
      'slide',
      'wipe',
      'flip',
      'clockWipe',
      'iris',
      'none',
      'mapboxgl',
      'Map',
      'turf',
      'ThreeCanvas',
      'useDelayRender',
      'useEffect',
      'useMemo',
      'useRef',
      'useState',
      'process',
      'require',
      transformed,
    )

    const { Component, metadata } = scopedFn(
      React,
      remotion.useCurrentFrame,
      () => {
        const config = remotion.useVideoConfig()
        return {
          ...config,
          durationInFrames: compDurationInFrames.value,
        }
      },
      remotion.Img,
      remotion.Video,
      remotion.Audio,
      remotion.AbsoluteFill,
      remotion.Sequence,
      remotion.Series,
      remotion.Loop,
      remotion.interpolate,
      remotion.interpolateColors,
      remotion.spring,
      remotion.Easing,
      remotion.staticFile,
      remotion.calculateMetadata,
      transitions.TransitionSeries,
      transitions.linearTiming,
      transitions.springTiming,
      transitionsFade.fade,
      transitionsSlide.slide,
      transitionsWipe.wipe,
      transitionsFlip.flip,
      transitionsClockWipe.clockWipe,
      transitionsIris.iris,
      transitionsNone.none,
      mapboxgl,
      Map,
      turf,
      ThreeCanvas,
      remotion.useDelayRender,
      React.useEffect,
      React.useMemo,
      React.useRef,
      React.useState,
      { env: import.meta.env },
      requireShim,
    )

    // Update dimension refs from extracted metadata
    if (metadata) {
      compWidth.value = metadata.width || compWidth.value
      compHeight.value = metadata.height || compHeight.value
      compFps.value = metadata.fps || compFps.value
      compDurationInFrames.value = metadata.durationInFrames || compDurationInFrames.value
    }

    // React error boundary (defined after React import since it extends React.Component)
    class ErrorBoundary extends React.Component<{ children: any }, { hasError: boolean; error: any }> {
      constructor(props: any) {
        super(props)
        this.state = { hasError: false, error: null }
      }
      static getDerivedStateFromError(error: any) {
        return { hasError: true, error }
      }
      render() {
        if (this.state.hasError) {
          return React.createElement(
            'div',
            { style: { color: '#f87171', padding: '16px', fontFamily: 'monospace', fontSize: '13px', whiteSpace: 'pre-wrap' } },
            'Preview error: ' + (this.state.error?.message || String(this.state.error)),
          )
        }
        return this.props.children
      }
    }

    // Discard if a newer evalCode call came in while we were awaiting imports
    if (myId !== evalCallId) return

    // Mount or re-render
    if (!reactRoot) {
      reactRoot = createRoot(mountPoint.value!)
    }

    const WrappedComponent = () =>
      {
        const liveFrame = remotion.useCurrentFrame()
        const mappedFrame = Math.min(
          compDurationInFrames.value - 1,
          Math.max(0, Math.round(liveFrame * animationFrameScale.value)),
        )

        return React.createElement(
          remotion.AbsoluteFill,
          null,
          audioUrl
            ? React.createElement(
                remotion.Freeze,
                { frame: mappedFrame },
                React.createElement(Component),
              )
            : React.createElement(Component),
          audioUrl ? React.createElement(remotion.Audio, { src: audioUrl }) : null,
        )
      }

    reactRoot.render(
      React.createElement(
        ErrorBoundary,
        null,
        React.createElement(Player, {
          component: WrappedComponent,
          durationInFrames: playerDurationInFrames.value,
          compositionWidth: compWidth.value,
          compositionHeight: compHeight.value,
          fps: compFps.value,
          controls: true,
          loop: false,
          autoPlay: false,
          acknowledgeRemotionLicense: true,
          style: {
            width: '100%',
            height: '100%',
          },
          ref: (instance: any) => {
            remotionPlayerInstance = instance
            if (instance) {
              instance.addEventListener('timeupdate', (e: any) => {
                emit('update:currentFrame', e.detail.frame)
              })
              instance.addEventListener('play', () => {
                _playerPlaying = true
                emit('player-play')
              })
              instance.addEventListener('pause', () => {
                _playerPlaying = false
                emit('player-pause')
              })
            }
          },
        }),
      ),
    )
  } catch (err: any) {
    if (myId !== evalCallId) return
    // Unmount React so it releases DOM ownership, then show the error message via React
    if (reactRoot) {
      try { reactRoot.unmount() } catch { /* ignore */ }
      reactRoot = null
    }
    remotionPlayerInstance = null
    // Re-create root and render error message through React to avoid innerHTML/fiber mismatch
    if (mountPoint.value) {
      try {
        const { createRoot: cr } = await import('react-dom/client')
        const React2 = await import('react')
        reactRoot = cr(mountPoint.value)
        reactRoot.render(
          React2.createElement(
            'div',
            { style: { color: '#f87171', padding: '16px', fontFamily: 'monospace', fontSize: '13px', whiteSpace: 'pre-wrap' } },
            'Eval error: ' + (err?.message || String(err)),
          ),
        )
      } catch { /* ignore secondary errors */ }
    }
  }
}

onMounted(() => {
  void probeAudioDuration(props.audioUrl)
  evalCode(props.code, props.audioUrl)
  measureContainer()
  if (container.value) {
    resizeObserver = new ResizeObserver(measureContainer)
    resizeObserver.observe(container.value)
  }
})

watch(
  () => [props.code, props.audioUrl, playerDurationInFrames.value, animationFrameScale.value] as const,
  ([newCode, newAudioUrl]) => {
    evalCode(newCode, newAudioUrl)
  },
)

watch(() => props.audioUrl, (newAudioUrl) => {
  void probeAudioDuration(newAudioUrl)
})

watch(() => props.currentFrame, (frame) => {
  // Skip seekTo while the player is driving its own playback to avoid fighting it
  if (frame != null && remotionPlayerInstance && !_playerPlaying) {
    try {
      remotionPlayerInstance.seekTo(frame)
    } catch {
      // Player may not be ready yet
    }
  }
})

defineExpose({
  play:   () => { try { remotionPlayerInstance?.play()   } catch {} },
  pause:  () => { try { remotionPlayerInstance?.pause()  } catch {} },
  toggle: () => { try { remotionPlayerInstance?.toggle() } catch {} },
})

onBeforeUnmount(() => {
  if (reactRoot) {
    reactRoot.unmount()
    reactRoot = null
  }
  if (resizeObserver) {
    resizeObserver.disconnect()
  }
})
</script>
