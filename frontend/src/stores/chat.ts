/**
 * chat.ts — 对话 Pinia Store
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { http } from '@/utils/http'
import { streamChat } from '@/utils/sse'
import type { ChatMessage, PipelineEvent } from '@/types'

export const useChatStore = defineStore('chat', () => {
  const messages  = ref<ChatMessage[]>([])
  const loading   = ref(false)
  const streaming = ref(false)

  // RAG 管线追踪事件（用于可视化面板）
  const pipelineEvents = ref<PipelineEvent[]>([])
  const currentStreamContent = ref('')

  // 中断控制器（支持用户手动停止流式输出）
  let abortController: AbortController | null = null

  async function loadHistory() {
    try {
      const { data } = await http.get<{ messages: ChatMessage[]; count: number }>('/api/v1/chat/history')
      messages.value = data.messages ?? []
    } catch {
      // 未登录或网络错误时静默忽略，路由守卫会处理跳转
      messages.value = []
    }
  }

  async function sendMessage(content: string) {
    if (!content.trim() || loading.value) return

    // 添加用户消息
    messages.value.push({ role: 'user', content, timestamp: new Date().toISOString() })

    // 添加 AI 占位消息
    const aiMsg: ChatMessage = { role: 'assistant', content: '', timestamp: new Date().toISOString() }
    messages.value.push(aiMsg)
    const aiIndex = messages.value.length - 1

    loading.value = true
    streaming.value = true
    pipelineEvents.value = []
    currentStreamContent.value = ''

    // 创建 AbortController
    abortController = new AbortController()

    await streamChat(content, {
      onStart: () => {
        currentStreamContent.value = ''
      },

      onPipeline: (data) => {
        // 记录管线事件，供 RAGProcessPanel 实时展示
        pipelineEvents.value.push(data as PipelineEvent)
      },

      onToken: (data) => {
        // 支持两种模式：
        // 1. 新版增量模式：content 是增量 token，accumulated 是全量文本
        // 2. 旧版全量模式：content 就是全量文本（兼容 LearningAgent）
        if (data.accumulated !== undefined) {
          // 新版：使用 accumulated 全量文本（由后端累加，保证一致性）
          currentStreamContent.value = data.accumulated
          messages.value[aiIndex].content = data.accumulated
        } else {
          // 旧版兼容
          currentStreamContent.value = data.content
          messages.value[aiIndex].content = data.content
        }
      },

      onDone: (data) => {
        messages.value[aiIndex].content = data.content
        currentStreamContent.value = data.content
        loading.value  = false
        streaming.value = false
      },

      onError: (data) => {
        messages.value[aiIndex].content = `[错误] ${data.error}`
        loading.value  = false
        streaming.value = false
      },

      onClose: () => {
        loading.value  = false
        streaming.value = false
      },
    }, abortController.signal)

    // 清理
    abortController = null
  }

  /** 中断当前流式输出 */
  function stopStreaming() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    loading.value = false
    streaming.value = false
  }

  async function resetSession() {
    stopStreaming()
    await http.delete('/api/v1/chat/session')
    messages.value = []
    pipelineEvents.value = []
    currentStreamContent.value = ''
  }

  return {
    messages, loading, streaming,
    pipelineEvents, currentStreamContent,
    loadHistory, sendMessage, resetSession, stopStreaming,
  }
})