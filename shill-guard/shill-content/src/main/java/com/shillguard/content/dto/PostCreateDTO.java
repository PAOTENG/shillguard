package com.shillguard.content.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class PostCreateDTO {

    /** 标题可选，为空时后端用内容首句或“未命名笔记”兜底 */
    private String title;

    @NotBlank(message = "内容不能为空")
    private String content;

    /** 封面图 URL（图文帖的第一张图） */
    private String coverUrl;

    /** 视频 URL（视频帖） */
    private String mediaUrl;

    /** 1=纯文字 2=图文 3=视频；为空时后端按 coverUrl/mediaUrl 自动推断 */
    private Integer postType;

    private String topicTag;
}
