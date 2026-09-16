<template>
  <div class="report-page">
    <div class="page-toolbar">
      <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width:160px" @change="loadList">
        <el-option label="全部" value="" />
        <el-option label="待处理" :value="0" />
        <el-option label="处理中" :value="1" />
        <el-option label="已忽略" :value="2" />
        <el-option label="已删帖" :value="3" />
        <el-option label="已转AI审核" :value="4" />
        <el-option label="已人工审核" :value="5" />
      </el-select>
    </div>

    <div class="table-card" v-if="list.length || loading">
      <el-table :data="list" v-loading="loading">
        <el-table-column prop="reportId" label="ID" width="70" />
        <el-table-column label="举报人" width="110">
          <template #default="{ row }">{{ nameOf(row.reporterUserId) }}</template>
        </el-table-column>
        <el-table-column label="举报对象" width="140">
          <template #default="{ row }">
            <span v-if="row.reportedCommentId">评论#{{ row.reportedCommentId }}</span>
            <span v-else-if="row.reportedPostId">帖子#{{ row.reportedPostId }}</span>
            <span v-else>{{ nameOf(row.reportedUserId) }}</span>
            <div v-if="row.reportedUserId" class="reported-user-sub">{{ nameOf(row.reportedUserId) }}</div>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="100">
          <template #default="{ row }">{{ categoryText(row.reportCategory) }}</template>
        </el-table-column>
        <el-table-column label="举报原因" min-width="180">
          <template #default="{ row }">
            <div class="reason-cell">
              <span class="reason-text" :title="row.reportReason">{{ row.reportReason || '—' }}</span>
              <el-tooltip content="下载完整证据(.txt)" placement="top">
                <el-icon class="download-icon" @click="downloadEvidence(row)"><Download /></el-icon>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" round>
              {{ statusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reviewNote" label="审核备注" show-overflow-tooltip min-width="160" />
        <el-table-column prop="createdTime" label="举报时间" width="160" />
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 0 || row.status === 1">
              <el-button link type="primary" size="small" :loading="auditingId === row.reportId"
                @click="handleAiModerate(row)">{{ row.status === 1 ? '等待AI结果' : 'AI审核' }}</el-button>
              <el-button link type="success" size="small" @click="openManualReview(row)">人工复核</el-button>
              <el-button link type="warning" size="small" @click="handleIgnore(row)">忽略</el-button>
            </template>
            <template v-else-if="row.status === 5">
              <span style="color:#999;font-size:12px">已人工审核</span>
            </template>
            <template v-else>
              <el-button link type="success" size="small" @click="openManualReview(row)">人工复核</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination background layout="prev, pager, next, total"
          :total="total" :page-size="20"
          v-model:current-page="pageNum" @current-change="loadList" />
      </div>
    </div>

    <div class="empty-state" v-else-if="!loading">
      <div class="empty-icon">📋</div>
      <p>暂无举报记录</p>
    </div>

    <!-- AI审核结果弹窗 -->
    <el-dialog v-model="resultDialogVisible" title="AI 审核结果" width="640px" align-center>
      <div v-if="moderateResult" class="result-body">
        <div class="result-row">
          <span class="rl-label">异常分数</span>
          <span class="rl-value">
            <el-progress :percentage="Math.round((moderateResult.anomalyScore || 0) * 100)"
              :color="scoreColor(moderateResult.anomalyScore)" :show-text="false" style="width:160px" />
            <b>{{ (moderateResult.anomalyScore || 0).toFixed(2) }}</b>
          </span>
        </div>
        <div class="result-row">
          <span class="rl-label">内容类型</span>
          <span class="rl-value">{{ moderateResult.contentType }}</span>
        </div>
        <div class="result-row">
          <span class="rl-label">处罚动作</span>
          <el-tag :type="actionTagType(moderateResult.action)" size="small" round>
            {{ actionText(moderateResult.action) }}
          </el-tag>
        </div>
        <div class="result-row" v-if="moderateResult.violatedRules?.length">
          <span class="rl-label">违反规则</span>
          <span class="rl-value">{{ moderateResult.violatedRules.join('；') }}</span>
        </div>
        <div class="result-row" v-if="moderateResult.violatedLaws?.length">
          <span class="rl-label">违反法律</span>
          <span class="rl-value">{{ moderateResult.violatedLaws.join('；') }}</span>
        </div>
        <div class="result-summary" v-if="moderateResult.evidenceSummary">
          <div class="rl-label">证据摘要</div>
          <p>{{ moderateResult.evidenceSummary }}</p>
        </div>
        <div class="result-detail" v-if="moderateResult.evidenceDetail">
          <div class="rl-label">完整证据报告</div>
          <pre class="evidence-pre">{{ moderateResult.evidenceDetail }}</pre>
        </div>
      </div>
      <template #footer>
        <el-button @click="resultDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 人工复核弹窗：上方被举报内容，下方AI审核结果，底部通过/禁言按钮 -->
    <el-dialog v-model="manualDialogVisible" title="人工复核" width="680px" align-center :close-on-click-modal="false">
      <div class="manual-body" v-loading="manualLoading">
        <!-- 被举报内容 -->
        <div class="manual-section">
          <div class="section-title">一、被举报内容</div>
          <div class="content-box">
            <template v-if="manualContent.type === 'comment'">
              <div class="content-meta">评论 #{{ manualReviewRow?.reportedCommentId }}</div>
              <div class="content-text">{{ manualContent.text || '（评论已删除或加载失败）' }}</div>
            </template>
            <template v-else-if="manualContent.type === 'post'">
              <div class="content-meta">帖子 #{{ manualReviewRow?.reportedPostId }}</div>
              <div class="content-text"><b>{{ manualContent.title }}</b></div>
              <div class="content-text">{{ manualContent.text }}</div>
            </template>
            <template v-else>
              <div class="content-text muted">（举报对象为用户，无具体内容）</div>
            </template>
          </div>
        </div>

        <!-- AI审核结果 -->
        <div class="manual-section">
          <div class="section-title">二、AI 审核结果</div>
          <div class="content-box">
            <template v-if="manualEvidence">
              <div class="evidence-line"><span class="ev-label">禁言天数：</span>{{ manualEvidence.muteDays }} 天</div>
              <div class="evidence-line"><span class="ev-label">禁言类型：</span>{{ manualEvidence.muteType === 0 ? 'AI自动' : '人工' }}</div>
              <div class="evidence-line"><span class="ev-label">禁言原因：</span>{{ manualEvidence.muteReason }}</div>
              <div class="evidence-line"><span class="ev-label">举报备注：</span>{{ manualReviewRow?.reviewNote || '—' }}</div>
              <div v-if="manualEvidence.evidenceDetail" class="evidence-detail-block">
                <div class="ev-label">完整证据报告：</div>
                <pre class="evidence-pre">{{ manualEvidence.evidenceDetail }}</pre>
              </div>
            </template>
            <template v-else>
              <div class="content-text muted">该举报尚未进行 AI 审核，请管理员根据上方内容自行判断。</div>
            </template>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="manualDialogVisible = false">取消</el-button>
        <el-button type="success" :loading="passing" @click="handleManualPass">通过</el-button>
        <el-button type="danger" :loading="muting" @click="openMuteDialog">禁言</el-button>
      </template>
    </el-dialog>

    <!-- 禁言时长选择弹窗 -->
    <el-dialog v-model="muteDialogVisible" title="选择禁言时长" width="380px" align-center :close-on-click-modal="false">
      <div class="mute-dialog-body">
        <div class="mute-target">被禁言用户：{{ nameOf(manualReviewRow?.reportedUserId) }}</div>
        <el-select v-model="muteDays" placeholder="请选择禁言时长" style="width:100%">
          <el-option label="3 天" :value="3" />
          <el-option label="7 天" :value="7" />
          <el-option label="15 天" :value="15" />
          <el-option label="30 天" :value="30" />
          <el-option label="3 个月" :value="90" />
          <el-option label="6 个月" :value="180" />
          <el-option label="1 年" :value="365" />
        </el-select>
      </div>
      <template #footer>
        <el-button @click="muteDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="muting" @click="confirmMute">确定禁言</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import http from '@/api/http'
import { getPostDetail } from '@/api/post'
import { useUserNames } from '@/api/user'
import {
  moderateReport,
  getModerateResult,
  getCommentDetail,
  getLatestMute,
  manualMuteUser,
  updateReportStatus,
  type ModerateResult,
} from '@/api/report'

const list = ref<any[]>([])
const total = ref(0)
const pageNum = ref(1)
const loading = ref(false)
const filterStatus = ref<any>('')

// AI审核中状态（按钮loading）
const auditingId = ref<number | null>(null)
// 审核结果弹窗
const resultDialogVisible = ref(false)
const moderateResult = ref<ModerateResult | null>(null)
const { loadNames, nameOf } = useUserNames()

async function loadList() {
  loading.value = true
  try {
    const status = filterStatus.value === '' ? undefined : filterStatus.value
    const res: any = await http.get('/content/reports', { params: { pageNum: pageNum.value, pageSize: 20, status } })
    list.value = res.data?.records || []
    total.value = res.data?.total || 0
    // 解析举报人 + 被举报用户昵称
    const ids: number[] = []
    for (const r of list.value) {
      if (r.reporterUserId) ids.push(r.reporterUserId)
      if (r.reportedUserId) ids.push(r.reportedUserId)
      if (r.reviewerUserId) ids.push(r.reviewerUserId)
    }
    loadNames(ids)
  } finally {
    loading.value = false
  }
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

// AI审核：POST 立即受理，再轮询 /result；处理中再次点击会续查同一 taskId
async function handleAiModerate(row: any) {
  if (row.status !== 1) {
    await ElMessageBox.confirm('确认对该举报触发 AI 审核？审核可能需要数十秒。', 'AI审核', { type: 'info' })
  }
  auditingId.value = row.reportId
  try {
    await moderateReport(row.reportId)
    const deadline = Date.now() + 120000
    while (Date.now() < deadline) {
      const res: any = await getModerateResult(row.reportId)
      const job = res.data
      if (job?.status === 'done') {
        moderateResult.value = job.result
        resultDialogVisible.value = true
        ElMessage.success('AI审核完成')
        loadList()
        return
      }
      if (job?.status === 'error') {
        ElMessage.error(job.error || 'AI审核失败')
        loadList()
        return
      }
      await sleep(2000)
    }
    ElMessage.warning('审核仍在进行，请稍后点「等待AI结果」查看')
    loadList()
  } finally {
    auditingId.value = null
  }
}

// 忽略举报：后端状态2=已忽略（用query param传status）
async function handleIgnore(row: any) {
  await ElMessageBox.confirm('确认忽略该举报？', '确认', { type: 'warning' })
  await http.put(`/content/reports/${row.reportId}`, null, { params: { status: 2 } })
  ElMessage.success('已忽略')
  loadList()
}

// ===== 人工复核 =====
const manualDialogVisible = ref(false)
const manualLoading = ref(false)
const manualReviewRow = ref<any>(null)
const manualContent = ref<{ type: string; title?: string; text?: string }>({ type: '' })
const manualEvidence = ref<any>(null)
const passing = ref(false)
const muting = ref(false)

// 禁言时长选择
const muteDialogVisible = ref(false)
const muteDays = ref(7)

// 打开人工复核弹窗：加载被举报内容 + AI审核证据
async function openManualReview(row: any) {
  manualReviewRow.value = row
  manualDialogVisible.value = true
  manualLoading.value = true
  manualContent.value = { type: '' }
  manualEvidence.value = null

  try {
    // 1. 加载被举报内容
    if (row.reportedCommentId) {
      const res: any = await getCommentDetail(row.reportedCommentId)
      const c = res.data
      manualContent.value = { type: 'comment', text: c?.content || '' }
    } else if (row.reportedPostId) {
      const res: any = await getPostDetail(row.reportedPostId)
      const p = res.data
      manualContent.value = { type: 'post', title: p?.title || '', text: p?.content || '' }
    } else {
      manualContent.value = { type: 'user' }
    }

    // 2. 加载该用户最新的禁言记录（含AI证据），并行加载
    if (row.reportedUserId) {
      try {
        const res2: any = await getLatestMute(row.reportedUserId)
        manualEvidence.value = res2.data || null
      } catch {
        manualEvidence.value = null
      }
    }
  } finally {
    manualLoading.value = false
  }
}

// 人工复核通过：举报状态置5（已人工审核）
async function handleManualPass() {
  if (!manualReviewRow.value) return
  await ElMessageBox.confirm('确认该举报复核通过（不处罚被举报用户）？', '人工复核', { type: 'info' })
  passing.value = true
  try {
    await updateReportStatus(manualReviewRow.value.reportId, 5, '人工复核通过，未处罚')
    ElMessage.success('已标记为人工复核通过')
    manualDialogVisible.value = false
    loadList()
  } finally {
    passing.value = false
  }
}

// 打开禁言时长选择弹窗
function openMuteDialog() {
  if (!manualReviewRow.value) return
  if (!manualReviewRow.value.reportedUserId) {
    ElMessage.warning('该举报没有被举报用户ID，无法禁言')
    return
  }
  muteDays.value = 7
  muteDialogVisible.value = true
}

// 确认禁言：调后端手动禁言接口 + 更新举报状态为5
async function confirmMute() {
  const row = manualReviewRow.value
  if (!row || !muteDays.value) return
  muting.value = true
  try {
    const reason = `人工复核禁言：${row.reportReason || categoryText(row.reportCategory)}`
    await manualMuteUser(row.reportedUserId, reason, muteDays.value, row.reportId)
    await updateReportStatus(row.reportId, 5, `人工复核禁言 ${muteDays.value} 天`)
    ElMessage.success(`已禁言用户 ${nameOf(row.reportedUserId)}，时长 ${muteDays.value} 天`)
    muteDialogVisible.value = false
    manualDialogVisible.value = false
    loadList()
  } finally {
    muting.value = false
  }
}

// 下载该举报的完整证据为 .txt 文件
function downloadEvidence(row: any) {
  const target = row.reportedCommentId
    ? `评论 #${row.reportedCommentId}`
    : row.reportedPostId
      ? `帖子 #${row.reportedPostId}`
      : `用户 #${row.reportedUserId}`

  const lines: string[] = []
  lines.push('================================================')
  lines.push('  ShillGuard 举报证据报告')
  lines.push('================================================')
  lines.push('')
  lines.push(`举报ID：${row.reportId}`)
  lines.push(`举报时间：${row.createdTime || '—'}`)
  lines.push(`举报人ID：${row.reporterUserId ?? '—'}（${nameOf(row.reporterUserId)}）`)
  lines.push(`被举报对象：${target}`)
  lines.push(`被举报用户ID：${row.reportedUserId ?? '—'}（${nameOf(row.reportedUserId)}）`)
  lines.push(`举报分类：${categoryText(row.reportCategory)}`)
  lines.push(`处理状态：${statusText(row.status)}`)
  lines.push(`审核人ID：${row.reviewerUserId ?? '—'}（${nameOf(row.reviewerUserId)}）`)
  lines.push('')
  lines.push('------------------------------------------------')
  lines.push('一、举报原因')
  lines.push('------------------------------------------------')
  lines.push(row.reportReason || '（未填写）')
  lines.push('')
  lines.push('------------------------------------------------')
  lines.push('二、AI 审核证据 / 审核备注')
  lines.push('------------------------------------------------')
  lines.push(row.reviewNote || '（暂无审核结果，请先进行 AI 审核）')
  lines.push('')
  lines.push('================================================')
  lines.push(`  报告生成时间：${new Date().toLocaleString('zh-CN')}`)
  lines.push('================================================')
  lines.push('')

  const content = lines.join('\n')
  // 加 BOM 头确保中文在记事本里不乱码
  const blob = new Blob(['\uFEFF' + content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `举报证据_${row.reportId}.txt`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  ElMessage.success('证据文件已下载')
}

// ===== 文案辅助 =====
function statusText(s: number) {
  return ({ 0: '待处理', 1: '处理中', 2: '已忽略', 3: '已删帖', 4: '已转AI审核', 5: '已人工审核' } as any)[s] || '未知'
}
function statusTagType(s: number) {
  return ({ 0: 'warning', 1: 'primary', 2: 'info', 3: 'danger', 4: 'success', 5: 'success' } as any)[s] || 'info'
}
function categoryText(c: number) {
  return ({ 0: '广告水军', 1: '违法信息', 2: '侮辱谩骂', 3: '色情低俗', 4: '其他' } as any)[c] || '其他'
}
function actionText(a: string) {
  return ({ none: '无违规', manual_review: '待人工复核', auto_mute: '自动禁言' } as any)[a] || a
}
function actionTagType(a: string) {
  return ({ none: 'info', manual_review: 'warning', auto_mute: 'danger' } as any)[a] || 'info'
}
function scoreColor(s: number) {
  if (s == null) return '#909399'
  if (s >= 0.8) return '#F56C6C'
  if (s >= 0.6) return '#E6A23C'
  return '#67C23A'
}

onMounted(loadList)
</script>

<style scoped>
* { box-sizing: border-box; }
.report-page { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; }
.page-toolbar { margin-bottom: 16px; }
.table-card { background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 6px rgba(0,0,0,0.06); }
.pagination-wrap { display: flex; justify-content: flex-end; padding: 16px 20px; }
.empty-state { text-align: center; padding: 80px; color: #999; }
.empty-icon { font-size: 60px; margin-bottom: 16px; }
.empty-state p { font-size: 15px; margin: 0; }

/* 举报原因单元格：文本 + 下载图标并排 */
.reason-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.reason-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: #333;
}
.download-icon {
  flex-shrink: 0;
  font-size: 16px;
  color: #909399;
  cursor: pointer;
  transition: color 0.2s;
}
.download-icon:hover { color: #FF2442; }

/* 举报对象单元格：内容引用 + 被举报用户昵称小字 */
.reported-user-sub {
  font-size: 11px;
  color: #999;
  margin-top: 2px;
}

/* AI审核结果弹窗 */
.result-body { padding: 0 4px; }
.result-row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid #F2F2F2; }
.rl-label { font-size: 13px; color: #999; min-width: 80px; flex-shrink: 0; }
.rl-value { font-size: 14px; color: #333; display: flex; align-items: center; gap: 8px; }
.result-summary { padding: 12px 0; }
.result-summary p { margin: 6px 0 0; font-size: 14px; color: #333; line-height: 1.6; }
.result-detail { padding: 12px 0; }
.evidence-pre {
  margin: 6px 0 0;
  padding: 12px;
  background: #F7F7F7;
  border-radius: 8px;
  font-size: 13px;
  color: #333;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
}

/* 人工复核弹窗 */
.manual-body { padding: 0 4px; }
.manual-section { margin-bottom: 18px; }
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a1a;
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid #FF2442;
}
.content-box {
  background: #F7F7F7;
  border-radius: 8px;
  padding: 12px 14px;
  max-height: 220px;
  overflow-y: auto;
}
.content-meta { font-size: 12px; color: #999; margin-bottom: 6px; }
.content-text {
  font-size: 14px;
  color: #333;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
.content-text.muted { color: #aaa; font-size: 13px; }
.evidence-line { font-size: 13px; color: #333; line-height: 1.8; }
.ev-label { color: #999; }
.evidence-detail-block { margin-top: 10px; }

/* 禁言时长选择弹窗 */
.mute-dialog-body { padding: 4px 0; }
.mute-target {
  font-size: 13px;
  color: #666;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #F7F7F7;
  border-radius: 8px;
}
</style>
