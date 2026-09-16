<template>
  <div class="friends-page">
    <div class="friends-wrap">
      <h2 class="title">好友</h2>
      <p class="sub">你关注的人，可与之私聊。未互相关注时，对方回复前你只能发送一条消息。</p>

      <div class="friend-list" v-loading="loading">
        <div
          v-for="f in friends"
          :key="f.userId"
          class="friend-item"
          @click="goChat(f)"
        >
          <el-avatar :size="48" :src="f.avatarUrl" class="avatar">
            {{ f.nickname?.charAt(0) }}
          </el-avatar>
          <div class="meta">
            <div class="row1">
              <span class="nickname">{{ f.nickname }}</span>
              <span class="time" v-if="f.lastTime">{{ formatTime(f.lastTime) }}</span>
            </div>
            <div class="row2">
              <span class="preview" :class="{ unread: f.unread }">
                {{ previewText(f) }}
              </span>
              <span class="dot" v-if="f.unread"></span>
            </div>
          </div>
        </div>

        <div class="empty" v-if="!loading && !friends.length">
          <el-icon class="empty-icon"><ChatDotRound /></el-icon>
          <p>还没有关注的人，去发现页关注一些感兴趣的用户吧～</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { ChatDotRound } from '@element-plus/icons-vue'
import { getFriends, type ChatFriend } from '@/api/chat'

const router = useRouter()
const friends = ref<ChatFriend[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res: any = await getFriends()
    friends.value = res.data || []
  } finally {
    loading.value = false
  }
}

function goChat(f: ChatFriend) {
  router.push(`/chat/${f.userId}`)
}

function previewText(f: ChatFriend): string {
  if (!f.lastContent) return '开始聊天吧～'
  const prefix = f.lastSenderId === f.userId ? '' : '我：'
  const text = f.lastContent
  return prefix + (text.length > 24 ? text.slice(0, 24) + '…' : text)
}

function formatTime(t: string): string {
  const d = new Date(t.replace(' ', 'T'))
  if (isNaN(d.getTime())) return ''
  const today = new Date()
  if (d.toDateString() === today.toDateString()) {
    return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0')
  }
  return `${d.getMonth() + 1}/${d.getDate()}`
}

onMounted(load)
onActivated(load)
</script>

<style scoped>
.friends-page { min-height: calc(100vh - 74px); background: var(--bg-page); padding: 24px; color: var(--text-primary); }
.friends-wrap { max-width: 720px; margin: 0 auto; }
.title { font-size: 24px; font-weight: 800; margin: 0 0 6px; }
.sub { font-size: 13px; color: var(--text-tertiary); margin: 0 0 20px; }

.friend-list { display: flex; flex-direction: column; gap: 6px; }
.friend-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  background: var(--bg-card);
  border-radius: 14px;
  cursor: pointer;
  transition: background 0.18s, transform 0.18s;
}
.friend-item:hover { background: var(--bg-hover); transform: translateY(-1px); }
.avatar { flex-shrink: 0; border: 2px solid var(--border-strong); }
.meta { flex: 1; min-width: 0; }
.row1 { display: flex; align-items: center; justify-content: space-between; }
.nickname { font-size: 15px; font-weight: 700; color: var(--text-primary); }
.time { font-size: 12px; color: var(--text-muted); flex-shrink: 0; }
.row2 { display: flex; align-items: center; justify-content: space-between; margin-top: 6px; gap: 8px; }
.preview {
  font-size: 13px; color: var(--text-tertiary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.preview.unread { color: var(--text-primary); font-weight: 600; }
.dot {
  width: 9px; height: 9px; border-radius: 50%; background: #FF2442;
  flex-shrink: 0; box-shadow: 0 0 0 3px rgba(255,36,66,0.18);
}

.empty { text-align: center; color: var(--text-tertiary); padding: 60px 0; }
.empty-icon { font-size: 48px; color: var(--text-muted); margin-bottom: 12px; }
</style>
