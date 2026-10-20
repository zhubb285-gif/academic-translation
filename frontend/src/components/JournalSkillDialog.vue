<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { journalsApi } from '../api'

const props = defineProps<{ modelValue: boolean; journalId: number | null; journalName: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const skill = ref<any>(null)
const loading = ref(false)
const error = ref('')
const tab = ref('rules')
const query = ref('')
const shown = ref(20)
const article = ref<any>(null)
const articleOpen = ref(false)
const articleLoading = ref(false)
const articleError = ref('')
let request = 0
let articleRequest = 0
const references = computed(() => (skill.value?.references || []).filter((item: any) =>
  !query.value.trim() || `${item.title} ${item.doi} ${(item.domains || []).join(' ')}`.toLowerCase().includes(query.value.trim().toLowerCase())))
watch(query, () => { shown.value = 20 })
async function loadSkill() {
  const token = ++request
  skill.value = null
  error.value = ''
  loading.value = Boolean(props.modelValue && props.journalId)
  if (!loading.value) return
  try {
    const result = await journalsApi.skill(props.journalId!)
    if (token === request) skill.value = result
  } catch (e: any) {
    if (token === request) error.value = e.message || '无法读取 Skill'
  } finally { if (token === request) loading.value = false }
}
watch(() => [props.modelValue, props.journalId], () => {
  tab.value = 'rules'
  query.value = ''
  shown.value = 20
  articleOpen.value = false
  articleRequest++
  loadSkill()
}, { immediate: true })
async function viewArticle(id: string) {
  const token = ++articleRequest
  article.value = null
  articleError.value = ''
  articleLoading.value = true
  articleOpen.value = true
  try {
    const result = await journalsApi.article(id)
    if (token === articleRequest) article.value = result
  } catch (e: any) {
    if (token === articleRequest) articleError.value = e.message || '无法读取文章'
  } finally { if (token === articleRequest) articleLoading.value = false }
}
onBeforeUnmount(() => { request++; articleRequest++ })
</script>

<template>
  <el-dialog :model-value="modelValue" :title="`${journalName} · 期刊风格 Skill`" width="min(960px, calc(100vw - 24px))" append-to-body class="journal-skill-dialog" @update:model-value="emit('update:modelValue', $event)">
    <div class="skill-viewer">
      <div v-if="loading" class="viewer-state" role="status">正在读取完整 Skill 与文章依据…</div>
      <div v-else-if="error" class="viewer-state"><p role="alert">Skill 加载失败：{{ error }}</p><el-button round @click="loadSkill">重新加载</el-button></div>
      <template v-else-if="skill?.skill_available">
        <p class="viewer-eyebrow">JOURNAL STYLE SKILL</p>
        <p class="viewer-intro">这里展示翻译与校对实际读取的完整 Skill。它依据已收集文章归纳写作组织与语气，样本观察不等于官方投稿要求。</p>
        <div class="skill-facts"><div><strong>{{ skill.article_count }}</strong><span>篇参考文章</span></div><div><strong>{{ skill.full_text_count }}</strong><span>篇含全文</span></div><div><strong>{{ skill.abstract_count }}</strong><span>条仅摘要</span></div></div>
        <el-tabs v-model="tab">
          <el-tab-pane label="完整 Skill" name="rules"><div class="skill-meta"><span>{{ skill.skill_name }}</span><span>版本 {{ skill.version }}</span></div><pre class="skill-document" tabindex="0" aria-label="完整期刊风格 Skill 内容">{{ skill.content }}</pre></el-tab-pane>
          <el-tab-pane :label="`文章依据（${skill.article_count}）`" name="articles">
            <el-input v-model="query" clearable placeholder="搜索标题、DOI 或领域" aria-label="搜索期刊 Skill 的参考文章" />
            <div class="reference-list"><article v-for="item in references.slice(0, shown)" :key="item.id"><a :href="item.article_url" target="_blank" rel="noopener noreferrer">{{ item.title }} ↗</a><p>{{ item.year }} · {{ item.text_kind === 'full_text' ? '含全文' : '仅摘要' }} · {{ item.doi }}</p><p>{{ (item.domains || []).join(' / ') || '尚未分类' }}</p><button type="button" class="viewer-link" @click="viewArticle(item.id)">查看已收集文本 →</button></article><el-empty v-if="!references.length" description="没有匹配的文章" :image-size="60" /><button v-if="shown < references.length" type="button" class="viewer-link more-references" @click="shown += 20">再显示 20 篇（{{ Math.min(shown, references.length) }} / {{ references.length }}）</button></div>
          </el-tab-pane>
          <el-tab-pane label="统计与方法" name="profile"><p class="viewer-intro">以下为这批语料的统计记录。摘要统计只用于摘要风格参考，不作为正文或 Methods 的硬性阈值。</p><pre class="skill-document" tabindex="0" aria-label="语料统计与方法">{{ JSON.stringify(skill.profile, null, 2) }}</pre></el-tab-pane>
        </el-tabs>
      </template>
      <el-empty v-else description="该期刊尚未整理风格 Skill，可先查看官方作者指南或已有风格规则。" :image-size="70" />
    </div>
    <template #footer><el-button round @click="emit('update:modelValue', false)">关闭</el-button></template>
  </el-dialog>
  <el-dialog v-model="articleOpen" :title="article?.title || '文章原文'" width="min(820px, calc(100vw - 24px))" append-to-body @closed="articleRequest++">
    <div class="skill-viewer"><p v-if="articleLoading" role="status">正在读取文章…</p><p v-else-if="articleError" role="alert">文章加载失败：{{ articleError }}</p><template v-else-if="article"><p class="viewer-intro">{{ article.text_kind === 'full_text' ? '开放许可全文' : '索引摘要，未下载全文' }} · {{ article.doi }}</p><a class="viewer-link" :href="article.text_source_url" target="_blank" rel="noopener noreferrer">文本获取出处 ↗</a><div class="article-body"><p v-for="(paragraph, index) in article.paragraphs" :key="index">{{ paragraph }}</p></div></template></div>
  </el-dialog>
</template>

<style scoped>
.skill-viewer{color:#1d1d1f}.viewer-state{min-height:180px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:12px;color:#626269;font-size:13px}.viewer-eyebrow{font-size:10px;letter-spacing:1.8px;color:#626269;margin:0 0 12px}.viewer-intro{font-size:12px;line-height:1.8;color:#626269;margin:10px 0 20px}.skill-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:20px}.skill-facts>div{padding:16px 18px;background:#f5f5f7;border-radius:14px;display:flex;flex-direction:column;gap:7px}.skill-facts strong{font-size:24px;font-weight:600;letter-spacing:-.6px}.skill-facts span{font-size:11px;color:#626269}.skill-meta{display:flex;gap:16px;justify-content:space-between;font-size:11px;color:#626269;padding:4px 0 14px;flex-wrap:wrap;overflow-wrap:anywhere}.skill-document{max-height:48vh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.95 system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:22px;background:#f8f8fa;border:1px solid #e8e8ed;border-radius:14px;margin:0}.reference-list{max-height:48vh;overflow:auto;padding:0 2px}.reference-list article{padding:20px 0;border-bottom:1px solid #e5e5e7}.reference-list article>a{font-size:14px;line-height:1.65;color:#0066cc;text-decoration:none}.reference-list article p{font-size:11px;color:#626269;line-height:1.8;overflow-wrap:anywhere;margin:8px 0}.viewer-link{border:0;background:none;color:#0066cc;font:inherit;font-size:12px;cursor:pointer;text-decoration:none;padding:4px 0}.more-references{display:block;margin:16px auto}.article-body{max-height:55vh;overflow:auto;margin-top:16px}.article-body p{font-size:14px;line-height:1.95}.skill-document:focus-visible,.viewer-link:focus-visible,.reference-list article>a:focus-visible{outline:2px solid #0066cc;outline-offset:3px}@media(max-width:600px){.skill-facts{gap:8px}.skill-facts>div{padding:12px}.skill-facts strong{font-size:21px}.skill-document{padding:14px;font-size:12px}.reference-list article>a{font-size:13px}}
</style>
