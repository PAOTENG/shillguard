package com.shillguard.auth.service;

/**
 * 通知发送服务：短信验证码 / 邮件验证码。
 * 凭证在 application.yml 中配置（占位 * 需替换为真实值）。
 */
public interface NotificationService {

    /** 发送短信验证码 */
    void sendSmsCode(String phone, String code);

    /** 发送邮件验证码 */
    void sendEmailCode(String email, String code);
}
