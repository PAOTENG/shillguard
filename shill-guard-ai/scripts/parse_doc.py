"""parse_doc.py
==============
功能：通用文档解析工具，将多种格式文档转换为纯文本字符串，供 RAG / Chat Agent 使用。
输入：文件路径（str / Path）或字节流（bytes）+ 文件名（用于判断格式）
输出：纯文本字符串（含页码/工作表分隔符，方便 LLM 定位来源）
日期：2026-06
要求：
    支持格式 — TXT · Markdown · PDF（文本原生/扫描件/复杂版式）· DOCX · PPTX · XLSX · CSV
    PDF 策略 — PyMuPDF 优先（文本原生 + 复杂版式/多栏/表格/跨页）；
               检测为扫描件时自动降级为 EasyOCR GPU 识别
工具选型（见顶部注释）：
    PyMuPDF (fitz)          PDF 文本 + 复杂版式  pip install pymupdf
    EasyOCR + pdf2image     PDF 扫描件 OCR       pip install easyocr pdf2image torch torchvision
                                                 + 系统安装 poppler
    python-docx             DOCX                 pip install python-docx
    python-pptx             PPTX                 pip install python-pptx
    openpyxl                XLSX                 pip install openpyxl
    csv（内置）              CSV                 无需安装
"""

import csv
import io
import os
from pathlib import Path
from typing import Union

# 统一类型别名：支持文件路径或原始字节
Source = Union[str, Path, bytes]


# ══════════════════════════════════════════════════════════
#  公开主入口
# ══════════════════════════════════════════════════════════

def parse_document(source: Source, filename: str) -> str:
    """
    解析文档，返回纯文本。

    :param source:   文件路径（str/Path）或字节流（bytes）
    :param filename: 文件名（含后缀），用于判断文档格式
    :return:         提取的纯文本；出错时抛出 ValueError / ImportError / RuntimeError
    """
    data = _to_bytes(source)
    ext = Path(filename).suffix.lower()

    dispatch = {
        ".txt":  _parse_txt,
        ".md":   _parse_md,
        ".pdf":  _parse_pdf,
        ".docx": _parse_docx,
        ".pptx": _parse_pptx,
        ".xlsx": _parse_xlsx,
        ".csv":  _parse_csv,
    }

    parser = dispatch.get(ext)
    if parser is None:
        raise ValueError(
            f"不支持的文件格式：{ext!r}。"
            f"当前支持：{list(dispatch.keys())}"
        )

    return parser(data).strip()


# ══════════════════════════════════════════════════════════
#  TXT
# ══════════════════════════════════════════════════════════

def _parse_txt(data: bytes) -> str:
    """
    纯文本解析。
    依次尝试 UTF-8 → GBK → Latin-1，兼容中文 Windows 文件和西文文件。
    """
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    # 最后兜底：UTF-8 替换模式，不会抛异常
    return data.decode("utf-8", errors="replace")


# ══════════════════════════════════════════════════════════
#  Markdown
# ══════════════════════════════════════════════════════════

def _parse_md(data: bytes) -> str:
    """
    Markdown 解析。
    Markdown 本身是人类可读的纯文本格式，LLM 可直接理解 # ## * 等标记语法，
    因此直接当纯文本读取，无需渲染为 HTML 再剥离标签。
    """
    return _parse_txt(data)


# ══════════════════════════════════════════════════════════
#  PDF（三阶段策略）
# ══════════════════════════════════════════════════════════

def _parse_pdf(data: bytes) -> str:
    """
    PDF 三阶段解析策略：
      阶段1：PyMuPDF block 提取 —— 处理文本原生 PDF，按阅读顺序重建多栏/跨页内容
      阶段2：扫描检测 —— 有效字符数 < 阈值则判定为扫描件
      阶段3：OCR 降级 —— pytesseract + pdf2image 对扫描件逐页识别

    公式处理说明：PyMuPDF 提取公式的文本表示（如 E=mc²）。
    如需精确公式解析（LaTeX），可替换为 MathPix API（付费云端服务）。
    """
    text = _pdf_pymupdf(data)
    if _is_scanned(text):
        text = _pdf_ocr(data)
    return text


def _pdf_pymupdf(data: bytes) -> str:
    """
    使用 PyMuPDF（fitz）按 block 提取文本。

    get_text("blocks") 返回每个文字/图像块的坐标 + 内容，
    按 (y坐标整十取整, x坐标) 排序后重建阅读顺序，
    可正确处理：多栏布局、表格、跨页段落、页眉页脚。

    工具选型依据：
      - LangChain PyMuPDFLoader 默认使用此库
      - 速度最快（C 底层），内存占用低
      - 支持 PDF 1.0 ~ 2.0 全规范
    """
    try:
        import fitz  # pip install pymupdf
    except ImportError:
        raise ImportError("缺少 pymupdf，请执行：pip install pymupdf")

    doc = fitz.open(stream=data, filetype="pdf")
    pages_text = []

    for page_num, page in enumerate(doc, start=1):
        # blocks 格式：(x0, y0, x1, y1, text, block_no, block_type)
        # block_type: 0=文字块, 1=图像块
        blocks = page.get_text("blocks")

        # 按 y 坐标（粗粒度取整避免行内微小偏差）→ x 坐标排序
        # 效果：多栏文档从左到右、从上到下正确重建阅读顺序
        blocks.sort(key=lambda b: (round(b[1] / 12), b[0]))

        page_lines = []
        for b in blocks:
            if b[6] == 0:  # 只处理文字块
                text = b[4].strip()
                if text:
                    page_lines.append(text)

        if page_lines:
            pages_text.append(f"--- 第 {page_num} 页 ---\n" + "\n".join(page_lines))

    doc.close()
    return "\n\n".join(pages_text)


def _is_scanned(text: str, threshold: int = 80) -> bool:
    """
    判断 PDF 是否为扫描件。
    有效字符数（去除空白后）< threshold 则判定为扫描件，触发 OCR 降级。
    """
    return len(text.replace("\n", "").replace(" ", "").strip()) < threshold


def _pdf_ocr(data: bytes) -> str:
    """
    扫描件 OCR 解析：pdf2image 将每页转为图片，EasyOCR GPU 识别中英文。

    工具选型依据（为何从 pytesseract 换为 EasyOCR）：
      pytesseract：传统图像处理算法，中文准确率约 80~85%，无 GPU 支持，速度慢
      EasyOCR：基于深度学习（CRNN + Transformer），中文准确率约 93~96%，
               GPU 加速（torch+cu118），80+ 种语言，pip 即装即用，无系统级依赖

    系统依赖：
      poppler → D:\\Applications\\poppler\\poppler-26.02.0\\Library\\bin（已配置 PATH）
      torch GPU → pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
    """
    # ---- 第一步：导入依赖库 ----
    # pdf2image：将 PDF 每页渲染成 PIL 图片（底层依赖 poppler）
    # easyocr：基于深度学习的 OCR 识别库
    # numpy：将 PIL 图片转为 numpy 数组（EasyOCR 要求此格式）
    try:
        from pdf2image import convert_from_bytes
        import easyocr
        import numpy as np
    except ImportError:
        raise ImportError(
            "OCR 依赖缺失，请执行：pip install pdf2image easyocr\n"
            "并确认系统已安装 poppler 且已加入 PATH。"
        )

    # ---- 第二步：把 PDF 每页渲染成图片列表 ----
    # dpi=300：每英寸 300 像素，OCR 推荐最低分辨率，低于此值文字可能模糊
    try:
        images = convert_from_bytes(data, dpi=300)
    except Exception as e:
        raise RuntimeError(
            f"pdf2image 转换失败（请确认已安装 poppler 并加入 PATH）：{e}"
        )

    # ---- 第三步：初始化 EasyOCR 识别器 ----
    # gpu=True：使用 GPU 加速（需已安装 torch+cu118）
    # 首次运行自动下载模型文件（约 100MB），需联网，之后缓存在本地
    reader = easyocr.Reader(['ch_sim', 'en'], gpu=True)

    # ---- 第四步：逐页 OCR 识别 ----
    pages_text = []
    for i, img in enumerate(images, start=1):
        # PIL Image → numpy 数组（EasyOCR 接受 numpy array 格式）
        img_array = np.array(img)

        # 返回格式：[[坐标框, '识别文字', 置信度], ...]
        results = reader.readtext(img_array)

        # 过滤置信度 < 0.3 的结果（通常是噪点或乱码）
        lines = [result[1] for result in results if result[2] >= 0.3]

        if lines:
            pages_text.append(f"--- 第 {i} 页（OCR）---\n" + "\n".join(lines))

    return "\n\n".join(pages_text)


# ══════════════════════════════════════════════════════════
#  DOCX
# ══════════════════════════════════════════════════════════

def _parse_docx(data: bytes) -> str:
    """
    DOCX 解析：提取正文段落 + 所有表格。
    表格以"单元格 | 单元格"格式输出，LLM 可理解结构。

    工具选型依据：
      - python-docx 是处理 .docx 的唯一主流开源库，无竞争者
      - 支持段落样式、表格，不支持嵌入图片中的文字（需 OCR）
    """
    try:
        from docx import Document  # pip install python-docx
    except ImportError:
        raise ImportError("缺少 python-docx，请执行：pip install python-docx")

    doc = Document(io.BytesIO(data))
    parts = []

    # 段落（按文档顺序）
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            parts.append(text)

    # 表格（所有表格追加在段落之后）
    for table in doc.tables:
        parts.append("[ 表格 ]")
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            parts.append(" | ".join(cells))

    return "\n".join(parts)


# ══════════════════════════════════════════════════════════
#  PPTX
# ══════════════════════════════════════════════════════════

def _parse_pptx(data: bytes) -> str:
    """
    PPTX 解析：逐幻灯片提取文本框 + 表格内容。
    每张幻灯片用"--- 幻灯片 N ---"分隔，方便定位来源页。

    工具选型依据：
      - python-pptx 是处理 .pptx 的唯一主流开源库，无竞争者
      - 支持文本框、表格；不支持 SmartArt 内嵌文字
    """
    try:
        from pptx import Presentation  # pip install python-pptx
    except ImportError:
        raise ImportError("缺少 python-pptx，请执行：pip install python-pptx")

    prs = Presentation(io.BytesIO(data))
    slides_text = []

    for slide_num, slide in enumerate(prs.slides, start=1):
        parts = []

        for shape in slide.shapes:
            # 文本框
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = "".join(run.text for run in para.runs).strip()
                    if text:
                        parts.append(text)

            # 表格
            if shape.has_table:
                parts.append("[ 表格 ]")
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    parts.append(" | ".join(cells))

        if parts:
            slides_text.append(
                f"--- 幻灯片 {slide_num} ---\n" + "\n".join(parts)
            )

    return "\n\n".join(slides_text)


# ══════════════════════════════════════════════════════════
#  XLSX
# ══════════════════════════════════════════════════════════

def _parse_xlsx(data: bytes) -> str:
    """
    XLSX 解析：遍历所有工作表，每行以"值 | 值 | 值"格式输出。
    跳过全空行，每张工作表用"--- 工作表：名称 ---"分隔。

    工具选型依据：
      - openpyxl 是读写 .xlsx 的标准库，被 pandas 底层调用
      - read_only=True + data_only=True：只读模式 + 读取计算结果值（非公式字符串）
    """
    try:
        import openpyxl  # pip install openpyxl
    except ImportError:
        raise ImportError("缺少 openpyxl，请执行：pip install openpyxl")

    wb = openpyxl.load_workbook(
        io.BytesIO(data), read_only=True, data_only=True
    )
    sheets_text = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows_text = []

        for row in ws.iter_rows(values_only=True):
            cells = [str(cell) if cell is not None else "" for cell in row]
            if any(c.strip() for c in cells):  # 跳过全空行
                rows_text.append(" | ".join(cells))

        if rows_text:
            sheets_text.append(
                f"--- 工作表：{sheet_name} ---\n" + "\n".join(rows_text)
            )

    wb.close()
    return "\n\n".join(sheets_text)


# ══════════════════════════════════════════════════════════
#  CSV
# ══════════════════════════════════════════════════════════

def _parse_csv(data: bytes) -> str:
    """
    CSV 解析：内置 csv 模块，自动检测编码（UTF-8 / GBK）。
    每行以"值 | 值 | 值"格式输出，跳过全空行。

    工具选型依据：
      - Python 内置 csv 模块对绝大多数 CSV 够用，无需额外依赖
      - 若需要更复杂的 CSV（多分隔符/混合引号）可换 pandas.read_csv
    """
    text = _parse_txt(data)
    reader = csv.reader(io.StringIO(text))
    rows = []
    for row in reader:
        if any(cell.strip() for cell in row):
            rows.append(" | ".join(row))
    return "\n".join(rows)


# ══════════════════════════════════════════════════════════
#  内部工具函数
# ══════════════════════════════════════════════════════════

def _to_bytes(source: Source) -> bytes:
    """将路径或字节流统一转为 bytes。"""
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    with open(source, "rb") as f:
        return f.read()


# ══════════════════════════════════════════════════════════
#  命令行快速测试入口
#  用法：python parse_doc.py <文件路径>
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法：python parse_doc.py <文件路径>")
        print("示例：python parse_doc.py report.pdf")
        sys.exit(1)

    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"文件不存在：{file_path}")
        sys.exit(1)

    print(f"正在解析：{file_path}")
    result = parse_document(file_path, os.path.basename(file_path))
    preview = result[:3000]
    print("=" * 60)
    print(preview)
    if len(result) > 3000:
        print(f"\n... （共 {len(result)} 字符，仅展示前 3000）")
    print("=" * 60)
    print(f"解析完成，共提取 {len(result)} 个字符")
