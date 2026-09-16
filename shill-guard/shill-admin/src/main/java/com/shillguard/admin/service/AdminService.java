package com.shillguard.admin.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.entity.ContentPost;
import com.shillguard.common.entity.SysMenu;
import com.shillguard.common.entity.SysRole;
import com.shillguard.common.entity.SysUser;

import java.util.List;

/**
 * 管理后台业务接口，聚合帖子/视频、用户、角色权限(RBAC)三类管理能力。
 */
public interface AdminService {

    // ==================== 帖子 / 视频 ====================

    /**
     * 后台帖子分页（不限 status，可按状态/类型/关键词过滤）。
     *
     * @param postType 1=纯文字 2=图文 3=视频；null=全部
     * @param status   0=正常 1=已删除 2=审核中 3=审核不通过；null=全部
     */
    IPage<ContentPost> pagePosts(int pageNum, int pageSize, Integer status, Integer postType, String keyword);

    /** 设置帖子状态（逻辑删除/恢复/强制下架）。status: 0=正常 1=已删除 */
    void setPostStatus(Long postId, int status);

    // ==================== 用户 ====================

    /**
     * 后台用户分页（可按关键词/角色/状态过滤）。
     */
    IPage<SysUser> pageUsers(int pageNum, int pageSize, String keyword, Integer role, Integer status);

    /** 修改用户角色。role: 0=普通 1=审核员 2=管理员 3=超管 */
    void updateUserRole(Long userId, int role);

    /** 修改用户状态。status: 0=正常 1=禁言 2=封号 */
    void updateUserStatus(Long userId, int status);

    /** 重置密码为默认值（123456），返回受影响行数 */
    int resetPassword(Long userId);

    // ==================== 角色 / 菜单 (RBAC) ====================

    /** 全部角色列表 */
    List<SysRole> listRoles();

    /** 新增角色 */
    void createRole(SysRole role);

    /** 更新角色基本信息 */
    void updateRole(SysRole role);

    /** 删除角色（同时清理 sys_role_menu 关联）。预置角色(0-3)不允许删除 */
    void deleteRole(Long roleId);

    /** 全部菜单列表（前端自行按 parent_id 构建树） */
    List<SysMenu> listAllMenus();

    /** 查询某角色已分配的菜单ID */
    List<Long> getMenuIdsByRole(Long roleId);

    /**
     * 为角色分配菜单（全量覆盖）。
     *
     * @param roleId  角色ID
     * @param menuIds 菜单ID列表（覆盖原有分配）
     */
    void assignMenusToRole(Long roleId, List<Long> menuIds);
}
