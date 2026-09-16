import { defineStore } from 'pinia'
import { ref } from 'vue'

interface UserInfo {
  userId: number
  username: string
  nickname: string
  avatarUrl: string
  role: number
}

export const useUserStore = defineStore('user', () => {
  const storedUser = localStorage.getItem('userInfo')
  const userInfo = ref<UserInfo | null>(storedUser ? JSON.parse(storedUser) : null)
  const token = ref<string>(localStorage.getItem('token') || '')

  function setUser(info: UserInfo) {
    userInfo.value = info
    localStorage.setItem('userInfo', JSON.stringify(info))
  }

  function setToken(t: string) {
    token.value = t
    localStorage.setItem('token', t)
  }

  function clear() {
    userInfo.value = null
    token.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
  }

  const isLoggedIn = () => !!token.value
  const isAdmin = () => (userInfo.value?.role ?? 0) >= 2

  return { userInfo, token, setUser, setToken, clear, isLoggedIn, isAdmin }
})
