package com.shillguard.user.vo;

import lombok.Data;

/** 修改个人信息请求：所有字段可选，传哪个改哪个 */
@Data
public class UpdateProfileDTO {
    private String nickname;
    private String avatarUrl;
    private String phone;
    private String email;
}
