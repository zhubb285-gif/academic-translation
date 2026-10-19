<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { modelsApi } from '../api'
import ModelOrbit, { type OrbitItem } from '../components/ModelOrbit.vue'
import ModelIdentity from '../components/ModelIdentity.vue'

import { PROVIDERS, type Provider, defaultModel } from '../data/modelProviders'
const VISIBLE_PROVIDERS = PROVIDERS.filter(p => p.id !== 'custom')
const PRESETS = PROVIDERS.flatMap(p => p.models.map(m => ({ ...m, provider: p.id, capabilities: [] as string[], supports_json_mode: false, use_for_translation: true, use_for_proofreading: true })))
const configs = ref<any[]>([])
const loading = ref(true)
const loadingKeys = ref(true)
const loadError = ref('')
const keysError = ref('')
const apiKeys = ref<Record<string, string>>({})
const showDialog = ref(false)
const dialogKind = ref<'provider' | 'model'>('model')
const editingId = ref<number | null>(null)
const saving = ref(false)
const testing = ref(false)
const showKey = ref(false)
const testResult = ref<{ success: boolean; latency_ms?: number; error?: string } | null>(null)
const draftKey = ref('')
const draftBase = ref('')
const defaultForm = () => ({ name: '', provider: 'custom' as Provider, model_id: '', api_base_url: '', context_window: undefined as number | undefined, capabilities: [] as string[], cost_per_1k_input: undefined as number | undefined, cost_per_1k_output: undefined as number | undefined, supports_json_mode: false, use_for_translation: true, use_for_proofreading: true })
const form = ref(defaultForm())
const tagText = ref('')
const activeProvider = computed(() => PROVIDERS.find(p => p.id === form.value.provider) || PROVIDERS[PROVIDERS.length - 1]!)
const knownProvider = computed(() => PROVIDERS.some(p => p.id === form.value.provider))
const providerConfigured = (id: string) => Boolean(apiKeys.value[`${id}_api_key`]?.trim())
const connectedCount = computed(() => PROVIDERS.filter(p => providerConfigured(p.id)).length)
const available = computed(() => {
  const result = [...configs.value]
  for (const preset of PRESETS) if (!result.some(c => c.provider === preset.provider && c.model_id === preset.model_id)) result.push({ ...preset })
  return result
})
function displayName(config: any) {
  return PRESETS.find(p => p.model_id === config.model_id && p.provider === config.provider)?.name || config.name
}
const providerModels = computed(() => available.value.filter(c => c.provider === form.value.provider))
const orbitItems = computed<OrbitItem[]>(() => VISIBLE_PROVIDERS.map(p => ({
  key: `provider-${p.id}`, title: p.name, label: p.name, provider: p.id,
  tone: p.tone, caption: 'MODEL PROVIDER', configured: providerConfigured(p.id), kind: 'provider',
})))
const selectedModelKey = computed(() => `${form.value.provider}/${form.value.model_id}`)
let initialModel = ''
async function chooseModel(config?: any) {
  if (saving.value || testing.value) return
  if (dialogKind.value === 'model' && JSON.stringify([form.value, tagText.value]) !== initialModel) {
    try { await ElMessageBox.confirm('当前型号的参数尚未保存，切换会放弃这些参数修改。', '切换型号', { confirmButtonText: '切换', cancelButtonText: '继续编辑', customClass: 'palette-confirm' }) } catch { return }
  }
  const key = draftKey.value, base = draftBase.value
  openModel(config || { ...defaultForm(), provider: form.value.provider })
  draftKey.value = key; draftBase.value = base
}
function syncDraft() {
  draftKey.value = apiKeys.value[`${form.value.provider}_api_key`] || ''
  draftBase.value = apiKeys.value[`${form.value.provider}_base_url`] ?? activeProvider.value.base
  testResult.value = null; showKey.value = false
}
watch(() => form.value.provider, syncDraft)
watch([draftKey, draftBase, () => form.value.model_id, () => form.value.api_base_url], () => { testResult.value = null })
function openProvider(provider: string) {
  dialogKind.value = 'provider'; editingId.value = null
  form.value = { ...defaultForm(), provider: provider as Provider }
  syncDraft(); showDialog.value = true
}
function openModel(config: any) {
  dialogKind.value = 'model'; editingId.value = config.id || null
  form.value = { ...defaultForm(), ...config, api_base_url: config.api_base_url || '', capabilities: [...(config.capabilities || [])] }
  tagText.value = form.value.capabilities.join('、')
  initialModel = JSON.stringify([form.value, tagText.value])
  syncDraft(); showDialog.value = true
}
function openCreate() { openModel(defaultForm()) }
function selectItem(item: OrbitItem) { item.kind === 'provider' ? openProvider(item.provider) : openModel(item.config) }
async function loadConfigs() {
  loading.value = true; loadError.value = ''
  try { configs.value = await modelsApi.list() }
  catch (e: any) { loadError.value = e.message || '模型列表加载失败' }
  finally { loading.value = false }
}
async function loadKeys() {
  loadingKeys.value = true; keysError.value = ''
  try { apiKeys.value = await modelsApi.getKeys(); if (showDialog.value) syncDraft() }
  catch { keysError.value = '连接设置加载失败，请重试后再修改，以免覆盖已有配置。' }
  finally { loadingKeys.value = false }
}
async function testConnection() {
  testResult.value = null
  if (!knownProvider.value) { testResult.value = { success: false, error: '请先选择受支持的服务商' }; return }
  if (!draftKey.value.trim()) { testResult.value = { success: false, error: '请先填写 API Key' }; return }
  if (form.value.provider === 'custom' && !draftBase.value.trim()) { testResult.value = { success: false, error: '请先填写兼容接口的 Base URL' }; return }
  testing.value = true
  try {
    const fallback = defaultModel(form.value.provider)
    if (!form.value.model_id.trim() && !fallback) { testResult.value = { success: false, error: '请先填写控制台提供的模型 ID' }; return }
    testResult.value = await modelsApi.testProvider({ provider: form.value.provider, api_key: draftKey.value.trim(), base_url: draftBase.value.trim(), model: form.value.model_id.trim() || fallback })
  } catch (e: any) { testResult.value = { success: false, error: e.message } }
  finally { testing.value = false }
}
function validUrl(value: string) {
  if (!value.trim()) return true
  try { return ['http:', 'https:'].includes(new URL(value.trim()).protocol) } catch { return false }
}
async function saveDialog() {
  if (saving.value || loadingKeys.value || keysError.value) return
  if (!knownProvider.value) { ElMessage.warning('请选择受支持的服务商'); return }
  if (!validUrl(draftBase.value) || !validUrl(form.value.api_base_url)) { ElMessage.warning('接口地址须以 http:// 或 https:// 开头'); return }
  if (form.value.provider === 'custom' && !draftBase.value.trim() && (draftKey.value || dialogKind.value === 'provider')) { ElMessage.warning('请填写兼容接口的 Base URL'); return }
  if (dialogKind.value === 'model' && (!form.value.name.trim() || !form.value.model_id.trim())) { ElMessage.warning('请填写模型名称和模型 ID'); return }
  saving.value = true
  let connectionSaved = false
  try {
    const provider = form.value.provider
    const next = { ...apiKeys.value, [`${provider}_api_key`]: draftKey.value.trim() }
    if (provider !== 'anthropic') next[`${provider}_base_url`] = draftBase.value.trim()
    const changed = next[`${provider}_api_key`] !== (apiKeys.value[`${provider}_api_key`] || '') || (provider !== 'anthropic' && next[`${provider}_base_url`] !== (apiKeys.value[`${provider}_base_url`] || ''))
    if (changed) { await modelsApi.saveKeys({ [`${provider}_api_key`]: next[`${provider}_api_key`], ...(provider !== 'anthropic' ? { [`${provider}_base_url`]: next[`${provider}_base_url`] } : {}) }); apiKeys.value = next; connectionSaved = true }
    if (dialogKind.value === 'model') {
      const data = { ...form.value, name: form.value.name.trim(), model_id: form.value.model_id.trim(), api_base_url: form.value.api_base_url.trim() || null, context_window: form.value.context_window || null, cost_per_1k_input: typeof form.value.cost_per_1k_input === 'number' ? form.value.cost_per_1k_input : null, cost_per_1k_output: typeof form.value.cost_per_1k_output === 'number' ? form.value.cost_per_1k_output : null, capabilities: tagText.value.split(/[、,，]/).map(t => t.trim()).filter(Boolean) }
      if (editingId.value) {
        const updated = await modelsApi.update(editingId.value, data)
        configs.value = configs.value.map(c => c.id === editingId.value ? updated : c)
      } else { configs.value = [...configs.value, await modelsApi.create(data)] }
    }
    showDialog.value = false
    ElMessage.success(dialogKind.value === 'provider' ? '服务连接已保存' : '模型配置已保存')
  } catch (e: any) { ElMessage.error(`${connectionSaved ? '连接已保存，但模型参数保存失败：' : '保存失败：'}${e.message}`) }
  finally { saving.value = false }
}
async function deleteConfig() {
  if (!editingId.value || saving.value) return
  try { await ElMessageBox.confirm(`删除模型配置「${form.value.name}」？服务商 API Key 会保留。`, '移除模型', { confirmButtonText: '移除', cancelButtonText: '保留', customClass: 'palette-confirm', type: 'warning' }) } catch { return }
  saving.value = true
  try { await modelsApi.delete(editingId.value); configs.value = configs.value.filter(c => c.id !== editingId.value); showDialog.value = false; ElMessage.success('模型配置已移除') }
  catch (e: any) { ElMessage.error(e.message) }
  finally { saving.value = false }
}
function beforeClose(done: () => void) { if (!saving.value && !testing.value) done() }
onMounted(() => { loadConfigs(); loadKeys() })
</script>

<template>
  <div class="models-palette">
    <div class="palette-topline"><router-link to="/workspace">← 返回工作台</router-link><span>MODEL SETTINGS / 模型设置</span></div>
    <div v-if="loading || loadError" class="palette-loading" :role="loadError ? 'alert' : 'status'"><p>{{ loadError || '正在加载你的模型工作组…' }}</p><button v-if="loadError" class="quiet-button" @click="loadConfigs">重新加载</button></div>
    <ModelOrbit v-else :items="orbitItems" :paused="showDialog" light @select="selectItem" />
    <div class="collective-footer">
      <div><span class="section-index">01 — 你的模型工作组</span><p>{{ configs.length }} 个已启用模型<span class="separator">/</span>{{ connectedCount }} 个已配置连接</p></div>
      <button class="palette-add" @click="openCreate">添加自己的模型 <span aria-hidden="true">↗</span></button>
    </div>
    <div v-if="keysError" class="keys-error" role="alert">{{ keysError }} <button @click="loadKeys">重新加载</button></div>


    <el-dialog v-model="showDialog" class="palette-model-dialog" width="720px" :before-close="beforeClose" :close-on-click-modal="false" :close-on-press-escape="!saving && !testing" destroy-on-close @closed="showKey = false; testResult = null">
      <template #header="{ titleId }"><div class="dialog-intro"><div class="dialog-brand" :class="`brand-${activeProvider.tone}`"><ModelIdentity :provider="form.provider" /></div><div><span class="dialog-eyebrow">{{ dialogKind === 'provider' ? 'API CONNECTION / 服务连接' : editingId ? 'YOUR MODEL / 模型配置' : 'NEW COLLABORATOR / 添加模型' }}</span><h2 :id="titleId">{{ activeProvider.name }}</h2><p>{{ activeProvider.description }}</p></div></div></template>
      <form id="palette-model-form" class="palette-form" @submit.prevent="saveDialog">
        <div v-if="keysError || loadingKeys" class="dialog-alert" role="status">{{ keysError || '正在读取服务连接…' }}<button v-if="keysError" type="button" @click="loadKeys">重试</button></div>
        <fieldset :disabled="saving || testing || loadingKeys || Boolean(keysError)">
          <section class="provider-model-picker" aria-label="选择厂家的具体型号">
            <div class="form-section-title"><span>选择具体型号</span><span>型号可用性以你的账户为准</span></div>
            <div class="model-choices"><button v-for="model in providerModels" :key="model.id || model.model_id" type="button" :class="{ selected: dialogKind === 'model' && selectedModelKey === `${model.provider}/${model.model_id}` }" :aria-pressed="dialogKind === 'model' && selectedModelKey === `${model.provider}/${model.model_id}`" @click="chooseModel(model)">{{ displayName(model) }}<small>{{ model.id ? '已添加' : '预设' }}</small></button><button type="button" @click="chooseModel()">＋ 添加其他型号</button></div>
            <p v-if="!providerModels.length" class="field-help">点击「添加其他型号」，粘贴控制台中的准确模型 ID。</p>
          </section>
          <template v-if="dialogKind === 'model'">
            <div class="field-pair"><label for="model-name">模型名称<input id="model-name" v-model="form.name" required maxlength="200" placeholder="给模型起一个易识别的名字" /></label><label for="model-provider">服务商<select id="model-provider" v-model="form.provider" required><option v-for="provider in PROVIDERS" :key="provider.id" :value="provider.id">{{ provider.name }}</option><option v-if="!knownProvider" :value="form.provider" disabled>{{ form.provider }}（请选择受支持的服务商）</option></select></label></div>
            <label for="model-id">模型 ID<input id="model-id" v-model="form.model_id" required maxlength="300" spellcheck="false" placeholder="填写服务商提供的准确模型 ID" /><span class="field-help">模型名称可自定义，模型 ID 必须与接口提供的标识一致。</span></label>
          </template>
          <div class="form-section-title"><span>01 / 服务连接</span><span>同服务商模型共享</span></div>
          <label for="model-key">API Key<div class="password-field"><input id="model-key" v-model="draftKey" :type="showKey ? 'text' : 'password'" autocomplete="new-password" spellcheck="false" placeholder="输入服务商的 API Key" /><button type="button" :aria-pressed="showKey" :aria-label="showKey ? '隐藏 API Key' : '显示 API Key'" @click="showKey = !showKey">{{ showKey ? '隐藏' : '显示' }}</button></div></label>
          <label v-if="form.provider !== 'anthropic'" for="model-base">Base URL<input id="model-base" v-model="draftBase" type="url" spellcheck="false" :required="form.provider === 'custom' && dialogKind === 'provider'" :placeholder="activeProvider.base || 'https://你的服务地址/v1'" /><span class="field-help">修改这里会同步影响使用该服务商的模型。</span></label>
          <label v-if="dialogKind === 'provider'" for="connection-model-id">测试用模型 ID<input id="connection-model-id" v-model="form.model_id" spellcheck="false" :required="form.provider === 'custom'" :placeholder="defaultModel(form.provider) || '填写控制台中的模型 ID'" /></label>
          <div class="connection-test"><button type="button" class="quiet-button" @click="testConnection">{{ testing ? '正在测试…' : '测试连接 ↗' }}</button><span>测试会向所填接口发送一次简短请求。</span></div>
          <div v-if="testResult" class="connection-result" :class="testResult.success ? 'result-ok' : 'result-error'" role="status">{{ testResult.success ? `连接成功 · ${testResult.latency_ms ?? '—'} ms` : `连接失败：${testResult.error || '请检查密钥、接口和模型 ID'}` }}</div>
          <template v-if="dialogKind === 'model'">
            <div class="form-section-title"><span>02 / 模型分工</span><span>为翻译流程选择用途</span></div>
            <div class="usage-options"><label><input v-model="form.use_for_translation" type="checkbox" /><span>用于翻译<small>生成与修改译文</small></span></label><label><input v-model="form.use_for_proofreading" type="checkbox" /><span>用于独立校对<small>检查准确性与表达</small></span></label></div>
            <details class="advanced-fields"><summary>更多参数 <span>＋</span></summary><div class="advanced-body"><label for="model-tags">能力说明<input id="model-tags" v-model="tagText" placeholder="用顿号分隔，如：长文处理、术语核对" /><span class="field-help">由你填写，供同学选择模型参考；不是经过测评的能力排名。</span></label><div class="field-pair"><label for="model-context">上下文窗口（tokens）<input id="model-context" v-model.number="form.context_window" type="number" min="0" step="1000" placeholder="可选" /></label></div><div class="field-pair"><label for="model-input-price">输入估算（美元 / 千 tokens）<input id="model-input-price" v-model.number="form.cost_per_1k_input" type="number" min="0" step="any" placeholder="可选，自行维护" /></label><label for="model-output-price">输出估算（美元 / 千 tokens）<input id="model-output-price" v-model.number="form.cost_per_1k_output" type="number" min="0" step="any" placeholder="可选，自行维护" /></label></div><label class="inline-checkbox"><input v-model="form.supports_json_mode" type="checkbox" />支持结构化 JSON 输出</label></div></details>
          </template>
        </fieldset>
      </form>
      <template #footer><div class="dialog-footer"><button v-if="editingId && dialogKind === 'model'" class="remove-model" :disabled="saving || testing" @click="deleteConfig">移除模型</button><span v-else class="dialog-footer-note">按你的工作方式，安排模型。</span><div><button class="dialog-cancel" :disabled="saving || testing" @click="showDialog = false">取消</button><button type="submit" form="palette-model-form" class="dialog-save" :disabled="saving || testing || loadingKeys || Boolean(keysError)">{{ saving ? '正在保存…' : dialogKind === 'provider' ? '保存连接 ↗' : editingId ? '保存配置 ↗' : '保存并启用 ↗' }}</button></div></div></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.models-palette { background: #fff; color: #1d1d1f; padding: 28px 32px 54px; min-height: 780px; }
.palette-topline { display: flex; justify-content: space-between; align-items: center; max-width: 1136px; margin: 0 auto 12px; gap: 20px; }
.palette-topline a { color: #6e6e73; font-size: 11px; text-decoration: none; }
.palette-topline > span { font-size: 9px; letter-spacing: 1.5px; color: #86868b; }
.palette-loading { min-height: 590px; display: flex; align-items: center; justify-content: center; flex-direction: column; color: #6e6e73; font-size: 13px; }
.collective-footer { max-width: 880px; margin: 28px auto 0; display: flex; justify-content: space-between; align-items: center; gap: 24px; border-top: 1px solid #d2d2d7; padding: 24px 0 0; }
.section-index { font-size: 10px; color: #6e6e73; letter-spacing: 1px; }
.collective-footer p { font-size: 12px; font-weight: 400; margin: 9px 0 0; color: #1d1d1f; }
.separator { margin: 0 12px; color: #86868b; }
.palette-add { display: flex; align-items: center; gap: 30px; padding: 13px 19px; border: 1px solid #1d1d1f; border-radius: 7px; color: #fff; background: #1d1d1f; font-size: 12px; font-family: inherit; cursor: pointer; transition: background .2s; }
.palette-add:hover { background: #424245; }
.model-index { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px 18px; max-width: 880px; margin: 28px auto 0; }
.model-index button { display: inline-flex; align-items: center; gap: 7px; padding: 5px 0; font-size: 10px; color: #c4c3bd; border: 0; background: none; cursor: pointer; font-family: inherit; }
.model-index button:hover { color: #fff; }
.model-index button > span:first-child { width: 4px; height: 4px; border-radius: 50%; background: #74746f; }
.model-index button > span.enabled { background: #a6e0ba; }
.index-arrow { color: #b6b6b1; }
.palette-footnote { text-align: center; color: #a5a5a0; font-size: 10px; line-height: 1.8; margin: 18px auto 0; max-width: 640px; }
.keys-error { max-width: 880px; margin: 18px auto; padding: 12px; border: 1px solid #e4a68c55; font-size: 12px; color: #f1c4ae; }
.keys-error button,.dialog-alert button { border: 0; background: none; color: inherit; text-decoration: underline; cursor: pointer; }
.models-palette :is(button,a):focus-visible { outline: 2px solid #0066cc; outline-offset: 5px; }
.dialog-intro { display: flex; gap: 22px; align-items: center; padding: 6px 24px 22px 0; }
.dialog-brand { width: 70px; height: 76px; border-radius: 12px; padding: 15px; flex: none; transform: perspective(500px) rotateY(-16deg) rotateZ(-5deg); }
.brand-blue { color: #fff; background: #1948f0; --mark-eye: #1948f0; }
.brand-ivory { color: #121212; background: #eeede6; }
.brand-coral { color: #25130e; background: #e4a68c; }
.brand-lilac { color: #241d35; background: #c1b1ea; }
.brand-orange { color: #21120f; background: #ff613d; }
.brand-black { color: #f5f5ef; background: #030303; }
.model-choices { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.model-choices button { padding: 10px 12px; border: 1px solid #55554e; border-radius: 7px; background: #22221f; color: #eeede6; cursor: pointer; font: inherit; font-size: 12px; }
.model-choices button.selected { border-color: #d6ccff; background: #393249; }
.model-choices small { margin-left: 8px; color: #bcbcb6; font-size: 9px; }
.brand-green { color: #a6e0ba; background: #143936; }
.dialog-eyebrow { font-size: 9px; color: #b6b6b1; letter-spacing: 1.1px; }
.dialog-intro h2 { color: #f6f5f0; font-size: 26px; font-weight: 500; margin: 8px 0; line-height: 1.25; letter-spacing: -.8px; overflow-wrap: anywhere; }
.dialog-intro p { color: #b6b6b1; font-size: 11px; margin: 0; line-height: 1.7; }
.palette-form fieldset { padding: 0; margin: 0; border: 0; min-width: 0; display: grid; gap: 18px; }
.palette-form label { display: flex; flex-direction: column; gap: 8px; font-size: 11px; color: #dad9d2; line-height: 1.5; min-width: 0; }
.palette-form input:not([type=checkbox]),.palette-form select { width: 100%; min-width: 0; height: 42px; border-radius: 6px; border: 1px solid #50504b; background: #1c1c1a; color: #f6f5f0; font-size: 12px; font-family: inherit; padding: 10px 12px; box-shadow: none; color-scheme: dark; }
.palette-form input::placeholder { color: #a5a59f; opacity: 1; }
.palette-form input:focus-visible,.palette-form select:focus-visible { outline: 2px solid #bcc8ff; outline-offset: 2px; }
.palette-form fieldset:disabled { opacity: .6; }
.field-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.field-help { color: #b2b2ab; font-size: 10px; line-height: 1.7; }
.form-section-title { display: flex; justify-content: space-between; gap: 12px; align-items: center; font-size: 10px; letter-spacing: .7px; color: #c4c3bd; border-top: 1px solid #ffffff20; padding-top: 22px; margin-top: 5px; }
.form-section-title > span:last-child { font-size: 9px; color: #aaa9a3; letter-spacing: 0; }
.password-field { display: flex; position: relative; }
.password-field input { padding-right: 60px !important; }
.password-field button { position: absolute; right: 3px; top: 3px; bottom: 3px; padding: 0 11px; border: 0; border-radius: 4px; background: transparent; color: #d5d4ce; font-size: 10px; cursor: pointer; }
.password-field button:focus-visible { outline: 2px solid #bcc8ff; }
.connection-test { display: flex; align-items: center; flex-wrap: wrap; gap: 14px; }
.quiet-button { border: 1px solid #5b5b54; color: #f0efe9; padding: 9px 13px; border-radius: 6px; background: transparent; cursor: pointer; font: inherit; font-size: 11px; }
.connection-test > span { font-size: 9px; color: #aaa9a3; }
.connection-result { font-size: 11px; line-height: 1.7; padding: 11px 13px; border-radius: 5px; overflow-wrap: anywhere; }
.result-ok { color: #b2e7bb; background: #173022; }.result-error { color: #f5baa6; background: #3c221c; }
.usage-options { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.usage-options > label { flex-direction: row; align-items: center; gap: 12px; padding: 13px 14px; border: 1px solid #4b4b45; border-radius: 7px; cursor: pointer; }
.usage-options small { display: block; font-size: 9px; color: #aaa9a3; margin-top: 3px; }
.palette-form input[type=checkbox] { width: 15px; height: 15px; margin: 0; accent-color: #d6ccff; flex: none; }
.advanced-fields { border-top: 1px solid #ffffff20; margin-top: 2px; }
.advanced-fields summary { display: flex; align-items: center; justify-content: space-between; padding: 17px 0; font-size: 11px; color: #c4c3bd; cursor: pointer; list-style: none; }
.advanced-fields summary::-webkit-details-marker { display: none; }
.advanced-fields[open] summary > span { transform: rotate(45deg); }
.advanced-body { display: grid; gap: 18px; padding-bottom: 6px; }
.palette-form .inline-checkbox { flex-direction: row; align-items: center; gap: 10px; }
.dialog-alert { padding: 12px; margin: 0 0 18px; border-radius: 6px; background: #35271f; color: #f1c4ae; font-size: 11px; line-height: 1.7; }
.dialog-footer { display: flex; justify-content: space-between; align-items: center; gap: 16px; border-top: 1px solid #ffffff20; padding-top: 20px; }
.dialog-footer > div { display: flex; gap: 10px; }
.dialog-cancel,.dialog-save { border: 1px solid #55554e; border-radius: 6px; padding: 11px 18px; font-size: 11px; font-family: inherit; color: #f0efe9; background: none; cursor: pointer; }
.dialog-save { color: #151513; background: #f0efe9; border-color: #f0efe9; }
.dialog-footer-note { font-size: 9px; color: #aaa9a3; }
.remove-model { color: #e8ae98; font-size: 10px; background: none; border: 0; padding: 8px 0; cursor: pointer; }
.dialog-footer button:disabled { opacity: .5; cursor: wait; }
.palette-form :is(button,summary):focus-visible,.dialog-footer button:focus-visible { outline: 2px solid #bcc8ff; outline-offset: 3px; }
@media(max-width: 600px) {
  .models-palette { padding: 22px 16px 32px; min-height: auto; }
  .palette-topline { margin-bottom: 24px; gap: 10px; }.palette-topline > span { font-size: 8px; letter-spacing: .7px; }
  .collective-footer { margin-top: 24px; padding-top: 20px; gap: 18px; }
  .section-index { font-size: 9px; }.collective-footer p { font-size: 10px; }.separator { margin: 0 7px; }
  .palette-add { gap: 12px; font-size: 10px; padding: 11px 12px; }.model-index { gap: 7px 14px; margin-top: 22px; }.palette-footnote { font-size: 9px; text-align: left; }
  .dialog-intro { gap: 14px; }.dialog-brand { width: 52px; height: 58px; padding: 12px; }.dialog-intro h2 { font-size: 21px; }.dialog-eyebrow { font-size: 8px; }.dialog-intro p { font-size: 10px; }
  .field-pair { grid-template-columns: 1fr; gap: 18px; }.dialog-footer-note { display: none; }.dialog-footer > div { margin-left: auto; }.dialog-save,.dialog-cancel { padding: 10px 13px; }
  .usage-options { gap: 8px; }.usage-options > label { padding: 11px 8px; gap: 7px; font-size: 10px; }
}
@media(prefers-reduced-motion: reduce) { .palette-add { transition: none; } }
</style>

<style>
.palette-model-dialog.el-dialog { --el-dialog-bg-color: #fff; --el-text-color-primary: #1d1d1f; --el-text-color-regular: #424245; --el-dialog-padding-primary: 32px; border: 1px solid #d2d2d7; border-radius: 18px; padding: 32px; max-width: calc(100vw - 32px); color: #1d1d1f; box-shadow: 0 24px 80px #1d1d1f22; color-scheme: light; background: #fff !important; }
.palette-model-dialog .el-dialog__header { padding: 0 !important; margin: 0; }.palette-model-dialog .el-dialog__body { padding: 0 !important; }.palette-model-dialog .el-dialog__footer { padding: 20px 0 0 !important; }
.palette-model-dialog .el-dialog__headerbtn { top: 14px; right: 14px; width: 32px; height: 32px; }.palette-model-dialog .el-dialog__headerbtn .el-dialog__close { color: #424245; }.palette-model-dialog .el-dialog__headerbtn:focus-visible { outline: 2px solid #0066cc; outline-offset: 2px; }
.palette-confirm.el-message-box { --el-bg-color: #fff; --el-text-color-primary: #1d1d1f; --el-text-color-regular: #424245; --el-border-color: #d2d2d7; background: #fff; border-color: #d2d2d7; border-radius: 16px; max-width: calc(100vw - 32px); }
@media(max-width: 600px) { .palette-model-dialog.el-dialog { --el-dialog-padding-primary: 20px; padding: 24px 20px; max-width: calc(100vw - 24px); margin-top: 5vh !important; } }
</style>

<style scoped>
.models-palette .dialog-intro h2 { color: #1d1d1f; }
.models-palette .dialog-intro p, .models-palette .dialog-eyebrow, .models-palette .field-help, .models-palette .connection-test > span { color: #6e6e73; }
.models-palette .palette-form label { color: #424245; }
.models-palette .palette-form input:not([type=checkbox]), .models-palette .palette-form select { border-color: #d2d2d7; background: #f5f5f7; color: #1d1d1f; color-scheme: light; }
.models-palette .palette-form input::placeholder { color: #86868b; }
.models-palette .form-section-title, .models-palette .advanced-fields, .models-palette .dialog-footer { border-color: #d2d2d7; color: #424245; }
.models-palette .form-section-title > span:last-child, .models-palette .advanced-fields summary, .models-palette .dialog-footer-note { color: #6e6e73; }
.models-palette .usage-options > label { border-color: #d2d2d7; }
.models-palette .model-choices button { border-color: #d2d2d7; background: #f5f5f7; color: #1d1d1f; }
.models-palette .model-choices button.selected { border-color: #0066cc; background: #e8f0fe; }
.models-palette .model-choices small { color: #6e6e73; }
.models-palette .quiet-button, .models-palette .dialog-cancel { border-color: #b1b1b6; color: #1d1d1f; }
.models-palette .dialog-save { color: #fff; background: #1d1d1f; border-color: #1d1d1f; }
.models-palette .password-field button { color: #424245; }
</style>

<style>
/* Element Plus renders the dialog shell separately from its content; keep the light panel opaque. */
.palette-model-dialog.el-dialog,
.palette-model-dialog.el-dialog .el-dialog__header,
.palette-model-dialog.el-dialog .el-dialog__body,
.palette-model-dialog.el-dialog .el-dialog__footer {
  background-color: #fff !important;
  background-image: none !important;
  opacity: 1 !important;
}
.palette-model-dialog.el-dialog { --el-dialog-bg-color: #fff !important; }
</style>
