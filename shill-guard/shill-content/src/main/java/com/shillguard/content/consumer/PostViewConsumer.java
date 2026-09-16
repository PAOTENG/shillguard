package com.shillguard.content.consumer;

import com.rabbitmq.client.Channel;
import com.shillguard.content.service.HistoryService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.Exchange;
import org.springframework.amqp.rabbit.annotation.Queue;
import org.springframework.amqp.rabbit.annotation.QueueBinding;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

/**
 * 帖子浏览消费者：只异步写浏览历史。
 * 浏览量已在详情接口用 Redis INCR 计数，由 PostViewFlushJob 批量回写 MySQL，
 * 避免热帖每次打开都打一次 view_count 更新。
 *
 * 消息格式: "postId,userId"（userId 可能为空串，表示匿名浏览，只计数不记历史）
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class PostViewConsumer {

    private final HistoryService historyService;

    @RabbitListener(bindings = @QueueBinding(
            value = @Queue(name = "post.view.queue", durable = "true"),
            exchange = @Exchange(name = "shillguard.exchange", type = "topic"),
            key = "post.view"
    ))
    public void onViewMessage(String message, Channel channel, Message rawMessage) throws java.io.IOException {
        try {
            String[] parts = message.split(",");
            if (parts.length > 1 && !parts[1].isBlank()) {
                Long userId = Long.parseLong(parts[1]);
                Long postId = Long.parseLong(parts[0]);
                historyService.recordView(userId, postId);
            }
            channel.basicAck(rawMessage.getMessageProperties().getDeliveryTag(), false);
        } catch (Exception e) {
            log.error("处理帖子浏览历史失败: msg={}, err={}", message, e.getMessage());
            channel.basicNack(rawMessage.getMessageProperties().getDeliveryTag(), false, false);
        }
    }
}
