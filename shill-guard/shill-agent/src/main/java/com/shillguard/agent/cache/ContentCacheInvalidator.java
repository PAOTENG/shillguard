package com.shillguard.agent.cache;

import com.shillguard.common.cache.ContentCacheKeys;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;

/**
 * Agent 隐藏内容后失效 content 读缓存（两端共用 Redis db）。
 * 详情写空值短缓存，Feed 用 epoch 换代，不扫 KEYS。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ContentCacheInvalidator {

    private static final Duration HIDDEN_DETAIL_TTL = Duration.ofSeconds(60);

    private final StringRedisTemplate redisTemplate;

    /** 帖子逻辑删除：详情立刻不可见，首页缓存换代。 */
    public void onPostHidden(Long postId) {
        if (postId == null) {
            return;
        }
        try {
            redisTemplate.opsForValue().set(
                    ContentCacheKeys.POST_DETAIL + postId,
                    ContentCacheKeys.POST_DETAIL_NULL,
                    HIDDEN_DETAIL_TTL);
            redisTemplate.opsForValue().increment(ContentCacheKeys.FEED_EPOCH);
        } catch (Exception e) {
            log.warn("隐藏帖子后失效缓存失败: postId={}, err={}", postId, e.getMessage());
        }
    }

    /** 评论隐藏：只丢该帖详情（评论列表走 DB）。 */
    public void onPostDetailStale(Long postId) {
        if (postId == null) {
            return;
        }
        try {
            redisTemplate.delete(ContentCacheKeys.POST_DETAIL + postId);
        } catch (Exception e) {
            log.warn("失效帖子详情缓存失败: postId={}, err={}", postId, e.getMessage());
        }
    }
}
