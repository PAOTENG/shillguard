package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

@Data
@TableName("agent_mute_record")
public class AgentMuteRecord implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long muteId;
    private Long mutedUserId;
    private Long reporterUserId;
    private Long reviewerUserId;
    private Long relatedCommentId;
    private String muteReason;
    private String evidenceDetail;
    /** 0=自动(Agent) 1=人工 */
    private Integer muteType;
    private Integer muteDays;
    private LocalDateTime muteStartTime;
    private LocalDateTime muteEndTime;
    /** 1=禁言中 2=已解除 3=已申诉 */
    private Integer status;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdTime;
    private LocalDateTime updatedTime;
}
