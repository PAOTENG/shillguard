package com.shillguard.common.utils;

import io.jsonwebtoken.*;
import io.jsonwebtoken.security.Keys;
import lombok.extern.slf4j.Slf4j;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.Map;

@Slf4j
public class JwtUtils {

    private static final String SECRET = "shillguard-jwt-secret-key-must-be-at-least-256bits-long!!";
    private static final long EXPIRATION_MS = 7 * 24 * 60 * 60 * 1000L; // 7天

    private static final SecretKey KEY = Keys.hmacShaKeyFor(SECRET.getBytes(StandardCharsets.UTF_8));

    public static String generateToken(Long userId, String username, Integer role) {
        return generateToken(userId, username, role, EXPIRATION_MS);
    }

    /** 指定过期时长（毫秒），用于自动登录等长有效期场景 */
    public static String generateToken(Long userId, String username, Integer role, long expirationMs) {
        return Jwts.builder()
                .subject(String.valueOf(userId))
                .claim("username", username)
                .claim("role", role)
                .issuedAt(new Date())
                .expiration(new Date(System.currentTimeMillis() + expirationMs))
                .signWith(KEY)
                .compact();
    }

    public static Claims parseToken(String token) {
        return Jwts.parser()
                .verifyWith(KEY)
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }

    public static Long getUserId(String token) {
        return Long.parseLong(parseToken(token).getSubject());
    }

    public static String getUsername(String token) {
        return parseToken(token).get("username", String.class);
    }

    public static Integer getRole(String token) {
        return parseToken(token).get("role", Integer.class);
    }

    public static boolean isTokenValid(String token) {
        try {
            parseToken(token);
            return true;
        } catch (ExpiredJwtException e) {
            log.warn("Token已过期");
            return false;
        } catch (Exception e) {
            log.warn("Token无效: {}", e.getMessage());
            return false;
        }
    }
}
