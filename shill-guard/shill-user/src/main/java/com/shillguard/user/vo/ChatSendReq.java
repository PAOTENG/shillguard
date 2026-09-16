package com.shillguard.user.vo;

import lombok.Data;

/**
 * 聊天发送请求：兼容文本/表情图/文件三类消息。
 * type=0 文本 → content 必填；type=1 表情图 → mediaUrl 必填；type=2 文件 → mediaUrl/mediaName/mediaSize 必填。
 */
@Data
public class ChatSendReq {
    private Long receiverId;
    /** 0=文本 1=表情图 2=文件，默认 0 */
    private Integer type;
    private String content;
    private String mediaUrl;
    private String mediaName;
    private Long mediaSize;
}
