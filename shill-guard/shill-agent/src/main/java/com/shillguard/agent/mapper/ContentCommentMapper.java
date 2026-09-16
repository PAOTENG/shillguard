package com.shillguard.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.ContentComment;
import org.apache.ibatis.annotations.Mapper;

/**
 * Agent 服务用于查询 content_comment 表，按评论ID读取被举报评论的原文。
 */
@Mapper
public interface ContentCommentMapper extends BaseMapper<ContentComment> {
}
