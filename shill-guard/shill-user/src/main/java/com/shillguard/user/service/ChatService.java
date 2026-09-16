package com.shillguard.user.service;

import com.shillguard.user.entity.ChatMessage;
import com.shillguard.user.entity.ChatSticker;
import com.shillguard.user.vo.ChatFriendVO;
import com.shillguard.user.vo.ChatMessageVO;
import com.shillguard.user.vo.ChatSendReq;

import java.util.List;

public interface ChatService {

    /** 发送消息：校验聊天规则、落库、实时推送给接收方，返回已落库的消息（文本） */
    ChatMessage send(Long senderId, Long receiverId, String content);

    /** 发送消息（统一入口：文本/表情图/文件），校验规则、落库、实时推送 */
    ChatMessage send(Long senderId, ChatSendReq req);

    /** 好友列表（我关注的人 + 每人最近一条消息 + 未读标记） */
    List<ChatFriendVO> friends(Long me);

    /** 与某人的聊天历史（分页，时间正序，前端展示用） */
    List<ChatMessageVO> history(Long me, Long other, int pageNum, int pageSize);

    /** 标记对方发给我的未读消息为已读 */
    void markRead(Long me, Long other);

    /** 对方发给我、未读的消息数（用于徽标） */
    long unreadCount(Long me, Long other);

    /** 我的自定义表情包列表 */
    List<ChatSticker> myStickers(Long userId);

    /** 新增自定义表情包（图片已上传 MinIO，这里只存 url 元数据） */
    ChatSticker addSticker(Long userId, String url);

    /** 删除自定义表情包（仅限本人） */
    void deleteSticker(Long userId, Long stickerId);
}
