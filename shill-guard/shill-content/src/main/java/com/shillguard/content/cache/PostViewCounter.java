package com.shillguard.content.cache;

import com.shillguard.content.mapper.PostMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.util.Set;
import java.util.function.LongSupplier;

/**
 * 热帖浏览量：请求路径只做 Redis INCR，定时把总量回写 MySQL，避免热帖每次打开都 UPDATE。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class PostViewCounter {

    static final String TOTAL_KEY = "post:view:total:";
    static final String DIRTY_KEY = "post:view:dirty";

    private final StringRedisTemplate redisTemplate;
    private final PostMapper postMapper;

    /**
     * 浏览 +1，返回当前展示用总量。
     * Redis 无 key 时用 dbCountLoader 初始化（通常只在 Redis 重启后发生）。
     */
    public long increment(Long postId, LongSupplier dbCountLoader) {
        String key = TOTAL_KEY + postId;
        try {
            if (Boolean.FALSE.equals(redisTemplate.hasKey(key))) {
                long dbCount = Math.max(0L, dbCountLoader.getAsLong());
                redisTemplate.opsForValue().setIfAbsent(key, String.valueOf(dbCount));
            }
            Long total = redisTemplate.opsForValue().increment(key);
            redisTemplate.opsForSet().add(DIRTY_KEY, String.valueOf(postId));
            return total == null ? 0L : total;
        } catch (Exception e) {
            log.warn("Redis 浏览计数失败，降级写库: postId={}, err={}", postId, e.getMessage());
            try {
                postMapper.incrementViewCount(postId);
            } catch (Exception ex) {
                log.warn("降级写浏览量失败: postId={}, err={}", postId, ex.getMessage());
            }
            return dbCountLoader.getAsLong() + 1;
        }
    }

    public Long current(Long postId) {
        try {
            String raw = redisTemplate.opsForValue().get(TOTAL_KEY + postId);
            if (raw == null || raw.isBlank()) {
                return null;
            }
            return Long.parseLong(raw);
        } catch (Exception e) {
            return null;
        }
    }

    /** 把脏 key 的 Redis 总量刷进 MySQL；仅允许回写变大，避免并发回写把计数打回去。 */
    public int flushDirtyToDb() {
        Set<String> dirty;
        try {
            dirty = redisTemplate.opsForSet().members(DIRTY_KEY);
        } catch (Exception e) {
            log.warn("读取浏览量脏集合失败: {}", e.getMessage());
            return 0;
        }
        if (dirty == null || dirty.isEmpty()) {
            return 0;
        }
        int flushed = 0;
        for (String idStr : dirty) {
            try {
                Long postId = Long.parseLong(idStr);
                String raw = redisTemplate.opsForValue().get(TOTAL_KEY + postId);
                if (raw != null && !raw.isBlank()) {
                    long total = Long.parseLong(raw);
                    postMapper.applyViewCount(postId, total);
                    flushed++;
                }
                redisTemplate.opsForSet().remove(DIRTY_KEY, idStr);
            } catch (Exception e) {
                log.warn("回写浏览量失败: postId={}, err={}", idStr, e.getMessage());
            }
        }
        return flushed;
    }
}
