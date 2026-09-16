<template>
  <div class="chat-page">
    <div class="chat-wrap">
      <!-- 顶部对方信息 -->
      <div class="chat-header">
        <el-icon class="back" @click="router.back()"><ArrowLeft /></el-icon>
        <el-avatar :size="40" :src="other?.avatarUrl">{{ other?.nickname?.charAt(0) }}</el-avatar>
        <div class="header-name">{{ other?.nickname || '加载中…' }}</div>
        <div class="header-actions">
          <el-button
            v-if="isFollowing"
            size="small"
            round
            @click="onUnfollow"
            :loading="followLoading"
          >已关注</el-button>
          <el-button
            v-else
            size="small"
            type="primary"
            round
            @click="onFollow"
            :loading="followLoading"
          >+ 关注</el-button>
        </div>
      </div>

      <!-- 消息区 -->
      <div class="msg-area" ref="msgArea" v-loading="loading">
        <div
          v-for="m in messages"
          :key="m.id"
          class="msg-row"
          :class="{ mine: m.senderId === meId }"
        >
          <el-avatar :size="36" :src="m.senderId === meId ? meAvatar : other?.avatarUrl" class="msg-avatar">
            {{ (m.senderId === meId ? meNick : other?.nickname)?.charAt(0) }}
          </el-avatar>

          <!-- 文本 -->
          <div v-if="msgType(m) === 0" class="bubble">{{ m.content }}</div>

          <!-- 表情图 -->
          <div v-else-if="msgType(m) === 1" class="bubble sticker-bubble">
            <img :src="m.mediaUrl" class="sticker-img" alt="表情" @click="previewSticker(m.mediaUrl!)" />
          </div>

          <!-- 文件 -->
          <div v-else-if="msgType(m) === 2" class="bubble file-bubble">
            <div class="file-card" @click="downloadFile(m.mediaUrl!, m.mediaName || '文件')">
              <div class="file-icon"><el-icon><Document /></el-icon></div>
              <div class="file-meta">
                <div class="file-name">{{ m.mediaName || '未命名文件' }}</div>
                <div class="file-size">{{ formatSize(m.mediaSize) }}</div>
              </div>
              <el-icon class="file-dl"><Download /></el-icon>
            </div>
          </div>
        </div>
        <div class="empty" v-if="!loading && !messages.length">还没有消息，发条招呼吧～</div>
      </div>

      <!-- 取关限制提示 -->
      <div v-if="!isFollowing && !loading" class="follow-banner">
        <el-icon><WarningFilled /></el-icon>
        <span>你已取消关注对方，无法发送消息。重新关注后即可继续聊天。</span>
      </div>

      <!-- 输入区 -->
      <div class="input-area" :class="{ 'input-disabled': !isFollowing }">
        <!-- 表情按钮 -->
        <el-popover :visible="emojiVisible" placement="top-start" :width="340" trigger="manual">
          <template #reference>
            <el-button class="tool-btn" @click="emojiVisible = !emojiVisible" title="表情">
              <el-icon><ChatLineRound /></el-icon>
            </el-button>
          </template>
          <div class="emoji-panel">
            <div class="emoji-tabs">
              <button :class="{ active: emojiTab === 'emoji' }" @click="emojiTab = 'emoji'">Emoji</button>
              <button :class="{ active: emojiTab === 'sticker' }" @click="emojiTab = 'sticker'">我的表情</button>
            </div>
            <!-- Emoji 网格 -->
            <div v-if="emojiTab === 'emoji'" class="emoji-grid">
              <button
                v-for="e in emojiList"
                :key="e"
                class="emoji-cell"
                @click="insertEmoji(e)"
              >{{ e }}</button>
            </div>
            <!-- 自定义表情 -->
            <div v-else class="sticker-grid">
              <div class="sticker-cell add" @click="stickerFileInput?.click()">
                <el-icon><Plus /></el-icon>
                <span>上传</span>
              </div>
              <div
                v-for="s in stickers"
                :key="s.id"
                class="sticker-cell"
                @click="sendSticker(s.url)"
                @contextmenu.prevent="removeSticker(s.id)"
                :title="`点击发送 / 右键删除`"
              >
                <img :src="s.url" alt="表情" />
              </div>
              <div v-if="!stickers.length" class="sticker-empty">点击 + 上传图片作为表情包</div>
            </div>
            <input
              ref="stickerFileInput"
              type="file"
              accept="image/*"
              style="display:none"
              @change="onUploadSticker"
            />
          </div>
        </el-popover>

        <!-- 文件按钮 -->
        <el-button class="tool-btn" @click="fileInput?.click()" :loading="fileUploading" title="发送文件（不支持文件夹，≤50MB）">
          <el-icon><Paperclip /></el-icon>
        </el-button>
        <input
          ref="fileInput"
          type="file"
          style="display:none"
          @change="onUploadFile"
        />

        <el-input
          v-model="text"
          :placeholder="isFollowing ? '输入消息，回车发送…' : '请先关注对方后才能发消息'"
          @keyup.enter="onSend"
          :disabled="sending || !isFollowing"
        />
        <el-button type="primary" :loading="sending" :disabled="!isFollowing" @click="onSend">发送</el-button>
      </div>
    </div>

    <!-- 表情大图预览 -->
    <el-image-viewer v-if="previewUrl" :url-list="[previewUrl]" @close="previewUrl = ''" teleported />
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Document, Download, ChatLineRound, Paperclip, Plus, WarningFilled } from '@element-plus/icons-vue'
import {
  getHistory, markRead, sendMessage as restSend, sendMediaMessage,
  getMyStickers, addSticker, deleteSticker, type ChatMessage, type ChatSticker,
} from '@/api/chat'
import { uploadImage, uploadChatFile } from '@/api/file'
import { getUserProfile, getUserStats, followUser, unfollowUser } from '@/api/user'
import { useUserStore } from '@/store/user'
import { useChatStore } from '@/store/chat'
import { useDownloadDir } from '@/composables/useDownloadDir'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const chatStore = useChatStore()
const { downloadFile: dlFile } = useDownloadDir()

const otherId = Number(route.params.id)
const meId = userStore.userInfo?.userId as number
const meAvatar = userStore.userInfo?.avatarUrl
const meNick = userStore.userInfo?.nickname

const other = ref<any>(null)
const messages = ref<ChatMessage[]>([])
const text = ref('')
const sending = ref(false)
const loading = ref(false)
const msgArea = ref<HTMLElement | null>(null)

// 关注状态
const isFollowing = ref(false)
const followLoading = ref(false)

// 表情面板
const emojiVisible = ref(false)
const emojiTab = ref<'emoji' | 'sticker'>('emoji')
const stickers = ref<ChatSticker[]>([])
const stickerFileInput = ref<HTMLInputElement | null>(null)
const previewUrl = ref('')

// 文件上传
const fileInput = ref<HTMLInputElement | null>(null)
const fileUploading = ref(false)

// 常用 Emoji（所有用户默认都有）
const emojiList = [
  '😀','😁','😂','🤣','😃','😄','😅','😆','😉','😊','😋','😎','😍','😘','🥰','😗',
  '🙂','🤗','🤔','😐','😑','😶','🙄','😏','😣','😥','😮','🤐','😯','😪','😫','😴',
  '😌','😛','😜','😝','🤤','😒','😓','😔','🙃','🤑','😲','😖','😞','😟','😤','😢',
  '😭','😦','😧','😨','😩','🤯','😬','😰','😱','😳','🤪','😵','😡','😠','🤬','😷',
  '🤒','🤕','🤢','🤮','🥳','🥺','😎','🤩','🤫','🤥','🤧','👍','👎','👏','🙌','🙏',
  '💪','✌️','🤘','🤞','👌','✋','❤️','🧡','💛','💚','💙','💜','🖤','💔','💖','🔥',
  '⭐','✨','💯','🎉','🎊','🎁','🌹','🌸','😋','🤤','😴','🥱','🤣','😂','🙏','💪',
]

function msgType(m: ChatMessage): number {
  const t = (m as any).type
  // WS 推送的信封 type 是 "ack"/"message" 字符串，真正的消息类型在 msgType 里；
  // REST/历史接口的 type 才是数字。这里统一归一化为数字。
  if (typeof t === 'number') return t
  return (m as any).msgType ?? 0
}

/** 从任意来源（WS 推送 / REST 返回 / 历史）的消息对象中解析出数字消息类型 */
function resolveType(m: any): number {
  if (m.msgType != null) return m.msgType
  if (typeof m.type === 'number') return m.type
  return 0
}

function scrollToBottom() {
  nextTick(() => {
    if (msgArea.value) msgArea.value.scrollTop = msgArea.value.scrollHeight
  })
}

function appendMessage(m: any) {
  if (!m || !m.id) return
  if (messages.value.some(x => x.id === m.id)) return // 去重
  messages.value.push({
    id: m.id,
    senderId: m.senderId,
    receiverId: m.receiverId,
    content: m.content,
    isRead: m.isRead ?? 0,
    createdTime: m.createdTime,
    type: resolveType(m),
    mediaUrl: m.mediaUrl ?? null,
    mediaName: m.mediaName ?? null,
    mediaSize: m.mediaSize ?? null,
  })
  scrollToBottom()
}

async function load() {
  loading.value = true
  try {
    const [profileRes, histRes, statsRes]: any[] = await Promise.all([
      getUserProfile(otherId),
      getHistory(otherId, 1, 50),
      getUserStats(otherId),
    ])
    other.value = profileRes.data
    isFollowing.value = statsRes.data?.isFollowing ?? false
    messages.value = (histRes.data || []).map((m: any) => ({
      ...m,
      type: resolveType(m),
      mediaUrl: m.mediaUrl ?? null,
      mediaName: m.mediaName ?? null,
      mediaSize: m.mediaSize ?? null,
    }))
    scrollToBottom()
    await markRead(otherId).catch(() => {})
  } finally {
    loading.value = false
  }
}

async function loadStickers() {
  try {
    const res: any = await getMyStickers()
    stickers.value = res.data || []
  } catch { stickers.value = [] }
}

async function onSend() {
  const content = text.value.trim()
  if (!content) return
  sending.value = true
  try {
    if (chatStore.connected) {
      chatStore.send(otherId, content)
    } else {
      const res: any = await restSend(otherId, content)
      appendMessage(res.data)
    }
    text.value = ''
  } catch { /* 由拦截器提示 */ } finally {
    sending.value = false
  }
}

// 插入 emoji 到输入框
function insertEmoji(e: string) {
  text.value += e
}

// 取消关注
async function onUnfollow() {
  try {
    await ElMessageBox.confirm(
      `确定取消关注「${other.value?.nickname || '该用户'}」吗？取消后将无法发送消息，需重新关注才能继续聊天。`,
      '取消关注',
      { confirmButtonText: '确定取消关注', cancelButtonText: '再想想', type: 'warning' }
    )
  } catch {
    return // 用户取消
  }
  followLoading.value = true
  try {
    await unfollowUser(otherId)
    isFollowing.value = false
    ElMessage.success('已取消关注')
  } catch { /* 由拦截器提示 */ } finally {
    followLoading.value = false
  }
}

// 重新关注
async function onFollow() {
  followLoading.value = true
  try {
    await followUser(otherId)
    isFollowing.value = true
    ElMessage.success('关注成功')
  } catch { /* 由拦截器提示 */ } finally {
    followLoading.value = false
  }
}

// 发送自定义表情图（type=1）
async function sendSticker(url: string) {
  emojiVisible.value = false
  try {
    if (chatStore.connected) {
      chatStore.sendMedia({ receiverId: otherId, type: 1, mediaUrl: url })
    } else {
      const res: any = await sendMediaMessage({ receiverId: otherId, type: 1, mediaUrl: url })
      appendMessage(res.data)
    }
  } catch { /* 由拦截器提示 */ }
}

// 上传图片作为自定义表情包
async function onUploadSticker(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const upRes: any = await uploadImage(file)
    const addRes: any = await addSticker(upRes.data)
    stickers.value.unshift(addRes.data)
    ElMessage.success('表情已添加（点击发送，右键删除）')
  } catch { /* 由拦截器提示 */ } finally {
    input.value = ''
  }
}

async function removeSticker(id: number) {
  try {
    await deleteSticker(id)
    stickers.value = stickers.value.filter(s => s.id !== id)
    ElMessage.success('已删除表情')
  } catch { /* 由拦截器提示 */ }
}

// 上传文件并发送（type=2）
async function onUploadFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('单个文件不能超过 50MB')
    input.value = ''
    return
  }
  fileUploading.value = true
  try {
    const upRes: any = await uploadChatFile(file)
    const payload = {
      receiverId: otherId,
      type: 2 as const,
      mediaUrl: upRes.data,
      mediaName: file.name,
      mediaSize: file.size,
    }
    if (chatStore.connected) {
      chatStore.sendMedia(payload)
    } else {
      const res: any = await sendMediaMessage(payload)
      appendMessage(res.data)
    }
  } catch { /* 由拦截器提示 */ } finally {
    fileUploading.value = false
    input.value = ''
  }
}

function previewSticker(url: string) {
  previewUrl.value = url
}

function formatSize(size?: number | null): string {
  if (!size) return ''
  if (size < 1024) return size + ' B'
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB'
  return (size / 1024 / 1024).toFixed(2) + ' MB'
}

function downloadFile(url: string, name: string) {
  dlFile(url, name)
}

// 实时回调：收到对方消息或自己消息的 ack 都在此追加
function onLiveMessage(data: any) {
  appendMessage(data)
  if (data.senderId === otherId) {
    markRead(otherId).catch(() => {})
  }
}

onMounted(async () => {
  await load()
  await loadStickers()
  chatStore.registerChat(otherId, onLiveMessage)
})

onBeforeUnmount(() => {
  chatStore.unregisterChat(otherId)
})
</script>

<style scoped>
.chat-page {
  height: calc(100vh - 74px);
  background: var(--bg-page);
  padding: 20px 24px 0;
  color: var(--text-primary);
}
.chat-wrap {
  max-width: 760px;
  height: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  background: var(--bg-card);
  border-radius: 16px 16px 0 0;
  overflow: hidden;
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-color);
}
.back { font-size: 22px; cursor: pointer; color: var(--text-secondary); }
.header-name { font-size: 16px; font-weight: 700; flex: 1; }
.header-actions { flex-shrink: 0; }

/* 取关限制提示条 */
.follow-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: rgba(255, 150, 0, 0.1);
  color: #e6a23c;
  font-size: 13px;
  border-top: 1px solid rgba(230, 162, 60, 0.2);
}
.follow-banner .el-icon { font-size: 16px; flex-shrink: 0; }

.msg-area {
  flex: 1;
  overflow-y: auto;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.msg-row { display: flex; align-items: flex-start; gap: 10px; }
.msg-row.mine { flex-direction: row-reverse; }
.msg-avatar { flex-shrink: 0; border: 1px solid var(--border-strong); }
.bubble {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 15px;
  line-height: 1.5;
  word-break: break-word;
  background: var(--bg-hover);
  color: var(--text-primary);
}
.msg-row.mine .bubble {
  background: linear-gradient(135deg, #FF2442, #FF6A82);
  color: #fff;
}
.sticker-bubble { padding: 4px; background: transparent !important; }
.sticker-img { width: 120px; max-width: 120px; height: auto; border-radius: 8px; cursor: zoom-in; display: block; }

/* 文件消息 */
.file-bubble { padding: 8px; max-width: 280px; background: var(--bg-hover) !important; color: var(--text-primary) !important; }
.msg-row.mine .file-bubble { background: var(--bg-hover) !important; color: var(--text-primary) !important; }
.file-card {
  display: flex; align-items: center; gap: 10px; padding: 8px 10px;
  border: 1px solid var(--border-strong); border-radius: 10px; cursor: pointer;
  transition: border-color 0.18s, box-shadow 0.18s;
}
.file-card:hover { border-color: var(--brand); box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.file-icon {
  width: 38px; height: 38px; border-radius: 8px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 20px;
  background: rgba(255,36,66,0.1); color: var(--brand);
}
.file-meta { flex: 1; min-width: 0; }
.file-name { font-size: 14px; font-weight: 600; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 160px; }
.file-size { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; }
.file-dl { color: var(--text-tertiary); font-size: 18px; }

.empty { text-align: center; color: var(--text-tertiary); margin: auto; font-size: 14px; }

.input-area {
  display: flex;
  gap: 8px;
  padding: 12px 18px 14px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-card);
  align-items: center;
}
.input-area.input-disabled {
  opacity: 0.5;
  pointer-events: none;
}
.tool-btn {
  flex-shrink: 0; padding: 0 12px !important; height: 38px;
  background: var(--bg-hover) !important; border: none !important; color: var(--text-secondary) !important;
}
.tool-btn:hover { color: var(--brand) !important; }
.tool-btn .el-icon { font-size: 20px; }
.input-area .el-button:not(.tool-btn) {
  background: #FF2442 !important;
  border-color: #FF2442 !important;
  font-weight: 700;
}

/* 表情面板 */
.emoji-panel { padding: 4px; }
.emoji-tabs { display: flex; gap: 6px; margin-bottom: 10px; border-bottom: 1px solid var(--border-color); }
.emoji-tabs button {
  padding: 6px 14px; border: none; background: transparent; cursor: pointer;
  font-size: 13px; color: var(--text-tertiary); border-bottom: 2px solid transparent;
}
.emoji-tabs button.active { color: var(--brand); border-bottom-color: var(--brand); font-weight: 600; }
.emoji-grid {
  display: grid; grid-template-columns: repeat(10, 1fr); gap: 2px;
  max-height: 220px; overflow-y: auto;
}
.emoji-cell {
  font-size: 20px; border: none; background: transparent; cursor: pointer;
  padding: 4px; border-radius: 6px; transition: background 0.15s;
}
.emoji-cell:hover { background: var(--bg-hover); }
.sticker-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
  max-height: 220px; overflow-y: auto; position: relative; min-height: 120px;
}
.sticker-cell {
  aspect-ratio: 1; border: 1px dashed var(--border-strong); border-radius: 8px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  cursor: pointer; overflow: hidden; background: var(--bg-hover);
  color: var(--text-tertiary); font-size: 12px; gap: 4px;
  transition: border-color 0.15s, color 0.15s;
}
.sticker-cell.add { font-size: 22px; }
.sticker-cell.add:hover { border-color: var(--brand); color: var(--brand); }
.sticker-cell:not(.add) { border-style: solid; }
.sticker-cell:not(.add):hover { border-color: var(--brand); }
.sticker-cell img { width: 100%; height: 100%; object-fit: cover; }
.sticker-empty {
  grid-column: 1 / -1; text-align: center; color: var(--text-tertiary);
  font-size: 13px; padding: 30px 0;
}
</style>
