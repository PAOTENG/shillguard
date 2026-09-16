package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 用户恶意行为风险记录。
 *
 * <p>每次"识别恶意行为用户"检测运行时，每个被检测用户写一条记录，
 * 保留异常分数、预警级别、今日内容快照与 Agent 生成的完整证据，便于申诉复核。
 */
@Data
@TableName("user_risk_record")
public class UserRiskRecord implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long riskId;
    private Long userId;
    private Float anomalyScore;
    /** 1=预警 2=高危(已禁言) */
    private Integer warningLevel;
    /** 本次检测的今日内容快照（帖子+评论） */
    private String contentSnapshot;
    /** Agent 生成的完整证据报告（高危用户） */
    private String evidenceDetail;
    private LocalDateTime detectTime;
}
