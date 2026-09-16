package com.shillguard.agent.dto;

import lombok.Data;
import java.io.Serializable;
import java.util.List;

/** 批量证据生成响应体（Python /ai/detect-evidence 返回）。 */
@Data
public class DetectEvidenceResponseDTO implements Serializable {
    private List<UserEvidenceResultDTO> results;
}
