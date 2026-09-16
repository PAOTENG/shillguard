/**
 * useSSE - 通用 SSE 流式读取 composable
 *
 * 使用方式：
 *   const { readSSE } = useSSE()
 *   await readSSE(response, {
 *     onDelta: (text) => { ... },   // 每收到一个 delta token 回调
 *     onDone: () => { ... },        // 收到 [DONE] 时回调
 *     onError: (msg) => { ... },    // 收到 error 字段时回调
 *   })
 *
 * 后端 SSE 格式：
 *   data: {"delta": "..."}\n\n
 *   data: [DONE]\n\n
 *   data: {"error": "..."}\n\n
 */
export function useSSE() {
  async function readSSE(
    resp: Response,
    handlers: {
      onDelta: (text: string) => void
      onDone?: () => void
      onError?: (msg: string) => void
    }
  ) {
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let done = false

    while (!done) {
      const { value, done: streamDone } = await reader.read()
      done = streamDone
      if (value) {
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6).trim()
          if (payload === '[DONE]') {
            handlers.onDone?.()
            continue
          }
          try {
            const obj = JSON.parse(payload)
            if (obj.delta) handlers.onDelta(obj.delta)
            if (obj.error) handlers.onError?.(obj.error)
          } catch {
            // 忽略无法解析的行
          }
        }
      }
    }
  }

  return { readSSE }
}
