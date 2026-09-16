package com.shillguard.content.config;

import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * RabbitMQ 配置类
 * 负责声明 Exchange（交换机），确保应用启动时自动在 RabbitMQ 中创建。
 * 队列和绑定由 shill-notify 服务的 @RabbitListener 注解自动声明。
 *
 * RabbitMQ 地址：127.0.0.1:5672
 * 账号：admin / shillguard123
 */
@Configuration
public class RabbitMqConfig {

    /**
     * 声明 Topic 类型的交换机 shillguard.exchange
     * Topic 类型支持通配符路由，如 user.* 可匹配 user.mute、user.ban 等
     * durable=true 表示 RabbitMQ 重启后交换机不消失
     */
    @Bean
    public TopicExchange shillguardExchange() {
        return new TopicExchange("shillguard.exchange", true, false);
    }
}
