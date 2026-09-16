package com.shillguard.agent.dto;

import lombok.Data;

import java.io.Serializable;

/**
 * 轮询 Python 异步审核结果：GET /ai/moderate/result/{taskId} 的响应体。
 *
 * <ul>
 *   <li>status = "pending" / "processing"：任务仍在执行，继续轮询</li>
 *   <li>status = "done"：审核完成，{@link #result} 填充</li>
 *   <li>status = "error"：任务失败，{@link #error} 填充错误原因</li>
 *   <li>status = "not_found"：taskId 不存在（重启/超期被清除）</li>
 * </ul>
 */
@Data
public class ModerateTaskResultDTO implements Serializable {

    private String taskId;

    /** pending / processing / done / error / not_found */
    private String status;

    /** status=done 时填充，结构与同步接口返回体一致 */
    private ModerateResultDTO result;

    /** status=error 时填充，Python 抛出的异常信息 */
    private String error;
}
