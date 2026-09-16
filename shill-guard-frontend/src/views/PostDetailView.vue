<template>
  <div class="detail-page">
    <div class="detail-wrap" :class="{ 'with-comments': showComments }" v-loading="loading">
      <div class="detail-card" v-if="post">
        <!-- 1) 图片/视频区 -->
        <div class="media-panel">
          <video v-if="post.mediaUrl" :src="post.mediaUrl" :poster="post.coverUrl || undefined"
                 controls preload="metadata" playsinline class="main-video"></video>
          <img v-else-if="post.coverUrl" :src="post.coverUrl" class="main-img" />
          <div v-else class="no-img">
            <el-icon size="64" color="#ddd"><Document /></el-icon>
          </div>
          <div class="tag-row" v-if="post.topicTag">
            <span class="topic-tag"># {{ post.topicTag }}</span>
          </div>
        </div>

        <!-- 2) 文案区 -->
        <div class="content-panel">
          <!-- 作者信息 -->
          <div class="author-bar">
            <el-avatar :size="44" :src="post.avatarUrl" class="author-ava">{{ post.nickname?.charAt(0) }}</el-avatar>
            <div class="author-info">
              <div class="author-name">{{ post.nickname || post.username }}</div>
              <div class="post-time">{{ formatTime(post.createdTime) }}</div>
            </div>
            <!-- 关注作者按钮：不是自己时显示 -->
            <el-button v-if="!isAuthorSelf" size="small" round
              :type="authorFollowed ? '' : 'primary'" :class="{ 'followed-btn': authorFollowed }"
              :loading="followLoading" @click="toggleFollowAuthor" class="author-follow-btn">
              {{ authorFollowed ? '已关注' : '+ 关注' }}
            </el-button>
            <el-button v-if="canDelete" text type="danger" size="small" @click="handleDelete" style="margin-left:auto">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>

          <!-- 标题正文 -->
          <h1 class="post-title">{{ post.title }}</h1>
          <div class="post-content">{{ post.content }}</div>

          <!-- 互动栏：点赞 + 收藏 + 评论（点击评论图标弹出评论面板） -->
          <div class="action-bar">
            <button class="like-btn" :class="{ liked: post.isLiked }" @click="handleLike">
              <ThumbsUp />
              <span>{{ post.likeCount || 0 }}</span>
            </button>
            <button class="fav-btn" :class="{ faved: post.isFavorited }" @click="handleFav">
              <el-icon><Star /></el-icon>
              <span>收藏</span>
            </button>
            <button class="stat-btn" :class="{ active: showComments }" @click="toggleComments">
              <el-icon><ChatDotSquare /></el-icon>
              <span>{{ post.commentCount || 0 }}</span>
            </button>
            <button v-if="userStore.isLoggedIn() && !isAuthorSelf" class="report-btn" @click="openReportPost">
              <el-icon><WarnTriangleFilled /></el-icon>
              <span>举报</span>
            </button>
          </div>
        </div>

        <!-- 3) 评论面板：点击评论图标后才显示，整体左移让“图片+文案+评论”三者居中 -->
        <transition name="slide-panel">
          <div class="comment-panel" v-if="showComments">
            <!-- 顶部标题（固定） -->
            <div class="comment-header">
              <span>{{ post.commentCount || 0 }} 条评论</span>
              <el-button text size="small" @click="showComments = false" class="close-btn">
                <el-icon><Close /></el-icon>
              </el-button>
            </div>

            <!-- 评论列表：滚轮往下滑加载更多，一页 10 条 -->
            <div class="comment-list" ref="commentListRef" @scroll="onListScroll">
              <div class="comment-item" v-for="c in comments" :key="c.commentId">
                <el-avatar :size="36" :src="c.avatarUrl" class="c-ava">{{ (c.nickname || c.username || '?').charAt(0) }}</el-avatar>
                <div class="c-body">
                  <div class="c-header">
                    <span class="c-name">{{ c.nickname || c.username }}</span>
                    <span class="c-time">{{ formatTime(c.createdTime) }}</span>
                    <el-button v-if="c.userId === userStore.userInfo?.userId" text type="danger" size="small"
                      @click="handleDeleteComment(c.commentId)" style="margin-left:auto;padding:0 4px">
                      <el-icon><Delete /></el-icon>
                    </el-button>
                  </div>
                  <div class="c-text" @click="openReply(c)">{{ c.content }}</div>
                  <div class="c-actions">
                    <button class="c-like-btn" :class="{ liked: c.isLiked }" @click="toggleLikeComment(c)">
                      <ThumbsUp /><span>{{ c.likeCount || 0 }}</span>
                    </button>
                    <button class="c-reply-btn" @click="openReply(c)">回复</button>
                    <button v-if="userStore.isLoggedIn() && c.userId !== userStore.userInfo?.userId"
                      class="c-reply-btn" @click="openReportComment(c)">举报</button>
                    <button v-if="c.replyCount > 0" class="c-toggle-replies" @click="toggleReplies(c)">
                      {{ c.repliesOpen ? '收起回复' : `展开 ${c.replyCount} 条回复` }}
                    </button>
                  </div>

                  <!-- 子回复列表 -->
                  <div class="reply-list" v-if="c.repliesOpen && c.replies.length">
                    <div class="reply-item" v-for="r in c.replies" :key="r.commentId">
                      <el-avatar :size="28" :src="r.avatarUrl" class="r-ava">{{ (r.nickname || r.username || '?').charAt(0) }}</el-avatar>
                      <div class="r-body">
                        <div class="r-line">
                          <span class="r-name">{{ r.nickname || r.username }}</span>
                          <span class="r-text">{{ r.content }}</span>
                        </div>
                        <div class="r-meta">
                          <span class="r-time">{{ formatTime(r.createdTime) }}</span>
                          <button class="c-like-btn sm" :class="{ liked: r.isLiked }" @click="toggleLikeComment(r)">
                            <ThumbsUp /><span>{{ r.likeCount || 0 }}</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- 内联回复输入框：点击评论/回复按钮弹出，提交即子评论 -->
                  <div class="reply-input" v-if="c.replyOpen && userStore.isLoggedIn()">
                    <el-input v-model="replyText" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }"
                      :placeholder="`回复 @${c.nickname || c.username}`" class="reply-text-input" />
                    <div class="reply-action-row">
                      <el-button link size="small" :loading="replyAiWriting" :disabled="!replyText.trim()"
                        @click="handleReplyAiWrite" class="ai-inline-btn">
                        <el-icon v-if="!replyAiWriting"><MagicStick /></el-icon>
                        {{ replyAiWriting ? '续写中' : 'AI续写' }}
                      </el-button>
                      <el-button type="primary" size="small" :disabled="!replyText.trim()" @click="submitReply(c)">发送</el-button>
                    </div>
                  </div>
                  <div class="reply-input login-hint sm" v-else-if="c.replyOpen && !userStore.isLoggedIn()">
                    <router-link to="/login">登录</router-link> 后回复
                  </div>
                </div>
              </div>

              <div class="list-tip" v-if="loadingComments">加载中...</div>
              <div class="list-tip" v-else-if="!hasMore && comments.length">— 已经到底了 —</div>
              <div class="no-comment" v-if="!comments.length && !loadingComments">
                暂无评论，来说第一句吧 💬
              </div>
            </div>

            <!-- 底部输入框：固定不动，写死在评论面板底部 -->
            <div class="comment-input-fixed" v-if="userStore.isLoggedIn()">
              <div class="comment-input-row">
                <el-avatar :size="32" :src="userStore.userInfo?.avatarUrl" class="input-ava">
                  {{ userStore.userInfo?.nickname?.charAt(0) }}
                </el-avatar>
                <el-input v-model="commentText" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }"
                  placeholder="说点什么..." class="comment-input" />
              </div>
              <div class="comment-action-row">
                <el-button link size="small" :loading="commentAiWriting" :disabled="!commentText.trim()"
                  @click="handleCommentAiWrite" class="ai-inline-btn">
                  <el-icon v-if="!commentAiWriting"><MagicStick /></el-icon>
                  {{ commentAiWriting ? '续写中' : 'AI续写' }}
                </el-button>
                <el-button type="primary" round size="small" :disabled="!commentText.trim()" :loading="submitting"
                  @click="submitComment" class="publish-btn">发布</el-button>
              </div>
            </div>
            <div class="login-hint" v-else>
              <router-link to="/login">登录</router-link> 后参与评论
            </div>
          </div>
        </transition>
      </div>
      <!-- end detail-card -->
    </div>
    <!-- end detail-wrap：wrap 只包住卡片，宽度过渡只影响卡片居中 -->

    <div class="back-btn-wrap">
      <el-button @click="router.back()" round><el-icon><ArrowLeft /></el-icon> 返回</el-button>
    </div>

    <!-- 收藏夹选择弹窗：选择已有夹子或新建一个 -->
    <el-dialog v-model="favDialogVisible" title="收藏到收藏夹" width="420px" align-center>
      <div class="fav-dialog-body">
        <div class="fav-list">
          <div class="fav-item" :class="{ selected: selectedFolderId === null }" @click="selectedFolderId = null">
            <el-icon><Star /></el-icon>
            <span class="fav-name">未分组</span>
          </div>
          <div class="fav-item" v-for="f in folders" :key="f.folderId"
            :class="{ selected: selectedFolderId === f.folderId }" @click="selectedFolderId = f.folderId">
            <el-icon><FolderOpened /></el-icon>
            <span class="fav-name">{{ f.folderName }}</span>
            <span class="fav-count">{{ f.postCount }} 篇</span>
          </div>
        </div>
        <div class="fav-new">
          <el-input v-model="newFolderName" placeholder="新建收藏夹（可选）" size="default" maxlength="20" />
        </div>
      </div>
      <template #footer>
        <el-button @click="favDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="favSubmitting" @click="confirmFav"
          style="background:#FF2442;border-color:#FF2442">确定收藏</el-button>
      </template>
    </el-dialog>

    <!-- 举报弹窗：选择举报分类 + 填写理由 -->
    <el-dialog v-model="reportDialogVisible" title="举报" width="440px" align-center>
      <div class="report-dialog-body">
        <div class="report-target">
          举报对象：<span>{{ reportTargetLabel }}</span>
        </div>
        <div class="report-field">
          <div class="report-label">举报分类</div>
          <el-select v-model="reportCategory" placeholder="请选择举报分类" style="width:100%">
            <el-option label="广告/水军" :value="0" />
            <el-option label="违法信息" :value="1" />
            <el-option label="侮辱谩骂" :value="2" />
            <el-option label="色情低俗" :value="3" />
            <el-option label="其他" :value="4" />
          </el-select>
        </div>
        <div class="report-field">
          <div class="report-label">举报说明（可选）</div>
          <el-input v-model="reportReason" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }"
            placeholder="补充说明该内容违规的具体情况" maxlength="500" show-word-limit />
        </div>
      </div>
      <template #footer>
        <el-button @click="reportDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="reportSubmitting" @click="confirmReport"
          style="background:#FF2442;border-color:#FF2442">提交举报</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ChatDotSquare, Delete, ArrowLeft, Document, Close, Star, FolderOpened, MagicStick, WarnTriangleFilled } from '@element-plus/icons-vue'
import { getPostDetail, likePost, unlikePost, getComments, addComment, deleteComment, deletePost, likeComment, unlikeComment, getReplies } from '@/api/post'
import { listFolders, createFolder, favoritePost, unfavoritePost } from '@/api/interaction'
import { followUser, unfollowUser, getUserStats } from '@/api/user'
import { submitReport } from '@/api/report'
import { useUserStore } from '@/store/user'
import ThumbsUp from '@/components/ThumbsUp.vue'
import { streamWrite } from '@/api/writer'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const postId = Number(route.params.id)

const post = ref<any>(null)
const comments = ref<any[]>([])
const loading = ref(false)
const loadingComments = ref(false)
const submitting = ref(false)
const commentText = ref('')
const commentAiWriting = ref(false)
const replyAiWriting = ref(false)

// 评论面板开关 + 分页（一页 10 条，滚轮下滑加载更多）
const showComments = ref(true)
const pageNum = ref(1)
const pageSize = 10
const hasMore = ref(true)
const commentListRef = ref<HTMLElement | null>(null)

// 回复相关：一次只展开一条评论的内联回复框
const activeReplyId = ref<number | null>(null)
const replyText = ref('')

// 给评论对象补上交互用的本地字段
function normComment(c: any) {
  return {
    ...c,
    isLiked: !!c.isLiked,
    replies: [] as any[],
    repliesLoaded: false,
    repliesOpen: false,
    replyOpen: false,
  }
}

const canDelete = computed(() =>
  userStore.userInfo?.userId === post.value?.userId || userStore.isAdmin()
)
// 是否是作者本人（本人不显示关注按钮）
const isAuthorSelf = computed(() => String(userStore.userInfo?.userId) === String(post.value?.userId))
// 是否已关注作者
const authorFollowed = ref(false)
const followLoading = ref(false)

function formatTime(t: string) {
  if (!t) return ''
  const d = new Date(t)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  return d.toLocaleDateString('zh-CN')
}

async function loadPost() {
  loading.value = true
  try {
    const res: any = await getPostDetail(postId)
    post.value = res.data
    // 加载作者的关注状态（不是自己且已登录时）
    if (post.value && !isAuthorSelf.value && userStore.isLoggedIn()) {
      try {
        const s: any = await getUserStats(post.value.userId)
        authorFollowed.value = !!s.data?.isFollowing
      } catch { authorFollowed.value = false }
    }
  } finally {
    loading.value = false
  }
}

// 关注 / 取消关注作者
async function toggleFollowAuthor() {
  if (!userStore.isLoggedIn()) { router.push('/login'); return }
  if (!post.value) return
  followLoading.value = true
  try {
    if (authorFollowed.value) {
      await unfollowUser(post.value.userId)
      authorFollowed.value = false
      ElMessage.success('已取消关注')
    } else {
      await followUser(post.value.userId)
      authorFollowed.value = true
      ElMessage.success('关注成功')
    }
  } finally {
    followLoading.value = false
  }
}

// 加载评论：reset=true 重新从第 1 页加载；false 追加下一页
async function loadComments(reset = true) {
  if (reset) {
    pageNum.value = 1
    hasMore.value = true
    comments.value = []
  }
  if (!hasMore.value) return
  loadingComments.value = true
  try {
    const res: any = await getComments(postId, pageNum.value, pageSize)
    const records = (res.data?.records || []).map(normComment)
    comments.value = reset ? records : [...comments.value, ...records]
    // 不足一页说明没有更多了
    hasMore.value = records.length === pageSize
    if (!reset) {
      // 追加后保持滚动位置不跳动：滚到上一批末尾附近
      await nextTick()
      const el = commentListRef.value
      if (el) el.scrollTop = el.scrollTop // no-op，仅保留位置
    }
  } finally {
    loadingComments.value = false
  }
}

// 滚轮下滑到底部自动加载下一页
function onListScroll(e: Event) {
  const el = e.target as HTMLElement
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 60) {
    if (hasMore.value && !loadingComments.value) {
      pageNum.value++
      loadComments(false)
    }
  }
}

// 点击评论图标：展开/收起评论面板，首次展开时加载评论
function toggleComments() {
  showComments.value = !showComments.value
  if (showComments.value && comments.value.length === 0) {
    loadComments(true)
  }
}

async function handleLike() {
  if (!userStore.isLoggedIn()) { router.push('/login'); return }
  // 已点赞 → 取消点赞；未点赞 → 点赞。点赞后图标变红（.liked 类）
  if (post.value.isLiked) {
    await unlikePost(postId)
    post.value.isLiked = false
    post.value.likeCount = Math.max(0, (post.value.likeCount || 1) - 1)
  } else {
    await likePost(postId)
    post.value.isLiked = true
    post.value.likeCount = (post.value.likeCount || 0) + 1
  }
}

// ===== 收藏 =====
const favDialogVisible = ref(false)
const folders = ref<any[]>([])
const selectedFolderId = ref<number | null>(null)
const newFolderName = ref('')
const favSubmitting = ref(false)

async function handleFav() {
  if (!userStore.isLoggedIn()) { router.push('/login'); return }
  // 已收藏 → 直接取消
  if (post.value.isFavorited) {
    await unfavoritePost(postId)
    post.value.isFavorited = false
    ElMessage.success('已取消收藏')
    return
  }
  // 未收藏 → 打开收藏夹选择弹窗
  selectedFolderId.value = null
  newFolderName.value = ''
  try {
    const res: any = await listFolders()
    folders.value = res.data || []
  } catch { folders.value = [] }
  favDialogVisible.value = true
}

async function confirmFav() {
  favSubmitting.value = true
  try {
    let folderId = selectedFolderId.value
    // 若填了新收藏夹名称，先创建再收藏到新夹
    if (newFolderName.value.trim()) {
      const res: any = await createFolder(newFolderName.value.trim())
      folderId = res.data.folderId
    }
    await favoritePost(postId, folderId === null ? undefined : folderId)
    post.value.isFavorited = true
    favDialogVisible.value = false
    ElMessage.success('收藏成功')
  } finally {
    favSubmitting.value = false
  }
}

// ===== 举报 =====
const reportDialogVisible = ref(false)
const reportCategory = ref(0)
const reportReason = ref('')
const reportSubmitting = ref(false)
// 举报目标：'post' | 'comment'；记录被举报的评论ID与评论作者ID
const reportTarget = ref<'post' | 'comment'>('post')
const reportTargetCommentId = ref<number | null>(null)
const reportTargetUserId = ref<number | null>(null)
const reportTargetLabel = ref('帖子')

function openReportPost() {
  if (!userStore.isLoggedIn()) { router.push('/login'); return }
  reportTarget.value = 'post'
  reportTargetCommentId.value = null
  reportTargetUserId.value = post.value?.userId ?? null
  reportTargetLabel.value = '帖子'
  reportCategory.value = 0
  reportReason.value = ''
  reportDialogVisible.value = true
}

function openReportComment(c: any) {
  if (!userStore.isLoggedIn()) { router.push('/login'); return }
  reportTarget.value = 'comment'
  reportTargetCommentId.value = c.commentId
  reportTargetUserId.value = c.userId ?? null
  reportTargetLabel.value = '评论'
  reportCategory.value = 0
  reportReason.value = ''
  reportDialogVisible.value = true
}

async function confirmReport() {
  reportSubmitting.value = true
  try {
    const payload: any = {
      reportCategory: reportCategory.value,
      reportReason: reportReason.value || undefined,
    }
    if (reportTarget.value === 'post') {
      payload.reportedPostId = postId
      payload.reportedUserId = post.value?.userId
    } else {
      payload.reportedCommentId = reportTargetCommentId.value
      // 评论举报时把评论作者ID一起带上，避免后端 reported_user_id 列无默认值导致插入失败
      payload.reportedUserId = reportTargetUserId.value
    }
    await submitReport(payload)
    reportDialogVisible.value = false
    ElMessage.success('举报已提交，平台将进行审核')
  } finally {
    reportSubmitting.value = false
  }
}

async function submitComment() {
  if (!commentText.value.trim()) return
  submitting.value = true
  try {
    const res: any = await addComment({ postId, content: commentText.value })
    // 后端返回新评论 id，本地直接插入到列表顶部（即时反馈，不用整页刷新）
    const newComment = normComment({
      commentId: res.data,
      userId: userStore.userInfo?.userId,
      username: userStore.userInfo?.username,
      nickname: userStore.userInfo?.nickname,
      avatarUrl: userStore.userInfo?.avatarUrl,
      content: commentText.value,
      likeCount: 0,
      isLiked: false,
      createdTime: new Date().toISOString()
    })
    comments.value.unshift(newComment)
    commentText.value = ''
    post.value.commentCount = (post.value.commentCount || 0) + 1
  } finally {
    submitting.value = false
  }
}

// 评论点赞/取消点赞：图标变红（.liked 类）。评论和子回复共用此函数
async function toggleLikeComment(c: any) {
  if (!userStore.isLoggedIn()) { router.push('/login'); return }
  if (c.isLiked) {
    await unlikeComment(c.commentId)
    c.isLiked = false
    c.likeCount = Math.max(0, (c.likeCount || 1) - 1)
  } else {
    await likeComment(c.commentId)
    c.isLiked = true
    c.likeCount = (c.likeCount || 0) + 1
  }
}

// 点击评论内容/回复按钮：弹出该评论的内联回复框；首次展开顺便加载已有子回复
function openReply(c: any) {
  if (!userStore.isLoggedIn()) { router.push('/login'); return }
  c.replyOpen = !c.replyOpen
  if (c.replyOpen) {
    activeReplyId.value = c.commentId
    replyText.value = ''
    if (!c.repliesLoaded) loadReplies(c)
  } else {
    activeReplyId.value = null
  }
}

// 加载某条评论的子回复
async function loadReplies(c: any) {
  const res: any = await getReplies(c.commentId, 1, 50)
  c.replies = (res.data?.records || []).map((r: any) => ({ ...r, isLiked: !!r.isLiked }))
  c.repliesLoaded = true
  c.repliesOpen = true
}

// 展开/收起子回复
function toggleReplies(c: any) {
  if (!c.repliesLoaded) { loadReplies(c); return }
  c.repliesOpen = !c.repliesOpen
}

// 提交子回复：parentCommentId 指向被回复的评论，replyToUserId 指向其作者
async function submitReply(c: any) {
  if (!replyText.value.trim()) return
  const text = replyText.value
  try {
    const res: any = await addComment({
      postId,
      content: text,
      parentCommentId: c.commentId,
      replyToUserId: c.userId
    })
    c.replies.unshift({
      commentId: res.data,
      userId: userStore.userInfo?.userId,
      username: userStore.userInfo?.username,
      nickname: userStore.userInfo?.nickname,
      avatarUrl: userStore.userInfo?.avatarUrl,
      content: text,
      likeCount: 0,
      isLiked: false,
      createdTime: new Date().toISOString()
    })
    c.repliesLoaded = true
    c.repliesOpen = true
    // 成功后再关闭输入框、清空文本
    c.replyOpen = false
    activeReplyId.value = null
    replyText.value = ''
    post.value.commentCount = (post.value.commentCount || 0) + 1
  } catch {
    // 失败时保留输入内容，方便用户重试（错误提示由 http 拦截器统一弹出）
  }
}

async function handleDeleteComment(commentId: number) {
  await ElMessageBox.confirm('确定删除此评论？', '提示', { type: 'warning' })
  await deleteComment(commentId)
  comments.value = comments.value.filter(c => c.commentId !== commentId)
  post.value.commentCount = Math.max(0, (post.value.commentCount || 1) - 1)
}

async function handleCommentAiWrite() {
  if (!commentText.value.trim()) return
  commentAiWriting.value = true
  const original = commentText.value
  try {
    await streamWrite(original, '', (delta) => { commentText.value += delta }, () => { commentAiWriting.value = false })
  } catch (e: any) {
    ElMessage.error('AI续写失败：' + (e.message || '未知错误'))
    commentAiWriting.value = false
  }
}

async function handleReplyAiWrite() {
  if (!replyText.value.trim()) return
  replyAiWriting.value = true
  const original = replyText.value
  try {
    await streamWrite(original, '', (delta) => { replyText.value += delta }, () => { replyAiWriting.value = false })
  } catch (e: any) {
    ElMessage.error('AI续写失败：' + (e.message || '未知错误'))
    replyAiWriting.value = false
  }
}

async function handleDelete() {
  await ElMessageBox.confirm('确定删除此帖子？', '提示', { type: 'warning' })
  await deletePost(postId)
  ElMessage.success('已删除')
  router.push('/')
}

onMounted(() => {
  loadPost()
  loadComments()
})
</script>

<style scoped>
* { box-sizing: border-box; }
.detail-page {
  min-height: calc(100vh - 60px);
  background: var(--bg-page);
  padding: 20px 24px;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
}

/* 整体布局容器，overflow处理超宽情况 */
.detail-wrap {
  overflow-x: auto;
}
.detail-wrap.with-comments { /* 评论展开时card自动扩宽，无需额外处理 */ }
.back-btn-wrap { margin: 16px 0; }

.detail-card {
  display: inline-flex;
  background: #fff;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 2px 16px rgba(0,0,0,0.08);
  min-height: 560px;
  align-items: stretch;
  vertical-align: top;
}

/* 1) 图片区：固定宽度，展开评论时尺寸不变，只随容器居中左移 */
.media-panel {
  flex: 0 0 480px;
  width: 480px;
  background: #0a0a0a;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}
.main-img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
  max-height: calc(100vh - 100px);
}
.main-video {
  width: 100%;
  max-height: calc(100vh - 100px);
  display: block;
  background: #000;
}
.no-img {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 400px;
  background: #F5F5F5;
}
.tag-row { position: absolute; bottom: 16px; left: 16px; }
.topic-tag {
  background: rgba(0,0,0,0.5);
  color: #fff;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 13px;
  backdrop-filter: blur(4px);
}

/* 2) 文案区：固定宽度，与图片区拼合精确撑起card背景 */
.content-panel {
  flex: 0 0 420px;
  width: 420px;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.author-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px;
  border-bottom: 1px solid #F5F5F5;
}
.author-ava { flex-shrink: 0; }
.author-name { font-weight: 600; font-size: 14px; color: #1a1a1a; }
.post-time { font-size: 12px; color: #999; margin-top: 2px; }
.author-follow-btn { margin-left: 12px; }
.author-follow-btn:not(.followed-btn) { background: #FF2442; border-color: #FF2442; }
.author-follow-btn.followed-btn { color: #999; border-color: #ddd; }

.post-title {
  font-size: 20px;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0;
  padding: 16px 20px 8px;
  line-height: 1.4;
}
.post-content {
  font-size: 15px;
  color: #333;
  line-height: 1.8;
  padding: 0 20px 16px;
  white-space: pre-wrap;
  flex: 1 1 auto;
}

.action-bar {
  display: flex;
  gap: 12px;
  padding: 12px 20px;
  border-top: 1px solid #F5F5F5;
}
.like-btn, .stat-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: #767676;
  padding: 6px 12px;
  border-radius: 20px;
  transition: all 0.2s;
}
.like-btn:hover { color: #FF2442; background: rgba(255,36,66,0.06); }
/* 点赞后变红 */
.like-btn.liked { color: #FF2442; }
.fav-btn { display: flex; align-items: center; gap: 6px; background: none; border: none; cursor: pointer; font-size: 14px; color: #767676; padding: 6px 12px; border-radius: 20px; transition: all 0.2s; }
.fav-btn:hover { color: #FFA500; background: rgba(255,165,0,0.08); }
.fav-btn.faved { color: #FFA500; }
.stat-btn:hover { color: #555; background: #F5F5F5; }
.stat-btn.active { color: #FF2442; background: rgba(255,36,66,0.06); }

/* 收藏夹弹窗 */
.fav-dialog-body { padding: 0 4px; }
.fav-list { max-height: 280px; overflow-y: auto; margin-bottom: 14px; }
.fav-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border: 1.5px solid #EFEFEF; border-radius: 10px; margin-bottom: 8px; cursor: pointer; transition: all 0.18s; }
.fav-item:hover { border-color: #FF2442; }
.fav-item.selected { border-color: #FF2442; background: rgba(255,36,66,0.05); }
.fav-item .fav-name { flex: 1; font-size: 14px; color: #333; }
.fav-item .fav-count { font-size: 12px; color: #999; }

/* 3) 评论面板 */
.comment-panel {
  flex: 0 0 460px;
  width: 460px;
  display: flex;
  flex-direction: column;
  border-left: 1px solid #F0F0F0;
  background: #fff;
  min-height: 0;
}
.comment-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
  border-bottom: 1px solid #F5F5F5;
  flex-shrink: 0;
}
.close-btn { color: #999; }

/* 评论列表：可滚动区域，滚轮下滑加载更多 */
.comment-list {
  flex: 1 1 0;
  overflow-y: auto;
  padding: 12px 18px;
  scrollbar-width: thin;
}
.comment-item {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.c-ava { flex-shrink: 0; }
.c-body { flex: 1; min-width: 0; }
.c-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.c-name { font-size: 13px; font-weight: 600; color: #1a1a1a; }
.c-time { font-size: 11px; color: #bbb; }
.c-text { font-size: 14px; color: #333; line-height: 1.6; word-break: break-word; cursor: pointer; }
.c-text:hover { color: #000; }

/* 评论操作行：点赞 / 回复 / 展开回复 */
.c-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 6px;
}
.c-like-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  color: #999;
  padding: 2px 4px;
  transition: color 0.2s;
}
.c-like-btn:hover { color: #FF2442; }
.c-like-btn.liked { color: #FF2442; }
.c-like-btn.sm { font-size: 11px; }
.c-reply-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  color: #999;
  padding: 2px 4px;
}
.c-reply-btn:hover { color: #FF2442; }
.c-toggle-replies {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  color: #13386c;
  padding: 2px 4px;
  margin-left: auto;
}
.c-toggle-replies:hover { opacity: 0.75; }

/* 子回复列表 */
.reply-list {
  margin-top: 10px;
  padding: 8px 12px;
  background: #F7F7F7;
  border-radius: 10px;
}
.reply-item {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.reply-item:last-child { margin-bottom: 0; }
.r-ava { flex-shrink: 0; }
.r-body { flex: 1; min-width: 0; }
.r-line { font-size: 13px; line-height: 1.5; word-break: break-word; }
.r-name { font-weight: 600; color: #FF2442; margin-right: 6px; }
.r-text { color: #333; }
.r-meta { display: flex; align-items: center; gap: 12px; margin-top: 3px; }
.r-time { font-size: 11px; color: #bbb; }

/* 内联回复输入框 */
.reply-input {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;
}
.reply-action-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.reply-input.login-hint.sm {
  font-size: 12px;
  padding: 6px 0;
}
.list-tip { text-align: center; color: #bbb; font-size: 12px; padding: 10px 0; }
.no-comment { text-align: center; color: #ccc; font-size: 14px; padding: 40px 0; }

/* 底部输入框：固定在评论面板底部，不随列表滚动 */
.comment-input-fixed {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #F5F5F5;
  background: #fff;
  flex-shrink: 0;
}
.comment-input-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.comment-action-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-left: 40px;
}
.input-ava { flex-shrink: 0; margin-top: 6px; }
:deep(.comment-input .el-textarea__inner) {
  background: #F2F2F2;
  box-shadow: none;
  border-radius: 12px;
  resize: none;
}
:deep(.reply-text-input .el-textarea__inner) {
  border-radius: 10px;
  resize: none;
}
.ai-inline-btn {
  color: #FF2442;
  font-size: 12px;
  padding: 0 4px;
  white-space: nowrap;
}
.ai-inline-btn:hover { opacity: 0.75; }
.ai-inline-btn:disabled { color: #ccc; }
.publish-btn {
  background: #FF2442;
  border-color: #FF2442;
  flex-shrink: 0;
}
.login-hint {
  color: #999;
  font-size: 13px;
  text-align: center;
  padding: 14px;
  border-top: 1px solid #F5F5F5;
  flex-shrink: 0;
}
.login-hint a { color: #FF2442; font-weight: 600; }

/* 评论面板展开动画 */
.slide-panel-enter-active, .slide-panel-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.slide-panel-enter-from, .slide-panel-leave-to {
  opacity: 0;
  transform: translateX(40px);
}

/* 举报按钮（帖子操作栏） */
.report-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: #767676;
  padding: 6px 12px;
  border-radius: 20px;
  transition: all 0.2s;
  margin-left: auto;
}
.report-btn:hover { color: #FF2442; background: rgba(255,36,66,0.06); }

/* 举报弹窗 */
.report-dialog-body { padding: 0 4px; }
.report-target {
  font-size: 13px;
  color: #666;
  margin-bottom: 14px;
  padding: 8px 12px;
  background: #F7F7F7;
  border-radius: 8px;
}
.report-target span { color: #FF2442; font-weight: 600; }
.report-field { margin-bottom: 14px; }
.report-label { font-size: 13px; color: #333; margin-bottom: 6px; }
</style>
