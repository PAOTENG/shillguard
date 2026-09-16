package com.shillguard.content.vo;

import com.shillguard.common.entity.ContentComment;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 评论展示对象：在 ContentComment 基础上附加评论者信息，供前端评论列表使用。
 */
@Data
@EqualsAndHashCode(callSuper = true)
public class CommentVO extends ContentComment {

    /** 评论者用户名 */
    private String username;

    /** 评论者昵称 */
    private String nickname;

    /** 评论者头像 URL */
    private String avatarUrl;

    /** 当前用户是否已点赞该评论 */
    private Boolean isLiked;
}
