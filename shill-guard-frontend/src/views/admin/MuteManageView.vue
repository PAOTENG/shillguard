<template>
  <div class="mute-page">
    <!-- 页头操作栏 -->
    <div class="page-toolbar">
      <div class="toolbar-left">
        <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width:140px" @change="loadList">
          <el-option label="全部" value="" />
          <el-option label="禁言中" :value="1" />
          <el-option label="已解除" :value="0" />
        </el-select>
      </div>
      <el-button type="primary" round @click="showMuteDialog = true"
        style="background:#FF2442;border-color:#FF2442">
        <el-icon><Plus /></el-icon> 手动禁言
      </el-button>
    </div>

    <!-- 表格 -->
    <div class="table-card">
      <el-table :data="list" v-loading="loading" row-class-name="table-row">
        <el-table-column prop="muteId" label="ID" width="70" />
        <el-table-column label="被禁用户" width="120">
          <template #default="{ row }">
            {{ nameOf(row.mutedUserId) }}
          </template>
        </el-table-column>
        <el-table-column prop="muteReason" label="禁言原因" show-overflow-tooltip min-width="180" />
        <el-table-column prop="muteDays" label="天数" width="70" />
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.muteType === 0 ? 'danger' : 'warning'" size="small" round>
              {{ row.muteType === 0 ? '🤖 Agent' : '✍️ 人工' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'danger' : 'success'" size="small" round>
              {{ row.status === 1 ? '禁言中' : '已解除' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="createdTime" label="时间" width="150" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 1" link type="primary" size="small" @click="handleUnmute(row.muteId)">解除禁言</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          background layout="prev, pager, next, total"
          :total="total" :page-size="10"
          v-model:current-page="pageNum"
          @current-change="loadList"
        />
      </div>
    </div>
  </div>

  <!-- 手动禁言对话框 -->
  <el-dialog v-model="showMuteDialog" title="手动禁言" width="420px">
    <el-form :model="muteForm" label-width="80px" size="large">
      <el-form-item label="用户ID">
        <el-input-number v-model="muteForm.userId" :min="1" style="width:100%" />
      </el-form-item>
      <el-form-item label="禁言原因">
        <el-input v-model="muteForm.reason" type="textarea" :rows="3" placeholder="请输入禁言原因" />
      </el-form-item>
      <el-form-item label="天数">
        <el-input-number v-model="muteForm.duration" :min="1" :max="365" />
        <span style="margin-left:8px;color:#999;font-size:13px">天</span>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button round @click="showMuteDialog = false">取消</el-button>
      <el-button type="primary" round :loading="submitting" @click="handleManualMute"
        style="background:#FF2442;border-color:#FF2442">确认禁言</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { getMuteList, manualMute, cancelMute } from '@/api/agent'
import { useUserNames } from '@/api/user'

const list = ref<any[]>([])
const total = ref(0)
const pageNum = ref(1)
const loading = ref(false)
const showMuteDialog = ref(false)
const submitting = ref(false)
const filterStatus = ref<any>('')
const muteForm = reactive({ userId: undefined as any, reason: '', duration: 7 })
const { loadNames, nameOf } = useUserNames()

async function loadList() {
  loading.value = true
  try {
    const status = filterStatus.value === '' ? undefined : filterStatus.value
    const res: any = await getMuteList(pageNum.value, 10, status)
    list.value = res.data?.records || []
    total.value = res.data?.total || 0
    // 解析被禁用户昵称
    loadNames(list.value.map((r: any) => r.mutedUserId).filter(Boolean))
  } finally {
    loading.value = false
  }
}

async function handleUnmute(muteId: number) {
  await ElMessageBox.confirm('确认解除该禁言？', '提示', { type: 'warning' })
  await cancelMute(muteId)
  ElMessage.success('已解除禁言')
  loadList()
}

async function handleManualMute() {
  if (!muteForm.userId || !muteForm.reason) {
    ElMessage.warning('用户ID和禁言原因不能为空')
    return
  }
  submitting.value = true
  try {
    await manualMute({ userId: muteForm.userId, reason: muteForm.reason, duration: muteForm.duration })
    ElMessage.success('禁言成功')
    showMuteDialog.value = false
    Object.assign(muteForm, { userId: undefined, reason: '', duration: 7 })
    loadList()
  } finally {
    submitting.value = false
  }
}

onMounted(loadList)
</script>

<style scoped>
* { box-sizing: border-box; }
.mute-page { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; }
.page-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.toolbar-left { display: flex; gap: 10px; }
.table-card { background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 6px rgba(0,0,0,0.06); }
:deep(.table-row:hover > td) { background: #FFF5F6 !important; }
.pagination-wrap { display: flex; justify-content: flex-end; padding: 16px 20px; }
</style>
