<template>
  <div class="ai-chat-test">
    <el-card shadow="never">
      <template #header>
        <span class="card-title">对话测试</span>
        <span class="card-hint">测试 AI 助手的回答效果，支持流式输出与 Markdown 渲染</span>
      </template>

      <div class="form-row">
        <el-input
          v-model="message"
          placeholder="例如：怎么发笔记？最多能传几张图？"
          clearable
          @keyup.enter="handleSend"
        />
        <el-input
          v-model="threadId"
          placeholder="会话 ID（thread_id）"
          style="width: 220px; flex-shrink: 0;"
        />
      </div>

      <div class="file-row">
        <el-upload
          v-model:file-list="fileList"
          multiple
          :auto-upload="false"
          :show-file-list="true"
          action="#"
          class="file-upload"
        >
          <el-button size="small" plain>附加文档（可选）</el-button>
        </el-upload>
      </div>

      <el-button
        type="primary"
        :loading="loading"
        :disabled="!message.trim()"
        @click="handleSend"
        style="margin-top: 12px;"
      >
        发送
      </el-button>
      <span v-if="status" class="status-text" :class="{ done: status === '完成 ✓' }">{{ status }}</span>

      <div class="output-label">AI 回复（流式）</div>
      <div
        ref="outputEl"
        class="output markdown-body"
        v-html="renderedHtml || '<span class=\"placeholder\">（等待发送）</span>'"
      />

      <div class="hint-row">
        建议测试问题：
        <el-tag
          v-for="q in sampleQuestions" :key="q"
          size="small" type="info" style="cursor:pointer; margin: 2px;"
          @click="message = q"
        >{{ q }}</el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import { sendChatMessage } from '@/api/ragAdmin'
import { useSSE } from '@/composables/useSSE'

marked.use({
  gfm: true,
  breaks: true,
})

const message = ref('怎么发笔记？最多能传几张图？')
const threadId = ref('test_001')
const fileList = ref<any[]>([])
const loading = ref(false)
const status = ref('')
const fullText = ref('')
const renderedHtml = ref('')
const outputEl = ref<HTMLElement>()

const { readSSE } = useSSE()

const sampleQuestions = ['怎么发笔记', '忘记密码', '电子烟能带货吗', '粉丝多少能接广告', '怎么开直播', '笔记被误删怎么申诉']

function renderMd(text: string) {
  renderedHtml.value = marked.parse(text) as string
  nextTick(() => {
    outputEl.value?.querySelectorAll<HTMLElement>('pre code:not(.hljs)').forEach(b => hljs.highlightElement(b))
    if (outputEl.value) outputEl.value.scrollTop = outputEl.value.scrollHeight
  })
}

async function handleSend() {
  if (!message.value.trim() || loading.value) return
  loading.value = true
  status.value = '正在请求...'
  fullText.value = ''
  renderedHtml.value = ''

  try {
    const files = fileList.value.map((f: any) => f.raw as File).filter(Boolean)
    const resp = await sendChatMessage(message.value.trim(), threadId.value || 'default', files)

    await readSSE(resp, {
      onDelta: (text) => {
        fullText.value += text
        renderMd(fullText.value)
      },
      onDone: () => { status.value = '完成 ✓' },
      onError: (msg) => { status.value = '错误：' + msg },
    })

    if (!status.value.includes('完成') && !status.value.includes('错误')) {
      status.value = '完成 ✓'
    }
  } catch (e: any) {
    status.value = '错误：' + e.message
    renderedHtml.value = '<span style="color:#f56c6c">发生错误：' + e.message + '</span>'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.ai-chat-test { max-width: 900px; }
.card-title { font-size: 15px; font-weight: 600; margin-right: 12px; }
.card-hint { font-size: 12px; color: #999; }
.form-row { display: flex; gap: 12px; align-items: center; }
.file-row { margin-top: 10px; }
.file-upload { display: inline-block; }
.status-text { margin-left: 12px; font-size: 12px; color: #999; }
.status-text.done { color: #67c23a; }
.output-label { font-size: 13px; color: #666; margin: 16px 0 6px; }
.output {
  background: #fafafa;
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 14px;
  min-height: 140px;
  max-height: 600px;
  overflow-y: auto;
  font-size: 14px;
  line-height: 1.7;
}
.output :deep(.placeholder) { color: #ccc; }
.output :deep(p) { margin: 0 0 8px; }
.output :deep(p:last-child) { margin-bottom: 0; }
.output :deep(pre) {
  background: #f6f8fa;
  border: 1px solid #e1e4e8;
  border-radius: 6px;
  padding: 12px 16px;
  overflow-x: auto;
  margin: 8px 0;
}
.output :deep(pre code) { background: none; padding: 0; font-size: 13px; }
.output :deep(code) {
  background: #f0f0f0;
  padding: 2px 5px;
  border-radius: 3px;
  font-size: 13px;
  font-family: 'Consolas', 'Monaco', monospace;
}
.output :deep(ul), .output :deep(ol) { padding-left: 20px; margin: 4px 0 8px; }
.output :deep(li) { margin: 2px 0; }
.hint-row { margin-top: 12px; font-size: 12px; color: #999; }
</style>
