package com.shillguard.content.util;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * 敏感词/违法词审核工具。
 *
 * 实现：内置一份敏感词表，对文本做“包含”匹配，命中即视为审核不通过。
 * 这是教学项目的简化实现；生产环境建议用 DFA/Trie 算法 + 词库文件 + ES，这里保持简单清晰。
 *
 * status 约定：0=审核通过 1=已删除 2=审核中 3=审核不通过
 */
public final class SensitiveWordChecker {

    private SensitiveWordChecker() {}

    /** 内置敏感词表（示例词，实际项目应从词库文件或配置中心加载） */
    private static final Set<String> SENSITIVE_WORDS = new HashSet<>(Arrays.asList(
            // 涉政/违法类（占位示例）
            "反动", "颠覆", "煽动", "传销", "诈骗", "洗钱", "贩毒", "赌博", "黄赌毒",
            // 营销违规/水军相关（与“水军检测”平台主题相关）
            "刷单", "刷量", "代刷", "炒信", "黑公关", "网络水军", "虚假宣传", "夸大宣传",
            // 常见辱骂/低俗
            "傻逼", "废物", "去死", "滚蛋"
    ));

    /**
     * 检查文本是否包含敏感词。
     *
     * @param text 待检查文本（标题/正文/标签拼接）
     * @return 命中的敏感词列表（去重）；为空表示通过
     */
    public static List<String> findSensitiveWords(String text) {
        List<String> hit = new ArrayList<>();
        if (text == null || text.isBlank()) {
            return hit;
        }
        // 统一小写，便于匹配英文敏感词（此处主要为中文，影响不大）
        String lower = text.toLowerCase();
        for (String word : SENSITIVE_WORDS) {
            if (lower.contains(word.toLowerCase())) {
                hit.add(word);
            }
        }
        return hit;
    }

    /** 是否审核通过（不含敏感词） */
    public static boolean isClean(String text) {
        return findSensitiveWords(text).isEmpty();
    }
}
