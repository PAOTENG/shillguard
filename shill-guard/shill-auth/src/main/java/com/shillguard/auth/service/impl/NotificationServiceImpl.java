package com.shillguard.auth.service.impl;

import com.aliyun.dypnsapi20170525.Client;
import com.aliyun.dypnsapi20170525.models.SendSmsVerifyCodeRequest;
import com.aliyun.dypnsapi20170525.models.SendSmsVerifyCodeResponse;
import com.aliyun.teaopenapi.models.Config;
import com.shillguard.auth.service.NotificationService;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.ResultCode;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * 短信/邮件验证码发送实现。
 *
 * 【短信通道：阿里云 PNVS 号码认证服务】
 *   个人实名认证即可，免企业资质、免签名申请、免模板审核。
 *   在「号码认证服务控制台 → 短信认证」开通后，使用平台预置的签名和模板。
 *
 * 配置项（application.yml，带 * 的是占位符，需替换为你的真实凭证）：
 *   aliyun.sms.access-key-id     : *  （阿里云 RAM AccessKey Id）
 *   aliyun.sms.access-key-secret : *  （阿里云 RAM AccessKey Secret）
 *   aliyun.sms.sign-name         : *  （控制台预置的系统签名名称）
 *   aliyun.sms.template-code     : *  （控制台预置的验证码模板 Code）
 *   spring.mail.username         : *  （发件邮箱）
 *   spring.mail.password         : *  （邮箱授权码，非登录密码）
 *
 * 注意：PNVS 预置验证码模板的验证码变量名约定为 ${code}，这里以 {"code":"xxxxxx","min":"5"} 下发。
 *      若你选用的模板变量名不同，请调整下方 templateParam。
 */
@Slf4j
@Service
public class NotificationServiceImpl implements NotificationService {

    @Value("${aliyun.sms.access-key-id:}")
    private String accessKeyId;

    @Value("${aliyun.sms.access-key-secret:}")
    private String accessKeySecret;

    @Value("${aliyun.sms.sign-name:}")
    private String signName;

    @Value("${aliyun.sms.template-code:}")
    private String templateCode;

    @Value("${spring.mail.username:}")
    private String mailFrom;

    private final JavaMailSender mailSender;

    /** 邮件发送专用线程池：SMTP 投递慢，异步发送避免阻塞登录接口 */
    private final ExecutorService emailExecutor = Executors.newFixedThreadPool(
            2, r -> {
                Thread t = new Thread(r, "email-sender");
                t.setDaemon(true);
                return t;
            });

    /** PNVS 客户端，凭证未配置时为 null（发送时给出明确提示） */
    private Client pnvsClient;

    @PostConstruct
    public void initSmsClient() {
        if (isPlaceholder(accessKeyId) || isPlaceholder(accessKeySecret)) {
            log.warn("阿里云 PNVS 短信凭证未配置（仍为占位符），手机验证码将无法发送。请在 application.yml 替换。");
            return;
        }
        try {
            Config config = new Config()
                    .setAccessKeyId(accessKeyId)
                    .setAccessKeySecret(accessKeySecret)
                    .setEndpoint("dypnsapi.aliyuncs.com");
            this.pnvsClient = new Client(config);
            log.info("阿里云 PNVS 短信客户端初始化成功");
        } catch (Exception e) {
            log.error("阿里云 PNVS 客户端初始化失败: {}", e.getMessage());
        }
    }

    public NotificationServiceImpl(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Override
    public void sendSmsCode(String phone, String code) {
        if (pnvsClient == null) {
            throw new BizException(ResultCode.CODE_SEND_FAIL.getCode(),
                    "短信服务未配置，请在后端 application.yml 填写阿里云 PNVS 凭证（access-key/sign-name/template-code）");
        }
        if (isPlaceholder(signName) || isPlaceholder(templateCode)) {
            throw new BizException(ResultCode.CODE_SEND_FAIL.getCode(),
                    "短信签名/模板未配置，请在号码认证服务控制台获取预置签名名与模板 Code 并填入 application.yml");
        }
        try {
            // 预置模板变量：code=验证码, min=有效分钟数。验证码由我们自己生成并在 Redis 校验。
            String templateParam = "{\"code\":\"" + code + "\",\"min\":\"5\"}";
            SendSmsVerifyCodeRequest req = new SendSmsVerifyCodeRequest()
                    .setPhoneNumber(phone)
                    .setSignName(signName)
                    .setTemplateCode(templateCode)
                    .setTemplateParam(templateParam);
            SendSmsVerifyCodeResponse resp = pnvsClient.sendSmsVerifyCode(req);
            String retCode = resp.getBody() == null ? "" : resp.getBody().getCode();
            if (!"OK".equals(retCode)) {
                String msg = resp.getBody() == null ? "" : resp.getBody().getMessage();
                log.error("PNVS 短信发送失败: phone={}, code={}, msg={}", phone, retCode, msg);
                throw new BizException(ResultCode.CODE_SEND_FAIL.getCode(), "短信发送失败：" + msg);
            }
            log.info("PNVS 短信验证码已发送: phone={}", phone);
        } catch (BizException e) {
            throw e;
        } catch (Exception e) {
            log.error("PNVS 短信发送异常: phone={}, err={}", phone, e.getMessage());
            throw new BizException(ResultCode.CODE_SEND_FAIL);
        }
    }

    @Override
    public void sendEmailCode(String email, String code) {
        if (isPlaceholder(mailFrom)) {
            throw new BizException(ResultCode.CODE_SEND_FAIL.getCode(),
                    "邮件服务未配置，请在后端 application.yml 填写 spring.mail 账号信息");
        }
        // 异步发送：SMTP 投递慢（尤其 SSL 握手），丢到线程池立刻返回，前端零等待
        emailExecutor.submit(() -> {
            try {
                SimpleMailMessage msg = new SimpleMailMessage();
                msg.setFrom(mailFrom);
                msg.setTo(email);
                msg.setSubject("【ShillGuard】登录验证码");
                msg.setText("你正在设置自动登录，验证码为：" + code + "，5 分钟内有效。如非本人操作请忽略。");
                mailSender.send(msg);
                log.info("邮件验证码已发送: email={}", email);
            } catch (Exception e) {
                // 异步发送失败不影响接口返回；验证码已在 Redis，用户 60s 后可重试
                log.error("邮件异步发送失败: email={}, err={}", email, e.getMessage());
            }
        });
    }

    @PreDestroy
    public void shutdownExecutor() {
        emailExecutor.shutdown();
        try {
            if (!emailExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                emailExecutor.shutdownNow();
            }
        } catch (InterruptedException ignored) {
            emailExecutor.shutdownNow();
        }
    }

    /** 判断配置是否仍为占位符 */
    private boolean isPlaceholder(String v) {
        return v == null || v.isBlank() || "*".equals(v.trim());
    }
}
