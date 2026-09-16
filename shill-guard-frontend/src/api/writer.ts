const AI_BASE = 'http://localhost:8000'

/**
 * 调用续写 Agent，流式返回续写内容。
 * @param content     用户已有的原文
 * @param requirement 续写要求（可为空，留空则自由续写）
 * @param onDelta     每收到一个 token 时的回调
 * @param onDone      全部完成时的回调
 */
export async function streamWrite(
  content: string,
  requirement: string,
  onDelta: (delta: string) => void,
  onDone: () => void
) {
  const res = await fetch(`${AI_BASE}/ai/write`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, requirement }),
  })

  if (!res.ok || !res.body) {
    throw new Error(`续写请求失败：${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const text = decoder.decode(value, { stream: true })
    // SSE 格式：每行 "data: {...}\n\n" 或 "data: [DONE]\n\n"
    const lines = text.split('\n')
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6).trim()
      if (payload === '[DONE]') { onDone(); return }
      try {
        const obj = JSON.parse(payload)
        if (obj.delta) onDelta(obj.delta)
      } catch { /* 忽略解析失败的行 */ }
    }
  }
  onDone()
}
