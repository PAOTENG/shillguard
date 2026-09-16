package com.shillguard.admin.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.SysUser;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

/**
 * 管理后台用户 Mapper：管理 sys_user 的角色、状态、密码。
 */
@Mapper
public interface AdminSysUserMapper extends BaseMapper<SysUser> {

    @Update("UPDATE sys_user SET role = #{role}, updated_time = NOW() WHERE user_id = #{userId}")
    int updateRole(@Param("userId") Long userId, @Param("role") int role);

    @Update("UPDATE sys_user SET status = #{status}, updated_time = NOW() WHERE user_id = #{userId}")
    int updateStatus(@Param("userId") Long userId, @Param("status") int status);

    @Update("UPDATE sys_user SET password = #{password}, updated_time = NOW() WHERE user_id = #{userId}")
    int updatePassword(@Param("userId") Long userId, @Param("password") String password);
}
