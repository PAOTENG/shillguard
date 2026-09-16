/**
 * RAG 知识库 & 测试用例生成 API
 * 调用 Python 后端（/ai/*），通过 vite proxy 转发到 localhost:8000
 */

export interface KbDocument {
  file: string
  chunks: number
}

export interface KbDocListResponse {
  documents: KbDocument[]
  total_chunks: number
}

export interface KbUploadResponse {
  status: 'ok' | 'error'
  file?: string
  chunks?: number
  total_chars?: number
  reason?: string
}

/** 获取已索引文档列表 */
export async function getDocList(): Promise<KbDocListResponse> {
  const resp = await fetch('/ai/rag/documents')
  if (!resp.ok) throw new Error('HTTP ' + resp.status)
  return resp.json()
}

/** 上传文件到知识库 */
export async function uploadToKb(file: File): Promise<KbUploadResponse> {
  const fd = new FormData()
  fd.append('file', file, file.name)
  const resp = await fetch('/ai/rag/upload', { method: 'POST', body: fd })
  if (!resp.ok) throw new Error('HTTP ' + resp.status)
  return resp.json()
}

/** 删除知识库文档 */
export async function deleteDoc(filename: string): Promise<void> {
  const resp = await fetch('/ai/rag/documents/' + encodeURIComponent(filename), { method: 'DELETE' })
  if (!resp.ok) throw new Error('HTTP ' + resp.status)
}

/**
 * 发送对话消息（SSE 流式），返回 Response 供调用方消费 body stream
 * @param message  消息内容
 * @param threadId 会话 ID
 * @param files    可选附件
 */
export async function sendChatMessage(
  message: string,
  threadId: string,
  files?: File[]
): Promise<Response> {
  const fd = new FormData()
  fd.append('message', message)
  fd.append('thread_id', threadId)
  if (files) {
    for (const f of files) fd.append('files', f, f.name)
  }
  const resp = await fetch('/ai/chat', { method: 'POST', body: fd })
  if (!resp.ok) throw new Error('HTTP ' + resp.status)
  return resp
}

/**
 * 上传文件生成测试用例（SSE 流式），返回 Response
 */
export async function generateTests(file: File): Promise<Response> {
  const fd = new FormData()
  fd.append('file', file, file.name)
  const resp = await fetch('/ai/rag/generate-tests', { method: 'POST', body: fd })
  if (!resp.ok) throw new Error('HTTP ' + resp.status)
  return resp
}
