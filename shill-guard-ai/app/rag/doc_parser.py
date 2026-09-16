"""app/rag/doc_parser.py
=======================
功能：通用文档解析器，将多种格式文档转换为纯文本字符串，供 Chat Agent RAG 层使用。

输入：
  - 文件路径（str / pathlib.Path）或字节流（bytes）+ 文件名字符串
  - 或 FastAPI 的 UploadFile 对象（通过 parse_upload_file() 异步接口）

输出：
  - 纯文本字符串（含页码 / 工作表分隔标记，方便 LLM 定位来源）
  - 超出 max_chars 时自动截断，防止 LLM 上下文窗口溢出

日期：2026-06

支持格式：
  TXT · Markdown · PDF（文本原生 / 扫描件 / 复杂版式）· DOCX · PPTX · XLSX · CSV

依赖安装：
  pip install pymupdf python-docx python-pptx openpyxl easyocr pdf2image

系统级依赖（OCR 扫描件需要，pdf2image 底层需要 poppler，pip 无法安装）：
  Windows:
    poppler → D:\\Applications\\poppler\\poppler-26.02.0\\Library\\bin（已配置 PATH）
  Docker / Linux:
    RUN apt-get install -y poppler-utils

OCR 引擎：EasyOCR（基于深度学习，GPU 加速，中文准确率 ~95%）
  pip install easyocr torch torchvision
  torch GPU 版：pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

项目调用位置：
  - app/agents/chat/router.py  → parse_document(data, filename) 处理用户上传文档（同步版）
  - app/rag/indexer.py         → parse_document(bytes, filename)  构建知识库索引
  - parse_upload_file() 异步版当前未被路由直接调用，保留备用

==========================================================================
讲解与设计说明（供开发者阅读）

【为什么用 io.BytesIO？】
  python-docx / openpyxl / python-pptx 的构造函数要求传入"文件对象"，
  不接受原始 bytes。io.BytesIO(data) 把内存中的字节流包装成假文件对象，
  避免先写入磁盘再读取，提高性能并保持无副作用。

【为什么用字典派发而不是 if-elif？】
  dispatch 字典以 O(1) 速度查找解析器函数，新增格式只需加一行条目，
  不需要修改主函数逻辑，符合开闭原则。

【PDF 为什么三阶段？】
  阶段1 PyMuPDF：速度最快，处理文本原生 + 复杂版式；
  阶段2 扫描检测：文本提取结果有效字符 < 80 则判定为扫描件；
  阶段3 OCR 降级：pytesseract + pdf2image 识别图片中的文字。

【为什么按 (round(y/12), x) 排序 block？】
  PDF 多栏布局中同一行的左右两栏 y 坐标会有 1~5pt 微小偏差，
  直接排序会把同行内容打乱。除以 12 取整后相同行落入同一"桶"，
  再按 x 排序即可正确重建左→右阅读顺序。

【为什么加 max_chars 截断？】
  200 页 PDF 提取后可达 50 万字符，超出 LLM 上下文窗口（通常 8k~128k token）
  会直接报错。截断保留文档前段（最重要内容往往在前），避免服务崩溃。

【parse_upload_file 为什么是 async？】
  FastAPI 的 UploadFile.read() 是协程（async），必须用 await 调用，
  所以包装函数也必须是 async def，供 router.py 中的 async 路由函数 await 调用。
==========================================================================
"""

import csv
import io
import os
from pathlib import Path
from typing import Union

# ── 类型别名 ────────────────────────────────────────────────────────────────
# Union[str, Path, bytes]：类型注解，表示参数可以是三种类型之一。
# 仅供 IDE 类型检查和文档提示使用，运行时不强制校验。
Source = Union[str, Path, bytes]

# ── 默认截断长度 ─────────────────────────────────────────────────────────────
# -1 表示不截断（行业主流做法：解析器只负责提取，不做内容截断决策）
# 截断策略应在上层 router.py / graph.py 根据当前对话 token 用量动态决定
# 参考：LangChain / LlamaIndex / Unstructured 的 document loader 均不在解析层截断
DEFAULT_MAX_CHARS = -1


# ══════════════════════════════════════════════════════════════════════════════
#  公开接口 1：同步调用（供 indexer.py 构建 RAG 知识库时使用）
# ══════════════════════════════════════════════════════════════════════════════

def parse_document(source: Source, filename: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """
    解析文档，返回纯文本字符串。

    参数：
        source    — 文件路径（str/Path）或字节流（bytes）
        filename  — 文件名含后缀，如 "report.pdf"，用于判断格式
        max_chars — 最大字符数，超出截断（默认 50000），传 -1 表示不截断

    返回：
        提取的纯文本字符串，首尾空白已去除

    异常：
        ValueError    — 不支持的文件格式
        ImportError   — 缺少对应解析库（提示安装命令）
        RuntimeError  — 文件损坏或系统工具未安装（如 poppler）
    """
    # ---- 第一步：把传进来的文件统一变成"字节"格式 ----
    # source 可能是路径字符串，也可能已经是字节
    # _to_bytes 帮我们统一处理，后面所有解析函数只认识字节格式
    data = _to_bytes(source)

    # ---- 第二步：从文件名取出后缀，用来判断文件格式 ----
    # Path(filename)：把文件名字符串包装成路径对象
    # .suffix：取出后缀部分，比如 "report.PDF" 取出 ".PDF"
    # .lower()：全部变小写，避免 ".PDF" 和 ".pdf" 被当成两种格式
    # 最终 ext 里存的是类似 ".pdf"、".docx" 这样的字符串
    ext = Path(filename).suffix.lower()

    # ---- 第三步：建一张"格式->解析函数"的查询表 ----
    # 字典的 key 是后缀字符串，value 是对应的解析函数（注意：这里存的是函数本身，没有加括号调用）
    # 好处：新增格式只需加一行，不需要改主逻辑（不用写一大堆 if-elif）
    dispatch = {
        ".txt":  _parse_txt,
        ".md":   _parse_md,
        ".pdf":  _parse_pdf,
        ".docx": _parse_docx,
        ".pptx": _parse_pptx,
        ".xlsx": _parse_xlsx,
        ".csv":  _parse_csv,
    }

    # ---- 第四步：拿后缀去查询表，找到对应的解析函数 ----
    # dispatch.get(ext)：如果 ext 在字典里，返回对应的函数；不在则返回 None
    parser = dispatch.get(ext)
    if parser is None:
        # 查不到说明这个格式不支持，直接报错
        # raise ValueError：主动抛出"值错误"异常，函数立即终止
        # f"..." 是格式化字符串，{ext!r} 表示带引号显示，比如 '.xyz'
        raise ValueError(
            f"不支持的文件格式：{ext!r}。"
            f"当前支持：{list(dispatch.keys())}"
        )

    # ---- 第五步：调用查到的函数，解析文档，取到文字结果 ----
    # parser(data)：调用找到的函数（比如 _parse_pdf），把字节数据传进去
    # .strip()：去掉结果字符串首尾的空格、换行符等空白字符
    result = parser(data).strip()

    # ---- 第六步：根据 max_chars 决定是否截断 ----
    # max_chars > 0：只有传了正整数才截断（-1 表示不截断，直接跳过这段）
    # len(result) > max_chars：结果字符数超过上限才需要截断
    if max_chars > 0 and len(result) > max_chars:
        # result[:max_chars]：Python 切片语法，取字符串的前 max_chars 个字符
        # 然后拼上一段提示文字，让 LLM 知道文档内容不完整，避免它误以为已读完全文
        result = (
            result[:max_chars]
            + f"\n\n[文档内容过长，已截断。原文共 {len(result)} 字符，"
            f"当前仅展示前 {max_chars} 字符。如需分析完整内容，建议使用 RAG 知识库功能。]"
        )

    # ---- 最后：返回处理好的纯文本 ----
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  公开接口 2：异步调用（供 router.py 处理 FastAPI UploadFile 时使用）
# ══════════════════════════════════════════════════════════════════════════════

async def parse_upload_file(upload_file, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """
    解析 FastAPI UploadFile 对象，返回纯文本字符串。

    参数：
        upload_file — FastAPI 的 UploadFile 实例
                      .filename 属性：原始文件名字符串
                      .read()   方法：async，读取全部字节，返回 bytes
        max_chars   — 最大字符数，超出截断

    返回：
        提取的纯文本字符串

    用法（在 router.py 中）：
        from app.rag.doc_parser import parse_upload_file

        @router.post("/chat")
        async def chat(file: UploadFile = File(None), ...):
            doc_text = await parse_upload_file(file) if file else ""

    说明：
        upload_file.read() 是协程（coroutine），必须 await 调用，
        因此本函数也必须是 async def。
        内部直接复用同步的 parse_document()，不重复逻辑。
    """
    # ==== 关于 async / await 的说明（Python 异步概念）====
    # 普通函数：代码一行一行顺序执行，遇到耗时操作（比如等文件传输）会"卡住"等待
    # async 函数：遇到耗时操作时，不卡住，把 CPU 让给其他任务，操作完了再回来继续
    # await：告诉 Python "这里需要等待，等好了再往下走"
    #
    # 为什么这里必须用 async？
    #   upload_file.read() 是 FastAPI 定义的协程函数（用 async def 定义的）
    #   协程函数必须用 await 调用，而 await 只能在 async def 函数内部使用
    #   所以这个包装函数也必须是 async def
    # =================================================

    # ---- 第一步：等待前端上传完文件，把文件内容全部读成字节 ----
    # await：在这里暂停，等 upload_file.read() 把文件全部读完
    # upload_file.read()：读取用户上传的文件全部内容，返回 bytes
    # 读好的字节数据存进 data
    data = await upload_file.read()

    # ---- 第二步：取出文件名 ----
    # upload_file.filename：FastAPI 从 HTTP 请求头里自动解析出的文件名，比如 "报告.pdf"
    # or "unknown.txt"：如果 filename 为空（None 或 ""），就用 "unknown.txt" 代替
    #   or 的逻辑：左边是"假值"（None/空字符串）时取右边的值
    filename = upload_file.filename or "unknown.txt"

    # ---- 第三步：调用普通的同步解析函数处理，直接返回结果 ----
    # 把字节数据 data 和文件名 filename 交给 parse_document 去判断格式和解析
    # 这里不需要 await，因为 parse_document 是普通函数（非协程），同步执行
    return parse_document(data, filename, max_chars=max_chars)


# ══════════════════════════════════════════════════════════════════════════════
#  TXT 解析
# ══════════════════════════════════════════════════════════════════════════════

def _parse_txt(data: bytes) -> str:
    """
    纯文本解析。
    #等于是直接进行解码输出
    调用：bytes.decode(encoding)
      — 将字节序列按指定编码转换为 Unicode 字符串
      — 若字节与编码不匹配则抛出 UnicodeDecodeError

    编码尝试顺序：
      utf-8   → 现代标准，macOS/Linux/互联网文件
      gbk     → 中文 Windows 默认编码（旧版 Word 导出、Windows 记事本另存为）
      latin-1 → 西欧文件；特性：任意单字节都合法，不会抛异常，作为兜底前一步

    兜底：errors="replace" 将无法解码的字节替换为 U+FFFD（?），保证不崩溃
    """
    # 准备按顺序尝试三种编码格式：utf-8、gbk、latin-1
    # 为什么要尝试多种？因为文件是别人创建的，不知道他用什么编码保存的
    # utf-8：现代标准，macOS/Linux/网络文件普遍使用
    # gbk：中文 Windows 系统的默认编码（很多旧版 Word 导出、Windows 记事本保存的文件）
    # latin-1：西欧编码，理论上任意单字节值都合法，不会解码失败，作为倒数第二保险
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            # data.decode(enc)：把字节按照 enc 编码翻译成 Unicode 字符串
            # 如果字节内容和编码方式不匹配，Python 会抛出 UnicodeDecodeError
            return data.decode(enc)
        except UnicodeDecodeError:
            # 解码失败：说明这个编码不对，用 continue 跳过，进入下一轮循环
            continue

    # 三种都失败了（极少发生）：用 errors="replace" 强制解码
    # errors="replace"：遇到无法解码的字节，用替换符 U+FFFD（显示为 ?) 代替
    # 保证函数一定能返回字符串，不会崩溃
    return data.decode("utf-8", errors="replace")


# ══════════════════════════════════════════════════════════════════════════════
#  Markdown 解析
# ══════════════════════════════════════════════════════════════════════════════

def _parse_md(data: bytes) -> str:
    """
    Markdown 解析。

    直接当纯文本读取，不渲染 HTML 再剥离标签。
    原因：LLM 天然理解 # ## * ` 等 Markdown 语法，
    不渲染反而保留了更多语义结构（标题层级、代码块标记等）。
    """
    return _parse_txt(data)


# ══════════════════════════════════════════════════════════════════════════════
#  PDF 解析（三阶段）
# ══════════════════════════════════════════════════════════════════════════════

def _parse_pdf(data: bytes) -> str:
    """
    PDF 三阶段解析策略：
      阶段1：PyMuPDF block 提取（文本原生 + 复杂版式/多栏/表格/跨页）
      阶段2：扫描检测（有效字符数 < 80 则判定为扫描件）
      阶段3：OCR 降级（EasyOCR + pdf2image，GPU 加速）
    """
    # ---- 第一阶段：用 PyMuPDF 尝试直接提取 PDF 里的文字 ----
    # 对于普通 PDF（文字是矢量文字，不是图片），这一步可以提取出所有文字
    # 结果存进 text
    text = _pdf_pymupdf(data)

    # ---- 第二阶段：判断是否是扫描件 ----
    # _is_scanned(text)：统计 text 里有效字符数量
    # 如果字符数量极少（小于80个），说明这个 PDF 是扫描件（内容是图片，没有文字层）
    if _is_scanned(text):
        # ---- 第三阶段：OCR 识别 ----
        # 是扫描件，丢弃第一阶段的结果，改用 OCR 方式重新处理
        # OCR = Optical Character Recognition，光学字符识别：把图片里的文字识别出来
        text = _pdf_ocr(data)

    # 返回最终文字（要么是 PyMuPDF 提取的，要么是 OCR 识别的）
    return text


def _pdf_pymupdf(data: bytes) -> str:
    """
    使用 PyMuPDF（fitz 模块）提取 PDF 文本。

    为什么叫 fitz？
      PyMuPDF 是对 MuPDF C 库的 Python 绑定，
      历史上以开发者 Artifex 的工程师 Tor Andersson（网名 fitz）命名。

    fitz.open() 参数说明：
      stream=data   → 从内存字节流打开，不需要落盘
      filetype="pdf" → 明确告知格式，避免自动检测出错

    fitz 模块其他常用方法：
      doc.page_count              → 总页数
      doc.metadata                → 字典，含 title/author/creationDate
      doc.get_toc()               → 目录大纲列表 [(level, title, page), ...]
      page.get_text("text")       → 纯文本，无位置信息
      page.get_text("blocks")     → 块列表，含坐标 ← 本函数使用
      page.get_text("dict")       → 完整字典，含字体大小/颜色/行距
      page.get_text("html")       → HTML 字符串
      page.get_images()           → 图片列表（可用于提取图片）
      page.search_for("keyword")  → 搜索关键词位置

    blocks 元组结构：
      (x0, y0, x1, y1, text, block_no, block_type)
        x0/y0：左上角坐标   x1/y1：右下角坐标
        text：块内文字      block_no：块编号
        block_type：0=文字块  1=图像块

    排序键 (round(b[1]/12), b[0]) 解析：
      b[1] 是 y 坐标（距页面顶端距离，单位 pt）
      除以 12 取整：把 y 坐标粗粒度化，同一行内 ±6pt 的误差会落到同一桶
      b[0] 是 x 坐标：同一行内按从左到右排序
      效果：正确处理双栏 PDF，左栏整段读完再读右栏
    """
    # 尝试导入 fitz（PyMuPDF 库的模块名）
    # 为什么放在函数内部 import？
    #   避免没装这个库就让整个文件报错，改为用到时才检查，并给出安装提示
    try:
        import fitz  # pip install pymupdf
    except ImportError:
        raise ImportError("缺少 pymupdf，请执行：pip install pymupdf")

    # ---- 第一步：用 fitz 把字节数据打开成 PDF 文档对象 ----
    # stream=data：从内存字节流打开，不需要先把文件写到磁盘
    # filetype="pdf"：明确告知格式，避免 fitz 自动猜测出错
    # doc 是文档对象，可以按页遍历
    doc = fitz.open(stream=data, filetype="pdf")

    # ---- 第二步：建空列表，用来收集每页提取的文字 ----
    pages_text = []

    # ---- 第三步：逐页处理 ----
    # enumerate(doc, start=1)：对 doc 里每一页循环
    #   page_num：页码，从 1 开始（start=1 让它从1算而不是从0算）
    #   page：当前页的对象
    for page_num, page in enumerate(doc, start=1):

        # page.get_text("blocks")：提取这页所有"文字块"的列表
        # 每个块是一个元组，共7个值：
        #   b[0] = 左边界 x0    b[1] = 上边界 y0
        #   b[2] = 右边界 x1    b[3] = 下边界 y1
        #   b[4] = 块内文字（字符串）
        #   b[5] = 块编号       b[6] = 块类型（0=文字，1=图片）
        blocks = page.get_text("blocks")

        # 对 blocks 按位置重新排序，重建正确的阅读顺序
        # 排序规则：先按 round(b[1]/12)，再按 b[0]
        #   b[1] 是块的上边界 y 坐标（离页面顶端的距离，单位是点 pt）
        #   除以12再取整：把 y 坐标粗粒度化，同一行内 ±6pt 的偏差会落入同一"桶"
        #   这样双栏 PDF 的左栏和右栏同行文字不会因为 y 值微小差异而排乱
        #   同桶内再按 b[0]（左边界 x）排序，实现从左到右的阅读顺序
        # key=lambda b: (...)：lambda 是匿名函数，这里定义排序键的计算规则
        blocks.sort(key=lambda b: (round(b[1] / 12), b[0]))

        # 建空列表，收集这一页的文字行
        page_lines = []

        for b in blocks:
            # b[6] == 0：只处理文字块，图片块（b[6]==1）跳过
            if b[6] == 0:
                # b[4] 是文字内容，.strip() 去掉首尾空白
                text = b[4].strip()
                # 不为空才加入（避免把空块也加进去）
                if text:
                    page_lines.append(text)

        # 这页有内容才加入总列表
        if page_lines:
            # f"--- 第 {page_num} 页 ---\n"：页码标记，帮助 LLM 知道内容来自哪页
            # "\n".join(page_lines)：把这页所有文字行用换行拼在一起
            pages_text.append(f"--- 第 {page_num} 页 ---\n" + "\n".join(page_lines))

    # ---- 第四步：关闭文档，释放内存 ----
    doc.close()

    # 把所有页用两个换行拼起来，返回整个 PDF 的文字
    # "\n\n".join(...)：每页之间留一个空行，视觉上分隔清晰
    return "\n\n".join(pages_text)


def _is_scanned(text: str, threshold: int = 80) -> bool:
    """
    判断 PDF 是否为扫描件。

    原理：扫描件是图片，PyMuPDF 提取不到文字，有效字符数极少。
    text.replace("\\n","").replace(" ","").strip()：去除所有空白再统计长度。
    threshold=80：经验值，小于 80 个有效字符视为扫描件。
    """
    # text.replace("\n", "")：把所有换行符去掉
    # .replace(" ", "")：把所有空格去掉
    # .strip()：再去掉首尾可能残留的其他空白字符（如制表符）
    # len(...)：统计剩下的有效字符数量
    # < threshold：如果有效字符数小于阈值（默认80），就认为是扫描件，返回 True
    # 原理：扫描件的 PDF 内容全是图片，PyMuPDF 根本提取不到文字，有效字符极少
    return len(text.replace("\n", "").replace(" ", "").strip()) < threshold


def _pdf_ocr(data: bytes) -> str:
    """
    扫描件 OCR：pdf2image 转图片 → EasyOCR GPU 识别中英文。

    为何从 pytesseract 换为 EasyOCR？
      pytesseract：传统图像处理算法，中文准确率约 80~85%，无 GPU 支持，速度慢
      EasyOCR：基于深度学习（CRNN + Transformer 架构），中文准确率约 93~96%，
               支持 GPU 加速（通过 PyTorch），80+ 种语言，pip 即装即用，无系统级依赖

    pdf2image 模块（仍使用）：
      convert_from_bytes(data, dpi=300) → PIL.Image 对象列表，每页一张
        dpi=300：分辨率，越高越清晰但越慢；300 是 OCR 推荐最低值
        底层调用 poppler 的 pdftoppm 命令行工具渲染 PDF 页面
      poppler 路径：D:\\Applications\\poppler\\poppler-26.02.0\\Library\\bin（已配置 PATH）

    EasyOCR 核心 API：
      easyocr.Reader(lang_list, gpu=True)
        lang_list：语言列表，['ch_sim', 'en'] = 简体中文 + 英文
        gpu=True：启用 GPU 加速，需已安装 torch+cu118
        首次运行会自动下载模型文件（约 100MB），需联网，之后缓存在本地
      reader.readtext(image)
        image：numpy 数组（由 np.array(PIL_img) 转换而来）
        返回：列表，每项为 [坐标框, '识别文字', 置信度]
        置信度范围：0.0 ~ 1.0，过滤 < 0.3 的结果可减少噪点和乱码
    """
    # ---- 第一步：导入依赖库 ----
    # pdf2image：将 PDF 每页渲染成 PIL 图片（底层依赖 poppler）
    # easyocr：基于深度学习的 OCR 识别库
    # numpy：将 PIL 图片转为 numpy 数组（EasyOCR 要求此格式）
    # 放在函数内部 import：用到时才检查，没装就报错提示安装
    try:
        from pdf2image import convert_from_bytes
        import easyocr
        import numpy as np
    except ImportError:
        raise ImportError(
            "OCR 依赖缺失，请执行：pip install pdf2image easyocr\n"
            "并确认系统已安装 poppler 且已加入 PATH。"
        )

    # ---- 第二步：把 PDF 的每一页渲染成图片 ----
    # convert_from_bytes(data, dpi=300)：
    #   data：PDF 的字节数据
    #   dpi=300：每英寸 300 像素，OCR 识别推荐最低分辨率，低于此值文字可能模糊
    #   返回值：PIL.Image 对象的列表，每页 PDF 对应列表里的一张图片
    # 底层：调用 poppler 工具（pdftoppm 命令）来渲染 PDF 页面为图片
    try:
        images = convert_from_bytes(data, dpi=300)
    except Exception as e:
        # 失败通常是因为 poppler 没有安装或没有加入系统 PATH
        raise RuntimeError(
            f"pdf2image 转换失败（请确认 poppler 已安装并加入 PATH）：{e}"
        )

    # ---- 第三步：初始化 EasyOCR 识别器 ----
    # ['ch_sim', 'en']：同时支持简体中文和英文识别
    # gpu=True：使用 GPU 加速，显著提升识别速度（需已安装 torch+cu118）
    # 注意：第一次调用时会自动下载模型文件（约 100MB），需联网，请耐心等待
    # 模型下载完成后缓存在本地，后续使用无需重新下载
    reader = easyocr.Reader(['ch_sim', 'en'], gpu=True)

    # ---- 第四步：建空列表，收集每页识别出的文字 ----
    pages_text = []

    # ---- 第五步：对每张图片逐一做 OCR 识别 ----
    # enumerate(images, start=1)：循环，i 是页码（从1开始），img 是 PIL 图片对象
    for i, img in enumerate(images, start=1):
        # PIL Image → numpy 数组
        # EasyOCR 的 readtext() 接受 numpy array，不接受 PIL Image 对象
        # np.array(img) 将 PIL 图片转为形状为 (高, 宽, 3) 的 RGB 数组
        img_array = np.array(img)

        # reader.readtext(img_array)：对这张图片做 OCR 识别
        # 返回格式：[[坐标框, '识别文字', 置信度], ...]
        #   坐标框：[[x1,y1],[x2,y2],[x3,y3],[x4,y4]] 四个角点坐标
        #   识别文字：字符串
        #   置信度：0.0~1.0 的浮点数，越接近 1.0 越准确
        results = reader.readtext(img_array)

        # 过滤低置信度结果（< 0.3 通常是噪点或乱码）
        # result[1]：识别文字（索引1）  result[2]：置信度（索引2）
        lines = [result[1] for result in results if result[2] >= 0.3]

        # 这页有识别内容才加入总列表
        if lines:
            text = "\n".join(lines)
            pages_text.append(f"--- 第 {i} 页（OCR）---\n{text}")

    # 所有页的文字用两个换行拼起来，返回整个扫描件 PDF 的文字
    return "\n\n".join(pages_text)


# ══════════════════════════════════════════════════════════════════════════════
#  DOCX 解析
# ══════════════════════════════════════════════════════════════════════════════

def _parse_docx(data: bytes) -> str:
    """
    DOCX 解析：提取正文段落 + 所有表格。

    docx.Document() 参数：
      io.BytesIO(data)：将字节流包装成文件对象，避免落盘

    Document 对象常用属性：
      doc.paragraphs         → 所有段落列表（按文档顺序）
      doc.tables             → 所有表格列表
      doc.sections           → 节列表（含页眉/页脚/页边距设置）
      doc.styles             → 样式字典（Heading 1/Normal/等）
      doc.core_properties    → 元数据（作者/创建时间/标题）

    Paragraph 对象：
      para.text              → 段落纯文本（合并所有 run）
      para.style.name        → 样式名，如 "Heading 1"/"Normal"
      para.runs              → 格式片段列表（粗体/斜体会分段）
      para.alignment         → 对齐方式

    Table 对象：
      table.rows             → 行列表
      row.cells              → 单元格列表
      cell.text              → 单元格纯文本

    已知局限：
      doc.paragraphs 和 doc.tables 是两个独立列表，
      无法保留段落与表格在文档中原始穿插顺序。
      对 RAG 语义检索场景影响不大，如需精确顺序可用 doc.element 遍历 XML。
    """
    # 导入 python-docx 库的 Document 类

    try:
        from docx import Document  # pip install python-docx
    except ImportError:
        raise ImportError("缺少 python-docx，请执行：pip install python-docx")

    # ---- 第一步：把字节数据包装成"假文件对象"，交给 Document 打开 ----
    # io.BytesIO(data)：把内存里的字节变成一个"假文件"
    #   原因：Document() 要求传入"文件对象"，不接受原始字节
    #   用 BytesIO 包一层就相当于给它一个假文件，省去了先写磁盘再读取的步骤
    # doc：Word 文档对象，可以访问段落和表格
    doc = Document(io.BytesIO(data))

    # ---- 第二步：建空列表，用来收集所有文字片段 ----
    parts = []

    # ---- 第三步：遍历所有段落，提取文字 ----
    # doc.paragraphs：Word 文档里所有段落的列表，按文档从上到下的顺序
    # 每个段落可能是正文、标题、列表项等
    for para in doc.paragraphs:
        # para.text：这个段落的完整文字（已合并段落内所有格式片段）
        # .strip()：去掉首尾空白
        text = para.text.strip()
        # 不为空才加入（空段落通常是排版用的空行，不需要）
        if text:
            parts.append(text)

    # ---- 第四步：遍历所有表格，提取表格内容 ----
    # doc.tables：Word 文档里所有表格的列表
    for table in doc.tables:
        # 先加一个表格标记，让 LLM 知道下面是表格内容
        parts.append("[ 表格 ]")
        # table.rows：表格所有行
        for row in table.rows:
            # row.cells：这行的所有单元格
            # [cell.text.strip() for cell in row.cells]：列表推导式
            #   对每个单元格取文字并去掉空白，收集成一个列表
            cells = [cell.text.strip() for cell in row.cells]
            # 用 " | " 把这行所有单元格的文字拼在一起，表示一行表格数据
            parts.append(" | ".join(cells))

    # 把所有片段用换行拼起来，返回完整文字
    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
#  PPTX 解析
# ══════════════════════════════════════════════════════════════════════════════

def _parse_pptx(data: bytes) -> str:
    """
    PPTX 解析：逐幻灯片提取文本框 + 表格。

    Presentation 对象：
      prs.slides             → 幻灯片列表
      prs.slide_width/height → 幻灯片尺寸（EMU 单位）
      prs.slide_layouts      → 版式列表
      prs.slide_masters      → 母版列表

    Slide 对象：
      slide.shapes           → 所有形状列表
      slide.slide_layout     → 当前版式
      slide.notes_slide      → 备注页

    Shape 对象：
      shape.has_text_frame   → bool，是否包含文本
      shape.has_table        → bool，是否是表格
      shape.has_chart        → bool，是否是图表
      shape.shape_type       → 枚举值（文本框/图片/形状/等）
      shape.name             → 形状名称
      shape.text_frame.paragraphs → 文本框中的段落列表

    已知局限：
      SmartArt 内部文字无法直接提取（需解析 XML）
      图片内文字需 OCR（本函数不处理）
    """
    # 导入 python-pptx 库的 Presentation 类

    try:
        from pptx import Presentation  # pip install python-pptx
    except ImportError:
        raise ImportError("缺少 python-pptx，请执行：pip install python-pptx")

    # ---- 第一步：打开 PPT 文件 ----
    # io.BytesIO(data)：同 DOCX，把字节包装成假文件对象
    # prs：演示文稿对象，包含所有幻灯片
    prs = Presentation(io.BytesIO(data))

    # ---- 第二步：建空列表，收集每张幻灯片的文字 ----
    slides_text = []

    # ---- 第三步：逐张幻灯片处理 ----
    # enumerate(prs.slides, start=1)：循环，slide_num 是幻灯片编号，slide 是幻灯片对象
    for slide_num, slide in enumerate(prs.slides, start=1):

        # 这张幻灯片的文字片段列表
        parts = []

        # ---- 遍历幻灯片里的每个"形状" ----
        # slide.shapes：幻灯片上所有元素的列表（文字框、图片、表格、形状等都叫 shape）
        for shape in slide.shapes:

            # 判断：这个形状有没有文字框？
            if shape.has_text_frame:
                # shape.text_frame.paragraphs：文字框里所有段落的列表
                for para in shape.text_frame.paragraphs:
                    # para.runs：段落内所有"格式片段"的列表
                    # 为什么要用 runs？因为 PPT 里同一段文字的不同部分可能有不同格式（粗体/斜体/颜色），
                    # 每种格式变化就会分成一个 run 存储
                    # "".join(run.text for run in para.runs)：把所有片段的文字拼在一起，还原完整文字
                    text = "".join(run.text for run in para.runs).strip()
                    # 不为空才加入
                    if text:
                        parts.append(text)

            # 判断：这个形状是不是表格？
            if shape.has_table:
                parts.append("[ 表格 ]")
                # shape.table.rows：表格所有行
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    parts.append(" | ".join(cells))

        # 这张幻灯片有内容才加入总列表
        if parts:
            # 加上幻灯片编号标记，帮助 LLM 知道内容来自哪张幻灯片
            slides_text.append(
                f"--- 幻灯片 {slide_num} ---\n" + "\n".join(parts)
            )

    # 所有幻灯片用两个换行拼起来，返回
    return "\n\n".join(slides_text)


# ══════════════════════════════════════════════════════════════════════════════
#  XLSX 解析
# ══════════════════════════════════════════════════════════════════════════════

def _parse_xlsx(data: bytes) -> str:
    """
    XLSX 解析：遍历所有工作表，转为表格文本。

    openpyxl.load_workbook() 参数：
      read_only=True   → 只读模式，跳过样式/公式计算，内存占用更小
      data_only=True   → 返回单元格的计算结果值，而非公式字符串
                         （不加此参数，含 =SUM(A1:A3) 的单元格返回字符串 "=SUM(A1:A3)"）

    Workbook 对象：
      wb.sheetnames              → 所有工作表名称列表，如 ['Sheet1', '汇总']
      wb[sheet_name]             → 按名称获取工作表
      wb.active                  → 活动工作表

    Worksheet 对象：
      ws.iter_rows(values_only=True) → 逐行迭代，每行返回值元组（不含 Cell 对象）
      ws.max_row                     → 有数据的最大行号
      ws.max_column                  → 有数据的最大列号
      ws.cell(row=1, column=1).value → 指定单元格的值
      ws.dimensions                  → 数据范围字符串，如 "A1:H100"

    全空行处理：
      any(c.strip() for c in cells)：若该行所有单元格均为空则跳过，
      避免输出大量无意义的 " |  |  | " 分隔行。
    """
    # 导入 openpyxl 库

    try:
        import openpyxl  # pip install openpyxl
    except ImportError:
        raise ImportError("缺少 openpyxl，请执行：pip install openpyxl")

    # ---- 第一步：打开 Excel 文件 ----
    # io.BytesIO(data)：把字节包装成假文件对象（同 DOCX/PPTX）
    # read_only=True：只读模式，跳过样式计算，节省内存，速度更快
    # data_only=True：读取单元格里的"计算结果值"，而不是公式字符串
    #   举例：单元格里存的是 =SUM(A1:A3)，不加此参数就会返回字符串 "=SUM(A1:A3)"
    #         加了之后返回计算结果，比如 150
    # wb：工作簿对象，包含所有工作表
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)

    # ---- 第二步：建空列表，收集每个工作表的文字 ----
    sheets_text = []

    # ---- 第三步：逐个工作表处理 ----
    # wb.sheetnames：所有工作表名称的列表，比如 ['Sheet1', '汇总', '明细']
    for sheet_name in wb.sheetnames:
        # 用名称取出这个工作表对象
        ws = wb[sheet_name]

        # 这个工作表的行数据列表
        rows_text = []

        # ---- 遍历这个工作表的每一行 ----
        # ws.iter_rows(values_only=True)：按行遍历，每行返回一个元组，里面是单元格的值
        #   values_only=True：直接拿值，不拿 Cell 对象，更简洁高效
        for row in ws.iter_rows(values_only=True):
            # 列表推导式：把这行每个单元格的值转成字符串
            # str(cell) if cell is not None else ""：
            #   单元格是 None（空格子）就用空字符串代替，否则转成字符串
            cells = [str(cell) if cell is not None else "" for cell in row]

            # any(c.strip() for c in cells)：
            #   检查这行是否至少有一个非空的单元格
            #   any()：只要有一个 True 就返回 True
            #   如果这行全是空格子，就跳过，不加入结果（避免输出大量空行）
            if any(c.strip() for c in cells):
                # 用 " | " 把这行所有单元格的值拼在一起
                rows_text.append(" | ".join(cells))

        # 这个工作表有数据才加入总列表
        if rows_text:
            # 加上工作表名称标记
            sheets_text.append(
                f"--- 工作表：{sheet_name} ---\n" + "\n".join(rows_text)
            )

    # ---- 第四步：关闭工作簿，释放内存 ----
    wb.close()

    # 所有工作表用两个换行拼起来，返回
    return "\n\n".join(sheets_text)


# ══════════════════════════════════════════════════════════════════════════════
#  CSV 解析
# ══════════════════════════════════════════════════════════════════════════════

def _parse_csv(data: bytes) -> str:
    """
    CSV 解析：内置 csv 模块，自动检测编码。

    csv 模块（Python 内置，无需安装）：
      csv.reader(f)         → 迭代器，每次返回一行的列表  ← 本函数使用
      csv.writer(f)         → 写入器，writerow([...]) 写一行
      csv.DictReader(f)     → 以首行为键，每行返回字典（适合有表头的 CSV）
      csv.DictWriter(f, fieldnames=[...]) → 按字典写入

    io.StringIO(text)：
      将字符串包装成文件对象，供 csv.reader 迭代，
      避免将数据写入临时文件。

    全空行处理：
      any(cell.strip() for cell in row)：跳过行内全部为空的行。
    """
    # ---- 第一步：先把字节转成字符串，解决编码问题 ----
    # _parse_txt(data)：复用 TXT 解析函数，它会自动尝试 utf-8/gbk/latin-1 等编码
    # CSV 本质上也是文本文件，只是有特定格式（逗号分隔），先解码是必须的

    text = _parse_txt(data)

    # ---- 第二步：把文字字符串包装成"假文件对象"，交给 csv.reader 读取 ----
    # io.StringIO(text)：和 BytesIO 类似，但包装的是字符串（不是字节）
    # csv.reader(f)：CSV 读取器，它知道如何处理逗号分隔、引号包裹等 CSV 格式规则
    #   返回一个迭代器，每次 next 给出一行的列表，比如 ["张三", "18", "北京"]
    reader = csv.reader(io.StringIO(text))

    # ---- 第三步：建空列表，收集每行数据 ----
    rows = []

    # ---- 第四步：遍历每一行 ----
    for row in reader:
        # any(cell.strip() for cell in row)：判断这行有没有非空内容
        # 空行（比如文件末尾多余的空行）会被跳过
        if any(cell.strip() for cell in row):
            # 用 " | " 把这行所有字段的值拼在一起
            # row 已经是列表，比如 ["张三", "18", "北京"]，join 后变成 "张三 | 18 | 北京"
            rows.append(" | ".join(row))

    # 所有行用换行拼起来，返回
    return "\n".join(rows)


# ══════════════════════════════════════════════════════════════════════════════
#  内部工具函数
# ══════════════════════════════════════════════════════════════════════════════

def _to_bytes(source: Source) -> bytes:
    """
    将路径或字节流统一转为 bytes。

    isinstance(source, (bytes, bytearray))：
      检查是否已经是字节类型，是则直接返回，避免重复转换。
      bytearray 也一并处理（可变字节序列，语义相同）。

    open(source, "rb")：
      "rb" = read binary，以二进制模式读取，
      保留原始字节不做任何编码转换，由各解析器自行处理编码。

    with ... as f：
      上下文管理器，无论正常退出还是异常，都会自动调用 f.close()，
      避免文件句柄泄漏。
    """
    # 判断：传进来的 source 是不是已经是"字节"类型（bytes 或 bytearray）？
    # isinstance() 是 Python 内置函数，用来检查变量是不是某种类型
    # bytes 和 bytearray 都是字节类型，两种都接受
    if isinstance(source, (bytes, bytearray)):
        # 已经是字节了，直接把它转成标准 bytes 返回，不用做任何事
        # 为什么还要 bytes(source)？因为传进来的可能是 bytearray（可变字节），
        # 统一转成 bytes（不可变字节），后续处理更安全
        return bytes(source)

    # 走到这里说明 source 是文件路径（字符串或 Path 对象）
    # open(source, "rb")：以二进制读取模式打开文件
    #   "r" = read（读取）   "b" = binary（二进制）
    #   二进制模式不会做任何编码转换，保留文件原始字节，由各解析函数自己处理编码
    # with ... as f：上下文管理器
    #   with 块结束时，不管是正常结束还是报错，都会自动调用 f.close() 关闭文件
    #   避免忘记关文件导致"文件句柄泄漏"（文件被占用无法删除等问题）
    with open(source, "rb") as f:
        # f.read()：把文件里所有内容一次性读出来，返回 bytes
        return f.read()


# ══════════════════════════════════════════════════════════════════════════════
#  命令行快速测试入口
#  用法：python -m app.rag.doc_parser <文件路径>
#  示例：python -m app.rag.doc_parser report.pdf
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法：python -m app.rag.doc_parser <文件路径>")
        print("示例：python -m app.rag.doc_parser report.pdf")
        sys.exit(1)

    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"文件不存在：{file_path}")
        sys.exit(1)

    print(f"正在解析：{file_path}")
    result = parse_document(file_path, os.path.basename(file_path), max_chars=-1)
    print("=" * 60)
    print(result[:3000])
    if len(result) > 3000:
        print(f"\n... （共 {len(result)} 字符，仅展示前 3000）")
    print("=" * 60)
    print(f"解析完成，共提取 {len(result)} 个字符")
