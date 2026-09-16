package com.shillguard.agent.dto;

import lombok.Data;

import java.io.Serializable;

/** POST /api/agent/moderate/{id} 立即返回：任务已受理，结果请轮询。 */
@Data
public class ModerateAcceptDTO implements Serializable {

    private Long reportId;
    private String taskId;
    /** processing / done / error */
    private String status;
}
