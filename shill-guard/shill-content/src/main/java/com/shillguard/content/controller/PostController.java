package com.shillguard.content.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.Result;
import com.shillguard.common.result.ResultCode;
import com.shillguard.content.dto.PostCreateDTO;
import com.shillguard.content.service.PostService;
import com.shillguard.content.vo.PostPublishResultVO;
import com.shillguard.content.vo.PostVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@Tag(name = "帖子接口")
@RestController
@RequestMapping("/api/content/posts")
@RequiredArgsConstructor
public class PostController {

    private final PostService postService;

    @Operation(summary = "帖子列表（分页，支持关键词搜索）")
    @GetMapping
    public Result<IPage<PostVO>> list(
            @RequestParam(name = "pageNum", defaultValue = "1") int pageNum,
            @RequestParam(name = "pageSize", defaultValue = "10") int pageSize,
            @RequestParam(name = "topicTag", required = false) String topicTag,
            @RequestParam(name = "userId", required = false) Long userId,
            @RequestParam(name = "keyword", required = false) String keyword,
            @RequestHeader(value = "X-User-Id", required = false) Long currentUserId) {
        // userId 可为null，为null时查所有帖子；有值时只查指定用户的帖子
        // keyword 可为null，模糊搜索标题/正文/标签
        // currentUserId 来自网关注入的 JWT（未登录时为null），用于标记是否已点赞
        return Result.success(postService.pageList(pageNum, pageSize, topicTag, userId, keyword, currentUserId));
    }

    @Operation(summary = "帖子详情")
    @GetMapping("/{postId}")
    public Result<PostVO> detail(@PathVariable("postId") Long postId,
                                 @RequestHeader(value = "X-User-Id", required = false) Long currentUserId) {
        return Result.success(postService.getDetail(postId, currentUserId));
    }

    @Operation(summary = "发布帖子（自动审核）")
    @PostMapping
    public Result<PostPublishResultVO> create(@Valid @RequestBody PostCreateDTO dto,
                                              @RequestHeader("X-User-Id") Long userId) {
        return Result.success(postService.createPost(dto, userId));
    }

    @Operation(summary = "我的帖子（含审核中/审核不通过，供用户中心）")
    @GetMapping("/mine")
    public Result<IPage<PostVO>> mine(
            @RequestParam(name = "pageNum", defaultValue = "1") int pageNum,
            @RequestParam(name = "pageSize", defaultValue = "20") int pageSize,
            @RequestHeader(value = "X-User-Id", required = false) Long userId) {
        if (userId == null) {
            throw new BizException(ResultCode.UNAUTHORIZED);
        }
        return Result.success(postService.pageMyPosts(userId, pageNum, pageSize));
    }

    @Operation(summary = "删除帖子")
    @DeleteMapping("/{postId}")
    public Result<Void> delete(@PathVariable("postId") Long postId,
                               @RequestHeader("X-User-Id") Long userId,
                               @RequestHeader("X-User-Role") Integer role) {
        postService.deletePost(postId, userId, role);
        return Result.success();
    }

    @Operation(summary = "点赞帖子")
    @PostMapping("/{postId}/like")
    public Result<Void> like(@PathVariable("postId") Long postId,
                             @RequestHeader("X-User-Id") Long userId) {
        postService.likePost(postId, userId);
        return Result.success();
    }

    @Operation(summary = "取消点赞")
    @DeleteMapping("/{postId}/like")
    public Result<Void> unlike(@PathVariable("postId") Long postId,
                               @RequestHeader("X-User-Id") Long userId) {
        postService.unlikePost(postId, userId);
        return Result.success();
    }
}
