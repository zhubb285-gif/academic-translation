<script setup lang="ts">
import { ref, watch } from 'vue'
const props = defineProps<{ term: any; loading?: boolean }>()
defineEmits<{ select: [translation: string]; research: [] }>()
const shown = ref<Record<string, number>>({ journal_cards: 2, authority_cards: 2 })
watch(() => props.term.id, () => { shown.value = { journal_cards: 2, authority_cards: 2 } })
const columns = [{ key: 'journal_cards', label: '01 · 期刊文章', empty: '当前语料未找到对应英文用法；这不代表该期刊从未使用此词。' }, { key: 'authority_cards', label: '02 · 分级信源', empty: '尚未取得可核对的信源原文，请查看检索记录并继续人工查证。' }]
const statusNames: Record<string, string> = { agreement: '两侧存在相同候选 · 请人工核定含义', different_candidates: '两侧候选不同 · 请人工裁决', usage_both: '两侧均有用法证据 · 中英对应待核定', journal_only: '仅期刊侧取得用法', authority_only: '仅信源侧取得原文', no_evidence: '尚未取得可采信原文' }
const traceNames: Record<string, string> = { found: '已取得完整词条', found_other_domain: '词形命中但领域不符，继续查证', found_usage: '已取得英文用法', no_usage_match: '当前语料未命中', no_exact_match: '未取得完整匹配', no_verified_detail_match: '未取得匹配详情页，需人工核查', unavailable: '无法自动读取，需人工核查', manual_required: '需打开信源人工检索', skipped_tier1_found: '一级已命中，停止向下查找', excluded: '三级信源，不参与采信', not_applicable: '领域不适用' }
</script>

<template>
  <section class="comparison" aria-label="期刊与信源证据对比">
    <div class="comparison-head"><div><span class="eyebrow">EVIDENCE COMPARISON</span><h3>同一个词，两侧依据。</h3></div><div class="decision-controls"><span class="decision-state">{{ term.confirmed_translation ? '已有人工裁决' : '等待人工裁决' }}</span><el-button size="small" :loading="loading" @click="$emit('research')">重新查证</el-button></div></div>
    <p class="comparison-policy">先检索期刊文章，再从一级信源起查；一级完整命中后停止向二级查找。即使期刊已命中，也查信源供对照。三级不采用。</p>
    <p class="comparison-result" role="status">{{ statusNames[term.research_summary?.comparison_status] || '查证完成后在这里对照原文' }}</p>
    <div class="comparison-grid"><section v-for="column in columns" :key="column.key"><h4>{{ column.label }} <span>{{ (term[column.key] || []).length }} 条</span></h4>
      <article v-for="(card, index) in (term[column.key] || []).slice(0, shown[column.key])" :key="`${card.source_url}-${index}`" class="comparison-evidence" :class="{ rejected: card.source_blocked }">
        <div class="evidence-label"><span>{{ column.key === 'journal_cards' ? (card.text_kind === 'full_text' ? '全文用法' : '摘要用法') : `${card.source_level}级信源` }}</span><span>{{ card.status_tag }}</span></div>
        <strong class="candidate">{{ card.recommended_translation }}</strong>
        <p class="article-title">{{ card.title || card.source_name }}</p>
        <blockquote v-if="card.source_checked && card.evidence_text">{{ card.evidence_text }}</blockquote><p v-else class="empty-evidence">原文已失效或尚未核对。</p>
        <p class="evidence-reason">{{ card.recommendation_reason }}</p>
        <p class="evidence-origin">{{ card.journal || card.source_name }}<span v-if="card.published_date"> · {{ String(card.published_date).slice(0, 10) }}</span><br v-if="card.doi" />{{ card.doi }}</p>
        <div class="evidence-links"><a v-if="card.source_url && card.source_checked" :href="card.source_url" target="_blank" rel="noopener noreferrer">原文出处 ↗</a><a v-if="card.search_url" :href="card.search_url" target="_blank" rel="noopener noreferrer">带词站内检索 ↗</a><a v-if="card.text_source_url && card.text_source_url !== card.source_url" :href="card.text_source_url" target="_blank" rel="noopener noreferrer">文本获取出处 ↗</a></div>
        <button type="button" class="select-candidate" :disabled="!card.recommended_translation || !card.source_checked || card.source_blocked || ['core_only', 'domain_mismatch'].includes(card.match_type)" @click="$emit('select', card.recommended_translation)">填入人工裁决栏 ↓</button>
      </article>
      <button v-if="term[column.key]?.length > (shown[column.key] || 2)" type="button" class="select-candidate" @click="shown[column.key] = (shown[column.key] || 2) + 3">再看 3 条（已显示 {{ Math.min(shown[column.key] || 2, term[column.key].length) }} / {{ term[column.key].length }}）</button>
      <p v-if="!term[column.key]?.length" class="comparison-empty">{{ column.empty }}</p>
    </section></div>
    <details class="lookup-trace"><summary>查看逐级检索记录（含未接通、未命中与禁用来源）</summary><ul><li v-for="(entry, index) in term.research_summary?.lookup_trace || []" :key="index"><strong>{{ entry.source }}</strong><span>{{ traceNames[entry.status] || entry.status }}<template v-if="entry.count != null"> · {{ entry.count }} 条</template></span></li></ul></details>
    <p class="comparison-footnote">英文出现在论文或网页中，只能证明该表达被使用；它与中文术语是否准确对应，需要核对定义、学科和上下文。</p>
  </section>
</template>

<style scoped>
.comparison { padding:22px; border:1px solid #e5e5e7; border-radius:18px; background:#fafafa; margin-bottom:20px; color:#1d1d1f; }
.comparison-head { display:flex; align-items:center; justify-content:space-between; gap:14px; }
.decision-controls { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.eyebrow { font-size:10px; letter-spacing:1.7px; color:#626269; }.comparison h3 { font-size:23px; margin:8px 0; letter-spacing:-.7px; }
.decision-state { background:#edf3ff; color:#275a9d; padding:8px 11px; border-radius:999px; font-size:11px; white-space:nowrap; }
.comparison-policy,.comparison-footnote { color:#626269; font-size:12px; line-height:1.8; }
.comparison-result { background:#edf3ff; color:#275a9d; padding:12px; border-radius:10px; font-size:12px; }
.comparison-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }.comparison-grid section { min-width:0; }
.comparison h4 { font-size:14px; margin:16px 0; }.comparison h4 span { font-size:11px; color:#626269; margin-left:7px; font-weight:400; }
.comparison-evidence { border:1px solid #e5e5e7; border-radius:14px; background:#fff; padding:16px; margin-bottom:12px; overflow-wrap:anywhere; }
.evidence-label { display:flex; justify-content:space-between; gap:10px; color:#626269; font-size:10px; line-height:1.6; }.candidate { display:block; font-size:17px; margin:12px 0; color:#1d1d1f; }
.article-title { font-size:12px; line-height:1.7; font-weight:550; }.comparison blockquote { font-size:12px; line-height:1.8; margin:12px 0; padding:10px 12px; background:#f4f6f8; border-left:2px solid #a6b7cb; }
.evidence-reason,.evidence-origin,.empty-evidence { font-size:11px; line-height:1.8; color:#626269; }
.evidence-links { display:flex; gap:10px; flex-wrap:wrap; margin:12px 0; }.evidence-links a { color:#0066cc; font-size:11px; text-decoration:none; }
.select-candidate { border:1px solid #d2d2d7; background:#fff; color:#0066cc; padding:9px 12px; font:inherit; font-size:12px; border-radius:999px; cursor:pointer; }
.select-candidate:disabled { opacity:.5; cursor:default; }.select-candidate:focus-visible,.lookup-trace summary:focus-visible { outline:2px solid #0066cc; outline-offset:3px; }
.comparison-empty { padding:22px 16px; border:1px dashed #d2d2d7; border-radius:12px; font-size:12px; line-height:1.8; color:#626269; }
.lookup-trace { font-size:12px; margin-top:18px; }.lookup-trace summary { cursor:pointer; padding:9px 0; }.lookup-trace ul { padding:0; list-style:none; max-height:280px; overflow:auto; }.lookup-trace li { display:flex; justify-content:space-between; gap:20px; padding:10px 0; border-top:1px solid #e5e5e7; }.lookup-trace li strong { font-weight:500; }.lookup-trace li span { color:#626269; text-align:right; }
.rejected { opacity:.6; }
@media(max-width:650px) { .comparison { padding:16px; }.comparison-grid { grid-template-columns:1fr; }.comparison-head { align-items:flex-start; flex-direction:column; } }
</style>
