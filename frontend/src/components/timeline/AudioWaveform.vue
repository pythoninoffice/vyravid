<template>
  <canvas
    ref="canvasRef"
    :width="width"
    :height="height"
    class="audio-waveform"
  ></canvas>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'

interface Props {
  audioUrl: string
  width: number
  height?: number
  waveColor?: string
  backgroundColor?: string
}

const props = withDefaults(defineProps<Props>(), {
  height: 60,
  waveColor: '#60a5fa',
  backgroundColor: 'transparent'
})

const canvasRef = ref<HTMLCanvasElement | null>(null)

const drawWaveform = async () => {
  if (!canvasRef.value) {
    console.warn('🌊 AudioWaveform: Canvas ref not available')
    return
  }

  const canvas = canvasRef.value
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    console.warn('🌊 AudioWaveform: Could not get canvas context')
    return
  }

  console.log('🌊 AudioWaveform: Starting to draw waveform', {
    url: props.audioUrl,
    width: props.width,
    height: props.height
  })

  try {
    // Clear canvas
    ctx.fillStyle = props.backgroundColor
    ctx.fillRect(0, 0, props.width, props.height)

    // Fetch audio file
    console.log('🌊 AudioWaveform: Fetching audio...')
    const response = await fetch(props.audioUrl, { mode: 'cors' })
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    const arrayBuffer = await response.arrayBuffer()
    console.log('🌊 AudioWaveform: Audio fetched, size:', arrayBuffer.byteLength)

    // Decode audio data
    console.log('🌊 AudioWaveform: Decoding audio...')
    const audioContext = new AudioContext()
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer)
    console.log('🌊 AudioWaveform: Audio decoded, duration:', audioBuffer.duration, 'channels:', audioBuffer.numberOfChannels)

    // Get audio data from first channel
    const rawData = audioBuffer.getChannelData(0)
    const samples = props.width // One sample per pixel
    const blockSize = Math.floor(rawData.length / samples)
    const filteredData = []

    // Downsample the audio data - use peak values for better visualization
    for (let i = 0; i < samples; i++) {
      const blockStart = blockSize * i
      let max = 0
      for (let j = 0; j < blockSize; j++) {
        const value = Math.abs(rawData[blockStart + j])
        if (value > max) max = value
      }
      filteredData.push(max)
    }

    console.log('🌊 Sample amplitude values (raw):', filteredData.slice(0, 10))

    // Normalize the data
    const maxAmplitude = Math.max(...filteredData)
    const normalizedData = filteredData.map(n => n / maxAmplitude)

    console.log('🌊 Max amplitude:', maxAmplitude)
    console.log('🌊 Normalized values:', normalizedData.slice(0, 10))

    // Draw waveform
    const barWidth = props.width / samples
    const halfHeight = props.height / 2

    ctx.fillStyle = props.waveColor

    let barsDrawn = 0
    let maxBarHeight = 0

    for (let i = 0; i < normalizedData.length; i++) {
      const barHeight = normalizedData[i] * halfHeight * 0.9 // 90% of half height
      const x = i * barWidth

      if (barHeight > maxBarHeight) maxBarHeight = barHeight

      // Draw symmetrical bars (top and bottom)
      ctx.fillRect(
        x,
        halfHeight - barHeight,
        Math.max(1, barWidth - 0.5),
        barHeight * 2
      )
      barsDrawn++
    }

    console.log('🌊 AudioWaveform: Waveform drawn successfully!', {
      samples,
      barsDrawn,
      maxBarHeight: maxBarHeight.toFixed(2),
      barWidth: barWidth.toFixed(2),
      canvasWidth: props.width,
      canvasHeight: props.height,
      fillColor: props.waveColor
    })

    // Close audio context to free resources
    await audioContext.close()

  } catch (error) {
    console.error('🌊 AudioWaveform: Error drawing waveform:', error)
    // Draw fallback simple waveform
    drawFallbackWaveform(ctx)
  }
}

const drawFallbackWaveform = (ctx: CanvasRenderingContext2D) => {
  // Draw a simple sine wave pattern as fallback
  ctx.strokeStyle = props.waveColor
  ctx.lineWidth = 2
  ctx.beginPath()

  const midY = props.height / 2
  const amplitude = props.height * 0.3

  for (let x = 0; x < props.width; x++) {
    const y = midY + Math.sin(x * 0.05) * amplitude
    if (x === 0) {
      ctx.moveTo(x, y)
    } else {
      ctx.lineTo(x, y)
    }
  }

  ctx.stroke()
}

// Draw waveform when component mounts
onMounted(() => {
  drawWaveform()
})

// Redraw if props change
watch(() => [props.audioUrl, props.width, props.height], () => {
  drawWaveform()
})
</script>

<style scoped>
.audio-waveform {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
