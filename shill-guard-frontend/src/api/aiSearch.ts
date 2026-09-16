/**
 * aiSearch.ts
 * 功能：前端调用 AI 对话 Agent，以 SSE 流式接收回答
 * 接口：POST http://localhost:8000/ai/chat  （后端由用户自行实现）
 * 输入：keyword（用户搜索词）+ 可选附件文件
 * 输出：流式 delta token，通过回调函数传递给调用方
 * 日期：2026-06
 */

const AI_BASE = 'http://localhost:8000'

export interface AiSearchOptions {
  query: string
  file?: File | null
  threadId?: string
  onDelta: (delta: string) => void
  onDone: () => void
  onError?: (err: Error) => void
}

export async function streamAiSearch(options: AiSearchOptions): Promise<void> {
  const { query, file, threadId, onDelta, onDone, onError } = options

  // 始终用 multipart/form-data，因为 Python 端用 Form(...) 接收
  const form = new FormData()
  form.append('message', query)
  form.append('thread_id', threadId || 'search_' + Date.now())
  if (file) {
    form.append('files', file, file.name)
  }

  let res: Response
  try {
    res = await fetch(`${AI_BASE}/ai/chat`, {
      method: 'POST',
      body: form,
    })
  } catch (e: any) {
    onError?.(new Error('无法连接 AI 服务：' + e.message))
    return
  }

  if (!res.ok) {
    onError?.(new Error(`AI 服务响应异常：${res.status}`))
    return
  }

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data:')) continue
      const data = trimmed.slice(5).trim()
      if (data === '[DONE]') { onDone(); return }
      try {
        const json = JSON.parse(data)
        if (json.delta) onDelta(json.delta)
      } catch {}
    }
  }
  onDone()
}
