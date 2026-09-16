package com.shillguard.agent.dto;

import lombok.Data;
import java.io.Serializable;
import java.util.List;

/**
 * 单个用户的今日内容包（发给 Python 检测算法）。
 */
@Data
public class UserContentDTO implements Serializable {
    private Long userId;
    private List<String> contentList;
}
