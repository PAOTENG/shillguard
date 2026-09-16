package com.shillguard.agent.service;

import com.shillguard.agent.dto.ModerateResultDTO;
import com.shillguard.agent.dto.ModerateTaskResultDTO;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

/**
 * 在独立线程轮询 Python 审核结果，完成后回调 {@link AgentService#finishModerate}。
 * HTTP 请求线程不再 sleep。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class ModeratePollWorker {

    private final RestTemplate restTemplate;
    private final ModerateJobStore jobStore;
    private final ObjectProvider<AgentService> agentService;

    @Value("${agent.python-service-url}")
    private String pythonServiceUrl;

    @Async("moderateExecutor")
    public void pollAndComplete(Long reportId, String taskId) {
        String pollUrl = pythonServiceUrl + "/ai/moderate/result/" + taskId;
        int maxRetries = 60;
        for (int i = 0; i < maxRetries; i++) {
            try {
                Thread.sleep(2_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                jobStore.markError(reportId, taskId, "审核轮询被中断");
                return;
            }
            try {
                ModerateTaskResultDTO poll = restTemplate.getForObject(pollUrl, ModerateTaskResultDTO.class);
                if (poll == null) {
                    continue;
                }
                switch (poll.getStatus()) {
                    case "done" -> {
                        ModerateResultDTO result = poll.getResult();
                        try {
                            agentService.getObject().finishModerate(reportId, result);
                            jobStore.markDone(reportId, taskId, result);
                            log.info("后台审核完成: reportId={}, taskId={}, action={}",
                                    reportId, taskId, result == null ? null : result.getAction());
                        } catch (Exception e) {
                            log.error("审核落库失败: reportId={}, taskId={}", reportId, taskId, e);
                            jobStore.markError(reportId, taskId, "处置落库失败: " + e.getMessage());
                        }
                        return;
                    }
                    case "error" -> {
                        jobStore.markError(reportId, taskId, poll.getError());
                        log.error("后台审核失败: reportId={}, taskId={}, err={}", reportId, taskId, poll.getError());
                        return;
                    }
                    case "not_found" -> {
                        jobStore.markError(reportId, taskId, "审核任务丢失（Python重启或超期）");
                        return;
                    }
                    default -> { }
                }
            } catch (RestClientException e) {
                log.warn("后台轮询审核异常将重试: taskId={}, err={}", taskId, e.getMessage());
            }
        }
        log.error("后台审核120s仍未结束: reportId={}, taskId={}，保持processing，下次点击续查同一taskId",
                reportId, taskId);
        jobStore.unlock(reportId);
    }
}
