package com.shillguard.user.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 用户自定义表情包（用户上传的图片表情，存于 MinIO）。
 */
@Data
@TableName("chat_sticker")
public class ChatSticker implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;
    /** 所属用户 */
    private Long userId;
    /** MinIO 图片地址 */
    private String url;
    private LocalDateTime createdTime;
}
