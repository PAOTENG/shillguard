package com.shillguard.auth.service;

import com.shillguard.auth.service.impl.NotificationServiceImpl;
import com.shillguard.auth.util.IdentifierUtils;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.ResultCode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadLocalRandom;

/**
 * 登录验证码服务：
 * - sendAndStore(identifier): 识别手机/邮箱，生成 6 位验证码，存 Redis（5 分钟有效），
 *   并通过短信/邮件发送。账号(用户名)不支持验证码。60 秒内不可重复发送。
 * - verify(identifier, code): 校验并删除。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class VerificationCodeService {

    private final StringRedisTemplate redisTemplate;
    private final NotificationServiceImpl notifier;

    private static final String CODE_KEY = "code:login:";
    private static final String RATE_KEY = "rate:login:";
    private static final long CODE_TTL_SEC = 300;       // 5 分钟
    private static final long RATE_TTL_SEC = 60;        // 60 秒间隔

    public void sendAndStore(String identifier) {
        if (identifier == null || identifier.isBlank()) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "请输入手机号/邮箱/账号");
        }
        String id = identifier.trim();
        IdentifierUtils.Type type = IdentifierUtils.detect(id);

        if (type == IdentifierUtils.Type.USERNAME) {
            // 账号没有可发送验证码的渠道
            throw new BizException(ResultCode.IDENTIFIER_NOT_SUPPORT);
        }
        // 格式校验
        if (type == IdentifierUtils.Type.PHONE && !IdentifierUtils.isPhone(id)) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "手机号格式不正确");
        }
        if (type == IdentifierUtils.Type.EMAIL && !IdentifierUtils.isEmail(id)) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "邮箱格式不正确");
        }
        // 限频：60 秒内只允许发一次（发送失败会回滚限频，便于重试）
        Boolean rateOk = redisTemplate.opsForValue().setIfAbsent(RATE_KEY + type + ":" + id, "1", RATE_TTL_SEC, TimeUnit.SECONDS);
        if (Boolean.FALSE.equals(rateOk)) {
            throw new BizException(ResultCode.CODE_RATE_LIMIT);
        }

        String code = String.format("%06d", ThreadLocalRandom.current().nextInt(1_000_000));
        redisTemplate.opsForValue().set(CODE_KEY + type + ":" + id, code, CODE_TTL_SEC, TimeUnit.SECONDS);

        try {
            if (type == IdentifierUtils.Type.PHONE) {
                notifier.sendSmsCode(id, code);
            } else {
                notifier.sendEmailCode(id, code);
            }
            log.info("验证码已生成并发送: type={}, id={}", type, id);
        } catch (RuntimeException e) {
            // 发送失败：回滚限频，避免用户被卡 60 秒无法重试
            redisTemplate.delete(RATE_KEY + type + ":" + id);
            redisTemplate.delete(CODE_KEY + type + ":" + id);
            throw e;
        }
    }

    public void verify(String identifier, String code) {
        if (identifier == null || code == null || code.isBlank()) {
            throw new BizException(ResultCode.CODE_INVALID);
        }
        String id = identifier.trim();
        IdentifierUtils.Type type = IdentifierUtils.detect(id);
        String stored = redisTemplate.opsForValue().get(CODE_KEY + type + ":" + id);
        if (stored == null || !stored.equals(code.trim())) {
            throw new BizException(ResultCode.CODE_INVALID);
        }
        // 校验成功后删除，防止复用
        redisTemplate.delete(CODE_KEY + type + ":" + id);
    }
}
