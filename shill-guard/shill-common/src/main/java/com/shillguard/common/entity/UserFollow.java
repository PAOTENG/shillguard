package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 用户关注关系表：follower_id 关注了 following_id。
 * 单表设计 + UNIQUE(follower_id, following_id) + 双向索引，支持中小规模。
 * follower_id=关注者(主动方)，following_id=被关注者(被动方)。
 */
@Data
@TableName("user_follow")
public class UserFollow implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long followId;
    private Long followerId;
    private Long followingId;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdTime;
}
