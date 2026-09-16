/**
 * PolicyRadar API 封装（代理到 http://localhost:8001）
 * Vite 代理前缀：/policy-api
 */

const BASE = '/policy-api/api/v1'
const AI_BASE = '/policy-api/ai'

export interface CategoryNode {
  id: number
  code: string
  label: string
  icon?: string
  level: number
  policy_count: number
  children: CategoryNode[]
}

export interface PolicyItem {
  id: number
  title: string
  publisher?: string
  region?: string
  pub_date?: string
  deadline?: string
  summary?: string
  category_l1?: string
  category_l2?: string
  policy_types: string[]
  funding_amount?: string
  key_conditions?: string
  score_relevance: number
  score_urgency: number
  score_value: number
  source_url?: string
}

export interface ReportRequest {
  keywords: Record<string, string>
  user_input: string
  module: string
}

/** 获取完整分类树 */
export async function getCategoryTree(): Promise<CategoryNode[]> {
  const resp = await fetch(`${BASE}/categories`)
  if (!resp.ok) throw new Error(`获取分类失败: ${resp.status}`)
  return resp.json()
}

/** 获取政策列表 */
export async function listPolicies(params: {
  region?: string
  l1?: string
  l2?: string
  limit?: number
  offset?: number
} = {}): Promise<PolicyItem[]> {
  const q = new URLSearchParams()
  if (params.region) q.set('region', params.region)
  if (params.l1) q.set('l1', params.l1)
  if (params.l2) q.set('l2', params.l2)
  if (params.limit) q.set('limit', String(params.limit))
  if (params.offset) q.set('offset', String(params.offset))
  const resp = await fetch(`${BASE}/policies?${q}`)
  if (!resp.ok) throw new Error(`获取政策失败: ${resp.status}`)
  return resp.json()
}

/** 流式生成报告（SSE）*/
export async function generateReport(req: ReportRequest): Promise<Response> {
  return fetch(`${BASE}/report/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
}

/** 提交报告评分反馈（供 Reflexion 优化器使用）*/
export async function submitReportFeedback(params: {
  session_id: string
  stars: number          // 1-5
}): Promise<void> {
  const score = params.stars / 5   // 归一化到 0~1
  await fetch(`${AI_BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: params.session_id,
      signal_type: 'explicit_rating',
      score,
      metadata: { stars: params.stars, source: 'report_rating_popup' },
    }),
  })
}

/** 手动触发采集 */
export async function triggerCrawl(source = 'all') {
  const resp = await fetch(`${BASE}/crawl/trigger`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source }),
  })
  if (!resp.ok) throw new Error(`触发采集失败: ${resp.status}`)
  return resp.json()
}
