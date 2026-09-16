package com.shillguard.user.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.shillguard.common.entity.SysUser;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.Result;
import com.shillguard.common.result.ResultCode;
import com.shillguard.user.mapper.SysUserMapper;
import com.shillguard.user.service.FollowService;
import com.shillguard.user.vo.UserStatsVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.*;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

@Tag(name = "用户接口")
@RestController
@RequestMapping("/api/user")
@RequiredArgsConstructor
public class UserController {

    private final SysUserMapper userMapper;
    private final FollowService followService;

    @Operation(summary = "获取当前用户信息（脱敏：不含密码）")
    @GetMapping("/me")
    public Result<SysUser> me(@RequestHeader("X-User-Id") Long userId) {
        SysUser user = userMapper.selectById(userId);
        if (user == null) {
            throw new BizException(ResultCode.USER_NOT_FOUND);
        }
        user.setPassword(null);
        return Result.success(user);
    }

    @Operation(summary = "获取指定用户公开信息")
    @GetMapping("/{userId}")
    public Result<SysUser> profile(@PathVariable("userId") Long userId) {
        SysUser user = userMapper.selectOne(new LambdaQueryWrapper<SysUser>()
                .eq(SysUser::getUserId, userId)
                .eq(SysUser::getStatus, 0)
                .select(SysUser::getUserId, SysUser::getNickname, SysUser::getAvatarUrl, SysUser::getRole));
        if (user == null) {
            throw new BizException(ResultCode.USER_NOT_FOUND);
        }
        return Result.success(user);
    }

    @Operation(summary = "修改个人信息（昵称/头像/手机号/邮箱）")
    @PutMapping("/me")
    public Result<Void> update(@RequestHeader("X-User-Id") Long userId,
                               @RequestBody com.shillguard.user.vo.UpdateProfileDTO dto) {
        if (dto == null) {
            return Result.success();
        }
        // 手机号/邮箱格式校验（非空才校验）
        if (dto.getPhone() != null && !dto.getPhone().isBlank()
                && !dto.getPhone().matches("^1[3-9]\\d{9}$")) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "手机号格式不正确");
        }
        if (dto.getEmail() != null && !dto.getEmail().isBlank()
                && !dto.getEmail().matches("^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$")) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "邮箱格式不正确");
        }
        LambdaUpdateWrapper<SysUser> wrapper = new LambdaUpdateWrapper<SysUser>()
                .eq(SysUser::getUserId, userId)
                .set(dto.getNickname() != null, SysUser::getNickname, dto.getNickname())
                .set(dto.getAvatarUrl() != null, SysUser::getAvatarUrl, dto.getAvatarUrl())
                .set(dto.getPhone() != null, SysUser::getPhone, dto.getPhone())
                .set(dto.getEmail() != null, SysUser::getEmail, dto.getEmail());
        userMapper.update(null, wrapper);
        return Result.success();
    }

    @Operation(summary = "管理员禁言用户")
    @PutMapping("/{userId}/mute")
    public Result<Void> mute(@PathVariable("userId") Long userId,
                             @RequestHeader("X-User-Role") Integer role) {
        if (role < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        LambdaUpdateWrapper<SysUser> wrapper = new LambdaUpdateWrapper<SysUser>()
                .eq(SysUser::getUserId, userId)
                .set(SysUser::getStatus, 1);
        userMapper.update(null, wrapper);
        return Result.success();
    }

    /**
     * 管理员解除用户禁言（将 status 恢复为 0=正常）
     * 需要 role >= 2
     */
    @Operation(summary = "管理员解除禁言")
    @PutMapping("/{userId}/unmute")
    public Result<Void> unmute(@PathVariable("userId") Long userId,
                               @RequestHeader("X-User-Role") Integer role) {
        if (role < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        LambdaUpdateWrapper<SysUser> wrapper = new LambdaUpdateWrapper<SysUser>()
                .eq(SysUser::getUserId, userId)
                .set(SysUser::getStatus, 0);
        userMapper.update(null, wrapper);
        return Result.success();
    }

    /**
     * 管理员分页查询用户列表
     * 支持按用户名或昵称模糊搜索
     * 需要 role >= 2
     *
     * @param pageNum  页码（从1开始）
     * @param pageSize 每页数量
     * @param keyword  搜索关键词（可选，模糊匹配用户名/昵称）
     */
    /**
     * 用户搜索（公开接口）：按用户名或昵称模糊搜索，返回公开字段。
     * 不按 status 过滤——被禁言/封号用户仍可被搜到，前端根据 status 标注"该用户被禁言"。
     * 最多 20 条。
     */
    @Operation(summary = "搜索用户（公开）")
    @GetMapping("/search")
    public Result<List<SysUser>> search(@RequestParam(name = "keyword") String keyword) {
        if (!StringUtils.hasText(keyword)) {
            return Result.success(Collections.emptyList());
        }
        LambdaQueryWrapper<SysUser> wrapper = new LambdaQueryWrapper<SysUser>()
                .and(w -> w.like(SysUser::getUsername, keyword)
                        .or().like(SysUser::getNickname, keyword))
                // 返回公开字段 + status（前端据此标注禁言状态）
                .select(SysUser::getUserId, SysUser::getUsername, SysUser::getNickname,
                        SysUser::getAvatarUrl, SysUser::getRole, SysUser::getStatus)
                .orderByDesc(SysUser::getCreatedTime)
                .last("LIMIT 20");
        List<SysUser> list = userMapper.selectList(wrapper);
        // 脱敏
        list.forEach(u -> { u.setPassword(null); u.setPhone(null); u.setEmail(null); });
        return Result.success(list);
    }

    // ==================== 关注相关 ====================

    @Operation(summary = "关注某用户")
    @PostMapping("/follow/{targetId}")
    public Result<Void> follow(@PathVariable("targetId") Long targetId,
                               @RequestHeader("X-User-Id") Long userId) {
        followService.follow(userId, targetId);
        return Result.success();
    }

    @Operation(summary = "取消关注")
    @DeleteMapping("/follow/{targetId}")
    public Result<Void> unfollow(@PathVariable("targetId") Long targetId,
                                 @RequestHeader("X-User-Id") Long userId) {
        followService.unfollow(userId, targetId);
        return Result.success();
    }

    @Operation(summary = "我的关注列表（公开字段）")
    @GetMapping("/followings")
    public Result<List<SysUser>> myFollowings(@RequestHeader("X-User-Id") Long userId) {
        return Result.success(followService.myFollowings(userId));
    }

    @Operation(summary = "我的粉丝列表（公开字段）")
    @GetMapping("/followers")
    public Result<List<SysUser>> myFollowers(@RequestHeader("X-User-Id") Long userId) {
        return Result.success(followService.myFollowers(userId));
    }

    @Operation(summary = "指定用户公开主页信息")
    @GetMapping("/profile/{userId}")
    public Result<SysUser> publicProfile(@PathVariable("userId") Long userId) {
        // 不按 status 过滤：被禁言/封号用户的主页仍可访问，前端据 status 标注禁言状态
        SysUser user = userMapper.selectOne(new LambdaQueryWrapper<SysUser>()
                .eq(SysUser::getUserId, userId)
                .select(SysUser::getUserId, SysUser::getUsername, SysUser::getNickname,
                        SysUser::getAvatarUrl, SysUser::getRole, SysUser::getStatus,
                        SysUser::getWarningLevel));
        if (user == null) {
            throw new BizException(ResultCode.USER_NOT_FOUND);
        }
        return Result.success(user);
    }

    @Operation(summary = "指定用户统计数据（笔记/获赞/被收藏/被关注，含是否已关注）")
    @GetMapping("/stats/{userId}")
    public Result<UserStatsVO> stats(@PathVariable("userId") Long userId,
                                     @RequestHeader(value = "X-User-Id", required = false) Long currentUserId) {
        return Result.success(followService.stats(userId, currentUserId));
    }

    /**
     * 批量获取用户昵称（管理端列表展示用）。
     * 入参 ids 为逗号分隔的用户ID，返回这些用户的 userId/nickname/username/avatarUrl/status。
     * 不按 status 过滤——管理端需要看到被禁言用户的昵称。
     * 需登录（网关已校验 Token）。
     */
    @Operation(summary = "批量获取用户昵称（管理端用）")
    @GetMapping("/names")
    public Result<List<SysUser>> names(@RequestParam(name = "ids") String ids) {
        if (ids == null || ids.isBlank()) {
            return Result.success(Collections.emptyList());
        }
        List<Long> idList = Arrays.stream(ids.split(","))
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .map(Long::valueOf)
                .distinct()
                .collect(Collectors.toList());
        if (idList.isEmpty()) {
            return Result.success(Collections.emptyList());
        }
        List<SysUser> users = userMapper.selectBatchIds(idList);
        // 只返回展示所需字段，脱敏
        users.forEach(u -> {
            u.setPassword(null);
            u.setPhone(null);
            u.setEmail(null);
        });
        return Result.success(users);
    }

    @Operation(summary = "管理员查询用户列表（分页）")
    @GetMapping("/list")
    public Result<IPage<SysUser>> list(
            @RequestParam(name = "pageNum", defaultValue = "1") int pageNum,
            @RequestParam(name = "pageSize", defaultValue = "20") int pageSize,
            @RequestParam(name = "keyword", required = false) String keyword,
            @RequestHeader("X-User-Role") Integer role) {
        if (role < 2) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        LambdaQueryWrapper<SysUser> wrapper = new LambdaQueryWrapper<SysUser>()
                // 如果有关键词，就同时模糊匹配用户名和昵称
                .and(StringUtils.hasText(keyword), w -> w
                        .like(SysUser::getUsername, keyword)
                        .or()
                        .like(SysUser::getNickname, keyword))
                .orderByDesc(SysUser::getCreatedTime);
        IPage<SysUser> page = userMapper.selectPage(new Page<>(pageNum, pageSize), wrapper);
        return Result.success(page);
    }
}
