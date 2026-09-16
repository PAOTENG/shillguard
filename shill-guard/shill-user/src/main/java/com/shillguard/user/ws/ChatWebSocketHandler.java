package com.shillguard.user.ws;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shillguard.user.entity.ChatMessage;
import com.shillguard.user.service.ChatService;
import com.shillguard.user.vo.ChatSendReq;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.util.HashMap;
import java.util.Map;

/**
 * 聊天 WebSocket 处理器：
 * - 连接建立：把会话注册到 OnlineSessionRegistry
 * - 收到消息：解析 {receiverId, type, content, mediaUrl, mediaName, mediaSize}
 *   → 调 ChatService.send 落库并推送给对方 → 给发送者回 ack
 * - 连接关闭：注销会话
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ChatWebSocketHandler extends TextWebSocketHandler {

    private final ChatService chatService;
    private final OnlineSessionRegistry registry;
    private final ObjectMapper objectMapper;

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        Long userId = (Long) session.getAttributes().get("userId");
        registry.register(userId, session);
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
        Long senderId = (Long) session.getAttributes().get("userId");
        JsonNode node = objectMapper.readTree(message.getPayload());

        ChatSendReq req = new ChatSendReq();
        req.setReceiverId(node.has("receiverId") ? node.get("receiverId").asLong() : null);
        req.setType(node.has("type") ? node.get("type").asInt() : 0);
        req.setContent(node.has("content") ? node.get("content").asText() : null);
        req.setMediaUrl(node.has("mediaUrl") ? node.get("mediaUrl").asText() : null);
        req.setMediaName(node.has("mediaName") ? node.get("mediaName").asText() : null);
        req.setMediaSize(node.has("mediaSize") && !node.get("mediaSize").isNull() ? node.get("mediaSize").asLong() : null);

        // 基本校验：文本内容非空，或媒体地址非空
        boolean hasText = req.getContent() != null && !req.getContent().isBlank();
        boolean hasMedia = req.getMediaUrl() != null && !req.getMediaUrl().isBlank();
        if (req.getReceiverId() == null || (!hasText && !hasMedia)) return;

        try {
            ChatMessage saved = chatService.send(senderId, req);
            // 给发送者回 ack（确认消息已落库，前端可追加到聊天界面）
            Map<String, Object> ack = basePayload("ack", saved);
            session.sendMessage(new TextMessage(objectMapper.writeValueAsString(ack)));
        } catch (Exception e) {
            // 规则不通过等业务异常：回 error 事件，前端提示
            Map<String, Object> err = new HashMap<>();
            err.put("type", "error");
            err.put("receiverId", req.getReceiverId());
            err.put("message", e.getMessage());
            session.sendMessage(new TextMessage(objectMapper.writeValueAsString(err)));
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        Long userId = (Long) session.getAttributes().get("userId");
        if (userId != null) {
            registry.unregister(userId, session);
        }
    }

    private Map<String, Object> basePayload(String type, ChatMessage m) {
        Map<String, Object> map = new HashMap<>();
        map.put("type", type);
        map.put("id", m.getId());
        map.put("senderId", m.getSenderId());
        map.put("receiverId", m.getReceiverId());
        map.put("msgType", m.getType());
        map.put("content", m.getContent());
        map.put("mediaUrl", m.getMediaUrl());
        map.put("mediaName", m.getMediaName());
        map.put("mediaSize", m.getMediaSize());
        map.put("createdTime", m.getCreatedTime());
        return map;
    }
}
