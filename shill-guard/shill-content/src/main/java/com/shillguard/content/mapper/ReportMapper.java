package com.shillguard.content.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.ContentReport;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface ReportMapper extends BaseMapper<ContentReport> {
}
