-- ================================================================
-- 恶意行为用户检测：风险记录表 + sys_user 预警级别列
-- ================================================================
USE shill_guard;

-- 用户风险记录表：每次检测每个用户一条记录，保留历史与证据（便于申诉复核）
CREATE TABLE IF NOT EXISTS `user_risk_record` (
    `risk_id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '风险记录ID',
    `user_id`          BIGINT       NOT NULL                COMMENT '用户ID',
    `anomaly_score`    FLOAT        NOT NULL DEFAULT 0      COMMENT '异常分数 0~1',
    `warning_level`    INT          NOT NULL DEFAULT 0      COMMENT '级别：1=预警 2=高危(已禁言)',
    `content_snapshot` TEXT         DEFAULT NULL            COMMENT '本次检测的今日内容快照（帖子+评论）',
    `evidence_detail`  TEXT         DEFAULT NULL            COMMENT 'Agent生成的完整证据报告（高危用户）',
    `detect_time`      DATETIME     DEFAULT NULL            COMMENT '检测时间',
    PRIMARY KEY (`risk_id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_warning_level` (`warning_level`),
    KEY `idx_detect_time` (`detect_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户恶意行为风险记录表';

-- sys_user 增加预警级别列（冗余，用于用户管理页快速显示徽标，避免每次查风险表取最新）
-- 0=无 1=预警 2=高危
ALTER TABLE `sys_user` ADD COLUMN `warning_level` INT NOT NULL DEFAULT 0 COMMENT '预警级别：0=无 1=预警 2=高危' AFTER `status`;
