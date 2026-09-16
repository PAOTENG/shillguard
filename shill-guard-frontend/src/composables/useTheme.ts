import { ref } from 'vue'

const STORAGE_KEY = 'sg-theme'
type Theme = 'light' | 'dark'

const isDark = ref(false)

/** 读取本地存储并应用到 <html> 上，应在 app 启动时调用一次 */
export function initTheme() {
  const saved = (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? null
  const prefersDark =
    window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
  const dark = saved ? saved === 'dark' : prefersDark
  setDark(dark)
}

function setDark(dark: boolean) {
  isDark.value = dark
  const root = document.documentElement
  root.classList.toggle('dark', dark)
  // 与 Element Plus 的 meta 标记保持一致
  root.setAttribute('data-theme', dark ? 'dark' : 'light')
}

/** 切换深色/浅色模式，并持久化 */
export function toggleTheme() {
  const next = !isDark.value
  setDark(next)
  localStorage.setItem(STORAGE_KEY, next ? 'dark' : 'light')
}

export function useTheme() {
  return { isDark, toggleTheme }
}
