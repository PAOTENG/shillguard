package com.shillguard.admin.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.ContentPost;
import org.apache.ibatis.annotations.Mapper;

/**
 * 管理后台帖子/视频 Mapper：直接操作 content_post，提供不限 status 的全量视图。
 */
@Mapper
public interface AdminPostMapper extends BaseMapper<ContentPost> {
}
