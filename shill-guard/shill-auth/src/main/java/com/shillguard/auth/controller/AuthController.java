package com.shillguard.auth.controller;

import com.shillguard.auth.dto.AutoLoginDTO;
import com.shillguard.auth.dto.LoginDTO;
import com.shillguard.auth.dto.RegisterDTO;
import com.shillguard.auth.dto.SendCodeDTO;
import com.shillguard.auth.service.AuthService;
import com.shillguard.auth.vo.LoginVO;
import com.shillguard.common.result.Result;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@Tag(name = "认证接口", description = "登录、注册、退出、验证码")
@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @Operation(summary = "用户登录（账号/手机号/邮箱 + 密码）")
    @PostMapping("/login")
    public Result<LoginVO> login(@Valid @RequestBody LoginDTO dto, HttpServletRequest request) {
        return Result.success(authService.login(dto, request.getRemoteAddr()));
    }

    @Operation(summary = "自动登录（账号/手机/邮箱 + 密码 + 验证码，长有效期）")
    @PostMapping("/auto-login")
    public Result<LoginVO> autoLogin(@Valid @RequestBody AutoLoginDTO dto, HttpServletRequest request) {
        return Result.success(authService.autoLogin(dto, request.getRemoteAddr()));
    }

    @Operation(summary = "发送登录验证码（仅手机号/邮箱）")
    @PostMapping("/send-code")
    public Result<Void> sendCode(@Valid @RequestBody SendCodeDTO dto) {
        authService.sendCode(dto.getIdentifier());
        return Result.success();
    }

    @Operation(summary = "用户注册")
    @PostMapping("/register")
    public Result<Void> register(@Valid @RequestBody RegisterDTO dto, HttpServletRequest request) {
        authService.register(dto, request.getRemoteAddr());
        return Result.success();
    }

    @Operation(summary = "退出登录")
    @PostMapping("/logout")
    public Result<Void> logout(@RequestHeader("X-User-Id") Long userId) {
        authService.logout(userId);
        return Result.success();
    }
}
