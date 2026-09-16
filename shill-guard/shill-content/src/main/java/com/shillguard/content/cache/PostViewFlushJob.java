package com.shillguard.content.cache;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 每 10 秒把 Redis 浏览总量刷回 MySQL。热帖打开不再同步打库。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class PostViewFlushJob {

    private final PostViewCounter postViewCounter;

    @Scheduled(fixedDelay = 10_000L, initialDelay = 10_000L)
    public void flush() {
        int n = postViewCounter.flushDirtyToDb();
        if (n > 0) {
            log.debug("浏览量回写完成: posts={}", n);
        }
    }
}
