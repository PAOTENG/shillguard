package com.shillguard.agent.dto;

import lombok.Data;
import java.io.Serializable;
import java.util.List;

/** 批量证据生成请求体（发给 Python /ai/detect-evidence）。 */
@Data
public class DetectEvidenceRequestDTO implements Serializable {
    private List<UserEvidenceInputDTO> users;
}
