package com.shillguard.agent.dto;

import lombok.Data;
import java.io.Serializable;
import java.util.List;

/** 批量检测响应体（Python /ai/detect-users 返回）。 */
@Data
public class DetectUsersResponseDTO implements Serializable {
    private List<UserScoreResultDTO> results;
}
