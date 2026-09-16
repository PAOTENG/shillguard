package com.shillguard.gateway.filter;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shillguard.common.result.Result;
import com.shillguard.common.result.ResultCode;
import com.shillguard.common.utils.JwtUtils;
import io.jsonwebtoken.Claims;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.util.AntPathMatcher;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.nio.charset.StandardCharsets;
import java.util.List;

@Slf4j
@Component
@RequiredArgsConstructor
public class AuthGlobalFilter implements GlobalFilter, Ordered {

    private final ObjectMapper objectMapper;

    private static final AntPathMatcher PATH_MATCHER = new AntPathMatcher();

    /** 无需鉴权的白名单路径（仅限GET请求） */
    private static final List<String> WHITE_LIST_GET = List.of(
            "/api/content/posts",              // GET 帖子列表（公开浏览）
            "/api/content/posts/**",           // GET 帖子详情（公开浏览）
            "/api/content/comments/post/**",   // GET 评论列表（公开浏览）
            "/api/content/comments/*/replies", // GET 评论子回复（公开浏览）
            "/api/user/search",                // GET 用户搜索（公开）
            "/api/user/profile/**",            // GET 指定用户公开主页（公开）
            "/api/user/stats/**",               // GET 指定用户统计（公开，登录后带 isFollowing）
            "/ws/**"                            // WebSocket 握手（token 由 chat 服务在握手时校验）
    );

    /** 无需鉴权的白名单路径（所有方法都放行） */
    private static final List<String> WHITE_LIST_ALL = List.of(
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/send-code",     // 发送登录验证码（登录前）
            "/api/auth/auto-login"     // 自动登录（登录前）
    );

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String path = exchange.getRequest().getURI().getPath();
        String method = exchange.getRequest().getMethod().name();

        // 登录/注册接口：所有方法都放行，不解析Token
        if (isWhiteListed(path, WHITE_LIST_ALL)) {
            return chain.filter(exchange);
        }

        // 公开浏览接口（仅GET）：有Token就注入用户信息（用于 isLiked 等个性化状态），
        // 没有Token也放行（匿名浏览）。即"可选鉴权"。
        if ("GET".equals(method) && isWhiteListed(path, WHITE_LIST_GET)) {
            String token = extractToken(exchange);
            if (token != null && JwtUtils.isTokenValid(token)) {
                return chain.filter(exchange.mutate().request(injectUserHeaders(exchange, token)).build());
            }
            return chain.filter(exchange);
        }

        // 其它接口：必须有有效Token
        String token = extractToken(exchange);
        if (token == null || token.isBlank()) {
            return writeErrorResponse(exchange, ResultCode.UNAUTHORIZED);
        }
        if (!JwtUtils.isTokenValid(token)) {
            return writeErrorResponse(exchange, ResultCode.TOKEN_INVALID);
        }
        return chain.filter(exchange.mutate().request(injectUserHeaders(exchange, token)).build());
    }

    /** 从 Authorization 头取出 Bearer token */
    private String extractToken(ServerWebExchange exchange) {
        String token = exchange.getRequest().getHeaders().getFirst(HttpHeaders.AUTHORIZATION);
        if (token != null && token.startsWith("Bearer ")) {
            token = token.substring(7);
        }
        return token;
    }

    /** 解析Token，把用户信息注入请求头传递给下游服务 */
    private ServerHttpRequest injectUserHeaders(ServerWebExchange exchange, String token) {
        Claims claims = JwtUtils.parseToken(token);
        String userId = claims.getSubject();
        String username = claims.get("username", String.class);
        String role = String.valueOf(claims.get("role", Integer.class));
        return exchange.getRequest().mutate()
                .header("X-User-Id", userId)
                .header("X-Username", username)
                .header("X-User-Role", role)
                .build();
    }

    private boolean isWhiteListed(String path, List<String> whiteList) {
        return whiteList.stream().anyMatch(pattern -> PATH_MATCHER.match(pattern, path));
    }

    private Mono<Void> writeErrorResponse(ServerWebExchange exchange, ResultCode code) {
        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(HttpStatus.OK);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        try {
            String body = objectMapper.writeValueAsString(Result.fail(code));
            DataBuffer buffer = response.bufferFactory()
                    .wrap(body.getBytes(StandardCharsets.UTF_8));
            return response.writeWith(Mono.just(buffer));
        } catch (JsonProcessingException e) {
            return response.setComplete();
        }
    }

    @Override
    public int getOrder() {
        return -100;
    }
}
