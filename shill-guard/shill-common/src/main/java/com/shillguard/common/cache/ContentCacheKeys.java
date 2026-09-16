package com.shillguard.common.cache;

/**
 * 内容读缓存的 Redis key。content 与 agent 必须用同一套前缀，
 * 否则审核隐藏只改 MySQL、用户仍从旧缓存读到已下架帖。
 */
public final class ContentCacheKeys {

    public static final String POST_DETAIL = "post:detail:";
    public static final String POST_DETAIL_LOCK = "post:detail:lock:";
    /** 与 HotPostCache 空值占位一致：命中后视为帖子不可见 */
    public static final String POST_DETAIL_NULL = "__NULL__";
    /**
     * Feed 代数。写入侧 INCR，读缓存 key 带上该值，避免 KEYS 扫库。
     */
    public static final String FEED_EPOCH = "post:feed:epoch";

    private ContentCacheKeys() {
    }
}
