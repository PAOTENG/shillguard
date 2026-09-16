<template>
  <div class="policy-agent">

    <!-- ── 顶部模块选择 ── -->
    <div class="module-tabs">
      <div v-for="mod in modules" :key="mod.key"
           class="module-tab" :class="{ active: activeModule === mod.key }"
           @click="switchModule(mod.key)">
        <span class="mod-icon">{{ mod.emoji }}</span>
        <span class="mod-label">{{ mod.label }}</span>
        <span class="mod-desc">{{ mod.desc }}</span>
      </div>
      <!-- 历史记录入口 -->
      <div class="history-btn" @click="showHistory = !showHistory" :class="{ active: showHistory }">
        <span class="mod-icon">🕐</span>
        <span class="mod-label">历史报告</span>
        <span class="mod-desc">{{ historyList.length }} 条</span>
      </div>
    </div>

    <div class="agent-body">

      <!-- ══════════════════════════════════════════
           历史记录抽屉（全宽覆盖，点击外部关闭）
      ══════════════════════════════════════════ -->
      <Transition name="history-slide">
        <div v-if="showHistory" class="history-panel" @click.self="showHistory = false">
          <div class="history-inner">
            <div class="history-header">
              <span class="history-title">历史报告</span>
              <button class="history-close" @click="showHistory = false">×</button>
            </div>
            <div class="history-scroll">
              <div v-if="!historyList.length" class="history-empty">暂无历史记录</div>
              <div v-for="item in historyList" :key="item.id"
                   class="history-item" @click="restoreHistory(item)">
                <div class="hi-module">{{ modules.find(m => m.key === item.module)?.emoji }} {{ modules.find(m => m.key === item.module)?.label }}</div>
                <div class="hi-title">{{ item.title }}</div>
                <div class="hi-time">{{ formatTime(item.timestamp) }}</div>
              </div>
            </div>
          </div>
        </div>
      </Transition>

      <!-- ══════════════════════════════════════════
           左侧：政策分类漏斗
      ══════════════════════════════════════════ -->
      <div class="funnel-panel">
        <div class="panel-header">
          <span class="panel-title">🔍 政策筛选</span>
          <el-button text size="small" @click="resetAll">全部重置</el-button>
        </div>

        <!-- 适用地区 [必填] -->
        <div class="funnel-block">
          <div class="block-label required">📍 适用地区</div>
          <div class="chip-group">
            <div v-for="r in regionList" :key="r"
                 class="chip" :class="{ selected: policy.region === r, required: !policy.region && submitted }"
                 @click="policy.region = policy.region === r ? '' : r">{{ r }}</div>
          </div>
          <div v-if="submitted && !policy.region" class="err-tip">请选择地区</div>
        </div>

        <!-- 政策大类 [必填] -->
        <div class="funnel-block">
          <div class="block-label required">📂 政策大类</div>
          <div class="chip-group">
            <div v-for="cat in policyTree[activeModule]" :key="cat.key"
                 class="chip" :class="{ selected: policy.l1 === cat.key }"
                 @click="selectL1(cat.key)">{{ cat.label }}</div>
          </div>
          <div v-if="submitted && !policy.l1" class="err-tip">请选择政策大类</div>
        </div>

        <!-- 二级分类 -->
        <transition name="slide-down">
          <div v-if="currentL2.length" class="funnel-block">
            <div class="block-label">📌 细分方向</div>
            <div class="chip-group">
              <div v-for="sub in currentL2" :key="sub.key"
                   class="chip" :class="{ selected: policy.l2 === sub.key }"
                   @click="selectL2(sub.key)">{{ sub.label }}</div>
            </div>
          </div>
        </transition>

        <!-- 三级分类 -->
        <transition name="slide-down">
          <div v-if="currentL3.length" class="funnel-block">
            <div class="block-label">🔖 申报类型</div>
            <div class="chip-group">
              <div v-for="item in currentL3" :key="item.key"
                   class="chip" :class="{ selected: policy.l3 === item.key }"
                   @click="policy.l3 = policy.l3 === item.key ? '' : item.key">{{ item.label }}</div>
            </div>
          </div>
        </transition>

        <!-- 已选摘要 -->
        <div v-if="policyTagList.length" class="selected-summary">
          <div class="block-label">✅ 已选条件</div>
          <div class="tag-row">
            <el-tag v-for="t in policyTagList" :key="t.key" closable size="small"
                    type="primary" @close="clearPolicyTag(t.key)">{{ t.val }}</el-tag>
          </div>
        </div>
      </div>

      <!-- ══════════════════════════════════════════
           右侧：企业信息表单 + 报告输出
      ══════════════════════════════════════════ -->
      <div class="right-panel">

        <!-- 企业信息卡片 -->
        <div class="form-card" :class="{ 'form-card--collapsed': formCollapsed }">
          <!-- 卡片头部（始终可见） -->
          <div class="form-card-header" @click="formCollapsed && toggleFormCollapse()">
            <div class="form-title-group">
              <span class="form-title">🏢 企业信息</span>
              <!-- 折叠后展示已选摘要 -->
              <transition name="fade">
                <div v-if="formCollapsed && collapsedSummaryTags.length" class="collapsed-summary">
                  <span v-for="tag in collapsedSummaryTags" :key="tag" class="csummary-tag">{{ tag }}</span>
                </div>
              </transition>
            </div>
            <div class="header-right">
              <span v-if="!formCollapsed" class="form-hint">
                标 <span class="req-star">*</span> 为必填
              </span>
              <!-- 折叠/展开箭头 -->
              <button class="collapse-btn" @click.stop="toggleFormCollapse" :title="formCollapsed ? '展开企业信息' : '折叠企业信息'">
                <svg class="chevron-icon" :class="{ 'chevron-up': !formCollapsed }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>
            </div>
          </div>

          <!-- 折叠内容区 -->
          <div class="form-body" :class="{ 'form-body--hidden': formCollapsed }">
          <div class="form-grid">

            <!-- Section 1: 基础信息 -->
            <div class="form-section-label">基础信息</div>

            <!-- 公司类型 [必填] -->
            <div class="form-row">
              <div class="form-field-label required">公司类型</div>
              <div class="chip-group">
                <div v-for="t in companyTypes" :key="t"
                     class="chip sm" :class="{ selected: enterprise.type === t }"
                     @click="enterprise.type = enterprise.type === t ? '' : t">{{ t }}</div>
              </div>
              <div v-if="submitted && !enterprise.type" class="err-tip">请选择公司类型</div>
            </div>

            <!-- 企业规模 [必填] -->
            <div class="form-row">
              <div class="form-field-label required">企业规模（人数）</div>
              <div class="chip-group">
                <div v-for="s in companySizes" :key="s.val"
                     class="chip sm" :class="{ selected: enterprise.size === s.val }"
                     @click="enterprise.size = enterprise.size === s.val ? '' : s.val">{{ s.label }}</div>
              </div>
              <div v-if="submitted && !enterprise.size" class="err-tip">请选择企业规模</div>
            </div>

            <!-- 主营行业 [必填] -->
            <div class="form-row">
              <div class="form-field-label required">主营行业</div>
              <div class="chip-group">
                <div v-for="ind in industries" :key="ind"
                     class="chip sm" :class="{ selected: enterprise.industry === ind }"
                     @click="enterprise.industry = enterprise.industry === ind ? '' : ind">{{ ind }}</div>
              </div>
              <div v-if="submitted && !enterprise.industry" class="err-tip">请选择主营行业</div>
            </div>

            <!-- Section 2: 经营状况 -->
            <div class="form-section-label">经营状况</div>

            <!-- 成立年限 -->
            <div class="form-row">
              <div class="form-field-label">成立年限</div>
              <div class="chip-group">
                <div v-for="y in foundedYears" :key="y"
                     class="chip sm" :class="{ selected: enterprise.founded === y }"
                     @click="enterprise.founded = enterprise.founded === y ? '' : y">{{ y }}</div>
              </div>
            </div>

            <!-- 年营业收入 -->
            <div class="form-row">
              <div class="form-field-label">年营业收入</div>
              <div class="chip-group">
                <div v-for="r in revenueRanges" :key="r"
                     class="chip sm" :class="{ selected: enterprise.revenue === r }"
                     @click="enterprise.revenue = enterprise.revenue === r ? '' : r">{{ r }}</div>
              </div>
            </div>

            <!-- 注册资本 -->
            <div class="form-row">
              <div class="form-field-label">注册资本</div>
              <div class="chip-group">
                <div v-for="c in capitalRanges" :key="c"
                     class="chip sm" :class="{ selected: enterprise.capital === c }"
                     @click="enterprise.capital = enterprise.capital === c ? '' : c">{{ c }}</div>
              </div>
            </div>

            <!-- 是否上市 -->
            <div class="form-row">
              <div class="form-field-label">上市状态</div>
              <div class="chip-group">
                <div v-for="s in listedStatus" :key="s"
                     class="chip sm" :class="{ selected: enterprise.listed === s }"
                     @click="enterprise.listed = enterprise.listed === s ? '' : s">{{ s }}</div>
              </div>
            </div>

            <!-- Section 3: 创新能力 -->
            <div class="form-section-label">创新能力</div>

            <!-- 研发投入占比 -->
            <div class="form-row">
              <div class="form-field-label">研发投入占营收比</div>
              <div class="chip-group">
                <div v-for="r in rdRatios" :key="r"
                     class="chip sm" :class="{ selected: enterprise.rdRatio === r }"
                     @click="enterprise.rdRatio = enterprise.rdRatio === r ? '' : r">{{ r }}</div>
              </div>
            </div>

            <!-- 研发人员占比 -->
            <div class="form-row">
              <div class="form-field-label">研发人员占比</div>
              <div class="chip-group">
                <div v-for="r in rdPersonRatios" :key="r"
                     class="chip sm" :class="{ selected: enterprise.rdPerson === r }"
                     @click="enterprise.rdPerson = enterprise.rdPerson === r ? '' : r">{{ r }}</div>
              </div>
            </div>

            <!-- 已持有资质 -->
            <div class="form-row">
              <div class="form-field-label">已持有资质（可多选）</div>
              <div class="chip-group">
                <div v-for="q in qualifications" :key="q"
                     class="chip sm" :class="{ selected: enterprise.quals.includes(q) }"
                     @click="toggleQual(q)">{{ q }}</div>
              </div>
            </div>

            <!-- 核心技术方向 -->
            <div class="form-row">
              <div class="form-field-label">核心技术方向（可多选）</div>
              <div class="chip-group">
                <div v-for="tech in techDomains" :key="tech"
                     class="chip sm" :class="{ selected: enterprise.techs.includes(tech) }"
                     @click="toggleTech(tech)">{{ tech }}</div>
              </div>
            </div>

            <!-- Section 4: 补充说明 -->
            <div class="form-section-label">补充说明（可选）</div>
            <div class="form-row">
              <el-input v-model="enterprise.extra" type="textarea" :rows="2"
                        placeholder="如：主要产品为XX，有核心专利N项，目前已完成A轮融资…"
                        :disabled="generating" />
            </div>

          </div>

          <!-- 生成按钮 -->
          <div class="generate-row">
            <el-button type="primary" :loading="generating" @click="startGenerate" class="gen-btn">
              <span v-if="!generating">🚀 生成政策分析报告</span>
              <span v-else>AI 分析中...</span>
            </el-button>
            <el-button v-if="reportContent" text @click="copyReport">📋 复制</el-button>
            <el-button v-if="reportContent" text @click="reportContent = ''">🗑 清空</el-button>
            <span v-if="validationErrors.length" class="val-err">
              ⚠ 请先完成必填项：{{ validationErrors.join('、') }}
            </span>
          </div>
          </div><!-- /form-body -->
        </div>

        <!-- 报告滚动区 -->
        <div class="report-card" ref="reportEl">
          <!-- 空状态 -->
          <div v-if="!reportContent && !generating" class="empty-state">
            <div class="empty-icon">📋</div>
            <div class="empty-title">填写左侧政策条件 + 企业信息，AI 为您生成专属报告</div>
            <div class="feature-grid">
              <div class="feat" v-for="f in features" :key="f.title">
                <span>{{ f.icon }}</span><b>{{ f.title }}</b><small>{{ f.desc }}</small>
              </div>
            </div>
          </div>

          <!-- 加载中 -->
          <div v-if="generating && !reportContent" class="loading-state">
            <div class="dots"><span /><span /><span /></div>
            <div>正在检索政策库并生成报告，请稍候...</div>
          </div>

          <!-- 报告内容 -->
          <div v-if="reportContent" class="markdown-body" v-html="renderedReport" />

          <!-- 滚动哨兵：用于检测用户是否已滚到底部 -->
          <div ref="sentinelEl" class="scroll-sentinel" />
        </div>

        <!-- 追问输入框：right-panel 直接子级，始终钉在底部 -->
        <div class="chat-input-bar">
          <input
            v-model="chatInput"
            class="chat-input"
            placeholder="继续追问，如：有哪些具体申报截止日期？"
            :disabled="generating || chatGenerating"
            @keydown.enter.prevent="sendFollowUp"
          />
          <button class="chat-send-btn" :disabled="generating || chatGenerating || !chatInput.trim()" @click="sendFollowUp">
            <span v-if="chatGenerating" class="chat-loading">···</span>
            <span v-else>发送</span>
          </button>
        </div>
      </div>

    </div>
  </div>

  <!-- ── 评分弹窗（Teleport 到 body，不受父布局裁剪）── -->
  <Teleport to="body">
    <Transition name="rating-popup">
      <div v-if="ratingVisible" class="rating-overlay" @click.self="dismissRating">
        <div
          class="rating-card"
          :class="{
            'rating-card--glow': ratingGlowing,
            'rating-card--fade': ratingFading,
          }"
        >
          <!-- 关闭按钮 -->
          <button class="rating-close" @click="dismissRating">×</button>

          <!-- 图标 + 标题 -->
          <div class="rating-icon">✨</div>
          <div class="rating-title">报告对您有帮助吗？</div>
          <div class="rating-subtitle">您的反馈帮助我们持续改进</div>

          <!-- 星星 -->
          <div class="rating-stars" :class="{ 'rating-stars--done': ratingDone }">
            <button
              v-for="s in 5"
              :key="s"
              class="star-btn"
              :class="{
                'star--lit':   s <= (hoverStar || selectedStar),
                'star--selected': s <= selectedStar,
              }"
              @mouseenter="!ratingDone && (hoverStar = s)"
              @mouseleave="!ratingDone && (hoverStar = 0)"
              @click="onStarClick(s)"
            >
              <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" style="display:block;pointer-events:none">
                <polygon
                  points="12,2.5 14.35,8.76 21.03,9.06 15.80,13.24 17.59,19.69 12,16 6.41,19.69 8.20,13.24 2.97,9.06 9.65,8.76"
                  fill="currentColor"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
          </div>

          <!-- 评分后的感谢提示 -->
          <Transition name="thanks">
            <div v-if="ratingDone" class="rating-thanks">
              <span class="thanks-emoji">{{ selectedStar >= 4 ? '🎉' : selectedStar >= 3 ? '👍' : '📝' }}</span>
              {{ selectedStar >= 4 ? '非常感谢！' : selectedStar >= 3 ? '感谢反馈！' : '感谢，我们会持续改进！' }}
            </div>
          </Transition>

          <!-- 未评分时提示跳过 -->
          <div v-if="!ratingDone" class="rating-skip" @click="dismissRating">稍后再说</div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, reactive, watch, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import { generateReport, submitReportFeedback } from '@/api/policyApi'

marked.setOptions({ breaks: true })

// ── 模块 ─────────────────────────────────────────────────────
const modules = [
  { key: 'policy',      emoji: '📄', label: '政策申报',  desc: '补贴/认定/税收/贷款' },
  { key: 'competition', emoji: '🏆', label: '科技竞赛',  desc: '国家级/省级/行业赛事' },
  { key: 'school',      emoji: '🎓', label: '校企合作',  desc: '产学研/人才引进/孵化' },
]

// 持久化：上次激活的模块
const activeModule = ref(localStorage.getItem('pr-last-module') || 'policy')
watch(activeModule, v => localStorage.setItem('pr-last-module', v))

const submitted = ref(false)
const generating = ref(false)
const reportEl = ref<HTMLElement>()
const formCollapsed = ref(false)

// ── 报告内容：按模块各自保存 ─────────────────────────────────
function _loadReportMap(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem('pr-report-map') || '{}') } catch { return {} }
}
const reportMap = reactive<Record<string, string>>(_loadReportMap())
const reportContent = computed({
  get: () => reportMap[activeModule.value] ?? '',
  set: (v: string) => { reportMap[activeModule.value] = v },
})
watch(reportMap, v => localStorage.setItem('pr-report-map', JSON.stringify(v)), { deep: true })

function toggleFormCollapse() {
  formCollapsed.value = !formCollapsed.value
}

// ── 历史记录 ─────────────────────────────────────────────────
interface HistoryItem {
  id: string
  timestamp: number
  module: string
  title: string
  policySnap: Record<string, string>
}
function _loadHistory(): HistoryItem[] {
  try { return JSON.parse(localStorage.getItem('pr-history') || '[]') } catch { return [] }
}
const historyList = ref<HistoryItem[]>(_loadHistory())
const showHistory = ref(false)

function _saveHistory(item: HistoryItem) {
  historyList.value.unshift(item)
  if (historyList.value.length > 30) historyList.value.splice(30)
  localStorage.setItem('pr-history', JSON.stringify(historyList.value))
}

function restoreHistory(item: HistoryItem) {
  activeModule.value = item.module
  const saved = localStorage.getItem(`pr-rc-${item.id}`)
  if (saved) reportMap[item.module] = saved
  showHistory.value = false
}

function formatTime(ts: number) {
  const d = new Date(ts)
  return `${d.getMonth()+1}-${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

// ── 追问输入框 ────────────────────────────────────────────────
const chatInput = ref('')
const chatGenerating = ref(false)

async function sendFollowUp() {
  const q = chatInput.value.trim()
  if (!q || chatGenerating.value || generating.value) return
  chatInput.value = ''
  chatGenerating.value = true

  reportMap[activeModule.value] = (reportMap[activeModule.value] || '') +
    `\n\n---\n**💬 追问：${q}**\n\n`

  try {
    const resp = await generateReport({
      keywords: buildKeywords(),
      user_input: q,
      module: activeModule.value,
    })
    if (!resp.ok || !resp.body) return
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const evt = JSON.parse(line.slice(6).trim())
          if (evt.type === 'delta') {
            reportMap[activeModule.value] += evt.content
            await nextTick()
            reportEl.value?.scrollTo({ top: reportEl.value.scrollHeight, behavior: 'smooth' })
          }
        } catch {}
      }
    }
  } catch (e) {
    ElMessage.error(`追问失败: ${e}`)
  } finally {
    chatGenerating.value = false
  }
}

// ── 滚动到底检测（第2次才弹评分） ───────────────────────────
const sentinelEl = ref<HTMLElement>()
let _scrollObserver: IntersectionObserver | null = null
let _scrollCount = 0

function _setupScrollDetection(sessionId: string) {
  _scrollCount = 0
  _scrollObserver?.disconnect()
  _scrollObserver = null

  nextTick(() => {
    if (!sentinelEl.value) return
    _scrollObserver = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && reportContent.value) {
          _scrollCount++
          if (_scrollCount >= 2 && sessionId) {
            _scrollObserver?.disconnect()
            _scrollObserver = null
            showRatingPopup(sessionId)
          }
        }
      },
      { root: reportEl.value, threshold: 0.8 }
    )
    _scrollObserver.observe(sentinelEl.value)
  })
}

onUnmounted(() => { _scrollObserver?.disconnect() })

// ── 评分弹窗 ─────────────────────────────────────────────────
const ratingVisible = ref(false)       // 弹窗是否显示
const ratingFading = ref(false)        // 是否正在淡出
const ratingGlowing = ref(false)        // 是否正在发光
const hoverStar = ref(0)              // 鼠标悬停的星数
const selectedStar = ref(0)           // 已选择的星数
const ratingDone = ref(false)         // 已完成评分
const currentSessionId = ref('')       // 当前报告的 session_id

function showRatingPopup(sessionId: string) {
  currentSessionId.value = sessionId
  selectedStar.value = 0
  hoverStar.value = 0
  ratingDone.value = false
  ratingFading.value = false
  ratingGlowing.value = false
  ratingVisible.value = true
}

async function onStarClick(star: number) {
  if (ratingDone.value) return
  selectedStar.value = star
  ratingDone.value = true

  // 异步上报反馈（不等待）
  submitReportFeedback({
    session_id: currentSessionId.value,
    stars: star,
  }).catch(() => {})

  // 触发金光环绕效果
  ratingGlowing.value = true
  await new Promise(r => setTimeout(r, 750))
  ratingGlowing.value = false

  // 等待 1 秒后淡出
  await new Promise(r => setTimeout(r, 1000))
  ratingFading.value = true
  await new Promise(r => setTimeout(r, 600))
  ratingVisible.value = false
}

function dismissRating() {
  ratingFading.value = true
  setTimeout(() => { ratingVisible.value = false }, 600)
}

// 折叠后展示的简短摘要标签
const collapsedSummaryTags = computed(() => {
  const tags: string[] = []
  if (enterprise.type) tags.push(enterprise.type)
  if (enterprise.size) {
    const label = companySizes.find(s => s.val === enterprise.size)?.label
    if (label) tags.push(label)
  }
  if (enterprise.industry) tags.push(enterprise.industry)
  return tags.slice(0, 4)
})

// ── 政策分类树（3级）────────────────────────────────────────
const policyTree: Record<string, any[]> = {
  policy: [
    {
      key: 'fund', label: '资金支持', children: [
        { key: 'fund.subsidy', label: '政府直接补贴', children: [
          { key: 'fund.subsidy.rd',   label: '研发补贴' },
          { key: 'fund.subsidy.mfg',  label: '技改补贴' },
          { key: 'fund.subsidy.exp',  label: '出口补贴' },
          { key: 'fund.subsidy.emp',  label: '就业补贴' },
          { key: 'fund.subsidy.rent', label: '场地租金补贴' },
        ]},
        { key: 'fund.tax', label: '税收优惠', children: [
          { key: 'fund.tax.15',    label: '企业所得税15%优惠' },
          { key: 'fund.tax.rdadd', label: '研发费用加计扣除' },
          { key: 'fund.tax.vat',   label: '增值税即征即退' },
          { key: 'fund.tax.import',label: '进口税收减免' },
        ]},
        { key: 'fund.loan', label: '贷款贴息', children: [
          { key: 'fund.loan.discount', label: '贷款贴息' },
          { key: 'fund.loan.guaran',   label: '政府担保贷款' },
          { key: 'fund.loan.startup',  label: '创业担保贷款' },
        ]},
        { key: 'fund.special', label: '专项基金', children: [
          { key: 'fund.special.guide',  label: '产业引导基金' },
          { key: 'fund.special.innov',  label: '科技创新专项' },
          { key: 'fund.special.green',  label: '绿色发展专项' },
          { key: 'fund.special.mfg',    label: '制造业专项' },
        ]},
        { key: 'fund.post', label: '后补助/奖励', children: [
          { key: 'fund.post.list',   label: '上市奖励' },
          { key: 'fund.post.patent', label: '知识产权奖励' },
          { key: 'fund.post.award',  label: '科技奖项奖励' },
        ]},
      ]
    },
    {
      key: 'cert', label: '资质认定', children: [
        { key: 'cert.hnte', label: '高新技术企业', children: [
          { key: 'cert.hnte.apply',  label: '首次申报' },
          { key: 'cert.hnte.renew',  label: '复审/重新认定' },
          { key: 'cert.hnte.award',  label: '认定奖励补贴' },
        ]},
        { key: 'cert.zjtx', label: '专精特新', children: [
          { key: 'cert.zjtx.innov',  label: '创新型中小企业' },
          { key: 'cert.zjtx.sme',    label: '专精特新中小企业' },
          { key: 'cert.zjtx.little', label: '专精特新"小巨人"' },
          { key: 'cert.zjtx.single', label: '制造业单项冠军' },
        ]},
        { key: 'cert.sme', label: '科技型中小企业', children: [
          { key: 'cert.sme.eval',  label: '科技型中小企业评价入库' },
          { key: 'cert.sme.incub', label: '孵化器/加速器入驻' },
        ]},
        { key: 'cert.ip', label: '知识产权', children: [
          { key: 'cert.ip.std',    label: '知识产权贯标认证' },
          { key: 'cert.ip.demo',   label: '知识产权示范企业' },
          { key: 'cert.ip.patent', label: '发明专利资助' },
        ]},
        { key: 'cert.techctr', label: '企业技术中心', children: [
          { key: 'cert.techctr.nation', label: '国家级企业技术中心' },
          { key: 'cert.techctr.prov',   label: '省级企业技术中心' },
        ]},
      ]
    },
    {
      key: 'tech', label: '科技创新', children: [
        { key: 'tech.ai',     label: '人工智能/大数据', children: [
          { key: 'tech.ai.apply', label: '应用场景示范' },
          { key: 'tech.ai.infra', label: '算力/数据基础设施' },
          { key: 'tech.ai.model', label: '大模型/算法研发' },
        ]},
        { key: 'tech.semi',   label: '半导体/集成电路', children: [
          { key: 'tech.semi.design', label: '芯片设计补贴' },
          { key: 'tech.semi.fab',    label: '制造工艺支持' },
          { key: 'tech.semi.pkg',    label: '封测补贴' },
        ]},
        { key: 'tech.new_energy', label: '新能源/储能', children: [
          { key: 'tech.ne.pv',   label: '光伏/风电' },
          { key: 'tech.ne.batt', label: '储能/电池' },
          { key: 'tech.ne.h2',   label: '氢能' },
        ]},
        { key: 'tech.bio',    label: '生物医药/医疗器械', children: [
          { key: 'tech.bio.drug',   label: '创新药研发' },
          { key: 'tech.bio.device', label: '医疗器械' },
          { key: 'tech.bio.cro',    label: 'CRO/医疗服务' },
        ]},
        { key: 'tech.material', label: '新材料', children: [] },
        { key: 'tech.iiot',   label: '工业互联网/智能制造', children: [
          { key: 'tech.iiot.demo', label: '智能工厂示范' },
          { key: 'tech.iiot.5g',   label: '5G+工业应用' },
        ]},
        { key: 'tech.aero',   label: '航空航天/卫星', children: [] },
        { key: 'tech.quantum', label: '量子信息技术', children: [] },
      ]
    },
    {
      key: 'talent', label: '人才政策', children: [
        { key: 'talent.senior', label: '高层次人才引进', children: [
          { key: 'talent.senior.house',   label: '住房补贴/安家费' },
          { key: 'talent.senior.salary',  label: '薪资补贴' },
          { key: 'talent.senior.abroad',  label: '海外人才归国' },
        ]},
        { key: 'talent.post',   label: '博士后设站', children: [] },
        { key: 'talent.train',  label: '职业技能培训补贴', children: [] },
        { key: 'talent.create', label: '创业人才扶持', children: [] },
      ]
    },
    {
      key: 'industry', label: '产业发展', children: [
        { key: 'industry.digital',   label: '数字经济',   children: [] },
        { key: 'industry.mfg',       label: '先进制造业', children: [] },
        { key: 'industry.service',   label: '现代服务业', children: [] },
        { key: 'industry.culture',   label: '文化创意',   children: [] },
        { key: 'industry.agri',      label: '农业现代化', children: [] },
        { key: 'industry.sports',    label: '体育产业',   children: [] },
      ]
    },
    {
      key: 'green', label: '绿色低碳', children: [
        { key: 'green.energy', label: '节能减排', children: [] },
        { key: 'green.ev',     label: '新能源汽车', children: [] },
        { key: 'green.carbon', label: '碳达峰/碳中和', children: [] },
        { key: 'green.cycle',  label: '循环经济', children: [] },
        { key: 'green.build',  label: '绿色建筑', children: [] },
      ]
    },
    {
      key: 'trade', label: '对外贸易', children: [
        { key: 'trade.export',   label: '出口退税/补贴', children: [] },
        { key: 'trade.cross',    label: '跨境电商',      children: [] },
        { key: 'trade.ftz',      label: '自贸区政策',    children: [] },
        { key: 'trade.overseas', label: '对外投资扶持',  children: [] },
      ]
    },
    {
      key: 'startup', label: '创业扶持', children: [
        { key: 'startup.sub',   label: '创业补贴',      children: [] },
        { key: 'startup.incub', label: '孵化基地入驻',  children: [] },
        { key: 'startup.angel', label: '天使投资引导',  children: [] },
        { key: 'startup.park',  label: '园区优惠政策',  children: [] },
      ]
    },
  ],

  competition: [
    {
      key: 'comp.national', label: '国家级赛事', children: [
        { key: 'comp.nat.inno',   label: '中国创新创业大赛', children: [] },
        { key: 'comp.nat.chuang', label: '"创客中国"大赛',   children: [] },
        { key: 'comp.nat.cup',    label: '"挑战杯"系列',     children: [] },
        { key: 'comp.nat.inter',  label: '"互联网+"大赛',    children: [] },
        { key: 'comp.nat.disr',   label: '颠覆性技术大赛',   children: [] },
        { key: 'comp.nat.data',   label: '数据要素大赛',     children: [] },
      ]
    },
    {
      key: 'comp.province', label: '省级赛事', children: [
        { key: 'comp.prov.gd',  label: '广东省创新创业大赛', children: [] },
        { key: 'comp.prov.bj',  label: '北京创新创业大赛',   children: [] },
        { key: 'comp.prov.sh',  label: '长三角创业大赛',     children: [] },
        { key: 'comp.prov.sz',  label: '深圳创新创业大赛',   children: [] },
        { key: 'comp.prov.hz',  label: '杭州未来科技城大赛', children: [] },
      ]
    },
    {
      key: 'comp.industry', label: '行业专项赛', children: [
        { key: 'comp.ind.ai',   label: 'AI/大数据专项赛', children: [] },
        { key: 'comp.ind.mfg',  label: '智能制造专项赛',  children: [] },
        { key: 'comp.ind.bio',  label: '生物医药专项赛',  children: [] },
        { key: 'comp.ind.ne',   label: '新能源专项赛',    children: [] },
        { key: 'comp.ind.agri', label: '农业科技赛',      children: [] },
        { key: 'comp.ind.fin',  label: '金融科技赛',      children: [] },
      ]
    },
    {
      key: 'comp.award', label: '奖励级别', children: [
        { key: 'comp.award.a', label: '国家级奖项', children: [] },
        { key: 'comp.award.b', label: '省部级奖项', children: [] },
        { key: 'comp.award.c', label: '市厅级奖项', children: [] },
      ]
    },
  ],

  school: [
    {
      key: 'school.research', label: '产学研合作', children: [
        { key: 'school.res.joint', label: '联合研究院/实验室', children: [] },
        { key: 'school.res.fund',  label: '横向科研项目',      children: [] },
        { key: 'school.res.trans', label: '科技成果转化',      children: [] },
      ]
    },
    {
      key: 'school.talent', label: '人才培养合作', children: [
        { key: 'school.tal.intern', label: '定向实习/实训基地', children: [] },
        { key: 'school.tal.doctor', label: '博士后工作站',      children: [] },
        { key: 'school.tal.order',  label: '订单式人才培养',    children: [] },
      ]
    },
    {
      key: 'school.incub', label: '孵化/转化', children: [
        { key: 'school.incub.park',  label: '大学科技园入驻',  children: [] },
        { key: 'school.incub.spin',  label: '技术转让/入股',   children: [] },
        { key: 'school.incub.fund',  label: '高校孵化基金',    children: [] },
      ]
    },
    {
      key: 'school.gov', label: '政府支持校企合作', children: [
        { key: 'school.gov.pilot', label: '国家产教融合试点',   children: [] },
        { key: 'school.gov.base',  label: '实训基地建设补贴',   children: [] },
        { key: 'school.gov.dual',  label: '"双师型"教师培养',   children: [] },
      ]
    },
  ],
}

// ── 省份/城市 ──────────────────────────────────────────────────
const regionList = [
  '全国', '北京', '上海', '广东', '深圳', '杭州', '成都', '武汉', '南京',
  '苏州', '重庆', '西安', '天津', '青岛', '长沙', '合肥', '郑州', '福州',
  '宁波', '厦门', '其他',
]

// ── 企业信息选项 ──────────────────────────────────────────────
const companyTypes = ['有限责任公司', '股份有限公司', '合伙企业', '外资企业', '国有企业', '个体工商户']
const companySizes = [
  { val: 'micro',  label: '微型 (<20人)' },
  { val: 'small',  label: '小型 (20-299人)' },
  { val: 'medium', label: '中型 (300-999人)' },
  { val: 'large',  label: '大型 (≥1000人)' },
]
const industries = [
  '人工智能/大数据', '软件/互联网', '半导体/集成电路', '新能源/储能', '生物医药',
  '医疗器械', '新材料', '智能制造/工业互联网', '节能环保', '航空航天',
  '金融科技', '文化/传媒', '农业科技', '消费/零售', '建筑/房地产', '教育', '其他',
]
const foundedYears = ['不足1年', '1-3年', '3-5年', '5-10年', '10年以上']
const revenueRanges = ['100万以下', '100-500万', '500万-5000万', '5000万-2亿', '2亿以上']
const capitalRanges = ['100万以下', '100-500万', '500万-2000万', '2000万-1亿', '1亿以上']
const listedStatus = ['未上市', '拟上市/辅导中', '新三板', '北交所', '科创板', '主板/创业板', '境外上市']
const rdRatios = ['1%以下', '1%-3%', '3%-5%', '5%-10%', '10%以上']
const rdPersonRatios = ['10%以下', '10%-30%', '30%-50%', '50%以上']
const qualifications = [
  '高新技术企业', '专精特新中小企业', '专精特新小巨人', '科技型中小企业',
  '国家企业技术中心', '知识产权贯标企业', '双软企业认定', '暂无'
]
const techDomains = [
  'AI/机器学习', '大数据/云计算', '芯片/FPGA', '新能源/光伏', '生物技术',
  '新材料', '工业软件', '智能硬件', '区块链', '量子计算', '机器人/自动化',
]

const features = [
  { icon: '🎯', title: '精准匹配',   desc: '向量+关键词双引擎' },
  { icon: '⏰', title: '截止日历',   desc: '按紧迫程度排序' },
  { icon: '✅', title: '条件核查',   desc: '结合企业实际情况' },
  { icon: '📈', title: '行动建议',   desc: '可落地的申报计划' },
]

// ── 政策筛选状态 ──────────────────────────────────────────────
const policy = reactive({ region: '', l1: '', l2: '', l3: '' })
const enterprise = reactive({
  type: '', size: '', industry: '', founded: '', revenue: '',
  capital: '', listed: '', rdRatio: '', rdPerson: '',
  quals: [] as string[], techs: [] as string[], extra: '',
})

// ── 计算：二/三级分类 ─────────────────────────────────────────
const currentL2 = computed(() => {
  const l1 = policyTree[activeModule.value]?.find(c => c.key === policy.l1)
  return l1?.children ?? []
})
const currentL3 = computed(() => {
  const l2 = currentL2.value.find((c: any) => c.key === policy.l2)
  return l2?.children ?? []
})

// ── 已选摘要标签 ──────────────────────────────────────────────
const policyTagList = computed(() => {
  const tags: { key: string; val: string }[] = []
  if (policy.region) tags.push({ key: 'region', val: `📍 ${policy.region}` })
  if (policy.l1) {
    const l1 = policyTree[activeModule.value]?.find((c: any) => c.key === policy.l1)
    if (l1) tags.push({ key: 'l1', val: `📂 ${l1.label}` })
  }
  if (policy.l2) {
    const l2 = currentL2.value.find((c: any) => c.key === policy.l2)
    if (l2) tags.push({ key: 'l2', val: `📌 ${(l2 as any).label}` })
  }
  if (policy.l3) {
    const l3 = currentL3.value.find((c: any) => c.key === policy.l3)
    if (l3) tags.push({ key: 'l3', val: `🔖 ${(l3 as any).label}` })
  }
  return tags
})

// ── 验证错误 ─────────────────────────────────────────────────
const validationErrors = computed(() => {
  if (!submitted.value) return []
  const errs: string[] = []
  if (!policy.region) errs.push('适用地区')
  if (!policy.l1) errs.push('政策大类')
  if (!enterprise.type) errs.push('公司类型')
  if (!enterprise.size) errs.push('企业规模')
  if (!enterprise.industry) errs.push('主营行业')
  return errs
})

// ── 操作 ─────────────────────────────────────────────────────
function switchModule(mod: string) {
  activeModule.value = mod
  policy.l1 = ''
  policy.l2 = ''
  policy.l3 = ''
  // 保留报告，切回时仍可查看
}

function selectL1(key: string) {
  policy.l1 = policy.l1 === key ? '' : key
  policy.l2 = ''
  policy.l3 = ''
}

function selectL2(key: string) {
  policy.l2 = policy.l2 === key ? '' : key
  policy.l3 = ''
}

function clearPolicyTag(key: string) {
  if (key === 'region') policy.region = ''
  if (key === 'l1') { policy.l1 = ''; policy.l2 = ''; policy.l3 = '' }
  if (key === 'l2') { policy.l2 = ''; policy.l3 = '' }
  if (key === 'l3') policy.l3 = ''
}

function resetAll() {
  policy.region = ''; policy.l1 = ''; policy.l2 = ''; policy.l3 = ''
  Object.assign(enterprise, {
    type: '', size: '', industry: '', founded: '', revenue: '',
    capital: '', listed: '', rdRatio: '', rdPerson: '',
    quals: [], techs: [], extra: '',
  })
  submitted.value = false
  reportMap[activeModule.value] = ''
  formCollapsed.value = false
}

function toggleQual(q: string) {
  const idx = enterprise.quals.indexOf(q)
  if (idx >= 0) enterprise.quals.splice(idx, 1)
  else enterprise.quals.push(q)
}

function toggleTech(t: string) {
  const idx = enterprise.techs.indexOf(t)
  if (idx >= 0) enterprise.techs.splice(idx, 1)
  else enterprise.techs.push(t)
}

// ── 构建用户输入描述 ─────────────────────────────────────────
function buildUserInput(): string {
  const parts: string[] = []
  if (enterprise.type) parts.push(`公司类型：${enterprise.type}`)
  if (enterprise.size) {
    const label = companySizes.find(s => s.val === enterprise.size)?.label
    parts.push(`企业规模：${label}`)
  }
  if (enterprise.industry) parts.push(`主营行业：${enterprise.industry}`)
  if (enterprise.founded) parts.push(`成立年限：${enterprise.founded}`)
  if (enterprise.revenue) parts.push(`年营收：${enterprise.revenue}`)
  if (enterprise.capital) parts.push(`注册资本：${enterprise.capital}`)
  if (enterprise.listed) parts.push(`上市状态：${enterprise.listed}`)
  if (enterprise.rdRatio) parts.push(`研发投入占比：${enterprise.rdRatio}`)
  if (enterprise.rdPerson) parts.push(`研发人员占比：${enterprise.rdPerson}`)
  if (enterprise.quals.length) parts.push(`已有资质：${enterprise.quals.join('、')}`)
  if (enterprise.techs.length) parts.push(`核心技术：${enterprise.techs.join('、')}`)
  if (enterprise.extra) parts.push(enterprise.extra)
  return parts.join('；')
}

// ── 构建关键词 ────────────────────────────────────────────────
function buildKeywords(): Record<string, string> {
  const kw: Record<string, string> = {}
  if (policy.region) kw.region = policy.region
  const l1 = policyTree[activeModule.value]?.find((c: any) => c.key === policy.l1)
  if (l1) kw.l1 = (l1 as any).label
  const l2 = currentL2.value.find((c: any) => c.key === policy.l2)
  if (l2) kw.l2 = (l2 as any).label
  const l3 = currentL3.value.find((c: any) => c.key === policy.l3)
  if (l3) kw.l3 = (l3 as any).label
  return kw
}

// ── 生成报告 ─────────────────────────────────────────────────
async function startGenerate() {
  submitted.value = true
  if (validationErrors.value.length) return

  formCollapsed.value = true
  generating.value = true
  reportMap[activeModule.value] = ''
  let sessionId = ''

  try {
    const resp = await generateReport({
      keywords: buildKeywords(),
      user_input: buildUserInput(),
      module: activeModule.value,
    })
    if (!resp.ok || !resp.body) throw new Error(`请求失败: ${resp.status}`)

    sessionId = resp.headers.get('X-Session-Id') ?? ''

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const evt = JSON.parse(line.slice(6).trim())
          if (evt.type === 'session') {
            sessionId = evt.session_id ?? sessionId
          } else if (evt.type === 'delta') {
            reportMap[activeModule.value] += evt.content
            await nextTick()
            reportEl.value?.scrollTo({ top: reportEl.value.scrollHeight, behavior: 'smooth' })
          } else if (evt.type === 'error') {
            ElMessage.error(`报告生成失败: ${evt.message}`)
          }
        } catch {}
      }
    }

    // 生成完成 → 存历史 + 设置滚动检测（用户滚到底第2次才弹评分）
    if (reportMap[activeModule.value]) {
      const id = sessionId || `local-${Date.now()}`
      localStorage.setItem(`pr-rc-${id}`, reportMap[activeModule.value])

      const l1Node = policyTree[activeModule.value]?.find((c: any) => c.key === policy.l1)
      const l2Node = currentL2.value.find((c: any) => c.key === policy.l2)
      const l3Node = currentL3.value.find((c: any) => c.key === policy.l3)
      const titleParts = [policy.region, l1Node?.label, l2Node?.label, l3Node?.label].filter(Boolean)
      _saveHistory({
        id,
        timestamp: Date.now(),
        module: activeModule.value,
        title: titleParts.join(' · ') || '政策报告',
        policySnap: { region: policy.region, l1: policy.l1, l2: policy.l2, l3: policy.l3 },
      })

      if (sessionId) _setupScrollDetection(sessionId)
    }
  } catch (e) {
    ElMessage.error(`请求失败: ${e}`)
  } finally {
    generating.value = false
  }
}

async function copyReport() {
  try {
    await navigator.clipboard.writeText(reportContent.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

const renderedReport = computed(() =>
  reportContent.value ? (marked(reportContent.value) as string) : ''
)
</script>

<style scoped>
* { box-sizing: border-box; }

.policy-agent {
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100vh;
  padding: 16px;
  font-family: -apple-system, 'PingFang SC', sans-serif;
  overflow: hidden;
  box-sizing: border-box;
}

/* ── 模块标签 ── */
.module-tabs { display: flex; gap: 10px; flex-shrink: 0; }
.module-tab {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px;
  padding: 12px 10px; background: #fff; border-radius: 12px;
  cursor: pointer; border: 2px solid transparent; transition: all 0.18s;
}
.module-tab:hover { border-color: #dbeafe; background: #f0f9ff; }
.module-tab.active { border-color: #3b82f6; background: #eff6ff; }
.mod-icon { font-size: 20px; }
.mod-label { font-size: 14px; font-weight: 700; color: #1e3a5f; }
.mod-desc { font-size: 11px; color: #6b7280; }

.history-btn {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  padding: 12px 16px; background: #fff; border-radius: 12px;
  cursor: pointer; border: 2px solid transparent; transition: all 0.18s;
  flex-shrink: 0; min-width: 90px;
}
.history-btn:hover { border-color: #fde68a; background: #fffbeb; }
.history-btn.active { border-color: #f59e0b; background: #fffbeb; }

/* ── 历史面板（侧抽屉样式，覆盖在 agent-body 顶层） ── */
.history-panel {
  position: absolute; inset: 0; z-index: 100;
  background: rgba(0,0,0,0.18);
  display: flex; justify-content: flex-end;
}
.history-inner {
  width: 320px; height: 100%; background: #fff;
  box-shadow: -4px 0 20px rgba(0,0,0,0.1);
  display: flex; flex-direction: column; border-radius: 14px 0 0 14px;
  overflow: hidden;
}
.history-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 18px; border-bottom: 1px solid #f3f4f6; flex-shrink: 0;
}
.history-title { font-size: 15px; font-weight: 700; color: #1e3a5f; }
.history-close {
  width: 26px; height: 26px; border: none; background: #f3f4f6;
  border-radius: 50%; font-size: 16px; cursor: pointer; color: #6b7280;
  display: flex; align-items: center; justify-content: center;
}
.history-close:hover { background: #e5e7eb; color: #374151; }
.history-scroll { flex: 1; overflow-y: auto; scrollbar-width: thin; }
.history-empty { padding: 40px 20px; text-align: center; color: #9ca3af; font-size: 13px; }
.history-item {
  padding: 12px 18px; cursor: pointer; border-bottom: 1px solid #f9fafb;
  transition: background 0.15s;
}
.history-item:hover { background: #f9fafb; }
.hi-module { font-size: 11px; color: #9ca3af; margin-bottom: 3px; }
.hi-title { font-size: 13px; font-weight: 600; color: #1e3a5f; line-height: 1.4; }
.hi-time { font-size: 11px; color: #d1d5db; margin-top: 3px; }

.history-slide-enter-active { transition: opacity 0.2s; }
.history-slide-leave-active { transition: opacity 0.2s; }
.history-slide-enter-from, .history-slide-leave-to { opacity: 0; }

/* ── 报告滚动区（独立卡片，high: 0 是约束 flex 子项高度的关键）── */
.report-card {
  flex: 1;
  height: 0;          /* 与 flex:1 配合，强制浏览器以 flex 分配的高度为准而非内容高度 */
  min-height: 0;
  padding: 18px;
  overflow-y: auto;
  background: #fff;
  border-radius: 14px;
}

/* 滚动哨兵（不可见，只用于 IntersectionObserver） */
.scroll-sentinel { height: 4px; }

/* ── 底部追问输入框（完全独立，不随报告变化）── */
.chat-input-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; flex-shrink: 0;
  background: #fff; border-radius: 14px;
  border: 1px solid #f0f2f5;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.chat-input {
  flex: 1; height: 36px; border: 1.5px solid #e5e7eb; border-radius: 18px;
  padding: 0 14px; font-size: 13px; color: #374151; outline: none;
  transition: border-color 0.2s;
  font-family: -apple-system, 'PingFang SC', sans-serif;
}
.chat-input:focus { border-color: #3b82f6; }
.chat-input:disabled { background: #f9fafb; color: #9ca3af; }
.chat-input::placeholder { color: #c4c9d4; }
.chat-send-btn {
  height: 36px; padding: 0 18px; border-radius: 18px; border: none;
  background: #3b82f6; color: #fff; font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all 0.18s; white-space: nowrap; flex-shrink: 0;
}
.chat-send-btn:hover:not(:disabled) { background: #2563eb; }
.chat-send-btn:disabled { background: #bfdbfe; cursor: not-allowed; }
.chat-loading { letter-spacing: 2px; animation: blink 1s infinite; }
@keyframes blink { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }

/* ── 主体 ── */
.agent-body { flex: 1; display: flex; gap: 14px; min-height: 0; overflow: hidden; position: relative; }

/* ── 漏斗面板 ── */
.funnel-panel {
  width: 240px; flex-shrink: 0; background: #fff; border-radius: 14px;
  padding: 14px; display: flex; flex-direction: column; gap: 10px;
  overflow-y: auto; scrollbar-width: thin;
}
.panel-header { display: flex; align-items: center; justify-content: space-between; }
.panel-title { font-size: 13px; font-weight: 700; color: #1e3a5f; }

.funnel-block { display: flex; flex-direction: column; gap: 5px; }
.block-label {
  font-size: 11px; font-weight: 700; color: #6b7280;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.block-label.required::after { content: ' *'; color: #ef4444; }

.chip-group { display: flex; flex-wrap: wrap; gap: 5px; }
.chip {
  padding: 4px 10px; border-radius: 16px; font-size: 12px; cursor: pointer;
  background: #f3f4f6; color: #374151; border: 1.5px solid transparent;
  transition: all 0.14s; user-select: none;
}
.chip:hover { background: #dbeafe; color: #1d4ed8; }
.chip.selected { background: #dbeafe; color: #1d4ed8; border-color: #3b82f6; font-weight: 600; }
.chip.sm { padding: 3px 8px; font-size: 11px; }

.err-tip { font-size: 11px; color: #ef4444; margin-top: 2px; }

.selected-summary { display: flex; flex-direction: column; gap: 5px;
  padding-top: 8px; border-top: 1px solid #f3f4f6; }
.tag-row { display: flex; flex-wrap: wrap; gap: 4px; }

/* ── 右侧 ── */
.right-panel {
  flex: 1; display: flex; flex-direction: column;
  gap: 10px; min-width: 0; min-height: 0; overflow: hidden;
}

/* ── 企业信息卡 ── */
.form-card {
  background: #fff; border-radius: 14px; padding: 16px;
  flex-shrink: 0; display: flex; flex-direction: column; gap: 0;
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1.5px solid transparent;
  max-height: 55%;
  overflow: hidden;
}
.form-card--collapsed {
  max-height: 58px;
  cursor: pointer;
  border-color: #e0eaff;
  background: linear-gradient(135deg, #f8fbff 0%, #ffffff 100%);
  box-shadow: 0 2px 8px rgba(59,130,246,0.06);
}
.form-card--collapsed:hover {
  border-color: #93c5fd;
  box-shadow: 0 4px 14px rgba(59,130,246,0.10);
}

/* 头部 */
.form-card-header {
  display: flex; align-items: center; justify-content: space-between;
  flex-shrink: 0; min-height: 26px;
}
.form-title-group { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; }
.form-title { font-size: 14px; font-weight: 700; color: #1e3a5f; white-space: nowrap; }
.header-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.form-hint { font-size: 11px; color: #9ca3af; }
.req-star { color: #ef4444; }

/* 折叠后摘要标签 */
.collapsed-summary { display: flex; align-items: center; gap: 5px; flex-wrap: nowrap; overflow: hidden; }
.csummary-tag {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: #dbeafe; color: #1d4ed8; font-weight: 500;
  white-space: nowrap; border: 1px solid #bfdbfe;
}

/* 折叠/展开按钮 */
.collapse-btn {
  width: 28px; height: 28px; border-radius: 8px; border: none;
  background: #f0f6ff; color: #3b82f6; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s; flex-shrink: 0;
}
.collapse-btn:hover { background: #dbeafe; color: #1d4ed8; transform: scale(1.05); }
.chevron-icon {
  width: 15px; height: 15px;
  transition: transform 0.32s cubic-bezier(0.4, 0, 0.2, 1);
  transform: rotate(0deg);
}
.chevron-up { transform: rotate(180deg); }

/* 可折叠内容区 */
.form-body {
  overflow-y: auto; scrollbar-width: thin;
  display: flex; flex-direction: column; gap: 10px;
  margin-top: 10px;
  transition: opacity 0.25s ease;
  opacity: 1;
}
.form-body--hidden {
  opacity: 0; pointer-events: none; overflow: hidden;
}

.form-grid { display: flex; flex-direction: column; gap: 8px; }
.form-section-label {
  font-size: 11px; font-weight: 700; color: #9ca3af;
  text-transform: uppercase; letter-spacing: 0.5px;
  padding: 4px 0 2px; border-bottom: 1px solid #f3f4f6;
}
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-field-label { font-size: 12px; color: #374151; font-weight: 500; }
.form-field-label.required::after { content: ' *'; color: #ef4444; }

.generate-row {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding-top: 10px; border-top: 1px solid #f3f4f6; flex-shrink: 0;
}
.gen-btn { padding: 9px 22px; font-weight: 600; }
.val-err { font-size: 12px; color: #ef4444; }

/* fade 过渡（摘要标签出现/消失） */
.fade-enter-active { transition: opacity 0.2s 0.15s ease; }
.fade-leave-active { transition: opacity 0.1s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* 空状态 */
.empty-state {
  display: flex; flex-direction: column; align-items: center;
  padding: 30px 20px; gap: 8px; color: #6b7280;
}
.empty-icon { font-size: 40px; }
.empty-title { font-size: 14px; font-weight: 600; color: #374151; text-align: center; }
.feature-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
  margin-top: 12px; width: 100%; max-width: 420px;
}
.feat {
  display: flex; flex-direction: column; align-items: center; gap: 3px;
  padding: 10px; background: #f9fafb; border-radius: 10px;
  border: 1px solid #e5e7eb; font-size: 12px; color: #6b7280;
}
.feat b { color: #374151; font-size: 13px; }

/* loading */
.loading-state {
  display: flex; flex-direction: column; align-items: center;
  gap: 12px; padding: 50px 20px; font-size: 13px; color: #6b7280;
}
.dots { display: flex; gap: 7px; }
.dots span {
  width: 9px; height: 9px; border-radius: 50%; background: #3b82f6;
  animation: bounce 1.2s infinite ease-in-out;
}
.dots span:nth-child(2) { animation-delay: 0.2s; }
.dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%,80%,100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* Markdown */
.markdown-body { font-size: 14px; line-height: 1.8; color: #374151; }
.markdown-body :deep(h2) {
  font-size: 16px; font-weight: 700; color: #1e3a5f;
  margin: 18px 0 8px; padding-bottom: 5px; border-bottom: 2px solid #e5e7eb;
}
.markdown-body :deep(h3) { font-size: 14px; font-weight: 600; color: #1e3a5f; margin: 14px 0 6px; }
.markdown-body :deep(table) { width: 100%; border-collapse: collapse; font-size: 12px; margin: 8px 0; }
.markdown-body :deep(th) { background: #eff6ff; padding: 7px 10px; border: 1px solid #dbeafe; font-weight: 600; color: #1d4ed8; }
.markdown-body :deep(td) { padding: 6px 10px; border: 1px solid #e5e7eb; }
.markdown-body :deep(tr:nth-child(even) td) { background: #f9fafb; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 18px; }
.markdown-body :deep(li) { margin: 3px 0; }
.markdown-body :deep(strong) { color: #1e3a5f; }
.markdown-body :deep(code) {
  background: #f3f4f6; padding: 1px 5px; border-radius: 3px; font-size: 12px;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid #3b82f6; padding: 6px 12px;
  background: #eff6ff; margin: 8px 0; border-radius: 0 8px 8px 0;
}
.markdown-body :deep(hr) { border-color: #e5e7eb; margin: 14px 0; }

/* 过渡 */
.slide-down-enter-active { transition: all 0.22s ease; }
.slide-down-leave-active { transition: all 0.18s ease; }
.slide-down-enter-from { opacity: 0; transform: translateY(-6px); }
.slide-down-leave-to { opacity: 0; }
</style>

<!-- 弹窗使用非 scoped 样式，确保 Teleport 到 body 后仍然生效 -->
<style>
/* ── 遮罩 ── */
.rating-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding-bottom: 44px;
  pointer-events: none;
}

/* ── 卡片：更圆润、更矮 ── */
.rating-card {
  pointer-events: all;
  position: relative;
  background: linear-gradient(160deg, #ffffff 0%, #fefcf5 100%);
  border-radius: 28px;
  padding: 18px 30px 16px;
  width: 300px;
  text-align: center;
  box-shadow:
    0 20px 50px rgba(0, 0, 0, 0.12),
    0 6px 16px rgba(0, 0, 0, 0.07),
    0 0 0 1px rgba(0, 0, 0, 0.04);
  will-change: transform, opacity, box-shadow;
  transition: box-shadow 0.05s;
}

/* ── 弹窗入场 / 离场动画 ── */
.rating-popup-enter-active {
  animation: popup-bounce-in 0.42s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
.rating-popup-leave-active {
  animation: popup-fade-out 0.5s ease forwards;
}
@keyframes popup-bounce-in {
  from { opacity: 0; transform: translateY(40px) scale(0.88); }
  to   { opacity: 1; transform: translateY(0)   scale(1); }
}
@keyframes popup-fade-out {
  to { opacity: 0; transform: translateY(16px) scale(0.93); }
}

/* ── 淡出 class ── */
.rating-card--fade {
  animation: popup-fade-out 0.6s ease forwards !important;
}

/* ── 金光环绕：box-shadow 亮起 → 熄灭 ── */
.rating-card--glow {
  animation: card-glow 0.75s ease-out forwards !important;
}
@keyframes card-glow {
  0% {
    box-shadow:
      0 20px 50px rgba(0,0,0,0.12),
      0 6px 16px rgba(0,0,0,0.07),
      0 0 0 0px  rgba(251,191,36,0),
      0 0  0px 0px rgba(251,191,36,0);
  }
  22% {
    box-shadow:
      0 20px 50px rgba(0,0,0,0.12),
      0 6px 16px rgba(0,0,0,0.07),
      0 0 0 3px  rgba(251,191,36,0.85),
      0 0 28px 10px rgba(251,191,36,0.38);
  }
  55% {
    box-shadow:
      0 20px 50px rgba(0,0,0,0.12),
      0 6px 16px rgba(0,0,0,0.07),
      0 0 0 2px  rgba(251,191,36,0.4),
      0 0 14px 5px rgba(251,191,36,0.15);
  }
  100% {
    box-shadow:
      0 20px 50px rgba(0,0,0,0.12),
      0 6px 16px rgba(0,0,0,0.07),
      0 0 0 0px  rgba(251,191,36,0),
      0 0  0px 0px rgba(251,191,36,0);
  }
}

/* ── 关闭按钮 ── */
.rating-close {
  position: absolute;
  top: 9px; right: 12px;
  width: 22px; height: 22px;
  border: none; background: none;
  font-size: 17px; color: #c4c9d4;
  cursor: pointer; line-height: 1;
  border-radius: 50%;
  transition: background 0.2s, color 0.2s;
  display: flex; align-items: center; justify-content: center;
}
.rating-close:hover { background: #f3f4f6; color: #374151; }

/* ── 内容 ── */
.rating-icon  { font-size: 30px; line-height: 1; margin-bottom: 4px; }
.rating-title {
  font-size: 15px; font-weight: 700;
  color: #111827; margin-bottom: 2px;
  letter-spacing: -0.3px;
}
.rating-subtitle {
  font-size: 11px; color: #b0b7c3;
  margin-bottom: 14px;
}

/* ── 星星区 ── */
.rating-stars {
  display: flex; justify-content: center; gap: 4px;
  margin-bottom: 10px;
}
.rating-stars--done { pointer-events: none; }

.star-btn {
  color: #dde0e7;
  background: none; border: none;
  cursor: pointer;
  transition: color 0.13s, transform 0.13s, filter 0.13s;
  padding: 3px;
  user-select: none;
  line-height: 0;
  border-radius: 6px;
}
.star-btn:hover {
  transform: scale(1.22) translateY(-1px);
  filter: drop-shadow(0 2px 5px rgba(251,191,36,0.45));
}
/* 点亮：金色 + 软阴影 */
.star--lit {
  color: #fbbf24;
  filter: drop-shadow(0 1px 3px rgba(251,191,36,0.35));
}
/* 已选：深金 + 轻微放大保持 */
.star--selected {
  color: #f59e0b;
  transform: scale(1.1);
  filter: drop-shadow(0 2px 6px rgba(245,158,11,0.5));
}

/* ── 感谢提示 ── */
.rating-thanks {
  font-size: 12.5px; color: #374151;
  font-weight: 600;
  display: flex; align-items: center; justify-content: center; gap: 4px;
  min-height: 20px;
}
.thanks-emoji { font-size: 15px; }

/* ── 感谢淡入 ── */
.thanks-enter-active { transition: opacity 0.3s, transform 0.3s; }
.thanks-enter-from   { opacity: 0; transform: translateY(4px); }

/* ── 跳过 ── */
.rating-skip {
  margin-top: 10px;
  font-size: 10.5px; color: #d1d5db;
  cursor: pointer;
  letter-spacing: 0.2px;
  transition: color 0.2s;
}
.rating-skip:hover { color: #9ca3af; }
</style>
