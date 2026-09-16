package com.shillguard.notify.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.entity.SysNotification;
import com.shillguard.common.result.Result;
import com.shillguard.notify.service.NotifyService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@Tag(name = "通知接口")
@RestController
@RequestMapping("/api/notify")
@RequiredArgsConstructor
public class NotifyController {

    private final NotifyService notifyService;

    /**
     * 查询当前用户的通知列表（分页）
     * 需要登录，X-User-Id 由网关注入
     */
    @Operation(summary = "通知列表（分页）")
    @GetMapping("/list")
    public Result<IPage<SysNotification>> list(
            @RequestParam(name = "pageNum", defaultValue = "1") int pageNum,
            @RequestParam(name = "pageSize", defaultValue = "20") int pageSize,
            @RequestHeader("X-User-Id") Long userId) {
        return Result.success(notifyService.pageList(userId, pageNum, pageSize));
    }

    /**
     * 获取未读通知数量
     * 前端用这个接口显示小红点数字
     */
    @Operation(summary = "未读通知数量")
    @GetMapping("/unread/count")
    public Result<Integer> unreadCount(@RequestHeader("X-User-Id") Long userId) {
        return Result.success(notifyService.unreadCount(userId));
    }

    /**
     * 标记单条通知为已读
     */
    @Operation(summary = "标记单条已读")
    @PutMapping("/read/{noticeId}")
    public Result<Void> markAsRead(@PathVariable("noticeId") Long noticeId,
                                   @RequestHeader("X-User-Id") Long userId) {
        notifyService.markAsRead(noticeId, userId);
        return Result.success();
    }

    /**
     * 全部标记为已读
     */
    @Operation(summary = "全部标记已读")
    @PutMapping("/read/all")
    public Result<Void> markAllAsRead(@RequestHeader("X-User-Id") Long userId) {
        notifyService.markAllAsRead(userId);
        return Result.success();
    }
}
