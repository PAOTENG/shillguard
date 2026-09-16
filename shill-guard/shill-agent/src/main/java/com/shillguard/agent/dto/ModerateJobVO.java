package com.shillguard.agent.dto;

import lombok.Data;

import java.io.Serializable;

/** GET /api/agent/moderate/{id}/result 轮询体。 */
@Data
public class ModerateJobVO implements Serializable {

    private Long reportId;
    private String taskId;
    /** processing / done / error */
    private String status;
    private ModerateResultDTO result;
    private String error;
}
