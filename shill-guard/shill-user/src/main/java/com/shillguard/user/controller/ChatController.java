package com.shillguard.user.controller;

import com.shillguard.common.result.Result;
import com.shillguard.user.entity.ChatMessage;
import com.shillguard.user.entity.ChatSticker;
import com.shillguard.user.service.ChatService;
import com.shillguard.user.vo.ChatFriendVO;
import com.shillguard.user.vo.ChatMessageVO;
import com.shillguard.user.vo.ChatSendReq;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@Tag(name = "聊天接口")
@RestController
@RequestMapping("/api/chat")
@RequiredArgsConstructor
public class ChatController {

    private final ChatService chatService;

    @Operation(summary = "好友列表（我关注的人 + 最近消息 + 未读标记）")
    @GetMapping("/friends")
    public Result<List<ChatFriendVO>> friends(@RequestHeader("X-User-Id") Long me) {
        return Result.success(chatService.friends(me));
    }

    @Operation(summary = "与某人的聊天历史（分页，时间正序）")
    @GetMapping("/messages/{otherUserId}")
    public Result<List<ChatMessageVO>> history(@RequestHeader("X-User-Id") Long me,
                                               @PathVariable("otherUserId") Long otherUserId,
                                               @RequestParam(defaultValue = "1") int pageNum,
                                               @RequestParam(defaultValue = "50") int pageSize) {
        return Result.success(chatService.history(me, otherUserId, pageNum, pageSize));
    }

    @Operation(summary = "发送消息（REST 兜底，支持文本/表情图/文件，规则校验同 WS）")
    @PostMapping("/send")
    public Result<ChatMessage> send(@RequestHeader("X-User-Id") Long me,
                                    @RequestBody ChatSendReq req) {
        return Result.success(chatService.send(me, req));
    }

    @Operation(summary = "标记与某人的未读消息为已读")
    @PostMapping("/read/{otherUserId}")
    public Result<Void> markRead(@RequestHeader("X-User-Id") Long me,
                                 @PathVariable("otherUserId") Long otherUserId) {
        chatService.markRead(me, otherUserId);
        return Result.success(null);
    }

    @Operation(summary = "与某人的未读消息数")
    @GetMapping("/unread/{otherUserId}")
    public Result<Long> unread(@RequestHeader("X-User-Id") Long me,
                               @PathVariable("otherUserId") Long otherUserId) {
        return Result.success(chatService.unreadCount(me, otherUserId));
    }

    // ===== 自定义表情包 =====

    @Operation(summary = "我的自定义表情包列表")
    @GetMapping("/stickers")
    public Result<List<ChatSticker>> myStickers(@RequestHeader("X-User-Id") Long me) {
        return Result.success(chatService.myStickers(me));
    }

    @Operation(summary = "新增自定义表情包（图片先上传 /api/file/image 拿到 url 后调用）")
    @PostMapping("/stickers")
    public Result<ChatSticker> addSticker(@RequestHeader("X-User-Id") Long me,
                                          @RequestBody Map<String, String> body) {
        return Result.success(chatService.addSticker(me, body.get("url")));
    }

    @Operation(summary = "删除自定义表情包（仅限本人）")
    @DeleteMapping("/stickers/{stickerId}")
    public Result<Void> deleteSticker(@RequestHeader("X-User-Id") Long me,
                                      @PathVariable("stickerId") Long stickerId) {
        chatService.deleteSticker(me, stickerId);
        return Result.success(null);
    }
}
