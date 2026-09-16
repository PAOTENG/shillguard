package com.shillguard.content.vo;

import lombok.Data;

/**
 * 发布帖子的审核结果。
 * reviewStatus: 0=审核通过 2=审核中 3=审核不通过
 */
@Data
public class PostPublishResultVO {

    private Long postId;

    private Integer reviewStatus;

    /** 审核不通过时的原因（命中敏感词等） */
    private String reason;
}
