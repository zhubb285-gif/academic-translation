<script setup lang="ts">
// Vue adaptation of the supplied React Bits AccordionGallery: solid colour panels.
import { computed, ref, watch, nextTick } from 'vue'
import { Delete } from '@element-plus/icons-vue'
const props = defineProps<{
  projects: any[]
  statusLabel: (status: string) => string
  progress: (project: any) => number
  formatDate: (value: string) => string
}>()
const emit = defineEmits<{ open: [id: number]; delete: [project: any] }>()
const activeId = ref<number | null>(null)
const page = ref(0)
const pageSize = 5
const root = ref<HTMLElement>()
const pageCount = computed(() => Math.ceil(props.projects.length / pageSize))
const panels = computed(() => props.projects.slice(page.value * pageSize, (page.value + 1) * pageSize))
const colours = ['#dae7f3', '#e7e0f1', '#dbe8de', '#f1e3d7', '#ece7cf']
watch(() => props.projects.map(p => p.id).join(','), () => {
  page.value = 0
}, { immediate: true })
watch(panels, items => {
  if (!items.some(p => p.id === activeId.value)) activeId.value = items[0]?.id ?? null
}, { immediate: true })
function hover(id: number) {
  if (matchMedia('(hover: hover) and (pointer: fine)').matches && !root.value?.contains(document.activeElement)) activeId.value = id
}
async function move(index: number, event: KeyboardEvent) {
  const direction = ['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : ['ArrowLeft', 'ArrowUp'].includes(event.key) ? -1 : 0
  if (!direction && event.key !== 'Home' && event.key !== 'End') return
  event.preventDefault()
  const target = event.key === 'Home' ? 0 : event.key === 'End' ? panels.value.length - 1 : (index + direction + panels.value.length) % panels.value.length
  activeId.value = panels.value[target].id
  await nextTick()
  root.value?.querySelectorAll<HTMLButtonElement>('.panel-toggle')[target]?.focus()
}
</script>

<template>
  <section ref="root" class="project-accordion-section" aria-label="我的项目手风琴画廊">
    <p class="gallery-hint">选择一张卡片，展开你的项目。<span>左右方向键也可切换</span></p>
    <div class="project-accordion" :class="{ 'single-panel': panels.length === 1 }">
      <article v-for="(project, index) in panels" :key="project.id" class="project-panel" :class="{ 'is-active': activeId === project.id }" :style="{ '--panel-colour': colours[(page * pageSize + index) % colours.length], '--panel-grow': panels.length > 1 ? (0.56 * (panels.length - 1)) / 0.44 : 1, '--panel-tilt': `${index < panels.findIndex(p => p.id === activeId) ? 5 : -5}deg` }" @pointerenter="hover(project.id)">
        <div class="panel-background" aria-hidden="true"><span>{{ String(page * pageSize + index + 1).padStart(2, '0') }}</span></div>
        <button class="panel-toggle" :id="`project-toggle-${project.id}`" :aria-expanded="activeId === project.id" :aria-controls="`project-details-${project.id}`" @click="activeId = project.id" @focus="activeId = project.id" @keydown="move(index, $event)">
          <span class="panel-index">PROJECT {{ String(page * pageSize + index + 1).padStart(2, '0') }}</span>
          <span class="panel-title">{{ project.name }}</span>
          <span class="panel-status">{{ statusLabel(project.status) }}</span>
          <span class="panel-expand-icon" aria-hidden="true">{{ activeId === project.id ? '−' : '＋' }}</span>
        </button>
        <div v-show="activeId === project.id" :id="`project-details-${project.id}`" class="panel-details" role="region" :aria-labelledby="`project-toggle-${project.id}`">
          <div class="panel-description"><span class="panel-type">{{ project.article_type || '学术翻译项目' }}</span><p>{{ project.domain || '通用学术领域' }}</p></div>
          <div class="panel-progress"><div><span>译文覆盖进度</span><strong>{{ project.translated_segments || 0 }} / {{ project.total_segments || 0 }} 句段</strong></div><div class="progress-track" role="progressbar" :aria-label="`${project.name}译文覆盖进度`" :aria-valuenow="progress(project)" :aria-valuemin="0" :aria-valuemax="100"><span :style="{width: `${progress(project)}%`}" /></div></div>
          <div class="panel-meta"><span>{{ project.translation_model || '尚未选择模型' }}</span><time>{{ formatDate(project.updated_at) }}</time></div>
          <div class="panel-actions"><button class="project-open" @click="emit('open', project.id)">打开项目 <span aria-hidden="true">↗</span></button><button class="project-delete" :aria-label="`删除项目：${project.name}`" @click="emit('delete', project)"><el-icon><Delete /></el-icon></button></div>
        </div>
      </article>
    </div>
    <nav v-if="pageCount > 1" class="gallery-pagination" aria-label="项目分页"><button :disabled="page === 0" @click="page--">← 上一组</button><span>{{ page + 1 }} / {{ pageCount }}</span><button :disabled="page + 1 >= pageCount" @click="page++">下一组 →</button></nav>
  </section>
</template>

<style scoped>
.project-accordion-section { min-width: 0; }
.gallery-hint { display:flex; justify-content:space-between; gap:16px; font-size:12px; color:#626269; margin:0 0 18px; }
.gallery-hint span { color:#6e6e73; }
.project-accordion { display:flex; gap:12px; height:460px; perspective:1400px; }
.project-panel { position:relative; flex:1 1 0; min-width:0; border-radius:22px; overflow:hidden; background:var(--panel-colour); color:#243042; transform:rotateY(var(--panel-tilt)); box-shadow:0 12px 25px -18px #24304255; transition:flex-grow .65s cubic-bezier(.22,1,.36,1),transform .65s cubic-bezier(.22,1,.36,1); }
.project-panel.is-active { flex-grow:var(--panel-grow); transform:rotateY(0); }
.single-panel .project-panel { max-width:100%; }
.panel-background { position:absolute; inset:0; pointer-events:none; overflow:hidden; }
.panel-background span { position:absolute; bottom:-20px; right:-12px; font-size:220px; font-weight:650; letter-spacing:-20px; line-height:1; opacity:.045; transition:transform .65s; transform:translateX(24px); }
.is-active .panel-background span { transform:none; }
.panel-toggle { display:flex; flex-direction:column; align-items:flex-start; position:relative; width:100%; height:100%; border:0; border-radius:22px; background:transparent; color:inherit; text-align:left; font:inherit; padding:28px 20px; cursor:pointer; }
.panel-index { font-size:10px; letter-spacing:1.5px; white-space:nowrap; }
.panel-title { margin:auto 0 32px; writing-mode:vertical-rl; font-size:21px; font-weight:600; letter-spacing:.03em; max-height:285px; overflow:hidden; text-overflow:ellipsis; }
.panel-status { font-size:11px; white-space:nowrap; }
.panel-expand-icon { position:absolute; top:25px; right:18px; font-size:20px; }
.is-active .panel-toggle { height:auto; padding:28px 28px 0; min-height:146px; }
.is-active .panel-title { writing-mode:horizontal-tb; margin:24px 16px 12px 0; font-size:clamp(21px,2.2vw,29px); line-height:1.35; letter-spacing:-.035em; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.is-active .panel-status { position:absolute; top:25px; right:54px; background:#ffffff75; padding:4px 9px; border-radius:999px; }
.panel-details { position:relative; padding:14px 28px 26px; animation:detail-reveal .45s .12s both; }
.panel-description { min-height:65px; }
.panel-type { font-size:11px; opacity:.9; }
.panel-description p { margin:8px 0 20px; font-size:13px; line-height:1.5; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.panel-progress { margin-top:20px; font-size:11px; }
.panel-progress > div:first-child { display:flex; justify-content:space-between; gap:10px; }
.panel-progress strong { font-weight:550; white-space:nowrap; }
.progress-track { height:5px; background:#24304215; border-radius:4px; margin-top:12px; overflow:hidden; }
.progress-track span { display:block; height:100%; background:#27634d; border-radius:inherit; }
.panel-meta { display:flex; flex-wrap:wrap; gap:6px 14px; margin-top:18px; font-size:10px; line-height:1.5; }
.panel-meta time { color:#4d5869; }
.panel-actions { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-top:22px; }
.project-open { display:flex; align-items:center; justify-content:space-between; gap:32px; background:#243042; color:#fff; border:0; border-radius:999px; font:inherit; font-size:12px; padding:12px 19px; cursor:pointer; }
.project-delete { display:grid; place-items:center; width:34px; height:34px; border:1px solid #24304235; border-radius:50%; background:transparent; color:#364357; cursor:pointer; }
.project-delete:hover { background:#fff8; color:#a51d2d; }
.panel-toggle:focus-visible { outline:3px solid #0066cc; outline-offset:-5px; }
.panel-actions button:focus-visible,.gallery-pagination button:focus-visible { outline:3px solid #0066cc; outline-offset:3px; }
.gallery-pagination { display:flex; align-items:center; justify-content:center; gap:24px; margin-top:24px; font-size:12px; color:#626269; }
.gallery-pagination button { font:inherit; border:1px solid #d2d2d7; border-radius:999px; background:#fff; padding:8px 14px; color:#243042; cursor:pointer; }
.gallery-pagination button:disabled { opacity:.45; cursor:default; }
@keyframes detail-reveal { from { opacity:0; transform:translateX(-12px); } to { opacity:1; transform:none; } }
@media(max-width:700px) {
  .gallery-hint span { display:none; }
  .project-accordion { height:auto; flex-direction:column; perspective:none; gap:10px; }
  .project-panel { flex:none; transform:none; }
  .panel-toggle { min-height:90px; padding:20px; display:grid; grid-template-columns:1fr auto; gap:8px 16px; }
  .panel-index { font-size:9px; }
  .panel-title { writing-mode:horizontal-tb; margin:0; font-size:16px; grid-row:2; grid-column:1 / -1; max-height:48px; padding-right:22px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
  .panel-status { grid-column:2; grid-row:1; margin-right:26px; }
  .panel-expand-icon { top:17px; right:18px; }
  .is-active .panel-toggle { display:flex; padding:24px 22px 0; min-height:126px; }
  .is-active .panel-title { font-size:23px; }
  .is-active .panel-status { top:20px; right:45px; margin:0; }
  .panel-details { padding:8px 22px 24px; }
  .panel-description { min-height:0; }
  .panel-progress { margin-top:24px; }
}
@media(prefers-reduced-motion:reduce) { .project-panel,.panel-background span { transition:none; transform:none; } .panel-details { animation:none; } }
</style>
