package com.shillguard.user.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * 用户统计 Mapper：通过 SQL 聚合计算某用户的笔记数/获赞数/被收藏数。
 * 所有表都在同一个 shill_guard 库，可直接 JOIN 聚合，无需跨服务调用。
 */
@Mapper
public interface UserStatsMapper {

    /** 审核通过的笔记数 */
    @Select("SELECT COUNT(*) FROM content_post WHERE user_id = #{userId} AND status = 0")
    long countPosts(@Param("userId") Long userId);

    /** 获赞总数：该用户所有审核通过帖子的 like_count 之和 */
    @Select("SELECT COALESCE(SUM(like_count), 0) FROM content_post WHERE user_id = #{userId} AND status = 0")
    long sumLikes(@Param("userId") Long userId);

    /** 被收藏总数：该用户所有审核通过帖子被收藏的次数 */
    @Select("SELECT COUNT(*) FROM user_favorite fav " +
            "INNER JOIN content_post p ON fav.post_id = p.post_id " +
            "WHERE p.user_id = #{userId} AND p.status = 0")
    long countFavorites(@Param("userId") Long userId);
}
