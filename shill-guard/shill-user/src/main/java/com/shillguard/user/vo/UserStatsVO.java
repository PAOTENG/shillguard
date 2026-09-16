package com.shillguard.user.vo;

import lombok.Data;

/**
 * 用户统计数据：用于公开主页展示笔记/获赞/被收藏/被关注等数量。
 * isFollowing 表示当前登录用户是否已关注该用户。
 */
@Data
public class UserStatsVO {
    private Long userId;
    private long postCount;       // 审核通过笔记数
    private long likeCount;       // 获赞总数
    private long favoriteCount;   // 被收藏总数
    private long followerCount;   // 被关注数（粉丝数）
    private long followingCount;  // 关注数
    private Boolean isFollowing;  // 当前登录用户是否已关注（未登录为 false）
}
