package com.shillguard.agent.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shillguard.agent.cache.ContentCacheInvalidator;
import com.shillguard.agent.dto.*;
import com.shillguard.agent.mapper.*;
import com.shillguard.agent.service.AgentService;
import com.shillguard.agent.service.ModerateJobStore;
import com.shillguard.agent.service.ModeratePollWorker;
import com.shillguard.common.entity.AgentMuteRecord;
import com.shillguard.common.entity.ContentComment;
import com.shillguard.common.entity.ContentPost;
import com.shillguard.common.entity.ContentReport;
import com.shillguard.common.entity.SysUser;
import com.shillguard.common.entity.UserRiskRecord;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.ResultCode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.client.RequestCallback;
import org.springframework.web.client.ResponseExtractor;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.*;

@Slf4j
@Service
@RequiredArgsConstructor
public class AgentServiceImpl implements AgentService {

    private final MuteRecordMapper muteRecordMapper;
    private final ContentReportMapper contentReportMapper;
    private final ContentCommentMapper contentCommentMapper;
    private final ContentPostMapper contentPostMapper;
    private final AgentSysUserMapper agentSysUserMapper;
    private final UserRiskRecordMapper userRiskRecordMapper;
    private final RabbitTemplate rabbitTemplate;
    private final RestTemplate restTemplate;
    private final org.springframework.transaction.PlatformTransactionManager transactionManager;
    private final ModerateJobStore moderateJobStore;
    private final ModeratePollWorker moderatePollWorker;
    private final ContentCacheInvalidator contentCacheInvalidator;

    @Value("${agent.python-service-url}")
    private String pythonServiceUrl;

    /** 自动禁言默认天数（与 Python 端 moderation_mute_days_default 对齐） */
    @Value("${agent.mute-days-default:30}")
    private int muteDaysDefault;

    @Override
    public void triggerDetect() {
        try {
            rabbitTemplate.convertAndSend("shillguard.exchange", "agent.detect.trigger", "manual");
            log.info("水军检测任务已触发");
        } catch (Exception e) {
            log.error("触发检测任务失败: {}", e.getMessage());
            try {
                restTemplate.postForObject(pythonServiceUrl + "/detect/trigger", null, String.class);
            } catch (Exception ex) {
                log.error("HTTP调用Python服务失败: {}", ex.getMessage());
            }
        }
    }

    @Override
    public void manualMute(Long userId, String reason, Integer days, Long operatorId) {
        manualMute(userId, reason, days, operatorId, null);
    }

    @Override
    public void manualMute(Long userId, String reason, Integer days, Long operatorId, Long reportId) {
        AgentMuteRecord record = new AgentMuteRecord();
        record.setMutedUserId(userId);
        record.setReviewerUserId(operatorId);
        record.setMuteReason(reason);
        record.setMuteType(1);
        record.setMuteDays(days);
        record.setMuteStartTime(LocalDateTime.now());
        record.setMuteEndTime(LocalDateTime.now().plusDays(days));
        record.setStatus(1);
        // 若来自举报人工复核，记录关联评论ID
        if (reportId != null) {
            ContentReport report = contentReportMapper.selectById(reportId);
            if (report != null) {
                record.setReporterUserId(report.getReporterUserId());
                record.setRelatedCommentId(report.getReportedCommentId());
            }
        }
        muteRecordMapper.insert(record);

        // 同步更新 sys_user.status=1（禁言），否则用户仍可发帖/评论
        agentSysUserMapper.updateStatus(userId, 1);

        // 通知RabbitMQ更新用户状态（notify服务写站内通知给用户）
        rabbitTemplate.convertAndSend("shillguard.exchange", "user.mute", userId + "," + days);
        log.info("手动禁言执行: userId={}, days={}, operator={}, reportId={}", userId, days, operatorId, reportId);

        // 若来自举报，逻辑隐藏被举报内容（帖子/评论 status=1，前端自动不显示，管理员仍可见）
        if (reportId != null) {
            ContentReport report = contentReportMapper.selectById(reportId);
            if (report != null) {
                hideReportedContent(report);
            }
        }
        // 新规则：被禁言用户的全部评论逻辑隐藏（status=1），且禁言到期后不自动恢复
        hideAllCommentsOfUser(userId);
    }

    @Override
    public AgentMuteRecord getLatestMuteByUser(Long userId) {
        LambdaQueryWrapper<AgentMuteRecord> wrapper = new LambdaQueryWrapper<AgentMuteRecord>()
                .eq(AgentMuteRecord::getMutedUserId, userId)
                .orderByDesc(AgentMuteRecord::getCreatedTime)
                .last("LIMIT 1");
        return muteRecordMapper.selectOne(wrapper);
    }

    @Override
    public void unmute(Long muteId) {
        AgentMuteRecord record = new AgentMuteRecord();
        record.setMuteId(muteId);
        record.setStatus(2);
        muteRecordMapper.updateById(record);
        log.info("解除禁言: muteId={}", muteId);
    }

    /**
     * 受理 AI 审核：CAS 把举报打成处理中，提交 Python 后立刻返回。
     * 轮询与禁言落库在 moderateExecutor 线程完成，避免占满 Tomcat。
     */
    @Override
    public ModerateAcceptDTO submitModerate(Long reportId) {
        ContentReport report = contentReportMapper.selectById(reportId);
        if (report == null) {
            throw new BizException(ResultCode.NOT_FOUND.getCode(), "举报记录不存在: " + reportId);
        }

        ModerateJobVO existing = moderateJobStore.get(reportId);
        if (existing != null && "done".equals(existing.getStatus())) {
            return toAccept(existing);
        }
        if (existing != null && "processing".equals(existing.getStatus())
                && existing.getTaskId() != null) {
            if (moderateJobStore.tryLock(reportId)) {
                moderatePollWorker.pollAndComplete(reportId, existing.getTaskId());
            }
            return toAccept(existing);
        }

        if (!moderateJobStore.tryLock(reportId)) {
            ModerateJobVO racing = moderateJobStore.get(reportId);
            if (racing != null) {
                return toAccept(racing);
            }
            throw new BizException(ResultCode.FAIL.getCode(), "该举报正在审核中，请稍后刷新");
        }

        boolean started = false;
        try {
            int cas = contentReportMapper.casMarkProcessing(reportId);
            if (cas == 0 && (report.getStatus() == null || report.getStatus() != 1)) {
                throw new BizException(ResultCode.FAIL.getCode(), "该举报已处理，无需重复审核");
            }

            ModerateRequestDTO request = buildRequestFromReport(report);
            String submitUrl = pythonServiceUrl + "/ai/moderate";
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            ModerateSubmitResponseDTO submit = restTemplate.postForObject(
                    submitUrl, new HttpEntity<>(request, headers), ModerateSubmitResponseDTO.class);
            if (submit == null || submit.getTaskId() == null) {
                throw new BizException(ResultCode.SERVER_ERROR.getCode(), "AI审核服务调用失败");
            }

            moderateJobStore.markProcessing(reportId, submit.getTaskId());
            started = true;
            moderatePollWorker.pollAndComplete(reportId, submit.getTaskId());

            ModerateAcceptDTO dto = new ModerateAcceptDTO();
            dto.setReportId(reportId);
            dto.setTaskId(submit.getTaskId());
            dto.setStatus("processing");
            return dto;
        } catch (RestClientException e) {
            log.error("提交Python审核失败: reportId={}, err={}", reportId, e.getMessage());
            throw new BizException(ResultCode.SERVER_ERROR.getCode(), "AI审核服务调用失败");
        } finally {
            if (!started) {
                moderateJobStore.unlock(reportId);
            }
        }
    }

    @Override
    public ModerateJobVO getModerateJob(Long reportId) {
        ModerateJobVO job = moderateJobStore.get(reportId);
        if (job != null) {
            return job;
        }
        ModerateJobVO empty = new ModerateJobVO();
        empty.setReportId(reportId);
        empty.setStatus("processing");
        return empty;
    }

    @Override
    public void finishModerate(Long reportId, ModerateResultDTO result) {
        if (result == null) {
            log.warn("审核完成但结果为空: reportId={}", reportId);
            return;
        }
        ContentReport report = contentReportMapper.selectById(reportId);
        if (report == null) {
            log.warn("审核完成但举报不存在: reportId={}", reportId);
            return;
        }
        applyAction(report, result);
    }

    private static ModerateAcceptDTO toAccept(ModerateJobVO job) {
        ModerateAcceptDTO dto = new ModerateAcceptDTO();
        dto.setReportId(job.getReportId());
        dto.setTaskId(job.getTaskId());
        dto.setStatus(job.getStatus());
        return dto;
    }

    /**
     * 异步调用 Python 审核 Agent（仅后台 worker 使用）：
     * <ol>
     *   <li>POST /ai/moderate → 立即拿到 taskId</li>
     *   <li>每 2s 轮询一次 GET /ai/moderate/result/{taskId}，最多 60 次（120s）</li>
     * </ol>
     */
    private ModerateRequestDTO buildRequestFromReport(ContentReport report) {
        ModerateRequestDTO req = new ModerateRequestDTO();
        req.setReportId(report.getReportId());
        req.setReportCategory(report.getReportCategory() == null ? 0 : report.getReportCategory());

        List<String> contentList;
        String contentType;
        Long reportedUserId = report.getReportedUserId();

        if (report.getReportedCommentId() != null) {
            // 举报评论
            ContentComment comment = contentCommentMapper.selectById(report.getReportedCommentId());
            if (comment == null) {
                throw new BizException(ResultCode.NOT_FOUND.getCode(), "被举报评论不存在");
            }
            contentType = "comment";
            contentList = Collections.singletonList(comment.getContent());
            if (reportedUserId == null) {
                reportedUserId = comment.getUserId();
            }
        } else if (report.getReportedPostId() != null) {
            // 举报帖子
            ContentPost post = contentPostMapper.selectById(report.getReportedPostId());
            if (post == null) {
                throw new BizException(ResultCode.NOT_FOUND.getCode(), "被举报帖子不存在");
            }
            contentType = "post";
            // 标题+正文拼成一条内容给 LLM 审核
            contentList = Collections.singletonList(post.getTitle() + "\n" + post.getContent());
            if (reportedUserId == null) {
                reportedUserId = post.getUserId();
            }
        } else {
            // 既没有评论ID也没有帖子ID，无法审核
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "举报记录缺少被举报内容标识");
        }

        req.setContentType(contentType);
        req.setContentList(contentList);
        req.setReportedUserId(reportedUserId);
        return req;
    }

    /**
     * 异步调用 Python 审核 Agent：
     * <ol>
     *   <li>POST /ai/moderate → 立即拿到 taskId（耗时 < 100ms）</li>
     *   <li>每 2s 轮询一次 GET /ai/moderate/result/{taskId}，最多 60 次（120s）</li>
     *   <li>status=done 时返回结果；status=error 或超时返回 null</li>
     * </ol>
     */
    private ModerateResultDTO callPythonModerate(ModerateRequestDTO request) {
        // Step 1: 提交任务，获取 taskId
        String submitUrl = pythonServiceUrl + "/ai/moderate";
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        HttpEntity<ModerateRequestDTO> entity = new HttpEntity<>(request, headers);

        ModerateSubmitResponseDTO submit;
        try {
            submit = restTemplate.postForObject(submitUrl, entity, ModerateSubmitResponseDTO.class);
        } catch (RestClientException e) {
            log.error("提交Python审核任务失败: url={}, error={}", submitUrl, e.getMessage());
            return null;
        }
        if (submit == null || submit.getTaskId() == null) {
            log.error("Python审核服务返回空 taskId");
            return null;
        }

        String taskId = submit.getTaskId();
        String pollUrl = pythonServiceUrl + "/ai/moderate/result/" + taskId;
        log.info("审核任务已提交: reportId={}, taskId={}", request.getReportId(), taskId);

        // Step 2: 轮询结果，最多等待 120s（60 次 × 2s）
        int maxRetries = 60;
        for (int i = 0; i < maxRetries; i++) {
            try {
                Thread.sleep(2_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                log.warn("审核轮询被中断: taskId={}", taskId);
                return null;
            }
            try {
                ModerateTaskResultDTO poll = restTemplate.getForObject(pollUrl, ModerateTaskResultDTO.class);
                if (poll == null) continue;

                switch (poll.getStatus()) {
                    case "done" -> {
                        ModerateResultDTO result = poll.getResult();
                        log.info("AI审核完成: reportId={}, taskId={}, action={}, score={}",
                                request.getReportId(), taskId,
                                result == null ? "null" : result.getAction(),
                                result == null ? "null" : result.getAnomalyScore());
                        return result;
                    }
                    case "error" -> {
                        log.error("Python审核任务执行失败: taskId={}, error={}", taskId, poll.getError());
                        return null;
                    }
                    case "not_found" -> {
                        log.error("Python审核任务已丢失（重启或超期）: taskId={}", taskId);
                        return null;
                    }
                    // pending / processing：继续轮询
                }
            } catch (RestClientException e) {
                log.warn("轮询审核结果异常（将重试）: taskId={}, error={}", taskId, e.getMessage());
            }
        }

        log.error("AI审核超时（120s）: taskId={}, reportId={}", taskId, request.getReportId());
        return null;
    }

    /**
     * 根据 Python 返回的 action 执行后续动作并更新举报状态。
     * DB 写操作通过 TransactionTemplate 包裹，保证原子性。
     * <ul>
     *   <li>auto_mute：写入禁言记录(含证据) + 更新 sys_user.status=1 + 发MQ通知 + 举报status=4</li>
     *   <li>manual_review：举报status=4（待人工复核，证据存reviewNote）</li>
     *   <li>none：举报status=2（已忽略）</li>
     * </ul>
     */
    private void applyAction(ContentReport report, ModerateResultDTO result) {
        String action = result.getAction();
        final Long reportedUserId = result.getReportedUserId() != null
                ? result.getReportedUserId()
                : report.getReportedUserId();

        new TransactionTemplate(transactionManager).execute(txStatus -> {
        ContentReport locked = contentReportMapper.selectForUpdate(report.getReportId());
        if (locked == null) {
            return null;
        }
        if (locked.getStatus() != null && locked.getStatus() != 0 && locked.getStatus() != 1) {
            log.info("审核结果已落库，跳过重复处置: reportId={}, status={}", locked.getReportId(), locked.getStatus());
            return null;
        }
        if ("auto_mute".equalsIgnoreCase(action)) {
            // 1) 写入禁言记录（muteType=0 表示Agent自动，含完整证据）
            AgentMuteRecord record = new AgentMuteRecord();
            record.setMutedUserId(reportedUserId);
            record.setReporterUserId(report.getReporterUserId());
            record.setRelatedCommentId(report.getReportedCommentId());
            record.setMuteReason(buildMuteReason(result));
            record.setEvidenceDetail(result.getEvidenceDetail());
            record.setMuteType(0); // 0=Agent自动
            record.setMuteDays(muteDaysDefault);
            record.setMuteStartTime(LocalDateTime.now());
            record.setMuteEndTime(LocalDateTime.now().plusDays(muteDaysDefault));
            record.setStatus(1); // 1=禁言中
            muteRecordMapper.insert(record);

            // 2) 更新用户状态为禁言
            agentSysUserMapper.updateStatus(reportedUserId, 1);

            // 3) 发MQ通知（notify服务会写站内通知给用户）
            try {
                rabbitTemplate.convertAndSend(
                        "shillguard.exchange", "user.mute",
                        reportedUserId + "," + muteDaysDefault);
            } catch (Exception e) {
                log.warn("禁言MQ通知发送失败，不影响主流程: {}", e.getMessage());
            }

            // 4) 举报状态置4（已转Agent处理）
            updateReportStatus(report, 4, "AI自动禁言" + muteDaysDefault + "天，分数:"
                    + result.getAnomalyScore() + "，" + result.getEvidenceSummary());
            // 5) 逻辑隐藏被举报内容（帖子/评论 status=1）
            hideReportedContent(report);
            // 6) 被禁言用户的全部评论逻辑隐藏（status=1），禁言到期后也不自动恢复
            hideAllCommentsOfUser(reportedUserId);
            log.info("AI审核→自动禁言: userId={}, days={}, score={}",
                    reportedUserId, muteDaysDefault, result.getAnomalyScore());

        } else if ("manual_review".equalsIgnoreCase(action)) {
            // 不自动禁言，标记举报为"已转Agent"待人工复核，把证据摘要存入reviewNote
            updateReportStatus(report, 4, "待人工复核，分数:"
                    + result.getAnomalyScore() + "，" + result.getEvidenceSummary());
            log.info("AI审核→待人工复核: reportId={}, score={}", report.getReportId(), result.getAnomalyScore());

        } else {
            // none：内容正常，举报忽略
            updateReportStatus(report, 2, "AI判定无违规，分数:"
                    + result.getAnomalyScore() + "，" + result.getEvidenceSummary());
            log.info("AI审核→无违规: reportId={}, score={}", report.getReportId(), result.getAnomalyScore());
        }
        return null;
        });
    }

    /**
     * 逻辑隐藏被举报内容：把对应帖子/评论的 status 置 1（已删除）。
     * 前台列表/详情查询已过滤 status=0，故被禁言用户的违规内容对普通用户不可见；
     * 管理员通过 shill-admin 的"不限 status"接口仍可查看全部内容。
     */
    private void hideReportedContent(ContentReport report) {
        try {
            if (report.getReportedCommentId() != null) {
                ContentComment existing = contentCommentMapper.selectById(report.getReportedCommentId());
                ContentComment cUpdate = new ContentComment();
                cUpdate.setCommentId(report.getReportedCommentId());
                cUpdate.setStatus(1);
                contentCommentMapper.updateById(cUpdate);
                if (existing != null) {
                    contentCacheInvalidator.onPostDetailStale(existing.getPostId());
                }
                log.info("已逻辑隐藏被举报评论: commentId={}", report.getReportedCommentId());
            } else if (report.getReportedPostId() != null) {
                ContentPost pUpdate = new ContentPost();
                pUpdate.setPostId(report.getReportedPostId());
                pUpdate.setStatus(1);
                contentPostMapper.updateById(pUpdate);
                contentCacheInvalidator.onPostHidden(report.getReportedPostId());
                log.info("已逻辑隐藏被举报帖子: postId={}", report.getReportedPostId());
            }
        } catch (Exception e) {
            log.warn("隐藏被举报内容失败，不影响禁言主流程: {}", e.getMessage());
        }
    }

    /** 拼接禁言原因摘要（写入 mute_reason 字段） */
    private String buildMuteReason(ModerateResultDTO result) {
        StringBuilder sb = new StringBuilder();
        if (result.getViolatedRules() != null && !result.getViolatedRules().isEmpty()) {
            sb.append("违反规则:").append(String.join(";", result.getViolatedRules())).append("。");
        }
        if (result.getViolatedLaws() != null && !result.getViolatedLaws().isEmpty()) {
            sb.append("违反法律:").append(String.join(";", result.getViolatedLaws())).append("。");
        }
        if (sb.length() == 0) {
            sb.append(result.getEvidenceSummary() == null ? "AI判定违规" : result.getEvidenceSummary());
        }
        return sb.toString();
    }

    /** 更新举报状态与审核备注 */
    private void updateReportStatus(ContentReport report, int status, String reviewNote) {
        LambdaUpdateWrapper<ContentReport> wrapper = new LambdaUpdateWrapper<ContentReport>()
                .eq(ContentReport::getReportId, report.getReportId())
                .set(ContentReport::getStatus, status)
                .set(reviewNote != null, ContentReport::getReviewNote, reviewNote)
                .set(ContentReport::getUpdatedTime, LocalDateTime.now());
        contentReportMapper.update(null, wrapper);
    }

    // ================================================================
    //  识别恶意行为用户检测
    // ================================================================

    @Override
    @Transactional(rollbackFor = Exception.class)
    public DetectResultVO detectMaliciousUsers() {
        // 1. 收集今日所有 status=0 的帖子与评论，按 userId 分组
        LocalDateTime startOfDay = LocalDate.now().atStartOfDay();
        List<ContentPost> posts = contentPostMapper.selectList(
                new LambdaQueryWrapper<ContentPost>()
                        .eq(ContentPost::getStatus, 0)
                        .ge(ContentPost::getCreatedTime, startOfDay));
        List<ContentComment> comments = contentCommentMapper.selectList(
                new LambdaQueryWrapper<ContentComment>()
                        .eq(ContentComment::getStatus, 0)
                        .ge(ContentComment::getCreatedTime, startOfDay));

        // userId -> 内容列表
        Map<Long, List<String>> userContentMap = new LinkedHashMap<>();
        for (ContentPost p : posts) {
            if (p.getUserId() == null) continue;
            userContentMap.computeIfAbsent(p.getUserId(), k -> new ArrayList<>())
                    .add("[帖子]" + (p.getTitle() == null ? "" : p.getTitle()) + " " + (p.getContent() == null ? "" : p.getContent()));
        }
        for (ContentComment c : comments) {
            if (c.getUserId() == null) continue;
            userContentMap.computeIfAbsent(c.getUserId(), k -> new ArrayList<>())
                    .add("[评论]" + (c.getContent() == null ? "" : c.getContent()));
        }
        log.info("恶意行为检测启动: 今日帖子{} 评论{} 涉及用户{}",
                posts.size(), comments.size(), userContentMap.size());

        DetectResultVO vo = new DetectResultVO();
        if (userContentMap.isEmpty()) {
            vo.setTotalUsers(0);
            vo.setWarningCount(0);
            vo.setMutedCount(0);
            vo.setResults(Collections.emptyList());
            return vo;
        }

        // 2. 构造请求体
        DetectUsersRequestDTO request = new DetectUsersRequestDTO();
        List<UserContentDTO> userContentList = new ArrayList<>();
        for (Map.Entry<Long, List<String>> e : userContentMap.entrySet()) {
            UserContentDTO uc = new UserContentDTO();
            uc.setUserId(e.getKey());
            uc.setContentList(e.getValue());
            userContentList.add(uc);
        }
        request.setUsers(userContentList);

        // 3. 调用 Python 检测算法 POST /ai/detect-users（打分）
        DetectUsersResponseDTO response = callPythonDetect(request);
        List<UserScoreResultDTO> results = (response == null || response.getResults() == null)
                ? Collections.emptyList() : response.getResults();

        // 3.5 对高危用户(score>=0.9) 调用证据生成 Agent POST /ai/detect-evidence，
        //     用专用证据 agent 的输出覆盖打分阶段的占位证据（更贴切、含具体违规条目）
        List<UserScoreResultDTO> highRisk = new ArrayList<>();
        for (UserScoreResultDTO r : results) {
            float score = r.getAnomalyScore() == null ? 0f : r.getAnomalyScore();
            if (score >= 0.9f) {
                highRisk.add(r);
            }
        }
        Map<Long, UserEvidenceResultDTO> evidenceMap = callEvidenceAgent(highRisk);
        for (UserScoreResultDTO r : highRisk) {
            UserEvidenceResultDTO ev = evidenceMap.get(r.getUserId());
            if (ev != null) {
                if (ev.getEvidenceDetail() != null && !ev.getEvidenceDetail().isEmpty()) {
                    r.setEvidenceDetail(ev.getEvidenceDetail());
                }
                r.setViolatingItems(ev.getViolatingItems());
            }
        }

        // 4. 分级处置
        int warningCount = 0;
        int mutedCount = 0;
        for (UserScoreResultDTO r : results) {
            float score = r.getAnomalyScore() == null ? 0f : r.getAnomalyScore();
            if (score > 0.8f && score < 0.9f) {
                // 预警：写风险记录 + sys_user.warning_level=1
                saveRiskRecord(r, 1, null);
                agentSysUserMapper.updateWarningLevel(r.getUserId(), 1);
                warningCount++;
                log.info("检测→预警: userId={}, score={}", r.getUserId(), score);
            } else if (score >= 0.9f) {
                // 高危：禁言7天 + 证据 agent 生成的完整证据落库
                String evidence = r.getEvidenceDetail();
                saveRiskRecord(r, 2, evidence);
                agentSysUserMapper.updateWarningLevel(r.getUserId(), 2);
                muteForDetection(r, evidence, 7);
                mutedCount++;
                log.info("检测→禁言7天: userId={}, score={}", r.getUserId(), score);
            } else {
                // 正常用户不写记录，但清掉历史预警级别（避免误报残留）
                agentSysUserMapper.updateWarningLevel(r.getUserId(), 0);
            }
        }

        vo.setTotalUsers(results.size());
        vo.setWarningCount(warningCount);
        vo.setMutedCount(mutedCount);
        vo.setResults(results);
        log.info("恶意行为检测完成: 检测{}人 预警{}人 禁言{}人", results.size(), warningCount, mutedCount);
        return vo;
    }

    /** 调用 Python 检测算法 */
    private DetectUsersResponseDTO callPythonDetect(DetectUsersRequestDTO request) {
        String url = pythonServiceUrl + "/ai/detect-users";
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        HttpEntity<DetectUsersRequestDTO> entity = new HttpEntity<>(request, headers);
        try {
            return restTemplate.postForObject(url, entity, DetectUsersResponseDTO.class);
        } catch (RestClientException e) {
            log.error("调用Python检测服务失败: url={}, error={}", url, e.getMessage());
            return null;
        }
    }

    /**
     * 调用证据生成 Agent（POST /ai/detect-evidence），对高危用户批量生成完整证据。
     * 返回 userId -> 证据结果 的映射；调用失败或无高危用户时返回空 map。
     */
    private Map<Long, UserEvidenceResultDTO> callEvidenceAgent(List<UserScoreResultDTO> highRisk) {
        if (highRisk.isEmpty()) {
            return Collections.emptyMap();
        }
        DetectEvidenceRequestDTO req = new DetectEvidenceRequestDTO();
        List<UserEvidenceInputDTO> inputs = new ArrayList<>();
        for (UserScoreResultDTO r : highRisk) {
            UserEvidenceInputDTO in = new UserEvidenceInputDTO();
            in.setUserId(r.getUserId());
            in.setContentList(r.getContentList());
            in.setAnomalyScore(r.getAnomalyScore());
            in.setViolatedRules(r.getViolatedRules());
            in.setViolatedLaws(r.getViolatedLaws());
            in.setJudgment(r.getEvidenceSummary());
            inputs.add(in);
        }
        req.setUsers(inputs);

        String url = pythonServiceUrl + "/ai/detect-evidence";
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        HttpEntity<DetectEvidenceRequestDTO> entity = new HttpEntity<>(req, headers);
        try {
            DetectEvidenceResponseDTO resp = restTemplate.postForObject(url, entity, DetectEvidenceResponseDTO.class);
            Map<Long, UserEvidenceResultDTO> map = new LinkedHashMap<>();
            if (resp != null && resp.getResults() != null) {
                for (UserEvidenceResultDTO er : resp.getResults()) {
                    map.put(er.getUserId(), er);
                }
            }
            log.info("证据Agent完成: 请求{}人, 返回{}人", highRisk.size(), map.size());
            return map;
        } catch (RestClientException e) {
            log.error("调用证据Agent失败: url={}, error={}", url, e.getMessage());
            return Collections.emptyMap();
        }
    }

    /** 写入用户风险记录（预警/高危） */
    private void saveRiskRecord(UserScoreResultDTO r, int level, String evidence) {
        UserRiskRecord rec = new UserRiskRecord();
        rec.setUserId(r.getUserId());
        rec.setAnomalyScore(r.getAnomalyScore());
        rec.setWarningLevel(level);
        rec.setContentSnapshot(String.join("\n", r.getContentList() == null ? Collections.emptyList() : r.getContentList()));
        rec.setEvidenceDetail(evidence);
        rec.setDetectTime(LocalDateTime.now());
        userRiskRecordMapper.insert(rec);
    }

    /**
     * 检测高危用户禁言7天：写 agent_mute_record(含证据) + sys_user.status=1 + MQ通知。
     * 与举报流不同：本流程不自动隐藏帖子/评论（用户决定）。
     * 证据优先用证据 agent 的输出；若证据 agent 挑出了具体违规条目，追加到证据末尾。
     */
    private void muteForDetection(UserScoreResultDTO r, String evidence, int days) {
        // 把具体违规条目追加进证据，便于申诉复核
        String fullEvidence = evidence;
        if (r.getViolatingItems() != null && !r.getViolatingItems().isEmpty()) {
            String items = "\n\n## 具体违规内容\n" + String.join("\n", r.getViolatingItems());
            fullEvidence = (evidence == null ? "" : evidence) + items;
        }
        AgentMuteRecord record = new AgentMuteRecord();
        record.setMutedUserId(r.getUserId());
        record.setMuteReason("恶意行为检测：异常分数" + r.getAnomalyScore() + "，"
                + (r.getEvidenceSummary() == null ? "" : r.getEvidenceSummary()));
        record.setEvidenceDetail(fullEvidence);
        record.setMuteType(0); // 0=Agent自动
        record.setMuteDays(days);
        record.setMuteStartTime(LocalDateTime.now());
        record.setMuteEndTime(LocalDateTime.now().plusDays(days));
        record.setStatus(1);
        muteRecordMapper.insert(record);

        agentSysUserMapper.updateStatus(r.getUserId(), 1);

        try {
            rabbitTemplate.convertAndSend("shillguard.exchange", "user.mute",
                    r.getUserId() + "," + days);
        } catch (Exception e) {
            log.warn("禁言MQ通知发送失败，不影响主流程: {}", e.getMessage());
        }

        // 被禁言用户：全部帖子+评论逻辑隐藏（status=1），禁言到期后不恢复
        hideAllCommentsOfUser(r.getUserId());
    }

    /**
     * 被禁言/封禁用户：逻辑隐藏其全部帖子与评论（status 0→1）。
     * 普通用户前端不再展示其任何帖子和评论；禁言到期后不自动恢复（status 保持1）。
     * 管理端列表不过滤 status，管理员仍可见。
     */
    private void hideAllCommentsOfUser(Long userId) {
        if (userId == null) {
            return;
        }
        int c = contentCommentMapper.update(null,
                new LambdaUpdateWrapper<ContentComment>()
                        .eq(ContentComment::getUserId, userId)
                        .eq(ContentComment::getStatus, 0)
                        .set(ContentComment::getStatus, 1));
        int p = contentPostMapper.update(null,
                new LambdaUpdateWrapper<ContentPost>()
                        .eq(ContentPost::getUserId, userId)
                        .eq(ContentPost::getStatus, 0)
                        .set(ContentPost::getStatus, 1));
        log.info("用户{}被禁言/封禁，逻辑隐藏其全部评论{}条、帖子{}条", userId, c, p);
    }

    /**
     * 隐藏证据 agent 挑出的具体违规内容：按 violatingItems 文本匹配该用户的帖子/评论，
     * 命中的置 status=1（逻辑隐藏，普通用户不可见，管理员仍可见）。
     * 只隐藏命中的具体条目，该用户其它帖子/评论不受影响。
     */
    private void hideViolatingContent(Long userId, List<String> violatingItems) {
        if (userId == null || violatingItems == null || violatingItems.isEmpty()) {
            return;
        }
        List<ContentPost> posts = contentPostMapper.selectList(
                new LambdaQueryWrapper<ContentPost>()
                        .eq(ContentPost::getUserId, userId)
                        .eq(ContentPost::getStatus, 0));
        List<ContentComment> comments = contentCommentMapper.selectList(
                new LambdaQueryWrapper<ContentComment>()
                        .eq(ContentComment::getUserId, userId)
                        .eq(ContentComment::getStatus, 0));

        int hidden = 0;
        for (String item : violatingItems) {
            if (item == null || item.isBlank()) continue;
            // 证据 agent 可能带 [帖子]/[评论] 前缀，去掉后用纯文本匹配
            String norm = item.replace("[帖子]", "").replace("[评论]", "").trim();
            if (norm.isEmpty()) continue;

            // 匹配帖子（标题+正文）
            for (ContentPost p : posts) {
                String postText = ((p.getTitle() == null ? "" : p.getTitle()) + " "
                        + (p.getContent() == null ? "" : p.getContent())).trim();
                if (!postText.isEmpty() && (postText.contains(norm) || norm.contains(postText))) {
                    ContentPost up = new ContentPost();
                    up.setPostId(p.getPostId());
                    up.setStatus(1);
                    contentPostMapper.updateById(up);
                    hidden++;
                    log.info("检测→隐藏违规帖子: postId={}, userId={}", p.getPostId(), userId);
                    break;
                }
            }
            // 匹配评论
            for (ContentComment c : comments) {
                String cText = c.getContent() == null ? "" : c.getContent().trim();
                if (!cText.isEmpty() && (cText.contains(norm) || norm.contains(cText))) {
                    ContentComment up = new ContentComment();
                    up.setCommentId(c.getCommentId());
                    up.setStatus(1);
                    contentCommentMapper.updateById(up);
                    hidden++;
                    log.info("检测→隐藏违规评论: commentId={}, userId={}", c.getCommentId(), userId);
                    break;
                }
            }
        }
        log.info("检测→违规内容隐藏完成: userId={}, 隐藏{}条", userId, hidden);
    }

    // ================================================================
    //  SSE 流式检测：实时把后端处理日志推送给前端
    // ================================================================

    /** 共享 JSON 序列化器（SSE 事件 data 序列化 + 解析 Python 返回）
     *  必须关闭 FAIL_ON_UNKNOWN_PROPERTIES：Python 端字段比 DTO 多时不抛异常。 */
    private final ObjectMapper streamMapper = new ObjectMapper()
            .configure(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    @Override
    public void detectMaliciousUsersStream(SseEmitter emitter) {
        // 检测耗时较长，在独立线程执行，通过 emitter 推送事件；Controller 立即返回 emitter
        Thread t = new Thread(() -> {
            try {
                runDetectStream(emitter);
                emitter.complete();
            } catch (Exception e) {
                log.error("流式检测异常", e);
                try {
                    sendEvent(emitter, "error", Map.of("msg", "检测异常: " + e.getMessage()));
                } catch (Exception ignored) {
                }
                emitter.completeWithError(e);
            }
        }, "detect-stream");
        t.setDaemon(true);
        t.start();
    }

    /**
     * 流式检测主流程：
     * 1. 收集今日内容（推送 stage/log）
     * 2. 调 Python /ai/detect-users-stream，逐用户中继 log/score 事件，并收集 results
     * 3. 高危用户调证据 Agent（推送 log）
     * 4. 分级处置（DB 写入包在事务里，推送 action）
     * 5. done 事件带汇总
     */
    private void runDetectStream(SseEmitter emitter) throws Exception {
        // ---- 1. 收集今日内容 ----
        sendEvent(emitter, "stage", Map.of("stage", "collect", "msg", "正在收集今日帖子与评论..."));
        LocalDateTime startOfDay = LocalDate.now().atStartOfDay();
        List<ContentPost> posts = contentPostMapper.selectList(
                new LambdaQueryWrapper<ContentPost>()
                        .eq(ContentPost::getStatus, 0)
                        .ge(ContentPost::getCreatedTime, startOfDay));
        List<ContentComment> comments = contentCommentMapper.selectList(
                new LambdaQueryWrapper<ContentComment>()
                        .eq(ContentComment::getStatus, 0)
                        .ge(ContentComment::getCreatedTime, startOfDay));

        Map<Long, List<String>> userContentMap = new LinkedHashMap<>();
        for (ContentPost p : posts) {
            if (p.getUserId() == null) continue;
            userContentMap.computeIfAbsent(p.getUserId(), k -> new ArrayList<>())
                    .add("[帖子]" + (p.getTitle() == null ? "" : p.getTitle()) + " " + (p.getContent() == null ? "" : p.getContent()));
        }
        for (ContentComment c : comments) {
            if (c.getUserId() == null) continue;
            userContentMap.computeIfAbsent(c.getUserId(), k -> new ArrayList<>())
                    .add("[评论]" + (c.getContent() == null ? "" : c.getContent()));
        }
        sendEvent(emitter, "log", Map.of(
                "source", "java",
                "msg", String.format("收集完成：今日帖子%d 评论%d 涉及用户%d",
                        posts.size(), comments.size(), userContentMap.size())));

        if (userContentMap.isEmpty()) {
            sendEvent(emitter, "done", Map.of(
                    "totalUsers", 0, "warningCount", 0, "mutedCount", 0,
                    "results", Collections.emptyList()));
            return;
        }

        // ---- 2. 构造请求并流式调用 Python ----
        DetectUsersRequestDTO request = new DetectUsersRequestDTO();
        List<UserContentDTO> userContentList = new ArrayList<>();
        for (Map.Entry<Long, List<String>> e : userContentMap.entrySet()) {
            UserContentDTO uc = new UserContentDTO();
            uc.setUserId(e.getKey());
            uc.setContentList(e.getValue());
            userContentList.add(uc);
        }
        request.setUsers(userContentList);

        sendEvent(emitter, "stage", Map.of("stage", "scoring", "msg", "调用 Python 检测算法，逐用户打分..."));
        List<UserScoreResultDTO> results = callPythonDetectStream(emitter, request);
        if (results.isEmpty()) {
            sendEvent(emitter, "log", Map.of(
                    "source", "java", "level", "error",
                    "msg", "Python 检测服务调用失败或未返回结果"));
        }

        // ---- 3. 高危用户调证据 Agent ----
        List<UserScoreResultDTO> highRisk = new ArrayList<>();
        for (UserScoreResultDTO r : results) {
            float score = r.getAnomalyScore() == null ? 0f : r.getAnomalyScore();
            if (score >= 0.9f) {
                highRisk.add(r);
            }
        }
        if (!highRisk.isEmpty()) {
            sendEvent(emitter, "stage", Map.of(
                    "stage", "evidence",
                    "msg", "高危用户" + highRisk.size() + "人，调用证据生成 Agent..."));
            Map<Long, UserEvidenceResultDTO> evidenceMap = callEvidenceAgent(highRisk);
            sendEvent(emitter, "log", Map.of(
                    "source", "java",
                    "msg", "证据 Agent 完成：请求" + highRisk.size() + "人，返回" + evidenceMap.size() + "人"));
            for (UserScoreResultDTO r : highRisk) {
                UserEvidenceResultDTO ev = evidenceMap.get(r.getUserId());
                if (ev != null) {
                    if (ev.getEvidenceDetail() != null && !ev.getEvidenceDetail().isEmpty()) {
                        r.setEvidenceDetail(ev.getEvidenceDetail());
                    }
                    r.setViolatingItems(ev.getViolatingItems());
                }
            }
        }

        // ---- 4. 分级处置（DB 写入包在事务里） ----
        sendEvent(emitter, "stage", Map.of("stage", "apply", "msg", "分级处置：预警 / 禁言 + 落库..."));
        final int[] counts = new int[2]; // [warningCount, mutedCount]
        final List<UserScoreResultDTO> finalResults = results;
        new TransactionTemplate(transactionManager).execute(status -> {
            int warn = 0, mute = 0;
            for (UserScoreResultDTO r : finalResults) {
                float score = r.getAnomalyScore() == null ? 0f : r.getAnomalyScore();
                // muteAction 优先（新级联逻辑）；anomalyScore 兜底（遗留打分路径）
                String muteAction = r.getMuteAction() != null ? r.getMuteAction() : "none";
                boolean isMute7 = "mute_7days".equals(muteAction) || score >= 0.9f;
                boolean isMute3 = "mute_3days".equals(muteAction);
                boolean isWarn  = !isMute7 && !isMute3 && score > 0.8f;
                int muteDays    = isMute7 ? 7 : 3;
                try {
                    if (isMute7 || isMute3) {
                        String evidence = r.getEvidenceDetail();
                        saveRiskRecord(r, 2, evidence);
                        agentSysUserMapper.updateWarningLevel(r.getUserId(), 2);
                        muteForDetection(r, evidence, muteDays);
                        mute++;
                        safeSend(emitter, "action", Map.of(
                                "userId", r.getUserId(), "action", "mute",
                                "score", score, "days", muteDays,
                                "muteAction", muteAction,
                                "msg", "禁言" + muteDays + "天 + 证据落库 + warning_level=2"));
                    } else if (isWarn) {
                        saveRiskRecord(r, 1, null);
                        agentSysUserMapper.updateWarningLevel(r.getUserId(), 1);
                        warn++;
                        safeSend(emitter, "action", Map.of(
                                "userId", r.getUserId(), "action", "warning",
                                "score", score, "msg", "预警：写风险记录 + warning_level=1"));
                    } else {
                        agentSysUserMapper.updateWarningLevel(r.getUserId(), 0);
                    }
                } catch (Exception ex) {
                    safeSend(emitter, "log", Map.of(
                            "source", "java", "level", "error",
                            "userId", r.getUserId(),
                            "msg", "处置失败: " + ex.getMessage()));
                }
            }
            counts[0] = warn;
            counts[1] = mute;
            return null;
        });

        // ---- 5. done ----
        DetectResultVO vo = new DetectResultVO();
        vo.setTotalUsers(results.size());
        vo.setWarningCount(counts[0]);
        vo.setMutedCount(counts[1]);
        vo.setResults(results);
        Map<String, Object> doneData = new LinkedHashMap<>();
        doneData.put("totalUsers", vo.getTotalUsers());
        doneData.put("warningCount", vo.getWarningCount());
        doneData.put("mutedCount", vo.getMutedCount());
        doneData.put("results", vo.getResults());
        sendEvent(emitter, "done", doneData);
        log.info("流式检测完成: 检测{}人 预警{}人 禁言{}人", results.size(), counts[0], counts[1]);
    }

    /**
     * 流式调用 Python POST /ai/detect-users-stream：
     * 用 RestTemplate.execute 的 ResponseExtractor 逐行读取 SSE 流，
     * 把 Python 的 log/score 事件中继给前端 emitter，并在 done 事件里解析出 results。
     */
    private List<UserScoreResultDTO> callPythonDetectStream(SseEmitter emitter, DetectUsersRequestDTO request) {
        String url = pythonServiceUrl + "/ai/detect-users-stream";
        List<UserScoreResultDTO> results = new ArrayList<>();

        // 流式调用可能持续数分钟（多用户×LLM+RAG），用独立的长超时 RestTemplate，
        // 不复用共享 bean 的 90s 读超时（SSE 事件间隔若超 90s 会触发超时）。
        SimpleClientHttpRequestFactory streamFactory = new SimpleClientHttpRequestFactory();
        streamFactory.setConnectTimeout(5_000);
        streamFactory.setReadTimeout(600_000); // 10 分钟
        RestTemplate streamRest = new RestTemplate(streamFactory);

        RequestCallback requestCallback = req -> {
            req.getHeaders().setContentType(MediaType.APPLICATION_JSON);
            streamMapper.writeValue(req.getBody(), request);
        };

        ResponseExtractor<Void> responseExtractor = response -> {
            try (InputStream is = response.getBody();
                 BufferedReader reader = new BufferedReader(
                         new InputStreamReader(is, StandardCharsets.UTF_8))) {
                String line;
                String currentEvent = "message";
                StringBuilder dataBuilder = new StringBuilder();
                while ((line = reader.readLine()) != null) {
                    if (line.startsWith("event:")) {
                        currentEvent = line.substring(6).trim();
                    } else if (line.startsWith("data:")) {
                        // data: 后可能有一个前导空格
                        String d = line.substring(5);
                        if (d.startsWith(" ")) d = d.substring(1);
                        dataBuilder.append(d);
                    } else if (line.isEmpty()) {
                        // 空行 = 一条 SSE 事件结束
                        if (dataBuilder.length() > 0) {
                            String data = dataBuilder.toString();
                            dataBuilder.setLength(0);
                            handlePythonEvent(emitter, currentEvent, data, results);
                        }
                        currentEvent = "message";
                    }
                }
            }
            return null;
        };

        try {
            streamRest.execute(url, HttpMethod.POST, requestCallback, responseExtractor);
        } catch (Exception e) {
            log.error("流式调用Python检测失败: url={}, error={}", url, e.getMessage());
            safeSend(emitter, "log", Map.of(
                    "source", "java", "level", "error",
                    "msg", "调用 Python 检测服务失败: " + e.getMessage()));
        }
        return results;
    }

    /** 处理从 Python 收到的一条 SSE 事件：中继或解析。 */
    private void handlePythonEvent(SseEmitter emitter, String event, String data,
                                   List<UserScoreResultDTO> results) {
        try {
            switch (event) {
                case "log":
                case "score":
                case "stage":
                    // 直接中继给前端（保持原始 event 与 data）
                    emitter.send(SseEmitter.event().name(event).data(data));
                    break;
                case "done":
                    // 解析 results 列表
                    JsonNode node = streamMapper.readTree(data);
                    JsonNode arr = node.get("results");
                    if (arr != null && arr.isArray()) {
                        for (JsonNode item : arr) {
                            results.add(streamMapper.treeToValue(item, UserScoreResultDTO.class));
                        }
                    }
                    break;
                case "error":
                    emitter.send(SseEmitter.event().name("log").data(data));
                    break;
                default:
                    break;
            }
        } catch (Exception e) {
            log.warn("中继Python事件失败: event={}, error={}", event, e.getMessage());
        }
    }

    /** 向 emitter 发送一条 SSE 事件（event name + JSON data）。 */
    private void sendEvent(SseEmitter emitter, String event, Object data) throws Exception {
        String json = streamMapper.writeValueAsString(data);
        emitter.send(SseEmitter.event().name(event).data(json));
    }

    /** 向 emitter 发送事件，吞掉异常（用于事务内发送，避免 IO 异常中断事务）。 */
    private void safeSend(SseEmitter emitter, String event, Object data) {
        try {
            sendEvent(emitter, event, data);
        } catch (Exception e) {
            log.warn("SSE发送失败(忽略): event={}, error={}", event, e.getMessage());
        }
    }
}
