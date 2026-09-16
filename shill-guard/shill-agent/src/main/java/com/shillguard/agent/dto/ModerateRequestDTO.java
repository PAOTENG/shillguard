package com.shillguard.agent.dto;

import lombok.Data;

import java.io.Serializable;
import java.util.List;

/**
 * 调用 Python 审核 Agent 的请求体。
 * 字段名与 Python schemas.ModerateRequest 严格一致（驼峰对应Python的camelCase）。
 */
@Data
public class ModerateRequestDTO implements Serializable {

    /** 举报记录ID */
    private Long reportId;

    /** 被举报用户ID */
    private Long reportedUserId;

    /** 内容类型：comment 或 post */
    private String contentType;

    /** 被举报的内容列表（可能多条评论或帖子） */
    private List<String> contentList;

    /** 举报分类：0=广告 1=违法 2=辱骂 3=涉黄 4=其他 */
    private Integer reportCategory;
}
