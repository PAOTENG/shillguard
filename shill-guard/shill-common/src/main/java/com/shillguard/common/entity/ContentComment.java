package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

@Data
@TableName("content_comment")
public class ContentComment implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long commentId;
    private Long userId;
    private Long postId;
    private Long parentCommentId;
    private Long replyToUserId;
    private String content;
    private Integer likeCount;
    /** 子回复数量 */
    private Integer replyCount;
    /** 0=正常 1=已删除 */
    private Integer status;
    /** 0=否 1=置顶 */
    private Integer isTop;
    private String clientIp;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdTime;
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedTime;
}
