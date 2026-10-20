<script setup lang="ts">
import { ref, computed, onMounted, watch, useId } from 'vue'
import { ElMessage } from 'element-plus'
import { journalsApi } from '../api'

const props = withDefaults(defineProps<{ modelValue: number | null; enabled?: boolean; domain?: string; disabled?: boolean }>(), { enabled: true, domain: '', disabled: false })
const emit = defineEmits<{
  'update:modelValue': [value: number | null]
  'update:enabled': [value: boolean]
  change: [value: { journal_id: number | null; style_skill_enabled: boolean }]
}>()
const pickerId = useId()
const journals = ref<any[]>([])
const skill = ref<any>(null)
const loading = ref(false)
const error = ref('')
const preview = ref(false)
const article = ref<any>(null)
const articleLoading = ref(false)
const articleError = ref('')
const query = ref('')
const shown = ref(20)
const selected = computed(() => journals.value.find(j => j.id === props.modelValue))
const references = computed(() => (skill.value?.references || []).filter((a: any) => !query.value || `${a.title} ${a.doi} ${(a.domains || []).join(' ')}`.toLowerCase().includes(query.value.toLowerCase())))
watch(query, () => { shown.value = 20 })
const unsupported = computed(() => /马克思|法学|法律|政治理论/.test(props.domain))
let request = 0
watch(() => props.modelValue, async id => {
  const current = ++request
  skill.value = null
  error.value = ''
  if (!id) { loading.value = false; return }
  loading.value = true
  try { const result = await journalsApi.skill(id); if (current === request) skill.value = result }
  catch (e: any) { if (current === request) error.value = e.message }
  finally { if (current === request) loading.value = false }
}, { immediate: true })
function choose(value?: number) {
  emit('update:modelValue', value || null)
  emit('change', { journal_id: value || null, style_skill_enabled: props.enabled })
}
function toggle(value: string | number | boolean) {
  const enabled = Boolean(value)
  emit('update:enabled', enabled)
  emit('change', { journal_id: props.modelValue, style_skill_enabled: enabled })
}
async function viewArticle(id: string) {
  articleLoading.value = true
  articleError.value = ''
  article.value = { title: '正在读取文章原文…', paragraphs: [] }
  try { article.value = await journalsApi.article(id) }
  catch (e: any) { articleError.value = e.message }
  finally { articleLoading.value = false }
}
onMounted(async () => {
  try { journals.value = await journalsApi.list({ limit: 100 }) }
  catch (e: any) { ElMessage.error('期刊加载失败：' + e.message) }
})
</script>

<template>
  <section class="skill-picker" aria-label="期刊风格选择">
    <div class="skill-heading"><div><span class="skill-eyebrow">JOURNAL STYLE</span><h3>先选期刊，再开始翻译。</h3><p>可选：将对应期刊的写作组织与语气规则注入后续翻译。</p></div><span class="skill-pill">Skill 风格参考</span></div>
    <label class="skill-label" :for="`journal-skill-${pickerId}`">目标期刊</label>
    <el-select :id="`journal-skill-${pickerId}`" :model-value="modelValue ?? undefined" :disabled="disabled" filterable clearable placeholder="通用学术翻译（不注入期刊 Skill）" style="width:100%" @change="choose">
      <el-option v-for="journal in journals" :key="journal.id" :label="journal.name" :value="journal.id" />
    </el-select>
    <div v-if="modelValue" class="skill-options"><el-switch :model-value="enabled" :disabled="disabled" aria-label="注入期刊风格 Skill" active-text="注入期刊风格 Skill" @change="toggle" /><button v-if="skill?.skill_available" type="button" class="text-button" @click="preview = true">查看依据与规则 ↗</button></div>
    <div v-if="loading" class="skill-note" role="status">正在读取风格规则及语料依据…</div>
    <p v-if="error" role="alert" class="skill-warning">风格依据加载失败：{{ error }}</p>
    <div v-if="skill && modelValue" class="skill-summary">
      <template v-if="skill.skill_available"><strong>{{ skill.article_count }} 篇文章作为依据</strong><p>{{ skill.full_text_count }} 篇含全文 · {{ skill.abstract_count }} 条仅摘要 · {{ enabled ? '后续翻译将注入 Skill' : 'Skill 已关闭' }}</p><p class="skill-note">样本风格是写作参考；摘要统计只用于摘要，不作为官方硬性规范。这是提示词技能，并非微调模型。</p></template>
      <p v-else>该刊暂无可注入的语料风格 Skill，仅使用现有期刊配置。</p>
      <a v-if="selected?.author_guide_url" :href="selected.author_guide_url" target="_blank" rel="noopener noreferrer">官方投稿指南 ↗</a>
      <details v-if="selected" class="journal-config"><summary>查看项目已录入的期刊要求</summary><p>{{ selected.english_variant }} English · {{ selected.citation_style || '引用格式未设置' }} · 摘要上限 {{ selected.abstract_word_limit ? selected.abstract_word_limit + ' 词' : '未设置' }}</p><p v-if="selected.style_rules?.tense">时态：{{ selected.style_rules.tense }}</p><p v-if="selected.style_rules?.voice">语态：{{ selected.style_rules.voice }}</p><p v-if="selected.style_rules?.abbreviations">缩写：{{ selected.style_rules.abbreviations }}</p><ul><li v-for="(rule, index) in selected.style_rules?.other || []" :key="index">{{ rule }}</li></ul><p>以上为项目配置，投稿前请核对官方最新指南。</p></details>
    </div>
    <p v-if="unsupported" class="skill-warning">当前 11 刊尚未覆盖马克思主义理论和法学专业语料。建议使用通用翻译，专业译法交由对应领域信源与人工核定。</p>
    <el-dialog v-model="preview" :title="`${selected?.name || ''} · 风格依据`" width="min(900px, calc(100vw - 24px))" append-to-body>
      <template v-if="skill"><p class="skill-note">{{ skill.article_count }} 篇 · {{ skill.full_text_count }} 篇含全文。文章按学科关键词选取，样本统计存在选择偏差。</p><el-tabs><el-tab-pane label="实际文章"><el-input v-model="query" clearable placeholder="搜索标题、DOI 或领域" aria-label="搜索语料文章" /><div class="skill-articles"><article v-for="item in references.slice(0, shown)" :key="item.id"><a :href="item.article_url" target="_blank" rel="noopener noreferrer">{{ item.title }}</a><p>{{ item.year }} · {{ item.text_kind === 'full_text' ? '含全文' : '仅摘要' }} · {{ item.doi }}</p><p>{{ item.domains.join(' / ') || '尚未分类' }}</p><button class="text-button" type="button" @click="viewArticle(item.id)">查看已收集文本</button></article><button v-if="shown < references.length" class="text-button" type="button" @click="shown += 20">再显示 20 篇（已显示 {{ Math.min(shown, references.length) }} / {{ references.length }}）</button><el-empty v-if="!references.length" description="没有匹配的文章" /></div></el-tab-pane><el-tab-pane label="Skill 规则"><pre class="skill-content">{{ skill.content }}</pre></el-tab-pane></el-tabs></template>
    </el-dialog>
    <el-dialog :model-value="Boolean(article)" :title="article?.title" @close="article = null" append-to-body width="min(800px, calc(100vw - 24px))"><div v-loading="articleLoading"><p v-if="articleError" role="alert">{{ articleError }}</p><template v-else-if="article"><p class="skill-note">{{ article.text_kind === 'full_text' ? '开放许可全文' : '索引摘要，未下载全文' }} · {{ article.doi }}</p><a v-if="article.text_source_url" :href="article.text_source_url" target="_blank" rel="noopener noreferrer">文本获取出处 ↗</a><div class="article-text"><p v-for="(paragraph, index) in article.paragraphs" :key="index">{{ paragraph }}</p></div></template></div></el-dialog>
  </section>
</template>

<style scoped>
.skill-picker { padding:24px; border:1px solid #e5e5e7; border-radius:20px; background:#fff; margin-bottom:20px; color:#1d1d1f; }
.skill-heading { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:20px; }
.skill-eyebrow { font-size:10px; letter-spacing:1.8px; color:#626269; }
.skill-heading h3 { margin:9px 0; font-size:22px; letter-spacing:-.6px; }
.skill-heading p,.skill-summary p { font-size:12px; line-height:1.7; color:#626269; margin:6px 0; }
.skill-pill { border-radius:999px; background:#edf3ff; color:#275a9d; padding:7px 11px; font-size:10px; white-space:nowrap; }
.skill-label { display:block; font-size:12px; margin-bottom:8px; font-weight:600; }
.skill-options { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-top:12px; }
.text-button { border:0; background:none; color:#0066cc; cursor:pointer; font:inherit; font-size:12px; padding:5px 0; }
.text-button:focus-visible { outline:2px solid #0066cc; outline-offset:4px; }
.skill-summary { border-top:1px solid #ececee; margin-top:16px; padding-top:16px; font-size:13px; }
.skill-note { color:#626269; font-size:12px; line-height:1.7; }
.skill-warning { background:#fff7e5; padding:12px; border-radius:10px; color:#795200; font-size:12px; line-height:1.8; }
.skill-summary a,.skill-articles a { color:#0066cc; text-decoration:none; line-height:1.6; }
.journal-config { margin-top:14px; font-size:12px; }.journal-config summary { cursor:pointer; color:#626269; }.journal-config ul { padding-left:18px; line-height:1.8; color:#626269; }
.skill-articles,.skill-content,.article-text { max-height:55vh; overflow:auto; }
.skill-articles article { border-bottom:1px solid #e5e5e7; padding:16px 0; }
.skill-articles p { color:#626269; font-size:12px; margin:8px 0; }
.skill-content { white-space:pre-wrap; font-size:13px; line-height:1.9; font-family:inherit; }
.article-text p { font-size:14px; line-height:1.9; }
@media(max-width:600px) { .skill-picker { padding:18px; } .skill-heading { flex-direction:column; } .skill-heading h3 { font-size:20px; } }
</style>
