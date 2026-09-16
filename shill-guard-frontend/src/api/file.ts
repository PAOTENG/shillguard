import http from './http'

// 上传图片到 MinIO（shill-file 服务），返回可访问的图片 URL
export const uploadImage = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return http.post('/file/image', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 30000,
  })
}

// 上传视频到 MinIO，返回可访问的视频 URL
export const uploadVideo = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return http.post('/file/video', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

// 上传聊天文件到 MinIO（支持压缩包与常见文档，单文件≤50MB），返回可访问 URL
export const uploadChatFile = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return http.post('/file/chat-file', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

// 上传头像到 MinIO（shill-file 服务），返回可访问的头像 URL
export const uploadAvatar = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return http.post('/file/avatar', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 30000,
  })
}
