package com.shillguard.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.AgentMuteRecord;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface MuteRecordMapper extends BaseMapper<AgentMuteRecord> {
}
