import http from './http'

// ==================== 帖子 / 视频管理 ====================

/** 帖子/视频分页（管理员，全量含已删除） */
export const getPostList = (params: {
  pageNum?: number
  pageSize?: number
  status?: number
  postType?: number
  keyword?: string
}) => http.get('/admin/posts', { params })

/** 设置帖子状态（0=正常 1=已删除） */
export const setPostStatus = (postId: number, status: number) =>
  http.put(`/admin/posts/${postId}/status`, null, { params: { status } })

// ==================== 用户管理 ====================

/** 用户分页（管理员，密码脱敏，可按角色/状态过滤） */
export const getAdminUserList = (params: {
  pageNum?: number
  pageSize?: number
  keyword?: string
  role?: number
  status?: number
}) => http.get('/admin/users', { params })

/** 修改用户角色（0=普通 1=审核员 2=管理员 3=超管） */
export const updateUserRole = (userId: number, role: number) =>
  http.put(`/admin/users/${userId}/role`, null, { params: { role } })

/** 修改用户状态（0=正常 1=禁言 2=封号） */
export const updateUserStatus = (userId: number, status: number) =>
  http.put(`/admin/users/${userId}/status`, null, { params: { status } })

/** 重置用户密码为 123456 */
export const resetUserPassword = (userId: number) =>
  http.put(`/admin/users/${userId}/password/reset`)

// ==================== 角色权限 (RBAC) ====================

export interface SysRole {
  roleId: number
  roleName: string
  roleCode: string
  description?: string
  status: number
  createdTime?: string
}

export interface SysMenu {
  menuId: number
  parentId: number
  menuName: string
  menuType: number
  path?: string
  component?: string
  perms?: string
  icon?: string
  sort: number
  status: number
}

/** 角色列表 */
export const getRoleList = () => http.get('/admin/roles')

/** 新增角色 */
export const createRole = (data: Partial<SysRole>) => http.post('/admin/roles', data)

/** 更新角色 */
export const updateRole = (data: Partial<SysRole>) => http.put('/admin/roles', data)

/** 删除角色（预置0-3不可删） */
export const deleteRole = (roleId: number) => http.delete(`/admin/roles/${roleId}`)

/** 全部菜单列表 */
export const getAllMenus = () => http.get('/admin/roles/menus')

/** 某角色已分配的菜单ID */
export const getRoleMenuIds = (roleId: number) => http.get(`/admin/roles/${roleId}/menus`)

/** 为角色分配菜单（全量覆盖） */
export const assignRoleMenus = (roleId: number, menuIds: number[]) =>
  http.put(`/admin/roles/${roleId}/menus`, menuIds)
