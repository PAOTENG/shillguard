package com.shillguard.content.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.ContentComment;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface CommentMapper extends BaseMapper<ContentComment> {

    @Update("UPDATE content_comment SET like_count = like_count + #{delta} WHERE comment_id = #{commentId}")
    void updateLikeCount(@Param("commentId") Long commentId, @Param("delta") int delta);

    @Update("UPDATE content_comment SET reply_count = reply_count + #{delta} WHERE comment_id = #{commentId}")
    void updateReplyCount(@Param("commentId") Long commentId, @Param("delta") int delta);
}
