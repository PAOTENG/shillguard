import http from './http'

// 当前用户信息（脱敏，不含密码）
export const getProfile = () => http.get('/user/me')

export const updateProfile = (data: { nickname?: string; avatarUrl?: string; phone?: string; email?: string }) =>
  http.put('/user/me', data)

export const getUserPosts = (userId: number, pageNum = 1, pageSize = 12) =>
  http.get(`/user/${userId}/posts`, { params: { pageNum, pageSize } })

export const getUserList = (pageNum = 1, pageSize = 20, keyword?: string) =>
  http.get('/user/list', { params: { pageNum, pageSize, keyword } })

// 公开搜索用户（按用户名/昵称模糊匹配），返回最多 20 条
export const searchUsers = (keyword: string) =>
  http.get('/user/search', { params: { keyword } })

export const updateUserStatus = (userId: number, status: number) =>
  http.put(`/user/${userId}/status`, { status })

// ===== 关注 =====
export const followUser = (targetId: number) => http.post(`/user/follow/${targetId}`)
export const unfollowUser = (targetId: number) => http.delete(`/user/follow/${targetId}`)
export const getMyFollowings = () => http.get('/user/followings')
export const getMyFollowers = () => http.get('/user/followers')

// 指定用户公开主页信息
export const getUserProfile = (userId: number) => http.get(`/user/profile/${userId}`)
// 指定用户统计（笔记/获赞/被收藏/被关注，含 isFollowing）
export const getUserStats = (userId: number) => http.get(`/user/stats/${userId}`)

/**
 * 批量获取用户昵称（管理端列表展示用）。
 * @param ids 用户ID数组
 * @returns { userId, nickname, username, avatarUrl, status } 列表
 */
export const getUserNames = (ids: number[]) =>
  http.get('/user/names', { params: { ids: ids.join(',') } })

/**
 * 把一批 userId 解析成 { id -> nickname } 的 map，供管理端表格把编号显示成昵称。
 * 调用方：const { nameMap, loadNames } = useUserNames(); loadNames([1,2,3]); nameMap.value[1]
 */
import { ref } from 'vue'
export function useUserNames() {
  const nameMap = ref<Record<number, { nickname: string; username: string; avatarUrl?: string; status?: number }>>({})
  async function loadNames(ids: number[]) {
    const uniq = Array.from(new Set(ids.filter(id => id != null && !nameMap.value[id])))
    if (!uniq.length) return
    try {
      const res: any = await getUserNames(uniq)
      const arr = res.data || []
      for (const u of arr) {
        nameMap.value[u.userId] = {
          nickname: u.nickname || u.username || `用户${u.userId}`,
          username: u.username || '',
          avatarUrl: u.avatarUrl,
          status: u.status,
        }
      }
    } catch {
      // 忽略，表格降级显示编号
    }
  }
  /** 取某用户的展示名（昵称优先，缺失则回退 用户#ID） */
  function nameOf(id: number | null | undefined): string {
    if (id == null) return '—'
    const u = nameMap.value[id]
    return u ? u.nickname : `用户#${id}`
  }
  return { nameMap, loadNames, nameOf }
}
