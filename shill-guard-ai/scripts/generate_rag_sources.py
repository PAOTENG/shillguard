"""生成 RAG 测试知识库：在 app/rag/sources/ 下生成 9 份多格式文档。
覆盖格式：TXT / Markdown / PDF / DOCX / PPTX / XLSX / CSV
覆盖业务领域：平台规则 / 操作指南 / 账号安全 / 商业化 / 客服 / 直播会员 / 隐私
运行：python scripts/generate_rag_sources.py
"""
from pathlib import Path

from docx import Document
from pptx import Presentation
from pptx.util import Inches, Pt
import openpyxl
import fitz  # PyMuPDF


SOURCES = Path(__file__).resolve().parent.parent / "app" / "rag" / "sources"
SOURCES.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────
# 1. 社区公约.txt   (TXT)
# ─────────────────────────────────────────────────────────────
def make_community_rules_txt():
    text = """《ShillGuard 社区公约》v3.2

一、禁止内容
1. 涉政、涉黄、涉暴、涉赌内容
2. 虚假宣传、夸大功效的带货笔记
3. 医疗类未经资质认证的诊疗建议
4. 引流到外部平台（微信、QQ群等）的二维码或链接

二、违规处理
- 首次违规：笔记下架，警告
- 二次违规：限流 7 天
- 三次违规：账号封禁 30 天
- 严重违规：永久封禁

三、申诉渠道
邮件至 appeal@shillguard.com，3 个工作日内回复。
"""
    (SOURCES / "社区公约.txt").write_text(text, encoding="utf-8")
    print("✓ 社区公约.txt")


# ─────────────────────────────────────────────────────────────
# 2. 内容审核标准.md   (Markdown)
# ─────────────────────────────────────────────────────────────
def make_review_standards_md():
    text = """# 内容审核标准（机器 + 人工）

## 图片审核

- 不得包含二维码（系统自动识别）
- 不得有明显水印（其他平台 logo）
- 不得暴露过度

## 文字审核

- 敏感词库匹配（政治 / 色情 / 医疗违禁词）
- 重复内容检测（搬运他人笔记）
- 虚假价格信息（与商品页不符）

## 处理时效

| 类型 | 平均处理时长 |
|------|--------------|
| 普通 | 10 分钟内 |
| 举报 | 1 小时内 |
| 申诉 | 1-3 个工作日 |
"""
    (SOURCES / "内容审核标准.md").write_text(text, encoding="utf-8")
    print("✓ 内容审核标准.md")


# ─────────────────────────────────────────────────────────────
# 3. 用户操作指南.docx   (DOCX)
# ─────────────────────────────────────────────────────────────
def make_user_guide_docx():
    doc = Document()
    doc.add_heading("《App 操作手册》", level=1)

    doc.add_heading("发笔记", level=2)
    doc.add_paragraph("1. 底部 \"+\" 按钮")
    doc.add_paragraph("2. 选图片/视频（最多9张图，视频60秒内）")
    doc.add_paragraph("3. 加标题（≤20字）、正文（≤1000字）")
    doc.add_paragraph("4. 添加话题标签（#开头，最多10个）")
    doc.add_paragraph("5. 添加地点（可选）")
    doc.add_paragraph("6. 发布")

    doc.add_heading("编辑笔记", level=2)
    doc.add_paragraph("仅在发布后 24 小时内可编辑")
    doc.add_paragraph("路径：我的 → 笔记 → 右上角\"…\" → 编辑")

    doc.add_heading("删除笔记", level=2)
    doc.add_paragraph("路径：我的 → 笔记 → 右上角\"…\" → 删除")
    doc.add_paragraph("删除后不可恢复，点赞收藏数全部清零")

    doc.add_heading("评论管理", level=2)
    doc.add_paragraph("自己笔记下的评论可删除")
    doc.add_paragraph("不能编辑评论，只能删除后重发")

    doc.save(SOURCES / "用户操作指南.docx")
    print("✓ 用户操作指南.docx")


# ─────────────────────────────────────────────────────────────
# 4. 账号安全FAQ.pdf   (PDF)
# ─────────────────────────────────────────────────────────────
def make_account_security_pdf():
    doc = fitz.open()
    page = doc.new_page()

    lines = [
        ("账号与安全 FAQ", True),
        ("", False),
        ("Q: 忘记密码怎么办？", True),
        ("A: 登录页 → 忘记密码 → 输入注册手机号 → 短信验证 → 重置密码。", False),
        ("   若手机号也丢失，走账号申诉：设置 → 帮助 → 账号申诉。", False),
        ("", False),
        ("Q: 如何修改绑定手机号？", True),
        ("A: 设置 → 账号与安全 → 手机号 → 验证旧手机号 → 输入新手机号。", False),
        ("   每 30 天只能改一次。", False),
        ("", False),
        ("Q: 账号被盗怎么办？", True),
        ("A: 立即冻结账号（登录页 → 更多 → 冻结账号），", False),
        ("   然后邮件 security@shillguard.com 申诉。", False),
        ("   申诉需提供：注册手机号、近 3 次登录地、身份证照片。", False),
        ("", False),
        ("Q: 第三方登录（微信/QQ）解绑？", True),
        ("A: 设置 → 账号与安全 → 第三方账号 → 解绑。", False),
        ("   注意：解绑前必须先绑定手机号，否则无法登录。", False),
    ]

    y = 80
    for text, is_bold in lines:
        fontname = "helv-bold" if is_bold else "helv"
        # PyMuPDF 内置字体不支持中文，使用 toka 字体或降级为图片
        # 这里用 insert_text 配置中文字体路径（Windows 微软雅黑）
        page.insert_text((72, y), text, fontname="china-s", fontsize=12 if is_bold else 11)
        y += 22

    doc.save(SOURCES / "账号安全FAQ.pdf")
    doc.close()
    print("✓ 账号安全FAQ.pdf")


# ─────────────────────────────────────────────────────────────
# 5. 品牌合作规范.docx   (DOCX)
# ─────────────────────────────────────────────────────────────
def make_brand_cooperation_docx():
    doc = Document()
    doc.add_heading("《品牌合作规范》v2.0", level=1)

    doc.add_heading("谁可以接广告", level=2)
    doc.add_paragraph("粉丝数 ≥ 1000")
    doc.add_paragraph("近 30 天发布笔记 ≥ 5 篇")
    doc.add_paragraph("无违规记录")

    doc.add_heading("报备流程", level=2)
    doc.add_paragraph("1. 品牌方在「蒲公英平台」下单")
    doc.add_paragraph("2. 博主接单 → 在笔记中标注\"赞助\"")
    doc.add_paragraph("3. 笔记发布后 24 小时内回填链接")
    doc.add_paragraph("4. 未报备的软广一经发现按违规处理")

    doc.add_heading("佣金与结算", level=2)
    doc.add_paragraph("平台抽成 10%")
    doc.add_paragraph("笔记发布后 7 天结算")
    doc.add_paragraph("提现门槛 100 元起")

    doc.save(SOURCES / "品牌合作规范.docx")
    print("✓ 品牌合作规范.docx")


# ─────────────────────────────────────────────────────────────
# 6. 带货违禁清单.csv   (CSV)
# ─────────────────────────────────────────────────────────────
def make_banned_goods_csv():
    import csv
    rows = [
        ["类别", "具体商品", "依据"],
        ["处方药", "抗生素、降压药、精神类药物", "《药品管理法》"],
        ["医疗器械", "注射器、隐形眼镜、助听器", "《医疗器械监督管理条例》"],
        ["烟草", "卷烟、雪茄、电子烟、烟丝", "《广告法》"],
        ["野生动物制品", "象牙、犀角、穿山甲鳞片", "《野生动物保护法》"],
        ["迷信服务", "算命、风水、占卜", "平台规则"],
        ["代孕捐卵", "代孕服务、捐卵广告", "《人类辅助生殖技术管理办法》"],
        ["催情迷药", "催情类、迷药类产品", "《刑法》"],
        ["虚假减肥", "7 天瘦 10 斤类虚假宣传", "《广告法》"],
    ]
    with open(SOURCES / "带货违禁清单.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print("✓ 带货违禁清单.csv")


# ─────────────────────────────────────────────────────────────
# 7. 申诉流程.txt   (TXT)
# ─────────────────────────────────────────────────────────────
def make_appeal_process_txt():
    text = """申诉流程

【笔记申诉】
- 路径：通知 → 违规通知 → 申诉
- 处理时间：1-3 个工作日
- 同一笔记仅可申诉 1 次

【账号封禁申诉】
- 邮件：appeal@shillguard.com
- 必含：账号 ID、封禁通知截图、申诉理由、整改承诺
- 处理时间：3-7 个工作日

【投诉其他用户】
- 路径：对方主页 → 右上角"…" → 投诉
- 选项：抄袭/广告/骚扰/违法
- 24 小时内反馈处理结果
"""
    (SOURCES / "申诉流程.txt").write_text(text, encoding="utf-8")
    print("✓ 申诉流程.txt")


# ─────────────────────────────────────────────────────────────
# 8. 直播规范.pptx   (PPTX)
# ─────────────────────────────────────────────────────────────
def make_live_streaming_pptx():
    prs = Presentation()

    # 第1张：开通条件
    slide1 = prs.slides.add_slide(prs.slide_layouts[1])
    slide1.shapes.title.text = "直播开通条件"
    slide1.placeholders[1].text = (
        "1. 实名认证\n"
        "2. 粉丝数 ≥ 500\n"
        "3. 近 30 天无违规记录"
    )

    # 第2张：禁止行为
    slide2 = prs.slides.add_slide(prs.slide_layouts[1])
    slide2.shapes.title.text = "直播禁止行为"
    slide2.placeholders[1].text = (
        "1. 直播带货需走蒲公英报备\n"
        "2. 不得引导站外交易\n"
        "3. 不得出现未成年人单独直播\n"
        "4. 单场直播时长 ≤ 4 小时"
    )

    # 第3张：会员权益
    slide3 = prs.slides.add_slide(prs.slide_layouts[1])
    slide3.shapes.title.text = "会员服务"
    slide3.placeholders[1].text = (
        "月卡 25 元，年卡 228 元\n"
        "权益包括：\n"
        "- 专属表情包\n"
        "- 隐藏信息流广告\n"
        "- 数据看板（粉丝增长、笔记表现）\n"
        "- 优先客服响应"
    )

    prs.save(SOURCES / "直播规范.pptx")
    print("✓ 直播规范.pptx")


# ─────────────────────────────────────────────────────────────
# 9. 隐私政策摘要.xlsx   (XLSX)
# ─────────────────────────────────────────────────────────────
def make_privacy_xlsx():
    wb = openpyxl.Workbook()

    # Sheet1：收集的数据
    ws1 = wb.active
    ws1.title = "收集的数据"
    ws1.append(["数据类别", "具体内容", "是否必要", "用途"])
    ws1.append(["必要", "手机号、昵称、头像", "是", "账号注册与登录"])
    ws1.append(["可选", "地理位置", "否", "本地内容推荐"])
    ws1.append(["可选", "通讯录", "否", "查找朋友功能"])
    ws1.append(["自动", "设备 ID、IP 地址", "是", "风控反作弊"])
    ws1.append(["自动", "浏览记录、点赞历史", "是", "个性化推荐"])

    # Sheet2：数据使用
    ws2 = wb.create_sheet("数据使用")
    ws2.append(["用途", "是否共享第三方"])
    ws2.append(["个性化推荐内容", "否"])
    ws2.append(["风控反作弊", "否"])
    ws2.append(["广告投放", "仅匿名 ID"])
    ws2.append(["不会出售用户数据", "—"])

    # Sheet3：数据导出
    ws3 = wb.create_sheet("数据导出")
    ws3.append(["项目", "说明"])
    ws3.append(["入口", "设置 → 账号与安全 → 数据导出"])
    ws3.append(["交付方式", "邮件发送下载链接"])
    ws3.append(["处理时长", "7 个工作日内"])
    ws3.append(["包含内容", "笔记、评论、收藏、关注列表"])

    wb.save(SOURCES / "隐私政策摘要.xlsx")
    print("✓ 隐私政策摘要.xlsx")


if __name__ == "__main__":
    print(f"生成 RAG 测试文档到：{SOURCES}\n")
    make_community_rules_txt()
    make_review_standards_md()
    make_user_guide_docx()
    make_account_security_pdf()
    make_brand_cooperation_docx()
    make_banned_goods_csv()
    make_appeal_process_txt()
    make_live_streaming_pptx()
    make_privacy_xlsx()
    print(f"\n全部完成，共 9 个文件。")
