<template>
  <div class="profile-page">
    <div class="profile-wrap">
      <!-- 用户卡片 -->
      <div class="profile-card">
        <div class="profile-bg"></div>
        <div class="profile-main">
          <div class="avatar-wrap" @click="avatarInput?.click()" :class="{ uploading: avatarUploading }">
            <el-avatar :size="80" :src="userStore.userInfo?.avatarUrl" class="profile-ava">
              {{ userStore.userInfo?.nickname?.charAt(0) }}
            </el-avatar>
            <div class="avatar-mask">
              <el-icon v-if="!avatarUploading"><Camera /></el-icon>
              <span v-if="!avatarUploading">更换</span>
              <span v-else>上传中</span>
            </div>
            <input ref="avatarInput" type="file" accept="image/png,image/jpeg,image/gif,image/webp"
                   style="display:none" @change="onAvatarChange" />
          </div>
          <div class="profile-info" v-if="!editing">
            <h2 class="profile-name">{{ userStore.userInfo?.nickname }}</h2>
            <p class="profile-username">@{{ userStore.userInfo?.username }}</p>
            <p class="profile-contact" v-if="profile?.phone">📱 {{ profile.phone }}</p>
            <p class="profile-contact" v-if="profile?.email">✉️ {{ profile.email }}</p>
            <span class="profile-badge" v-if="userStore.isAdmin()">
              <el-icon><Setting /></el-icon> 管理员
            </span>
          </div>
          <div class="edit-form" v-else>
            <el-input v-model="form.nickname" placeholder="昵称" size="large" style="max-width:200px" />
            <el-input v-model="form.phone" placeholder="手机号（选填）" size="large" style="max-width:200px" />
            <el-input v-model="form.email" placeholder="邮箱（选填）" size="large" style="max-width:220px" />
            <el-button type="primary" :loading="loading" @click="handleUpdate" round
              style="background:#FF2442;border-color:#FF2442">保存</el-button>
            <el-button @click="editing=false" round>取消</el-button>
          </div>
          <el-button v-if="!editing" class="edit-btn" round @click="startEdit">
            <el-icon><Edit /></el-icon> 编辑资料
          </el-button>
        </div>
        <div class="profile-stats">
          <div class="stat-item">
            <span class="stat-num">{{ myPosts.length }}</span>
            <span class="stat-label">笔记</span>
          </div>
          <div class="stat-item">
            <span class="stat-num">{{ totalLikes }}</span>
            <span class="stat-label">获赞</span>
          </div>
          <div class="stat-item">
            <span class="stat-num">{{ myPosts.reduce((s,p)=>s+(p.commentCount||0),0) }}</span>
            <span class="stat-label">评论</span>
          </div>
        </div>
      </div>

      <!-- 标签栏 -->
      <div class="tab-bar">
        <button v-for="t in tabs" :key="t.key" class="tab-btn" :class="{ active: activeTab === t.key }" @click="switchTab(t.key)">
          {{ t.label }}
        </button>
      </div>

      <!-- 我的笔记 -->
      <div class="panel-card" v-show="activeTab === 'posts'">
        <div class="section-head">
          <div class="section-title">我的笔记</div>
          <div class="status-filter">
            <button :class="{ active: statusFilter === 'all' }" @click="statusFilter='all'">全部</button>
            <button :class="{ active: statusFilter === 'pass' }" @click="statusFilter='pass'">已通过</button>
            <button :class="{ active: statusFilter === 'reject' }" @click="statusFilter='reject'">审核不通过</button>
          </div>
        </div>
        <div class="waterfall" v-if="filteredPosts.length" v-loading="loadingPosts">
          <div class="post-card" v-for="p in filteredPosts" :key="p.postId"
            @click="p.status === 0 && router.push(`/post/${p.postId}`)">
            <div class="card-cover" v-if="p.coverUrl">
              <img :src="p.coverUrl" loading="lazy" />
            </div>
            <div class="card-cover video-cover" v-else-if="p.mediaUrl">
              <el-icon size="28" color="#fff"><VideoPlay /></el-icon>
            </div>
            <div class="card-body">
              <div class="card-title">{{ p.title }}</div>
              <div class="card-row">
                <span class="status-tag" :class="statusClass(p.status)">{{ statusText(p.status) }}</span>
                <div class="card-meta">
                  <el-icon><Star /></el-icon>{{ p.likeCount||0 }}
                  <el-icon style="margin-left:8px"><ChatDotSquare /></el-icon>{{ p.commentCount||0 }}
                </div>
              </div>
              <div class="reject-reason" v-if="p.status === 3">审核不通过</div>
            </div>
          </div>
        </div>
        <div class="empty-state" v-else-if="!loadingPosts">
          📝 还没有笔记，<el-button text type="primary" @click="router.push('/publish')" style="color:#FF2442">去发布第一篇</el-button>
        </div>
      </div>

      <!-- 我的关注：用户列表，点进去看 TA 的主页 -->
      <div class="panel-card" v-show="activeTab === 'followings'">
        <div class="section-head">
          <div class="section-title">我的关注</div>
        </div>
        <div class="following-list" v-if="followings.length" v-loading="loadingRecords && false">
          <div class="following-item" v-for="u in followings" :key="u.userId" @click="router.push(`/user/${u.userId}`)">
            <el-avatar :size="48" :src="u.avatarUrl">{{ u.nickname?.charAt(0) }}</el-avatar>
            <div class="f-info">
              <div class="f-name">{{ u.nickname }}</div>
              <div class="f-username">@{{ u.username }}</div>
            </div>
            <el-button
              class="unfollow-btn"
              size="small"
              round
              :loading="unfollowLoadingId === u.userId"
              @click.stop="onUnfollow(u)"
            >取消关注</el-button>
          </div>
        </div>
        <div class="empty-state" v-else>还没有关注任何用户</div>
      </div>

      <!-- 我的粉丝：关注了我的用户列表，点进去看 TA 的主页，并显示总数 -->
      <div class="panel-card" v-show="activeTab === 'followers'">
        <div class="section-head">
          <div class="section-title">我的粉丝</div>
          <div class="count-badge">共 {{ followerCount }} 人</div>
        </div>
        <div class="following-list" v-if="followers.length">
          <div class="following-item" v-for="u in followers" :key="u.userId" @click="router.push(`/user/${u.userId}`)">
            <el-avatar :size="48" :src="u.avatarUrl">{{ u.nickname?.charAt(0) }}</el-avatar>
            <div class="f-info">
              <div class="f-name">{{ u.nickname }}</div>
              <div class="f-username">@{{ u.username }}</div>
            </div>
            <el-icon class="f-arrow"><ArrowRight /></el-icon>
          </div>
        </div>
        <div class="empty-state" v-else>还没有粉丝关注你</div>
      </div>

      <!-- 我的收藏 / 点赞记录 / 浏览记录：三者共用同一套帖子卡片展示 -->
      <div class="panel-card" v-show="activeTab !== 'posts' && activeTab !== 'followings' && activeTab !== 'followers'">
        <div class="section-head">
          <div class="section-title">{{ tabTitle }}</div>
        </div>
        <div class="waterfall" v-if="recordPosts.length" v-loading="loadingRecords">
          <div class="post-card" v-for="p in recordPosts" :key="p.postId" @click="router.push(`/post/${p.postId}`)">
            <div class="card-cover" v-if="p.coverUrl">
              <img :src="p.coverUrl" loading="lazy" />
            </div>
            <div class="card-cover video-cover" v-else-if="p.mediaUrl">
              <el-icon size="28" color="#fff"><VideoPlay /></el-icon>
            </div>
            <div class="card-body">
              <div class="card-title">{{ p.title }}</div>
              <div class="card-footer">
                <div class="card-author">
                  <el-avatar :size="20" :src="p.avatarUrl">{{ p.nickname?.charAt(0) }}</el-avatar>
                  <span class="author-name">{{ p.nickname || p.username }}</span>
                </div>
                <div class="card-meta">
                  <el-icon><Star /></el-icon>{{ p.likeCount||0 }}
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="empty-state" v-else-if="!loadingRecords">
          {{ emptyHint }}
        </div>
        <div class="load-more" v-if="recordHasMore && recordPosts.length && !loadingRecords">
          <el-button round @click="loadMoreRecords">加载更多</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, Star, ChatDotSquare, Setting, VideoPlay, ArrowRight, Camera } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { updateProfile, getProfile, unfollowUser } from '@/api/user'
import { uploadAvatar } from '@/api/file'
import { getMyPosts } from '@/api/post'
import { getFavoritePosts, getViewHistory, getLikedPosts } from '@/api/interaction'
import { getMyFollowings, getMyFollowers } from '@/api/user'

const router = useRouter()
const userStore = useUserStore()
const editing = ref(false)
const loading = ref(false)
const loadingPosts = ref(false)
const myPosts = ref<any[]>([])
const profile = ref<any>(null)
const form = reactive({ nickname: '', phone: '', email: '' })
const statusFilter = ref<'all' | 'pass' | 'reject'>('all')

// 头像上传
const avatarInput = ref<HTMLInputElement | null>(null)
const avatarUploading = ref(false)

async function onAvatarChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  // 简单前端校验
  if (!/^image\/(png|jpe?g|gif|webp)$/.test(file.type)) {
    ElMessage.error('仅支持 png/jpg/gif/webp 格式')
    input.value = ''
    return
  }
  if (file.size > 5 * 1024 * 1024) {
    ElMessage.error('头像不能超过 5MB')
    input.value = ''
    return
  }
  avatarUploading.value = true
  try {
    const upRes: any = await uploadAvatar(file)
    const url = upRes.data
    // 上传成功后立即写入数据库
    await updateProfile({ avatarUrl: url })
    userStore.setUser({ ...userStore.userInfo!, avatarUrl: url })
    if (profile.value) profile.value = { ...profile.value, avatarUrl: url }
    ElMessage.success('头像更新成功')
  } catch {
    /* http 拦截器已提示 */
  } finally {
    avatarUploading.value = false
    input.value = ''
  }
}

const totalLikes = computed(() => myPosts.value.reduce((s, p) => s + (p.likeCount || 0), 0))

// 状态：0=审核通过 2=审核中 3=审核不通过
function statusText(s: number) {
  return s === 0 ? '审核通过' : s === 2 ? '审核中' : s === 3 ? '审核不通过' : '已删除'
}
function statusClass(s: number) {
  return s === 0 ? 'pass' : s === 2 ? 'pending' : s === 3 ? 'reject' : ''
}

const filteredPosts = computed(() => {
  if (statusFilter.value === 'pass') return myPosts.value.filter(p => p.status === 0)
  if (statusFilter.value === 'reject') return myPosts.value.filter(p => p.status === 3)
  return myPosts.value
})

function startEdit() {
  form.nickname = userStore.userInfo?.nickname || ''
  form.phone = profile.value?.phone || ''
  form.email = profile.value?.email || ''
  editing.value = true
}

async function handleUpdate() {
  loading.value = true
  try {
    await updateProfile({
      nickname: form.nickname,
      phone: form.phone,
      email: form.email,
    })
    userStore.setUser({ ...userStore.userInfo!, nickname: form.nickname })
    profile.value = { ...profile.value, phone: form.phone, email: form.email }
    ElMessage.success('保存成功')
    editing.value = false
  } finally {
    loading.value = false
  }
}

async function loadProfile() {
  try {
    const res: any = await getProfile()
    profile.value = res.data
  } catch { /* 忽略 */ }
}

async function loadMyPosts() {
  loadingPosts.value = true
  try {
    const res: any = await getMyPosts(1, 100)
    myPosts.value = res.data?.records || []
  } finally {
    loadingPosts.value = false
  }
}

// ===== 标签页：我的笔记 / 我的收藏 / 点赞记录 / 浏览记录 =====
const tabs = [
  { key: 'posts', label: '我的笔记' },
  { key: 'followings', label: '我的关注' },
  { key: 'followers', label: '我的粉丝' },
  { key: 'favorites', label: '我的收藏' },
  { key: 'likes', label: '点赞记录' },
  { key: 'views', label: '浏览记录' },
] as const
type TabKey = typeof tabs[number]['key']
const activeTab = ref<TabKey>('posts')

const tabTitle = computed(() => tabs.find(t => t.key === activeTab.value)?.label || '')
const emptyHint = computed(() => {
  if (activeTab.value === 'followings') return '还没有关注任何用户'
  if (activeTab.value === 'followers') return '还没有粉丝关注你'
  if (activeTab.value === 'favorites') return '还没有收藏任何笔记'
  if (activeTab.value === 'likes') return '还没有点赞过任何笔记'
  return '还没有浏览记录'
})

// 我的关注列表
const followings = ref<any[]>([])
const unfollowLoadingId = ref<number | null>(null)
async function loadFollowings() {
  try {
    const res: any = await getMyFollowings()
    followings.value = res.data || []
    loadedTab.value.add('followings')
  } catch { followings.value = [] }
}

// 取消关注（从关注列表移除）
async function onUnfollow(u: any) {
  try {
    await ElMessageBox.confirm(
      `确定取消关注「${u.nickname}」吗？取消后将无法在聊天中发送消息。`,
      '取消关注',
      { confirmButtonText: '确定取消关注', cancelButtonText: '再想想', type: 'warning' }
    )
  } catch {
    return
  }
  unfollowLoadingId.value = u.userId
  try {
    await unfollowUser(u.userId)
    followings.value = followings.value.filter(f => f.userId !== u.userId)
    ElMessage.success('已取消关注')
  } catch { /* 由拦截器提示 */ } finally {
    unfollowLoadingId.value = null
  }
}

// 我的粉丝列表 + 粉丝总数
const followers = ref<any[]>([])
const followerCount = ref(0)
async function loadFollowers() {
  try {
    const res: any = await getMyFollowers()
    followers.value = res.data || []
    followerCount.value = followers.value.length
    loadedTab.value.add('followers')
  } catch { followers.value = [] }
}

// 三个记录页共用一份分页数据
const recordPosts = ref<any[]>([])
const loadingRecords = ref(false)
const recordPageNum = ref(1)
const recordPageSize = 20
const recordHasMore = ref(false)
// 标记当前记录页是否已加载过，避免来回切换重复请求
const loadedTab = ref<Set<string>>(new Set())

function switchTab(key: TabKey) {
  activeTab.value = key
  if (key === 'posts') return
  if (key === 'followings') {
    if (!loadedTab.value.has('followings')) loadFollowings()
    return
  }
  if (key === 'followers') {
    if (!loadedTab.value.has('followers')) loadFollowers()
    return
  }
  if (!loadedTab.value.has(key)) {
    loadRecords(true)
  }
}

async function loadRecords(reset = true) {
  if (reset) {
    recordPageNum.value = 1
    recordPosts.value = []
  }
  loadingRecords.value = true
  try {
    const api = activeTab.value === 'favorites' ? getFavoritePosts
      : activeTab.value === 'likes' ? getLikedPosts
      : getViewHistory
    const res: any = await api(recordPageNum.value, recordPageSize)
    const records = res.data?.records || []
    recordPosts.value = reset ? records : [...recordPosts.value, ...records]
    recordHasMore.value = records.length === recordPageSize
    loadedTab.value.add(activeTab.value)
  } finally {
    loadingRecords.value = false
  }
}

async function loadMoreRecords() {
  recordPageNum.value++
  await loadRecords(false)
}

onMounted(() => {
  loadMyPosts()
  loadProfile()
})
</script>

<style scoped>
* { box-sizing: border-box; }
.profile-page { min-height: calc(100vh - 60px); background: #F6F6F6; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; }
.profile-wrap { max-width: 900px; margin: 0 auto; }
.profile-card { background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.06); margin-bottom: 20px; }
.profile-bg { height: 120px; background: linear-gradient(135deg, #FF2442 0%, #ff9fa8 100%); }
.profile-main { display: flex; align-items: flex-end; gap: 16px; padding: 0 24px 20px; flex-wrap: wrap; }
.profile-ava { margin-top: -40px; border: 4px solid #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.15); flex-shrink: 0; }
.avatar-wrap { position: relative; margin-top: -40px; flex-shrink: 0; width: 80px; height: 80px; border-radius: 50%; cursor: pointer; overflow: hidden; border: 4px solid #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }
.avatar-wrap :deep(.el-avatar) { margin-top: 0; border: none; box-shadow: none; }
.avatar-mask { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; color: #fff; font-size: 12px; background: rgba(0,0,0,0.45); opacity: 0; transition: opacity 0.18s; }
.avatar-wrap:hover .avatar-mask { opacity: 1; }
.avatar-wrap.uploading .avatar-mask { opacity: 1; }
.profile-info { flex: 1; padding-top: 8px; }
.profile-name { font-size: 22px; font-weight: 700; color: #1a1a1a; margin: 0 0 4px; }
.profile-username { font-size: 14px; color: #999; margin: 0 0 6px; }
.profile-contact { font-size: 13px; color: #666; margin: 2px 0; }
.profile-badge { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: #FF2442; background: rgba(255,36,66,0.08); padding: 2px 8px; border-radius: 10px; }
.edit-form { display: flex; align-items: center; gap: 10px; padding-top: 8px; flex-wrap: wrap; }
.edit-btn { margin-left: auto; }
.profile-stats { display: flex; gap: 40px; padding: 16px 24px; border-top: 1px solid #F5F5F5; }
.stat-item { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.stat-num { font-size: 20px; font-weight: 700; color: #1a1a1a; }
.stat-label { font-size: 12px; color: #999; }

/* 标签栏 */
.tab-bar { display: flex; gap: 8px; margin-bottom: 16px; background: #fff; border-radius: 12px; padding: 8px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }
.tab-btn { flex: 1; padding: 10px 0; border: none; background: transparent; color: #777; font-size: 14px; font-weight: 600; cursor: pointer; border-radius: 8px; transition: all 0.18s; }
.tab-btn:hover { color: #FF2442; }
.tab-btn.active { background: #FF2442; color: #fff; }

.panel-card { background: #fff; border-radius: 16px; padding: 20px 24px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; gap: 12px; flex-wrap: wrap; }
.section-title { font-size: 16px; font-weight: 700; color: #1a1a1a; }
.count-badge { font-size: 13px; color: #FF2442; background: rgba(255,36,66,0.08); padding: 4px 12px; border-radius: 12px; font-weight: 600; }
.status-filter { display: flex; gap: 6px; }
.status-filter button {
  padding: 4px 14px; border-radius: 14px; border: 1.5px solid #EBEBEB;
  background: #fff; color: #777; font-size: 12px; cursor: pointer; transition: all 0.18s;
}
.status-filter button:hover { border-color: #FF2442; color: #FF2442; }
.status-filter button.active { background: #FF2442; border-color: #FF2442; color: #fff; }
.waterfall { columns: 4; column-gap: 12px; }
@media (max-width: 900px) { .waterfall { columns: 3; } }
@media (max-width: 640px) { .waterfall { columns: 2; } }
.post-card { break-inside: avoid; display: inline-block; width: 100%; margin-bottom: 12px; background: #F8F8F8; border-radius: 10px; overflow: hidden; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; }
.post-card:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,0.1); }
.card-cover img { width: 100%; display: block; }
.video-cover { display: flex; align-items: center; justify-content: center; height: 120px; background: linear-gradient(135deg, #2a2a2a, #555); }
.card-body { padding: 8px 10px 10px; }
.card-title { font-size: 13px; font-weight: 600; color: #1a1a1a; margin-bottom: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-row { display: flex; align-items: center; justify-content: space-between; }
.card-meta { font-size: 12px; color: #999; display: flex; align-items: center; gap: 4px; }
.card-footer { display: flex; align-items: center; justify-content: space-between; }
.card-author { display: flex; align-items: center; gap: 6px; }
.author-name { font-size: 12px; color: #767676; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 90px; }
.status-tag { font-size: 11px; padding: 1px 8px; border-radius: 8px; font-weight: 600; }
.status-tag.pass { color: #52c41a; background: rgba(82,196,26,0.1); }
.status-tag.pending { color: #fa8c16; background: rgba(250,140,22,0.1); }
.status-tag.reject { color: #FF2442; background: rgba(255,36,66,0.1); }
.reject-reason { font-size: 11px; color: #FF2442; margin-top: 4px; }
.empty-state { text-align: center; color: #999; padding: 40px; font-size: 15px; }
.load-more { text-align: center; padding: 16px 0 4px; }

/* 我的关注列表 */
.following-list { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
@media (max-width: 640px) { .following-list { grid-template-columns: 1fr; } }
.following-item { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border: 1.5px solid #EFEFEF; border-radius: 12px; cursor: pointer; transition: all 0.18s; }
.following-item:hover { border-color: #FF2442; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
.f-info { flex: 1; min-width: 0; }
.f-name { font-size: 15px; font-weight: 600; color: #1a1a1a; }
.f-username { font-size: 12px; color: #999; margin-top: 2px; }
.f-arrow { color: #ccc; }

/* 取消关注按钮 */
.unfollow-btn {
  flex-shrink: 0;
  border: 1.5px solid #ddd !important;
  background: #fff !important;
  color: #999 !important;
  font-size: 12px !important;
  font-weight: 600;
  transition: all 0.18s;
}
.unfollow-btn:hover {
  border-color: #FF2442 !important;
  color: #FF2442 !important;
  background: rgba(255,36,66,0.05) !important;
}
</style>
