<template>
  <div class="role-page">
    <div class="page-toolbar">
      <span class="page-title">角色列表</span>
      <el-button type="primary" round @click="openCreate">+ 新增角色</el-button>
    </div>

    <div class="table-card">
      <el-table :data="roles" v-loading="loading">
        <el-table-column prop="roleId" label="角色ID" width="90" />
        <el-table-column prop="roleName" label="角色名称" width="160" />
        <el-table-column prop="roleCode" label="编码" width="160" />
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 0 ? 'success' : 'danger'" size="small" round>
              {{ row.status === 0 ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openAssign(row)">分配菜单</el-button>
            <el-button link type="warning" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.roleId > 3" link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
            <span v-else style="color:#ccc;font-size:12px">预置不可删</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新增/编辑角色弹窗 -->
    <el-dialog v-model="formVisible" :title="editing ? '编辑角色' : '新增角色'" width="480px" align-center :close-on-click-modal="false">
      <el-form :model="form" label-width="90px">
        <el-form-item label="角色名称">
          <el-input v-model="form.roleName" placeholder="如：内容运营" />
        </el-form-item>
        <el-form-item label="角色编码">
          <el-input v-model="form.roleCode" placeholder="如：operator" :disabled="editing" />
          <div class="form-tip">编码用于唯一标识，编辑后不可修改</div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRole">保存</el-button>
      </template>
    </el-dialog>

    <!-- 分配菜单弹窗 -->
    <el-dialog v-model="assignVisible" :title="`分配菜单 - ${curRole?.roleName || ''}`" width="520px" align-center :close-on-click-modal="false">
      <div v-loading="assignLoading">
        <el-tree
          ref="treeRef"
          :data="menuTree"
          node-key="menuId"
          :props="{ label: 'menuName', children: 'children' }"
          show-checkbox
          default-expand-all
        />
      </div>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" :loading="assigning" @click="saveAssign">保存分配</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type ElTree } from 'element-plus'
import {
  getRoleList, createRole, updateRole, deleteRole,
  getAllMenus, getRoleMenuIds, assignRoleMenus,
  type SysRole, type SysMenu,
} from '@/api/admin'

const roles = ref<SysRole[]>([])
const loading = ref(false)

async function loadRoles() {
  loading.value = true
  try {
    const res: any = await getRoleList()
    roles.value = res.data || []
  } finally {
    loading.value = false
  }
}

// ===== 新增/编辑 =====
const formVisible = ref(false)
const editing = ref(false)
const saving = ref(false)
const form = ref<Partial<SysRole>>({})

function openCreate() {
  editing.value = false
  form.value = { roleName: '', roleCode: '', description: '', status: 0 }
  formVisible.value = true
}

function openEdit(row: SysRole) {
  editing.value = true
  form.value = { roleId: row.roleId, roleName: row.roleName, roleCode: row.roleCode, description: row.description }
  formVisible.value = true
}

async function saveRole() {
  if (!form.value.roleName || !form.value.roleCode) {
    ElMessage.warning('角色名称和编码不能为空')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await updateRole(form.value)
      ElMessage.success('已更新')
    } else {
      await createRole(form.value)
      ElMessage.success('已新增')
    }
    formVisible.value = false
    loadRoles()
  } finally {
    saving.value = false
  }
}

async function handleDelete(row: SysRole) {
  await ElMessageBox.confirm(`确认删除角色「${row.roleName}」？关联的菜单分配也会清除。`, '删除角色', { type: 'warning' })
  await deleteRole(row.roleId)
  ElMessage.success('已删除')
  loadRoles()
}

// ===== 分配菜单 =====
const assignVisible = ref(false)
const assignLoading = ref(false)
const assigning = ref(false)
const curRole = ref<SysRole | null>(null)
const menuTree = ref<any[]>([])
const treeRef = ref<InstanceType<typeof ElTree>>()

async function openAssign(row: SysRole) {
  curRole.value = row
  assignVisible.value = true
  assignLoading.value = true
  try {
    // 并行加载菜单树 + 当前角色已选菜单
    const [menuRes, idsRes]: any[] = await Promise.all([getAllMenus(), getRoleMenuIds(row.roleId)])
    menuTree.value = buildTree(menuRes.data || [])
    const checkedIds: number[] = idsRes.data || []
    // 仅勾选叶子菜单（菜单类型=1），避免父目录勾选导致全选
    nextTickSetChecked(checkedIds)
  } finally {
    assignLoading.value = false
  }
}

function nextTickSetChecked(ids: number[]) {
  // el-tree 渲染后设置勾选
  setTimeout(() => {
    treeRef.value?.setCheckedKeys(ids)
  }, 0)
}

/** 把平铺菜单列表按 parent_id 构建成树 */
function buildTree(menus: SysMenu[]): any[] {
  const map: Record<number, any> = {}
  const roots: any[] = []
  menus.forEach(m => { map[m.menuId] = { ...m, children: [] } })
  menus.forEach(m => {
    const node = map[m.menuId]
    if (m.parentId && map[m.parentId]) {
      map[m.parentId].children.push(node)
    } else {
      roots.push(node)
    }
  })
  return roots
}

async function saveAssign() {
  if (!curRole.value) return
  // 取勾选 + 半选的节点（半选的父目录也要保存，保证树结构完整）
  const checked = treeRef.value?.getCheckedKeys() as number[]
  const halfChecked = treeRef.value?.getHalfCheckedKeys() as number[]
  const allIds = [...(checked || []), ...(halfChecked || [])]
  assigning.value = true
  try {
    await assignRoleMenus(curRole.value.roleId, allIds)
    ElMessage.success('菜单分配已保存')
    assignVisible.value = false
  } finally {
    assigning.value = false
  }
}

onMounted(loadRoles)
</script>

<style scoped>
* { box-sizing: border-box; }
.role-page { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; }
.page-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-title { font-size: 15px; font-weight: 600; color: #1a1a1a; }
.table-card { background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 6px rgba(0,0,0,0.06); }
.form-tip { font-size: 12px; color: #999; line-height: 1.4; }
</style>
