package com.shillguard.common.result;

import lombok.Getter;

@Getter
public enum ResultCode {

    SUCCESS(200, "操作成功"),
    FAIL(400, "操作失败"),
    UNAUTHORIZED(401, "未登录或Token已过期"),
    FORBIDDEN(403, "无权限访问"),
    NOT_FOUND(404, "资源不存在"),
    PARAM_ERROR(422, "参数校验失败"),
    SERVER_ERROR(500, "服务器内部错误"),

    // 用户相关
    USER_NOT_FOUND(1001, "用户不存在"),
    USER_ALREADY_EXISTS(1002, "用户名已存在"),
    PASSWORD_ERROR(1003, "密码错误"),
    USER_MUTED(1004, "账号已被禁言"),
    USER_DISABLED(1005, "账号已被禁用"),

    // 内容相关
    POST_NOT_FOUND(2001, "帖子不存在"),
    COMMENT_NOT_FOUND(2002, "评论不存在"),
    ALREADY_LIKED(2003, "已经点赞过了"),
    ALREADY_FOLLOWED(2004, "已经关注过了"),

    // 文件相关
    FILE_UPLOAD_FAIL(3001, "文件上传失败"),
    FILE_TYPE_NOT_ALLOWED(3002, "不支持的文件类型"),
    FILE_TOO_LARGE(3003, "文件大小超出限制"),

    // Token相关
    TOKEN_INVALID(4001, "Token无效"),
    TOKEN_EXPIRED(4002, "Token已过期"),

    // 聊天相关
    CHAT_NOT_ALLOWED(5001, "对方未回复前只能发送一条消息，请等待对方回复"),
    CHAT_SELF(5002, "不能给自己发消息"),
    CHAT_NOT_FOLLOWING(5003, "已取消关注，请重新关注后才能发消息"),

    // 验证码相关
    CODE_INVALID(6001, "验证码错误或已过期"),
    CODE_RATE_LIMIT(6002, "验证码发送过于频繁，请稍后再试"),
    IDENTIFIER_NOT_SUPPORT(6003, "账号暂不支持验证码登录，请使用手机号或邮箱"),
    CODE_SEND_FAIL(6004, "验证码发送失败，请稍后再试");

    private final int code;
    private final String message;

    ResultCode(int code, String message) {
        this.code = code;
        this.message = message;
    }
}
