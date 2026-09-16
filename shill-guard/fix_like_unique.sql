-- 帖子点赞并发去重：清历史重复行后加联合唯一索引。
-- 可重复执行：索引已存在时跳过。

DELETE t1 FROM content_like t1
INNER JOIN content_like t2
  ON t1.user_id = t2.user_id
 AND t1.target_id = t2.target_id
 AND t1.target_type = t2.target_type
 AND t1.like_id > t2.like_id;

SET @exist := (
  SELECT COUNT(1) FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'content_like'
    AND index_name = 'uk_user_target'
);

SET @sql := IF(@exist = 0,
  'ALTER TABLE content_like ADD UNIQUE INDEX uk_user_target (user_id, target_id, target_type)',
  'SELECT 1');

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
