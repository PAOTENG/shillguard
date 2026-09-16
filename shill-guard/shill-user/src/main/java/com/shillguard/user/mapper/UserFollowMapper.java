package com.shillguard.user.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.SysUser;
import com.shillguard.common.entity.UserFollow;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface UserFollowMapper extends BaseMapper<UserFollow> {

    /** 某用户的粉丝数（被多少人关注） */
    @Select("SELECT COUNT(*) FROM user_follow WHERE following_id = #{userId}")
    long countFollowers(@Param("userId") Long userId);

    /** 某用户的关注数（关注了多少人） */
    @Select("SELECT COUNT(*) FROM user_follow WHERE follower_id = #{userId}")
    long countFollowings(@Param("userId") Long userId);

    /** follower 是否已关注 following */
    @Select("SELECT COUNT(*) FROM user_follow WHERE follower_id = #{followerId} AND following_id = #{followingId}")
    boolean isFollowing(@Param("followerId") Long followerId, @Param("followingId") Long followingId);

    /** 我关注的人列表（JOIN sys_user 取公开字段），按关注时间倒序 */
    @Select("SELECT u.user_id, u.username, u.nickname, u.avatar_url, u.role " +
            "FROM user_follow f INNER JOIN sys_user u ON f.following_id = u.user_id " +
            "WHERE f.follower_id = #{userId} AND u.status = 0 " +
            "ORDER BY f.created_time DESC")
    List<SysUser> listFollowings(@Param("userId") Long userId);

    /** 我的粉丝列表（关注了我的人，JOIN sys_user 取公开字段），按关注时间倒序 */
    @Select("SELECT u.user_id, u.username, u.nickname, u.avatar_url, u.role " +
            "FROM user_follow f INNER JOIN sys_user u ON f.follower_id = u.user_id " +
            "WHERE f.following_id = #{userId} AND u.status = 0 " +
            "ORDER BY f.created_time DESC")
    List<SysUser> listFollowers(@Param("userId") Long userId);
}
