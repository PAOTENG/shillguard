package com.shillguard.agent.dto;

import lombok.Data;
import java.io.Serializable;
import java.util.List;

/** 批量检测请求体（发给 Python /ai/detect-users）。 */
@Data
public class DetectUsersRequestDTO implements Serializable {
    private List<UserContentDTO> users;
}
