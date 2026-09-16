package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

@Data
@TableName("content_report")
public class ContentReport implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long reportId;
    private Long reporterUserId;
    private Long reportedCommentId;
    private Long reportedPostId;
    private Long reportedUserId;
    /** 0=广告水军 1=违法信息 2=侮辱谩骂 3=色情低俗 4=其他 */
    private Integer reportCategory;
    private String reportReason;
    private Long reviewerUserId;
    private String reviewNote;
    /** 0=待处理 1=处理中 2=已忽略 3=已删帖 4=已转Agent */
    private Integer status;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdTime;
    private LocalDateTime updatedTime;
}
