package com.shillguard.agent.dto;

import lombok.Data;
import java.io.Serializable;
import java.util.List;

/**
 * 检测结果汇总（返回给前端展示）。
 */
@Data
public class DetectResultVO implements Serializable {
    private int totalUsers;       // 本次检测用户数
    private int warningCount;     // 预警人数 (0.8<score<0.9)
    private int mutedCount;       // 禁言人数 (score>=0.9)
    private List<UserScoreResultDTO> results;  // 每用户明细
}
