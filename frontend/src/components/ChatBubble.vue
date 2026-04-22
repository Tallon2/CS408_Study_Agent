<template>
  <div class="bubble-wrap" :class="isUser ? 'bubble-wrap--user' : 'bubble-wrap--ai'">
    <div class="bubble-avatar">{{ isUser ? '👤' : '🤖' }}</div>
    <div class="bubble" :class="isUser ? 'bubble--user' : 'bubble--ai'">
      <!-- AI 消息：渲染 Markdown -->
      <div v-if="!isUser" class="bubble__content" v-html="renderedContent" />
      <!-- 用户消息：纯文本 -->
      <div v-else class="bubble__content">{{ message.content }}</div>
      <!-- 流式光标 -->
      <span v-if="isStreaming && !isUser" class="cursor">▋</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
// @ts-ignore
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import type { ChatMessage } from '@/types'

const props = defineProps<{
  message: ChatMessage
  isStreaming?: boolean
}>()

const isUser = computed(() => props.message.role === 'user')

const md: MarkdownIt = new MarkdownIt({
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(str, { language: lang }).value}</code></pre>`
      } catch {}
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`
  },
  linkify: true,
  typographer: true,
})

const renderedContent = computed(() =>
  props.message.content ? md.render(props.message.content) : '<span style="color:#999">思考中...</span>'
)
</script>

<style scoped>
.bubble-wrap { display: flex; gap: 10px; margin-bottom: 16px; align-items: flex-start; }
.bubble-wrap--user { flex-direction: row-reverse; }
.bubble-avatar { font-size: 28px; flex-shrink: 0; line-height: 1; margin-top: 4px; }
.bubble { max-width: 75%; padding: 12px 16px; border-radius: 12px; position: relative; word-break: break-word; }
.bubble--ai { background: white; border: 1px solid #e8e8e8; border-radius: 2px 12px 12px 12px; }
.bubble--user { background: #1890ff; color: white; border-radius: 12px 2px 12px 12px; }
.bubble__content { font-size: 15px; line-height: 1.7; }
.bubble--ai .bubble__content :deep(pre) { background: #f6f8fa; border-radius: 6px; padding: 12px; overflow-x: auto; }
.bubble--ai .bubble__content :deep(code) { font-family: 'Fira Code', monospace; font-size: 13px; }
.bubble--ai .bubble__content :deep(p) { margin-bottom: 8px; }
.bubble--ai .bubble__content :deep(ul), .bubble--ai .bubble__content :deep(ol) { padding-left: 20px; margin-bottom: 8px; }
.cursor { display: inline-block; animation: blink 1s step-end infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
</style>
