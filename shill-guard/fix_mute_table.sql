-- 重建 agent_mute_record 表，使其与 shill-common 的 AgentMuteRecord 实体一致
-- 注意：会清空该表现有数据（当前表schema已严重落后，无法正常使用）
USE shill_guard;

DROP TABLE IF EXISTS `agent_mute_record`;

CREATE TABLE `agent_mute_record` (
    `mute_id`            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '禁言记录ID',
    `muted_user_id`      BIGINT       NOT NULL                COMMENT '被禁言用户ID',
    `reporter_user_id`   BIGINT       DEFAULT NULL            COMMENT '举报人用户ID（来自举报时填）',
    `reviewer_user_id`   BIGINT       DEFAULT NULL            COMMENT '审核人用户ID（人工操作时填）',
    `related_comment_id` BIGINT       DEFAULT NULL            COMMENT '关联的违规评论ID',
    `mute_reason`        VARCHAR(500) DEFAULT NULL            COMMENT '禁言原因',
    `evidence_detail`    TEXT         DEFAULT NULL            COMMENT '证据详情（Agent分析结果）',
    `mute_type`          INT          NOT NULL DEFAULT 0      COMMENT '类型：0=Agent自动 1=人工',
    `mute_days`          INT          NOT NULL DEFAULT 7      COMMENT '禁言天数',
    `mute_start_time`    DATETIME     DEFAULT NULL            COMMENT '禁言开始时间',
    `mute_end_time`      DATETIME     DEFAULT NULL            COMMENT '禁言解除时间',
    `status`             INT          NOT NULL DEFAULT 1      COMMENT '状态：1=禁言中 2=已解除 3=已申诉',
    `created_time`       DATETIME     DEFAULT NULL            COMMENT '创建时间（自动填充）',
    `updated_time`       DATETIME     DEFAULT NULL            COMMENT '更新时间',
    PRIMARY KEY (`mute_id`),
    KEY `idx_muted_user_id` (`muted_user_id`),
    KEY `idx_status` (`status`),
    KEY `idx_created_time` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='禁言记录表';
