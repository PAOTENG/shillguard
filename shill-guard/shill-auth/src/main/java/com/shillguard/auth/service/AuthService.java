package com.shillguard.auth.service;

import com.shillguard.auth.dto.AutoLoginDTO;
import com.shillguard.auth.dto.LoginDTO;
import com.shillguard.auth.dto.RegisterDTO;
import com.shillguard.auth.vo.LoginVO;

public interface AuthService {

    LoginVO login(LoginDTO dto, String clientIp);

    /** 自动登录：密码 + 验证码校验通过后发放长有效期 token */
    LoginVO autoLogin(AutoLoginDTO dto, String clientIp);

    /** 发送登录验证码（仅手机/邮箱） */
    void sendCode(String identifier);

    void register(RegisterDTO dto, String clientIp);

    void logout(Long userId);
}
