<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { terminologyApi } from '../api'

const props = defineProps<{ projectId: number }>()
const emit = defineEmits<{ changed: [] }>()
const documents = ref<any[]>([])
const models = ref<any[]>([])
const chosenModel = ref('')
const starting = ref(false)
const error = ref('')
const loaded = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
let revision = ''
let generation = 0
let disposed = false
const activeStatuses = ['queued', 'extracting', 'researching']
const busy = computed(() => documents.value.some(d => ['pending', 'parsing'].includes(d.parse_status) || activeStatuses.includes(d.analysis.status)))
const ready = computed(() => documents.value.some(d => d.parse_status === 'done' && !['done', ...activeStatuses].includes(d.analysis.status)))
const hasCompleted = computed(() => documents.value.some(d => d.analysis.status === 'done'))
const labels: Record<string, string> = { not_started: '等待识别', queued: '排队中', extracting: 'AI 正在识别疑似术语', researching: '正在查期刊与分级信源', done: '已完成 · 待人工核定', partial: '部分查证未完成', error: '任务未完成', needs_model: '需要配置 AI 模型', interrupted: '任务中断 · 可继续' }
const steps = ['AI 识别疑似术语', '查期刊文章', '查一级 → 二级信源', '人工核定译法']
const modelKey = (model: any) => JSON.stringify([model.provider, model.model])

async function refresh(token = generation) {
  try {
    const result = await terminologyApi.discovery(props.projectId)
    if (disposed || token !== generation) return
    documents.value = result.documents
    models.value = result.models
    if (!chosenModel.value) chosenModel.value = result.selected_model ? modelKey(result.selected_model) : (models.value[0] ? modelKey(models.value[0]) : '')
    const next = JSON.stringify(result.documents)
    if (revision && revision !== next) emit('changed')
    revision = next
    error.value = ''
    loaded.value = true
  } catch (e: any) {
    if (!disposed && token === generation) error.value = '进度读取失败：' + e.message
  } finally {
    if (!disposed && token === generation) timer = setTimeout(() => refresh(token), busy.value || error.value ? 3000 : 10000)
  }
}
async function start() {
  starting.value = true
  try {
    const [provider, model] = JSON.parse(chosenModel.value)
    const result = await terminologyApi.discover(props.projectId, { provider, model })
    ElMessage.success(result.message)
    clearTimeout(timer)
    await refresh()
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally { starting.value = false }
}
watch(() => props.projectId, () => {
  clearTimeout(timer)
  generation++
  revision = ''
  chosenModel.value = ''
  loaded.value = false
  documents.value = []
  refresh(generation)
}, { immediate: true })
onBeforeUnmount(() => { disposed = true; clearTimeout(timer) })
</script>

<template>
  <section class="discovery-panel mb-24" aria-labelledby="discovery-title">
    <div class="discovery-top">
      <div><span class="eyebrow">BEFORE TRANSLATION</span><h2 id="discovery-title">先找出值得查证的词。</h2><p>上传后自动用 AI 识别疑似专业术语，再查期刊与分级信源。识别和检索都不会代替人工确认。</p></div>
      <router-link :to="`/project/${projectId}`" class="upload-link">上传文档 ↗</router-link>
    </div>
    <ol class="discovery-steps" aria-label="术语处理顺序"><li v-for="(step, index) in steps" :key="step"><span>{{ String(index + 1).padStart(2, '0') }}</span>{{ step }}</li></ol>
    <div v-if="error" class="discovery-error" role="alert">{{ error }}</div>
    <p v-if="loaded && !documents.length" class="empty-note">还没有文档。先上传中文原文，系统会自动开始。</p>
    <div v-for="doc in documents" :key="doc.id" class="document-job">
      <div class="job-heading"><strong>{{ doc.filename }}</strong><span :class="{ running: activeStatuses.includes(doc.analysis.status), failed: ['error', 'partial', 'needs_model', 'interrupted'].includes(doc.analysis.status) }">{{ doc.parse_status !== 'done' ? ({ pending: '等待解析', parsing: '解析文档中', error: '文档解析失败' } as Record<string, string>)[doc.parse_status] : labels[doc.analysis.status] || doc.analysis.status }}</span></div>
      <template v-if="doc.parse_status === 'done'">
        <p v-if="doc.analysis.provider" class="job-detail">识别模型：{{ doc.analysis.provider }} / {{ doc.analysis.model }}</p>
        <p v-if="doc.analysis.total_chunks" class="job-detail" aria-live="polite">已识别 {{ doc.analysis.completed_chunks || 0 }} / {{ doc.analysis.total_chunks }} 批原文 · 疑似术语 {{ doc.analysis.identified_count || 0 }} 个 · 已处理查证 {{ doc.analysis.researched_count || 0 }} / {{ doc.analysis.identified_count || 0 }} 个<span v-if="doc.analysis.current_term"> · 当前：{{ doc.analysis.current_term }}</span></p>
        <p v-if="doc.analysis.status === 'done' && !doc.analysis.identified_count" class="job-detail">AI 本轮未识别到可保存的专业术语。你仍可手动添加需要核对的词。</p>
        <p v-if="doc.analysis.error" class="discovery-error">{{ doc.analysis.error }}</p>
      </template>
      <p v-else-if="doc.parse_error" class="discovery-error">{{ doc.parse_error }}</p>
    </div>
    <div v-if="documents.length" class="discovery-actions">
      <el-select v-model="chosenModel" aria-label="术语识别模型" placeholder="选择已配置的真实 AI 模型" :disabled="busy || starting" class="model-picker"><el-option v-for="model in models" :key="modelKey(model)" :label="model.label" :value="modelKey(model)" /></el-select>
      <el-button type="primary" :loading="starting" :disabled="busy || !ready || !chosenModel" @click="start">{{ busy ? '后台处理中' : !ready && hasCompleted ? '本轮处理已完成' : hasCompleted ? '处理剩余文档' : 'AI 识别并查证' }}</el-button>
      <router-link v-if="!models.length && loaded" to="/models">先配置模型 →</router-link>
    </div>
    <p v-if="hasCompleted" class="completion-note">接下来：在术语列表核对“AI 识别依据”，排除普通词，再查看两侧证据并确认译法。三级信源不采用。</p>
  </section>
</template>

<style scoped>
.discovery-panel{background:#fff;border:1px solid #e5e5e7;border-radius:20px;padding:26px;color:#1d1d1f}.discovery-top{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}.eyebrow{font-size:10px;letter-spacing:1.8px;color:#626269}.discovery-panel h2{font-size:23px;letter-spacing:-.5px;margin:10px 0}.discovery-panel p{font-size:12px;line-height:1.8;color:#626269;margin:6px 0}.upload-link{white-space:nowrap;font-size:12px;color:#0066cc;text-decoration:none;margin-top:24px}.discovery-steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:22px 0;padding:0;list-style:none}.discovery-steps li{font-size:12px;background:#f5f5f7;border-radius:10px;padding:12px;line-height:1.6}.discovery-steps span{font-size:10px;color:#626269;margin-right:8px}.document-job{padding:16px 0;border-top:1px solid #ececef}.job-heading{display:flex;justify-content:space-between;gap:16px;font-size:12px;line-height:1.6}.job-heading strong{font-weight:550;overflow-wrap:anywhere}.job-heading>span{color:#626269;flex-shrink:0}.job-heading>span.running{color:#0066cc}.job-heading>span.failed,.discovery-panel .discovery-error{color:#a33523}.discovery-panel .job-detail{font-size:11px;overflow-wrap:anywhere}.discovery-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:14px}.discovery-actions a{font-size:12px;color:#0066cc}.model-picker{width:260px;max-width:100%}.discovery-panel .completion-note{margin-top:18px;color:#145333}.upload-link:focus-visible,.discovery-actions a:focus-visible{outline:2px solid #0066cc;outline-offset:4px;border-radius:3px}@media(max-width:700px){.discovery-panel{padding:20px}.discovery-steps{grid-template-columns:1fr 1fr}.job-heading{flex-wrap:wrap;gap:5px}.discovery-top{gap:10px}.discovery-panel h2{font-size:21px}.discovery-actions{align-items:stretch}.model-picker{width:100%}}
</style>
