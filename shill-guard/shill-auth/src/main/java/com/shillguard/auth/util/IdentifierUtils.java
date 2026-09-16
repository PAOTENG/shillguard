package com.shillguard.auth.util;

import java.util.regex.Pattern;

/**
 * 登录标识识别工具：判断用户输入的是手机号、邮箱还是账号(用户名)。
 * 用于"手机号/邮箱/账号 三选一登录"与验证码发送。
 */
public final class IdentifierUtils {

    /** 中国大陆手机号：1开头，第二位3-9，共11位 */
    private static final Pattern PHONE = Pattern.compile("^1[3-9]\\d{9}$");
    /** 常见邮箱格式 */
    private static final Pattern EMAIL = Pattern.compile("^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$");

    public enum Type { PHONE, EMAIL, USERNAME }

    private IdentifierUtils() {}

    /** 识别类型：先手机号、再邮箱、否则视为账号 */
    public static Type detect(String identifier) {
        if (identifier == null) return Type.USERNAME;
        String s = identifier.trim();
        if (PHONE.matcher(s).matches()) return Type.PHONE;
        if (EMAIL.matcher(s).matches()) return Type.EMAIL;
        return Type.USERNAME;
    }

    public static boolean isPhone(String s) { return s != null && PHONE.matcher(s).matches(); }
    public static boolean isEmail(String s) { return s != null && EMAIL.matcher(s).matches(); }
}
