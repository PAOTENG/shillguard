package com.shillguard.user.ws;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;

import java.util.concurrent.ConcurrentHashMap;

/**
 * 在线用户会话注册表：记录每个用户的 WebSocket 会话，用于实时推送。
 * 单机内存方案；多实例可扩展为 Redis Pub/Sub 广播。
 */
@Slf4j
@Component
public class OnlineSessionRegistry {

    private final ConcurrentHashMap<Long, WebSocketSession> sessions = new ConcurrentHashMap<>();

    public void register(Long userId, WebSocketSession session) {
        WebSocketSession old = sessions.put(userId, session);
        if (old != null && old.isOpen()) {
            try { old.close(); } catch (Exception ignored) {}
        }
        log.info("用户上线: userId={}, 在线人数={}", userId, sessions.size());
    }

    public void unregister(Long userId, WebSocketSession session) {
        sessions.remove(userId, session);
        log.info("用户下线: userId={}, 在线人数={}", userId, sessions.size());
    }

    public boolean isOnline(Long userId) {
        return sessions.containsKey(userId);
    }

    /** 给指定用户推送一条文本消息；不在线则返回 false */
    public boolean sendToUser(Long userId, String payload) {
        WebSocketSession session = sessions.get(userId);
        if (session == null || !session.isOpen()) {
            return false;
        }
        try {
            session.sendMessage(new TextMessage(payload));
            return true;
        } catch (Exception e) {
            log.warn("推送消息失败: userId={}, err={}", userId, e.getMessage());
            return false;
        }
    }
}
