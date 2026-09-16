package com.shillguard.agent.config;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * RabbitMQ 配置（Agent 服务）。
 * <p>
 * 与 shill-content / Python shill-guard-ai 共用 Topic Exchange {@code shillguard.exchange}。
 * 审核任务队列由 Python Worker 消费；Java 仍可通过 HTTP POST/GET 提交与轮询（Python 内部入队）。
 * Spring AMQP 声明已存在的 Exchange/Queue 时会跳过，不会报错。
 */
@Configuration
public class RabbitMqConfig {

    public static final String EXCHANGE = "shillguard.exchange";
    public static final String MODERATE_QUEUE = "ai.moderate.queue";
    public static final String MODERATE_ROUTING_KEY = "ai.moderate.request";

    @Bean
    public TopicExchange shillguardExchange() {
        return new TopicExchange(EXCHANGE, true, false);
    }

    /** Python LangGraph 审核 Worker 消费的 durable 队列。 */
    @Bean
    public Queue aiModerateQueue() {
        return new Queue(MODERATE_QUEUE, true);
    }

    @Bean
    public Binding aiModerateBinding(Queue aiModerateQueue, TopicExchange shillguardExchange) {
        return BindingBuilder.bind(aiModerateQueue)
                .to(shillguardExchange)
                .with(MODERATE_ROUTING_KEY);
    }
}
