package com.shillguard.content.service.impl;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.shillguard.common.entity.ContentPost;
import com.shillguard.content.mapper.LikeMapper;
import com.shillguard.content.mapper.ViewHistoryMapper;
import com.shillguard.content.service.HistoryService;
import com.shillguard.content.service.support.PostEnricher;
import com.shillguard.content.vo.PostVO;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

@Slf4j
@Service
@RequiredArgsConstructor
public class HistoryServiceImpl implements HistoryService {

    private final ViewHistoryMapper viewHistoryMapper;
    private final LikeMapper likeMapper;
    private final PostEnricher postEnricher;

    @Override
    public void recordView(Long userId, Long postId) {
        if (userId == null || postId == null) return;
        viewHistoryMapper.upsertView(userId, postId);
    }

    @Override
    public IPage<PostVO> pageViewHistory(Long userId, int pageNum, int pageSize, Long currentUserId) {
        IPage<ContentPost> page = viewHistoryMapper.pageViewHistory(new Page<>(pageNum, pageSize), userId);
        return postEnricher.enrichPage(page, currentUserId);
    }

    @Override
    public IPage<PostVO> pageLikedPosts(Long userId, int pageNum, int pageSize, Long currentUserId) {
        IPage<ContentPost> page = likeMapper.pageLikedPosts(new Page<>(pageNum, pageSize), userId);
        return postEnricher.enrichPage(page, currentUserId);
    }
}
