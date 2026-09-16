package com.shillguard.admin.controller;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.admin.service.AdminService;
import com.shillguard.common.entity.SysUser;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.Result;
import com.shillguard.common.result.ResultCode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/**
 * 用户管理接口：改角色、封号/解封、重置密码。
 * 用户列表沿用 shill-user 的 /api/user/list，本服务提供更细粒度的管理操作。
 */
@Tag(name = "后台-用户管理")
@RestController
@RequestMapping("/api/admin/users")
@RequiredArgsConstructor
public class UserAdminController {

    private final AdminService adminService;

    @Operation(summary = "用户分页（管理员，可按角色/状态过滤，密码脱敏）")
    @GetMapping
    public Result<IPage<SysUser>> list(
            @RequestParam(name = "pageNum", defaultValue = "1") int pageNum,
            @RequestParam(name = "pageSize", defaultValue = "20") int pageSize,
            @RequestParam(name = "keyword", required = false) String keyword,
            @RequestParam(name = "role", required = false) Integer role,
            @RequestParam(name = "status", required = false) Integer status,
            @RequestHeader("X-User-Role") Integer curRole) {
        if (curRole < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        return Result.success(adminService.pageUsers(pageNum, pageSize, keyword, role, status));
    }

    @Operation(summary = "修改用户角色")
    @PutMapping("/{userId}/role")
    public Result<Void> updateRole(@PathVariable("userId") Long userId,
                                   @RequestParam int role,
                                   @RequestHeader("X-User-Role") Integer curRole) {
        if (curRole < 3) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        adminService.updateUserRole(userId, role);
        return Result.success();
    }

    @Operation(summary = "修改用户状态（封号/解封/禁言）")
    @PutMapping("/{userId}/status")
    public Result<Void> updateStatus(@PathVariable("userId") Long userId,
                                     @RequestParam int status,
                                     @RequestHeader("X-User-Role") Integer curRole) {
        if (curRole < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        adminService.updateUserStatus(userId, status);
        return Result.success();
    }

    @Operation(summary = "重置用户密码为默认值(123456)")
    @PutMapping("/{userId}/password/reset")
    public Result<Void> resetPassword(@PathVariable("userId") Long userId,
                                      @RequestHeader("X-User-Role") Integer curRole) {
        if (curRole < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        adminService.resetPassword(userId);
        return Result.success();
    }
}
