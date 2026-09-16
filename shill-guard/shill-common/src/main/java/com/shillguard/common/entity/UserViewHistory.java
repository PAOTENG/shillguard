package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/** 用户浏览记录：一个用户对一篇帖子只保留一条记录，重复浏览时更新 view_time。 */
@Data
@TableName("user_view_history")
public class UserViewHistory implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long historyId;
    private Long userId;
    private Long postId;
    private LocalDateTime viewTime;
}
