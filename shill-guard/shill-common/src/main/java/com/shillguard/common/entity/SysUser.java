package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

@Data
@TableName("sys_user")
public class SysUser implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long userId;
    private String username;
    private String password;
    private String nickname;
    private String phone;
    private String email;
    private String avatarUrl;
    /** 0=普通用户 1=审核员 2=管理员 3=超管 */
    private Integer role;
    /** 0=正常 1=禁言 */
    private Integer status;
    /** 预警级别：0=无 1=预警 2=高危（由恶意行为检测写入，用于用户管理页徽标） */
    private Integer warningLevel;
    /** 关注数（我关注了多少人） */
    private Long followingCount;
    /** 被关注数（粉丝数） */
    private Long followerCount;
    /** 被点赞数（我所有帖子获赞总数） */
    private Long likedCount;
    /** 被收藏数（我所有帖子被收藏总数） */
    private Long favoritedCount;
    private String registerIp;
    private LocalDateTime lastLoginTime;
    private String lastLoginIp;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdTime;
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedTime;
}
