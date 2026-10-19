<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import ModelIdentity from './ModelIdentity.vue'
export interface OrbitItem { key: string; title: string; label: string; provider: string; tone: string; caption: string; configured: boolean; kind: string; config?: any }
const props = defineProps<{ items: OrbitItem[]; paused?: boolean; light?: boolean }>()
const emit = defineEmits<{ select: [item: OrbitItem] }>()
const root = ref<HTMLElement>()
const width = ref(900)
const rotation = ref(0)
const hovering = ref(false)
const manualPause = ref(false)
const reduced = ref(false)
const tile = computed(() => Math.min(116, width.value * .205))
const radiusX = computed(() => Math.min(310, width.value * .385))
const radiusY = computed(() => Math.min(205, width.value * .435))
const height = computed(() => 2 * radiusY.value + tile.value + 72)
let observer: ResizeObserver, media: MediaQueryList, frame = 0, previous = 0
function style(i: number) {
  const angle = i / props.items.length * Math.PI * 2 + rotation.value
  const x = Math.sin(angle) * radiusX.value
  const y = -Math.cos(angle) * radiusY.value
  return { width: `${tile.value}px`, height: `${tile.value}px`,
    transform: `translate(-50%, -50%) translate3d(${x}px,${y}px,0) perspective(700px) rotateY(${Math.sin(angle) * -63}deg) rotateZ(${Math.sin(angle * 2) * 11}deg)`,
    zIndex: Math.round(20 + Math.sin(angle) * 2 + Math.cos(angle) * 5),
  }
}
function animate(now: number) {
  const delta = Math.min(now - previous, 64); previous = now
  if (!props.paused && !hovering.value && !manualPause.value && !reduced.value && !document.hidden) rotation.value += delta * .000045
  frame = requestAnimationFrame(animate)
}
function motionChange() { reduced.value = media.matches }
onMounted(() => {
  observer = new ResizeObserver(entries => { width.value = entries[0].contentRect.width })
  if (root.value) observer.observe(root.value)
  media = matchMedia('(prefers-reduced-motion: reduce)'); motionChange(); media.addEventListener('change', motionChange)
  previous = performance.now(); frame = requestAnimationFrame(animate)
})
onBeforeUnmount(() => { observer?.disconnect(); media?.removeEventListener('change', motionChange); cancelAnimationFrame(frame) })
</script>
<template>
  <div ref="root" class="model-orbit" :class="{ 'is-light': light }" :style="{height: `${height}px`}" @mouseenter="hovering = true" @mouseleave="hovering = false" @focusin="hovering = true" @focusout="hovering = false">
    <div class="orbit-center"><span class="orbit-eyebrow">YOUR AI COLLECTIVE</span><h1>让合适的模型，<br>完成擅长的事。</h1><p>翻译、推理与独立校对。<br>点击厂家，选择具体型号。</p></div>
    <div role="group" aria-label="模型与服务商，点击打开配置" class="orbit-track">
      <button v-for="(item, i) in items" :key="item.key" class="orbit-tile" :class="`tone-${item.tone}`" :style="style(i)" type="button" :aria-label="`配置${item.kind === 'provider' ? '服务商' : '模型'}：${item.title}`" @click="emit('select',item)">
        <span class="tile-mark"><ModelIdentity :provider="item.provider" /></span><span class="tile-label">{{ item.label }}</span><span class="tile-caption">{{ item.caption }}</span><span v-if="item.configured" class="tile-dot" aria-label="已配置" />
      </button>
    </div>
    <button class="motion-toggle" type="button" :disabled="reduced" :aria-label="manualPause ? '继续标识环动画' : '暂停标识环动画'" @click="manualPause = !manualPause">{{ manualPause || reduced ? '▶' : 'Ⅱ' }} <span>{{ manualPause || reduced ? '静止浏览' : '缓慢环绕' }}</span></button>
  </div>
</template>
<style scoped>
.model-orbit { position: relative; width: min(100%, 900px); margin: 0 auto; isolation: isolate; }
.orbit-center { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 330px; max-width: 50%; text-align: center; z-index: 2; pointer-events: none; }
.orbit-eyebrow { display: block; color: #b7b7b2; font-size: 9px; letter-spacing: 2px; margin-bottom: 16px; }
.orbit-center h1 { color: #f6f5f0; font-weight: 500; font-size: 34px; letter-spacing: -1.2px; line-height: 1.25; margin: 0; }
.orbit-center p { font-size: 11px; color: #b6b6b1; line-height: 1.8; margin: 18px 0 0; }
.orbit-track { position: absolute; inset: 0; }
.orbit-tile { position: absolute; top: 50%; left: 50%; border: 1px solid #ffffff0b; border-radius: 18px; display: flex; align-items: center; justify-content: center; flex-direction: column; padding: 14px 8px 10px; cursor: pointer; color: #f5f5ef; background: #080808; box-shadow: 0 3px 3px #0002; will-change: transform; font-family: inherit; }
.tile-mark { display: block; width: 48%; height: 48%; margin-bottom: 6px; transition: transform .25s; }
.tile-label { font-size: 12px; font-weight: 600; line-height: 1.2; letter-spacing: -.4px; white-space: nowrap; }
.tile-caption { font-size: 8px; margin-top: 4px; opacity: .8; white-space: nowrap; }
.tile-dot { position: absolute; top: 10px; right: 10px; width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.orbit-tile:hover .tile-mark { transform: scale(1.12); }
.orbit-tile:hover { outline: 1px solid #ffffff80; }
.orbit-tile:focus-visible { outline: 3px solid #bcc8ff; outline-offset: 6px; }
.tone-ivory { background: #eeede6; color: #121212; }
.tone-blue { background: #1948f0; color: white; --mark-eye: #1948f0; }
.tone-sky { background: #4f8cff; color: #071631; }
.tone-teal { background: #0f766e; color: #d6fff5; }
.tone-rose { background: #e86f8b; color: #2f101a; }
.tone-mint { background: #a6e0ba; color: #12352a; }
.tone-coral { background: #e4a68c; color: #25130e; }
.tone-green { background: #143936; color: #a6e0ba; }
.tone-black { background: #030303; color: #f5f5ef; --mark-eye: #030303; }
.tone-lilac { background: #c1b1ea; color: #241d35; }
.tone-orange { background: #ff613d; color: #21120f; }
.model-orbit.is-light .orbit-eyebrow { color: #6e6e73; }
.model-orbit.is-light .orbit-center h1 { color: #1d1d1f; }
.model-orbit.is-light .orbit-center p { color: #6e6e73; }
.model-orbit.is-light .orbit-tile { border-color: #00000018; box-shadow: 0 10px 24px #1d1d1f18, 0 2px 5px #1d1d1f20; }
.model-orbit.is-light .tone-ivory { background: #fff; color: #1d1d1f; border: 2px solid #1d1d1f; box-shadow: 0 10px 24px #1d1d1f25, inset 0 0 0 3px #f5f5f7; }
.model-orbit.is-light .tone-black { border-color: #303036; }
.model-orbit.is-light .motion-toggle { color: #6e6e73; }
.motion-toggle { position: absolute; bottom: 0; left: 50%; transform: translateX(-50%); border: 0; border-radius: 20px; background: none; color: #b7b7b2; padding: 8px 12px; font-size: 10px; cursor: pointer; display: flex; align-items: center; gap: 7px; white-space: nowrap; }
.motion-toggle:disabled { cursor: default; }
.motion-toggle:focus-visible { outline: 2px solid #bcc8ff; outline-offset: 2px; }
@media(max-width: 600px) {
  .orbit-center { width: 190px; max-width: 53%; }
  .orbit-center h1 { font-size: clamp(19px,5.8vw,28px); line-height: 1.35; letter-spacing: -.7px; }
  .orbit-eyebrow { font-size: 7px; letter-spacing: 1px; margin-bottom: 10px; }
  .orbit-center p { font-size: 9px; margin-top: 12px; line-height: 1.8; }
  .orbit-tile { border-radius: 12px; padding: 8px 3px; }
  .tile-label { font-size: 8px; letter-spacing: -.1px; }
  .tile-caption { display: none; }
  .tile-mark { margin-bottom: 4px; }
  .tile-dot { width: 4px; height: 4px; top: 7px; right: 7px; }
}
@media(prefers-reduced-motion: reduce) { .tile-mark { transition: none; } }
</style>
