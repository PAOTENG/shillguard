package com.shillguard.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.ContentPost;
import org.apache.ibatis.annotations.Mapper;

/**
 * Agent 服务用于查询 content_post 表，按帖子ID读取被举报帖子的标题与正文。
 */
@Mapper
public interface ContentPostMapper extends BaseMapper<ContentPost> {
}
