package com.shillguard.user.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.user.entity.ChatMessage;
import com.shillguard.user.vo.ChatFriendVO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface ChatMessageMapper extends BaseMapper<ChatMessage> {

    /** A 发给 B 的消息数 */
    @Select("SELECT COUNT(*) FROM chat_message WHERE sender_id = #{a} AND receiver_id = #{b}")
    long countSent(@Param("a") Long a, @Param("b") Long b);

    /** 我关注的人列表 + 每人最近一条消息（含方向与未读标记），按最近消息时间倒序 */
    @Select("SELECT u.user_id AS userId, u.nickname AS nickname, u.avatar_url AS avatarUrl, " +
            "CASE WHEN m.type = 1 THEN '[表情]' " +
            "  WHEN m.type = 2 THEN CONCAT('[文件] ', IFNULL(m.media_name,'')) " +
            "  ELSE m.content END AS lastContent, " +
            "m.sender_id AS lastSenderId, m.created_time AS lastTime, " +
            "CASE WHEN m.sender_id = u.user_id AND m.is_read = 0 THEN 1 ELSE 0 END AS unread " +
            "FROM user_follow f " +
            "INNER JOIN sys_user u ON f.following_id = u.user_id " +
            "LEFT JOIN chat_message m ON m.id = ( " +
            "  SELECT MAX(id) FROM chat_message " +
            "  WHERE (sender_id = #{me} AND receiver_id = u.user_id) " +
            "     OR (sender_id = u.user_id AND receiver_id = #{me}) " +
            ") " +
            "WHERE f.follower_id = #{me} AND u.status = 0 " +
            "ORDER BY (m.created_time IS NULL), m.created_time DESC, u.nickname")
    List<ChatFriendVO> listFriends(@Param("me") Long me);

    /** 与某人的聊天历史（分页），按时间正序，限定双方消息 */
    @Select("SELECT * FROM chat_message " +
            "WHERE (sender_id = #{me} AND receiver_id = #{other}) " +
            "   OR (sender_id = #{other} AND receiver_id = #{me}) " +
            "ORDER BY created_time DESC, id DESC " +
            "LIMIT #{size} OFFSET #{offset}")
    List<ChatMessage> pageHistory(@Param("me") Long me, @Param("other") Long other,
                                  @Param("offset") int offset, @Param("size") int size);

    /** 对方发给我、且未读的消息数 */
    @Select("SELECT COUNT(*) FROM chat_message WHERE sender_id = #{other} AND receiver_id = #{me} AND is_read = 0")
    long countUnread(@Param("me") Long me, @Param("other") Long other);

    /** 把对方发给我、未读的消息全部标记为已读 */
    @Update("UPDATE chat_message SET is_read = 1 WHERE sender_id = #{other} AND receiver_id = #{me} AND is_read = 0")
    int markRead(@Param("me") Long me, @Param("other") Long other);
}
