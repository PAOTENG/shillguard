package com.shillguard.agent.service;

import com.shillguard.agent.dto.DetectResultVO;
import com.shillguard.agent.dto.ModerateAcceptDTO;
import com.shillguard.agent.dto.ModerateJobVO;
import com.shillguard.agent.dto.ModerateResultDTO;
import com.shillguard.common.entity.AgentMuteRecord;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

public interface AgentService {

    void triggerDetect();

    void manualMute(Long userId, String reason, Integer days, Long operatorId);

    /**
     * 手动禁言（带举报ID）：执行禁言的同时，逻辑隐藏该举报指向的帖子/评论。
     * 用于"人工复核→禁言"流程，确保被禁言用户的违规内容对普通用户不可见。
     *
     * @param userId     被禁言用户ID
     * @param reason     禁言原因
     * @param days       禁言天数
     * @param operatorId 操作人（管理员）ID
     * @param reportId   触发本次禁言的举报ID（可为 null，null 时不隐藏内容）
     */
    void manualMute(Long userId, String reason, Integer days, Long operatorId, Long reportId);

    void unmute(Long muteId);

    /**
     * 查询某用户最新的一条禁言记录（含 AI 证据），供管理员人工复核时展示。
     *
     * @param userId 被举报用户ID
     * @return 最新的禁言记录，没有则返回 null
     */
    AgentMuteRecord getLatestMuteByUser(Long userId);

    /**
     * 受理 AI 审核：立刻返回，不在 Tomcat 线程里等待 LLM。
     * 重复点击若任务仍在跑，返回同一 taskId。
     */
    ModerateAcceptDTO submitModerate(Long reportId);

    /** 前端轮询审核结果。 */
    ModerateJobVO getModerateJob(Long reportId);

    /** 后台 worker 在 Python 完成后落处置（幂等）。 */
    void finishModerate(Long reportId, ModerateResultDTO result);

    /**
     * 识别恶意行为用户：收集今日所有帖子+评论并按用户分组，调用 Python 检测算法
     * （POST /ai/detect-users，复用审核 graph）得到每用户的异常分数，再分级处置：
     * <ul>
     *   <li>0.8 &lt; score &lt; 0.9：写 user_risk_record(预警) + sys_user.warning_level=1</li>
     *   <li>score &gt;= 0.9：禁言7天 + 用审核 graph 生成完整证据，写 user_risk_record(高危)
     *       + sys_user.warning_level=2 + agent_mute_record(含证据)。不自动隐藏内容。</li>
     * </ul>
     *
     * @return 检测结果汇总（含每用户明细），用于前端弹窗展示
     */
    DetectResultVO detectMaliciousUsers();

    /**
     * 识别恶意行为用户（SSE 流式版本）：与 {@link #detectMaliciousUsers()} 逻辑一致，
     * 但通过 SseEmitter 实时把后端处理日志推送给前端：
     * <ul>
     *   <li>收集今日内容的统计</li>
     *   <li>逐用户打分过程中 Python 返回的 RAG-DEBUG 日志与分数（中继）</li>
     *   <li>证据 Agent 调用进度</li>
     *   <li>分级处置（预警/禁言）的逐条动作</li>
     *   <li>结束时 done 事件带汇总</li>
     * </ul>
     * 该方法立即返回，检测在独立线程中执行，通过 emitter 推送事件。
     *
     * @param emitter SSE 发射器（由 Controller 创建）
     */
    void detectMaliciousUsersStream(SseEmitter emitter);
}
