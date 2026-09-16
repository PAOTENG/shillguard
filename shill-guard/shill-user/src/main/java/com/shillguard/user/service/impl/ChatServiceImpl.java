package com.shillguard.user.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shillguard.common.entity.SysUser;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.ResultCode;
import com.shillguard.user.entity.ChatMessage;
import com.shillguard.user.entity.ChatSticker;
import com.shillguard.user.mapper.ChatMessageMapper;
import com.shillguard.user.mapper.ChatStickerMapper;
import com.shillguard.user.mapper.SysUserMapper;
import com.shillguard.user.mapper.UserFollowMapper;
import com.shillguard.user.service.ChatService;
import com.shillguard.user.vo.ChatFriendVO;
import com.shillguard.user.vo.ChatMessageVO;
import com.shillguard.user.vo.ChatSendReq;
import com.shillguard.user.ws.OnlineSessionRegistry;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class ChatServiceImpl implements ChatService {

    private final ChatMessageMapper chatMessageMapper;
    private final UserFollowMapper userFollowMapper;
    private final SysUserMapper userMapper;
    private final ChatStickerMapper stickerMapper;
    private final OnlineSessionRegistry registry;
    private final ObjectMapper objectMapper;

    @Override
    @Transactional
    public ChatMessage send(Long senderId, Long receiverId, String content) {
        ChatSendReq req = new ChatSendReq();
        req.setReceiverId(receiverId);
        req.setType(0);
        req.setContent(content);
        return send(senderId, req);
    }

    @Override
    @Transactional
    public ChatMessage send(Long senderId, ChatSendReq req) {
        Long receiverId = req.getReceiverId();
        if (senderId == null || receiverId == null) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "发送失败：接收方无效");
        }
        if (senderId.equals(receiverId)) {
            throw new BizException(ResultCode.CHAT_SELF);
        }
        int type = req.getType() == null ? 0 : req.getType();
        // 文本消息内容不能为空；表情图/文件必须有 mediaUrl
        if (type == 0 && !StringUtils.hasText(req.getContent())) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "消息内容不能为空");
        }
        if ((type == 1 || type == 2) && !StringUtils.hasText(req.getMediaUrl())) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "媒体地址不能为空");
        }

        // 聊天规则：
        // 1. 互相关注 → 无限制
        // 2. 我关注对方、对方没关注我 → 只能发1条，对方回复后解锁
        // 3. 我没关注对方（取关了） → 禁止发消息，需重新关注
        boolean senderFollows = userFollowMapper.isFollowing(senderId, receiverId);
        boolean receiverFollows = userFollowMapper.isFollowing(receiverId, senderId);

        if (!senderFollows) {
            // 取关后禁止发消息
            throw new BizException(ResultCode.CHAT_NOT_FOLLOWING);
        }

        if (!receiverFollows) {
            // 单向关注：只能发1条，对方回复后才解锁
            long sent = chatMessageMapper.countSent(senderId, receiverId);
            long received = chatMessageMapper.countSent(receiverId, senderId);
            if (sent >= 1 && received == 0) {
                throw new BizException(ResultCode.CHAT_NOT_ALLOWED);
            }
        }

        ChatMessage msg = new ChatMessage();
        msg.setSenderId(senderId);
        msg.setReceiverId(receiverId);
        msg.setType(type);
        msg.setContent(type == 0 ? req.getContent() : (StringUtils.hasText(req.getContent()) ? req.getContent() : ""));
        msg.setMediaUrl(req.getMediaUrl());
        msg.setMediaName(req.getMediaName());
        msg.setMediaSize(req.getMediaSize());
        msg.setIsRead(0);
        msg.setCreatedTime(LocalDateTime.now());
        chatMessageMapper.insert(msg);

        // 实时推送给接收方（不在线则跳过，下次进入聊天界面拉历史时能看到）
        pushToReceiver(msg);
        return msg;
    }

    /** 推送给接收方：携带消息类型/媒体信息 + 发送者昵称头像，供前端弹窗直接展示 */
    private void pushToReceiver(ChatMessage msg) {
        try {
            SysUser sender = userMapper.selectById(msg.getSenderId());
            Map<String, Object> payload = new HashMap<>();
            payload.put("type", "message");
            payload.put("id", msg.getId());
            payload.put("senderId", msg.getSenderId());
            payload.put("receiverId", msg.getReceiverId());
            payload.put("msgType", msg.getType());
            payload.put("content", msg.getContent());
            payload.put("mediaUrl", msg.getMediaUrl());
            payload.put("mediaName", msg.getMediaName());
            payload.put("mediaSize", msg.getMediaSize());
            payload.put("createdTime", msg.getCreatedTime());
            payload.put("senderNickname", sender == null ? null : sender.getNickname());
            payload.put("senderAvatar", sender == null ? null : sender.getAvatarUrl());
            registry.sendToUser(msg.getReceiverId(), objectMapper.writeValueAsString(payload));
        } catch (Exception e) {
            log.warn("推送聊天消息失败: {}", e.getMessage());
        }
    }

    @Override
    public List<ChatFriendVO> friends(Long me) {
        return chatMessageMapper.listFriends(me);
    }

    @Override
    public List<ChatMessageVO> history(Long me, Long other, int pageNum, int pageSize) {
        int offset = (pageNum - 1) * pageSize;
        List<ChatMessage> list = chatMessageMapper.pageHistory(me, other, offset, pageSize);
        if (list == null || list.isEmpty()) return Collections.emptyList();
        // SQL 按时间倒序取一页，翻转成正序便于前端自下而上展示
        Collections.reverse(list);
        return list.stream().map(m -> {
            ChatMessageVO vo = new ChatMessageVO();
            BeanUtils.copyProperties(m, vo);
            return vo;
        }).toList();
    }

    @Override
    public void markRead(Long me, Long other) {
        chatMessageMapper.markRead(me, other);
    }

    @Override
    public long unreadCount(Long me, Long other) {
        return chatMessageMapper.countUnread(me, other);
    }

    @Override
    public List<ChatSticker> myStickers(Long userId) {
        return stickerMapper.selectList(new LambdaQueryWrapper<ChatSticker>()
                .eq(ChatSticker::getUserId, userId)
                .orderByDesc(ChatSticker::getCreatedTime));
    }

    @Override
    public ChatSticker addSticker(Long userId, String url) {
        if (!StringUtils.hasText(url)) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "表情地址不能为空");
        }
        ChatSticker s = new ChatSticker();
        s.setUserId(userId);
        s.setUrl(url);
        s.setCreatedTime(LocalDateTime.now());
        stickerMapper.insert(s);
        return s;
    }

    @Override
    public void deleteSticker(Long userId, Long stickerId) {
        ChatSticker s = stickerMapper.selectById(stickerId);
        if (s == null || !userId.equals(s.getUserId())) {
            throw new BizException(ResultCode.NOT_FOUND);
        }
        stickerMapper.deleteById(stickerId);
    }
}
