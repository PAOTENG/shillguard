package com.shillguard.auth.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/** 自动登录请求：账号/手机/邮箱 + 密码 + 验证码（验证码仅手机/邮箱需要） */
@Data
public class AutoLoginDTO {
    @NotBlank(message = "请输入手机号/邮箱/账号")
    private String identifier;
    @NotBlank(message = "密码不能为空")
    private String password;
    /** 手机号/邮箱收到的 6 位验证码 */
    private String code;
}
