package com.shillguard.auth.util;

import javax.imageio.ImageIO;
import java.awt.*;
import java.awt.geom.Ellipse2D;
import java.awt.geom.Rectangle2D;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.io.IOException;

/**
 * 头像生成工具：根据昵称首字生成一张 256x256 的圆形渐变头像（PNG）。
 * 颜色按用户名 hash 取色，保证不同用户颜色基本不同。
 *
 * 仅用 JDK 内置能力，无需第三方图像库。
 * 注意：中文字符需要系统有 CJK 字体（Windows 自带微软雅黑，Linux 需装 fonts-wqy-zenhei 等）。
 */
public final class AvatarGenerator {

    private AvatarGenerator() {}

    /** 配色表（柔和渐变起色） */
    private static final Color[] PALETTE = {
            new Color(255, 122, 138), new Color(255, 165, 92),  new Color(255, 206, 106),
            new Color(130, 203, 114), new Color(90, 191, 217),  new Color(120, 160, 250),
            new Color(180, 130, 230), new Color(240, 130, 200), new Color(250, 110, 110),
            new Color(80, 200, 180),  new Color(200, 180, 90),  new Color(150, 195, 230),
            new Color(210, 150, 200), new Color(170, 210, 130),
    };

    private static final int SIZE = 256;

    /**
     * 生成头像 PNG 字节数组。
     *
     * @param text    昵称或用户名（取首个字符绘制）
     * @param seed    颜色种子（一般用用户名 hashCode）
     * @return PNG 字节数组
     */
    public static byte[] generate(String text, int seed) {
        BufferedImage img = new BufferedImage(SIZE, SIZE, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g = img.createGraphics();
        try {
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);

            // 1) 圆形裁剪，让头像呈圆形
            Ellipse2D circle = new Ellipse2D.Double(0, 0, SIZE - 1, SIZE - 1);
            g.setClip(circle);

            // 2) 对角线渐变填充
            Color c1 = PALETTE[Math.abs(seed) % PALETTE.length];
            Color c2 = PALETTE[(Math.abs(seed) / 3 + 5) % PALETTE.length];
            GradientPaint paint = new GradientPaint(0, 0, c1, SIZE, SIZE, c2);
            g.setPaint(paint);
            g.fillRect(0, 0, SIZE, SIZE);

            g.setClip(null);

            // 3) 居中绘制首字
            String ch = firstChar(text);
            g.setColor(Color.WHITE);
            Font font = pickFont(SIZE / 2 + 24);
            g.setFont(font);
            FontMetrics fm = g.getFontMetrics();
            Rectangle2D bounds = fm.getStringBounds(ch, g);
            int x = (int) ((SIZE - bounds.getWidth()) / 2 - bounds.getX());
            int y = (int) ((SIZE - bounds.getHeight()) / 2 - bounds.getY());
            g.drawString(ch, x, y);
        } finally {
            g.dispose();
        }

        try (ByteArrayOutputStream baos = new ByteArrayOutputStream()) {
            ImageIO.write(img, "png", baos);
            return baos.toByteArray();
        } catch (IOException e) {
            throw new RuntimeException("生成头像失败", e);
        }
    }

    /** 取首个字符（中文取第一个汉字，英文取首字母） */
    private static String firstChar(String text) {
        if (text == null || text.isEmpty()) {
            return "?";
        }
        return text.trim().substring(0, 1);
    }

    /**
     * 选择字体：优先用常见 CJK 字体，找不到就用逻辑字体兜底。
     */
    private static Font pickFont(int size) {
        String[] candidates = {"Microsoft YaHei", "微软雅黑", "PingFang SC", "WenQuanYi Zen Hei", "Noto Sans CJK SC"};
        for (String name : candidates) {
            Font f = new Font(name, Font.BOLD, size);
            // 能否显示常见中文"人"字，粗略判断字体是否含 CJK
            if (f.canDisplayUpTo("人") == -1) {
                return f;
            }
        }
        // 兜底：逻辑无衬线字体
        return new Font(Font.SANS_SERIF, Font.BOLD, size);
    }
}
