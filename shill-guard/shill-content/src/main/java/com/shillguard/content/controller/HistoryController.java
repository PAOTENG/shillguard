package com.shillguard.content.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.Result;
import com.shillguard.common.result.ResultCode;
import com.shillguard.content.service.HistoryService;
import com.shillguard.content.vo.PostVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@Tag(name = "浏览/点赞记录接口")
@RestController
@RequestMapping("/api/content/history")
@RequiredArgsConstructor
public class HistoryController {

    private final HistoryService historyService;

    @Operation(summary = "我的浏览记录（完整帖子分页）")
    @GetMapping("/views")
    public Result<IPage<PostVO>> viewHistory(
            @RequestParam(name = "pageNum", defaultValue = "1") int pageNum,
            @RequestParam(name = "pageSize", defaultValue = "20") int pageSize,
            @RequestHeader("X-User-Id") Long userId) {
        if (userId == null) throw new BizException(ResultCode.UNAUTHORIZED);
        return Result.success(historyService.pageViewHistory(userId, pageNum, pageSize, userId));
    }

    @Operation(summary = "我的点赞记录（完整帖子分页）")
    @GetMapping("/likes")
    public Result<IPage<PostVO>> likedPosts(
            @RequestParam(name = "pageNum", defaultValue = "1") int pageNum,
            @RequestParam(name = "pageSize", defaultValue = "20") int pageSize,
            @RequestHeader("X-User-Id") Long userId) {
        if (userId == null) throw new BizException(ResultCode.UNAUTHORIZED);
        return Result.success(historyService.pageLikedPosts(userId, pageNum, pageSize, userId));
    }
}
