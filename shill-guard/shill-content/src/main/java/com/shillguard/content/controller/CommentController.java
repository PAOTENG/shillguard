package com.shillguard.content.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.entity.ContentComment;
import com.shillguard.common.result.Result;
import com.shillguard.content.dto.CommentCreateDTO;
import com.shillguard.content.service.CommentService;
import com.shillguard.content.vo.CommentVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@Tag(name = "评论接口")
@RestController
@RequestMapping("/api/content/comments")
@RequiredArgsConstructor
public class CommentController {

    private final CommentService commentService;

    @Operation(summary = "获取帖子评论列表")
    @GetMapping("/post/{postId}")
    public Result<IPage<CommentVO>> listByPost(
            @PathVariable("postId") Long postId,
            @RequestParam(name = "pageNum", defaultValue = "1") int pageNum,
            @RequestParam(name = "pageSize", defaultValue = "20") int pageSize,
            @RequestHeader(value = "X-User-Id", required = false) Long currentUserId) {
        return Result.success(commentService.pageByPost(postId, pageNum, pageSize, currentUserId));
    }

    @Operation(summary = "获取评论的子回复列表")
    @GetMapping("/{commentId}/replies")
    public Result<IPage<CommentVO>> listReplies(
            @PathVariable("commentId") Long commentId,
            @RequestParam(name = "pageNum", defaultValue = "1") int pageNum,
            @RequestParam(name = "pageSize", defaultValue = "20") int pageSize,
            @RequestHeader(value = "X-User-Id", required = false) Long currentUserId) {
        return Result.success(commentService.pageReplies(commentId, pageNum, pageSize, currentUserId));
    }

    @Operation(summary = "发表评论")
    @PostMapping
    public Result<Long> addComment(@Valid @RequestBody CommentCreateDTO dto,
                                   @RequestHeader("X-User-Id") Long userId,
                                   HttpServletRequest request) {
        return Result.success(commentService.addComment(dto, userId, request.getRemoteAddr()));
    }

    @Operation(summary = "删除评论")
    @DeleteMapping("/{commentId}")
    public Result<Void> deleteComment(@PathVariable("commentId") Long commentId,
                                      @RequestHeader("X-User-Id") Long userId,
                                      @RequestHeader("X-User-Role") Integer role) {
        commentService.deleteComment(commentId, userId, role);
        return Result.success();
    }

    @Operation(summary = "点赞评论")
    @PostMapping("/{commentId}/like")
    public Result<Void> likeComment(@PathVariable("commentId") Long commentId,
                                    @RequestHeader("X-User-Id") Long userId) {
        commentService.likeComment(commentId, userId);
        return Result.success();
    }

    @Operation(summary = "取消点赞评论")
    @DeleteMapping("/{commentId}/like")
    public Result<Void> unlikeComment(@PathVariable("commentId") Long commentId,
                                      @RequestHeader("X-User-Id") Long userId) {
        commentService.unlikeComment(commentId, userId);
        return Result.success();
    }

    @Operation(summary = "获取单条评论详情（管理员人工复核用）")
    @GetMapping("/{commentId}")
    public Result<ContentComment> detail(@PathVariable("commentId") Long commentId) {
        return Result.success(commentService.getCommentDetail(commentId));
    }
}
