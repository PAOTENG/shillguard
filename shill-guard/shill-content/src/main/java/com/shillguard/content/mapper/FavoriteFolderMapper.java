package com.shillguard.content.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.UserFavoriteFolder;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface FavoriteFolderMapper extends BaseMapper<UserFavoriteFolder> {

    /** 收藏夹内帖子数 +delta（收藏+1，取消收藏-1） */
    @Update("UPDATE user_favorite_folder SET post_count = post_count + #{delta} WHERE folder_id = #{folderId}")
    void updatePostCount(@Param("folderId") Long folderId, @Param("delta") int delta);
}
