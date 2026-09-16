package com.shillguard.content.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.entity.ContentReport;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.Result;
import com.shillguard.common.result.ResultCode;
import com.shillguard.content.service.ReportService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@Tag(name = "举报接口")
@RestController
@RequestMapping("/api/content/reports")
@RequiredArgsConstructor
public class ReportController {

    private final ReportService reportService;

    /**
     * 管理员查询举报列表（分页）
     * 需要 role >= 1（审核员及以上）
     */
    @Operation(summary = "举报列表（分页）")
    @GetMapping
    public Result<IPage<ContentReport>> list(
            @RequestParam(name = "pageNum", defaultValue = "1") int pageNum,
            @RequestParam(name = "pageSize", defaultValue = "10") int pageSize,
            @RequestParam(name = "status", required = false) Integer status,
            @RequestHeader("X-User-Role") Integer role) {
        if (role < 1) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        return Result.success(reportService.pageList(pageNum, pageSize, status));
    }

    /**
     * 更新举报状态（审核处理）
     * 需要 role >= 1（审核员及以上）
     *
     * @param reportId   举报ID（路径参数）
     * @param status     新状态：0=待处理 1=处理中 2=已忽略 3=已删帖 4=已转Agent
     * @param reviewNote 审核备注（可选）
     */
    @Operation(summary = "处理举报（更新状态）")
    @PutMapping("/{reportId}")
    public Result<Void> handle(
            @PathVariable("reportId") Long reportId,
            @RequestParam Integer status,
            @RequestParam(name = "reviewNote", required = false) String reviewNote,
            @RequestHeader("X-User-Id") Long reviewerId,
            @RequestHeader("X-User-Role") Integer role) {
        if (role < 1) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        reportService.updateStatus(reportId, status, reviewNote, reviewerId);
        return Result.success();
    }

    /**
     * 普通用户提交举报
     * 需要登录（X-User-Id 由网关注入）
     */
    @Operation(summary = "提交举报")
    @PostMapping
    public Result<Void> submit(
            @RequestBody ContentReport report,
            @RequestHeader("X-User-Id") Long userId) {
        // 强制设置举报人为当前登录用户，防止伪造
        report.setReporterUserId(userId);
        report.setStatus(0); // 初始状态：待处理
        reportService.submitReport(report);
        return Result.success();
    }
}
