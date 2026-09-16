import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { streamAiSearch } from '@/api/aiSearch'

export interface ChatMessage {
  id: string
  query: string
  answer: string
  fileName: string
  fileSize: number
  loading: boolean
  error: string
  done: boolean
}

export interface ConversationItem {
  thread_id: string
  title: string
  last_message: string
  last_time: string
}

const AI_BASE = 'http://localhost:8000'

export const useAiChatStore = defineStore('aiChat', () => {
  const messages = ref<ChatMessage[]>([])
  const currentFile = ref<File | null>(null)
  const threadId = ref<string>(localStorage.getItem('ai_thread_id') || 'chat_' + Date.now())
  const lastQuery = ref<string>('')
  const conversations = ref<ConversationItem[]>([])

  function setFile(file: File | null) {
    currentFile.value = file
  }

  function clearFile() {
    currentFile.value = null
  }

  function clearAll() {
    messages.value = []
    lastQuery.value = ''
    threadId.value = 'chat_' + Date.now()
    localStorage.setItem('ai_thread_id', threadId.value)
  }

  function newSession() {
    messages.value = []
    lastQuery.value = ''
    threadId.value = 'chat_' + Date.now()
    localStorage.setItem('ai_thread_id', threadId.value)
  }

  async function ask(query: string) {
    const q = query.trim()
    if (!q) return

    const last = messages.value[messages.value.length - 1]
    if (last && last.query === q && (last.loading || last.done)) return

    lastQuery.value = q
    localStorage.setItem('ai_thread_id', threadId.value)

    // 用 reactive 包装消息对象，确保 onDelta 修改时触发 Vue 响应式更新
    const msg = reactive<ChatMessage>({
      id: 'msg_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8),
      query: q,
      answer: '',
      fileName: currentFile.value?.name || '',
      fileSize: currentFile.value?.size || 0,
      loading: true,
      error: '',
      done: false,
    })
    messages.value.push(msg)

    await streamAiSearch({
      query: q,
      file: currentFile.value,
      threadId: threadId.value,
      onDelta: (d) => { msg.answer += d },
      onDone: () => {
        msg.loading = false
        msg.done = true
        ElMessage.success('AI 回答完成')
        loadConversationList()
      },
      onError: (e) => {
        msg.error = e.message
        msg.loading = false
        ElMessage.error('AI 回答失败：' + e.message)
      },
    })
  }

  async function reanswer(messageId: string) {
    const msg = messages.value.find(m => m.id === messageId)
    if (!msg) return

    msg.answer = ''
    msg.error = ''
    msg.loading = true
    msg.done = false

    const file = currentFile.value && currentFile.value.name === msg.fileName
      ? currentFile.value
      : null

    await streamAiSearch({
      query: msg.query,
      file,
      threadId: threadId.value,
      onDelta: (d) => { msg.answer += d },
      onDone: () => {
        msg.loading = false
        msg.done = true
        ElMessage.success('AI 重新回答完成')
        loadConversationList()
      },
      onError: (e) => {
        msg.error = e.message
        msg.loading = false
        ElMessage.error('AI 重新回答失败：' + e.message)
      },
    })
  }

  async function loadConversationList() {
    try {
      const res = await fetch(`${AI_BASE}/ai/conversations?limit=30`)
      if (res.ok) {
        const data = await res.json()
        conversations.value = data.conversations || []
      }
    } catch (e) {
      console.error('[aiChat] loadConversationList error:', e)
    }
  }

  async function loadHistory(tid: string) {
    try {
      const res = await fetch(`${AI_BASE}/ai/history/${tid}`)
      if (!res.ok) {
        console.error('[aiChat] loadHistory API error:', res.status)
        return
      }
      const data = await res.json()
      console.log('[aiChat] loadHistory received:', data)
      if (!data.messages || data.messages.length === 0) {
        console.log('[aiChat] no messages for thread:', tid)
        return
      }

      threadId.value = tid
      localStorage.setItem('ai_thread_id', tid)
      lastQuery.value = ''
      messages.value = []

      for (let i = 0; i < data.messages.length; i += 2) {
        const userMsg = data.messages[i]
        const aiMsg = data.messages[i + 1]
        if (userMsg && userMsg.role === 'user') {
          messages.value.push({
            id: 'loaded_' + i,
            query: userMsg.content,
            answer: aiMsg?.content || '',
            fileName: '',
            fileSize: 0,
            loading: false,
            error: '',
            done: true,
          })
          lastQuery.value = userMsg.content
        }
      }
    } catch (e) {
      console.error('[aiChat] loadHistory error:', e)
    }
  }

  return {
    messages,
    currentFile,
    threadId,
    lastQuery,
    conversations,
    setFile,
    clearFile,
    clearAll,
    newSession,
    ask,
    reanswer,
    loadConversationList,
    loadHistory,
  }
})
