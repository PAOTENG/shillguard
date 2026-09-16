<template>
  <div class="main-layout">
    <!-- 左侧菜单栏 -->
    <aside class="sidebar">
      <!-- Logo -->
      <div class="brand" @click="router.push('/')">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 48 48" width="34" height="34" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="sgGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#FF2442" />
                <stop offset="100%" stop-color="#FF6A82" />
              </linearGradient>
            </defs>
            <path d="M24 3.5 7 9.2v11.3c0 9.6 6.9 17.9 17 21 10.1-3.1 17-11.4 17-21V9.2L24 3.5Z"
                  fill="url(#sgGrad)" />
            <path d="M16 24.2l5.4 5.4L32 19" fill="none" stroke="#fff" stroke-width="3.2"
                  stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </span>
        <span class="brand-text">ShillGuard</span>
      </div>

      <!-- 菜单 -->
      <nav class="nav-menu">
        <router-link to="/" class="nav-item" :class="{ active: isHome }">
          <el-icon><HomeFilled /></el-icon><span>发现</span>
        </router-link>

        <!-- 好友按钮：紧挨在“发现”下方，进入好友/聊天列表 -->
        <router-link to="/friends" class="nav-item" v-if="userStore.isLoggedIn()">
          <el-icon><ChatDotRound /></el-icon><span>好友</span>
        </router-link>

        <router-link to="/search" class="nav-item">
          <el-icon><Search /></el-icon><span>搜索</span>
        </router-link>
        <router-link to="/profile" class="nav-item" v-if="userStore.isLoggedIn()">
          <el-icon><User /></el-icon><span>个人中心</span>
        </router-link>
        <div class="nav-item ai-nav-item" :class="{ active: isAiPage }" @click="goAiChat">
          <el-icon><MagicStick /></el-icon><span>问AI</span>
        </div>
        <router-link to="/admin" class="nav-item" v-if="userStore.isAdmin()">
          <el-icon><Setting /></el-icon><span>管理后台</span>
        </router-link>
      </nav>

      <!-- 底部：头像 / 关于我们 / 主题切换 -->
      <div class="side-footer">
        <!-- 我的头像昵称组合：紧挨在“关于我们”上方 -->
        <template v-if="userStore.isLoggedIn()">
          <el-dropdown @command="handleCommand" trigger="click" placement="right-start">
            <div class="avatar-row">
              <el-avatar :size="40" :src="userStore.userInfo?.avatarUrl" class="user-avatar">
                {{ userStore.userInfo?.nickname?.charAt(0) }}
              </el-avatar>
              <div class="avatar-meta">
                <div class="avatar-name">{{ userStore.userInfo?.nickname }}</div>
                <div class="avatar-sub">@{{ userStore.userInfo?.username }}</div>
              </div>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <div class="dropdown-header">
                  <el-avatar :size="40" :src="userStore.userInfo?.avatarUrl">{{ userStore.userInfo?.nickname?.charAt(0) }}</el-avatar>
                  <div>
                    <div class="dropdown-name">{{ userStore.userInfo?.nickname }}</div>
                    <div class="dropdown-username">@{{ userStore.userInfo?.username }}</div>
                  </div>
                </div>
                <el-dropdown-item command="profile"><el-icon><User /></el-icon>个人中心</el-dropdown-item>
                <el-dropdown-item command="logout" divided><el-icon><SwitchButton /></el-icon>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
        <template v-else>
          <el-button class="login-btn" round @click="router.push('/login')">登录 / 注册</el-button>
        </template>

        <div class="footer-item" @click="aboutVisible = true">
          <el-icon><InfoFilled /></el-icon><span>关于我们</span>
        </div>
        <div class="footer-item" @click="settingsVisible = true">
          <el-icon><Setting /></el-icon><span>设置</span>
        </div>
        <div class="footer-item" @click="toggleTheme">
          <el-icon><Sunny v-if="isDark" /><Moon v-else /></el-icon>
          <span>{{ isDark ? '浅色模式' : '深色模式' }}</span>
        </div>
        <div v-if="userStore.isAdmin()" class="footer-item admin-entry" @click="openRagAdmin">
          <el-icon><Tools /></el-icon><span>文件向量库</span>
        </div>
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <div class="content-col">
      <!-- 顶部搜索栏（AI 对话页隐藏，因为输入框在底部） -->
      <header class="topbar" v-if="!isAiPage">
        <div class="topbar-inner">
          <div class="search-box" v-if="!isAiPage" :class="{ 'chat-active': chatMode }">
            <div class="search-box-content">
              <!-- 第一行：文本输入 -->
              <div class="search-row-1">
                <el-input
                  v-model="searchKeyword"
                  placeholder="搜索笔记或用户..."
                  @keyup.enter="handleSearch"
                  clearable
                  class="search-input-inner"
                >
                  <template #prefix><el-icon><Search /></el-icon></template>
                </el-input>
              </div>
              <!-- 第二行：附件 + Chat 按钮 -->
              <div class="search-row-2">
                <input type="file" ref="fileInputRef" accept=".pdf,.doc,.docx,.txt,.md,.csv" hidden @change="onFileChange" />
                <button class="attach-btn" @click="fileInputRef?.click()" :title="attachedFile ? attachedFile.name : '上传附件'">
                  <el-icon><Paperclip /></el-icon>
                </button>
                <!-- 附件回显 -->
                <div v-if="attachedFile" class="attach-chip">
                  <el-icon class="attach-chip-icon"><Document /></el-icon>
                  <span class="attach-chip-name">{{ attachedFile.name }}</span>
                  <span class="attach-chip-size">{{ formatFileSize(attachedFile.size) }}</span>
                  <el-icon class="attach-chip-close" @click.stop="clearAttachedFile"><Close /></el-icon>
                </div>
                <button class="chat-toggle-btn" :class="{ active: chatMode }" @click="toggleChatMode">
                  <span class="chat-text">Chat</span>
                </button>
              </div>
            </div>
            <!-- 发送按钮：垂直居中于整个搜索框（跨两行） -->
            <button class="search-send-btn" @click="handleSearch" title="搜索">
              <el-icon><Top /></el-icon>
            </button>
          </div>
          <!-- 发布笔记按钮：放在搜索框这一行的最右边，搜索页不显示 -->
          <button
            v-if="userStore.isLoggedIn() && route.path !== '/search'"
            class="topbar-publish"
            type="button"
            @click="router.push('/publish')"
          >
            <el-icon><Plus /></el-icon><span>发布笔记</span>
          </button>
        </div>
      </header>

      <!-- 主内容 -->
      <main class="main-content">
        <router-view />
      </main>
    </div>

    <!-- 关于我们 -->
    <el-dialog v-model="aboutVisible" title="关于 ShillGuard" width="560px" class="about-dialog">
      <div class="about-body">
        <div class="about-logo">
          <svg viewBox="0 0 48 48" width="48" height="48" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="sgGrad2" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#FF2442" />
                <stop offset="100%" stop-color="#FF6A82" />
              </linearGradient>
            </defs>
            <path d="M24 3.5 7 9.2v11.3c0 9.6 6.9 17.9 17 21 10.1-3.1 17-11.4 17-21V9.2L24 3.5Z" fill="url(#sgGrad2)" />
            <path d="M16 24.2l5.4 5.4L32 19" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
        <p class="about-desc">
          ShillGuard 是一个面向社交媒体的<strong>水军智能检测与禁言</strong>平台，
          致力于识别营销号/水军的刷量、误导与违规行为，守护健康的社区内容生态。
        </p>
        <div class="feature-list">
          <div class="feature-item">
            <el-icon class="fi-icon"><HomeFilled /></el-icon>
            <div><div class="fi-title">笔记瀑布流</div><div class="fi-text">浏览全站图文笔记，按话题分类筛选，沉浸式详情阅读。</div></div>
          </div>
          <div class="feature-item">
            <el-icon class="fi-icon"><EditPen /></el-icon>
            <div><div class="fi-title">发布与审核</div><div class="fi-text">支持图文/视频发布，内置敏感词检测，违规内容自动审核拦截。</div></div>
          </div>
          <div class="feature-item">
            <el-icon class="fi-icon"><Search /></el-icon>
            <div><div class="fi-title">智能搜索</div><div class="fi-text">一键搜索笔记与用户，快速定位感兴趣的内容与作者。</div></div>
          </div>
          <div class="feature-item">
            <el-icon class="fi-icon"><Star /></el-icon>
            <div><div class="fi-title">互动体系</div><div class="fi-text">点赞、收藏夹、评论回复、关注作者，完整的社交互动闭环。</div></div>
          </div>
          <div class="feature-item">
            <el-icon class="fi-icon"><Setting /></el-icon>
            <div><div class="fi-title">水军治理后台</div><div class="fi-text">数据看板、用户管理、举报处理与一键禁言，运营治理一体化。</div></div>
          </div>
          <div class="feature-item">
            <el-icon class="fi-icon"><Moon /></el-icon>
            <div><div class="fi-title">深色模式</div><div class="fi-text">支持浅色/深色主题一键切换，护眼舒适，随系统偏好自适应。</div></div>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 设置 -->
    <el-dialog v-model="settingsVisible" title="设置" width="480px" class="about-dialog">
      <div class="settings-body">
        <div class="setting-row">
          <div class="setting-info">
            <div class="setting-title">聊天文件下载路径</div>
            <div class="setting-desc">
              接收到的聊天文件将保存到该目录。浏览器需支持 File System Access API（Chrome/Edge 推荐）。
              <span v-if="!dlSupported" class="setting-warn">当前浏览器不支持，将使用默认下载。</span>
            </div>
            <div class="setting-current" v-if="dlDirName">
              当前：<strong>{{ dlDirName }}</strong>
            </div>
          </div>
        </div>
        <div class="setting-actions">
          <el-button type="primary" round @click="chooseDlDir" style="background:#FF2442;border-color:#FF2442">选择目录</el-button>
          <el-button round @click="clearDlDir" :disabled="!dlDirName">恢复默认</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Setting, Plus, Search, User, SwitchButton, HomeFilled, EditPen,
  InfoFilled, Sunny, Moon, Star, ChatDotRound, ChatDotSquare, Paperclip, Tools,
  Document, Close, MagicStick, Top
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { logout } from '@/api/auth'
import { useTheme } from '@/composables/useTheme'
import { useChatStore } from '@/store/chat'
import { useDownloadDir } from '@/composables/useDownloadDir'
import { useAiChatStore } from '@/store/aiChat'
import { onMounted, watch } from 'vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const chatStore = useChatStore()
const aiChatStore = useAiChatStore()
const searchKeyword = ref('')
const chatMode = ref(false)
const attachedFile = ref<File | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const aboutVisible = ref(false)
const settingsVisible = ref(false)
const { isDark, toggleTheme } = useTheme()
const { dirName: dlDirName, isSupported: dlSupported, chooseDir: chooseDlDir, clearDir: clearDlDir } = useDownloadDir()

const isHome = computed(() => route.path === '/')
const isAiPage = computed(() => route.path === '/search' && route.query.tab === 'ai')
// 跳转到 AI 对话页面
function goAiChat() {
  router.push({ path: '/search', query: { tab: 'ai' } })
}

// 文件向量库：仅管理员可见，新标签页打开 RAG 管理台
const openRagAdmin = () => {
  if (!userStore.isAdmin()) return
  window.open('http://localhost:8000/', '_blank')
}

// 登录后建立聊天 WebSocket；登出时断开
onMounted(() => { if (userStore.isLoggedIn()) chatStore.connect() })
watch(() => userStore.token, (t) => {
  if (t) chatStore.connect()
  else chatStore.disconnect()
})

function toggleChatMode() {
  chatMode.value = !chatMode.value
}
function onFileChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  attachedFile.value = f ?? null
  if (f) {
    chatMode.value = true
    aiChatStore.setFile(f)
    ElMessage.success(`已添加附件：${f.name}`)
  }
}

function clearAttachedFile() {
  attachedFile.value = null
  aiChatStore.clearFile()
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}
function handleSearch() {
  if (!searchKeyword.value.trim()) return
  const q: Record<string, string> = { keyword: searchKeyword.value.trim() }
  if (chatMode.value) {
    q.tab = 'ai'
  }
  router.push({ path: '/search', query: q })
  attachedFile.value = null
  if (fileInputRef.value) fileInputRef.value.value = ''
}

async function handleCommand(cmd: string) {
  if (cmd === 'profile') {
    router.push('/profile')
  } else if (cmd === 'logout') {
    try { await logout() } catch {}
    chatStore.disconnect()
    userStore.clear()
    ElMessage.success('已退出登录')
    router.push('/login')
  }
}
</script>

<style scoped>
* { box-sizing: border-box; }
.main-layout {
  min-height: 100vh;
  background: var(--bg-page);
  color: var(--text-primary);
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
  display: flex;
  transition: background-color 0.25s ease, color 0.25s ease;
}

/* ===== 左侧侧边栏 ===== */
.sidebar {
  position: sticky;
  top: 0;
  align-self: flex-start;
  height: 100vh;
  width: 220px;
  flex-shrink: 0;
  background: #fafafa;
  display: flex;
  flex-direction: column;
  padding: 20px 16px;
  /* 菜单栏换用更饱满的中文字体 */
  font-family: 'HarmonyOS Sans SC', 'Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', sans-serif;
  transition: background-color 0.25s ease, border-color 0.25s ease;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 4px 6px 18px;
}
.brand-mark { display: flex; line-height: 0; filter: drop-shadow(0 4px 8px rgba(255,36,66,0.25)); }
.brand-text {
  font-size: 23px;
  font-weight: 900;
  background: linear-gradient(135deg, #FF2442, #FF6A82);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  letter-spacing: -0.5px;
}

.nav-menu { display: flex; flex-direction: column; gap: 6px; }
.nav-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 11px 14px;
  border-radius: 999px;
  font-size: 17px;
  color: var(--text-secondary);
  font-weight: 700; /* 加粗 */
  transition: all 0.18s ease;
  cursor: pointer;
}
.nav-item .el-icon { font-size: 21px; color: var(--text-tertiary); transition: color 0.18s; }
.nav-item:hover { background: var(--bg-hover); color: var(--brand); }
.nav-item:hover .el-icon { color: var(--brand); }
.nav-item.active {
  background: linear-gradient(135deg, #FF2442, #FF6A82);
  color: #fff;
  box-shadow: 0 6px 16px rgba(255,36,66,0.28);
}
.nav-item.active .el-icon { color: #fff; }

/* 问AI 按钮：AI 专属紫蓝渐变高亮 */
.nav-item.ai-nav-item {
  background: linear-gradient(135deg, #6C5CE7, #A29BFE);
  color: #fff;
  box-shadow: 0 6px 16px rgba(108,92,231,0.28);
}
.nav-item.ai-nav-item .el-icon { color: #fff; }
.nav-item.ai-nav-item:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(108,92,231,0.40);
  color: #fff;
}
.nav-item.ai-nav-item:hover .el-icon { color: #fff; }

/* 发布笔记按钮：结构与 .nav-item 完全一致，仅红色背景，文字自然对齐 */
.publish-btn {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 11px 14px;
  border: none;
  border-radius: 999px;
  width: 100%;
  height: 44px;
  background: linear-gradient(135deg, #FF2442, #FF6A82);
  color: #fff;
  font-size: 17px;
  font-weight: 800;
  font-family: inherit;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(255,36,66,0.28);
  transition: transform 0.18s, box-shadow 0.18s;
}
.publish-btn:hover { transform: translateY(-1px); box-shadow: 0 8px 20px rgba(255,36,66,0.36); }
.publish-btn .el-icon { font-size: 21px; color: #fff; }
.publish-btn .el-icon svg { transform: scale(1.25); } /* 加号视觉加粗，不影响布局 */

/* ===== 底部 ===== */
.side-footer {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

.avatar-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px;
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.18s;
  margin-bottom: 2px;
}
.avatar-row:hover { background: var(--bg-hover); }
.user-avatar { border: 2px solid #FF2442; flex-shrink: 0; }
.avatar-meta { min-width: 0; }
.avatar-name { font-size: 14px; font-weight: 700; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.avatar-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.login-btn {
  width: 100%;
  background: var(--brand) !important;
  border-color: var(--brand) !important;
  color: #fff !important;
  font-weight: 700;
  height: 40px;
}
.login-btn:hover { background: #e01f3a !important; }

.footer-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  border-radius: 999px;
  font-size: 16px;
  color: var(--text-secondary);
  font-weight: 700;
  cursor: pointer;
  transition: all 0.18s ease;
}
.footer-item .el-icon { font-size: 20px; color: var(--text-tertiary); transition: color 0.18s; }
.footer-item:hover { background: var(--bg-hover); color: var(--brand); }
.footer-item:hover .el-icon { color: var(--brand); }
.admin-entry { color: var(--brand); }
.admin-entry .el-icon { color: var(--brand); }
.admin-entry:hover { background: var(--brand); color: #fff; }
.admin-entry:hover .el-icon { color: #fff; }

.dropdown-header { display: flex; align-items: center; gap: 12px; padding: 12px 16px 10px; border-bottom: 1px solid var(--border-color); margin-bottom: 4px; }
.dropdown-name { font-weight: 700; font-size: 14px; color: var(--text-primary); }
.dropdown-username { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

/* ===== 右侧内容区 ===== */
.content-col { flex: 1; min-width: 0; display: flex; flex-direction: column; }

.topbar {
  position: sticky;
  top: 0;
  z-index: 200;
  background: var(--bg-page);
  padding: 56px 0 14px;
}
/* 顶栏内容容器：与帖子区同宽(1280)、同水平 padding(24)、居中，
   使发布按钮右边缘与帖子右边缘对齐 */
.topbar-inner {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 24px;
  display: flex;
  align-items: center;
  gap: 16px;
}
.search-box {
  width: 100%;
  max-width: 830px;
  margin: 0 auto;
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 10px;
  background: var(--bg-card);
  border-radius: 18px;
  border: 1.5px solid var(--border-color);
  box-shadow: 0 2px 10px rgba(0,0,0,0.06);
  padding: 4px 14px 8px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.search-box-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.search-box:focus-within {
  border-color: rgba(255,36,66,0.35);
  box-shadow: 0 4px 16px rgba(255,36,66,0.10);
}
.search-box.chat-active {
  border-color: #13386c;
  box-shadow: 0 4px 16px rgba(19,56,108,0.15);
}
.search-row-1 { width: 100%; display: flex; align-items: center; gap: 8px; }
.search-row-1 .search-input-inner { flex: 1; }
/* 红色圆形发送/搜索按钮 —— 跨两行垂直居中 */
.search-send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  border: none;
  border-radius: 50%;
  background: linear-gradient(135deg, #FF2442, #FF6A82);
  color: #fff;
  font-size: 20px;
  cursor: pointer;
  box-shadow: 0 3px 10px rgba(255,36,66,0.30);
  transition: transform 0.15s, box-shadow 0.15s;
  align-self: center;
}
.search-send-btn:hover {
  transform: translateY(-1px) scale(1.05);
  box-shadow: 0 5px 14px rgba(255,36,66,0.40);
}
.search-send-btn:active { transform: scale(0.95); }
.search-row-2 {
  display: flex;
  align-items: center;
  gap: 4px;
  padding-top: 4px;
  justify-content: flex-start;
}
.attach-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 15px;
  cursor: pointer;
  transition: all 0.18s;
  flex-shrink: 0;
}
.attach-btn:hover { background: var(--bg-hover); color: #FF2442; }

/* 附件回显卡片 */
.attach-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(255, 36, 66, 0.08);
  border: 1px solid rgba(255, 36, 66, 0.2);
  font-size: 12px;
  color: var(--text-secondary);
  max-width: 240px;
  animation: chip-in 0.2s ease;
}
@keyframes chip-in {
  from { opacity: 0; transform: scale(0.9); }
  to { opacity: 1; transform: scale(1); }
}
.attach-chip-icon { color: #FF2442; font-size: 14px; flex-shrink: 0; }
.attach-chip-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}
.attach-chip-size { color: var(--text-tertiary); flex-shrink: 0; font-size: 11px; }
.attach-chip-close {
  cursor: pointer;
  color: var(--text-tertiary);
  font-size: 14px;
  flex-shrink: 0;
  transition: color 0.15s;
}
.attach-chip-close:hover { color: #FF2442; }

.chat-toggle-btn {
  display: flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: background 0.18s;
}
.chat-toggle-btn:hover { background: var(--bg-hover); }
.chat-toggle-btn.active { background: rgba(19,56,108,0.10); }
.chat-text {
  font-style: italic;
  font-weight: 800;
  font-size: 14px;
  font-family: Georgia, 'Palatino Linotype', Palatino, serif;
  color: #13386c;
  letter-spacing: 0.4px;
}
/* 顶栏右侧的发布笔记按钮 */
.topbar-publish {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 44px;
  padding: 0 20px;
  border: none;
  border-radius: 999px;
  background: linear-gradient(135deg, #FF2442, #FF6A82);
  color: #fff;
  font-size: 15px;
  font-weight: 800;
  font-family: inherit;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(255,36,66,0.28);
  transition: transform 0.18s, box-shadow 0.18s;
}
.topbar-publish:hover { transform: translateY(-1px); box-shadow: 0 8px 20px rgba(255,36,66,0.36); }
.topbar-publish .el-icon { font-size: 18px; }
:deep(.search-box .el-input__wrapper) {
  background: transparent;
  box-shadow: none !important;
  border: none;
  padding: 2px 4px;
  height: 42px;
}
:deep(.search-box .el-input__inner) { font-size: 15px; }

.search-dots {
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  gap: 4px;
  pointer-events: none;
}
.search-dots span {
  width: 5px; height: 5px; border-radius: 50%;
  background: #FF2442;
  opacity: 0.55;
}
.search-dots span:nth-child(2) { opacity: 0.35; }
.search-dots span:nth-child(3) { opacity: 0.18; }

.main-content { flex: 1; min-height: 0; padding-top: 16px; }

/* ===== 关于我们弹窗 ===== */
.about-body { padding: 4px 6px; }
.settings-body { padding: 4px 6px; }
.setting-row { display: flex; gap: 12px; }
.setting-info { flex: 1; }
.setting-title { font-size: 16px; font-weight: 700; color: var(--text-primary); margin-bottom: 6px; }
.setting-desc { font-size: 13px; color: var(--text-tertiary); line-height: 1.6; }
.setting-warn { color: #e6a23c; }
.setting-current { margin-top: 8px; font-size: 13px; color: var(--text-secondary); }
.setting-current strong { color: var(--brand); }
.setting-actions { margin-top: 18px; display: flex; gap: 10px; }
.about-logo { display: flex; justify-content: center; margin-bottom: 14px; filter: drop-shadow(0 6px 14px rgba(255,36,66,0.25)); }
.about-desc { font-size: 15px; line-height: 1.7; color: var(--text-secondary); margin: 0 0 22px; text-align: center; }
.about-desc strong { color: var(--brand); }
.feature-list { display: grid; grid-template-columns: 1fr 1fr; gap: 16px 18px; }
.feature-item { display: flex; gap: 12px; align-items: flex-start; }
.fi-icon {
  font-size: 24px;
  color: #fff;
  background: linear-gradient(135deg, #FF2442, #FF6A82);
  width: 40px; height: 40px;
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.fi-title { font-size: 15px; font-weight: 700; color: var(--text-primary); margin-bottom: 3px; }
.fi-text { font-size: 13px; line-height: 1.55; color: var(--text-tertiary); }

@media (max-width: 900px) {
  .sidebar { width: 72px; padding: 16px 8px; }
  .brand-text, .nav-item span, .avatar-meta, .publish-btn span, .footer-item span, .login-btn span { display: none; }
  .nav-item { justify-content: center; padding: 11px; }
  .publish-btn { justify-content: center; padding: 11px; height: 44px; }
  .footer-item { justify-content: center; padding: 11px; }
  .feature-list { grid-template-columns: 1fr; }
}
</style>
