<template>
  <div class="project-detail">
    <!-- Apple-style Sub-navigation Bar -->
    <ProjectHeaderNav :project-id="id" current-tab="overview" :project-name="project?.name" />

    <div v-if="loading" ><el-skeleton :rows="6" animated /></div>
    <template v-else-if="project">
      <!-- 项目头部 -->
      <div class="project-header card mb-24">
        <div class="flex-between">
          <div>
            <div class="project-title">{{ project.name }}</div>
            <div class="project-sub">
              <el-tag v-if="project.domain" type="info" size="small">{{ project.domain }}</el-tag>
              <el-tag v-if="project.article_type" size="small" type="success">{{ project.article_type }}</el-tag>
              <el-tag v-if="project.translation_model" size="small">{{ project.translation_model }}</el-tag>
            </div>
          </div>
          <div class="flex gap-8">
            <el-button @click="$router.push(`/project/${id}/terminology`)">
              <el-icon><Search /></el-icon> 术语查证
            </el-button>
            <el-button type="primary" @click="$router.push(`/project/${id}/translate`)">
              <el-icon><EditPen /></el-icon> 翻译工作台
            </el-button>
            <el-button type="warning" @click="$router.push(`/project/${id}/proofread`)">
              <el-icon><Checked /></el-icon> 校对报告
            </el-button>
            <el-button type="danger" plain @click="handleDeleteProject">
              <el-icon><Delete /></el-icon> 删除项目
            </el-button>
          </div>
        </div>
      </div>

      <!-- 统计卡片 -->
      <div class="stat-grid mb-24">
        <div class="stat-card">
          <div class="stat-label">总段落数</div>
          <div class="stat-value">{{ stats?.segments?.total || 0 }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">已翻译</div>
          <div class="stat-value">{{ stats?.segments?.translated || 0 }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">已审定</div>
          <div class="stat-value">{{ stats?.segments?.approved || 0 }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">待处理</div>
          <div class="stat-value">{{ stats?.segments?.pending || 0 }}</div>
        </div>
        <div class="stat-card danger">
          <div class="stat-label">FLAG 标记</div>
          <div class="stat-value">{{ stats?.segments?.flagged || 0 }}</div>
        </div>
        <div class="stat-card danger">
          <div class="stat-label">待裁决问题</div>
          <div class="stat-value">{{ stats?.issues?.by_status?.pending || 0 }}</div>
        </div>
      </div>

      <!-- 进度 -->
      <div class="card mb-24">
        <div class="flex-between mb-16">
          <strong>翻译进度</strong>
          <span style="color: #888">{{ stats?.progress_percent || 0 }}%</span>
        </div>
        <el-progress :percentage="stats?.progress_percent || 0" :stroke-width="16" :format="() => ''" />
      </div>

      <JournalSkillPicker :model-value="project.journal_id" :enabled="project.style_skill_enabled" :domain="project.domain || ''" :disabled="journalSaving" @change="saveJournalSkill" />

      <!-- 上传文档区域 -->
      <div class="card mb-24">
        <div class="flex-between mb-16">
          <strong>📎 上传论文文档</strong>
          <span class="text-secondary" style="font-size: 13px;">支持 PDF、DOCX、TXT</span>
        </div>

        <el-upload
          drag
          :action="`http://127.0.0.1:8000/api/v1/documents/upload/${id}`"
          :on-success="handleUploadSuccess"
          :on-error="handleUploadError"
          :before-upload="beforeUpload"
          :show-file-list="true"
          accept=".pdf,.docx,.doc,.txt"
        >
          <el-icon class="el-icon--upload" size="48"><UploadFilled /></el-icon>
          <div class="el-upload__text">
            拖放文件到此处，或 <em>点击上传</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">上传后自动分段 → AI 识别疑似专业术语 → 查期刊文章 → 查一级、二级信源。请使用已配置的真实 AI 模型。</div>
          </template>
        </el-upload>

        <!-- 已上传文档列表 -->
        <div v-if="documents.length > 0" class="uploaded-docs mt-16">
          <el-table :data="documents" size="small">
            <el-table-column prop="filename" label="文件名" />
            <el-table-column prop="file_type" label="类型" width="80" />
            <el-table-column label="解析状态" width="100">
              <template #default="{ row }">
                <el-tag :type="parseStatusType(row.parse_status)" size="small">
                  {{ parseStatusLabel(row.parse_status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="word_count" label="字数" width="80" />
            <el-table-column prop="segment_count" label="段落数" width="80" />
          </el-table>
        </div>
      </div>

      <TermDiscoveryPanel :project-id="id" @changed="refreshDocuments" />

    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, EditPen, Checked, UploadFilled, Delete } from '@element-plus/icons-vue'
import ProjectHeaderNav from '../components/ProjectHeaderNav.vue'
import { projectsApi, documentsApi } from '../api'
import JournalSkillPicker from '../components/JournalSkillPicker.vue'
import TermDiscoveryPanel from '../components/TermDiscoveryPanel.vue'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))
const project = ref<any>(null)
const stats = ref<any>(null)
const documents = ref<any[]>([])
const loading = ref(false)
const journalSaving = ref(false)
const handleDeleteProject = async () => {
  if (!project.value) return
  await ElMessageBox.confirm(
    `确定要删除项目「${project.value.name}」吗？包含的所有文档、段落和记录将被彻底清除，此操作不可撤销。`,
    '删除确认',
    { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
  )
  try {
    await projectsApi.delete(id.value)
    ElMessage.success('项目已成功删除')
    router.push('/')
  } catch (e: any) {
    ElMessage.error('删除失败: ' + e.message)
  }
}

const parseStatusType = (s: string) => ({ pending: 'info', parsing: 'warning', done: 'success', error: 'danger' }[s] || 'info')
const parseStatusLabel = (s: string) => ({ pending: '等待中', parsing: '解析中', done: '已完成', error: '解析错误' }[s] || s)

const loadProject = async () => {
  loading.value = true
  try {
    const [p, s, docs] = await Promise.all([
      projectsApi.get(id.value),
      projectsApi.stats(id.value),
      documentsApi.listByProject(id.value),
    ]) as any[]
    project.value = p
    stats.value = s
    documents.value = docs
  } catch (e: any) {
    ElMessage.error('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

const saveJournalSkill = async (values: { journal_id: number | null; style_skill_enabled: boolean }) => {
  if (journalSaving.value) return
  journalSaving.value = true
  try {
    project.value = await projectsApi.update(id.value, values)
    ElMessage.success(values.journal_id && values.style_skill_enabled ? '期刊风格 Skill 已保存，后续翻译生效' : '期刊风格设置已保存')
  } catch (e: any) {
    ElMessage.error('期刊设置保存失败：' + e.message)
  } finally {
    journalSaving.value = false
  }
}

const beforeUpload = (file: File) => {
  const allowed = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain']
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!['pdf', 'docx', 'doc', 'txt'].includes(ext || '')) {
    ElMessage.error('仅支持 PDF、DOCX、TXT 格式')
    return false
  }
  return true
}

const handleUploadSuccess = () => {
  ElMessage.success('上传成功，解析后将自动识别术语并查证，可进入「术语查证」查看进度')
  setTimeout(() => loadProject(), 2000)
}

const refreshDocuments = async () => {
  try {
    const [docs, currentStats] = await Promise.all([documentsApi.listByProject(id.value), projectsApi.stats(id.value)])
    documents.value = docs
    stats.value = currentStats
  } catch { /* The discovery panel displays connection failures. */ }
}

const handleUploadError = () => {
  ElMessage.error('文件上传失败，请检查后端服务是否运行')
}

onMounted(() => {
  loadProject()
})
</script>

<style scoped>
.project-title {
  font-size: 20px;
  font-weight: 700;
  color: #1a1a2e;
  margin-bottom: 8px;
}

.project-sub {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.mt-8 { margin-top: 8px; }
.mt-16 { margin-top: 16px; }
.text-secondary { color: #888; }

.uploaded-docs {
  border-top: 1px solid #f0f4f8;
  padding-top: 16px;
}

.journal-option-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 4px 0;
  gap: 16px;
}

.journal-option-title {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.j-name {
  font-weight: 600;
  color: #1a1a2e;
}

.j-abbr {
  font-size: 12px;
  color: #888;
}

.journal-option-tags {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-shrink: 0;
}

.style-rules-box {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 10px 14px;
}
</style>
