-- 重建 sys_notification 表，使其与 SysNotification 实体 + schema.sql 一致
-- 运行中的表被改成了 receiver_id/sender_id/related_type/read_time 模型，
-- 但实体和所有 service 代码都用 user_id，那些列无任何代码引用，属于孤立列。
USE shill_guard;

DROP TABLE IF EXISTS `sys_notification`;

CREATE TABLE `sys_notification` (
    `notice_id`     BIGINT       NOT NULL AUTO_INCREMENT COMMENT '通知ID',
    `user_id`       BIGINT       NOT NULL                COMMENT '接收通知的用户ID',
    `notice_type`   INT          NOT NULL DEFAULT 0      COMMENT '类型：0=系统 1=禁言 2=评论 3=点赞 4=申诉',
    `title`         VARCHAR(100) DEFAULT NULL            COMMENT '通知标题',
    `content`       VARCHAR(500) DEFAULT NULL            COMMENT '通知内容',
    `related_id`    BIGINT       DEFAULT NULL            COMMENT '关联业务ID',
    `is_read`       INT          NOT NULL DEFAULT 0      COMMENT '是否已读：0=未读 1=已读',
    `created_time`  DATETIME     DEFAULT NULL            COMMENT '创建时间（自动填充）',
    PRIMARY KEY (`notice_id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_is_read` (`is_read`),
    KEY `idx_created_time` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='站内通知表';
