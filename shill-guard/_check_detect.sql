-- 检测是否跑出结果
SELECT 'risk_record' AS src, risk_id, user_id, anomaly_score, warning_level, detect_time FROM user_risk_record ORDER BY risk_id DESC LIMIT 10;
SELECT 'mute_record' AS src, mute_id, muted_user_id, mute_type, mute_days, status, created_time FROM agent_mute_record ORDER BY mute_id DESC LIMIT 10;
-- 检测后用户的 warning_level
SELECT user_id, username, nickname, status, warning_level FROM sys_user WHERE user_id IN (8,9,11) ORDER BY user_id;
-- 今日恶意评论还在不在
SELECT user_id, COUNT(*) AS cnt FROM content_comment WHERE created_time >= CURDATE() AND user_id IN (8,9,11) GROUP BY user_id;
