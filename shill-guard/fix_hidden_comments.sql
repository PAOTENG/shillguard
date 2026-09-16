-- 1) 查看"赵丽吃瓜人"现状：用户状态 + 评论/帖子 status 分布 + 禁言记录
SELECT u.user_id, u.username, u.nickname, u.status, u.warning_level,
       (SELECT COUNT(*) FROM content_comment c WHERE c.user_id = u.user_id AND c.status = 0) AS visible_comments,
       (SELECT COUNT(*) FROM content_comment c WHERE c.user_id = u.user_id AND c.status = 1) AS hidden_comments,
       (SELECT COUNT(*) FROM content_post p WHERE p.user_id = u.user_id AND p.status = 0) AS visible_posts,
       (SELECT COUNT(*) FROM content_post p WHERE p.user_id = u.user_id AND p.status = 1) AS hidden_posts
FROM sys_user u
WHERE u.nickname LIKE '%赵丽吃瓜%' OR u.username LIKE '%赵丽吃瓜%';

SELECT m.mute_id, m.muted_user_id, m.mute_type, m.mute_days,
       m.mute_start_time, m.mute_end_time, m.status
FROM agent_mute_record m
WHERE m.muted_user_id = (SELECT user_id FROM sys_user WHERE nickname LIKE '%赵丽吃瓜%' LIMIT 1)
ORDER BY m.mute_start_time DESC;

-- 2) 手动补隐藏"赵丽吃瓜人"：所有 status=0 的评论和帖子置 status=1
UPDATE content_comment
SET status = 1
WHERE user_id = (SELECT user_id FROM sys_user WHERE nickname LIKE '%赵丽吃瓜%' LIMIT 1)
  AND status = 0;

UPDATE content_post
SET status = 1
WHERE user_id = (SELECT user_id FROM sys_user WHERE nickname LIKE '%赵丽吃瓜%' LIMIT 1)
  AND status = 0;

-- 3) 全量回溯：对所有当前被禁言/封禁（status<>0）的用户，把他们残留的 status=0 评论和帖子全部隐藏
UPDATE content_comment c
JOIN sys_user u ON c.user_id = u.user_id
SET c.status = 1
WHERE c.status = 0 AND u.status <> 0;

UPDATE content_post p
JOIN sys_user u ON p.user_id = u.user_id
SET p.status = 1
WHERE p.status = 0 AND u.status <> 0;
