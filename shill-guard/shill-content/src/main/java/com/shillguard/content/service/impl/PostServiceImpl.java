package com.shillguard.content.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shillguard.common.cache.ContentCacheKeys;
import com.shillguard.common.entity.ContentLike;
import com.shillguard.common.entity.ContentPost;
import com.shillguard.common.entity.SysUser;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.ResultCode;
import com.shillguard.content.cache.HotPostCache;
import com.shillguard.content.cache.PostViewCounter;
import com.shillguard.content.dto.PostCreateDTO;
import com.shillguard.content.mapper.LikeMapper;
import com.shillguard.content.mapper.PostMapper;
import com.shillguard.content.mapper.UserMapper;
import com.shillguard.content.service.HistoryService;
import com.shillguard.content.service.PostService;
import com.shillguard.content.service.support.PostEnricher;
import com.shillguard.content.util.SensitiveWordChecker;
import com.shillguard.content.vo.PostPublishResultVO;
import com.shillguard.content.vo.PostVO;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.Duration;
import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class PostServiceImpl implements PostService {

    private final PostMapper postMapper;
    private final LikeMapper likeMapper;
    private final UserMapper userMapper;
    private final PostEnricher postEnricher;
    private final HistoryService historyService;
    private final RabbitTemplate rabbitTemplate;
    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final HotPostCache hotPostCache;
    private final PostViewCounter postViewCounter;

    /** 首页推荐流缓存 key 前缀，缓存原始 ContentPost 分页（不含个性化状态），TTL 60s */
    private static final String FEED_CACHE_PREFIX = "post:feed:";
    private static final Duration FEED_CACHE_TTL = Duration.ofSeconds(60);
    private static final String POST_VIEW_ROUTING_KEY = "post.view";

    @Override
    public IPage<PostVO> pageList(int pageNum, int pageSize, String topicTag, Long userId, String keyword, Long currentUserId) {
        // 1) 先查 Redis 缓存的原始帖子分页（命中则免去 DB 排序分页查询）
        IPage<ContentPost> page = tryLoadFeedCache(pageNum, pageSize, topicTag, userId, keyword);
        if (page == null) {
            LambdaQueryWrapper<ContentPost> wrapper = new LambdaQueryWrapper<ContentPost>()
                    // 首页/搜索只展示审核通过(status=0)的帖子
                    .eq(ContentPost::getStatus, 0)
                    // 如果传了 userId，就只查这个用户的帖子
                    .eq(userId != null, ContentPost::getUserId, userId)
                    .like(StringUtils.hasText(topicTag), ContentPost::getTopicTag, topicTag)
                    // 关键词搜索：标题 / 正文 / 标签 任一模糊命中
                    .and(StringUtils.hasText(keyword), w -> w
                            .like(ContentPost::getTitle, keyword)
                            .or().like(ContentPost::getContent, keyword)
                            .or().like(ContentPost::getTopicTag, keyword))
                    .orderByDesc(ContentPost::getCreatedTime);
            page = postMapper.selectPage(new Page<>(pageNum, pageSize), wrapper);
            trySaveFeedCache(pageNum, pageSize, topicTag, userId, keyword, page);
        }
        // 2) 个性化状态（isLiked/isFavorited/作者）仍按当前用户实时补全
        return postEnricher.enrichPage(page, currentUserId);
    }

    @Override
    public IPage<PostVO> pageMyPosts(Long userId, int pageNum, int pageSize) {
        // 用户中心：查自己所有帖子，排除已删除(status=1)，包含审核中(2)/审核不通过(3)
        LambdaQueryWrapper<ContentPost> wrapper = new LambdaQueryWrapper<ContentPost>()
                .eq(ContentPost::getUserId, userId)
                .ne(ContentPost::getStatus, 1)
                .orderByDesc(ContentPost::getCreatedTime);
        IPage<ContentPost> page = postMapper.selectPage(new Page<>(pageNum, pageSize), wrapper);
        return postEnricher.enrichPage(page, userId);
    }

    @Override
    public PostVO getDetail(Long postId, Long currentUserId) {
        ContentPost post = hotPostCache.getOrLoad(postId);
        if (post == null) {
            throw new BizException(ResultCode.POST_NOT_FOUND);
        }
        // 浏览量走 Redis INCR，详情页立即可见；MySQL 由定时任务批量回写。
        long views = postViewCounter.increment(postId, () -> {
            ContentPost fresh = postMapper.selectById(postId);
            Long db = (fresh == null) ? null : fresh.getViewCount();
            return db == null ? 0L : db;
        });
        post.setViewCount(views);
        // 浏览历史仍走 MQ，避免详情接口同步写 user_view_history
        asyncRecordHistory(postId, currentUserId);

        IPage<PostVO> page = postEnricher.enrich(List.of(post), 1, 1, 1, currentUserId);
        return page.getRecords().get(0);
    }

    /** 异步记录浏览历史；失败时仅对登录用户降级同步写历史，浏览量已在 Redis 计数 */
    private void asyncRecordHistory(Long postId, Long currentUserId) {
        String payload = postId + "," + (currentUserId == null ? "" : currentUserId);
        try {
            rabbitTemplate.convertAndSend("shillguard.exchange", POST_VIEW_ROUTING_KEY, payload);
        } catch (Exception e) {
            log.warn("浏览历史MQ发送失败，降级同步写历史: {}", e.getMessage());
            if (currentUserId != null) {
                try {
                    historyService.recordView(currentUserId, postId);
                } catch (Exception ex) {
                    log.warn("降级同步写浏览历史失败: {}", ex.getMessage());
                }
            }
        }
    }

    @Override
    @Transactional
    public PostPublishResultVO createPost(PostCreateDTO dto, Long userId) {
        // 禁言校验：被禁言用户不允许发帖
        SysUser user = userMapper.selectById(userId);
        if (user != null && user.getStatus() != null && user.getStatus() != 0) {
            throw new BizException(ResultCode.USER_MUTED);
        }

        ContentPost post = new ContentPost();
        post.setUserId(userId);
        // 标题可选：为空时用内容前 30 字兜底，再为空则“未命名笔记”
        String title = dto.getTitle();
        if (title == null || title.isBlank()) {
            String content = dto.getContent() == null ? "" : dto.getContent();
            title = content.length() > 30 ? content.substring(0, 30) : content;
            if (title.isBlank()) {
                title = "未命名笔记";
            }
        }
        post.setTitle(title);
        post.setContent(dto.getContent());
        post.setCoverUrl(dto.getCoverUrl());
        post.setMediaUrl(dto.getMediaUrl());
        // postType 可默认：未传时按媒体自动推断（视频→3，有图→2，纯文字→1）
        Integer postType = dto.getPostType();
        if (postType == null) {
            if (dto.getMediaUrl() != null && !dto.getMediaUrl().isBlank()) {
                postType = 3;
            } else if (dto.getCoverUrl() != null && !dto.getCoverUrl().isBlank()) {
                postType = 2;
            } else {
                postType = 1;
            }
        }
        post.setPostType(postType);
        post.setTopicTag(dto.getTopicTag());
        // 先置为“审核中”，插入后再做敏感词检查决定最终状态
        post.setStatus(2);
        post.setViewCount(0L);
        post.setLikeCount(0);
        post.setCommentCount(0);
        postMapper.insert(post);
        log.info("帖子已提交审核: postId={}, userId={}", post.getPostId(), userId);

        // 自动审核：检查标题+正文+标签是否含敏感词/违法词
        String checkText = (post.getTitle() + " " + post.getContent() + " " + (post.getTopicTag() == null ? "" : post.getTopicTag()));
        List<String> badWords = SensitiveWordChecker.findSensitiveWords(checkText);

        PostPublishResultVO result = new PostPublishResultVO();
        result.setPostId(post.getPostId());

        ContentPost update = new ContentPost();
        update.setPostId(post.getPostId());
        if (badWords.isEmpty()) {
            // 无敏感词 → 审核通过，上首页
            update.setStatus(0);
            result.setReviewStatus(0);
            result.setReason("审核通过");
            log.info("帖子审核通过: postId={}", post.getPostId());
        } else {
            // 命中敏感词 → 审核不通过
            update.setStatus(3);
            result.setReviewStatus(3);
            result.setReason("包含敏感词：" + String.join("、", badWords));
            log.warn("帖子审核不通过: postId={}, 命中={}", post.getPostId(), badWords);
        }
        postMapper.updateById(update);
        // 新帖上线/审核结果变更，清首页推荐流缓存
        evictFeedCache();
        return result;
    }

    @Override
    public void deletePost(Long postId, Long userId, Integer role) {
        ContentPost post = postMapper.selectById(postId);
        if (post == null) {
            throw new BizException(ResultCode.POST_NOT_FOUND);
        }
        if (!post.getUserId().equals(userId) && role < 1) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        ContentPost update = new ContentPost();
        update.setPostId(postId);
        update.setStatus(1);
        postMapper.updateById(update);
        evictFeedCache();
        hotPostCache.evict(postId);
    }

    @Override
    @Transactional
    public void likePost(Long postId, Long userId) {
        ContentLike like = new ContentLike();
        like.setUserId(userId);
        like.setTargetId(postId);
        like.setTargetType(1);
        int inserted = likeMapper.insertIgnore(like);
        if (inserted <= 0) {
            throw new BizException(ResultCode.ALREADY_LIKED);
        }
        postMapper.updateLikeCount(postId, 1);
        userMapper.incrementLikedCountByPost(postId, 1);
        hotPostCache.evict(postId);
    }

    @Override
    @Transactional
    public void unlikePost(Long postId, Long userId) {
        int deleted = likeMapper.delete(new LambdaQueryWrapper<ContentLike>()
                .eq(ContentLike::getUserId, userId)
                .eq(ContentLike::getTargetId, postId)
                .eq(ContentLike::getTargetType, 1));
        if (deleted > 0) {
            postMapper.updateLikeCount(postId, -1);
            userMapper.incrementLikedCountByPost(postId, -1);
            hotPostCache.evict(postId);
        }
    }

    // ==================== 首页推荐流 Redis 缓存 ====================

    private String feedCacheKey(int pageNum, int pageSize, String topicTag, Long userId, String keyword) {
        return FEED_CACHE_PREFIX + feedEpoch() + ":" + pageNum + ":" + pageSize + ":"
                + (topicTag == null ? "all" : topicTag) + ":"
                + (userId == null ? "all" : userId) + ":"
                + (keyword == null ? "all" : keyword);
    }

    private long feedEpoch() {
        try {
            String v = redisTemplate.opsForValue().get(ContentCacheKeys.FEED_EPOCH);
            if (v == null || v.isBlank()) {
                return 0L;
            }
            return Long.parseLong(v);
        } catch (Exception e) {
            return 0L;
        }
    }

    /** 尝试从 Redis 读取缓存的原始帖子分页；未命中返回 null */
    private IPage<ContentPost> tryLoadFeedCache(int pageNum, int pageSize, String topicTag, Long userId, String keyword) {
        try {
            String json = redisTemplate.opsForValue().get(feedCacheKey(pageNum, pageSize, topicTag, userId, keyword));
            if (json == null || json.isBlank()) return null;
            JsonNode node = objectMapper.readTree(json);
            long total = node.get("total").asLong();
            long current = node.get("current").asLong();
            long size = node.get("size").asLong();
            List<ContentPost> records = objectMapper.readValue(
                    node.get("records").traverse(),
                    objectMapper.getTypeFactory().constructCollectionType(List.class, ContentPost.class));
            Page<ContentPost> page = new Page<>(current, size, total);
            page.setRecords(records);
            return page;
        } catch (Exception e) {
            log.warn("读取推荐流缓存失败，回源DB: {}", e.getMessage());
            return null;
        }
    }

    /** 查询DB后回写缓存；任何异常只打日志，不影响主流程 */
    private void trySaveFeedCache(int pageNum, int pageSize, String topicTag, Long userId, String keyword, IPage<ContentPost> page) {
        try {
            java.util.Map<String, Object> body = new java.util.HashMap<>();
            body.put("total", page.getTotal());
            body.put("current", page.getCurrent());
            body.put("size", page.getSize());
            body.put("records", page.getRecords());
            String json = objectMapper.writeValueAsString(body);
            redisTemplate.opsForValue().set(
                    feedCacheKey(pageNum, pageSize, topicTag, userId, keyword),
                    json, FEED_CACHE_TTL);
        } catch (Exception e) {
            log.warn("写入推荐流缓存失败: {}", e.getMessage());
        }
    }

    /** 首页缓存换代：INCR epoch，旧 key 随 TTL 过期，避免 KEYS 扫 Redis */
    private void evictFeedCache() {
        try {
            redisTemplate.opsForValue().increment(ContentCacheKeys.FEED_EPOCH);
        } catch (Exception e) {
            log.warn("清空推荐流缓存失败: {}", e.getMessage());
        }
    }
}
