package com.shillguard.user.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shillguard.common.entity.UserFollow;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.ResultCode;
import com.shillguard.user.mapper.SysUserMapper;
import com.shillguard.user.mapper.UserFollowMapper;
import com.shillguard.user.mapper.UserStatsMapper;
import com.shillguard.user.service.FollowService;
import com.shillguard.user.vo.UserStatsVO;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class FollowServiceImpl implements FollowService {

    private final UserFollowMapper followMapper;
    private final UserStatsMapper statsMapper;
    private final SysUserMapper userMapper;

    @Override
    @Transactional
    public void follow(Long followerId, Long followingId) {
        if (followerId == null || followingId == null) {
            // 登录态异常或目标用户缺失时给出明确提示，便于定位
            throw new BizException(ResultCode.PARAM_ERROR.getCode(),
                    "关注失败：登录状态异常或目标用户无效");
        }
        // 不能关注自己
        if (followerId.equals(followingId)) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "不能关注自己");
        }
        // 目标用户必须存在且为正常状态，避免关注到已注销/不存在用户
        com.shillguard.common.entity.SysUser target = userMapper.selectById(followingId);
        if (target == null || target.getStatus() == null || target.getStatus() != 0) {
            throw new BizException(ResultCode.USER_NOT_FOUND);
        }
        // 已关注则幂等返回
        if (followMapper.isFollowing(followerId, followingId)) {
            return;
        }
        UserFollow f = new UserFollow();
        f.setFollowerId(followerId);
        f.setFollowingId(followingId);
        followMapper.insert(f);
        // 维护双方计数：关注者的关注数+1，被关注者的粉丝数+1
        userMapper.incrementFollowingCount(followerId, 1);
        userMapper.incrementFollowerCount(followingId, 1);
    }

    @Override
    @Transactional
    public void unfollow(Long followerId, Long followingId) {
        int deleted = followMapper.delete(new LambdaQueryWrapper<UserFollow>()
                .eq(UserFollow::getFollowerId, followerId)
                .eq(UserFollow::getFollowingId, followingId));
        if (deleted > 0) {
            userMapper.incrementFollowingCount(followerId, -1);
            userMapper.incrementFollowerCount(followingId, -1);
        }
    }

    @Override
    public boolean isFollowing(Long followerId, Long followingId) {
        if (followerId == null || followingId == null) return false;
        return followMapper.isFollowing(followerId, followingId);
    }

    @Override
    public List<com.shillguard.common.entity.SysUser> myFollowings(Long userId) {
        return followMapper.listFollowings(userId);
    }

    @Override
    public List<com.shillguard.common.entity.SysUser> myFollowers(Long userId) {
        return followMapper.listFollowers(userId);
    }

    @Override
    public UserStatsVO stats(Long userId, Long currentUserId) {
        UserStatsVO vo = new UserStatsVO();
        vo.setUserId(userId);
        vo.setPostCount(statsMapper.countPosts(userId));
        vo.setLikeCount(statsMapper.sumLikes(userId));
        vo.setFavoriteCount(statsMapper.countFavorites(userId));
        vo.setFollowerCount(followMapper.countFollowers(userId));
        vo.setFollowingCount(followMapper.countFollowings(userId));
        vo.setIsFollowing(isFollowing(currentUserId, userId));
        return vo;
    }
}
