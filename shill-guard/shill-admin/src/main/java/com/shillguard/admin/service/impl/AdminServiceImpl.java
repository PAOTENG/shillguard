package com.shillguard.admin.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.admin.mapper.*;
import com.shillguard.admin.service.AdminService;
import com.shillguard.common.entity.*;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.ResultCode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class AdminServiceImpl implements AdminService {

    private final AdminPostMapper postMapper;
    private final AdminCommentMapper commentMapper;
    private final AdminSysUserMapper userMapper;
    private final SysRoleMapper roleMapper;
    private final SysMenuMapper menuMapper;
    private final SysRoleMenuMapper roleMenuMapper;
    private final PasswordEncoder passwordEncoder;

    @Value("${admin.default-reset-password:123456}")
    private String defaultResetPassword;

    // ==================== 帖子 / 视频 ====================

    @Override
    public IPage<ContentPost> pagePosts(int pageNum, int pageSize, Integer status, Integer postType, String keyword) {
        LambdaQueryWrapper<ContentPost> wrapper = new LambdaQueryWrapper<ContentPost>()
                .eq(status != null, ContentPost::getStatus, status)
                .eq(postType != null, ContentPost::getPostType, postType)
                // 管理后台不强制 status=0，可查看含已删除/审核中的全量内容
                .and(StringUtils.hasText(keyword), w -> w
                        .like(ContentPost::getTitle, keyword)
                        .or().like(ContentPost::getContent, keyword)
                        .or().like(ContentPost::getTopicTag, keyword))
                .orderByDesc(ContentPost::getCreatedTime);
        return postMapper.selectPage(new Page<>(pageNum, pageSize), wrapper);
    }

    @Override
    public void setPostStatus(Long postId, int status) {
        ContentPost post = postMapper.selectById(postId);
        if (post == null) {
            throw new BizException(ResultCode.POST_NOT_FOUND);
        }
        ContentPost update = new ContentPost();
        update.setPostId(postId);
        update.setStatus(status);
        postMapper.updateById(update);
        log.info("后台设置帖子状态: postId={}, status={}", postId, status);
    }

    // ==================== 用户 ====================

    @Override
    public IPage<SysUser> pageUsers(int pageNum, int pageSize, String keyword, Integer role, Integer status) {
        LambdaQueryWrapper<SysUser> wrapper = new LambdaQueryWrapper<SysUser>()
                .eq(role != null, SysUser::getRole, role)
                .eq(status != null, SysUser::getStatus, status)
                .and(StringUtils.hasText(keyword), w -> w
                        .like(SysUser::getUsername, keyword)
                        .or().like(SysUser::getNickname, keyword)
                        .or().like(SysUser::getPhone, keyword))
                .orderByDesc(SysUser::getCreatedTime);
        IPage<SysUser> page = userMapper.selectPage(new Page<>(pageNum, pageSize), wrapper);
        // 脱敏：清空密码
        if (page.getRecords() != null) {
            page.getRecords().forEach(u -> u.setPassword(null));
        }
        return page;
    }

    @Override
    public void updateUserRole(Long userId, int role) {
        SysUser user = userMapper.selectById(userId);
        if (user == null) {
            throw new BizException(ResultCode.USER_NOT_FOUND);
        }
        if (role < 0 || role > 3) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "角色取值范围 0-3");
        }
        userMapper.updateRole(userId, role);
        log.info("后台修改用户角色: userId={}, role={}", userId, role);
    }

    @Override
    @Transactional
    public void updateUserStatus(Long userId, int status) {
        SysUser user = userMapper.selectById(userId);
        if (user == null) {
            throw new BizException(ResultCode.USER_NOT_FOUND);
        }
        if (status < 0 || status > 2) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "状态取值范围 0-2");
        }
        userMapper.updateStatus(userId, status);
        // 新规则：禁言(1)/封号(2)时，逻辑隐藏该用户全部帖子与评论（status 0→1）。
        // 解封(status=0)时【不恢复】——禁言/封禁到期后其历史帖子和评论仍保持隐藏。
        if (status != 0) {
            int c = commentMapper.update(null,
                    new LambdaUpdateWrapper<ContentComment>()
                            .eq(ContentComment::getUserId, userId)
                            .eq(ContentComment::getStatus, 0)
                            .set(ContentComment::getStatus, 1));
            int p = postMapper.update(null,
                    new LambdaUpdateWrapper<ContentPost>()
                            .eq(ContentPost::getUserId, userId)
                            .eq(ContentPost::getStatus, 0)
                            .set(ContentPost::getStatus, 1));
            log.info("后台修改用户状态: userId={}, status={}, 逻辑隐藏其全部评论{}条、帖子{}条", userId, status, c, p);
        } else {
            log.info("后台修改用户状态: userId={}, status=0(解封)，历史帖子/评论保持隐藏不恢复", userId);
        }
    }

    @Override
    public int resetPassword(Long userId) {
        SysUser user = userMapper.selectById(userId);
        if (user == null) {
            throw new BizException(ResultCode.USER_NOT_FOUND);
        }
        String encoded = passwordEncoder.encode(defaultResetPassword);
        int rows = userMapper.updatePassword(userId, encoded);
        log.info("后台重置用户密码: userId={}, rows={}", userId, rows);
        return rows;
    }

    // ==================== 角色 / 菜单 (RBAC) ====================

    @Override
    public List<SysRole> listRoles() {
        return roleMapper.selectList(new LambdaQueryWrapper<SysRole>().orderByAsc(SysRole::getRoleId));
    }

    @Override
    public void createRole(SysRole role) {
        if (role.getRoleName() == null || role.getRoleName().isBlank()
                || role.getRoleCode() == null || role.getRoleCode().isBlank()) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "角色名称和编码不能为空");
        }
        // sys_role.role_id 无 AUTO_INCREMENT（需与 sys_user.role 精确对应，预置 0-3 手动分配），
        // 新增角色取 max(role_id)+1，从 4 开始。
        SysRole max = roleMapper.selectOne(new LambdaQueryWrapper<SysRole>()
                .orderByDesc(SysRole::getRoleId).last("LIMIT 1"));
        long nextId = (max == null || max.getRoleId() == null) ? 0L : max.getRoleId() + 1L;
        role.setRoleId(nextId);
        role.setStatus(0);
        roleMapper.insert(role);
        log.info("新增角色: roleId={}, code={}", role.getRoleId(), role.getRoleCode());
    }

    @Override
    public void updateRole(SysRole role) {
        if (role.getRoleId() == null) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "角色ID不能为空");
        }
        // 不允许通过更新修改 role_code（避免破坏与 sys_user.role 的映射稳定性）
        role.setRoleCode(null);
        roleMapper.updateById(role);
        log.info("更新角色: roleId={}", role.getRoleId());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteRole(Long roleId) {
        if (roleId != null && roleId >= 0 && roleId <= 3) {
            throw new BizException(ResultCode.FAIL.getCode(), "预置角色(0-3)不允许删除");
        }
        SysRole role = roleMapper.selectById(roleId);
        if (role == null) {
            throw new BizException(ResultCode.NOT_FOUND.getCode(), "角色不存在");
        }
        // 先清理角色-菜单关联，再删角色
        roleMenuMapper.delete(new LambdaQueryWrapper<SysRoleMenu>()
                .eq(SysRoleMenu::getRoleId, roleId));
        roleMapper.deleteById(roleId);
        log.info("删除角色: roleId={}", roleId);
    }

    @Override
    public List<SysMenu> listAllMenus() {
        return menuMapper.selectList(new LambdaQueryWrapper<SysMenu>()
                .eq(SysMenu::getStatus, 0)
                .orderByAsc(SysMenu::getSort)
                .orderByAsc(SysMenu::getMenuId));
    }

    @Override
    public List<Long> getMenuIdsByRole(Long roleId) {
        return roleMenuMapper.selectMenuIdsByRoleId(roleId);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void assignMenusToRole(Long roleId, List<Long> menuIds) {
        SysRole role = roleMapper.selectById(roleId);
        if (role == null) {
            throw new BizException(ResultCode.NOT_FOUND.getCode(), "角色不存在");
        }
        // 全量覆盖：先删后插
        roleMenuMapper.delete(new LambdaQueryWrapper<SysRoleMenu>()
                .eq(SysRoleMenu::getRoleId, roleId));
        if (menuIds != null && !menuIds.isEmpty()) {
            for (Long menuId : menuIds) {
                SysRoleMenu rm = new SysRoleMenu(roleId, menuId);
                roleMenuMapper.insert(rm);
            }
        }
        log.info("为角色分配菜单: roleId={}, menuCount={}", roleId, menuIds == null ? 0 : menuIds.size());
    }
}
