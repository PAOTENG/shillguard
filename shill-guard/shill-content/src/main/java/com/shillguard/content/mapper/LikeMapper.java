package com.shillguard.content.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.entity.ContentLike;
import com.shillguard.common.entity.ContentPost;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/** 点赞记录 Mapper：用于持久化帖子点赞、查询用户的点赞历史。 */
@Mapper
public interface LikeMapper extends BaseMapper<ContentLike> {

    /** 我的点赞记录：JOIN content_post，只取审核通过帖子，target_type=1=帖子，按点赞时间倒序 */
    @Select("SELECT p.* FROM content_like l " +
            "INNER JOIN content_post p ON l.target_id = p.post_id " +
            "WHERE l.user_id = #{userId} AND l.target_type = 1 AND p.status = 0 " +
            "ORDER BY l.created_time DESC")
    IPage<ContentPost> pageLikedPosts(IPage<ContentPost> page, @Param("userId") Long userId);

    /**
     * 并发安全写入：依赖 uk_user_target 唯一索引，重复点赞返回 0 而不抛错。
     */
    @org.apache.ibatis.annotations.Insert(
            "INSERT IGNORE INTO content_like (user_id, target_id, target_type, created_time) " +
            "VALUES (#{userId}, #{targetId}, #{targetType}, NOW())")
    int insertIgnore(ContentLike like);
}
