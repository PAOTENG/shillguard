package com.shillguard.content.cache;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.shillguard.common.cache.ContentCacheKeys;
import com.shillguard.common.entity.ContentPost;
import com.shillguard.content.mapper.PostMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

/**
 * 热帖详情缓存：Cache-Aside + 互斥锁防击穿 + 空值防穿透 + TTL 随机防雪崩。
 * 只缓存 ContentPost 本体；点赞/收藏等个性化字段仍按当前用户实时查库。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class HotPostCache {

    static final String DETAIL_KEY = ContentCacheKeys.POST_DETAIL;
    private static final String LOCK_KEY = ContentCacheKeys.POST_DETAIL_LOCK;
    /** 空值占位：帖子不存在或已下架，短 TTL，避免非法 id 把流量打到 DB */
    private static final String NULL_VALUE = ContentCacheKeys.POST_DETAIL_NULL;
    private static final Duration NULL_TTL = Duration.ofSeconds(60);
    private static final Duration LOCK_TTL = Duration.ofSeconds(3);
    private static final int BASE_TTL_SEC = 90;
    private static final int JITTER_SEC = 30;

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final PostMapper postMapper;

    /**
     * @return 可展示的帖子；不存在或 status!=0 返回 null
     */
    public ContentPost getOrLoad(Long postId) {
        CacheRead first = read(postId);
        if (first.hit) {
            return first.post;
        }

        String lockKey = LOCK_KEY + postId;
        Boolean locked = redisTemplate.opsForValue().setIfAbsent(lockKey, "1", LOCK_TTL);
        if (Boolean.TRUE.equals(locked)) {
            try {
                CacheRead again = read(postId);
                if (again.hit) {
                    return again.post;
                }
                return loadAndCache(postId);
            } finally {
                redisTemplate.delete(lockKey);
            }
        }

        sleepQuietly(40);
        CacheRead waited = read(postId);
        if (waited.hit) {
            return waited.post;
        }
        // 未抢到锁且等待后仍未命中：回源一次，避免详情接口空等
        return loadAndCache(postId);
    }

    public void evict(Long postId) {
        if (postId == null) {
            return;
        }
        try {
            redisTemplate.delete(DETAIL_KEY + postId);
        } catch (Exception e) {
            log.warn("删除帖子详情缓存失败: postId={}, err={}", postId, e.getMessage());
        }
    }

    private ContentPost loadAndCache(Long postId) {
        ContentPost post = postMapper.selectById(postId);
        try {
            if (post == null || post.getStatus() == null || post.getStatus() != 0) {
                redisTemplate.opsForValue().set(DETAIL_KEY + postId, NULL_VALUE, NULL_TTL);
                return null;
            }
            int ttl = BASE_TTL_SEC + ThreadLocalRandom.current().nextInt(JITTER_SEC + 1);
            redisTemplate.opsForValue().set(
                    DETAIL_KEY + postId,
                    objectMapper.writeValueAsString(post),
                    Duration.ofSeconds(ttl));
            return post;
        } catch (Exception e) {
            log.warn("写入帖子详情缓存失败，直接返回DB结果: postId={}, err={}", postId, e.getMessage());
            return (post != null && post.getStatus() != null && post.getStatus() == 0) ? post : null;
        }
    }

    private CacheRead read(Long postId) {
        try {
            String json = redisTemplate.opsForValue().get(DETAIL_KEY + postId);
            if (json == null) {
                return CacheRead.miss();
            }
            if (NULL_VALUE.equals(json) || json.isBlank()) {
                return CacheRead.hitNull();
            }
            return CacheRead.hit(objectMapper.readValue(json, ContentPost.class));
        } catch (Exception e) {
            log.warn("读取帖子详情缓存失败，回源DB: postId={}, err={}", postId, e.getMessage());
            return CacheRead.miss();
        }
    }

    private static void sleepQuietly(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private record CacheRead(boolean hit, ContentPost post) {
        static CacheRead miss() {
            return new CacheRead(false, null);
        }

        static CacheRead hitNull() {
            return new CacheRead(true, null);
        }

        static CacheRead hit(ContentPost post) {
            return new CacheRead(true, post);
        }
    }
}
