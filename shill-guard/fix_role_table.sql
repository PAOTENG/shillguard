-- 修复 sys_role：去掉 AUTO_INCREMENT，使 role_id 与 sys_user.role(0-3) 精确对应
USE shill_guard;

-- 先清空角色菜单关联与角色表（role_menu 无外键约束，直接重建）
DELETE FROM sys_role_menu;
DROP TABLE IF EXISTS `sys_role`;

CREATE TABLE `sys_role` (
    `role_id`      BIGINT       NOT NULL                COMMENT '角色ID（与 sys_user.role 对应，手动分配）',
    `role_name`    VARCHAR(50)  NOT NULL                COMMENT '角色名称',
    `role_code`    VARCHAR(50)  NOT NULL                COMMENT '角色编码',
    `description`  VARCHAR(200) DEFAULT NULL            COMMENT '描述',
    `status`       INT          NOT NULL DEFAULT 0      COMMENT '状态：0=启用 1=禁用',
    `created_time` DATETIME     DEFAULT NULL            COMMENT '创建时间',
    `updated_time` DATETIME     DEFAULT NULL            COMMENT '更新时间',
    PRIMARY KEY (`role_id`),
    UNIQUE KEY `uk_role_code` (`role_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色表';

-- 精确插入预置角色 0-3（无 AUTO_INCREMENT，0 可正常存储）
INSERT INTO `sys_role` (`role_id`, `role_name`, `role_code`, `description`, `status`, `created_time`, `updated_time`) VALUES
    (0, '普通用户',    'user',        '前台普通用户，无后台权限',         0, NOW(), NOW()),
    (1, '审核员',      'reviewer',    '可处理举报、查看禁言、AI审核',       0, NOW(), NOW()),
    (2, '管理员',      'admin',       '可管理内容/用户/举报/禁言',         0, NOW(), NOW()),
    (3, '超级管理员',  'super_admin', '全部权限，含角色权限管理',           0, NOW(), NOW());

-- 重新分配角色-菜单（与 rbac_schema.sql 种子一致）
INSERT INTO `sys_role_menu` (`role_id`, `menu_id`) VALUES
    (3, 1),(3, 10),(3, 11),(3, 12),(3, 13),(3, 20),(3, 21),(3, 22),(3, 23),
    (2, 1),(2, 10),(2, 11),(2, 12),(2, 13),(2, 20),(2, 21),(2, 23),
    (1, 1),(1, 13),(1, 23);
