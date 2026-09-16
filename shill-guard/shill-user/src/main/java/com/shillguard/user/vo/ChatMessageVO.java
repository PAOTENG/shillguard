package com.shillguard.user.vo;

import lombok.Data;

import java.time.LocalDateTime;

/** 聊天消息（聊天界面展示用） */
@Data
public class ChatMessageVO {
    private Long id;
    private Long senderId;
    private Long receiverId;
    private String content;
    private Integer isRead;
    private LocalDateTime createdTime;
    /** 消息类型：0=文本 1=表情图 2=文件 */
    private Integer type;
    private String mediaUrl;
    private String mediaName;
    private Long mediaSize;
    /** 发送者昵称（仅用于实时推送 payload，历史消息不需要） */
    private String senderNickname;
    /** 发送者头像（仅用于实时推送 payload） */
    private String senderAvatar;
}
