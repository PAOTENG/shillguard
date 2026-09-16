<template>
  <div class="video-page">
    <div class="page-toolbar">
      <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width:140px" @change="loadList">
        <el-option label="全部" value="" />
        <el-option label="正常" :value="0" />
        <el-option label="已删除" :value="1" />
        <el-option label="审核中" :value="2" />
      </el-select>
      <el-input
        v-model="keyword" placeholder="搜索视频标题/正文..."
        clearable style="width:240px"
        @keyup.enter="loadList" @clear="loadList"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button round @click="loadList">搜索</el-button>
    </div>

    <div class="table-card">
      <el-table :data="list" v-loading="loading">
        <el-table-column prop="postId" label="ID" width="70" />
        <el-table-column label="封面" width="110">
          <template #default="{ row }">
            <el-image v-if="row.coverUrl" :src="row.coverUrl" style="width:80px;height:50px" fit="cover" />
            <video v-else-if="row.mediaUrl" :src="row.mediaUrl" style="width:80px;height:50px;object-fit:cover" />
            <span v-else style="color:#ccc">—</span>
          </template>
        </el-table-column>
        <el-table-column label="标题" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ deleted: row.status === 1 }">{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="userId" label="作者" width="80" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" round>{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="viewCount" label="浏览" width="80" />
        <el-table-column prop="likeCount" label="点赞" width="70" />
        <el-table-column prop="createdTime" label="发布时间" width="150" />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="preview(row)">预览</el-button>
            <el-button v-if="row.status === 0" link type="danger" size="small" @click="handleDelete(row)">下架</el-button>
            <el-button v-else link type="success" size="small" @click="handleRestore(row)">恢复</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination background layout="prev, pager, next, total"
          :total="total" :page-size="pageSize"
          v-model:current-page="pageNum" @current-change="loadList" />
      </div>
    </div>

    <!-- 视频预览弹窗 -->
    <el-dialog v-model="previewVisible" :title="curVideo?.title || '视频预览'" width="640px" align-center>
      <div v-if="curVideo" class="preview-body">
        <video v-if="curVideo.mediaUrl" :src="curVideo.mediaUrl" controls style="width:100%;max-height:360px" />
        <div v-else style="color:#999;padding:20px;text-align:center">该帖子无视频源（mediaUrl 为空）</div>
        <div class="preview-meta">
          <div><span class="pm-label">作者ID：</span>{{ curVideo.userId }}</div>
          <div><span class="pm-label">发布时间：</span>{{ curVideo.createdTime }}</div>
          <div><span class="pm-label">正文：</span>{{ curVideo.content }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { getPostList, setPostStatus } from '@/api/admin'

const list = ref<any[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = 20
const loading = ref(false)
const keyword = ref('')
const filterStatus = ref<any>('')

const previewVisible = ref(false)
const curVideo = ref<any>(null)

async function loadList() {
  loading.value = true
  try {
    // 视频管理固定 postType=3
    const res: any = await getPostList({
      pageNum: pageNum.value,
      pageSize,
      postType: 3,
      status: filterStatus.value === '' ? undefined : filterStatus.value,
      keyword: keyword.value || undefined,
    })
    list.value = res.data?.records || []
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

function preview(row: any) {
  curVideo.value = row
  previewVisible.value = true
}

async function handleDelete(row: any) {
  await ElMessageBox.confirm(`确认下架视频 #${row.postId}？下架后普通用户不可见。`, '下架', { type: 'warning' })
  await setPostStatus(row.postId, 1)
  ElMessage.success('已下架')
  loadList()
}

async function handleRestore(row: any) {
  await ElMessageBox.confirm(`确认恢复视频 #${row.postId}？`, '恢复', { type: 'info' })
  await setPostStatus(row.postId, 0)
  ElMessage.success('已恢复')
  loadList()
}

function statusText(s: number) {
  return ({ 0: '正常', 1: '已删除', 2: '审核中', 3: '审核不通过' } as any)[s] || '未知'
}
function statusTagType(s: number) {
  return ({ 0: 'success', 1: 'info', 2: 'warning', 3: 'danger' } as any)[s] || 'info'
}

onMounted(loadList)
</script>

<style scoped>
* { box-sizing: border-box; }
.video-page { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; }
.page-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.table-card { background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 6px rgba(0,0,0,0.06); }
.pagination-wrap { display: flex; justify-content: flex-end; padding: 16px 20px; }
.deleted { color: #aaa; text-decoration: line-through; }
.preview-body { padding: 0 4px; }
.preview-meta { margin-top: 12px; font-size: 13px; color: #333; line-height: 1.8; }
.pm-label { color: #999; }
</style>
