/**
 * useAiChatFile.ts
 * 跨组件共享的 AI 对话附件文件。
 * MainLayout 选文件 → 存这里 → SearchView 读取并发送 → 清空
 */
import { ref } from 'vue'

const pendingFile = ref<File | null>(null)

export function useAiChatFile() {
  const setFile = (f: File | null) => { pendingFile.value = f }
  const getFile = (): File | null => pendingFile.value
  const clearFile = () => { pendingFile.value = null }
  return { pendingFile, setFile, getFile, clearFile }
}
