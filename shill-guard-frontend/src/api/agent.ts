import http from './http'

/**
 * 立即触发"识别恶意行为用户"检测。
 * 后端会收集今日所有帖子+评论、调用 Python 检测算法打分并分级处置，
 * 返回检测结果汇总（每用户分数与明细），用于前端弹窗展示。
 * 该调用会跑完所有用户的审核 graph，耗时较长，单独放宽超时到 5 分钟。
 */
export const triggerDetect = () =>
  http.post('/agent/detect-users', null, { timeout: 300000 })

export const getStats = () =>
  http.get('/agent/stats')

export const getMuteList = (pageNum = 1, pageSize = 20, status?: number) =>
  http.get('/agent/mute/records', { params: { pageNum, pageSize, status } })

export const manualMute = (data: { userId: number; reason: string; duration?: number }) =>
  http.post('/agent/mute', data)

export const cancelMute = (muteId: number) =>
  http.put(`/agent/mute/${muteId}/cancel`)

/**
 * 立即触发"识别恶意行为用户"检测（SSE 流式版本）。
 * 用 fetch + ReadableStream 消费 text/event-stream，逐事件回调 onEvent。
 * 后端会实时推送：log（RAG-DEBUG/打分日志）、score（单用户分数）、
 * stage（阶段进度）、action（预警/禁言处置）、done（汇总+明细）、error。
 *
 * @param onEvent 收到一条 SSE 事件时的回调 (eventName, data)
 * @param signal  可选 AbortSignal，用于取消
 */
export async function triggerDetectStream(
  onEvent: (event: string, data: any) => void,
  signal?: AbortSignal
): Promise<void> {
  const token = localStorage.getItem('token')
  const resp = await fetch('/api/agent/detect-users/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: null,
    signal,
  })
  if (!resp.ok || !resp.body) {
    throw new Error('流式连接失败: HTTP ' + resp.status)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent = 'message'
  let dataLines: string[] = []

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // 按行切分，保留最后一段不完整内容在 buffer
    let nl: number
    while ((nl = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, nl)
      buffer = buffer.slice(nl + 1)

      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        let d = line.slice(5)
        if (d.startsWith(' ')) d = d.slice(1)
        dataLines.push(d)
      } else if (line === '') {
        // 空行 = 一条 SSE 事件帧结束
        if (dataLines.length > 0) {
          const dataStr = dataLines.join('')
          dataLines = []
          let parsed: any = dataStr
          try {
            parsed = JSON.parse(dataStr)
          } catch {
            // 非 JSON，原样字符串
          }
          onEvent(currentEvent, parsed)
        }
        currentEvent = 'message'
      }
    }
  }
  // flush 残留
  if (dataLines.length > 0) {
    const dataStr = dataLines.join('')
    try {
      onEvent(currentEvent, JSON.parse(dataStr))
    } catch {
      onEvent(currentEvent, dataStr)
    }
  }
}
