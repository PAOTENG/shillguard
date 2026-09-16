package com.shillguard.agent.dto;

import lombok.Data;

import java.io.Serializable;
import java.util.List;

/**
 * Python 审核 Agent 返回的响应体。
 * 字段名与 Python schemas.ModerateResult 严格一致。
 */
@Data
public class ModerateResultDTO implements Serializable {

    private Long reportId;
    private Long reportedUserId;

    /** 异常分数 0~1，越高越严重 */
    private Float anomalyScore;

    /** LLM 判定的内容类型 */
    private String contentType;

    /** 违反的平台规则列表 */
    private List<String> violatedRules;

    /** 违反的法律条文列表 */
    private List<String> violatedLaws;

    /** 证据摘要（一句话） */
    private String evidenceSummary;

    /** 完整证据报告（Markdown） */
    private String evidenceDetail;

    /** 处罚动作：none / manual_review / auto_mute */
    private String action;
}
