<template>
  <div class="user-page" v-loading="loading">
    <div class="user-wrap" v-if="user">
      <!-- 用户卡片 -->
      <div class="user-card">
        <div class="user-bg"></div>
        <div class="user-main">
          <el-avatar :size="80" :src="user.avatarUrl" class="user-ava">{{ user.nickname?.charAt(0) }}</el-avatar>
          <div class="user-info">
            <h2 class="user-name">
              {{ user.nickname }}
              <el-tag v-if="user.status === 1" size="small" type="warning" effect="plain" class="mute-tag">该用户被禁言</el-tag>
              <el-tag v-else-if="user.status === 2" size="small" type="danger" effect="plain" class="mute-tag">该用户被封禁</el-tag>
            </h2>
            <p class="user-username">@{{ user.username }}</p>
          </div>
          <!-- 关注按钮：不是自己时才显示 -->
          <el-button v-if="!isSelf" :type="stats.isFollowing ? '' : 'primary'" round
            :class="{ faved: stats.isFollowing }" :loading="followLoading" @click="toggleFollow"
            class="follow-btn">
            {{ stats.isFollowing ? '已关注' : '+ 关注' }}
          </el-button>
        </div>
        <!-- 统计 -->
        <div class="user-stats">
          <div class="stat-item"><span class="stat-num">{{ stats.postCount }}</span><span class="stat-label">笔记</span></div>
          <div class="stat-item"><span class="stat-num">{{ stats.likeCount }}</span><span class="stat-label">获赞</span></div>
          <div class="stat-item"><span class="stat-num">{{ stats.favoriteCount }}</span><span class="stat-label">被收藏</span></div>
          <div class="stat-item"><span class="stat-num">{{ stats.followerCount }}</span><span class="stat-label">被关注</span></div>
        </div>
      </div>

      <!-- TA 的笔记 -->
      <div class="panel-card">
        <div class="section-title">TA 的笔记</div>
        <div class="waterfall" v-if="posts.length" v-loading="loadingPosts">
          <div class="post-card" v-for="p in posts" :key="p.postId" @click="router.push(`/post/${p.postId}`)">
            <div class="card-cover" v-if="p.coverUrl"><img :src="p.coverUrl" loading="lazy" /></div>
            <div class="card-cover video-cover" v-else-if="p.mediaUrl">
              <el-icon size="28" color="#fff"><VideoPlay /></el-icon>
            </div>
            <div class="card-body">
              <div class="card-title">{{ p.title }}</div>
              <div class="card-footer">
                <div class="card-likes" :class="{ liked: p.isLiked }"><ThumbsUp /><span>{{ p.likeCount||0 }}</span></div>
                <div class="card-fav" :class="{ faved: p.isFavorited }" @click.stop="toggleFav(p)">
                  <el-icon><Star /></el-icon>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="empty-state" v-else-if="!loadingPosts">TA 还没有发布笔记</div>
        <div class="load-more" v-if="hasMore && posts.length && !loadingPosts">
          <el-button round @click="loadMore">加载更多</el-button>
        </div>
      </div>
    </div>
    <div class="back-btn-wrap">
      <el-button @click="router.back()" round><el-icon><ArrowLeft /></el-icon> 返回</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Star, ArrowLeft, VideoPlay } from '@element-plus/icons-vue'
import { getUserProfile, getUserStats, followUser, unfollowUser } from '@/api/user'
import { getPostList } from '@/api/post'
import { favoritePost, unfavoritePost } from '@/api/interaction'
import { useUserStore } from '@/store/user'
import ThumbsUp from '@/components/ThumbsUp.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const targetId = computed(() => Number(route.params.id))

const loading = ref(false)
const user = ref<any>(null)
const stats = ref<any>({ postCount: 0, likeCount: 0, favoriteCount: 0, followerCount: 0, followingCount: 0, isFollowing: false })
const followLoading = ref(false)

const posts = ref<any[]>([])
const pageNum = ref(1)
const pageSize = 20
const loadingPosts = ref(false)
const hasMore = ref(true)

const isSelf = computed(() => String(userStore.userInfo?.userId) === String(targetId.value))

async function loadUser() {
  loading.value = true
  try {
    const [p, s]: any = await Promise.all([getUserProfile(targetId.value), getUserStats(targetId.value)])
    user.value = p.data
    stats.value = s.data
  } finally {
    loading.value = false
  }
}

async function loadPosts(reset = true) {
  if (reset) { pageNum.value = 1; posts.value = []; hasMore.value = true }
  loadingPosts.value = true
  try {
    const res: any = await getPostList(pageNum.value, pageSize, undefined, undefined, targetId.value)
    const records = res.data?.records || []
    posts.value = reset ? records : [...posts.value, ...records]
    hasMore.value = records.length === pageSize
  } finally {
    loadingPosts.value = false
  }
}

function loadMore() { pageNum.value++; loadPosts(false) }

async function toggleFollow() {
  if (!userStore.isLoggedIn()) { router.push('/login'); return }
  followLoading.value = true
  try {
    if (stats.value.isFollowing) {
      await unfollowUser(targetId.value)
      stats.value.isFollowing = false
      stats.value.followerCount = Math.max(0, stats.value.followerCount - 1)
      ElMessage.success('已取消关注')
    } else {
      await followUser(targetId.value)
      stats.value.isFollowing = true
      stats.value.followerCount = (stats.value.followerCount || 0) + 1
      ElMessage.success('关注成功')
    }
  } finally {
    followLoading.value = false
  }
}

async function toggleFav(p: any) {
  if (!userStore.isLoggedIn()) { router.push('/login'); return }
  if (p.isFavorited) { await unfavoritePost(p.postId); p.isFavorited = false }
  else { await favoritePost(p.postId); p.isFavorited = true }
}

onMounted(() => { loadUser(); loadPosts(true) })
watch(targetId, () => { loadUser(); loadPosts(true) })
</script>

<style scoped>
* { box-sizing: border-box; }
.user-page { min-height: calc(100vh - 60px); background: #F6F6F6; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; }
.user-wrap { max-width: 900px; margin: 0 auto; }
.user-card { background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.06); margin-bottom: 20px; }
.user-bg { height: 120px; background: linear-gradient(135deg, #FF2442 0%, #ff9fa8 100%); }
.user-main { display: flex; align-items: flex-end; gap: 16px; padding: 0 24px 20px; flex-wrap: wrap; }
.user-ava { margin-top: -40px; border: 4px solid #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.15); flex-shrink: 0; }
.user-info { flex: 1; padding-top: 8px; }
.user-name { font-size: 22px; font-weight: 700; color: #1a1a1a; margin: 0 0 4px; display: flex; align-items: center; gap: 8px; }
.mute-tag { font-size: 13px; }
.user-username { font-size: 14px; color: #999; margin: 0; }
.follow-btn { margin-left: auto; }
.follow-btn:not(.faved) { background: #FF2442; border-color: #FF2442; }
.follow-btn.faved { color: #999; border-color: #ddd; }
.user-stats { display: flex; gap: 40px; padding: 16px 24px; border-top: 1px solid #F5F5F5; }
.stat-item { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.stat-num { font-size: 20px; font-weight: 700; color: #1a1a1a; }
.stat-label { font-size: 12px; color: #999; }
.panel-card { background: #fff; border-radius: 16px; padding: 20px 24px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }
.section-title { font-size: 16px; font-weight: 700; color: #1a1a1a; margin-bottom: 16px; }
.waterfall { columns: 4; column-gap: 12px; }
@media (max-width: 900px) { .waterfall { columns: 3; } }
@media (max-width: 640px) { .waterfall { columns: 2; } }
.post-card { break-inside: avoid; display: inline-block; width: 100%; margin-bottom: 12px; background: #F8F8F8; border-radius: 10px; overflow: hidden; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; }
.post-card:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,0.1); }
.card-cover img { width: 100%; display: block; }
.video-cover { display: flex; align-items: center; justify-content: center; height: 120px; background: linear-gradient(135deg, #2a2a2a, #555); }
.card-body { padding: 8px 10px 10px; }
.card-title { font-size: 13px; font-weight: 600; color: #1a1a1a; margin-bottom: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-footer { display: flex; align-items: center; justify-content: space-between; }
.card-likes { display: flex; align-items: center; gap: 4px; font-size: 12px; color: #999; }
.card-likes.liked { color: #FF2442; }
.card-fav { display: flex; align-items: center; font-size: 14px; color: #bbb; cursor: pointer; transition: color 0.2s; }
.card-fav:hover { color: #FFA500; }
.card-fav.faved { color: #FFA500; }
.empty-state { text-align: center; color: #999; padding: 40px; font-size: 15px; }
.load-more { text-align: center; padding: 16px 0 4px; }
.back-btn-wrap { max-width: 900px; margin: 16px auto; }
</style>
