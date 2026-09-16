package com.shillguard.agent.dto;

import lombok.Data;
import java.io.Serializable;
import java.util.List;

/** 单个用户的证据生成结果（Python /ai/detect-evidence 返回）。 */
@Data
public class UserEvidenceResultDTO implements Serializable {
    private Long userId;
    private String evidenceDetail;
    private List<String> violatingItems;
}
