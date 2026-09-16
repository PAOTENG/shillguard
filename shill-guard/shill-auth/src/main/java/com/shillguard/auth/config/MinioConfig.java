package com.shillguard.auth.config;

import io.minio.BucketExistsArgs;
import io.minio.MakeBucketArgs;
import io.minio.MinioClient;
import io.minio.SetBucketPolicyArgs;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * MinIO 客户端配置（auth 服务用）。
 * 注册用户时自动生成头像上传到这里，和 shill-file 共用同一个 bucket。
 */
@Slf4j
@Configuration
public class MinioConfig {

    @Value("${minio.endpoint}")
    private String endpoint;

    @Value("${minio.access-key}")
    private String accessKey;

    @Value("${minio.secret-key}")
    private String secretKey;

    @Value("${minio.bucket-name}")
    private String bucketName;

    @Bean
    public MinioClient minioClient() {
        MinioClient client = MinioClient.builder()
                .endpoint(endpoint)
                .credentials(accessKey, secretKey)
                .build();
        // 确保 bucket 存在且对外可公开读（浏览器才能直接加载头像）
        try {
            boolean exists = client.bucketExists(
                    BucketExistsArgs.builder().bucket(bucketName).build());
            if (!exists) {
                client.makeBucket(MakeBucketArgs.builder().bucket(bucketName).build());
                log.info("MinIO bucket '{}' 创建成功", bucketName);
            }
            // 设置公开读策略：允许匿名 GET 对象
            String policy = "{" +
                    "\"Version\":\"2012-10-17\"," +
                    "\"Statement\":[{" +
                    "\"Effect\":\"Allow\"," +
                    "\"Principal\":{\"AWS\":[\"*\"]}," +
                    "\"Action\":[\"s3:GetObject\"]," +
                    "\"Resource\":[\"arn:aws:s3:::" + bucketName + "/*\"]}]}";
            client.setBucketPolicy(SetBucketPolicyArgs.builder()
                    .bucket(bucketName).config(policy).build());
        } catch (Exception e) {
            // 不影响启动，头像上传失败时会在注册流程里降级处理
            log.warn("MinIO bucket 初始化失败（不影响服务启动）: {}", e.getMessage());
        }
        return client;
    }
}
