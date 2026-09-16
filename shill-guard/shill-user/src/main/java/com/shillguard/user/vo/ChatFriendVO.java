package com.shillguard.user.vo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 好友列表项：当前用户关注的某个用户 + 最近一条消息预览 + 未读标记。
 */
@Data
public class ChatFriendVO {
    private Long userId;
    private String nickname;
    private String avatarUrl;
    /** 最近一条消息正文（前端截断显示） */
    private String lastContent;
    /** 最近一条消息的发送者ID（用于判断方向） */
    private Long lastSenderId;
    private LocalDateTime lastTime;
    /** 最近一条是否对方发来且未读 → 红点 */
    private Boolean unread;
}
