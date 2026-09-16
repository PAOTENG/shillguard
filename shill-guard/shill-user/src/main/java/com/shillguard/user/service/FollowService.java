package com.shillguard.user.service;

import com.shillguard.common.entity.SysUser;
import com.shillguard.user.vo.UserStatsVO;

import java.util.List;

public interface FollowService {

    /** 关注某用户 */
    void follow(Long followerId, Long followingId);

    /** 取消关注 */
    void unfollow(Long followerId, Long followingId);

    /** 当前用户是否已关注目标用户 */
    boolean isFollowing(Long followerId, Long followingId);

    /** 我的关注列表（公开字段） */
    List<SysUser> myFollowings(Long userId);

    /** 我的粉丝列表（公开字段） */
    List<SysUser> myFollowers(Long userId);

    /** 某用户的统计 + 当前用户是否已关注他 */
    UserStatsVO stats(Long userId, Long currentUserId);
}
