package com.shillguard.admin;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;

/**
 * 管理后台微服务启动类。
 *
 * <p>聚合管理帖子、视频、用户、角色权限(RBAC)四类后台管理能力，
 * 通过直接访问共享数据库（content_post / content_comment / sys_user / sys_role / sys_menu 等）
 * 提供不限 status 的全量视图与运营操作，区别于面向 C 端的 shill-content/shill-user。
 */
@SpringBootApplication
@MapperScan("com.shillguard.admin.mapper")
@ComponentScan(basePackages = {"com.shillguard.admin", "com.shillguard.common"})
public class AdminApplication {
    public static void main(String[] args) {
        SpringApplication.run(AdminApplication.class, args);
    }
}
