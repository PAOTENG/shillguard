<template>
  <div class="dashboard">
    <!-- 数据卡片 -->
    <div class="stat-grid">
      <div class="stat-card" v-for="item in statCards" :key="item.label">
        <div class="stat-icon" :style="{ background: item.bg }">
          <el-icon :size="24" :color="item.color"><component :is="item.icon" /></el-icon>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ item.value }}</div>
          <div class="stat-label">{{ item.label }}</div>
        </div>
        <div class="stat-trend" :class="item.trend > 0 ? 'up' : 'neutral'">
          {{ item.trend > 0 ? `+${item.trend}` : '--' }}
        </div>
      </div>
    </div>

    <!-- Agent 检测控制 -->
    <div class="section-card detect-card">
      <div class="section-header">
        <div>
          <div class="section-title">🤖 AI Agent 实时检测</div>
          <div class="section-sub">收集今日所有帖子与评论，识别恶意行为用户（煽动情绪/网暴/辱骂等）</div>
        </div>
        <div style="display:flex;gap:8px">
          <el-button
            v-if="consoleLogs.length > 0 && !detecting"
            size="small" plain round @click="clearConsole"
          >清空日志</el-button>
          <el-button
            type="primary" round
            :loading="detecting"
            @click="triggerDetect"
            style="background:#FF2442;border-color:#FF2442;min-width:120px"
          >
            {{ detecting ? '检测中...' : '立即触发检测' }}
          </el-button>
        </div>
      </div>
      <div class="detect-steps">
        <div class="step" v-for="s in steps" :key="s.title">
          <div class="step-num">{{ s.num }}</div>
          <div class="step-info">
            <div class="step-title">{{ s.title }}</div>
            <div class="step-desc">{{ s.desc }}</div>
          </div>
        </div>
      </div>

      <!-- 实时控制台：流式显示后端处理日志 -->
      <div v-if="consoleLogs.length > 0" class="console-wrap">
        <div class="console-head">
          <span>🖥️ 后端实时日志</span>
          <span class="console-count">{{ consoleLogs.length }} 行</span>
        </div>
        <div ref="consoleBoxRef" class="console-box">
          <div
            v-for="(ln, i) in consoleLogs" :key="i"
            class="console-line"
            :class="'ln-' + ln.kind"
          >
            <span class="ln-time">{{ ln.time }}</span>
            <span class="ln-tag" v-if="ln.tag">[{{ ln.tag }}]</span>
            <span class="ln-msg">{{ ln.msg }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 最近禁言 -->
    <div class="section-card">
      <div class="section-header">
        <div class="section-title">🔴 最近禁言记录</div>
        <el-button text @click="router.push('/admin/mute')">查看全部 →</el-button>
      </div>
      <el-table :data="recentMutes" size="small" :show-header="true">
        <el-table-column label="用户" width="120">
          <template #default="{ row }">{{ nameOf(row.mutedUserId) }}</template>
        </el-table-column>
        <el-table-column prop="muteReason" label="禁言原因" show-overflow-tooltip />
        <el-table-column prop="muteType" label="类型" width="90">
          <template #default="{ row }">
            <el-tag :type="row.muteType === 0 ? 'danger' : 'warning'" size="small">
              {{ row.muteType === 0 ? 'Agent自动' : '人工' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="createdTime" label="时间" width="120" />
      </el-table>
      <div class="table-empty" v-if="!recentMutes.length">暂无禁言记录</div>
    </div>

    <!-- 检测结果弹窗 -->
    <el-dialog v-model="resultVisible" title="识别恶意行为用户 · 检测结果" width="720px">
      <div v-if="detectResult">
        <div class="result-summary">
          <div class="rs-item">检测用户：<b>{{ detectResult.totalUsers }}</b></div>
          <div class="rs-item rs-warn">预警：<b>{{ detectResult.warningCount }}</b></div>
          <div class="rs-item rs-danger">禁言：<b>{{ detectResult.mutedCount }}</b></div>
        </div>
        <el-table :data="detectResult.results" size="small" max-height="420">
          <el-table-column label="用户" width="120">
            <template #default="{ row }">{{ nameOf(row.userId) }}</template>
          </el-table-column>
          <el-table-column label="异常分数" width="100">
            <template #default="{ row }">
              <span :style="{ color: scoreColor(row.anomalyScore), fontWeight: 600 }">
                {{ row.anomalyScore?.toFixed(3) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="级别" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.anomalyScore >= 0.9" type="danger" size="small">高危·禁言7天</el-tag>
              <el-tag v-else-if="row.anomalyScore > 0.8" type="warning" size="small">预警</el-tag>
              <el-tag v-else type="info" size="small">正常</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="contentType" label="类型" width="100" />
          <el-table-column prop="evidenceSummary" label="证据摘要" show-overflow-tooltip />
          <el-table-column label="证据" width="90" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.anomalyScore >= 0.9 && row.evidenceDetail"
                link type="danger" size="small"
                @click="openEvidence(row)"
              >查看证据</el-button>
              <span v-else style="color:#ccc;font-size:12px">--</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div v-else style="text-align:center;color:#999;padding:20px">无检测结果</div>
      <template #footer>
        <el-button @click="resultVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 证据详情弹窗 -->
    <el-dialog v-model="evidenceVisible" :title="`完整证据报告 - ${nameOf(curEvidenceUser?.userId)}`" width="760px" align-center>
      <div v-if="curEvidenceUser" style="max-height:60vh;overflow:auto">
        <div style="margin-bottom:12px;color:#666;font-size:13px">
          异常分数：<b :style="{color: scoreColor(curEvidenceUser.anomalyScore)}">{{ curEvidenceUser.anomalyScore?.toFixed(3) }}</b>
        </div>
        <pre style="white-space:pre-wrap;word-break:break-word;background:#F8F8F8;padding:16px;border-radius:8px;font-size:13px;line-height:1.7;font-family:inherit">{{ curEvidenceUser.evidenceDetail }}</pre>
        <div v-if="curEvidenceUser.violatingItems?.length" style="margin-top:16px">
          <div style="font-weight:600;margin-bottom:8px;color:#FF2442">具体违规内容</div>
          <div v-for="(item, i) in curEvidenceUser.violatingItems" :key="i" style="background:#FFF5F5;padding:10px;border-radius:6px;margin-bottom:6px;font-size:13px;border-left:3px solid #FF2442">
            {{ item }}
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="evidenceVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, ChatDotSquare, Warning } from '@element-plus/icons-vue'
import { triggerDetectStream, getMuteList } from '@/api/agent'
import { useUserNames } from '@/api/user'

const router = useRouter()
const detecting = ref(false)
const recentMutes = ref<any[]>([])
const resultVisible = ref(false)
const detectResult = ref<any>(null)
const evidenceVisible = ref(false)
const curEvidenceUser = ref<any>(null)
const { loadNames, nameOf } = useUserNames()

// 实时控制台日志
interface ConsoleLine {
  time: string
  kind: 'log' | 'stage' | 'score' | 'action' | 'done' | 'error'
  tag: string
  msg: string
}
const consoleLogs = ref<ConsoleLine[]>([])
const consoleBoxRef = ref<HTMLElement | null>(null)

function nowStr() {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function pushLog(kind: ConsoleLine['kind'], tag: string, msg: string) {
  consoleLogs.value.push({ time: nowStr(), kind, tag, msg })
  nextTick(() => {
    const box = consoleBoxRef.value
    if (box) box.scrollTop = box.scrollHeight
  })
}

function clearConsole() {
  consoleLogs.value = []
}

function scoreColor(s: number) {
  if (s >= 0.9) return '#FF2442'
  if (s > 0.8) return '#e6a23c'
  return '#67c23a'
}

function openEvidence(row: any) {
  curEvidenceUser.value = row
  evidenceVisible.value = true
}

const statCards = ref([
  { label: '禁言用户', value: '--', icon: User, color: '#FF2442', bg: 'rgba(255,36,66,0.1)', trend: 0 },
  { label: '今日新增', value: '--', icon: ChatDotSquare, color: '#67c23a', bg: 'rgba(103,194,58,0.1)', trend: 0 },
  { label: '待处理', value: '--', icon: Warning, color: '#e6a23c', bg: 'rgba(230,162,60,0.1)', trend: 0 },
])

const steps = [
  { num: '1', title: '收集今日内容', desc: '抓取平台所有用户今日帖子与评论' },
  { num: '2', title: '识别恶意行为用户', desc: '基于RAG对比法律法规，计算每用户异常分数' },
  { num: '3', title: '分级处置', desc: '预警标记 / 高危自动禁言7天并生成证据' },
]

// 处理一条 SSE 事件，写入控制台 + 汇总结果
function handleEvent(event: string, data: any) {
  switch (event) {
    case 'stage': {
      const stage = data?.stage || ''
      const msg = data?.msg || ''
      pushLog('stage', stage, msg)
      break
    }
    case 'log': {
      const src = data?.source || 'python'
      const lvl = data?.level === 'error' ? 'error' : 'log'
      const uid = data?.userId != null ? `用户${data.userId}` : ''
      const tag = uid ? `${src}:${uid}` : src
      pushLog(lvl as any, tag, data?.msg || '')
      break
    }
    case 'score': {
      const uid = data?.userId
      const score = data?.anomalyScore
      const idx = data?.index
      const total = data?.total
      const sc = score != null ? Number(score).toFixed(3) : '?'
      const extra = data?.skipped ? '（无内容，跳过）'
        : data?.error ? '（打分失败）'
        : `类型=${data?.contentType || '-'} 违规法条${data?.violatedLaws?.length || 0}条`
      const emoji = score >= 0.9 ? '🔴' : score > 0.8 ? '🟡' : '🟢'
      pushLog('score', `${idx}/${total}`,
        `${emoji} 用户${uid} 异常分数=${sc} ${extra}`)
      break
    }
    case 'action': {
      const uid = data?.userId
      const act = data?.action
      const score = data?.score
      const sc = score != null ? Number(score).toFixed(3) : '?'
      const kind = act === 'mute' ? 'action' : 'action'
      pushLog(kind as any, act,
        `用户${uid} ${act === 'mute' ? '禁言' + (data?.days || 7) + '天' : '预警'} 分数=${sc} — ${data?.msg || ''}`)
      break
    }
    case 'done': {
      const t = data?.totalUsers ?? '?'
      const w = data?.warningCount ?? '?'
      const m = data?.mutedCount ?? '?'
      pushLog('done', '完成', `检测结束：共${t}人，预警${w}人，禁言${m}人`)
      detectResult.value = data
      resultVisible.value = true
      if (data) {
        ElMessage.success(`检测完成：预警 ${data.warningCount} 人，禁言 ${data.mutedCount} 人`)
        // 解析检测结果中的用户昵称
        loadNames((data.results || []).map((r: any) => r.userId).filter(Boolean))
      }
      loadRecentMutes()
      break
    }
    case 'error': {
      pushLog('error', 'error', data?.msg || '检测异常')
      break
    }
    default:
      if (typeof data === 'string') pushLog('log', event, data)
  }
}

async function triggerDetect() {
  if (detecting.value) return
  detecting.value = true
  clearConsole()
  pushLog('stage', '开始', '点击触发检测，建立流式连接...')
  try {
    await triggerDetectStream(handleEvent)
  } catch (e: any) {
    pushLog('error', 'error', '检测失败：' + (e?.message || '服务异常'))
    ElMessage.error('检测失败：' + (e?.message || '服务异常'))
  } finally {
    detecting.value = false
  }
}

async function loadRecentMutes() {
  try {
    const res: any = await getMuteList(1, 5)
    recentMutes.value = res.data?.records || []
    statCards.value[0].value = String(recentMutes.value.filter((m: any) => m.status === 1).length)
    loadNames(recentMutes.value.map((m: any) => m.mutedUserId).filter(Boolean))
  } catch {}
}

onMounted(loadRecentMutes)
</script>

<style scoped>
* { box-sizing: border-box; }
.dashboard { display: flex; flex-direction: column; gap: 20px; font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; }
.stat-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.stat-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 1px 6px rgba(0,0,0,0.06);
}
.stat-icon { width: 52px; height: 52px; border-radius: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.stat-value { font-size: 26px; font-weight: 700; color: #1a1a1a; line-height: 1; }
.stat-label { font-size: 13px; color: #999; margin-top: 4px; }
.stat-trend { margin-left: auto; font-size: 13px; color: #ccc; }
.stat-trend.up { color: #67c23a; }

.section-card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 1px 6px rgba(0,0,0,0.06); }
.detect-card { border-left: 4px solid #FF2442; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.section-title { font-size: 15px; font-weight: 700; color: #1a1a1a; }
.section-sub { font-size: 13px; color: #999; margin-top: 3px; }

.detect-steps { display: flex; gap: 16px; }
.step { flex: 1; display: flex; gap: 12px; background: #F8F8F8; padding: 14px; border-radius: 10px; }
.step-num { width: 28px; height: 28px; border-radius: 50%; background: #FF2442; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; flex-shrink: 0; }
.step-title { font-size: 13px; font-weight: 600; color: #1a1a1a; margin-bottom: 3px; }
.step-desc { font-size: 12px; color: #999; }
.table-empty { text-align: center; color: #ccc; padding: 20px; font-size: 13px; }
.result-summary { display: flex; gap: 24px; padding: 12px 16px; background: #F8F8F8; border-radius: 8px; margin-bottom: 12px; font-size: 14px; }
.rs-item { color: #555; }
.rs-warn b { color: #e6a23c; }
.rs-danger b { color: #FF2442; }

/* 实时控制台 */
.console-wrap { margin-top: 16px; border: 1px solid #2b2b2b; border-radius: 10px; overflow: hidden; }
.console-head {
  display: flex; justify-content: space-between; align-items: center;
  background: #1e1e1e; color: #d4d4d4; font-size: 12px; padding: 8px 14px;
  border-bottom: 1px solid #333;
}
.console-count { color: #888; }
.console-box {
  background: #1e1e1e; color: #d4d4d4; font-family: 'Consolas','Menlo','Courier New',monospace;
  font-size: 12.5px; line-height: 1.7; padding: 12px 14px; max-height: 360px; overflow-y: auto;
}
.console-box::-webkit-scrollbar { width: 8px; }
.console-box::-webkit-scrollbar-thumb { background: #444; border-radius: 4px; }
.console-line { white-space: pre-wrap; word-break: break-word; }
.ln-time { color: #6a6a6a; margin-right: 8px; }
.ln-tag { color: #569cd6; margin-right: 8px; }
.ln-msg { color: #d4d4d4; }
.ln-log .ln-msg { color: #b0b0b0; }
.ln-stage .ln-tag { color: #4ec9b0; }
.ln-stage .ln-msg { color: #4ec9b0; font-weight: 600; }
.ln-score .ln-msg { color: #dcdcaa; }
.ln-action .ln-tag { color: #e6a23c; }
.ln-action .ln-msg { color: #e6a23c; font-weight: 600; }
.ln-done .ln-tag { color: #67c23a; }
.ln-done .ln-msg { color: #67c23a; font-weight: 700; }
.ln-error .ln-tag { color: #FF2442; }
.ln-error .ln-msg { color: #FF2442; }
</style>
