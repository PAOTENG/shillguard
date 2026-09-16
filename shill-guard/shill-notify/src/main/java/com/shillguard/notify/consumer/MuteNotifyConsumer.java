package com.shillguard.notify.consumer;

import com.rabbitmq.client.Channel;
import com.shillguard.common.entity.SysNotification;
import com.shillguard.notify.service.NotifyService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.Exchange;
import org.springframework.amqp.rabbit.annotation.Queue;
import org.springframework.amqp.rabbit.annotation.QueueBinding;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

import java.io.IOException;

@Slf4j
@Component
@RequiredArgsConstructor
public class MuteNotifyConsumer {

    private final NotifyService notifyService;

    @RabbitListener(bindings = @QueueBinding(
            value = @Queue(name = "notify.mute.queue", durable = "true"),
            exchange = @Exchange(name = "shillguard.exchange", type = "topic"),
            key = "user.mute"
    ))
    public void onMuteMessage(String message, Channel channel, Message rawMessage) throws IOException {
        try {
            // message格式: "userId,days"
            String[] parts = message.split(",");
            Long userId = Long.parseLong(parts[0]);
            Integer days = Integer.parseInt(parts[1]);
            log.info("接收到禁言通知: userId={}, days={}", userId, days);

            // 写入站内通知表
            SysNotification notification = new SysNotification();
            notification.setUserId(userId);
            notification.setNoticeType(1); // 1=禁言通知
            notification.setTitle("账号禁言通知");
            notification.setContent("您的账号已被禁言 " + days + " 天，如有异议请提交申诉。");
            notifyService.saveNotification(notification);

            channel.basicAck(rawMessage.getMessageProperties().getDeliveryTag(), false);
        } catch (Exception e) {
            log.error("处理禁言通知失败: {}", e.getMessage());
            channel.basicNack(rawMessage.getMessageProperties().getDeliveryTag(), false, false);
        }
    }

    @RabbitListener(bindings = @QueueBinding(
            value = @Queue(name = "notify.comment.queue", durable = "true"),
            exchange = @Exchange(name = "shillguard.exchange", type = "topic"),
            key = "comment.created"
    ))
    public void onCommentMessage(String message, Channel channel, Message rawMessage) throws IOException {
        try {
            // message格式: "commentId,postId,userId"
            String[] parts = message.split(",");
            Long commentId = Long.parseLong(parts[0]);
            Long postId = Long.parseLong(parts[1]);
            Long userId = Long.parseLong(parts[2]);
            log.info("接收到评论通知: commentId={}, postId={}, userId={}", commentId, postId, userId);

            // 写入站内通知（通知评论者本人）
            SysNotification notification = new SysNotification();
            notification.setUserId(userId);
            notification.setNoticeType(2); // 2=评论通知
            notification.setTitle("评论发表成功");
            notification.setContent("您的评论已发表成功，帖子ID: " + postId);
            notification.setRelatedId(commentId);
            notifyService.saveNotification(notification);

            channel.basicAck(rawMessage.getMessageProperties().getDeliveryTag(), false);
        } catch (Exception e) {
            log.error("处理评论通知失败: {}", e.getMessage());
            channel.basicNack(rawMessage.getMessageProperties().getDeliveryTag(), false, false);
        }
    }
}
