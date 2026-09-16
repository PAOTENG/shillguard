package com.shillguard.file;

import com.baomidou.mybatisplus.autoconfigure.MybatisPlusAutoConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.ComponentScan;

// 文件服务只使用 MinIO，不连数据库。
// 但 shill-common 传递引入了 mybatis-plus-starter，会触发数据源自动配置，
// 这里显式排除掉，避免启动时因缺少 datasource.url 而失败。
@SpringBootApplication(exclude = {
        DataSourceAutoConfiguration.class,
        MybatisPlusAutoConfiguration.class
})
@ComponentScan(basePackages = {"com.shillguard.file", "com.shillguard.common"})
public class FileApplication {
    public static void main(String[] args) {
        SpringApplication.run(FileApplication.class, args);
    }
}
