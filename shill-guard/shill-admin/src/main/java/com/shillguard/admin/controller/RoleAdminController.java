package com.shillguard.admin.controller;

import com.shillguard.admin.service.AdminService;
import com.shillguard.common.entity.SysMenu;
import com.shillguard.common.entity.SysRole;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.Result;
import com.shillguard.common.result.ResultCode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 角色权限管理接口（RBAC）。
 *
 * <p>提供角色 CRUD、菜单列表、角色-菜单分配查询与更新。
 * 角色ID 与 sys_user.role 对应：0=普通 1=审核员 2=管理员 3=超管。
 */
@Tag(name = "后台-角色权限(RBAC)")
@RestController
@RequestMapping("/api/admin/roles")
@RequiredArgsConstructor
public class RoleAdminController {

    private final AdminService adminService;

    @Operation(summary = "角色列表")
    @GetMapping
    public Result<List<SysRole>> listRoles(@RequestHeader("X-User-Role") Integer curRole) {
        if (curRole < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        return Result.success(adminService.listRoles());
    }

    @Operation(summary = "新增角色")
    @PostMapping
    public Result<Void> create(@RequestBody SysRole role,
                               @RequestHeader("X-User-Role") Integer curRole) {
        if (curRole < 3) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        adminService.createRole(role);
        return Result.success();
    }

    @Operation(summary = "更新角色")
    @PutMapping
    public Result<Void> update(@RequestBody SysRole role,
                               @RequestHeader("X-User-Role") Integer curRole) {
        if (curRole < 3) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        adminService.updateRole(role);
        return Result.success();
    }

    @Operation(summary = "删除角色（预置角色0-3不可删）")
    @DeleteMapping("/{roleId}")
    public Result<Void> delete(@PathVariable("roleId") Long roleId,
                               @RequestHeader("X-User-Role") Integer curRole) {
        if (curRole < 3) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        adminService.deleteRole(roleId);
        return Result.success();
    }

    @Operation(summary = "全部菜单列表（构建菜单树用）")
    @GetMapping("/menus")
    public Result<List<SysMenu>> listAllMenus(@RequestHeader("X-User-Role") Integer curRole) {
        if (curRole < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        return Result.success(adminService.listAllMenus());
    }

    @Operation(summary = "查询某角色已分配的菜单ID")
    @GetMapping("/{roleId}/menus")
    public Result<List<Long>> roleMenus(@PathVariable("roleId") Long roleId,
                                        @RequestHeader("X-User-Role") Integer curRole) {
        if (curRole < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        return Result.success(adminService.getMenuIdsByRole(roleId));
    }

    @Operation(summary = "为角色分配菜单（全量覆盖）")
    @PutMapping("/{roleId}/menus")
    public Result<Void> assignMenus(@PathVariable("roleId") Long roleId,
                                    @RequestBody List<Long> menuIds,
                                    @RequestHeader("X-User-Role") Integer curRole) {
        if (curRole < 3) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        adminService.assignMenusToRole(roleId, menuIds);
        return Result.success();
    }
}
