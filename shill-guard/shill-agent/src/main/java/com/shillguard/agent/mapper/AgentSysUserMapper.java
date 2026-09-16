package com.shillguard.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.SysUser;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

/**
 * Agent 服务用于更新 sys_user.status（禁言/解禁）。
 * 复用 shill-common 的 SysUser 实体；只做状态更新，不查敏感字段。
 */
@Mapper
public interface AgentSysUserMapper extends BaseMapper<SysUser> {

    /** 把用户状态置为指定值（1=禁言 0=正常 2=封号） */
    @Update("UPDATE sys_user SET status = #{status}, updated_time = NOW() WHERE user_id = #{userId}")
    int updateStatus(@Param("userId") Long userId, @Param("status") int status);

    /** 更新用户预警级别：0=无 1=预警 2=高危（由恶意行为检测写入） */
    @Update("UPDATE sys_user SET warning_level = #{level}, updated_time = NOW() WHERE user_id = #{userId}")
    int updateWarningLevel(@Param("userId") Long userId, @Param("level") int level);
}
