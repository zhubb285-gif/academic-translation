<script setup>
// Vue adaptation of the React Bits TextType supplied by the user.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { gsap } from 'gsap'

const props = defineProps({
  text: { type: [String, Array], required: true },
  as: { type: String, default: 'span' },
  typingSpeed: { type: Number, default: 75 },
  initialDelay: { type: Number, default: 200 },
  pauseDuration: { type: Number, default: 4000 },
  deletingSpeed: { type: Number, default: 50 },
  loop: { type: Boolean, default: true },
  showCursor: { type: Boolean, default: true },
  cursorStyle: { type: String, default: 'bar' },
  cursorCharacter: { type: String, default: '|' },
  cursorColor: { type: String, default: 'currentColor' },
  cursorBlinkDuration: { type: Number, default: 0.5 },
  cursorGlide: { type: Boolean, default: true },
  typeEffect: { type: String, default: 'fade' },
  startOnVisible: { type: Boolean, default: true },
})
const emit = defineEmits(['sentenceComplete'])
const root = ref(null)
const caret = ref(null)
const cursor = ref(null)
const blink = ref(null)
const index = ref(0)
const count = ref(0)
const deleting = ref(false)
const reducedMotion = ref(false)
const visible = ref(false)
const sentences = computed(() => Array.isArray(props.text) ? props.text.map(String) : [props.text])
const segment = value => typeof Intl.Segmenter === 'function'
  ? Array.from(new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(value), part => part.segment)
  : Array.from(value)
const chars = computed(() => segment(sentences.value[index.value] || ''))
const shown = computed(() => chars.value.slice(0, count.value))
const longest = computed(() => sentences.value.reduce((a, b) => segment(a).length >= segment(b).length ? a : b, ''))
let timer, observer, resizeObserver, motionQuery, blinking, resumeBlink
let alive = false
let position = null
const glyphAnimations = new Set()
const animatedGlyphs = new WeakSet()

function clearTimer() { clearTimeout(timer) }
function updateMotion() {
  reducedMotion.value = motionQuery.matches
  restart()
}
function startBlink() {
  blinking?.kill()
  resumeBlink?.kill()
  if (!blink.value) return
  gsap.killTweensOf(blink.value)
  gsap.set(blink.value, { opacity: 1 })
  if (reducedMotion.value || props.cursorBlinkDuration <= 0) return
  blinking = gsap.to(blink.value, {
    opacity: 0, duration: props.cursorBlinkDuration, ease: 'sine.inOut', repeat: -1, yoyo: true,
  })
}
function placeCursor(instant = false) {
  if (!alive || !caret.value || !cursor.value) return
  const x = caret.value.offsetLeft
  const y = caret.value.offsetTop
  if (position && Math.abs(position.x - x) < 0.5 && Math.abs(position.y - y) < 0.5) return
  const jump = instant || !position || !props.cursorGlide || reducedMotion.value || Math.abs(position.y - y) > 1
  position = { x, y }
  gsap.killTweensOf(cursor.value)
  if (jump) gsap.set(cursor.value, { x, y })
  else gsap.to(cursor.value, { x, y, duration: Math.min(0.18, Math.max(0.06, props.typingSpeed * 0.0016)), ease: 'power3.out' })
  if (!blinking || reducedMotion.value) return
  blinking.pause()
  resumeBlink?.kill()
  gsap.set(blink.value, { opacity: 1 })
  resumeBlink = gsap.delayedCall(0.12, () => blinking?.restart())
}
function animateChar(node) {
  if (!node || animatedGlyphs.has(node) || reducedMotion.value || props.typeEffect === 'none' || !node.animate) return
  animatedGlyphs.add(node)
  const frames = {
    fade: [{ opacity: 0 }, { opacity: 1 }],
    blur: [{ opacity: 0, filter: 'blur(.3em)' }, { opacity: 1, filter: 'blur(0)' }],
    rise: [{ opacity: 0, top: '.6em' }, { opacity: 1, top: '0' }],
  }[props.typeEffect]
  if (!frames) return
  const animation = node.animate(frames, { duration: 360, easing: 'cubic-bezier(.25,1,.5,1)' })
  glyphAnimations.add(animation)
  animation.onfinish = () => glyphAnimations.delete(animation)
}
function schedule(delay) {
  clearTimer()
  if (!alive || !visible.value || reducedMotion.value) return
  timer = setTimeout(tick, Math.max(0, delay))
}
function tick() {
  if (!alive || reducedMotion.value) return
  if (!deleting.value) {
    if (count.value < chars.value.length) {
      count.value++
      schedule(count.value === chars.value.length ? props.pauseDuration : props.typingSpeed)
    } else if (props.loop || index.value < sentences.value.length - 1) {
      deleting.value = true
      schedule(props.deletingSpeed)
    }
  } else if (count.value > 0) {
    count.value--
    schedule(props.deletingSpeed)
  } else {
    emit('sentenceComplete', sentences.value[index.value], index.value)
    index.value = (index.value + 1) % Math.max(1, sentences.value.length)
    deleting.value = false
    schedule(props.initialDelay + props.typingSpeed)
  }
}
function restart() {
  clearTimer()
  for (const animation of glyphAnimations) animation.cancel()
  glyphAnimations.clear()
  index.value = 0
  count.value = reducedMotion.value ? chars.value.length : 0
  deleting.value = false
  position = null
  startBlink()
  nextTick(() => placeCursor(true))
  schedule(props.initialDelay + props.typingSpeed)
}
watch([count, index, () => props.showCursor], () => nextTick(() => placeCursor()))
watch(() => [props.text, props.typingSpeed, props.loop, props.typeEffect, props.showCursor], () => { if (alive) restart() }, { deep: true })
onMounted(() => {
  alive = true
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  reducedMotion.value = motionQuery.matches
  motionQuery.addEventListener('change', updateMotion)
  resizeObserver = new ResizeObserver(() => placeCursor(true))
  resizeObserver.observe(root.value)
  if (props.startOnVisible) {
    observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return
      visible.value = true
      restart()
      observer.disconnect()
    }, { threshold: 0.1 })
    observer.observe(root.value)
  } else {
    visible.value = true
    restart()
  }
})
onBeforeUnmount(() => {
  alive = false
  clearTimer()
  observer?.disconnect()
  resizeObserver?.disconnect()
  motionQuery?.removeEventListener('change', updateMotion)
  blinking?.kill()
  resumeBlink?.kill()
  if (cursor.value) gsap.killTweensOf(cursor.value)
  if (blink.value) gsap.killTweensOf(blink.value)
  for (const animation of glyphAnimations) animation.cancel()
  glyphAnimations.clear()
})
</script>

<template>
  <component :is="as" ref="root" class="text-type" :class="{ 'text-type--reduced': reducedMotion }">
    <span class="text-type__sr">{{ sentences.join(' ') }}</span>
    <span class="text-type__space" aria-hidden="true">{{ longest }}</span>
    <span class="text-type__content" aria-hidden="true"><span
      v-for="(char, i) in shown" :key="`${index}-${i}`" class="text-type__char" :ref="animateChar"
    >{{ char }}</span><span ref="caret" class="text-type__caret">&#8203;</span></span>
    <span v-if="showCursor" ref="cursor" aria-hidden="true" class="text-type__cursor" :class="`text-type__cursor--${cursorStyle}`" :style="{ color: cursorColor }">
      <span ref="blink" class="text-type__blink"><template v-if="cursorStyle === 'character'">{{ cursorCharacter }}</template><span v-else class="text-type__shape" /></span>
    </span>
  </component>
</template>

<style scoped>
.text-type { position: relative; display: inline-block; white-space: pre-wrap; max-width: 100%; padding-right: .16em; }
.text-type__space { visibility: hidden; }
.text-type__content { position: absolute; inset: 0; }
.text-type__sr { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
.text-type__char { position: relative; }
.text-type__caret { display: inline-block; width: 0; }
.text-type__cursor { position: absolute; top: 0; left: 0; white-space: pre; pointer-events: none; will-change: transform; }
.text-type__blink { display: inline-block; }
.text-type__cursor--character .text-type__blink { margin-left: .08em; }
.text-type__shape { display: inline-block; margin-left: .04em; background-color: currentColor; }
.text-type__cursor--bar .text-type__shape { width: max(2px,.06em); height: .95em; vertical-align: -.12em; border-radius: 1px; }
.text-type__cursor--block .text-type__shape { width: .56em; height: 1.1em; vertical-align: -.2em; border-radius: .06em; }
.text-type__cursor--underscore .text-type__shape { width: .56em; height: max(2px,.075em); vertical-align: -.12em; }
.text-type--reduced .text-type__cursor { display: none; }
</style>
