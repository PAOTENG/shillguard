package com.shillguard.content.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.shillguard.common.entity.ContentReport;

public interface ReportService {

    /**
     * 分页查询举报列表
     *
     * @param pageNum  页码
     * @param pageSize 每页数量
     * @param status   状态筛选（null=全部）
     */
    IPage<ContentReport> pageList(int pageNum, int pageSize, Integer status);

    /**
     * 更新举报状态（处理举报）
     *
     * @param reportId    举报ID
     * @param status      新状态：0=待处理 1=处理中 2=已忽略 3=已删帖 4=已转Agent
     * @param reviewNote  审核备注
     * @param reviewerId  审核人用户ID
     */
    void updateStatus(Long reportId, Integer status, String reviewNote, Long reviewerId);

    /**
     * 提交新举报
     *
     * @param report 举报实体（由 Controller 填入）
     */
    void submitReport(ContentReport report);
}
