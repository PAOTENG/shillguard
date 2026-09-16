package com.shillguard.agent.dto;

import lombok.Data;
import java.io.Serializable;
import java.util.List;

/** 单个高危用户的证据生成输入（发给 Python /ai/detect-evidence）。 */
@Data
public class UserEvidenceInputDTO implements Serializable {
    private Long userId;
    private List<String> contentList;
    private Float anomalyScore;
    private List<String> violatedRules;
    private List<String> violatedLaws;
    private String judgment;
}
