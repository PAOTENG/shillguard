package com.shillguard.agent.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

@Configuration
public class RestTemplateConfig {

    /**
     * RestTemplate 加超时配置：
     * - 连接超时 5s：连不上 Python 服务快速失败
     * - 读取超时 90s：AI 审核涉及多次 LLM 调用 + RAG 检索，耗时较长（10~60s），给足时间
     *
     * 用 SimpleClientHttpRequestFactory 直接设置（毫秒），兼容所有 Spring Boot 3.x 版本，
     * 避免 RestTemplateBuilder 不同小版本方法名差异。
     */
    @Bean
    public RestTemplate restTemplate() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(5_000);   // 5 秒
        factory.setReadTimeout(90_000);     // 90 秒
        return new RestTemplate(factory);
    }
}
