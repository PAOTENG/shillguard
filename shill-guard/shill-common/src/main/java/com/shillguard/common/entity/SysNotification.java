package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 站内通知实体类
 * 对应数据库表 sys_notification
 */
@Data
@TableName("sys_notification")
public class SysNotification implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long noticeId;
    private Long userId;
    /** 0=系统通知 1=禁言通知 2=评论通知 3=点赞通知 4=申诉结果 */
    private Integer noticeType;
    private String title;
    private String content;
    /** 关联业务ID（如禁言记录ID、评论ID等） */
    private Long relatedId;
    /** 0=未读 1=已读 */
    private Integer isRead;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdTime;
}
