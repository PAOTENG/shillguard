package com.shillguard.notify.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.entity.SysNotification;

public interface NotifyService {

    /** 分页查询用户通知列表 */
    IPage<SysNotification> pageList(Long userId, int pageNum, int pageSize);

    /** 获取未读通知数量 */
    int unreadCount(Long userId);

    /** 标记单条通知为已读 */
    void markAsRead(Long noticeId, Long userId);

    /** 标记当前用户所有通知为已读 */
    void markAllAsRead(Long userId);

    /** 内部方法：写入一条通知（供MQ消费者调用） */
    void saveNotification(SysNotification notification);
}
