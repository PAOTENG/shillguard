package com.shillguard.file.controller;

import com.shillguard.common.exception.BizException;
import com.shillguard.common.result.Result;
import com.shillguard.common.result.ResultCode;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.Arrays;
import java.util.List;
import java.util.UUID;

@Slf4j
@Tag(name = "文件上传接口")
@RestController
@RequestMapping("/api/file")
@RequiredArgsConstructor
public class FileController {

    private final MinioClient minioClient;

    @Value("${minio.bucket-name}")
    private String bucketName;

    @Value("${minio.endpoint}")
    private String endpoint;

    private static final List<String> ALLOWED_IMAGE_TYPES =
            Arrays.asList("image/jpeg", "image/png", "image/gif", "image/webp");
    private static final List<String> ALLOWED_VIDEO_TYPES =
            Arrays.asList("video/mp4", "video/quicktime", "video/x-msvideo");
    private static final long MAX_IMAGE_SIZE = 10 * 1024 * 1024L; // 10MB
    private static final long MAX_VIDEO_SIZE = 200 * 1024 * 1024L; // 200MB
    /** 聊天文件：单文件最大 50MB */
    private static final long MAX_CHAT_FILE_SIZE = 50 * 1024 * 1024L;
    /** 聊天文件允许的后缀（支持压缩包与常见文档，按后缀判断更可靠） */
    private static final List<String> ALLOWED_CHAT_FILE_EXTS = Arrays.asList(
            ".zip", ".rar", ".7z", ".gz", ".tar", ".bz2",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
            ".txt", ".md", ".csv", ".json", ".xml",
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
            ".mp3", ".wav", ".flac", ".mp4", ".mov", ".avi",
            ".zipx", ".tgz"
    );

    @Operation(summary = "上传图片")
    @PostMapping("/image")
    public Result<String> uploadImage(@RequestParam("file") MultipartFile file) {
        validateFile(file, ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE);
        return Result.success(doUpload(file, "images/"));
    }

    @Operation(summary = "上传视频")
    @PostMapping("/video")
    public Result<String> uploadVideo(@RequestParam("file") MultipartFile file) {
        validateFile(file, ALLOWED_VIDEO_TYPES, MAX_VIDEO_SIZE);
        return Result.success(doUpload(file, "videos/"));
    }

    @Operation(summary = "上传头像")
    @PostMapping("/avatar")
    public Result<String> uploadAvatar(@RequestParam("file") MultipartFile file) {
        validateFile(file, ALLOWED_IMAGE_TYPES, 5 * 1024 * 1024L);
        return Result.success(doUpload(file, "avatars/"));
    }

    @Operation(summary = "上传聊天文件（支持压缩包与常见文档，单文件≤50MB，不支持文件夹）")
    @PostMapping("/chat-file")
    public Result<String> uploadChatFile(@RequestParam("file") MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new BizException("文件不能为空");
        }
        if (file.getSize() > MAX_CHAT_FILE_SIZE) {
            throw new BizException(ResultCode.FILE_TOO_LARGE);
        }
        // 拒绝文件夹上传：浏览器目录上传时文件名常含 "/"，且 originalFilename 可能为空
        String name = file.getOriginalFilename();
        if (name == null || name.isBlank()) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "文件名无效");
        }
        if (name.contains("/") || name.contains("\\")) {
            throw new BizException(ResultCode.PARAM_ERROR.getCode(), "不支持上传文件夹");
        }
        String lower = name.toLowerCase();
        boolean extOk = ALLOWED_CHAT_FILE_EXTS.stream().anyMatch(lower::endsWith);
        if (!extOk) {
            throw new BizException(ResultCode.FILE_TYPE_NOT_ALLOWED);
        }
        return Result.success(doUpload(file, "chat-files/"));
    }

    private void validateFile(MultipartFile file, List<String> allowedTypes, long maxSize) {
        if (file == null || file.isEmpty()) {
            throw new BizException("文件不能为空");
        }
        if (!allowedTypes.contains(file.getContentType())) {
            throw new BizException(ResultCode.FILE_TYPE_NOT_ALLOWED);
        }
        if (file.getSize() > maxSize) {
            throw new BizException(ResultCode.FILE_TOO_LARGE);
        }
    }

    private String doUpload(MultipartFile file, String folder) {
        String ext = "";
        String originalName = file.getOriginalFilename();
        if (originalName != null && originalName.contains(".")) {
            ext = originalName.substring(originalName.lastIndexOf("."));
        }
        String objectName = folder + UUID.randomUUID() + ext;
        try {
            minioClient.putObject(PutObjectArgs.builder()
                    .bucket(bucketName)
                    .object(objectName)
                    .stream(file.getInputStream(), file.getSize(), -1)
                    .contentType(file.getContentType())
                    .build());
            String url = endpoint + "/" + bucketName + "/" + objectName;
            log.info("文件上传成功: {}", url);
            return url;
        } catch (Exception e) {
            log.error("MinIO上传失败: {}", e.getMessage());
            throw new BizException(ResultCode.FILE_UPLOAD_FAIL);
        }
    }
}
