-- ================================================================
-- ShillGuard 水军智能检测平台 - 数据库初始化脚本
-- 数据库: shill_guard
-- 字符集: utf8mb4
-- 执行方式: MySQL 8.0+
-- ================================================================

-- 使用目标数据库（Docker 容器启动时会自动创建 shill_guard 数据库）
USE shill_guard;

-- ================================================================
-- 表1: sys_user 用户表
-- 存储所有注册用户信息，包括管理员
-- ================================================================
CREATE TABLE IF NOT EXISTS `sys_user` (
    `user_id`         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '用户ID',
    `username`        VARCHAR(50)  NOT NULL                COMMENT '登录账号，唯一',
    `password`        VARCHAR(100) NOT NULL                COMMENT '密码（BCrypt加密）',
    `nickname`        VARCHAR(50)  DEFAULT NULL            COMMENT '昵称',
    `phone`           VARCHAR(20)  DEFAULT NULL            COMMENT '手机号',
    `email`           VARCHAR(100) DEFAULT NULL            COMMENT '邮箱',
    `avatar_url`      VARCHAR(500) DEFAULT NULL            COMMENT '头像URL（存MinIO）',
    `role`            INT          NOT NULL DEFAULT 0      COMMENT '角色：0=普通用户 1=审核员 2=管理员 3=超级管理员',
    `status`          INT          NOT NULL DEFAULT 0      COMMENT '状态：0=正常 1=禁言 2=封号',
    `register_ip`     VARCHAR(50)  DEFAULT NULL            COMMENT '注册时IP',
    `last_login_time` DATETIME     DEFAULT NULL            COMMENT '最后登录时间',
    `last_login_ip`   VARCHAR(50)  DEFAULT NULL            COMMENT '最后登录IP',
    `created_time`    DATETIME     DEFAULT NULL            COMMENT '创建时间（自动填充）',
    `updated_time`    DATETIME     DEFAULT NULL            COMMENT '更新时间（自动填充）',
    PRIMARY KEY (`user_id`),
    UNIQUE KEY `uk_username` (`username`),
    KEY `idx_status` (`status`),
    KEY `idx_role` (`role`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';


-- ================================================================
-- 表2: content_post 帖子表
-- 存储用户发布的所有帖子
-- ================================================================
CREATE TABLE IF NOT EXISTS `content_post` (
    `post_id`       BIGINT        NOT NULL AUTO_INCREMENT COMMENT '帖子ID',
    `user_id`       BIGINT        NOT NULL                COMMENT '发布者用户ID',
    `title`         VARCHAR(200)  NOT NULL                COMMENT '帖子标题',
    `content`       TEXT          NOT NULL                COMMENT '帖子正文',
    `cover_url`     VARCHAR(500)  DEFAULT NULL            COMMENT '封面图URL',
    `media_url`     VARCHAR(500)  DEFAULT NULL            COMMENT '视频/图组URL',
    `post_type`     INT           NOT NULL DEFAULT 1      COMMENT '类型：1=纯文字 2=图文 3=视频',
    `topic_tag`     VARCHAR(50)   DEFAULT NULL            COMMENT '话题标签',
    `status`        INT           NOT NULL DEFAULT 0      COMMENT '状态：0=正常 1=已删除 2=审核中',
    `view_count`    BIGINT        NOT NULL DEFAULT 0      COMMENT '浏览数',
    `like_count`    INT           NOT NULL DEFAULT 0      COMMENT '点赞数',
    `comment_count` INT           NOT NULL DEFAULT 0      COMMENT '评论数',
    `created_time`  DATETIME      DEFAULT NULL            COMMENT '发布时间（自动填充）',
    `updated_time`  DATETIME      DEFAULT NULL            COMMENT '更新时间（自动填充）',
    PRIMARY KEY (`post_id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_status` (`status`),
    KEY `idx_topic_tag` (`topic_tag`),
    KEY `idx_created_time` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='帖子表';


-- ================================================================
-- 表3: content_comment 评论表
-- 存储所有帖子评论（支持二级回复）
-- ================================================================
CREATE TABLE IF NOT EXISTS `content_comment` (
    `comment_id`        BIGINT   NOT NULL AUTO_INCREMENT COMMENT '评论ID',
    `user_id`           BIGINT   NOT NULL                COMMENT '评论者用户ID',
    `post_id`           BIGINT   NOT NULL                COMMENT '所属帖子ID',
    `parent_comment_id` BIGINT   DEFAULT NULL            COMMENT '父评论ID（NULL=一级评论）',
    `reply_to_user_id`  BIGINT   DEFAULT NULL            COMMENT '被回复用户ID',
    `content`           TEXT     NOT NULL                COMMENT '评论内容',
    `like_count`        INT      NOT NULL DEFAULT 0      COMMENT '点赞数',
    `reply_count`       INT      NOT NULL DEFAULT 0      COMMENT '子回复数量',
    `status`            INT      NOT NULL DEFAULT 0      COMMENT '状态：0=正常 1=已删除',
    `is_top`            INT      NOT NULL DEFAULT 0      COMMENT '是否置顶：0=否 1=是',
    `client_ip`         VARCHAR(50) DEFAULT NULL         COMMENT '评论者IP（用于水军检测）',
    `created_time`      DATETIME DEFAULT NULL            COMMENT '评论时间（自动填充）',
    `updated_time`      DATETIME DEFAULT NULL            COMMENT '更新时间（自动填充）',
    PRIMARY KEY (`comment_id`),
    KEY `idx_post_id` (`post_id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_parent_comment_id` (`parent_comment_id`),
    KEY `idx_status` (`status`),
    KEY `idx_created_time` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='评论表';


-- ================================================================
-- 表3b: content_like 点赞表
-- 用户对帖子/评论的点赞；联合唯一约束防并发重复点赞
-- ================================================================
CREATE TABLE IF NOT EXISTS `content_like` (
    `like_id`      BIGINT   NOT NULL AUTO_INCREMENT COMMENT '点赞ID',
    `user_id`      BIGINT   NOT NULL                COMMENT '点赞用户ID',
    `target_id`    BIGINT   NOT NULL                COMMENT '被点赞对象ID',
    `target_type`  TINYINT  NOT NULL                COMMENT '0=评论 1=帖子',
    `created_time` DATETIME DEFAULT NULL            COMMENT '点赞时间',
    PRIMARY KEY (`like_id`),
    UNIQUE KEY `uk_user_target` (`user_id`, `target_id`, `target_type`),
    KEY `idx_target` (`target_type`, `target_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='点赞表';


-- ================================================================
-- 表4: content_report 举报表
-- 用户对帖子/评论/用户的举报记录
-- ================================================================
CREATE TABLE IF NOT EXISTS `content_report` (
    `report_id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '举报ID',
    `reporter_user_id`   BIGINT       NOT NULL                COMMENT '举报人用户ID',
    `reported_comment_id` BIGINT      DEFAULT NULL            COMMENT '被举报的评论ID（举报评论时填）',
    `reported_post_id`   BIGINT       DEFAULT NULL            COMMENT '被举报的帖子ID（举报帖子时填）',
    `reported_user_id`   BIGINT       DEFAULT NULL            COMMENT '被举报的用户ID',
    `report_category`    INT          NOT NULL DEFAULT 0      COMMENT '举报类型：0=广告水军 1=违法信息 2=侮辱谩骂 3=色情低俗 4=其他',
    `report_reason`      VARCHAR(500) DEFAULT NULL            COMMENT '举报说明',
    `reviewer_user_id`   BIGINT       DEFAULT NULL            COMMENT '审核人用户ID',
    `review_note`        VARCHAR(500) DEFAULT NULL            COMMENT '审核备注',
    `status`             INT          NOT NULL DEFAULT 0      COMMENT '状态：0=待处理 1=处理中 2=已忽略 3=已删帖 4=已转Agent',
    `created_time`       DATETIME     DEFAULT NULL            COMMENT '举报时间（自动填充）',
    `updated_time`       DATETIME     DEFAULT NULL            COMMENT '更新时间',
    PRIMARY KEY (`report_id`),
    KEY `idx_reporter_user_id` (`reporter_user_id`),
    KEY `idx_status` (`status`),
    KEY `idx_created_time` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='举报表';


-- ================================================================
-- 表5: agent_mute_record 禁言记录表
-- 记录 Agent 自动检测和管理员手动操作的所有禁言
-- ================================================================
CREATE TABLE IF NOT EXISTS `agent_mute_record` (
    `mute_id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '禁言记录ID',
    `muted_user_id`    BIGINT       NOT NULL                COMMENT '被禁言用户ID',
    `reporter_user_id` BIGINT       DEFAULT NULL            COMMENT '举报人用户ID（来自举报时填）',
    `reviewer_user_id` BIGINT       DEFAULT NULL            COMMENT '审核人用户ID（人工操作时填）',
    `related_comment_id` BIGINT     DEFAULT NULL            COMMENT '关联的违规评论ID',
    `mute_reason`      VARCHAR(500) DEFAULT NULL            COMMENT '禁言原因',
    `evidence_detail`  TEXT         DEFAULT NULL            COMMENT '证据详情（Agent分析结果）',
    `mute_type`        INT          NOT NULL DEFAULT 0      COMMENT '类型：0=Agent自动 1=人工',
    `mute_days`        INT          NOT NULL DEFAULT 7      COMMENT '禁言天数',
    `mute_start_time`  DATETIME     DEFAULT NULL            COMMENT '禁言开始时间',
    `mute_end_time`    DATETIME     DEFAULT NULL            COMMENT '禁言解除时间',
    `status`           INT          NOT NULL DEFAULT 1      COMMENT '状态：1=禁言中 2=已解除 3=已申诉',
    `created_time`     DATETIME     DEFAULT NULL            COMMENT '创建时间（自动填充）',
    `updated_time`     DATETIME     DEFAULT NULL            COMMENT '更新时间',
    PRIMARY KEY (`mute_id`),
    KEY `idx_muted_user_id` (`muted_user_id`),
    KEY `idx_status` (`status`),
    KEY `idx_created_time` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='禁言记录表';


-- ================================================================
-- 初始数据：插入默认管理员账号
--
-- 账号: admin
-- 密码: admin2026  (以下哈希是 BCryptPasswordEncoder(10) 的结果)
-- ！！如果登录失败，请用注册接口创建账号，然后执行：
-- UPDATE sys_user SET role = 3 WHERE username = '你的账号';
-- ================================================================
INSERT IGNORE INTO `sys_user`
    (`username`, `password`, `nickname`, `role`, `status`, `created_time`, `updated_time`)
VALUES
    ('admin',
     '$2a$10$sMl2H4DjxdlHY8FkVJCF8uBgFHrY8Q2NbSfJlQFX3V0GwNX7GJLZK',
     '超级管理员',
     3, 0, NOW(), NOW());

-- ================================================================
-- 表6: sys_notification 站内通知表
-- 存储所有推送给用户的通知（禁言通知、评论通知、申诉结果等）
-- ================================================================
CREATE TABLE IF NOT EXISTS `sys_notification` (
    `notice_id`     BIGINT       NOT NULL AUTO_INCREMENT COMMENT '通知ID',
    `user_id`       BIGINT       NOT NULL                COMMENT '接收通知的用户ID',
    `notice_type`   INT          NOT NULL DEFAULT 0      COMMENT '类型：0=系统通知 1=禁言通知 2=评论通知 3=点赞通知 4=申诉结果',
    `title`         VARCHAR(100) DEFAULT NULL            COMMENT '通知标题',
    `content`       VARCHAR(500) DEFAULT NULL            COMMENT '通知内容',
    `related_id`    BIGINT       DEFAULT NULL            COMMENT '关联业务ID（如禁言记录ID、评论ID等）',
    `is_read`       INT          NOT NULL DEFAULT 0      COMMENT '是否已读：0=未读 1=已读',
    `created_time`  DATETIME     DEFAULT NULL            COMMENT '创建时间（自动填充）',
    PRIMARY KEY (`notice_id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_is_read` (`is_read`),
    KEY `idx_created_time` (`created_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='站内通知表';


-- ================================================================
-- 初始数据：插入几条测试帖子（便于前端首页展示）
-- 注意：user_id=1 对应上面插入的 admin 用户（自增从1开始）
-- ================================================================
INSERT IGNORE INTO `content_post`
    (`post_id`, `user_id`, `title`, `content`, `post_type`, `topic_tag`, `status`, `view_count`, `like_count`, `comment_count`, `created_time`, `updated_time`)
VALUES
    (1, 1, '欢迎来到 ShillGuard！', '这是一个社交媒体水军智能检测平台，我们致力于打击虚假评论，维护真实的用户生态。', 1, '公告', 0, 100, 20, 3, NOW(), NOW()),
    (2, 1, '平台使用指南', '注册账号后即可发布帖子和评论。管理员会定期检测水军账号，请放心使用本平台。', 1, '帮助', 0, 50, 10, 1, NOW(), NOW());
