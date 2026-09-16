package com.shillguard.agent.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.shillguard.agent.dto.ModerateJobVO;
import com.shillguard.agent.dto.ModerateResultDTO;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Duration;

/**
 * AI 审核任务状态：锁防重复提交，job JSON 给前端轮询。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ModerateJobStore {

    private static final String LOCK = "moderate:lock:";
    private static final String JOB = "moderate:job:";
    private static final Duration LOCK_TTL = Duration.ofSeconds(180);
    private static final Duration JOB_TTL = Duration.ofHours(1);

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;

    public boolean tryLock(Long reportId) {
        Boolean ok = redisTemplate.opsForValue().setIfAbsent(LOCK + reportId, "1", LOCK_TTL);
        return Boolean.TRUE.equals(ok);
    }

    public void unlock(Long reportId) {
        redisTemplate.delete(LOCK + reportId);
    }

    public ModerateJobVO get(Long reportId) {
        try {
            String json = redisTemplate.opsForValue().get(JOB + reportId);
            if (json == null || json.isBlank()) {
                return null;
            }
            return objectMapper.readValue(json, ModerateJobVO.class);
        } catch (Exception e) {
            log.warn("读取审核任务失败: reportId={}, err={}", reportId, e.getMessage());
            return null;
        }
    }

    public void save(ModerateJobVO job) {
        try {
            redisTemplate.opsForValue().set(
                    JOB + job.getReportId(),
                    objectMapper.writeValueAsString(job),
                    JOB_TTL);
        } catch (Exception e) {
            log.warn("写入审核任务失败: reportId={}, err={}", job.getReportId(), e.getMessage());
        }
    }

    public void markProcessing(Long reportId, String taskId) {
        ModerateJobVO job = new ModerateJobVO();
        job.setReportId(reportId);
        job.setTaskId(taskId);
        job.setStatus("processing");
        save(job);
    }

    public void markDone(Long reportId, String taskId, ModerateResultDTO result) {
        ModerateJobVO job = new ModerateJobVO();
        job.setReportId(reportId);
        job.setTaskId(taskId);
        job.setStatus("done");
        job.setResult(result);
        save(job);
        unlock(reportId);
    }

    public void markError(Long reportId, String taskId, String error) {
        ModerateJobVO job = new ModerateJobVO();
        job.setReportId(reportId);
        job.setTaskId(taskId);
        job.setStatus("error");
        job.setError(error);
        save(job);
        unlock(reportId);
    }
}
