import { defineStore } from 'pinia'
import { ref, h } from 'vue'
import { ElNotification, ElMessage } from 'element-plus'
import router from '@/router'
import { sendMessage as restSend, sendMediaMessage } from '@/api/chat'
import { useUserStore } from '@/store/user'

type MsgHandler = (msg: any) => void

/**
 * 聊天实时连接管理（全局单例）：
 * - 登录后建立 WebSocket，断线自动重连
 * - 收到对方消息：若正在与对方聊天界面则实时追加；否则弹窗提醒，点击进入聊天
 * - send: 优先走 WS，失败降级 REST
 */
export const useChatStore = defineStore('chat', () => {
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  let reconnectTimer: any = null
  // 当前正在打开的聊天界面注册的实时回调：otherUserId -> handler
  const chatHandlers = new Map<number, MsgHandler>()

  function buildUrl(token: string) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    return `${proto}://${location.host}/ws/chat?token=${encodeURIComponent(token)}`
  }

  function connect() {
    const userStore = useUserStore()
    if (!userStore.isLoggedIn()) return
    if (ws.value && (ws.value.readyState === WebSocket.OPEN || ws.value.readyState === WebSocket.CONNECTING)) return
    const url = buildUrl(userStore.token)
    const socket = new WebSocket(url)
    ws.value = socket

    socket.onopen = () => { connected.value = true }
    socket.onclose = () => {
      connected.value = false
      scheduleReconnect()
    }
    socket.onerror = () => { connected.value = false }
    socket.onmessage = (ev) => handleIncoming(ev.data)
  }

  function scheduleReconnect() {
    const userStore = useUserStore()
    if (!userStore.isLoggedIn()) return
    clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(() => connect(), 3000)
  }

  function disconnect() {
    clearTimeout(reconnectTimer)
    chatHandlers.clear()
    if (ws.value) {
      ws.value.onclose = null
      ws.value.close()
      ws.value = null
    }
    connected.value = false
  }

  function handleIncoming(raw: string) {
    let data: any
    try { data = JSON.parse(raw) } catch { return }

    if (data.type === 'message') {
      // 对方发来的消息
      const senderId = data.senderId
      const cb = chatHandlers.get(senderId)
      if (cb) {
        cb(data) // 正在聊天界面 → 实时追加
      } else {
        // 不在聊天界面 → 弹窗提醒
        popupNotification(data)
      }
    } else if (data.type === 'ack') {
      // 我发出的消息已被服务端落库 → 在对应聊天界面追加
      const cb = chatHandlers.get(data.receiverId)
      if (cb) cb(data)
    } else if (data.type === 'error') {
      ElMessage.error(data.message || '发送失败')
    }
  }

  function popupNotification(data: any) {
    const nick = data.senderNickname || '新消息'
    const avatar = data.senderAvatar || ''
    const preview = previewText(data)

    // IM 风格弹窗：左侧头像 + 右侧昵称/预览，点击进入聊天
    const card = h('div', { class: 'chat-notify-card' }, [
      h('div', { class: 'cn-avatar-wrap' }, [
        h('div', { class: 'cn-avatar' },
          avatar
            ? h('img', { src: avatar, alt: nick })
            : h('span', null, (nick || '?').charAt(0))
        ),
        h('span', { class: 'cn-dot' }),
      ]),
      h('div', { class: 'cn-body' }, [
        h('div', { class: 'cn-top' }, [
          h('span', { class: 'cn-name' }, nick),
          h('span', { class: 'cn-title' }, '发来一条消息'),
        ]),
        h('div', { class: 'cn-preview' }, preview),
      ]),
    ])

    ElNotification({
      title: '',
      message: card,
      type: 'info',
      duration: 5000,
      position: 'bottom-right',
      customClass: 'chat-notify',
      showClose: true,
      onClick: () => {
        router.push(`/chat/${data.senderId}`)
      },
    })
  }

  /** 根据消息类型生成预览文本 */
  function previewText(data: any): string {
    const t = data.msgType ?? data.type ?? 0
    if (t === 1) return '[表情]'
    if (t === 2) return `[文件] ${data.mediaName || ''}`
    return (data.content || '').slice(0, 60)
  }

  /** 聊天界面打开时注册实时回调，关闭时注销 */
  function registerChat(otherUserId: number, cb: MsgHandler) {
    chatHandlers.set(otherUserId, cb)
  }
  function unregisterChat(otherUserId: number) {
    chatHandlers.delete(otherUserId)
  }

  /** 发送文本消息：优先 WS，失败降级 REST */
  async function send(receiverId: number, content: string) {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify({ receiverId, type: 0, content }))
      return
    }
    await restSend(receiverId, content)
  }

  /** 发送媒体消息（表情图/文件）：优先 WS，失败降级 REST */
  async function sendMedia(payload: {
    receiverId: number
    type: 1 | 2
    mediaUrl: string
    mediaName?: string
    mediaSize?: number
    content?: string
  }) {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify(payload))
      return
    }
    await sendMediaMessage(payload)
  }

  return { connected, connect, disconnect, registerChat, unregisterChat, send, sendMedia }
})
