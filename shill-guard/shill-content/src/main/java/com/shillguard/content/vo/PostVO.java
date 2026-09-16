package com.shillguard.content.vo;

import com.shillguard.common.entity.ContentPost;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 帖子展示对象：在 ContentPost 基础上附加作者信息，供前端列表/详情使用。
 * 字段名与前端一致：username、nickname、avatarUrl。
 */
@Data
@EqualsAndHashCode(callSuper = true)
public class PostVO extends ContentPost {

    /** 作者用户名 */
    private String username;

    /** 作者昵称 */
    private String nickname;

    /** 作者头像 URL（来自 sys_user.avatar_url） */
    private String avatarUrl;

    /** 当前登录用户是否已点赞（未登录或未点过为 false/null） */
    private Boolean isLiked;

    /** 当前登录用户是否已收藏（未登录或未收藏为 false/null） */
    private Boolean isFavorited;
}
