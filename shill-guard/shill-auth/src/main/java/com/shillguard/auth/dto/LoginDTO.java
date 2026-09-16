package com.shillguard.auth.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

@Data
public class LoginDTO {

    @NotBlank(message = "请输入手机号/邮箱/账号")
    private String username;

    @NotBlank(message = "密码不能为空")
    private String password;
}
