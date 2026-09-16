<template>
  <div class="home-page">
    <!-- 话题选项卡片栏 -->
    <div class="topic-bar-wrap">
      <!-- 查看某用户的帖子时显示归属横幅 -->
      <div class="user-banner" v-if="filterUserId">
        正在查看 @{{ filterUname || 'TA' }} 的笔记
        <el-button text size="small" @click="clearUserFilter">返回推荐</el-button>
      </div>
      <div class="topic-bar">
        <button
          v-for="t in topics" :key="t.value"
          class="topic-chip"
          :class="{ active: activeTopic === t.value }"
          @click="selectTopic(t.value)"
        >
          {{ t.label }}
        </button>
      </div>
    </div>

    <!-- 瀑布流卡片区 -->
    <div class="waterfall-wrap" v-loading="loading">
      <div class="waterfall" v-if="posts.length">
        <div
          class="post-card"
          v-for="post in posts"
          :key="post.postId"
          @click="router.push(`/post/${post.postId}`)"
        >
          <!-- 封面图片 -->
          <div class="card-cover" v-if="post.coverUrl">
            <img :src="post.coverUrl" alt="cover" loading="lazy" />
            <div class="play-badge" v-if="post.postType === 3">
              <svg viewBox="0 0 48 48" width="34" height="34" xmlns="http://www.w3.org/2000/svg"><circle cx="24" cy="24" r="22" fill="rgba(0,0,0,0.45)"/><path d="M19 16l14 8-14 8z" fill="#fff"/></svg>
            </div>
            <div class="cover-tag" v-if="post.topicTag"># {{ post.topicTag }}</div>
          </div>
          <div class="card-no-cover" v-else>
            <div class="play-badge no-cover-badge" v-if="post.postType === 3">
              <svg viewBox="0 0 48 48" width="40" height="40" xmlns="http://www.w3.org/2000/svg"><circle cx="24" cy="24" r="22" fill="rgba(0,0,0,0.35)"/><path d="M19 16l14 8-14 8z" fill="#fff"/></svg>
            </div>
            <div class="cover-tag" v-if="post.topicTag"># {{ post.topicTag }}</div>
          </div>
          <!-- 内容 -->
          <div class="card-body">
            <h3 class="card-title">{{ post.title }}</h3>
            <p class="card-text" v-if="!post.coverUrl">{{ post.content?.slice(0, 100) }}</p>
            <div class="card-time">{{ formatTime(post.createdTime) }}</div>
          </div>
          <!-- 作者行 -->
            <div class="card-footer">
            <div class="card-author">
              <el-avatar :size="22" :src="post.avatarUrl" class="author-avatar">
                {{ post.nickname?.charAt(0) }}
              </el-avatar>
              <span class="author-name">{{ post.nickname || post.username }}</span>
            </div>
            <div class="card-actions">
              <div class="card-likes" :class="{ liked: post.isLiked }">
                <ThumbsUp />
                <span>{{ post.likeCount || 0 }}</span>
              </div>
              <div class="card-fav" :class="{ faved: post.isFavorited }" @click.stop="toggleFav(post)">
                <el-icon><Star /></el-icon>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div class="empty-state" v-else-if="!loading">
        <div class="empty-icon">📝</div>
        <p>暂无内容，成为第一个发布吧！</p>
        <el-button type="primary" round @click="router.push('/publish')"
          style="background:#FF2442;border-color:#FF2442">立即发布</el-button>
      </div>
    </div>

    <!-- 加载更多 -->
    <div class="load-more" v-if="hasMore && !loading">
      <el-button round @click="loadMore">加载更多</el-button>
    </div>
    <div class="no-more" v-else-if="!hasMore && posts.length">— 已经到底了 —</div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Star } from '@element-plus/icons-vue'
import { getPostList } from '@/api/post'
import { favoritePost, unfavoritePost } from '@/api/interaction'
import { useUserStore } from '@/store/user'
import ThumbsUp from '@/components/ThumbsUp.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

// 相对时间格式化（与详情页一致：刚刚 / N分钟前 / N小时前 / 日期）
function formatTime(t: string) {
  if (!t) return ''
  const d = new Date(t)
  if (isNaN(d.getTime())) return ''
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  return d.toLocaleDateString('zh-CN')
}

// 收藏 / 取消收藏（首页卡片上一键收藏到“未分组”，详情页可选收藏夹）
async function toggleFav(post: any) {
  if (!userStore.isLoggedIn()) { router.push('/login'); return }
  if (post.isFavorited) {
    await unfavoritePost(post.postId)
    post.isFavorited = false
  } else {
    await favoritePost(post.postId)
    post.isFavorited = true
  }
}

// 分类栏：点“推荐”时 activeTopic='' → 不传 topicTag → 后端返回全部帖子（含未来新发的）。
// 点其他分类时按 topicTag 模糊过滤。
const topics = [
  { label: '推荐', value: '' },
  { label: '科技', value: '科技' },
  { label: '生活', value: '生活' },
  { label: '美食', value: '美食' },
  { label: '旅行', value: '旅行' },
  { label: '娱乐', value: '娱乐' },
  { label: '时尚', value: '时尚' },
  { label: '运动', value: '运动' },
  { label: '财经', value: '财经' },
  { label: '教育', value: '教育' },
]

const posts = ref<any[]>([])
const pageNum = ref(1)
const pageSize = 20
const loading = ref(false)
const hasMore = ref(true)
const activeTopic = ref('')

// 按用户过滤（从搜索页点用户跳来时带 userId / uname）
const filterUserId = ref<number | undefined>(undefined)
const filterUname = ref('')

async function loadPosts(reset = true) {
  if (reset) {
    pageNum.value = 1
    posts.value = []
    hasMore.value = true
  }
  loading.value = true
  try {
    // 推荐（activeTopic=''）时传 undefined，后端不加 topicTag 过滤，返回全部帖子
    const res: any = await getPostList(pageNum.value, pageSize, activeTopic.value || undefined, undefined, filterUserId.value)
    const records = res.data?.records || []
    posts.value = reset ? records : [...posts.value, ...records]
    hasMore.value = records.length === pageSize
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  pageNum.value++
  await loadPosts(false)
}

function selectTopic(val: string) {
  activeTopic.value = val
  loadPosts()
}

function clearUserFilter() {
  filterUserId.value = undefined
  filterUname.value = ''
  router.replace({ query: {} })
  loadPosts(true)
}

watch(() => route.query.keyword, (kw) => {
  if (kw !== undefined) loadPosts()
})

// 从搜索页点用户跳来：/?userId=X&uname=Y
watch(() => route.query.userId, (uid) => {
  filterUserId.value = uid ? Number(uid) : undefined
  filterUname.value = (route.query.uname as string) || ''
  loadPosts(true)
}, { immediate: true })

// 发布成功后 MainLayout 跳到 /?refresh=时间戳，这里监听并刷新帖子列表
watch(() => route.query.refresh, () => {
  loadPosts(true)
})
</script>

<style scoped>
* { box-sizing: border-box; }
.home-page { padding-bottom: 40px; font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; }

/* 话题栏（参考小红书：居中纯文字 Tab，选中加粗 + 红色下划线） */
.topic-bar-wrap {
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
  position: sticky;
  top: 74px;
  z-index: 100;
}
.topic-bar {
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 24px;
  display: flex;
  gap: 30px;
  overflow-x: auto;
  scrollbar-width: none;
  height: 56px;
  align-items: center;
  justify-content: center;
}
.user-banner {
  max-width: 1440px;
  margin: 0 auto;
  padding: 10px 24px;
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
  background: #fff5f6;
  color: #FF2442;
  font-size: 14px;
  font-weight: 600;
  border-bottom: 1px solid #FFE0E5;
}
.topic-bar::-webkit-scrollbar { display: none; }
.topic-chip {
  flex-shrink: 0;
  position: relative;
  padding: 8px 2px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 15px;
  cursor: pointer;
  transition: color 0.18s, font-size 0.18s;
  font-weight: 500;
  white-space: nowrap;
  line-height: 1.4;
}
.topic-chip:hover { color: var(--text-primary); }
.topic-chip.active {
  color: var(--text-primary);
  font-weight: 700;
  font-size: 17px;
}
.topic-chip.active::after {
  content: '';
  position: absolute;
  left: 50%;
  bottom: 0;
  transform: translateX(-50%);
  width: 22px;
  height: 3px;
  border-radius: 2px;
  background: var(--brand);
}

/* 瀑布流 */
.waterfall-wrap {
  max-width: 1280px;
  margin: 0 auto;
  padding: 20px 24px 0;
}
/* 瀑布流 */
.waterfall-wrap {
  max-width: 1280px;
  margin: 0 auto;
  padding: 20px 24px 0;
}
.waterfall {
  columns: 5;
  column-gap: 20px;
}
@media (max-width: 1100px) { .waterfall { columns: 4; } }
@media (max-width: 768px) { .waterfall { columns: 3; } }
@media (max-width: 480px) { .waterfall { columns: 2; } }

/* 卡片 */
.post-card {
  break-inside: avoid;
  margin-bottom: 20px;
  display: inline-block;
  width: 100%;
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.post-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
}
.card-cover {
  position: relative;
  overflow: hidden;
  background: #F5F5F5;
}
.card-cover img {
  width: 100%;
  display: block;
  transition: transform 0.3s;
}
.post-card:hover .card-cover img { transform: scale(1.04); }
/* 视频帖播放图标 */
.play-badge {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: none;
  filter: drop-shadow(0 2px 6px rgba(0,0,0,0.4));
}
.no-cover-badge { position: static; transform: none; margin: 14px auto; display: block; }
.card-no-cover {
  background: linear-gradient(135deg, #fff5f6, #fff);
  min-height: 20px;
  position: relative;
}
.cover-tag {
  position: absolute;
  top: 8px;
  left: 8px;
  background: rgba(0,0,0,0.45);
  color: #fff;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  backdrop-filter: blur(4px);
}
.card-no-cover .cover-tag {
  position: relative;
  top: 0; left: 0;
  display: inline-block;
  margin: 10px 10px 0;
  background: rgba(255,36,66,0.1);
  color: #FF2442;
}
.card-body { padding: 10px 12px 6px; }
.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0 0 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.5;
}
.card-text {
  font-size: 13px;
  color: #767676;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.5;
}
.card-time {
  margin-top: 6px;
  font-size: 12px;
  color: #9b9b9b;
}
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px 10px;
}
.card-author { display: flex; align-items: center; gap: 6px; }
.author-avatar { flex-shrink: 0; }
.author-name { font-size: 12px; color: #767676; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 90px; }
.card-likes { display: flex; align-items: center; gap: 4px; font-size: 12px; color: #999; }
.card-likes.liked { color: #FF2442; }
.card-actions { display: flex; align-items: center; gap: 10px; }
.card-fav { display: flex; align-items: center; font-size: 14px; color: #bbb; cursor: pointer; transition: color 0.2s, transform 0.15s; }
.card-fav:hover { color: #FFA500; }
.card-fav.faved { color: #FFA500; }
.card-fav.faved:active { transform: scale(0.85); }

/* 空状态 */
.empty-state { text-align: center; padding: 80px 20px; color: #999; }
.empty-icon { font-size: 60px; margin-bottom: 16px; }
.empty-state p { font-size: 16px; margin: 0 0 20px; }

/* 加载更多 */
.load-more { text-align: center; padding: 20px; }
.no-more { text-align: center; color: #ccc; font-size: 13px; padding: 20px; }
</style>
