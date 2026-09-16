package com.shillguard.agent.dto;

import lombok.Data;

import java.io.Serializable;

/**
 * Python 异步审核接口 POST /ai/moderate 的立即返回体。
 * Python 端接收请求后将任务入队，立刻返回 taskId；Java 凭此轮询结果。
 */
@Data
public class ModerateSubmitResponseDTO implements Serializable {

    /** 异步任务 ID（UUID），用于后续 GET /ai/moderate/result/{taskId} 轮询 */
    private String taskId;

    /** 任务初始状态，始终为 "pending" */
    private String status;
}
