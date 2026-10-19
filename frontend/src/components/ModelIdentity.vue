<script setup lang="ts">
import deepseek from '../assets/model-logos/deepseek.svg?raw'
import openai from '../assets/model-logos/openai.svg?raw'
import claude from '../assets/model-logos/claude.svg?raw'
import qwen from '../assets/model-logos/qwen.svg?raw'
import mimo from '../assets/model-logos/xiaomimimo.svg?raw'
import kimi from '../assets/model-logos/kimi.svg?raw'
import zhipu from '../assets/model-logos/zhipu.svg?raw'
import doubao from '../assets/model-logos/doubao.svg?raw'
import minimax from '../assets/model-logos/minimax.svg?raw'
import gemini from '../assets/model-logos/gemini.svg?raw'
defineProps<{ provider: string }>()
const logos: Record<string, string> = { deepseek, openai, anthropic: claude, qwen, mimo, moonshot: kimi, zhipu, doubao, minimax, google: gemini }
</script>
<template>
  <span v-if="logos[provider]" class="brand-mark" v-html="logos[provider]" aria-hidden="true" />
  <svg v-else viewBox="0 0 64 64" fill="none" aria-hidden="true"><rect x="7" y="7" width="20" height="20" rx="4" fill="currentColor"/><rect x="37" y="7" width="20" height="20" rx="4" stroke="currentColor" stroke-width="3"/><rect x="7" y="37" width="20" height="20" rx="4" stroke="currentColor" stroke-width="3"/><rect x="37" y="37" width="20" height="20" rx="4" fill="currentColor"/></svg>
</template>
<style scoped>
.brand-mark,svg { width: 100%; height: 100%; display: block; }
.brand-mark :deep(svg) { width: 100%; height: 100%; display: block; }
</style>
