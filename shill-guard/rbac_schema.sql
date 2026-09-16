-- ================================================================
-- RBAC 角色权限表 + 种子数据
-- 角色ID 与 sys_user.role (INT) 对应：0=普通 1=审核员 2=管理员 3=超管
-- ================================================================
USE shill_guard;

-- 角色表（role_id 不用 AUTO_INCREMENT：需与 sys_user.role 精确对应，预置 0-3 手动分配）
CREATE TABLE IF NOT EXISTS `sys_role` (
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

-- 菜单/权限表
CREATE TABLE IF NOT EXISTS `sys_menu` (
    `menu_id`      BIGINT       NOT NULL AUTO_INCREMENT COMMENT '菜单ID',
    `parent_id`    BIGINT       NOT NULL DEFAULT 0      COMMENT '父菜单ID（0=顶级）',
    `menu_name`    VARCHAR(50)  NOT NULL                COMMENT '菜单名称',
    `menu_type`    INT          NOT NULL DEFAULT 1      COMMENT '类型：0=目录 1=菜单 2=按钮',
    `path`         VARCHAR(100) DEFAULT NULL            COMMENT '前端路由路径',
    `component`    VARCHAR(100) DEFAULT NULL            COMMENT '前端组件名',
    `perms`        VARCHAR(100) DEFAULT NULL            COMMENT '权限标识',
    `icon`         VARCHAR(50)  DEFAULT NULL            COMMENT '图标',
    `sort`         INT          NOT NULL DEFAULT 0      COMMENT '排序',
    `status`       INT          NOT NULL DEFAULT 0      COMMENT '状态：0=启用 1=禁用',
    `created_time` DATETIME     DEFAULT NULL            COMMENT '创建时间',
    `updated_time` DATETIME     DEFAULT NULL            COMMENT '更新时间',
    PRIMARY KEY (`menu_id`),
    KEY `idx_parent_id` (`parent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='菜单权限表';

-- 角色-菜单关联表
CREATE TABLE IF NOT EXISTS `sys_role_menu` (
    `role_id` BIGINT NOT NULL COMMENT '角色ID',
    `menu_id` BIGINT NOT NULL COMMENT '菜单ID',
    PRIMARY KEY (`role_id`, `menu_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色菜单关联表';

-- ================================================================
-- 种子数据：角色（精确插入 0-3，无 AUTO_INCREMENT 故 0 可正常存储）
-- ================================================================
INSERT INTO `sys_role` (`role_id`, `role_name`, `role_code`, `description`, `status`, `created_time`, `updated_time`) VALUES
    (0, '普通用户', 'user',      '前台普通用户，无后台权限',         0, NOW(), NOW()),
    (1, '审核员',   'reviewer',  '可处理举报、查看禁言、AI审核',       0, NOW(), NOW()),
    (2, '管理员',   'admin',     '可管理内容/用户/举报/禁言',         0, NOW(), NOW()),
    (3, '超级管理员','super_admin','全部权限，含角色权限管理',         0, NOW(), NOW());

-- ================================================================
-- 种子数据：菜单（与前端 admin 路由对应）
-- ================================================================
INSERT IGNORE INTO `sys_menu` (`menu_id`, `parent_id`, `menu_name`, `menu_type`, `path`, `component`, `perms`, `icon`, `sort`, `status`, `created_time`, `updated_time`) VALUES
    (1,  0, '数据概览',  1, '/admin',         'DashboardView',    'admin:dashboard', 'DataBoard', 1,  0, NOW(), NOW()),
    (10, 0, '内容管理',  0, '',               NULL,               'admin:content',   'Document',  10, 0, NOW(), NOW()),
    (11, 10,'帖子管理',  1, '/admin/posts',   'PostManageView',   'admin:post:list', 'Document',  11, 0, NOW(), NOW()),
    (12, 10,'视频管理',  1, '/admin/videos',  'VideoManageView',  'admin:video:list','VideoPlay', 12, 0, NOW(), NOW()),
    (13, 10,'举报处理',  1, '/admin/reports', 'ReportManageView', 'admin:report:list','Warning',  13, 0, NOW(), NOW()),
    (20, 0, '用户与权限',0, '',               NULL,               'admin:user',      'User',      20, 0, NOW(), NOW()),
    (21, 20,'用户管理',  1, '/admin/users',   'UserManageView',   'admin:user:list', 'User',      21, 0, NOW(), NOW()),
    (22, 20,'角色权限',  1, '/admin/roles',   'RoleManageView',   'admin:role:list', 'Lock',      22, 0, NOW(), NOW()),
    (23, 20,'禁言管理',  1, '/admin/mute',    'MuteManageView',   'admin:mute:list', 'Mute',      23, 0, NOW(), NOW());

-- ================================================================
-- 种子数据：角色-菜单分配
--   超管(3)：全部菜单
--   管理员(2)：除角色权限(22)外全部
--   审核员(1)：数据概览 + 举报处理 + 禁言管理
-- ================================================================
INSERT IGNORE INTO `sys_role_menu` (`role_id`, `menu_id`) VALUES
    (3, 1),(3, 10),(3, 11),(3, 12),(3, 13),(3, 20),(3, 21),(3, 22),(3, 23),
    (2, 1),(2, 10),(2, 11),(2, 12),(2, 13),(2, 20),(2, 21),(2, 23),
    (1, 1),(1, 13),(1, 23);
