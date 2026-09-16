package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/** 用户收藏记录：一个用户对一篇帖子只收藏一次，可归入某个收藏夹(folder_id 可空=未分组)。 */
@Data
@TableName("user_favorite")
public class UserFavorite implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long favoriteId;
    private Long userId;
    private Long folderId;
    private Long postId;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdTime;
}
