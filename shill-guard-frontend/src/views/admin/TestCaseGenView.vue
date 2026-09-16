<template>
  <div class="test-case-view">
    <el-card shadow="never">
      <template #header>
        <span class="card-title">测试用例生成</span>
        <span class="card-hint">上传文档，自动生成文档摘要 + 覆盖功能/边界/异常/业务规则的测试用例</span>
      </template>

      <div
        class="upload-zone"
        :class="{ 'has-file': !!selectedFile }"
        @click="triggerFileInput"
      >
        <el-icon :size="28" style="margin-bottom: 8px;"><Document /></el-icon>
        <div>{{ uploadZoneText }}</div>
        <div style="font-size:12px;color:#bbb;margin-top:4px;">支持 PDF / DOCX / XLSX / PPTX / TXT / CSV / MD</div>
      </div>
      <input ref="fileInputRef" type="file" hidden @change="onFileSelected" />

      <div v-if="selectedFile" class="file-info">
        文件：{{ selectedFile.name }}（{{ (selectedFile.size / 1024).toFixed(1) }} KB）
      </div>

      <el-button
        type="primary"
        :loading="loading"
        :disabled="!selectedFile"
        @click="handleGenerate"
        style="margin-top: 12px;"
      >
        生成测试用例
      </el-button>
      <span v-if="status" class="status-text" :class="{ done: status === '完成 ✓' }">{{ status }}</span>

      <div class="output-label">生成结果（流式）</div>
      <div class="test-output" ref="outputEl">{{ output || '（上传文件后点击按钮生成）' }}</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Document } from '@element-plus/icons-vue'
import { generateTests } from '@/api/ragAdmin'
import { useSSE } from '@/composables/useSSE'

const fileInputRef = ref<HTMLInputElement>()
const selectedFile = ref<File | null>(null)
const uploadZoneText = ref('点击选择要生成测试用例的文件')
const loading = ref(false)
const status = ref('')
const output = ref('')
const outputEl = ref<HTMLElement>()

const { readSSE } = useSSE()

function triggerFileInput() {
  fileInputRef.value?.click()
}

function onFileSelected() {
  const file = fileInputRef.value?.files?.[0]
  if (file) {
    selectedFile.value = file
    uploadZoneText.value = '已选择：' + file.name
  }
}

async function handleGenerate() {
  if (!selectedFile.value || loading.value) return
  loading.value = true
  status.value = '正在生成摘要和测试用例...'
  output.value = ''

  try {
    const resp = await generateTests(selectedFile.value)
    await readSSE(resp, {
      onDelta: (text) => {
        output.value += text
        if (outputEl.value) outputEl.value.scrollTop = outputEl.value.scrollHeight
      },
      onDone: () => { status.value = '完成 ✓' },
      onError: (msg) => { status.value = '错误：' + msg },
    })
    if (!status.value.includes('完成') && !status.value.includes('错误')) {
      status.value = '完成 ✓'
    }
  } catch (e: any) {
    status.value = '错误：' + e.message
    output.value += '\n[错误] ' + e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.test-case-view { max-width: 900px; }
.card-title { font-size: 15px; font-weight: 600; margin-right: 12px; }
.card-hint { font-size: 12px; color: #999; }
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
.file-info { font-size: 12px; color: #666; margin-top: 8px; }
.status-text { margin-left: 12px; font-size: 12px; color: #999; }
.status-text.done { color: #67c23a; }
.output-label { font-size: 13px; color: #666; margin: 16px 0 6px; }
.test-output {
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 6px;
  padding: 16px;
  min-height: 200px;
  max-height: 700px;
  overflow-y: auto;
  white-space: pre-wrap;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.6;
}
</style>
