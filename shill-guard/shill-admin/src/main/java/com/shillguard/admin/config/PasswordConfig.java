package com.shillguard.admin.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

/**
 * 密码编码器配置：仅用于"重置密码"功能，将明文 "123456" 编码为 BCrypt 写入 sys_user。
 * 与 shill-auth 登录时使用的 BCrypt 算法一致，无需引入完整 Spring Security 过滤链。
 */
@Configuration
public class PasswordConfig {
    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
