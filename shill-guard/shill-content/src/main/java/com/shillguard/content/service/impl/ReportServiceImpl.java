package com.shillguard.content.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.shillguard.common.entity.ContentComment;
import com.shillguard.common.entity.ContentPost;
import com.shillguard.common.entity.ContentReport;
import com.shillguard.content.mapper.CommentMapper;
import com.shillguard.content.mapper.PostMapper;
import com.shillguard.content.mapper.ReportMapper;
import com.shillguard.content.service.ReportService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

@Slf4j
@Service
@RequiredArgsConstructor
public class ReportServiceImpl implements ReportService {

    private final ReportMapper reportMapper;
    private final CommentMapper commentMapper;
    private final PostMapper postMapper;

    @Override
    public IPage<ContentReport> pageList(int pageNum, int pageSize, Integer status) {
        LambdaQueryWrapper<ContentReport> wrapper = new LambdaQueryWrapper<ContentReport>()
                // 如果传了 status 就按 status 过滤，否则查全部
                .eq(status != null, ContentReport::getStatus, status)
                .orderByDesc(ContentReport::getCreatedTime);
        return reportMapper.selectPage(new Page<>(pageNum, pageSize), wrapper);
    }

    @Override
    public void updateStatus(Long reportId, Integer status, String reviewNote, Long reviewerId) {
        LambdaUpdateWrapper<ContentReport> wrapper = new LambdaUpdateWrapper<ContentReport>()
                .eq(ContentReport::getReportId, reportId)
                .set(ContentReport::getStatus, status)
                .set(reviewNote != null, ContentReport::getReviewNote, reviewNote)
                .set(reviewerId != null, ContentReport::getReviewerUserId, reviewerId)
                .set(ContentReport::getUpdatedTime, LocalDateTime.now());
        reportMapper.update(null, wrapper);
        log.info("举报状态更新: reportId={}, status={}, reviewer={}", reportId, status, reviewerId);
    }

    @Override
    public void submitReport(ContentReport report) {
        // 兜底：reported_user_id 在数据库里没有默认值，前端若没传则按举报对象查出作者ID补上
        if (report.getReportedUserId() == null) {
            if (report.getReportedCommentId() != null) {
                ContentComment c = commentMapper.selectById(report.getReportedCommentId());
                if (c != null) {
                    report.setReportedUserId(c.getUserId());
                }
            } else if (report.getReportedPostId() != null) {
                ContentPost p = postMapper.selectById(report.getReportedPostId());
                if (p != null) {
                    report.setReportedUserId(p.getUserId());
                }
            }
        }
        // 仍为空时给 0，避免 NOT NULL 列插入失败（0 表示"未知用户"，审核流程会按内容判定）
        if (report.getReportedUserId() == null) {
            report.setReportedUserId(0L);
        }
        reportMapper.insert(report);
        log.info("新举报提交: reportId={}, reporter={}, reportedUser={}",
                report.getReportId(), report.getReporterUserId(), report.getReportedUserId());
    }
}
