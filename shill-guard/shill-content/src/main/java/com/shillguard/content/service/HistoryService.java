package com.shillguard.content.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.content.vo.PostVO;

public interface HistoryService {

    /** 记录浏览（重复浏览只更新时间，不新增） */
    void recordView(Long userId, Long postId);

    /** 我的浏览记录（分页，返回完整帖子，按浏览时间倒序） */
    IPage<PostVO> pageViewHistory(Long userId, int pageNum, int pageSize, Long currentUserId);

    /** 我的点赞记录（分页，返回完整帖子，按点赞时间倒序） */
    IPage<PostVO> pageLikedPosts(Long userId, int pageNum, int pageSize, Long currentUserId);
}
