import http from './http'

/** 举报提交请求体（对应后端 ContentReport 实体） */
export interface ReportSubmitReq {
  reportedCommentId?: number
  reportedPostId?: number
  reportedUserId?: number
  /** 0=广告水军 1=违法信息 2=侮辱谩骂 3=色情低俗 4=其他 */
  reportCategory: number
  reportReason?: string
}

/** AI审核返回结果（对应后端 ModerateResultDTO） */
export interface ModerateResult {
  reportId: number
  reportedUserId: number
  anomalyScore: number
  contentType: string
  violatedRules: string[]
  violatedLaws: string[]
  evidenceSummary: string
  evidenceDetail: string
  /** none / manual_review / auto_mute */
  action: string
}

/** 普通用户提交举报 */
export const submitReport = (data: ReportSubmitReq) =>
  http.post('/content/reports', data)

/** 管理员触发 AI 审核（立即受理）。结果请用 getModerateResult 轮询 */
export const moderateReport = (reportId: number) =>
  http.post(`/agent/moderate/${reportId}`, null, { timeout: 15000 })

/** 轮询 AI 审核结果（Python 可能要数十秒） */
export const getModerateResult = (reportId: number) =>
  http.get(`/agent/moderate/${reportId}/result`, { timeout: 15000 })

/** 取单条评论详情（人工复核时查看被举报评论原文） */
export const getCommentDetail = (commentId: number) =>
  http.get(`/content/comments/${commentId}`)

/** 取某用户最新的禁言记录（含 AI 证据，人工复核时展示） */
export const getLatestMute = (userId: number) =>
  http.get('/agent/mute/latest', { params: { userId } })

/** 管理员手动禁言用户（后端 @RequestParam，用 query params 传参）
 *  reportId 可选：来自人工复核禁言时传入，后端会同步逻辑隐藏被举报内容 */
export const manualMuteUser = (userId: number, reason: string, days: number, reportId?: number) =>
  http.post('/agent/mute', null, { params: { userId, reason, days, reportId } })

/** 更新举报状态（后端 @RequestParam，用 query params 传参） */
export const updateReportStatus = (reportId: number, status: number, reviewNote?: string) =>
  http.put(`/content/reports/${reportId}`, null, { params: { status, reviewNote } })
