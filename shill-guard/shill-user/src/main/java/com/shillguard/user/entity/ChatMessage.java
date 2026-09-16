package com.shillguard.user.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 用户私聊消息。is_read 从“接收方”视角：0=接收方未读，1=已读。
 */
@Data
@TableName("chat_message")
public class ChatMessage {

    @TableId(type = IdType.AUTO)
    private Long id;
    private Long senderId;
    private Long receiverId;
    private String content;
    private Integer isRead;
    private LocalDateTime createdTime;
    /** 消息类型：0=文本 1=表情图 2=文件 */
    private Integer type;
    /** 媒体地址（表情图/文件的 MinIO URL） */
    private String mediaUrl;
    /** 文件原名 / 表情图标记 */
    private String mediaName;
    /** 文件大小（字节） */
    private Long mediaSize;
}
