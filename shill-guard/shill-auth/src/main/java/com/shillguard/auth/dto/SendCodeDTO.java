package com.shillguard.auth.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/** 发送验证码请求：identifier 为手机号或邮箱 */
@Data
public class SendCodeDTO {
    @NotBlank(message = "请输入手机号/邮箱")
    private String identifier;
}
