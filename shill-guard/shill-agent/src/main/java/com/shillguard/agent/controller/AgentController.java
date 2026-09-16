package com.shillguard.agent.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.shillguard.agent.dto.DetectResultVO;
import com.shillguard.agent.dto.ModerateAcceptDTO;
import com.shillguard.agent.dto.ModerateJobVO;
import com.shillguard.agent.mapper.MuteRecordMapper;
import com.shillguard.agent.service.AgentService;
import com.shillguard.common.entity.AgentMuteRecord;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.Result;
import com.shillguard.common.result.ResultCode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Tag(name = "Agent检测接口")
@RestController
@RequestMapping("/api/agent")
@RequiredArgsConstructor
public class AgentController {

    private final AgentService agentService;
    private final MuteRecordMapper muteRecordMapper;

    @Operation(summary = "手动触发水军检测（管理员）")
    @PostMapping("/detect/trigger")
    public Result<String> triggerDetect(@RequestHeader("X-User-Role") Integer role) {
        if (role < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        agentService.triggerDetect();
        return Result.success("检测任务已提交");
    }

    @Operation(summary = "查询禁言记录列表")
    @GetMapping("/mute/records")
    public Result<IPage<AgentMuteRecord>> muteList(
            @RequestParam(name = "pageNum", defaultValue = "1") int pageNum,
            @RequestParam(name = "pageSize", defaultValue = "10") int pageSize,
            @RequestParam(name = "status", required = false) Integer status,
            @RequestHeader("X-User-Role") Integer role) {
        if (role < 1) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        // status: 1=禁言中  2=已解除  null=全部
        IPage<AgentMuteRecord> page = muteRecordMapper.selectPage(
                new Page<>(pageNum, pageSize),
                new LambdaQueryWrapper<AgentMuteRecord>()
                        .eq(status != null, AgentMuteRecord::getStatus, status)
                        .orderByDesc(AgentMuteRecord::getCreatedTime)
        );
        return Result.success(page);
    }

    @Operation(summary = "手动执行禁言")
    @PostMapping("/mute")
    public Result<Void> manualMute(@RequestParam Long userId,
                                   @RequestParam String reason,
                                   @RequestParam(name = "days", defaultValue = "7") Integer days,
                                   @RequestParam(name = "reportId", required = false) Long reportId,
                                   @RequestHeader("X-User-Id") Long operatorId,
                                   @RequestHeader("X-User-Role") Integer role) {
        if (role < 1) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        agentService.manualMute(userId, reason, days, operatorId, reportId);
        return Result.success();
    }

    @Operation(summary = "解除禁言")
    @DeleteMapping("/mute/{muteId}")
    public Result<Void> unmute(@PathVariable("muteId") Long muteId,
                               @RequestHeader("X-User-Role") Integer role) {
        if (role < 1) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        agentService.unmute(muteId);
        return Result.success();
    }

    /**
     * 受理 AI 审核：立即返回 taskId，不占用 Tomcat 等待 LLM。
     * 结果请轮询 GET /moderate/{reportId}/result。
     */
    @Operation(summary = "AI审核举报（立即受理，结果请轮询）")
    @PostMapping("/moderate/{reportId}")
    public Result<ModerateAcceptDTO> moderateReport(
            @PathVariable("reportId") Long reportId,
            @RequestHeader("X-User-Role") Integer role) {
        if (role < 1) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        return Result.success(agentService.submitModerate(reportId));
    }

    @Operation(summary = "查询AI审核结果")
    @GetMapping("/moderate/{reportId}/result")
    public Result<ModerateJobVO> moderateResult(
            @PathVariable("reportId") Long reportId,
            @RequestHeader("X-User-Role") Integer role) {
        if (role < 1) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        return Result.success(agentService.getModerateJob(reportId));
    }

    @Operation(summary = "查询某用户最新的禁言记录（含AI证据，人工复核用）")
    @GetMapping("/mute/latest")
    public Result<AgentMuteRecord> latestMute(
            @RequestParam Long userId,
            @RequestHeader("X-User-Role") Integer role) {
        if (role < 1) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        return Result.success(agentService.getLatestMuteByUser(userId));
    }

    /**
     * 立即触发"识别恶意行为用户"检测（管理员及以上）。
     * 后端收集今日所有帖子+评论按用户分组，调用 Python 检测算法打分，
     * 0.8<score<0.9 写预警标记，score>=0.9 禁言7天并生成证据。
     *
     * @return 检测结果汇总（每用户分数与明细）
     */
    @Operation(summary = "识别恶意行为用户检测（管理员及以上）")
    @PostMapping("/detect-users")
    public Result<DetectResultVO> detectMaliciousUsers(
            @RequestHeader("X-User-Role") Integer role) {
        if (role < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        DetectResultVO vo = agentService.detectMaliciousUsers();
        return Result.success(vo);
    }

    /**
     * 立即触发"识别恶意行为用户"检测（SSE 流式版本）。
     * 返回 text/event-stream，实时推送后端处理日志与逐用户打分/处置进度。
     * 检测在独立线程执行，通过 SseEmitter 推送事件，结束后前端拿到汇总。
     */
    @Operation(summary = "识别恶意行为用户检测·SSE实时日志流（管理员及以上）")
    @PostMapping(value = "/detect-users/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter detectMaliciousUsersStream(
            @RequestHeader("X-User-Role") Integer role) {
        if (role < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        // 10 分钟超时（检测可能较长）
        SseEmitter emitter = new SseEmitter(600_000L);
        agentService.detectMaliciousUsersStream(emitter);
        return emitter;
    }
}
