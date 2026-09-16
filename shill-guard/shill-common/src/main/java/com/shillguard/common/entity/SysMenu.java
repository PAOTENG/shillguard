package com.shillguard.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 菜单/权限表。支持树形结构（parent_id）与三种类型：目录/菜单/按钮。
 */
@Data
@TableName("sys_menu")
public class SysMenu implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long menuId;
    private Long parentId;
    private String menuName;
    /** 0=目录 1=菜单 2=按钮 */
    private Integer menuType;
    private String path;
    private String component;
    private String perms;
    private String icon;
    private Integer sort;
    /** 0=启用 1=禁用 */
    private Integer status;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdTime;
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedTime;
}
