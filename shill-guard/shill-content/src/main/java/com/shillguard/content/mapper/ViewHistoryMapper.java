package com.shillguard.content.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.entity.ContentPost;
import com.shillguard.common.entity.UserViewHistory;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface ViewHistoryMapper extends BaseMapper<UserViewHistory> {

    /**
     * 记录浏览：存在则更新 view_time 为当前时间，不存在则插入。
     * 利用 user_view_history 的 UNIQUE(user_id, post_id) 做 upsert。
     */
    @Insert("INSERT INTO user_view_history(user_id, post_id, view_time) " +
            "VALUES(#{userId}, #{postId}, NOW()) " +
            "ON DUPLICATE KEY UPDATE view_time = VALUES(view_time)")
    void upsertView(@Param("userId") Long userId, @Param("postId") Long postId);

    /** 我的浏览记录：JOIN content_post，只取审核通过的帖子，按 view_time 倒序 */
    @Select("SELECT p.* FROM user_view_history h " +
            "INNER JOIN content_post p ON h.post_id = p.post_id " +
            "WHERE h.user_id = #{userId} AND p.status = 0 " +
            "ORDER BY h.view_time DESC")
    IPage<ContentPost> pageViewHistory(IPage<ContentPost> page, @Param("userId") Long userId);
}
