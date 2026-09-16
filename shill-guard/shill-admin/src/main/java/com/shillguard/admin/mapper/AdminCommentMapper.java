package com.shillguard.admin.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.ContentComment;
import org.apache.ibatis.annotations.Mapper;

/** 管理后台评论 Mapper。 */
@Mapper
public interface AdminCommentMapper extends BaseMapper<ContentComment> {
}
