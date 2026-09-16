<template>
  <div class="admin-layout">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-logo" @click="router.push('/')">
        <svg viewBox="0 0 48 48" width="32" height="32" xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0;filter:drop-shadow(0 4px 8px rgba(255,36,66,0.25));">
          <defs>
            <linearGradient id="sgGradAdmin" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="#FF2442" />
              <stop offset="100%" stop-color="#FF6A82" />
            </linearGradient>
          </defs>
          <path d="M24 3.5 7 9.2v11.3c0 9.6 6.9 17.9 17 21 10.1-3.1 17-11.4 17-21V9.2L24 3.5Z" fill="url(#sgGradAdmin)" />
          <path d="M16 24.2l5.4 5.4L32 19" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <span class="logo-text">ShillGuard</span>
      </div>
      <div class="sidebar-label">管理控制台</div>
      <nav class="sidebar-nav">
        <template v-for="(item, idx) in navItems" :key="item.path">
          <div
            v-if="item.group && (idx === 0 || navItems[idx - 1].group !== item.group)"
            class="nav-group-label"
          >{{ item.group }}</div>
          <router-link
            :to="item.path"
            class="nav-item"
            :class="{ active: route.path === item.path }"
          >
            <el-icon :size="18"><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </router-link>
        </template>
      </nav>
      <div class="sidebar-footer">
        <div class="admin-user">
          <el-avatar :size="32" :src="userStore.userInfo?.avatarUrl">{{ userStore.userInfo?.nickname?.charAt(0) }}</el-avatar>
          <span>{{ userStore.userInfo?.nickname }}</span>
        </div>
        <el-button text @click="handleLogout" class="logout-btn">
          <el-icon><SwitchButton /></el-icon>
        </el-button>
      </div>
    </aside>

    <!-- 主区域 -->
    <div class="admin-main-wrap">
      <header class="admin-header">
        <div class="page-title">{{ route.meta.title || '管理后台' }}</div>
        <div class="header-actions">
          <el-button round size="small" @click="router.push('/')">
            <el-icon><ArrowLeft /></el-icon> 返回前台
          </el-button>
        </div>
      </header>
      <main class="admin-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DataBoard, User, Warning, SwitchButton, ArrowLeft, Document, VideoPlay, Lock, Mute, ChatDotRound, Collection, EditPen, Reading } from '@element-plus/icons-vue'
import { logout } from '@/api/auth'
import { useUserStore } from '@/store/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const navItems = [
  { path: '/admin', label: '数据概览', icon: DataBoard, group: '' },
  { path: '/admin/posts', label: '帖子管理', icon: Document, group: '' },
  { path: '/admin/videos', label: '视频管理', icon: VideoPlay, group: '' },
  { path: '/admin/users', label: '用户管理', icon: User, group: '' },
  { path: '/admin/roles', label: '角色权限', icon: Lock, group: '' },
  { path: '/admin/reports', label: '举报处理', icon: Warning, group: '' },
  { path: '/admin/mute', label: '禁言管理', icon: Mute, group: '' },
  { path: '/admin/policy-agent', label: '政策情报 Agent', icon: Reading, group: '政策情报' },
  { path: '/admin/ai-chat', label: 'AI 对话测试', icon: ChatDotRound, group: 'AI 工具' },
  { path: '/admin/ai-kb', label: '知识库管理', icon: Collection, group: 'AI 工具' },
  { path: '/admin/ai-tests', label: '测试用例生成', icon: EditPen, group: 'AI 工具' },
]

async function handleLogout() {
  try { await logout() } catch {}
  userStore.clear()
  ElMessage.success('已退出')
  router.push('/login')
}
</script>

<style scoped>
* { box-sizing: border-box; }
.admin-layout {
  display: flex;
  min-height: 100vh;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
}

/* 侧边栏 */
.sidebar {
  width: 220px;
  flex-shrink: 0;
  background: #1a1a2e;
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: hidden;
}
.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 20px 8px;
  cursor: pointer;
}
.logo-text {
  font-size: 20px;
  font-weight: 900;
  background: linear-gradient(135deg, #FF2442, #FF6A82);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  letter-spacing: -0.5px;
}
.sidebar-label { font-size: 11px; color: rgba(255,255,255,0.3); padding: 0 20px 16px; text-transform: uppercase; letter-spacing: 1px; }
.nav-group-label { font-size: 11px; color: rgba(255,255,255,0.25); padding: 14px 12px 4px; text-transform: uppercase; letter-spacing: 1px; }
.sidebar-nav { flex: 1; padding: 4px 12px; display: flex; flex-direction: column; gap: 4px; }
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  color: rgba(255,255,255,0.6);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.18s;
}
.nav-item:hover { background: rgba(255,255,255,0.08); color: #fff; }
.nav-item.active { background: rgba(255,36,66,0.2); color: #FF2442; }
.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid rgba(255,255,255,0.08);
  display: flex;
  align-items: center;
  gap: 10px;
}
.admin-user { display: flex; align-items: center; gap: 8px; color: rgba(255,255,255,0.7); font-size: 13px; flex: 1; overflow: hidden; }
.admin-user span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.logout-btn { color: rgba(255,255,255,0.4) !important; }
.logout-btn:hover { color: #FF2442 !important; }

/* 主区域 */
.admin-main-wrap { flex: 1; display: flex; flex-direction: column; background: #F0F2F5; overflow: hidden; }
.admin-header {
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #EBEBEB;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
}
.page-title { font-size: 16px; font-weight: 700; color: #1a1a1a; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.admin-content { flex: 1; padding: 24px; overflow-y: auto; }
</style>
