import { ref } from 'vue'
import { ElMessage } from 'element-plus'

/**
 * 聊天文件下载路径管理：
 * - 优先使用 File System Access API（showDirectoryPicker）让用户选择目录，
 *   句柄持久化到 IndexedDB，刷新后仍可用；下载时直接写入该目录。
 * - 浏览器不支持时回退为浏览器默认下载（<a download>）。
 * 注意：Web 环境无法强制指定系统级下载路径，此处提供“记住目录并写入”的最佳实现。
 */
const DB_NAME = 'shillguard-chat'
const STORE = 'kv'
const DIR_KEY = 'download-dir'
const DIR_NAME_KEY = 'download-dir-name'

const dirHandle = ref<FileSystemDirectoryHandle | null>(null)
const dirName = ref<string>('')
let inited = false

async function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) req.result.createObjectStore(STORE)
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function idbSet(key: string, val: any) {
  const db = await openDB()
  return new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).put(val, key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

async function idbGet<T = any>(key: string): Promise<T | undefined> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly')
    const r = tx.objectStore(STORE).get(key)
    r.onsuccess = () => resolve(r.result as T)
    r.onerror = () => reject(r.error)
  })
}

async function idbDel(key: string) {
  const db = await openDB()
  return new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).delete(key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

/** 启动时从 IndexedDB 恢复已保存的目录句柄与名称 */
async function init() {
  if (inited) return
  inited = true
  try {
    dirName.value = (await idbGet<string>(DIR_NAME_KEY)) || ''
    // 句柄恢复后需重新请求授权才能写
    const handle = (await idbGet<FileSystemDirectoryHandle>(DIR_KEY)) || null
    if (handle) {
      // @ts-expect-error requestPermission 是非标准但广泛实现的 API
      const perm = await handle.requestPermission?.({ mode: 'readwrite' })
      if (perm === 'granted') dirHandle.value = handle
    }
  } catch { /* 忽略 */ }
}

function supported() {
  return typeof (window as any).showDirectoryPicker === 'function'
}

/** 选择下载目录（浏览器会弹出目录选择器） */
async function chooseDir() {
  if (!supported()) {
    ElMessage.info('当前浏览器不支持选择下载目录，将使用浏览器默认下载')
    return
  }
  try {
    const handle = await (window as any).showDirectoryPicker({ mode: 'readwrite' })
    dirHandle.value = handle
    dirName.value = handle.name || '已选择的文件夹'
    await idbSet(DIR_KEY, handle)
    await idbSet(DIR_NAME_KEY, dirName.value)
    ElMessage.success(`已设置下载路径：${dirName.value}`)
  } catch (e: any) {
    if (e?.name !== 'AbortError') ElMessage.error('选择目录失败')
  }
}

/** 清除已保存的下载目录，回退为浏览器默认下载 */
async function clearDir() {
  dirHandle.value = null
  dirName.value = ''
  await idbDel(DIR_KEY)
  await idbDel(DIR_NAME_KEY)
  ElMessage.success('已恢复为浏览器默认下载')
}

/** 下载文件：优先写入已选目录，否则浏览器默认下载 */
async function downloadFile(url: string, filename: string) {
  const safeName = filename || 'download'
  try {
    if (dirHandle.value) {
      const fileRes = await fetch(url)
      const blob = await fileRes.blob()
      const fileHandle = await dirHandle.value.getFileHandle(safeName, { create: true })
      // @ts-expect-error createWritable 非标准但广泛实现
      const writable = await fileHandle.createWritable()
      await writable.write(blob)
      await writable.close()
      ElMessage.success(`已保存到：${dirName.value}/${safeName}`)
      return
    }
  } catch (e: any) {
    // 写入失败（如权限丢失），回退默认下载
    dirHandle.value = null
  }
  // 回退：浏览器默认下载
  const a = document.createElement('a')
  a.href = url
  a.download = safeName
  document.body.appendChild(a)
  a.click()
  a.remove()
}

export function useDownloadDir() {
  // 模块级单例，首次调用时初始化
  init()
  return {
    dirName,
    isSupported: supported,
    chooseDir,
    clearDir,
    downloadFile,
  }
}
