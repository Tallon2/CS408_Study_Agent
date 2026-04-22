/**
 * sse.ts — SSE 流式对话工具
 * 
 * 封装 fetch + ReadableStream 实现真正的 SSE 客户端，
 * 支持回调方式处理各类事件。
 * 支持 AbortController 中断流式请求。
 */

export interface SSECallbacks {
  onStart?: (data: { message: string }) => void
  onToken?: (data: { content: string; accumulated?: string }) => void
  onPipeline?: (data: { stage: string; [key: string]: unknown }) => void
  onDone?: (data: { content: string }) => void
  onError?: (data: { error: string }) => void
  onClose?: () => void
}

/**
 * 发起 SSE 流式对话请求
 * @param message 用户消息
 * @param callbacks 各类事件回调
 * @param signal 可选的 AbortSignal，用于中断请求
 */
export async function streamChat(
  message: string,
  callbacks: SSECallbacks,
  signal?: AbortSignal
): Promise<void> {
  const token = localStorage.getItem('access_token')
  
  try {
    const response = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ message }),
      signal,
    })

    if (!response.ok) {
      const err = await response.json().catch(() => ({ error: '请求失败' }))
      callbacks.onError?.({ error: err.detail || '请求失败' })
      return
    }

    const reader = response.body?.getReader()
    if (!reader) return

    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) { callbacks.onClose?.(); break }

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''  // 保留未完成的行

      let currentEvent = ''
      for (const line of lines) {
        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          const rawData = line.slice(5).trim()
          if (!rawData || rawData === '[DONE]') continue

          try {
            const data = JSON.parse(rawData)
            switch (currentEvent) {
              case 'start':    callbacks.onStart?.(data);    break
              case 'token':    callbacks.onToken?.(data);    break
              case 'pipeline': callbacks.onPipeline?.(data); break
              case 'done':     callbacks.onDone?.(data);     break
              case 'error':    callbacks.onError?.(data);    break
            }
          } catch { /* 忽略解析错误 */ }
          currentEvent = ''
        }
      }
    }
  } catch (err) {
    // AbortError 是正常中断，不触发 onError
    if (err instanceof DOMException && err.name === 'AbortError') {
      callbacks.onClose?.()
      return
    }
    callbacks.onError?.({ error: String(err) })
  }
}