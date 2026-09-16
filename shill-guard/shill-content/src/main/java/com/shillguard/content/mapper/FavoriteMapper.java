package com.shillguard.content.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.entity.ContentPost;
import com.shillguard.common.entity.UserFavorite;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface FavoriteMapper extends BaseMapper<UserFavorite> {

    /** 我的收藏：JOIN content_post，只取审核通过的帖子，按收藏时间倒序 */
    @Select("SELECT p.* FROM user_favorite f " +
            "INNER JOIN content_post p ON f.post_id = p.post_id " +
            "WHERE f.user_id = #{userId} AND p.status = 0 " +
            "ORDER BY f.created_time DESC")
    IPage<ContentPost> pageFavoritePosts(IPage<ContentPost> page, @Param("userId") Long userId);
}
