<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { mountTechText } from './techTextEngine.js'

const props = defineProps({
  text: { type: String, default: 'React Bits' },
  fontFamily: { type: String, default: '' },
  fontWeight: { type: Number, default: 600 },
  fontSize: { type: Number, default: 150 },
  letterSpacing: { type: Number, default: -0.05 },
  color: { type: String, default: 'currentColor' },
  accentColor: { type: String, default: 'currentColor' },
  align: { type: String, default: 'center' },
  reach: { type: Number, default: 200 },
  softness: { type: Number, default: 0.7 },
  dashLength: { type: Number, default: 4 },
  dashGap: { type: Number, default: 2 },
  strokeWidth: { type: Number, default: 1.5 },
  lineStyle: { type: String, default: 'dashed' },
  reveal: { type: String, default: 'letter' },
  specks: { type: Number, default: 15 },
  selection: { type: Boolean, default: true },
  labels: { type: Boolean, default: true },
  draggable: { type: Boolean, default: true },
  bounce: { type: Number, default: 0.4 },
  sweep: { type: Boolean, default: true },
  speed: { type: Number, default: 1 },
  clickKick: { type: Boolean, default: true },
  intro: { type: String, default: 'none' },
  introDuration: { type: Number, default: 2 },
  guides: { type: Boolean, default: false },
})
const container = ref(null)
const canvas = ref(null)
const ready = ref(false)
let renderer
onMounted(() => {
  if (!canvas.value?.getContext('2d')) return
  renderer = mountTechText(container.value, canvas.value, () => props)
  ready.value = true
})
watch(props, () => renderer?.wake())
onBeforeUnmount(() => renderer?.dispose())
</script>

<template>
  <div ref="container" class="tech-text" role="img" :aria-label="text">
    <canvas ref="canvas" class="tech-text-canvas" aria-hidden="true" />
    <span v-if="!ready" class="tech-text-fallback" aria-hidden="true">{{ text }}</span>
  </div>
</template>

<style scoped>
.tech-text {
  position: relative;
  width: 100%;
  height: 100%;
  touch-action: pan-y;
  user-select: none;
}
.tech-text-canvas { display: block; width: 100%; height: 100%; }
.tech-text-fallback {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-size: clamp(38px, 10vw, 150px);
  font-weight: 600;
  letter-spacing: -.05em;
}
</style>
