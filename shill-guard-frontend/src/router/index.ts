import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/store/user'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true }
    },
    {
      path: '/',
      component: () => import('@/views/layout/MainLayout.vue'),
      children: [
        {
          path: '',
          name: 'Home',
          component: () => import('@/views/HomeView.vue')
        },
        {
          path: 'post/:id',
          name: 'PostDetail',
          component: () => import('@/views/PostDetailView.vue')
        },
        {
          path: 'search',
          name: 'Search',
          component: () => import('@/views/SearchView.vue'),
          meta: { public: true }
        },
        {
          path: 'publish',
          name: 'Publish',
          component: () => import('@/views/PublishView.vue'),
          meta: { requiresAuth: true }
        },
        {
          path: 'profile',
          name: 'Profile',
          component: () => import('@/views/ProfileView.vue'),
          meta: { requiresAuth: true }
        },
        {
          path: 'friends',
          name: 'Friends',
          component: () => import('@/views/FriendsView.vue'),
          meta: { requiresAuth: true }
        },
        {
          path: 'chat/:id',
          name: 'Chat',
          component: () => import('@/views/ChatView.vue'),
          meta: { requiresAuth: true }
        },
        {
          path: 'user/:id',
          name: 'UserProfile',
          component: () => import('@/views/UserView.vue'),
          meta: { public: true }
        }
      ]
    },
    {
      path: '/admin',
      component: () => import('@/views/layout/AdminLayout.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
      children: [
        {
          path: '',
          name: 'AdminDashboard',
          component: () => import('@/views/admin/DashboardView.vue')
        },
        {
          path: 'mute',
          name: 'AdminMute',
          component: () => import('@/views/admin/MuteManageView.vue')
        },
        {
          path: 'users',
          name: 'AdminUsers',
          component: () => import('@/views/admin/UserManageView.vue')
        },
        {
          path: 'reports',
          name: 'AdminReports',
          component: () => import('@/views/admin/ReportManageView.vue')
        },
        {
          path: 'posts',
          name: 'AdminPosts',
          component: () => import('@/views/admin/PostManageView.vue')
        },
        {
          path: 'videos',
          name: 'AdminVideos',
          component: () => import('@/views/admin/VideoManageView.vue')
        },
        {
          path: 'roles',
          name: 'AdminRoles',
          component: () => import('@/views/admin/RoleManageView.vue')
        },
        {
          path: 'ai-chat',
          name: 'AdminAiChat',
          component: () => import('@/views/admin/AiChatTestView.vue'),
          meta: { title: 'AI 对话测试' }
        },
        {
          path: 'ai-kb',
          name: 'AdminAiKb',
          component: () => import('@/views/admin/KnowledgeBaseView.vue'),
          meta: { title: '知识库管理' }
        },
        {
          path: 'ai-tests',
          name: 'AdminAiTests',
          component: () => import('@/views/admin/TestCaseGenView.vue'),
          meta: { title: '测试用例生成' }
        },
        {
          path: 'policy-agent',
          name: 'AdminPolicyAgent',
          component: () => import('@/views/admin/PolicyAgentView.vue'),
          meta: { title: '政策情报 Agent' }
        },
      ]
    }
  ]
})

router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  if (to.meta.requiresAuth && !userStore.isLoggedIn()) {
    next('/login')
  } else if (to.meta.requiresAdmin && !userStore.isAdmin()) {
    next('/')
  } else {
    next()
  }
})

export default router
