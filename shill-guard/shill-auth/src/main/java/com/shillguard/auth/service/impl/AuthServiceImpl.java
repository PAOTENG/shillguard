package com.shillguard.auth.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shillguard.auth.dto.AutoLoginDTO;
import com.shillguard.auth.dto.LoginDTO;
import com.shillguard.auth.dto.RegisterDTO;
import com.shillguard.auth.mapper.UserMapper;
import com.shillguard.auth.service.AuthService;
import com.shillguard.auth.util.AvatarGenerator;
import com.shillguard.auth.util.IdentifierUtils;
import com.shillguard.auth.vo.LoginVO;
import com.shillguard.common.entity.SysUser;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.ResultCode;
import com.shillguard.common.utils.JwtUtils;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.minio.ListObjectsArgs;
import io.minio.Result;
import io.minio.messages.Item;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.io.ByteArrayInputStream;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
@RequiredArgsConstructor
public class AuthServiceImpl implements AuthService {

    private final UserMapper userMapper;
    private final PasswordEncoder passwordEncoder;
    private final StringRedisTemplate redisTemplate;
    private final MinioClient minioClient;
    private final com.shillguard.auth.service.VerificationCodeService verificationCodeService;

    @Value("${minio.endpoint}")
    private String minioEndpoint;

    @Value("${minio.bucket-name}")
    private String minioBucket;

    private static final String TOKEN_KEY_PREFIX = "user:token:";
    private static final long TOKEN_EXPIRE_DAYS = 7;
    private static final long AUTO_TOKEN_EXPIRE_DAYS = 30;   // 自动登录 30 天

    /** 按 手机号 / 邮箱 / 用户名 查找用户 */
    private SysUser findByIdentifier(String identifier) {
        if (identifier == null || identifier.isBlank()) return null;
        String id = identifier.trim();
        IdentifierUtils.Type type = IdentifierUtils.detect(id);
        LambdaQueryWrapper<SysUser> wrapper = new LambdaQueryWrapper<>();
        switch (type) {
            case PHONE -> wrapper.eq(SysUser::getPhone, id);
            case EMAIL -> wrapper.eq(SysUser::getEmail, id);
            default -> wrapper.eq(SysUser::getUsername, id);
        }
        return userMapper.selectOne(wrapper);
    }

    @Override
    public LoginVO login(LoginDTO dto, String clientIp) {
        SysUser user = findByIdentifier(dto.getUsername());
        if (user == null) {
            throw new BizException(ResultCode.USER_NOT_FOUND);
        }
        if (!passwordEncoder.matches(dto.getPassword(), user.getPassword())) {
            throw new BizException(ResultCode.PASSWORD_ERROR);
        }
        if (user.getStatus() == 1) {
            throw new BizException(ResultCode.USER_MUTED);
        }
        return buildLoginVO(user, clientIp, TOKEN_EXPIRE_DAYS);
    }

    @Override
    public LoginVO autoLogin(AutoLoginDTO dto, String clientIp) {
        SysUser user = findByIdentifier(dto.getIdentifier());
        if (user == null) {
            throw new BizException(ResultCode.USER_NOT_FOUND);
        }
        if (!passwordEncoder.matches(dto.getPassword(), user.getPassword())) {
            throw new BizException(ResultCode.PASSWORD_ERROR);
        }
        if (user.getStatus() == 1) {
            throw new BizException(ResultCode.USER_MUTED);
        }
        // 验证码校验（仅手机/邮箱；账号不支持自动登录验证码）
        IdentifierUtils.Type type = IdentifierUtils.detect(dto.getIdentifier());
        if (type == IdentifierUtils.Type.USERNAME) {
            throw new BizException(ResultCode.IDENTIFIER_NOT_SUPPORT);
        }
        verificationCodeService.verify(dto.getIdentifier(), dto.getCode());
        // 验证通过 → 发放长有效期 token
        return buildLoginVO(user, clientIp, AUTO_TOKEN_EXPIRE_DAYS);
    }

    @Override
    public void sendCode(String identifier) {
        verificationCodeService.sendAndStore(identifier);
    }

    /** 组装 LoginVO 并落库 token + 更新登录信息 */
    private LoginVO buildLoginVO(SysUser user, String clientIp, long expireDays) {
        String token = JwtUtils.generateToken(user.getUserId(), user.getUsername(), user.getRole(),
                expireDays * 24 * 60 * 60 * 1000L);
        redisTemplate.opsForValue().set(
                TOKEN_KEY_PREFIX + user.getUserId(),
                token,
                expireDays, TimeUnit.DAYS
        );
        SysUser update = new SysUser();
        update.setUserId(user.getUserId());
        update.setLastLoginTime(LocalDateTime.now());
        update.setLastLoginIp(clientIp);
        userMapper.updateById(update);
        log.info("用户登录成功: userId={}, username={}, expireDays={}", user.getUserId(), user.getUsername(), expireDays);
        return LoginVO.builder()
                .userId(user.getUserId())
                .username(user.getUsername())
                .nickname(user.getNickname())
                .avatarUrl(user.getAvatarUrl())
                .role(user.getRole())
                .token(token)
                .expireIn(expireDays * 24 * 3600)
                .build();
    }

    @Override
    public void register(RegisterDTO dto, String clientIp) {
        Long count = userMapper.selectCount(new LambdaQueryWrapper<SysUser>()
                .eq(SysUser::getUsername, dto.getUsername()));
        if (count > 0) {
            throw new BizException(ResultCode.USER_ALREADY_EXISTS);
        }

        SysUser user = new SysUser();
        user.setUsername(dto.getUsername());
        user.setPassword(passwordEncoder.encode(dto.getPassword()));
        user.setNickname(dto.getNickname() != null ? dto.getNickname() : dto.getUsername());
        user.setPhone(dto.getPhone());
        user.setEmail(dto.getEmail());
        user.setRole(0);
        user.setStatus(0);
        user.setRegisterIp(clientIp);

        // 注册时随机分配头像池中的一张像素风头像；池为空才回退到文字生成头像
        String avatarUrl = randomPoolAvatarUrl();
        if (avatarUrl == null) {
            avatarUrl = generateAndUploadAvatar(user.getNickname(), dto.getUsername());
        }
        user.setAvatarUrl(avatarUrl);

        userMapper.insert(user);

        log.info("新用户注册: username={}, avatar={}", dto.getUsername(), avatarUrl);
    }

    /**
     * 从 MinIO 的 avatars/pool/ 前缀中随机挑一张头像，返回可访问 URL。
     * 头像池由运维批量上传（像素风头像），注册时无需生成新图，避免首字母头像不美观。
     * 池为空或读取异常返回 null，由调用方回退到文字头像生成。
     */
    private String randomPoolAvatarUrl() {
        try {
            Iterable<Result<Item>> results = minioClient.listObjects(
                    ListObjectsArgs.builder()
                            .bucket(minioBucket)
                            .prefix("avatars/pool/")
                            .recursive(false)
                            .build());
            List<String> names = new ArrayList<>();
            for (Result<Item> r : results) {
                try {
                    Item it = r.get();
                    String name = it.objectName();
                    if (name != null && !name.endsWith("/")) names.add(name);
                } catch (Exception ignore) { }
            }
            if (names.isEmpty()) return null;
            String pick = names.get(ThreadLocalRandom.current().nextInt(names.size()));
            return minioEndpoint + "/" + minioBucket + "/" + pick;
        } catch (Exception e) {
            log.warn("读取头像池失败: {}", e.getMessage());
            return null;
        }
    }

    /**
     * 生成头像并上传到 MinIO，返回可访问的 URL。
     * 用昵称首字 + 用户名 hash 配色，生成一张圆形渐变头像。
     * 任何异常都只打日志返回 null，不影响注册主流程。
     */
    private String generateAndUploadAvatar(String nickname, String username) {
        try {
            String text = (nickname != null && !nickname.isEmpty()) ? nickname : username;
            byte[] bytes = AvatarGenerator.generate(text, username == null ? 0 : username.hashCode());
            String objectName = "avatars/" + UUID.randomUUID() + ".png";
            minioClient.putObject(PutObjectArgs.builder()
                    .bucket(minioBucket)
                    .object(objectName)
                    .stream(new ByteArrayInputStream(bytes), bytes.length, -1)
                    .contentType("image/png")
                    .build());
            String url = minioEndpoint + "/" + minioBucket + "/" + objectName;
            log.info("头像生成上传成功: {}", url);
            return url;
        } catch (Exception e) {
            log.warn("头像生成/上传失败，跳过（不阻断注册）: {}", e.getMessage());
            return null;
        }
    }

    @Override
    public void logout(Long userId) {
        redisTemplate.delete(TOKEN_KEY_PREFIX + userId);
        log.info("用户退出登录: userId={}", userId);
    }
}
