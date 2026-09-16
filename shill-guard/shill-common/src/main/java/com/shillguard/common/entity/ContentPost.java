package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

@Data
@TableName("content_post")
public class ContentPost implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long postId;
    private Long userId;
    private String title;
    private String content;
    private String coverUrl;
    private String mediaUrl;
    /** 1=纯文字 2=图文 3=视频 */
    private Integer postType;
    private String topicTag;
    /** 0=正常 1=已删除 2=审核中 */
    private Integer status;
    private Long viewCount;
    private Integer likeCount;
    private Integer commentCount;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdTime;
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedTime;
}
