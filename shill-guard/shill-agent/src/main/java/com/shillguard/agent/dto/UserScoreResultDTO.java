package com.shillguard.agent.dto;

import lombok.Data;
import java.io.Serializable;
import java.util.List;

/**
 * Python 检测算法返回的单个用户结果。
 */
@Data
public class UserScoreResultDTO implements Serializable {
    private Long userId;

    // ── 新级联检测字段（Python /ai/detect-users 返回）──
    /** 禁言决策：none | mute_3days | mute_7days */
    private String muteAction = "none";
    /** 违规条数（1条→3天，2+条→7天） */
    private Integer violationCount = 0;

    // ── 遗留打分字段（anomalyScore 路径兼容）──
    private Float anomalyScore;
    private String contentType;
    private List<String> violatedRules;
    private List<String> violatedLaws;
    private String evidenceSummary;
    private String evidenceDetail;
    private List<String> contentList;
    /** 证据 agent 挑出的具体违规帖子/评论原文（高危用户才有） */
    private List<String> violatingItems;
}
