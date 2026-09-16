package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 点赞记录表：记录用户对帖子/评论的点赞。
 * target_type: 0=评论 1=帖子
 * 联合唯一(user_id, target_id, target_type)防重复点赞。
 */
@Data
@TableName("content_like")
public class ContentLike implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long likeId;
    private Long userId;
    private Long targetId;
    private Integer targetType;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdTime;
}
