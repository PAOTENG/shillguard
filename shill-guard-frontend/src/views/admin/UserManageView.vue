<template>
  <div class="user-page">
    <div class="page-toolbar">
      <el-select v-model="filterRole" placeholder="全部角色" clearable style="width:140px" @change="loadList">
        <el-option label="全部" value="" />
        <el-option label="普通用户" :value="0" />
        <el-option label="审核员" :value="1" />
        <el-option label="管理员" :value="2" />
        <el-option label="超级管理员" :value="3" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width:140px" @change="loadList">
        <el-option label="全部" value="" />
        <el-option label="正常" :value="0" />
        <el-option label="禁言中" :value="1" />
        <el-option label="已封号" :value="2" />
      </el-select>
      <el-input
        v-model="keyword" placeholder="搜索用户名/昵称/手机号..."
        clearable style="width:240px"
        @keyup.enter="loadList" @clear="loadList"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button round @click="loadList">搜索</el-button>
    </div>

    <div class="table-card">
      <el-table :data="list" v-loading="loading">
        <el-table-column prop="userId" label="ID" width="70" />
        <el-table-column label="用户" min-width="160">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:10px">
              <el-avatar :size="32" :src="row.avatarUrl">{{ row.nickname?.charAt(0) }}</el-avatar>
              <div>
                <div style="font-weight:600;font-size:13px;display:flex;align-items:center;gap:6px">
                  {{ row.nickname }}
                  <el-tooltip v-if="row.warningLevel === 1" content="恶意行为预警：异常分数 0.8~0.9" placement="top">
                    <el-icon color="#e6a23c" :size="14"><Warning /></el-icon>
                  </el-tooltip>
                  <el-tooltip v-else-if="row.warningLevel === 2" content="高危用户：已自动禁言7天" placement="top">
                    <el-icon color="#FF2442" :size="14"><WarningFilled /></el-icon>
                  </el-tooltip>
                </div>
                <div style="color:#999;font-size:12px">@{{ row.username }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="roleTagType(row.role)" size="small" round>{{ roleText(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" round>{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="createdTime" label="注册时间" width="150" />
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openRoleDialog(row)">改角色</el-button>
            <el-button v-if="row.status !== 2" link type="danger" size="small" @click="handleBan(row)">封号</el-button>
            <el-button v-else link type="success" size="small" @click="handleUnban(row)">解封</el-button>
            <el-button link type="warning" size="small" @click="handleResetPwd(row)">重置密码</el-button>
            <el-button link type="info" size="small" @click="router.push(`/admin/mute?userId=${row.userId}`)">禁言记录</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination background layout="prev, pager, next, total"
          :total="total" :page-size="20"
          v-model:current-page="pageNum" @current-change="loadList" />
      </div>
    </div>

    <!-- 改角色弹窗 -->
    <el-dialog v-model="roleDialogVisible" :title="`修改角色 - ${curUser?.nickname || ''}`" width="420px" align-center>
      <el-select v-model="curRole" style="width:100%">
        <el-option label="普通用户" :value="0" />
        <el-option label="审核员" :value="1" />
        <el-option label="管理员" :value="2" />
        <el-option label="超级管理员" :value="3" />
      </el-select>
      <div class="role-tip">仅超级管理员(role=3)可修改他人角色。修改后该用户登录态权限即时生效。</div>
      <template #footer>
        <el-button @click="roleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="roleSaving" @click="saveRole">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Warning, WarningFilled } from '@element-plus/icons-vue'
import { getAdminUserList, updateUserRole, updateUserStatus, resetUserPassword } from '@/api/admin'

const router = useRouter()
const list = ref<any[]>([])
const total = ref(0)
const pageNum = ref(1)
const loading = ref(false)
const keyword = ref('')
const filterRole = ref<any>('')
const filterStatus = ref<any>('')

async function loadList() {
  loading.value = true
  try {
    const res: any = await getAdminUserList({
      pageNum: pageNum.value,
      pageSize: 20,
      keyword: keyword.value || undefined,
      role: filterRole.value === '' ? undefined : filterRole.value,
      status: filterStatus.value === '' ? undefined : filterStatus.value,
    })
    list.value = res.data?.records || []
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

// ===== 改角色 =====
const roleDialogVisible = ref(false)
const curUser = ref<any>(null)
const curRole = ref(0)
const roleSaving = ref(false)

function openRoleDialog(row: any) {
  curUser.value = row
  curRole.value = row.role
  roleDialogVisible.value = true
}

async function saveRole() {
  if (!curUser.value) return
  roleSaving.value = true
  try {
    await updateUserRole(curUser.value.userId, curRole.value)
    ElMessage.success('角色已更新')
    roleDialogVisible.value = false
    loadList()
  } finally {
    roleSaving.value = false
  }
}

// ===== 封号/解封 =====
async function handleBan(row: any) {
  await ElMessageBox.confirm(`确认封号用户「${row.nickname}」？封号后该用户无法登录。`, '封号', { type: 'warning' })
  await updateUserStatus(row.userId, 2)
  ElMessage.success('已封号')
  loadList()
}

async function handleUnban(row: any) {
  await ElMessageBox.confirm(`确认解封用户「${row.nickname}」？`, '解封', { type: 'info' })
  await updateUserStatus(row.userId, 0)
  ElMessage.success('已解封')
  loadList()
}

// ===== 重置密码 =====
async function handleResetPwd(row: any) {
  await ElMessageBox.confirm(`确认将用户「${row.nickname}」的密码重置为 123456？`, '重置密码', { type: 'warning' })
  await resetUserPassword(row.userId)
  ElMessage.success('密码已重置为 123456')
}

// ===== 文案 =====
function roleText(r: number) {
  return ({ 0: '普通用户', 1: '审核员', 2: '管理员', 3: '超级管理员' } as any)[r] || '未知'
}
function roleTagType(r: number) {
  return ({ 0: 'info', 1: 'warning', 2: 'danger', 3: 'danger' } as any)[r] || 'info'
}
function statusText(s: number) {
  return ({ 0: '正常', 1: '禁言中', 2: '已封号' } as any)[s] ?? '正常'
}
function statusTagType(s: number) {
  return ({ 0: 'success', 1: 'warning', 2: 'danger' } as any)[s] ?? 'success'
}

onMounted(loadList)
</script>

<style scoped>
* { box-sizing: border-box; }
.user-page { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; }
.page-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.table-card { background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 6px rgba(0,0,0,0.06); }
.pagination-wrap { display: flex; justify-content: flex-end; padding: 16px 20px; }
.role-tip { font-size: 12px; color: #999; margin-top: 10px; line-height: 1.5; }
</style>
