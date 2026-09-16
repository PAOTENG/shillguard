package com.shillguard.content.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.entity.ContentComment;
import com.shillguard.content.dto.CommentCreateDTO;
import com.shillguard.content.vo.CommentVO;

public interface CommentService {

    IPage<CommentVO> pageByPost(Long postId, int pageNum, int pageSize, Long currentUserId);

    /** 查询某条评论的子回复列表（分页） */
    IPage<CommentVO> pageReplies(Long parentCommentId, int pageNum, int pageSize, Long currentUserId);

    Long addComment(CommentCreateDTO dto, Long userId, String clientIp);

    void deleteComment(Long commentId, Long userId, Integer role);

    void likeComment(Long commentId, Long userId);

    /** 取消点赞评论 */
    void unlikeComment(Long commentId, Long userId);

    /** 取单条评论原文（供管理员人工复核查看被举报评论内容） */
    ContentComment getCommentDetail(Long commentId);
}
