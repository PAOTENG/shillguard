import http from './http'

export interface LoginParams {
  username: string
  password: string
}

export interface RegisterParams {
  username: string
  password: string
  nickname?: string
  phone?: string
  email?: string
}

export interface LoginResult {
  userId: number
  username: string
  nickname: string
  avatarUrl: string
  role: number
  token: string
  expireIn: number
}

export const login = (params: LoginParams) =>
  http.post<any, { data: LoginResult }>('/auth/login', params)

export const register = (params: RegisterParams) =>
  http.post('/auth/register', params)

export const logout = () =>
  http.post('/auth/logout')

// 发送登录验证码（仅手机号/邮箱）。邮件 SMTP 投递较慢，单独放宽到 30s
export const sendCode = (identifier: string) =>
  http.post('/auth/send-code', { identifier }, { timeout: 30000 })

// 自动登录（账号/手机/邮箱 + 密码 + 验证码，长有效期）
export const autoLogin = (params: { identifier: string; password: string; code: string }) =>
  http.post<any, { data: LoginResult }>('/auth/auto-login', params)
