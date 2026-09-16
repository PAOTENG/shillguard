package com.shillguard.admin.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.admin.service.AdminService;
import com.shillguard.common.entity.ContentPost;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.Result;
import com.shillguard.common.result.ResultCode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 帖子/视频管理接口。
 *
 * <p>视频复用 content_post 表，post_type=3 即视频，故视频管理 = 帖子管理加 postType=3 过滤。
 * 管理员可查看全量（含已删除/审核中）内容并执行逻辑删除/恢复。
 */
@Tag(name = "后台-帖子/视频管理")
@RestController
@RequestMapping("/api/admin/posts")
@RequiredArgsConstructor
public class PostAdminController {

    private final AdminService adminService;

    @Operation(summary = "帖子分页（管理员，全量）")
    @GetMapping
    public Result<IPage<ContentPost>> list(
            @RequestParam(name = "pageNum", defaultValue = "1") int pageNum,
            @RequestParam(name = "pageSize", defaultValue = "20") int pageSize,
            @RequestParam(name = "status", required = false) Integer status,
            @RequestParam(name = "postType", required = false) Integer postType,
            @RequestParam(name = "keyword", required = false) String keyword,
            @RequestHeader("X-User-Role") Integer role) {
        if (role < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        return Result.success(adminService.pagePosts(pageNum, pageSize, status, postType, keyword));
    }

    @Operation(summary = "设置帖子状态（逻辑删除/恢复）")
    @PutMapping("/{postId}/status")
    public Result<Void> setStatus(@PathVariable("postId") Long postId,
                                  @RequestParam int status,
                                  @RequestHeader("X-User-Role") Integer role) {
        if (role < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        adminService.setPostStatus(postId, status);
        return Result.success();
    }
}
