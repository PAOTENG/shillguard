package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/** 收藏夹分组：每个用户可创建多个收藏夹（专辑）。 */
@Data
@TableName("user_favorite_folder")
public class UserFavoriteFolder implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long folderId;
    private Long userId;
    private String folderName;
    private Long postCount;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdTime;
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedTime;
}
