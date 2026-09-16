package com.shillguard.agent.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.shillguard.common.entity.ContentReport;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface ContentReportMapper extends BaseMapper<ContentReport> {

    /** 待处理 → 处理中，并发下只有一行成功 */
    @Update("UPDATE content_report SET status = 1, updated_time = NOW() " +
            "WHERE report_id = #{reportId} AND status = 0")
    int casMarkProcessing(@Param("reportId") Long reportId);

    /** 处置时锁定举报行，避免两次 apply 各写一条禁言 */
    @Select("SELECT * FROM content_report WHERE report_id = #{reportId} FOR UPDATE")
    ContentReport selectForUpdate(@Param("reportId") Long reportId);
}
