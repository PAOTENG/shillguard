package com.shillguard.notify.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.shillguard.common.entity.SysNotification;
import com.shillguard.notify.mapper.NotificationMapper;
import com.shillguard.notify.service.NotifyService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

@Slf4j
@Service
@RequiredArgsConstructor
public class NotifyServiceImpl implements NotifyService {

    private final NotificationMapper notificationMapper;

    @Override
    public IPage<SysNotification> pageList(Long userId, int pageNum, int pageSize) {
        LambdaQueryWrapper<SysNotification> wrapper = new LambdaQueryWrapper<SysNotification>()
                .eq(SysNotification::getUserId, userId)
                .orderByDesc(SysNotification::getCreatedTime);
        return notificationMapper.selectPage(new Page<>(pageNum, pageSize), wrapper);
    }

    @Override
    public int unreadCount(Long userId) {
        return Math.toIntExact(notificationMapper.selectCount(new LambdaQueryWrapper<SysNotification>()
                .eq(SysNotification::getUserId, userId)
                .eq(SysNotification::getIsRead, 0)));
    }

    @Override
    public void markAsRead(Long noticeId, Long userId) {
        // 只能标记自己的通知为已读，防止越权
        LambdaUpdateWrapper<SysNotification> wrapper = new LambdaUpdateWrapper<SysNotification>()
                .eq(SysNotification::getNoticeId, noticeId)
                .eq(SysNotification::getUserId, userId)
                .set(SysNotification::getIsRead, 1);
        notificationMapper.update(null, wrapper);
    }

    @Override
    public void markAllAsRead(Long userId) {
        LambdaUpdateWrapper<SysNotification> wrapper = new LambdaUpdateWrapper<SysNotification>()
                .eq(SysNotification::getUserId, userId)
                .eq(SysNotification::getIsRead, 0)
                .set(SysNotification::getIsRead, 1);
        notificationMapper.update(null, wrapper);
    }

    @Override
    public void saveNotification(SysNotification notification) {
        notification.setIsRead(0);
        notificationMapper.insert(notification);
        log.info("通知写入: userId={}, type={}", notification.getUserId(), notification.getNoticeType());
    }
}
