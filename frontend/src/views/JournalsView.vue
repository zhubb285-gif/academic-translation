<template>
  <div class="journals-view">
    <div class="apple-back-bar journal-back">
      <button class="apple-back-pill" @click="$router.push('/workspace')"><el-icon><ArrowLeft /></el-icon><span>返回我的项目</span></button>
      <span class="bar-hint">JOURNAL COLLECTION</span>
    </div>

    <header class="journal-heading">
      <div><p class="eyebrow">为你的下一篇论文</p><h1><TextType text="找到你的目标期刊。" :typing-speed="75" :pause-duration="4000" :deleting-speed="50" type-effect="fade" cursor-style="bar" :cursor-glide="true" :show-cursor="true" /></h1><p class="heading-desc">从写作风格到投稿要求，让每一次表达更有方向。</p></div>
      <el-button round type="primary" @click="openCreate"><el-icon><Plus /></el-icon>添加期刊</el-button>
    </header>

    <div class="collection-toolbar">
      <div><span class="collection-label">期刊规范</span><span class="collection-count">{{ journals.length }} 本期刊</span></div>
      <el-input v-model="searchQuery" aria-label="搜索期刊" placeholder="搜索期刊名称或缩写" clearable @input="debouncedSearch"><template #prefix><el-icon><Search /></el-icon></template></el-input>
    </div>

    <div v-if="loading" class="gallery-loading" role="status">正在整理你的期刊书架…</div>
    <div v-else-if="loadError" class="gallery-loading" role="alert"><p>{{ loadError }}</p><el-button @click="loadJournals(searchQuery)">重新加载</el-button></div>
    <template v-else-if="journals.length">
      <ConcaveJournalCarousel v-model="selectedIndex" :items="galleryItems" />
      <section v-if="selectedJournal" class="journal-details" aria-label="当前期刊规范">
        <div class="details-heading">
          <div><p class="eyebrow">投稿之前，先了解它</p><h2>{{ selectedJournal.name }}</h2><p class="journal-domain">{{ selectedJournal.domain || '学科领域待补充' }}</p></div>
          <div class="details-actions"><a v-if="selectedJournal.author_guide_url" class="guide-link" :href="selectedJournal.author_guide_url" target="_blank" rel="noopener noreferrer">官方作者指南 ↗</a><el-button round type="primary" plain @click="viewSkill(selectedJournal)">查看期刊 Skill</el-button><el-button round @click="editJournal(selectedJournal)">编辑风格规则</el-button></div>
        </div>
        <div class="specs-grid">
          <div><span>英语规范</span><strong>{{ selectedJournal.english_variant === 'British' ? '英式英语' : selectedJournal.english_variant === 'American' ? '美式英语' : selectedJournal.english_variant || '未设定' }}</strong></div>
          <div><span>摘要字数上限</span><strong>{{ selectedJournal.abstract_word_limit ? `${selectedJournal.abstract_word_limit} 词` : '未设定' }}</strong></div>
          <div><span>引用格式</span><strong>{{ selectedJournal.citation_style || '未设定' }}</strong></div>
          <div><span>出版方</span><strong>{{ selectedJournal.publisher || '未设定' }}</strong></div>
        </div>
        <div v-if="selectedRules.length" class="style-notes"><div v-for="rule in selectedRules" :key="rule.label"><h3>{{ rule.label }}</h3><p>{{ rule.text }}</p></div></div>
        <div v-else class="no-rules">还没有录入写作风格规则，可根据官方作者指南补充。</div>
        <footer class="details-footer"><span>指南核验：{{ selectedJournal.guide_verified_date || '待核验' }} · 投稿前请以期刊最新官方要求为准</span><div class="cover-tools"><a v-if="coverSource" :href="coverSource" target="_blank" rel="noopener noreferrer">图片来源 ↗</a><span v-else-if="customCovers[selectedJournal.id]">自定义封面 · 保存在当前浏览器</span><span v-else>专属文字封面</span><button @click="coverInput?.click()">更换封面</button><button v-if="customCovers[selectedJournal.id]" @click="removeCustomCover">还原</button><input ref="coverInput" type="file" accept="image/png,image/jpeg,image/webp" aria-label="上传当前期刊的封面图片" hidden @change="uploadCover" /></div></footer>
      </section>
      <p class="gallery-hint">拖动封面，探索更多期刊 · 左右方向键也可切换</p>
    </template>
    <el-empty v-else :description="searchQuery ? '没有找到匹配的期刊，换个关键词试试' : '还没有期刊，添加第一本吧'" />

    <JournalSkillDialog v-model="showSkill" :journal-id="skillJournal?.id ?? null" :journal-name="skillJournal?.name || ''" />

    <!-- 添加/编辑期刊对话框 -->
    <el-dialog v-model="showDialog" :title="editingId ? '编辑期刊' : '添加期刊'" width="680px">
      <el-form :model="form" label-width="110px">
        <el-row :gutter="16">
          <el-col :span="16">
            <el-form-item label="期刊名称" required>
              <el-input v-model="form.name" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="缩写">
              <el-input v-model="form.abbreviation" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="出版商">
              <el-input v-model="form.publisher" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="学科领域">
              <el-input v-model="form.domain" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="期刊主页 URL">
          <el-input v-model="form.homepage_url" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="作者指南 URL">
          <el-input v-model="form.author_guide_url" placeholder="https://..." />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="英语规范">
              <el-select v-model="form.english_variant" style="width:100%">
                <el-option label="American English" value="American" />
                <el-option label="British English" value="British" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="摘要字数上限">
              <el-input-number v-model="form.abstract_word_limit" :min="0" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="引用格式">
              <el-select v-model="form.citation_style" style="width:100%">
                <el-option label="Vancouver" value="Vancouver" />
                <el-option label="APA" value="APA" />
                <el-option label="IEEE" value="IEEE" />
                <el-option label="Chicago" value="Chicago" />
                <el-option label="Harvard" value="Harvard" />
                <el-option label="其他" value="Other" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 风格规则 JSON 编辑 -->
        <el-form-item label="风格规则">
          <div style="width:100%">
            <el-input
              v-model="styleRulesJson"
              type="textarea"
              :rows="6"
              placeholder='从官方指南归纳，例如：
{
  "tense": "过去式描述实验，现在式讨论结论",
  "voice": "优先使用主动语态",
  "abbreviations": "首次出现须全称，括号内注明缩写",
  "other": ["避免过长句子", "专业术语需首次解释"]
}'
            />
            <div style="font-size:12px; color:#aaa; margin-top:4px;">
              ⚠ 风格规则应从目标期刊官方作者指南归纳，并记录核验日期
            </div>
          </div>
        </el-form-item>
        <el-form-item label="指南核验日期">
          <el-input v-model="form.guide_verified_date" placeholder="如：2024-10" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" @click="saveJournal" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import TextType from '../components/TextType.vue'
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Search, ArrowLeft } from '@element-plus/icons-vue'
import { journalsApi } from '../api'
import ConcaveJournalCarousel from '../components/ConcaveJournalCarousel.vue'
import JournalSkillDialog from '../components/JournalSkillDialog.vue'
import { journalCover } from '../data/journalCovers'

const journals = ref<any[]>([])
const selectedIndex = ref(0)
const showSkill = ref(false)
const skillJournal = ref<{ id: number; name: string } | null>(null)
function viewSkill(journal: any) {
  skillJournal.value = { id: journal.id, name: journal.name }
  showSkill.value = true
}
const loadError = ref('')
const coverInput = ref<HTMLInputElement>()
const customCovers = ref<Record<string, string>>({})
try { customCovers.value = JSON.parse(localStorage.getItem('academic-qa-journal-covers') || '{}') } catch { /* Private mode or malformed cache: use publisher covers. */ }
const selectedJournal = computed(() => journals.value[selectedIndex.value])
const galleryItems = computed(() => journals.value.map(j => ({
  id: j.id, title: j.name, subtitle: j.publisher,
  ...journalCover(j.name), image: customCovers.value[j.id] || journalCover(j.name).image,
})))
const coverSource = computed(() => selectedJournal.value && !customCovers.value[selectedJournal.value.id] ? journalCover(selectedJournal.value.name).source : undefined)
const selectedRules = computed(() => {
  const rules = selectedJournal.value?.style_rules || {}
  const labels: Record<string, string> = { tense: '时态', voice: '表达与语态', abbreviations: '术语与缩写', other: '其他写作要求' }
  return Object.entries(rules).filter(([key, value]) => key !== 'cover_image' && value).map(([key, value]) => ({
    label: labels[key] || key,
    text: Array.isArray(value) ? value.join('；') : typeof value === 'object' ? JSON.stringify(value) : String(value),
  }))
})
function persistCovers(next: Record<string, string>) {
  try { localStorage.setItem('academic-qa-journal-covers', JSON.stringify(next)); customCovers.value = next; return true }
  catch { ElMessage.error('浏览器存储空间不足，请使用更小的图片'); return false }
}
function uploadCover(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  const journalId = selectedJournal.value?.id
  if (!file || !journalId) return
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 2 * 1024 * 1024) {
    ElMessage.warning('请选择 2 MB 以内的 JPG、PNG 或 WebP 图片'); return
  }
  const reader = new FileReader()
  reader.onload = () => { if (persistCovers({ ...customCovers.value, [journalId]: String(reader.result) })) ElMessage.success('期刊封面已更新，保存在当前浏览器') }
  reader.onerror = () => ElMessage.error('图片读取失败，请重试')
  reader.readAsDataURL(file)
}
function removeCustomCover() {
  const next = { ...customCovers.value }; delete next[selectedJournal.value.id]; persistCovers(next)
}
function openCreate() { resetForm(); showDialog.value = true }

const loading = ref(false)
const searchQuery = ref('')
const showDialog = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const styleRulesJson = ref('')

const form = ref({
  name: '', abbreviation: '', publisher: '', domain: '',
  homepage_url: '', author_guide_url: '', english_variant: 'American',
  abstract_word_limit: undefined as number | undefined,
  citation_style: '', guide_verified_date: '',
  style_rules: null as any,
})

const resetForm = () => {
  form.value = {
    name: '', abbreviation: '', publisher: '', domain: '',
    homepage_url: '', author_guide_url: '', english_variant: 'American',
    abstract_word_limit: undefined, citation_style: '',
    guide_verified_date: '', style_rules: null,
  }
  styleRulesJson.value = ''
  editingId.value = null
}

const loadJournals = async (search?: string) => {
  loading.value = true
  loadError.value = ''
  try {
    journals.value = await journalsApi.list({ search, limit: 100 }) as any[]
    selectedIndex.value = 0
  } catch (e: any) {
    loadError.value = e.message || '期刊加载失败，请检查服务后重试'
  } finally {
    loading.value = false
  }
}

let searchTimeout: any
const debouncedSearch = () => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => loadJournals(searchQuery.value || undefined), 300)
}

const editJournal = (journal: any) => {
  editingId.value = journal.id
  Object.assign(form.value, journal)
  styleRulesJson.value = journal.style_rules ? JSON.stringify(journal.style_rules, null, 2) : ''
  showDialog.value = true
}

const saveJournal = async () => {
  if (!form.value.name) {
    ElMessage.warning('请填写期刊名称')
    return
  }
  // 解析 JSON 风格规则
  if (styleRulesJson.value) {
    try {
      form.value.style_rules = JSON.parse(styleRulesJson.value)
    } catch {
      ElMessage.error('风格规则 JSON 格式不正确')
      return
    }
  }
  saving.value = true
  try {
    if (editingId.value) {
      const updated = await journalsApi.update(editingId.value, form.value) as any
      const idx = journals.value.findIndex(j => j.id === editingId.value)
      if (idx >= 0) journals.value[idx] = updated
    } else {
      const j = await journalsApi.create(form.value) as any
      journals.value.unshift(j)
    }
    showDialog.value = false
    resetForm()
    ElMessage.success('期刊信息已保存')
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

onMounted(() => loadJournals())
onBeforeUnmount(() => clearTimeout(searchTimeout))
</script>

<style scoped>
.journals-view { max-width: 1240px; margin: 0 auto; }
.journal-back { display: flex; align-items: center; justify-content: space-between; margin-bottom: 44px; }
.journal-back .bar-hint { letter-spacing: 2px; font-size: 10px; }
.journal-heading { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 46px; }
.eyebrow { font-size: 11px; color: #86868b; letter-spacing: 1.5px; margin: 0 0 14px; }
.journal-heading h1 { font-size: clamp(30px, 4vw, 48px); line-height: 1.2; font-weight: 650; letter-spacing: -2px; color: #1d1d1f; margin: 0; }
.heading-desc { color: #86868b; font-size: 14px; line-height: 1.7; margin: 18px 0 0; }
.journal-heading > .el-button { height: 40px; padding: 0 20px; }
.collection-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 24px; border-top: 1px solid #dedee3; padding-top: 24px; }
.collection-label { color: #1d1d1f; font-size: 14px; font-weight: 600; }
.collection-count { margin-left: 14px; font-size: 12px; color: #86868b; }
.collection-toolbar > .el-input { width: 264px; }
.collection-toolbar :deep(.el-input__wrapper) { border-radius: 24px; background: #eaeaefaa; box-shadow: none; padding: 4px 14px; }
.gallery-loading { display: grid; justify-items: center; align-content: center; min-height: 420px; gap: 12px; color: #86868b; }
.journal-details { background: #fff; border: 1px solid #e7e7ec; border-radius: 24px; padding: 32px 36px 20px; margin-top: 36px; }
.details-heading { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 24px; padding-bottom: 28px; }
.details-heading .eyebrow { margin-bottom: 8px; font-size: 10px; }
.details-heading h2 { font-size: 24px; line-height: 1.3; font-weight: 600; color: #1d1d1f; letter-spacing: -.7px; margin: 0; text-wrap: balance; }
.journal-domain { font-size: 12px; color: #86868b; margin: 10px 0 0; }
.details-actions { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; max-width: 100%; }
.details-actions .el-button + .el-button { margin-left: 0; }
.guide-link { font-size: 12px; color: #0071e3; text-decoration: none; }
.specs-grid { display: grid; grid-template-columns: 1fr 1fr 1.2fr 1.5fr; padding: 22px 0; border-top: 1px solid #eeeef1; border-bottom: 1px solid #eeeef1; gap: 24px; }
.specs-grid > div { display: flex; flex-direction: column; gap: 10px; }
.specs-grid span { font-size: 11px; color: #86868b; }
.specs-grid strong { font-size: 13px; font-weight: 500; line-height: 1.5; color: #1d1d1f; }
.style-notes { display: grid; grid-template-columns: 1fr 1fr; gap: 22px 36px; padding: 26px 0; }
.style-notes h3 { font-size: 12px; font-weight: 600; color: #1d1d1f; margin: 0 0 8px; }
.style-notes p { font-size: 12px; line-height: 1.9; color: #6e6e73; margin: 0; }
.no-rules { padding: 28px 0; color: #86868b; font-size: 13px; }
.details-footer { border-top: 1px solid #eeeef1; padding-top: 16px; color: #98989d; font-size: 10px; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; line-height: 1.7; }
.cover-tools { display: flex; align-items: center; gap: 10px; }
.cover-tools a, .cover-tools button { color: #86868b; font-size: 10px; text-decoration: none; }
.cover-tools button { border: 0; background: transparent; padding: 0; cursor: pointer; color: #0071e3; }
.gallery-hint { text-align: center; font-size: 10px; letter-spacing: .5px; color: #98989d; margin: 22px 0 12px; }
@media (max-width: 800px) {
  .details-heading { align-items: flex-start; flex-direction: column; }
  .specs-grid { grid-template-columns: 1fr 1fr; }
  .journal-details { padding: 26px 24px 20px; }
}
@media (max-width: 600px) {
  .journal-back { margin-bottom: 30px; }
  .journal-back .bar-hint { display: none; }
  .journal-heading { flex-direction: column; align-items: flex-start; gap: 20px; margin-bottom: 28px; }
  .journal-heading h1 { letter-spacing: -1px; }
  .heading-desc { font-size: 12px; margin-top: 12px; }
  .collection-toolbar { align-items: flex-start; flex-direction: column; gap: 16px; }
  .collection-toolbar > .el-input { width: 100%; }
  .style-notes { grid-template-columns: 1fr; gap: 20px; }
  .journal-details { padding: 24px 20px 18px; margin-top: 28px; }
  .details-heading h2 { font-size: 22px; }
  .details-actions { flex-wrap: wrap; gap: 12px; }
  :deep(.el-dialog) { max-width: calc(100vw - 24px); }
}
</style>
