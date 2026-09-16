import http from './http'

export interface ChatFriend {
  userId: number
  nickname: string
  avatarUrl: string
  lastContent: string | null
  lastSenderId: number | null
  lastTime: string | null
  unread: boolean
}

export interface ChatMessage {
  id: number
  senderId: number
  receiverId: number
  content: string
  isRead: number
  createdTime: string
  /** 0=文本 1=表情图 2=文件 */
  type?: number
  mediaUrl?: string | null
  mediaName?: string | null
  mediaSize?: number | null
  /** 仅实时推送 payload 携带 */
  senderNickname?: string | null
  senderAvatar?: string | null
}

export interface ChatSticker {
  id: number
  userId: number
  url: string
  createdTime: string
}

export const getFriends = () => http.get('/chat/friends')
export const getHistory = (otherUserId: number, pageNum = 1, pageSize = 50) =>
  http.get(`/chat/messages/${otherUserId}`, { params: { pageNum, pageSize } })
export const sendMessage = (receiverId: number, content: string) =>
  http.post('/chat/send', { receiverId, type: 0, content })

/** 发送媒体消息（表情图/文件）：文件先上传拿到 url 再调用 */
export const sendMediaMessage = (payload: {
  receiverId: number
  type: 1 | 2
  mediaUrl: string
  mediaName?: string
  mediaSize?: number
  content?: string
}) => http.post('/chat/send', { ...payload })

export const markRead = (otherUserId: number) =>
  http.post(`/chat/read/${otherUserId}`)
export const getUnreadCount = (otherUserId: number) =>
  http.get(`/chat/unread/${otherUserId}`)

// ===== 自定义表情包 =====
export const getMyStickers = () => http.get('/chat/stickers')
export const addSticker = (url: string) => http.post('/chat/stickers', { url })
export const deleteSticker = (id: number) => http.delete(`/chat/stickers/${id}`)
