import http from './http'

// ===== 收藏夹 =====
export const listFolders = () => http.get('/content/favorites/folders')

export const createFolder = (name: string) =>
  http.post('/content/favorites/folders', null, { params: { name } })

export const deleteFolder = (folderId: number) =>
  http.delete(`/content/favorites/folders/${folderId}`)

// ===== 收藏 / 取消收藏 =====
export const favoritePost = (postId: number, folderId?: number) =>
  http.post('/content/favorites', null, { params: { postId, folderId } })

export const unfavoritePost = (postId: number) =>
  http.delete(`/content/favorites/${postId}`)

// 我的收藏记录（完整帖子分页）
export const getFavoritePosts = (pageNum = 1, pageSize = 20) =>
  http.get('/content/favorites/posts', { params: { pageNum, pageSize } })

// ===== 浏览 / 点赞记录 =====
export const getViewHistory = (pageNum = 1, pageSize = 20) =>
  http.get('/content/history/views', { params: { pageNum, pageSize } })

export const getLikedPosts = (pageNum = 1, pageSize = 20) =>
  http.get('/content/history/likes', { params: { pageNum, pageSize } })
