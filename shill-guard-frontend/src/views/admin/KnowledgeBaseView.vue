<template>
  <div class="kb-view">
    <el-card shadow="never" style="margin-bottom: 20px;">
      <template #header>
        <span class="card-title">上传文件到知识库</span>
      </template>

      <div
        class="upload-zone"
        :class="{ 'has-file': uploadStatus === 'success', 'uploading': uploadStatus === 'uploading' }"
        @click="triggerFileInput"
      >
        <el-icon :size="28" style="margin-bottom: 8px;"><Upload /></el-icon>
        <div>{{ uploadZoneText }}</div>
        <div style="font-size:12px;color:#bbb;margin-top:4px;">支持 PDF / DOCX / XLSX / PPTX / TXT / CSV / MD</div>
      </div>
      <input ref="fileInputRef" type="file" hidden @change="onFileSelected" />

      <div v-if="uploadMessage" class="upload-msg" :class="uploadStatus">{{ uploadMessage }}</div>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div style="display:flex; align-items:center; justify-content:space-between;">
          <span class="card-title">已索引文档</span>
          <el-button size="small" plain @click="loadDocList" :loading="tableLoading">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>

      <el-table :data="docList" v-loading="tableLoading" empty-text="知识库为空，请上传文档">
        <el-table-column prop="file" label="文件名" />
        <el-table-column prop="chunks" label="chunk 数" width="120" align="center" />
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button size="small" type="danger" plain @click="handleDelete(row.file)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="totalChunks > 0" class="total-hint">共 {{ totalChunks }} 个 chunk</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, Refresh } from '@element-plus/icons-vue'
import { getDocList, uploadToKb, deleteDoc, type KbDocument } from '@/api/ragAdmin'

const fileInputRef = ref<HTMLInputElement>()
const docList = ref<KbDocument[]>([])
const totalChunks = ref(0)
const tableLoading = ref(false)
const uploadStatus = ref<'' | 'uploading' | 'success' | 'error'>('')
const uploadMessage = ref('')
const uploadZoneText = ref('点击选择文件上传到知识库')

function triggerFileInput() {
  fileInputRef.value?.click()
}

async function onFileSelected() {
  const file = fileInputRef.value?.files?.[0]
  if (!file) return

  uploadZoneText.value = '正在上传：' + file.name
  uploadStatus.value = 'uploading'
  uploadMessage.value = ''

  try {
    const result = await uploadToKb(file)
    if (result.status === 'ok') {
      uploadStatus.value = 'success'
      uploadMessage.value = `✓ 上传成功：${result.file}，切分成 ${result.chunks} 块，共 ${result.total_chars} 字符`
      uploadZoneText.value = '点击继续上传'
      await loadDocList()
    } else {
      uploadStatus.value = 'error'
      uploadMessage.value = result.reason || '上传失败'
      uploadZoneText.value = '点击重新选择文件'
    }
  } catch (e: any) {
    uploadStatus.value = 'error'
    uploadMessage.value = '错误：' + e.message
    uploadZoneText.value = '点击重新选择文件'
  } finally {
    if (fileInputRef.value) fileInputRef.value.value = ''
  }
}

async function loadDocList() {
  tableLoading.value = true
  try {
    const data = await getDocList()
    docList.value = data.documents || []
    totalChunks.value = data.total_chunks || 0
  } catch (e: any) {
    ElMessage.error('加载文档列表失败：' + e.message)
  } finally {
    tableLoading.value = false
  }
}

async function handleDelete(filename: string) {
  try {
    await ElMessageBox.confirm(`确定删除「${filename}」？`, '确认删除', { type: 'warning' })
    await deleteDoc(filename)
    ElMessage.success('删除成功')
    await loadDocList()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('删除失败：' + e.message)
  }
}

onMounted(loadDocList)
</script>

<style scoped>
.kb-view { max-width: 900px; }
.card-title { font-size: 15px; font-weight: 600; }
.upload-zone {
  border: 2px dashed #ddd;
  border-radius: 8px;
  padding: 30px;
  text-align: center;
  color: #999;
  cursor: pointer;
  transition: all .2s;
  font-size: 14px;
}
.upload-zone:hover { border-color: #ff2442; color: #ff2442; }
.upload-zone.has-file { border-color: #67c23a; color: #67c23a; }
.upload-zone.uploading { border-color: #409eff; color: #409eff; }
.upload-msg { margin-top: 10px; font-size: 13px; }
.upload-msg.success { color: #67c23a; }
.upload-msg.error { color: #f56c6c; }
.upload-msg.uploading { color: #409eff; }
.total-hint { font-size: 12px; color: #999; margin-top: 10px; }
</style>
