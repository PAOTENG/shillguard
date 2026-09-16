<template>
  <div class="search-page" :class="{ 'ai-fullscreen': activeTab === 'ai' }">
    <!-- 双 Tab：帖子 / 用户 / Chat -->
    <el-tabs v-model="activeTab" class="search-tabs" @tab-change="onTabChange">
      <el-tab-pane label="帖子" name="posts">
        <!-- 帖子结果：瀑布流复用首页卡片样式 -->
        <div v-loading="loadingPosts" class="result-area">
          <div class="waterfall" v-if="posts.length">
            <div class="post-card" v-for="p in posts" :key="p.postId" @click="router.push(`/post/${p.postId}`)">
              <div class="card-cover" v-if="p.coverUrl">
                <img :src="p.coverUrl" loading="lazy" />
                <div class="cover-tag" v-if="p.topicTag"># {{ p.topicTag }}</div>
              </div>
              <div class="card-no-cover" v-else>
                <div class="cover-tag" v-if="p.topicTag"># {{ p.topicTag }}</div>
              </div>
              <div class="card-body">
                <h3 class="card-title" v-html="highlight(p.title)"></h3>
                <p class="card-text" v-if="!p.coverUrl" v-html="highlight(p.content?.slice(0, 100))"></p>
              </div>
              <div class="card-footer">
                <div class="card-author">
                  <el-avatar :size="22" :src="p.avatarUrl">{{ p.nickname?.charAt(0) }}</el-avatar>
                  <span class="author-name">{{ p.nickname || p.username }}</span>
                </div>
                <div class="card-likes" :class="{ liked: p.isLiked }">
                  <ThumbsUp /><span>{{ p.likeCount || 0 }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="empty" v-else-if="!loadingPosts && searched">
            <div class="empty-icon">🔍</div>
            <p>没有找到相关帖子</p>
          </div>
          <div class="empty" v-else-if="!loadingPosts && !searched">
            <div class="empty-icon">📝</div>
            <p>输入关键词，搜索你感兴趣的帖子</p>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="用户" name="users">
        <div v-loading="loadingUsers" class="result-area">
          <div class="user-list" v-if="users.length">
            <div class="user-card" v-for="u in users" :key="u.userId" @click="goProfile(u)">
              <el-avatar :size="48" :src="u.avatarUrl">{{ u.nickname?.charAt(0) }}</el-avatar>
              <div class="user-info">
                <div class="user-name">
                  <span v-html="highlight(u.nickname || u.username)"></span>
                  <el-tag v-if="u.status === 1" size="small" type="warning" effect="plain" class="mute-tag">该用户被禁言</el-tag>
                  <el-tag v-else-if="u.status === 2" size="small" type="danger" effect="plain" class="mute-tag">该用户被封禁</el-tag>
                </div>
                <div class="user-username" v-html="highlight('@' + u.username)"></div>
              </div>
              <el-button round size="small" class="view-btn">查看</el-button>
            </div>
          </div>
          <div class="empty" v-else-if="!loadingUsers && searched">
            <div class="empty-icon">👤</div>
            <p>没有找到相关用户</p>
          </div>
          <div class="empty" v-else-if="!loadingUsers && !searched">
            <div class="empty-icon">👥</div>
            <p>输入关键词，搜索用户</p>
          </div>
        </div>
      </el-tab-pane>
      <!-- Chat Tab -->
      <el-tab-pane name="ai">
        <template #label>
          <span class="ai-tab-label">✦ Chat</span>
        </template>
        <div class="ai-chat-container">
          <div class="ai-chat-layout">
            <!-- 左侧：历史对话列表 -->
            <div class="ai-sidebar">
              <button class="new-chat-btn" @click="aiChatStore.newSession()">+ 新对话</button>
              <div class="conv-list">
                <div
                  class="conv-item"
                  v-for="conv in aiChatStore.conversations"
                  :key="conv.thread_id"
                  :class="{ active: conv.thread_id === aiChatStore.threadId }"
                  @click="aiChatStore.loadHistory(conv.thread_id)"
                >
                  <div class="conv-title">{{ conv.title || '未命名对话' }}</div>
                  <div class="conv-preview">{{ conv.last_message }}</div>
                  <div class="conv-time" v-if="conv.last_time">{{ conv.last_time }}</div>
                </div>
              </div>
            </div>

            <!-- 右侧：当前对话 -->
            <div class="ai-main">
              <!-- 当前附件信息（持久保留） -->
              <div class="ai-current-file" v-if="aiChatStore.currentFile">
                <el-icon class="file-icon"><Document /></el-icon>
                <span class="file-name">{{ aiChatStore.currentFile.name }}</span>
                <span class="file-size">{{ formatFileSize(aiChatStore.currentFile.size) }}</span>
                <el-icon class="file-clear" @click="aiChatStore.clearFile()"><Close /></el-icon>
              </div>

              <!-- 对话列表 -->
              <div class="chat-list" v-if="aiChatStore.messages.length">
                <div class="chat-item" v-for="msg in aiChatStore.messages" :key="msg.id">
                  <!-- 用户问题 -->
                  <div class="chat-question">
                    <div class="chat-q-text">{{ msg.query }}</div>
                    <div class="chat-q-file" v-if="msg.fileName">
                      <el-icon><Document /></el-icon>
                      <span>{{ msg.fileName }}</span>
                      <span class="chat-q-file-size">{{ formatFileSize(msg.fileSize) }}</span>
                    </div>
                  </div>
                  <!-- AI 回答 -->
                  <div class="chat-answer">
                    <div class="chat-a-header">
                      <span class="ai-badge">✦ AI</span>
                      <span class="ai-status" v-if="msg.loading">回答中…</span>
                      <span class="ai-status done" v-else-if="msg.done">完成</span>
                      <button class="reanswer-btn" v-if="msg.done && !msg.loading" @click="aiChatStore.reanswer(msg.id)">↻ 重新回答</button>
                    </div>
                    <div class="ai-typing" v-if="msg.loading && !msg.answer">
                      <span></span><span></span><span></span>
                    </div>
                    <div class="ai-error" v-if="msg.error">⚠️ {{ msg.error }}</div>
                    <div class="ai-text" v-if="msg.answer">{{ msg.answer }}<span class="ai-cursor" v-if="msg.loading"></span></div>
                  </div>
                </div>
              </div>

              <!-- 空状态 -->
              <div class="empty" v-if="!aiChatStore.messages.length">
                <div class="empty-icon">✦</div>
                <p>在下方输入框中输入问题，向 AI 提问</p>
              </div>
            </div>
          </div>

          <!-- 底部输入栏 -->
          <div class="ai-input-bar">
            <input type="file" ref="aiFileInputRef" accept=".pdf,.doc,.docx,.txt,.md,.csv" hidden @change="onAiFileChange" />
            <button class="ai-attach-btn" @click="aiFileInputRef?.click()" title="上传附件">
              <el-icon><Paperclip /></el-icon>
            </button>
            <div v-if="aiChatStore.currentFile" class="ai-input-chip">
              <el-icon><Document /></el-icon>
              <span class="chip-name">{{ aiChatStore.currentFile.name }}</span>
              <el-icon class="chip-close" @click="aiChatStore.clearFile()"><Close /></el-icon>
            </div>
            <el-input
              v-model="aiInput"
              placeholder="问 AI 任何问题..."
              @keyup.enter="sendAiMessage"
              class="ai-input-field"
            />
            <button class="ai-send-btn" @click="sendAiMessage" title="发送">
              <el-icon><Top /></el-icon>
            </button>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 热门搜索：未搜索且非 AI tab 时展示 -->
    <div class="hot-search" v-if="!searched && activeTab !== 'ai'">
      <div class="hot-title">🔥 热门搜索</div>
      <div class="hot-chips">
        <button v-for="h in hotWords" :key="h" @click="keyword = h; doSearch()" class="hot-chip">{{ h }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Document, Close, Top, Paperclip } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getPostList } from '@/api/post'
import { searchUsers } from '@/api/user'
import { useAiChatStore } from '@/store/aiChat'
import ThumbsUp from '@/components/ThumbsUp.vue'

const route = useRoute()
const router = useRouter()
const aiChatStore = useAiChatStore()

const keyword = ref('')
const activeTab = ref<'posts' | 'users' | 'ai'>('posts')
const searched = ref(false)

// AI 底部输入栏
const aiInput = ref('')
const aiFileInputRef = ref<HTMLInputElement | null>(null)

const posts = ref<any[]>([])
const users = ref<any[]>([])
const loadingPosts = ref(false)
const loadingUsers = ref(false)

// 热门搜索词（示例数据；后续可接后端热搜榜）
const hotWords = ['科技', '财经', '生活', '美食', '旅行', '健身', '游戏', '动漫']

function escapeHtml(s: string) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
// 关键词高亮（避免 XSS：先转义再插高亮标签）
function highlight(text: string) {
  if (!text || !keyword.value) return escapeHtml(text)
  const kw = keyword.value
  const esc = escapeHtml(text)
  const re = new RegExp(`(${kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
  return esc.replace(re, '<em>$1</em>')
}

async function searchPosts() {
  if (!keyword.value.trim()) { posts.value = []; return }
  loadingPosts.value = true
  try {
    const res: any = await getPostList(1, 40, undefined, keyword.value.trim())
    posts.value = res.data?.records || []
  } finally {
    loadingPosts.value = false
  }
}

async function searchUsersFn() {
  if (!keyword.value.trim()) { users.value = []; return }
  loadingUsers.value = true
  try {
    const res: any = await searchUsers(keyword.value.trim())
    users.value = res.data || []
  } finally {
    loadingUsers.value = false
  }
}

function doSearch() {
  if (!keyword.value.trim()) return
  searched.value = true
  const q: Record<string, string> = { keyword: keyword.value.trim() }
  if (activeTab.value === 'ai') q.tab = 'ai'
  router.replace({ query: q })
  if (activeTab.value === 'posts') searchPosts()
  else if (activeTab.value === 'users') searchUsersFn()
  else aiChatStore.ask(keyword.value.trim())
}

function onTabChange(tab: string) {
  if (tab === 'ai') {
    router.replace({ query: { keyword: keyword.value, tab: 'ai' } })
    return
  }
  if (!searched.value) return
  if (tab === 'posts') searchPosts()
  else searchUsersFn()
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}

function goProfile(u: any) {
  // 跳到该用户的公开主页（展示统计 + 关注 + TA 的笔记）
  router.push(`/user/${u.userId}`)
}

// AI 底部输入栏：发送消息
function sendAiMessage() {
  const q = aiInput.value.trim()
  if (!q) return
  aiInput.value = ''
  keyword.value = q
  searched.value = true
  activeTab.value = 'ai'
  router.replace({ query: { keyword: q, tab: 'ai' } })
  aiChatStore.ask(q)
}

// AI 底部输入栏：文件上传
function onAiFileChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) {
    aiChatStore.setFile(f)
    ElMessage.success(`已添加附件：${f.name}`)
  }
}

onMounted(() => {
  aiChatStore.loadConversationList()
  const kw = route.query.keyword as string
  const tab = route.query.tab as string
  // 即使没有 keyword，也要根据 tab 切换到对应标签（比如点"问AI"进来时没有 keyword）
  if (tab === 'ai') {
    activeTab.value = 'ai'
  }
  if (kw) {
    keyword.value = kw
    if (tab === 'ai') {
      searched.value = true
      if (aiChatStore.lastQuery !== kw.trim()) {
        aiChatStore.ask(kw)
      }
    } else {
      doSearch()
    }
  }
})

watch(() => route.query, (q) => {
  const kw = q.keyword as string
  const tab = q.tab as string
  // 没有 keyword 也要切换 tab（比如从帖子 tab 点"问AI"切过来）
  if (tab === 'ai') {
    activeTab.value = 'ai'
  }
  if (!kw) return
  keyword.value = kw
  if (tab === 'ai') {
    searched.value = true
    if (aiChatStore.lastQuery !== kw.trim()) {
      aiChatStore.ask(kw)
    }
  } else {
    doSearch()
  }
})
</script>

<style scoped>
* { box-sizing: border-box; }
.search-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 24px 60px;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
}
/* AI 对话页：填满屏幕，只有消息区滚动 */
.search-page.ai-fullscreen {
  max-width: 1280px;
  padding: 16px 24px 0;
  height: calc(100vh - 16px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.search-page.ai-fullscreen .search-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.search-page.ai-fullscreen :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
}
.search-page.ai-fullscreen :deep(.el-tab-pane) {
  height: 100%;
}
.search-header { margin-bottom: 12px; }
:deep(.search-input .el-input__wrapper) { border-radius: 24px; }
:deep(.search-input .el-input-group__append) {
  border-radius: 0 24px 24px 0;
  padding: 0;
  overflow: hidden;
}
:deep(.search-input .el-input-group__append .el-button) { height: 100%; border-radius: 0 24px 24px 0; }

.search-tabs { background: #fff; border-radius: 16px; padding: 8px 20px 20px; box-shadow: 0 1px 6px rgba(0,0,0,0.05); }
.result-area { min-height: 200px; }

/* 瀑布流帖子卡片（与首页一致风格） */
.waterfall { columns: 4; column-gap: 12px; }
@media (max-width: 1100px) { .waterfall { columns: 3; } }
@media (max-width: 768px) { .waterfall { columns: 2; } }
.post-card {
  break-inside: avoid; margin-bottom: 12px; display: inline-block; width: 100%;
  background: #fff; border-radius: 12px; overflow: hidden; cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  border: 1px solid #F2F2F2;
}
.post-card:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,0.12); }
.card-cover { position: relative; overflow: hidden; background: #F5F5F5; }
.card-cover img { width: 100%; display: block; }
.cover-tag {
  position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.45); color: #fff;
  font-size: 11px; padding: 2px 8px; border-radius: 10px; backdrop-filter: blur(4px);
}
.card-no-cover { background: linear-gradient(135deg, #fff5f6, #fff); min-height: 20px; position: relative; }
.card-no-cover .cover-tag { position: relative; top: 0; left: 0; display: inline-block; margin: 10px; background: rgba(255,36,66,0.1); color: #FF2442; }
.card-body { padding: 10px 12px 6px; }
.card-title { font-size: 14px; font-weight: 600; color: #1a1a1a; margin: 0 0 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.5; }
.card-text { font-size: 13px; color: #767676; margin: 0; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.5; }
.card-footer { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px 10px; }
.card-author { display: flex; align-items: center; gap: 6px; }
.author-name { font-size: 12px; color: #767676; max-width: 90px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-likes { display: flex; align-items: center; gap: 4px; font-size: 12px; color: #999; }
.card-likes.liked { color: #FF2442; }

/* 用户卡片 */
.user-list { display: flex; flex-direction: column; gap: 10px; }
.user-card {
  display: flex; align-items: center; gap: 14px; padding: 14px 16px; background: #FAFAFA;
  border-radius: 12px; cursor: pointer; transition: background 0.18s; border: 1px solid #F2F2F2;
}
.user-card:hover { background: #fff5f6; border-color: #FFD0D8; }
.user-info { flex: 1; min-width: 0; }
.user-name { font-size: 15px; font-weight: 600; color: #1a1a1a; display: flex; align-items: center; gap: 6px; }
.mute-tag { font-size: 12px; }
.user-username { font-size: 13px; color: #999; margin-top: 2px; }
.view-btn { color: #FF2442; border-color: #FFB8C0; }
.view-btn:hover { background: #fff5f6; border-color: #FF2442; }

/* 高亮 */
:deep(em) { color: #FF2442; font-style: normal; font-weight: 600; background: rgba(255,36,66,0.08); border-radius: 3px; padding: 0 2px; }

/* 空状态 */
.empty { text-align: center; padding: 60px 20px; color: #999; }
.empty-icon { font-size: 56px; margin-bottom: 12px; }
.empty p { font-size: 15px; margin: 0; }

/* AI Chat Tab */
.ai-tab-label { font-weight: 700; color: #13386c; }
.ai-chat-container { display: flex; flex-direction: column; height: 100%; min-height: 500px; }
.ai-chat-layout { display: flex; gap: 16px; flex: 1; min-height: 0; overflow: hidden; padding: 12px 0; }

/* 左侧侧边栏 */
.ai-sidebar { width: 240px; flex-shrink: 0; border-right: 1px solid #e8e8e8; padding-right: 12px; overflow-y: auto; min-height: 0; }
.ai-sidebar .new-chat-btn {
  width: 100%; font-size: 14px; color: #13386c; background: #f0f4ff;
  border: 1px solid #c7d2fe; border-radius: 8px; padding: 8px 0;
  cursor: pointer; transition: all 0.18s; margin-bottom: 12px;
}
.ai-sidebar .new-chat-btn:hover { background: #e0e7ff; border-color: #13386c; }
.conv-list { display: flex; flex-direction: column; gap: 4px; }
.conv-item {
  padding: 10px 12px; border-radius: 8px; cursor: pointer; transition: background 0.15s;
  border: 1px solid transparent;
}
.conv-item:hover { background: #f5f7fa; }
.conv-item.active { background: #eef2ff; border-color: #c7d2fe; }
.conv-title { font-size: 13px; font-weight: 600; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.conv-preview { font-size: 12px; color: #999; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.conv-time { font-size: 11px; color: #bbb; margin-top: 4px; font-family: "SF Mono", "Consolas", monospace; }
.conv-time { font-size: 11px; color: #bbb; margin-top: 4px; font-family: "SF Mono", "Consolas", monospace; }

/* 右侧主区域 */
.ai-main { flex: 1; min-width: 0; overflow-y: auto; padding-right: 4px; }

/* 当前附件 */
.ai-current-file {
  display: flex; align-items: center; gap: 8px;
  background: #f0f4ff; border: 1px solid #d0deff; border-radius: 10px;
  padding: 8px 14px; margin-bottom: 16px; font-size: 13px;
}
.ai-current-file .file-icon { color: #13386c; font-size: 16px; }
.ai-current-file .file-name { font-weight: 600; color: #333; }
.ai-current-file .file-size { color: #888; }
.ai-current-file .file-clear { cursor: pointer; color: #999; margin-left: auto; }
.ai-current-file .file-clear:hover { color: #e01f3a; }

/* 对话列表 */
.chat-list { display: flex; flex-direction: column; gap: 20px; }
.chat-item { display: flex; flex-direction: column; gap: 8px; }

/* 用户问题 */
.chat-question {
  background: #f5f5f5; border-radius: 12px 12px 4px 12px;
  padding: 12px 16px; margin-left: auto; max-width: 80%; align-self: flex-end;
}
.chat-q-text { font-size: 15px; color: #1a1a1a; line-height: 1.6; word-break: break-word; }
.chat-q-file {
  display: flex; align-items: center; gap: 5px; margin-top: 6px;
  font-size: 12px; color: #888; background: #fff; border-radius: 6px;
  padding: 3px 8px; width: fit-content;
}
.chat-q-file-size { color: #aaa; }

/* AI 回答 */
.chat-answer { max-width: 90%; }
.chat-a-header {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 8px;
}
.ai-badge {
  background: linear-gradient(135deg, #13386c, #2563a8);
  color: #fff; font-size: 12px; font-weight: 700;
  padding: 3px 10px; border-radius: 999px;
}
.ai-status { font-size: 13px; color: #999; }
.ai-status.done { color: #13386c; font-weight: 600; }
.reanswer-btn {
  font-size: 12px; color: #13386c; background: none;
  border: 1px solid #cdd8ee; border-radius: 6px;
  padding: 2px 10px; cursor: pointer; margin-left: auto;
  transition: all 0.18s;
}
.reanswer-btn:hover { background: #f0f4ff; border-color: #13386c; }
.ai-text {
  font-size: 15px; line-height: 1.9; color: #222;
  white-space: pre-wrap; word-break: break-word;
  background: #f8f9ff; border-left: 3px solid #13386c;
  border-radius: 0 12px 12px 0; padding: 16px 20px;
}
.ai-cursor {
  display: inline-block; width: 2px; height: 1em;
  background: #13386c; margin-left: 2px; vertical-align: middle;
  animation: blink 0.9s infinite;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
.ai-typing {
  display: flex; gap: 6px; padding: 20px 0; justify-content: center;
}
.ai-typing span {
  width: 8px; height: 8px; border-radius: 50%; background: #13386c;
  animation: bounce 1.2s infinite;
}
.ai-typing span:nth-child(2) { animation-delay: 0.2s; }
.ai-typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce { 0%,80%,100%{transform:scale(0.6);opacity:0.4} 40%{transform:scale(1);opacity:1} }
.ai-error { padding: 16px; color: #e01f3a; font-size: 14px; }

/* 热门搜索 */
.hot-search { margin-top: 20px; background: #fff; border-radius: 16px; padding: 20px; box-shadow: 0 1px 6px rgba(0,0,0,0.05); }
.hot-title { font-size: 15px; font-weight: 600; color: #1a1a1a; margin-bottom: 14px; }
.hot-chips { display: flex; flex-wrap: wrap; gap: 10px; }
.hot-chip {
  padding: 6px 16px; border-radius: 18px; border: 1.5px solid #EBEBEB; background: #fff;
  color: #555; font-size: 14px; cursor: pointer; transition: all 0.18s;
}
.hot-chip:hover { border-color: #FF2442; color: #FF2442; transform: translateY(-1px); }

/* AI 底部输入栏 */
.ai-input-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fff;
  border: 1.5px solid #e0e0e0;
  border-radius: 24px;
  padding: 8px 12px;
  margin-top: 12px;
  margin-bottom: 16px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.06);
  transition: border-color 0.2s, box-shadow 0.2s;
  flex-shrink: 0;
}
.ai-input-bar:focus-within {
  border-color: rgba(255,36,66,0.35);
  box-shadow: 0 4px 16px rgba(255,36,66,0.10);
}
.ai-attach-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border: none;
  border-radius: 50%;
  background: #f5f5f5;
  color: #888;
  font-size: 18px;
  cursor: pointer;
  transition: all 0.15s;
}
.ai-attach-btn:hover { background: #fff5f6; color: #FF2442; }
.ai-input-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 8px;
  background: rgba(255,36,66,0.08);
  border: 1px solid rgba(255,36,66,0.2);
  font-size: 12px;
  color: #555;
  max-width: 200px;
  flex-shrink: 0;
}
.ai-input-chip .chip-name {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-weight: 600;
}
.ai-input-chip .chip-close { cursor: pointer; color: #999; flex-shrink: 0; }
.ai-input-chip .chip-close:hover { color: #FF2442; }
.ai-input-field { flex: 1; }
:deep(.ai-input-field .el-input__wrapper) {
  box-shadow: none !important;
  background: transparent;
}
:deep(.ai-input-field .el-input__inner) { font-size: 15px; border: none; }
.ai-send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border: none;
  border-radius: 50%;
  background: linear-gradient(135deg, #FF2442, #FF6A82);
  color: #fff;
  font-size: 20px;
  cursor: pointer;
  box-shadow: 0 3px 10px rgba(255,36,66,0.30);
  transition: transform 0.15s, box-shadow 0.15s;
}
.ai-send-btn:hover {
  transform: translateY(-1px) scale(1.05);
  box-shadow: 0 5px 14px rgba(255,36,66,0.40);
}
.ai-send-btn:active { transform: scale(0.95); }
</style>
