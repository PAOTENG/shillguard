package com.shillguard.content.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.shillguard.common.entity.ContentComment;
import com.shillguard.common.entity.SysUser;
import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.ResultCode;
import com.shillguard.content.cache.HotPostCache;
import com.shillguard.content.dto.CommentCreateDTO;
import com.shillguard.content.mapper.CommentMapper;
import com.shillguard.content.mapper.PostMapper;
import com.shillguard.content.mapper.UserMapper;
import com.shillguard.content.service.CommentService;
import com.shillguard.content.vo.CommentVO;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.BeanUtils;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class CommentServiceImpl implements CommentService {

    private final CommentMapper commentMapper;
    private final PostMapper postMapper;
    private final UserMapper userMapper;
    private final RabbitTemplate rabbitTemplate;
    private final StringRedisTemplate redisTemplate;
    private final HotPostCache hotPostCache;

    /** 评论点赞记录存在 Redis Set：key = comment:like:{commentId}，value = 点赞用户ID */
    private static final String LIKE_KEY_PREFIX = "comment:like:";

    @Override
    public IPage<CommentVO> pageByPost(Long postId, int pageNum, int pageSize, Long currentUserId) {
        IPage<ContentComment> page = commentMapper.selectPage(
                new Page<>(pageNum, pageSize),
                new LambdaQueryWrapper<ContentComment>()
                        .eq(ContentComment::getPostId, postId)
                        .eq(ContentComment::getStatus, 0)
                        .isNull(ContentComment::getParentCommentId)
                        .orderByDesc(ContentComment::getIsTop)
                        .orderByDesc(ContentComment::getCreatedTime)
        );
        return convertPage(page, currentUserId);
    }

    @Override
    public IPage<CommentVO> pageReplies(Long parentCommentId, int pageNum, int pageSize, Long currentUserId) {
        IPage<ContentComment> page = commentMapper.selectPage(
                new Page<>(pageNum, pageSize),
                new LambdaQueryWrapper<ContentComment>()
                        .eq(ContentComment::getParentCommentId, parentCommentId)
                        .eq(ContentComment::getStatus, 0)
                        .orderByAsc(ContentComment::getCreatedTime)
        );
        return convertPage(page, currentUserId);
    }

    @Override
    @Transactional
    public Long addComment(CommentCreateDTO dto, Long userId, String clientIp) {
        // 禁言校验：被禁言用户不允许发评论
        SysUser user = userMapper.selectById(userId);
        if (user != null && user.getStatus() != null && user.getStatus() != 0) {
            throw new BizException(ResultCode.USER_MUTED);
        }

        ContentComment comment = new ContentComment();
        comment.setUserId(userId);
        comment.setPostId(dto.getPostId());
        comment.setParentCommentId(dto.getParentCommentId());
        comment.setReplyToUserId(dto.getReplyToUserId());
        comment.setContent(dto.getContent());
        comment.setLikeCount(0);
        comment.setStatus(0);
        comment.setIsTop(0);
        comment.setClientIp(clientIp);
        commentMapper.insert(comment);
        postMapper.updateCommentCount(dto.getPostId(), 1);
        hotPostCache.evict(dto.getPostId());
        if (dto.getParentCommentId() != null) {
            commentMapper.updateReplyCount(dto.getParentCommentId(), 1);
        }

        // 发送MQ消息，触发通知服务
        try {
            rabbitTemplate.convertAndSend(
                    "shillguard.exchange",
                    "comment.created",
                    comment.getCommentId() + "," + dto.getPostId() + "," + userId
            );
        } catch (Exception e) {
            log.warn("评论创建MQ发送失败，不影响主流程: {}", e.getMessage());
        }

        return comment.getCommentId();
    }

    @Override
    @Transactional
    public void deleteComment(Long commentId, Long userId, Integer role) {
        ContentComment comment = commentMapper.selectById(commentId);
        if (comment == null) {
            throw new BizException(ResultCode.COMMENT_NOT_FOUND);
        }
        if (!comment.getUserId().equals(userId) && role < 1) {
            throw new BizException(ResultCode.FORBIDDEN);
        }
        ContentComment update = new ContentComment();
        update.setCommentId(commentId);
        update.setStatus(1);
        commentMapper.updateById(update);
        postMapper.updateCommentCount(comment.getPostId(), -1);
        hotPostCache.evict(comment.getPostId());
        if (comment.getParentCommentId() != null) {
            commentMapper.updateReplyCount(comment.getParentCommentId(), -1);
        }
    }

    @Override
    public void likeComment(Long commentId, Long userId) {
        String key = LIKE_KEY_PREFIX + commentId;
        Boolean added = redisTemplate.opsForSet().add(key, String.valueOf(userId)) == 1;
        if (Boolean.TRUE.equals(added)) {
            commentMapper.updateLikeCount(commentId, 1);
        } else {
            throw new BizException(ResultCode.ALREADY_LIKED);
        }
    }

    @Override
    public void unlikeComment(Long commentId, Long userId) {
        String key = LIKE_KEY_PREFIX + commentId;
        redisTemplate.opsForSet().remove(key, String.valueOf(userId));
        commentMapper.updateLikeCount(commentId, -1);
    }

    @Override
    public ContentComment getCommentDetail(Long commentId) {
        return commentMapper.selectById(commentId);
    }

    /**
     * 把评论分页结果转成 CommentVO 分页，并批量补全评论者信息（昵称/用户名/头像）。
     */
    private IPage<CommentVO> convertPage(IPage<ContentComment> page, Long currentUserId) {
        List<ContentComment> records = page.getRecords();
        List<CommentVO> voList = new ArrayList<>();
        if (records != null && !records.isEmpty()) {
            Map<Long, SysUser> userMap = batchQueryUsers(
                    records.stream().map(ContentComment::getUserId).filter(Objects::nonNull).collect(Collectors.toSet()));
            for (ContentComment c : records) {
                CommentVO vo = new CommentVO();
                BeanUtils.copyProperties(c, vo);
                SysUser u = userMap.get(c.getUserId());
                if (u != null) {
                    vo.setUsername(u.getUsername());
                    vo.setNickname(u.getNickname());
                    vo.setAvatarUrl(u.getAvatarUrl());
                }
                // 标记当前用户是否已点赞该评论
                vo.setIsLiked(isLikedBy(c.getCommentId(), currentUserId));
                voList.add(vo);
            }
        }
        Page<CommentVO> result = new Page<>(page.getCurrent(), page.getSize(), page.getTotal());
        result.setRecords(voList);
        return result;
    }

    /** 判断当前用户是否已点赞某评论 */
    private Boolean isLikedBy(Long commentId, Long currentUserId) {
        if (commentId == null || currentUserId == null) {
            return false;
        }
        Boolean member = redisTemplate.opsForSet().isMember(
                LIKE_KEY_PREFIX + commentId, String.valueOf(currentUserId));
        return Boolean.TRUE.equals(member);
    }

    private Map<Long, SysUser> batchQueryUsers(Set<Long> userIds) {
        if (userIds == null || userIds.isEmpty()) {
            return Collections.emptyMap();
        }
        List<SysUser> users = userMapper.selectBatchIds(userIds);
        Map<Long, SysUser> map = new HashMap<>();
        for (SysUser u : users) {
            map.put(u.getUserId(), u);
        }
        return map;
    }
}
