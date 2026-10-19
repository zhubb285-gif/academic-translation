<script setup lang="ts">
// Original Vue implementation: CSS perspective, no licensed React source required.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

export interface GalleryItem {
  id: number
  title: string
  subtitle?: string
  image?: string
  color?: string
  monogram?: string
}
const props = defineProps<{ items: GalleryItem[]; modelValue: number }>()
const emit = defineEmits<{ 'update:modelValue': [index: number] }>()
const stage = ref<HTMLElement>()
const width = ref(1000)
const position = ref(0)
const target = ref(0)
const dragging = ref(false)
const hovering = ref(false)
const paused = ref(true)
const reduced = ref(false)
const failed = ref(new Set<string>())
const count = computed(() => props.items.length)
const panelWidth = computed(() => Math.min(282, Math.max(178, width.value * 0.29)))
const panelHeight = computed(() => panelWidth.value * 1.36)
const active = computed(() => props.items[props.modelValue])
const wrap = (n: number) => count.value ? ((n % count.value) + count.value) % count.value : 0
let frame = 0, observer: ResizeObserver, media: MediaQueryList
let lastTime = 0, lastAdvance = 0, dragStart = 0, dragPosition = 0, moved = false
let pointerId: number | null = null

function select(index: number) {
  if (!count.value) return
  const next = wrap(index)
  let delta = next - wrap(Math.round(target.value))
  if (delta > count.value / 2) delta -= count.value
  if (delta < -count.value / 2) delta += count.value
  target.value = count.value < 5 ? next : Math.round(target.value) + delta
  emit('update:modelValue', next)
  lastAdvance = performance.now()
}
function move(direction: number) { select(wrap(Math.round(target.value)) + direction) }
function panelStyle(i: number) {
  let delta = i - position.value
  if (count.value >= 5) delta -= Math.round(delta / count.value) * count.value
  // A concave wall: the side panels curve toward the viewer and face inward.
  const angle = delta * 0.41
  const radius = (panelWidth.value + 26) / 0.41
  const x = Math.sin(angle) * radius
  const z = (1 - Math.cos(angle)) * radius
  const distance = Math.abs(delta)
  return {
    width: `${panelWidth.value}px`, height: `${panelHeight.value}px`,
    transform: `translate(-50%, -50%) translate3d(${x}px, 0, ${z}px) rotateY(${-angle}rad)`,
    opacity: distance > 2.45 ? 0 : Math.max(0.25, 1 - distance * 0.2),
    visibility: distance > 2.45 ? 'hidden' as const : 'visible' as const,
    zIndex: Math.round(100 - distance * 10),
    '--cover-color': props.items[i]?.color || '#33506d',
  }
}
function startDrag(event: PointerEvent) {
  if (count.value < 2 || (event.pointerType === 'mouse' && event.button !== 0)) return
  pointerId = event.pointerId
  dragging.value = true
  moved = false
  dragStart = event.clientX
  dragPosition = position.value
}
function drag(event: PointerEvent) {
  if (!dragging.value || event.pointerId !== pointerId) return
  const dx = event.clientX - dragStart
  if (Math.abs(dx) > 6) {
    moved = true
    stage.value?.setPointerCapture(event.pointerId)
  }
  if (moved) {
    const next = dragPosition - dx / (panelWidth.value + 26)
    position.value = target.value = count.value < 5 ? Math.max(0, Math.min(count.value - 1, next)) : next
  }
}
function endDrag(event: PointerEvent) {
  if (event.pointerId !== pointerId) return
  dragging.value = false
  pointerId = null
  if (stage.value?.hasPointerCapture(event.pointerId)) stage.value.releasePointerCapture(event.pointerId)
  target.value = Math.round(position.value)
  emit('update:modelValue', wrap(target.value))
  lastAdvance = performance.now()
}
function clickPanel(i: number) { if (!moved) select(i) }
function keyboard(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', ' '].includes(event.key)) return
  event.preventDefault()
  if (event.key === 'ArrowLeft') move(-1)
  if (event.key === 'ArrowRight') move(1)
  if (event.key === 'Home') select(0)
  if (event.key === 'End') select(count.value - 1)
  if (event.key === ' ') paused.value = !paused.value
}
function animate(now: number) {
  const elapsed = Math.min(now - lastTime, 64)
  lastTime = now
  if (!dragging.value) {
    position.value = reduced.value ? target.value : position.value + (target.value - position.value) * (1 - Math.exp(-elapsed / 95))
    if (Math.abs(position.value - target.value) < 0.0001) position.value = target.value
  }
  if (!paused.value && !hovering.value && !dragging.value && !reduced.value && count.value > 1 && now - lastAdvance > 6000) move(1)
  frame = requestAnimationFrame(animate)
}
function motionChanged() { reduced.value = media.matches }
watch(() => props.modelValue, value => {
  if (wrap(Math.round(target.value)) !== value) select(value)
})
watch(() => props.items.map(i => i.id).join(','), () => {
  position.value = target.value = 0
  failed.value = new Set()
  emit('update:modelValue', 0)
  lastAdvance = performance.now()
})
onMounted(() => {
  media = matchMedia('(prefers-reduced-motion: reduce)')
  motionChanged()
  media.addEventListener('change', motionChanged)
  observer = new ResizeObserver(entries => { width.value = entries[0].contentRect.width })
  if (stage.value) observer.observe(stage.value)
  lastAdvance = lastTime = performance.now()
  frame = requestAnimationFrame(animate)
})
onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
  media?.removeEventListener('change', motionChanged)
})
</script>

<template>
  <section class="concave-gallery" aria-roledescription="轮播图" aria-label="期刊封面画廊">
    <div ref="stage" class="gallery-stage" :class="{ dragging }" role="group" tabindex="0"
      aria-label="拖动浏览期刊，或按左右方向键切换，空格暂停自动轮播"
      :style="{ '--panel-height': `${panelHeight}px` }"
      @keydown="keyboard" @pointerdown="startDrag" @pointermove="drag" @pointerup="endDrag" @pointercancel="endDrag"
      @mouseenter="hovering = true" @mouseleave="hovering = false" @focusin="hovering = true" @focusout="hovering = false">
      <div class="gallery-floor" aria-hidden="true" />
      <div class="gallery-wall">
        <button v-for="(item, i) in items" :key="item.id" type="button" class="cover-panel"
          :class="{ 'is-active': i === modelValue }" :style="panelStyle(i)" :aria-label="`查看 ${item.title} 的投稿规范`"
          :aria-pressed="i === modelValue" :tabindex="i === modelValue ? 0 : -1" @click="clickPanel(i)" @dragstart.prevent>
          <img v-if="item.image && !failed.has(item.image)" class="cover-image" :src="item.image" :alt="`${item.title} 期刊图片`"
            referrerpolicy="no-referrer" draggable="false" @error="failed.add(item.image!)" />
          <div v-else class="cover-placeholder" aria-hidden="true"><span>{{ item.monogram || item.title.split(' ').map(w => w[0]).join('').slice(0, 4) }}</span><i /></div>
          <div class="cover-shade" />
          <div class="cover-top"><span>JOURNAL COLLECTION</span><span>{{ String(i + 1).padStart(2, '0') }}</span></div>
          <div class="cover-title" :class="{ 'long-title': item.title.length > 55 }"><small>{{ item.subtitle }}</small><h2>{{ item.title }}</h2><span class="cover-action">查看投稿规范 <span>↗</span></span></div>
        </button>
      </div>
    </div>
    <div class="gallery-navigation">
      <div class="gallery-caption"><span class="caption-eyebrow">正在浏览 · {{ String(modelValue + 1).padStart(2, '0') }} / {{ String(items.length).padStart(2, '0') }}</span><p>{{ active?.title }}</p></div>
      <div class="gallery-controls">
        <button type="button" :aria-label="paused ? '开始自动轮播' : '暂停自动轮播'" :disabled="items.length < 2 || reduced" @click="paused = !paused" class="play-button">{{ paused || reduced ? '▶' : 'Ⅱ' }}</button>
        <button type="button" aria-label="上一种期刊" :disabled="items.length < 2" @click="move(-1)">←</button>
        <button type="button" aria-label="下一种期刊" :disabled="items.length < 2" @click="move(1)">→</button>
      </div>
    </div>
    <div class="gallery-dots" aria-label="选择期刊"><button v-for="(item, i) in items" :key="item.id" type="button" :aria-label="item.title" :aria-current="i === modelValue ? 'true' : undefined" :class="{ active: i === modelValue }" @click="select(i)" /></div>
  </section>
</template>

<style scoped>
.concave-gallery { width: 100%; }
.gallery-stage { position: relative; height: calc(var(--panel-height) + 150px); min-height: 390px; max-height: 560px; overflow: hidden; touch-action: pan-y; cursor: grab; outline-offset: -5px; border-radius: 24px; user-select: none; }
.gallery-stage.dragging { cursor: grabbing; }
.gallery-wall { position: absolute; inset: 0; perspective: 1500px; perspective-origin: 50% 42%; pointer-events: none; }
.gallery-floor { position: absolute; width: 78%; height: 65px; left: 11%; bottom: 15px; background: radial-gradient(ellipse, #20314e18 0%, transparent 70%); filter: blur(12px); }
.cover-panel { position: absolute; top: 44%; left: 50%; padding: 0; border: 0; border-radius: 13px; overflow: hidden; background: var(--cover-color); color: white; text-align: left; pointer-events: auto; backface-visibility: hidden; box-shadow: 0 25px 42px -20px #18233570, 0 0 0 1px #ffffff44 inset; cursor: inherit; will-change: transform; }
.cover-panel:focus-visible { outline: 3px solid #0071e3; outline-offset: 5px; }
.cover-image { position: absolute; width: 100%; height: 100%; inset: 0; object-fit: cover; pointer-events: none; }
.cover-placeholder { position: absolute; inset: 0; overflow: hidden; background: linear-gradient(155deg, #ffffff16, transparent 60%); }
.cover-placeholder > span { position: absolute; left: -10px; top: 22%; font-size: 100px; font-weight: 700; letter-spacing: -10px; opacity: .16; }
.cover-placeholder i { position: absolute; width: 85%; aspect-ratio: 1; border: 1px solid #ffffff40; border-radius: 50%; right: -20%; top: 4%; box-shadow: 0 0 0 20px #ffffff09, 0 0 0 40px #ffffff07, 0 0 0 60px #ffffff05; transform: rotate(-25deg) scaleX(.7); }
.cover-shade { position: absolute; inset: 0; background: linear-gradient(180deg,#0004 0%,transparent 22%,#0001 35%,#000b 100%); }
.cover-top { position: absolute; top: 16px; left: 18px; right: 18px; display: flex; justify-content: space-between; font-size: 8px; font-weight: 500; letter-spacing: 1.5px; opacity: .8; }
.cover-title { position: absolute; bottom: 22px; left: 22px; right: 20px; }
.cover-title small { display: block; font-size: 10px; line-height: 1.5; opacity: .8; margin-bottom: 9px; }
.cover-title h2 { font-family: Georgia, 'Times New Roman', serif; font-size: clamp(21px, 2.7vw, 32px); font-weight: 500; line-height: 1.08; letter-spacing: -.8px; overflow-wrap: anywhere; margin: 0; text-wrap: balance; }
.cover-title.long-title h2 { font-size: 23px; line-height: 1.14; letter-spacing: -.5px; }
.cover-action { display: flex; justify-content: space-between; margin-top: 18px; padding-top: 12px; border-top: 1px solid #ffffff55; font-size: 10px; letter-spacing: .3px; }
.cover-action > span { font-size: 14px; }
.gallery-navigation { max-width: 750px; margin: -12px auto 0; padding: 0 24px; display: flex; justify-content: space-between; gap: 20px; align-items: center; position: relative; }
.caption-eyebrow { color: #86868b; font-size: 10px; letter-spacing: 1.2px; }
.gallery-caption p { font-size: 17px; font-weight: 600; margin: 8px 0 0; color: #1d1d1f; line-height: 1.4; }
.gallery-controls { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.gallery-controls button { width: 38px; height: 38px; border-radius: 50%; border: 1px solid #d2d2d7; background: #ffffffa0; color: #1d1d1f; cursor: pointer; font-size: 18px; transition: background .2s; }
.gallery-controls button:hover { background: #e8e8ed; }
.gallery-controls button:disabled { opacity: .3; cursor: default; }
.gallery-controls .play-button { border-color: transparent; background: transparent; font-size: 13px; color: #86868b; }
.gallery-dots { display: flex; justify-content: center; gap: 7px; margin-top: 22px; flex-wrap: wrap; padding: 0 24px; }
.gallery-dots button { border: 0; background: #c5c5cb; width: 6px; height: 6px; border-radius: 5px; padding: 0; cursor: pointer; position: relative; transition: width .3s, background .3s; }
.gallery-dots button::after { content: ''; position: absolute; inset: -9px -3px; }
.gallery-dots button.active { width: 22px; background: #1d1d1f; }
@media (max-width: 600px) {
  .gallery-stage { min-height: 350px; height: calc(var(--panel-height) + 110px); }
  .gallery-navigation { padding: 0 8px; gap: 12px; }
  .gallery-caption p { font-size: 14px; max-width: 200px; }
  .gallery-controls { gap: 4px; }
  .gallery-controls button { width: 32px; height: 32px; }
  .cover-title { bottom: 17px; left: 15px; right: 15px; }
  .cover-title h2 { font-size: 23px; }
  .cover-title.long-title h2 { font-size: 18px; }
  .cover-top { left: 15px; right: 15px; font-size: 7px; letter-spacing: .8px; }
  .cover-title small { font-size: 9px; }
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
