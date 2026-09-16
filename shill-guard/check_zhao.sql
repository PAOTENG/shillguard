SELECT user_id, username, nickname, status, warning_level
FROM sys_user
WHERE nickname LIKE '%赵丽吃瓜%' OR username LIKE '%赵丽吃瓜%' OR nickname LIKE '%赵丽%';

SELECT comment_id, user_id, post_id, status, LEFT(content, 30) AS content_preview, created_time
FROM content_comment
WHERE user_id = (
    SELECT user_id FROM sys_user
    WHERE nickname LIKE '%赵丽吃瓜%' OR username LIKE '%赵丽吃瓜%' LIMIT 1
)
ORDER BY created_time DESC;

SELECT mute_id, muted_user_id, mute_type, mute_days, mute_start_time, mute_end_time, status
FROM agent_mute_record
WHERE muted_user_id = (
    SELECT user_id FROM sys_user
    WHERE nickname LIKE '%赵丽吃瓜%' OR username LIKE '%赵丽吃瓜%' LIMIT 1
)
ORDER BY mute_start_time DESC;
