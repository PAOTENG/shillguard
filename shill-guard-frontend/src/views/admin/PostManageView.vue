<template>
  <div class="post-page">
    <div class="page-toolbar">
      <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width:140px" @change="loadList">
        <el-option label="全部" value="" />
        <el-option label="正常" :value="0" />
        <el-option label="已删除" :value="1" />
        <el-option label="审核中" :value="2" />
        <el-option label="审核不通过" :value="3" />
      </el-select>
      <el-select v-model="filterType" placeholder="全部类型" clearable style="width:140px" @change="loadList">
        <el-option label="全部" value="" />
        <el-option label="纯文字" :value="1" />
        <el-option label="图文" :value="2" />
        <el-option label="视频" :value="3" />
      </el-select>
      <el-input
        v-model="keyword" placeholder="搜索标题/正文/标签..."
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
        <el-table-column label="标题" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ deleted: row.status === 1 }">{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="80">
          <template #default="{ row }">{{ typeText(row.postType) }}</template>
        </el-table-column>
        <el-table-column label="作者" width="120">
          <template #default="{ row }">
            {{ nameOf(row.userId) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" round>{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="viewCount" label="浏览" width="80" />
        <el-table-column prop="likeCount" label="点赞" width="70" />
        <el-table-column prop="commentCount" label="评论" width="70" />
        <el-table-column prop="createdTime" label="发布时间" width="150" />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 0" link type="danger" size="small" @click="handleDelete(row)">逻辑删除</el-button>
            <el-button v-else link type="success" size="small" @click="handleRestore(row)">恢复</el-button>
            <el-button link type="primary" size="small" @click="viewDetail(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination background layout="prev, pager, next, total"
          :total="total" :page-size="pageSize"
          v-model:current-page="pageNum" @current-change="loadList" />
      </div>
    </div>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="帖子详情" width="640px" align-center>
      <div v-if="curDetail" class="detail-body">
        <div class="detail-row"><span class="dl-label">标题</span><b>{{ curDetail.title }}</b></div>
        <div class="detail-row"><span class="dl-label">作者</span>{{ nameOf(curDetail.userId) }}</div>
        <div class="detail-row"><span class="dl-label">类型</span>{{ typeText(curDetail.postType) }}</div>
        <div class="detail-row"><span class="dl-label">标签</span>{{ curDetail.topicTag || '—' }}</div>
        <div class="detail-row"><span class="dl-label">封面</span>
          <el-image v-if="curDetail.coverUrl" :src="curDetail.coverUrl" style="width:120px" fit="cover" />
          <span v-else>—</span>
        </div>
        <div class="detail-row"><span class="dl-label">视频</span>
          <video v-if="curDetail.mediaUrl && curDetail.postType === 3" :src="curDetail.mediaUrl" controls style="max-width:400px;max-height:240px" />
          <span v-else>{{ curDetail.mediaUrl || '—' }}</span>
        </div>
        <div class="detail-content">
          <div class="dl-label">正文</div>
          <div class="content-text">{{ curDetail.content }}</div>
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
import { useUserNames } from '@/api/user'

const list = ref<any[]>([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = 20
const loading = ref(false)
const keyword = ref('')
const filterStatus = ref<any>('')
const filterType = ref<any>('')

const detailVisible = ref(false)
const curDetail = ref<any>(null)
const { loadNames, nameOf } = useUserNames()

async function loadList() {
  loading.value = true
  try {
    const res: any = await getPostList({
      pageNum: pageNum.value,
      pageSize,
      status: filterStatus.value === '' ? undefined : filterStatus.value,
      postType: filterType.value === '' ? undefined : filterType.value,
      keyword: keyword.value || undefined,
    })
    list.value = res.data?.records || []
    total.value = res.data?.total || 0
    loadNames(list.value.map((r: any) => r.userId).filter(Boolean))
  } finally {
    loading.value = false
  }
}

async function handleDelete(row: any) {
  await ElMessageBox.confirm(`确认逻辑删除帖子 #${row.postId}？删除后普通用户不可见，管理员仍可恢复。`, '逻辑删除', { type: 'warning' })
  await setPostStatus(row.postId, 1)
  ElMessage.success('已逻辑删除')
  loadList()
}

async function handleRestore(row: any) {
  await ElMessageBox.confirm(`确认恢复帖子 #${row.postId}？恢复后将重新对普通用户可见。`, '恢复', { type: 'info' })
  await setPostStatus(row.postId, 0)
  ElMessage.success('已恢复')
  loadList()
}

function viewDetail(row: any) {
  curDetail.value = row
  detailVisible.value = true
}

function typeText(t: number) {
  return ({ 1: '纯文字', 2: '图文', 3: '视频' } as any)[t] || '未知'
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
.post-page { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; }
.page-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.table-card { background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 6px rgba(0,0,0,0.06); }
.pagination-wrap { display: flex; justify-content: flex-end; padding: 16px 20px; }
.deleted { color: #aaa; text-decoration: line-through; }

.detail-body { padding: 0 4px; }
.detail-row { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid #F2F2F2; font-size: 14px; color: #333; }
.dl-label { font-size: 13px; color: #999; min-width: 60px; flex-shrink: 0; }
.detail-content { padding: 12px 0; }
.content-text { margin-top: 6px; font-size: 14px; color: #333; line-height: 1.7; white-space: pre-wrap; word-break: break-word; background: #F7F7F7; padding: 12px; border-radius: 8px; }
</style>
