import http from './http'

export const getPostList = (pageNum = 1, pageSize = 10, topicTag?: string, keyword?: string, userId?: number) =>
  http.get('/content/posts', { params: { pageNum, pageSize, topicTag, keyword, userId } })

export const getPostDetail = (postId: number) =>
  http.get(`/content/posts/${postId}`)

export const createPost = (data: any) =>
  http.post('/content/posts', data)

// 我的帖子（含审核中/审核不通过，供用户中心）
export const getMyPosts = (pageNum = 1, pageSize = 50) =>
  http.get('/content/posts/mine', { params: { pageNum, pageSize } })

export const deletePost = (postId: number) =>
  http.delete(`/content/posts/${postId}`)

export const likePost = (postId: number) =>
  http.post(`/content/posts/${postId}/like`)

export const unlikePost = (postId: number) =>
  http.delete(`/content/posts/${postId}/like`)

export const getComments = (postId: number, pageNum = 1, pageSize = 20) =>
  http.get(`/content/comments/post/${postId}`, { params: { pageNum, pageSize } })

export const addComment = (data: any) =>
  http.post('/content/comments', data)

export const deleteComment = (commentId: number) =>
  http.delete(`/content/comments/${commentId}`)

export const likeComment = (commentId: number) =>
  http.post(`/content/comments/${commentId}/like`)

export const unlikeComment = (commentId: number) =>
  http.delete(`/content/comments/${commentId}/like`)

export const getReplies = (commentId: number, pageNum = 1, pageSize = 20) =>
  http.get(`/content/comments/${commentId}/replies`, { params: { pageNum, pageSize } })
