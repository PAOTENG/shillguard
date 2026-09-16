package com.shillguard.content.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.SysUser;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

/**
 * 内容服务用于查询 sys_user 的轻量 Mapper（与本模块共享同一个 shill_guard 库）。
 * 既用来批量取用户昵称/头像等信息，也给帖子、评论做作者信息补全；
 * 同时维护作者的被赞/被收藏统计列。
 */
@Mapper
public interface UserMapper extends BaseMapper<SysUser> {

    /** 帖子被点赞时，给作者的被赞数 +delta（用子查询取作者，避免多一次查询） */
    @Update("UPDATE sys_user SET liked_count = liked_count + #{delta} " +
            "WHERE user_id = (SELECT user_id FROM content_post WHERE post_id = #{postId})")
    void incrementLikedCountByPost(@Param("postId") Long postId, @Param("delta") int delta);

    /** 帖子被收藏时，给作者的被收藏数 +delta */
    @Update("UPDATE sys_user SET favorited_count = favorited_count + #{delta} " +
            "WHERE user_id = (SELECT user_id FROM content_post WHERE post_id = #{postId})")
    void incrementFavoritedCountByPost(@Param("postId") Long postId, @Param("delta") int delta);
}
