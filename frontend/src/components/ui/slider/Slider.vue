<script setup lang="ts">
import { SliderRange, SliderRoot, SliderThumb, SliderTrack } from 'reka-ui'
import { cn } from '@/lib/utils'

interface SliderProps {
  modelValue?: number[]
  min?: number
  max?: number
  step?: number
  class?: string
}

const props = withDefaults(defineProps<SliderProps>(), {
  modelValue: () => [0],
  min: 0,
  max: 100,
  step: 1,
  class: '',
})

const emits = defineEmits<{
  'update:modelValue': [value: number[]]
}>()
</script>

<template>
  <SliderRoot
    :model-value="modelValue"
    :min="min"
    :max="max"
    :step="step"
    :class="cn('relative flex w-full touch-none select-none items-center', props.class)"
    @update:model-value="(value) => emits('update:modelValue', value as number[])"
  >
    <SliderTrack class="relative h-2 w-full grow overflow-hidden rounded-full bg-orange-500">
      <SliderRange class="absolute h-full bg-orange-600" />
    </SliderTrack>
    <SliderThumb class="block h-5 w-5 rounded-full border-2 border-orange-500 bg-white ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 hover:scale-110 hover:border-orange-600 shadow-md" />
  </SliderRoot>
</template>
