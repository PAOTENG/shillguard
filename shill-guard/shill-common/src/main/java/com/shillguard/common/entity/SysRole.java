package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 角色表。role_id 与 sys_user.role (INT) 一一对应：
 * 0=普通用户 1=审核员 2=管理员 3=超级管理员。
 */
@Data
@TableName("sys_role")
public class SysRole implements Serializable {

    @TableId(type = IdType.INPUT)
    private Long roleId;
    private String roleName;
    private String roleCode;
    private String description;
    /** 0=启用 1=禁用 */
    private Integer status;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdTime;
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedTime;
}
