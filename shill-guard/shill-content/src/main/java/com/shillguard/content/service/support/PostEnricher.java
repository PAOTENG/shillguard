package com.shillguard.content.service.support;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.shillguard.common.entity.ContentLike;
import com.shillguard.common.entity.ContentPost;
import com.shillguard.common.entity.SysUser;
import com.shillguard.common.entity.UserFavorite;
import com.shillguard.content.mapper.FavoriteMapper;
import com.shillguard.content.mapper.LikeMapper;
import com.shillguard.content.mapper.UserMapper;
import com.shillguard.content.vo.PostVO;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.util.*;
import java.util.stream.Collectors;

/**
 * 帖子补全器：把 ContentPost 转成 PostVO，并批量补上作者信息、
 * 当前用户的 isLiked / isFavorited 状态。
 * 点赞/收藏状态以数据库(content_like/user_favorite)为准，保证与种子数据一致。
 */
@Component
@RequiredArgsConstructor
public class PostEnricher {

    private final UserMapper userMapper;
    private final LikeMapper likeMapper;
    private final FavoriteMapper favoriteMapper;

    /** 分页转换：ContentPost 分页 -> PostVO 分页（补作者 + 点赞/收藏状态） */
    public IPage<PostVO> enrichPage(IPage<ContentPost> page, Long currentUserId) {
        return enrich(page.getRecords(), page.getTotal(), page.getCurrent(), page.getSize(), currentUserId);
    }

    /**
     * 把一批 ContentPost 转成 PostVO 分页。
     * 用于“浏览/点赞/收藏记录”等场景：先查出一批帖子，再统一补全。
     */
    public IPage<PostVO> enrich(List<ContentPost> records, long total, long current, long size, Long currentUserId) {
        List<PostVO> voList = new ArrayList<>();
        if (records != null && !records.isEmpty()) {
            Map<Long, SysUser> userMap = batchQueryUsers(
                    records.stream().map(ContentPost::getUserId).filter(Objects::nonNull).distinct().collect(Collectors.toList()));
            // 批量查当前用户的点赞/收藏状态，避免逐条查库
            Set<Long> likedIds = currentUserId == null ? Collections.emptySet()
                    : queryLikedIds(currentUserId, records.stream().map(ContentPost::getPostId).toList());
            Set<Long> favedIds = currentUserId == null ? Collections.emptySet()
                    : queryFavoritedIds(currentUserId, records.stream().map(ContentPost::getPostId).toList());
            for (ContentPost p : records) {
                PostVO vo = new PostVO();
                org.springframework.beans.BeanUtils.copyProperties(p, vo);
                fillAuthor(vo, p.getUserId(), userMap);
                vo.setIsLiked(likedIds.contains(p.getPostId()));
                vo.setIsFavorited(favedIds.contains(p.getPostId()));
                voList.add(vo);
            }
        }
        Page<PostVO> result = new Page<>(current, size, total);
        result.setRecords(voList);
        return result;
    }

    public Boolean isLikedBy(Long postId, Long currentUserId) {
        if (postId == null || currentUserId == null) return false;
        Long cnt = likeMapper.selectCount(new LambdaQueryWrapper<ContentLike>()
                .eq(ContentLike::getUserId, currentUserId)
                .eq(ContentLike::getTargetId, postId)
                .eq(ContentLike::getTargetType, 1));
        return cnt != null && cnt > 0;
    }

    public Boolean isFavoritedBy(Long postId, Long currentUserId) {
        if (postId == null || currentUserId == null) return false;
        Long cnt = favoriteMapper.selectCount(new LambdaQueryWrapper<UserFavorite>()
                .eq(UserFavorite::getUserId, currentUserId)
                .eq(UserFavorite::getPostId, postId));
        return cnt != null && cnt > 0;
    }

    /** 批量查当前用户已点赞的帖子id集合 */
    private Set<Long> queryLikedIds(Long userId, List<Long> postIds) {
        if (postIds == null || postIds.isEmpty()) return Collections.emptySet();
        List<ContentLike> likes = likeMapper.selectList(new LambdaQueryWrapper<ContentLike>()
                .eq(ContentLike::getUserId, userId)
                .eq(ContentLike::getTargetType, 1)
                .in(ContentLike::getTargetId, postIds));
        return likes.stream().map(ContentLike::getTargetId).collect(Collectors.toSet());
    }

    /** 批量查当前用户已收藏的帖子id集合 */
    private Set<Long> queryFavoritedIds(Long userId, List<Long> postIds) {
        if (postIds == null || postIds.isEmpty()) return Collections.emptySet();
        List<UserFavorite> favs = favoriteMapper.selectList(new LambdaQueryWrapper<UserFavorite>()
                .eq(UserFavorite::getUserId, userId)
                .in(UserFavorite::getPostId, postIds));
        return favs.stream().map(UserFavorite::getPostId).collect(Collectors.toSet());
    }

    private Map<Long, SysUser> batchQueryUsers(Collection<Long> userIds) {
        if (userIds == null || userIds.isEmpty()) return Collections.emptyMap();
        List<SysUser> users = userMapper.selectBatchIds(userIds);
        Map<Long, SysUser> map = new HashMap<>();
        for (SysUser u : users) map.put(u.getUserId(), u);
        return map;
    }

    private void fillAuthor(PostVO vo, Long userId, Map<Long, SysUser> userMap) {
        if (userId == null) return;
        SysUser u = userMap.get(userId);
        if (u != null) {
            vo.setUsername(u.getUsername());
            vo.setNickname(u.getNickname());
            vo.setAvatarUrl(u.getAvatarUrl());
        }
    }
}
