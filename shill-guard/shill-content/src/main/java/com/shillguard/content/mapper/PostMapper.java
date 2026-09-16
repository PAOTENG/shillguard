package com.shillguard.content.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.ContentPost;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface PostMapper extends BaseMapper<ContentPost> {

    @Update("UPDATE content_post SET view_count = view_count + 1 WHERE post_id = #{postId}")
    void incrementViewCount(@Param("postId") Long postId);

    /** 热帖浏览量回写：只允许总量变大，避免并发刷盘把计数打回去 */
    @Update("UPDATE content_post SET view_count = #{count} WHERE post_id = #{postId} AND view_count < #{count}")
    int applyViewCount(@Param("postId") Long postId, @Param("count") long count);

    @Update("UPDATE content_post SET like_count = like_count + #{delta} WHERE post_id = #{postId}")
    void updateLikeCount(@Param("postId") Long postId, @Param("delta") int delta);

    @Update("UPDATE content_post SET comment_count = comment_count + #{delta} WHERE post_id = #{postId}")
    void updateCommentCount(@Param("postId") Long postId, @Param("delta") int delta);
}
