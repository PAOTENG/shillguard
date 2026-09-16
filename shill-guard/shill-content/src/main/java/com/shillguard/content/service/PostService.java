package com.shillguard.content.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.content.dto.PostCreateDTO;
import com.shillguard.content.vo.PostPublishResultVO;
import com.shillguard.content.vo.PostVO;

public interface PostService {

    /**
     * 分页查询帖子列表
     *
     * @param userId   按用户ID过滤（可为null，null=查全部）
     * @param topicTag 按话题标签过滤（可为null）
     * @param keyword  搜索关键词（可为null，模糊匹配标题/正文/标签）
     */
    IPage<PostVO> pageList(int pageNum, int pageSize, String topicTag, Long userId, String keyword, Long currentUserId);

    /**
     * 查询“我的”帖子（含审核中、审核不通过，排除已删除），供用户中心展示。
     */
    IPage<PostVO> pageMyPosts(Long userId, int pageNum, int pageSize);

    PostVO getDetail(Long postId, Long currentUserId);

    /**
     * 发布帖子并自动审核：先置为审核中，再做敏感词检查，通过则置 0，不通过则置 3。
     */
    PostPublishResultVO createPost(PostCreateDTO dto, Long userId);

    void deletePost(Long postId, Long userId, Integer role);

    void likePost(Long postId, Long userId);

    void unlikePost(Long postId, Long userId);
}
