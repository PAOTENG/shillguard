package com.shillguard.user.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.SysUser;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface SysUserMapper extends BaseMapper<SysUser> {

    /** 某用户被关注数 +delta */
    @Update("UPDATE sys_user SET follower_count = follower_count + #{delta} WHERE user_id = #{userId}")
    void incrementFollowerCount(@Param("userId") Long userId, @Param("delta") int delta);

    /** 某用户关注数 +delta */
    @Update("UPDATE sys_user SET following_count = following_count + #{delta} WHERE user_id = #{userId}")
    void incrementFollowingCount(@Param("userId") Long userId, @Param("delta") int delta);
}
