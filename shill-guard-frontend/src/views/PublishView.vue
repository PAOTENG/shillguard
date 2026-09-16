<template>
  <div class="publish-page">
    <div class="publish-wrap">
      <div class="page-header">
        <el-button text @click="router.back()"><el-icon><ArrowLeft /></el-icon> 返回</el-button>
        <h2>发布笔记</h2>
      </div>

      <!-- 审核中遮罩反馈 -->
      <div class="reviewing-mask" v-if="reviewing">
        <div class="reviewing-box">
          <el-icon class="rotating" :size="40" color="#FF2442"><Loading /></el-icon>
          <div class="reviewing-text">正在审核中...</div>
          <div class="reviewing-sub">系统正在检查内容是否包含敏感词或违法信息</div>
        </div>
      </div>

      <!-- 审核结果提示 -->
      <el-alert
        v-if="reviewResult"
        :title="reviewResult.reviewStatus === 0 ? '审核通过 ✓' : '审核不通过 ✗'"
        :type="reviewResult.reviewStatus === 0 ? 'success' : 'error'"
        show-icon
        :closable="false"
        class="review-alert"
      >
        <div class="alert-reason">{{ reviewResult.reason }}</div>
        <div class="alert-actions" v-if="reviewResult.reviewStatus === 0">
          <el-button size="small" type="primary" round @click="router.push(`/post/${reviewResult.postId}`)">查看笔记</el-button>
          <el-button size="small" round @click="router.push('/')">回首页</el-button>
          <el-button size="small" round @click="resetAll">再发一篇</el-button>
        </div>
        <div class="alert-actions" v-else>
          <el-button size="small" round @click="reviewResult = null">修改后重新提交</el-button>
        </div>
      </el-alert>

      <div class="form-card" v-if="!reviewResult">
        <!-- 类型切换 -->
        <div class="type-switch">
          <button :class="{ active: mode === 'image' }" @click="switchMode('image')">图文</button>
          <button :class="{ active: mode === 'video' }" @click="switchMode('video')">视频</button>
        </div>

        <!-- 标题（可选） -->
        <el-input v-model="form.title" placeholder="填写标题（可选，留空自动取正文开头）" maxlength="50" show-word-limit class="title-input" size="large" />

        <!-- 内容（必填） -->
        <el-input
          v-model="form.content" type="textarea" :rows="6"
          placeholder="分享你的想法（必填）..." maxlength="2000" show-word-limit
        />
        <div class="ai-write-bar">
          <div class="field-tip">内容为必填，发布前会做敏感词审核</div>
          <el-button
            size="small" round
            :loading="aiWriting"
            :disabled="!form.content.trim()"
            @click="handleAiWrite"
            class="ai-btn"
          >
            <el-icon v-if="!aiWriting"><MagicStick /></el-icon>
            {{ aiWriting ? 'AI 续写中...' : 'AI 续写' }}
          </el-button>
        </div>

        <!-- 媒体（必填） -->
        <div class="media-section">
          <div class="media-label">{{ mode === 'image' ? '图片（必填，最多9张，首图作封面）' : '视频（必填，最大200MB）' }}</div>

          <el-upload
            v-if="mode === 'image'"
            list-type="picture-card"
            :http-request="uploadImageReq"
            :before-upload="beforeImage"
            :on-remove="removeImage"
            :on-exceed="() => ElMessage.warning('最多上传 9 张图片')"
            :limit="9"
            accept="image/*"
            multiple
            class="img-uploader"
          >
            <el-icon class="upload-icon"><Plus /></el-icon>
          </el-upload>

          <el-upload
            v-else
            :http-request="uploadVideoReq"
            :before-upload="beforeVideo"
            :on-remove="removeVideo"
            :limit="1"
            :on-exceed="() => ElMessage.warning('只能上传 1 个视频')"
            accept="video/*"
            class="video-uploader"
          >
            <el-button type="primary" plain :loading="uploading">
              <el-icon><UploadFilled /></el-icon> 选择视频
            </el-button>
            <template #tip>
              <div class="upload-tip">支持 mp4 / mov，上传后自动存到 MinIO</div>
            </template>
          </el-upload>
        </div>

        <!-- 话题标签（可选） -->
        <el-input v-model="form.topicTag" placeholder="添加话题标签（可选，如：科技、生活）" :prefix-icon="PriceTag" class="topic-input" />

        <!-- 提交 -->
        <div class="submit-bar">
          <div class="status-hint">
            <span v-if="mode === 'image'">已上传 {{ imgUrlMap.size }}/9 张</span>
            <span v-else>{{ videoUrl ? '视频已就绪' : '未上传视频' }}</span>
          </div>
          <el-button @click="router.back()" round>取消</el-button>
          <el-button type="primary" :loading="reviewing" @click="handleSubmit" round
            style="background:#FF2442;border-color:#FF2442;min-width:120px">
            提交审核
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Plus, UploadFilled, PriceTag, Loading, MagicStick } from '@element-plus/icons-vue'
import { createPost } from '@/api/post'
import { uploadImage, uploadVideo } from '@/api/file'
import { streamWrite } from '@/api/writer'

const router = useRouter()
const reviewing = ref(false)
const uploading = ref(false)
const aiWriting = ref(false)
const reviewResult = ref<any>(null)
const mode = ref<'image' | 'video'>('image')

const form = reactive({ title: '', content: '', topicTag: '' })

// 已上传到 MinIO 的资源 URL（按 el-upload 文件 uid 映射，保持上传顺序）
const imgUrlMap = ref(new Map<number, string>())
const videoUrl = ref('')
const videoUid = ref<number | null>(null)

function switchMode(m: 'image' | 'video') {
  if (m === mode.value) return
  if (mode.value === 'image') imgUrlMap.value.clear()
  else { videoUrl.value = ''; videoUid.value = null }
  mode.value = m
}

// ---- 图片上传 ----
function beforeImage(file: File) {
  if (!file.type.startsWith('image/')) { ElMessage.error('只能上传图片'); return false }
  if (file.size > 10 * 1024 * 1024) { ElMessage.error('图片不能超过 10MB'); return false }
  return true
}
async function uploadImageReq(opt: any) {
  uploading.value = true
  try {
    const res: any = await uploadImage(opt.file)
    imgUrlMap.value.set(opt.file.uid, res.data)
    opt.onSuccess(res)
  } catch (e: any) {
    opt.onError(e)
  } finally {
    uploading.value = false
  }
}
function removeImage(file: any) {
  imgUrlMap.value.delete(file.uid)
}

// ---- 视频上传 ----
function beforeVideo(file: File) {
  if (!file.type.startsWith('video/')) { ElMessage.error('只能上传视频'); return false }
  if (file.size > 200 * 1024 * 1024) { ElMessage.error('视频不能超过 200MB'); return false }
  return true
}
async function uploadVideoReq(opt: any) {
  uploading.value = true
  try {
    const res: any = await uploadVideo(opt.file)
    videoUrl.value = res.data
    videoUid.value = opt.file.uid
    opt.onSuccess(res)
  } catch (e: any) {
    opt.onError(e)
  } finally {
    uploading.value = false
  }
}
function removeVideo() {
  videoUrl.value = ''
  videoUid.value = null
}

async function handleSubmit() {
  if (!form.content.trim()) { ElMessage.warning('请输入内容'); return }
  if (mode.value === 'image' && imgUrlMap.value.size === 0) { ElMessage.warning('请至少上传一张图片'); return }
  if (mode.value === 'video' && !videoUrl.value) { ElMessage.warning('请上传一个视频'); return }

  reviewing.value = true
  reviewResult.value = null
  try {
    const imageUrls = [...imgUrlMap.value.values()]
    const res: any = await createPost({
      title: form.title,
      content: form.content,
      topicTag: form.topicTag,
      postType: mode.value === 'video' ? 3 : 2,
      coverUrl: mode.value === 'image' ? imageUrls[0] : '',
      mediaUrl: mode.value === 'video' ? videoUrl.value : '',
    })
    // res.data = { postId, reviewStatus, reason }
    reviewResult.value = res.data
  } finally {
    reviewing.value = false
  }
}

async function handleAiWrite() {
  if (!form.content.trim()) return
  aiWriting.value = true
  const original = form.content
  form.content = original + ''
  try {
    await streamWrite(
      original,
      '',
      (delta) => { form.content += delta },
      () => { aiWriting.value = false }
    )
  } catch (e: any) {
    ElMessage.error('AI 续写失败：' + (e.message || '未知错误'))
    aiWriting.value = false
  }
}

function resetAll() {
  form.title = ''
  form.content = ''
  form.topicTag = ''
  imgUrlMap.value.clear()
  videoUrl.value = ''
  videoUid.value = null
  mode.value = 'image'
  reviewResult.value = null
}
</script>

<style scoped>
* { box-sizing: border-box; }
.publish-page {
  min-height: calc(100vh - 60px);
  background: #F6F6F6;
  padding: 24px;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
}
.publish-wrap { max-width: 720px; margin: 0 auto; position: relative; }
.page-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 22px; font-weight: 700; color: #1a1a1a; }

.form-card {
  background: #fff; border-radius: 16px; padding: 24px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.06);
  display: flex; flex-direction: column; gap: 16px;
}
:deep(.title-input .el-input__wrapper) { font-size: 16px; font-weight: 500; }
:deep(.el-textarea__inner) { border-radius: 8px; }
.ai-write-bar { display: flex; align-items: center; justify-content: space-between; margin-top: -8px; }
.field-tip { font-size: 12px; color: #999; }
.ai-btn { background: linear-gradient(135deg, #FF2442, #ff6b6b); border: none; color: #fff; font-size: 12px; }
.ai-btn:hover { opacity: 0.85; }
.ai-btn:disabled { opacity: 0.5; }

.type-switch { display: flex; gap: 8px; }
.type-switch button {
  padding: 6px 22px; border-radius: 18px; border: 1.5px solid #EBEBEB;
  background: #fff; color: #555; font-size: 14px; cursor: pointer; transition: all 0.18s;
}
.type-switch button:hover { border-color: #FF2442; color: #FF2442; }
.type-switch button.active { background: #FF2442; border-color: #FF2442; color: #fff; }

.media-section { display: flex; flex-direction: column; gap: 8px; }
.media-label { font-size: 14px; font-weight: 600; color: #333; }
.upload-icon { font-size: 24px; color: #999; }
.upload-tip { font-size: 12px; color: #999; margin-top: 6px; }
:deep(.img-uploader .el-upload-list--picture-card .el-upload-list__item) { border-radius: 10px; }
:deep(.img-uploader .el-upload--picture-card) { border-radius: 10px; }

.submit-bar { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.status-hint { margin-right: auto; font-size: 13px; color: #999; }

/* 审核中遮罩 */
.reviewing-mask {
  position: fixed; inset: 0; background: rgba(255,255,255,0.7);
  backdrop-filter: blur(4px); z-index: 999; display: flex; align-items: center; justify-content: center;
}
.reviewing-box { text-align: center; }
.reviewing-text { font-size: 20px; font-weight: 700; color: #FF2442; margin-top: 16px; }
.reviewing-sub { font-size: 13px; color: #999; margin-top: 6px; }
.rotating { animation: rotate 1s linear infinite; }
@keyframes rotate { to { transform: rotate(360deg); } }

.review-alert { margin-bottom: 16px; }
.alert-reason { font-size: 14px; color: #555; margin: 4px 0; }
.alert-actions { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
</style>
