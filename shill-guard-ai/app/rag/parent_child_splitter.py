"""父子切分：条级 Child + 节/邻条 Parent（结构优先）。

检索只索引 Child；生成侧在命中后回填对应 Parent。
不使用固定 500/50 滑动窗口作为父子基础。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ── 尺寸约束（方案约定）──────────────────────────────────────────────
CHILD_LONG_ARTICLE_THRESHOLD = 400  # 超过则条内再切子片段
CHILD_MIN_CHARS = 40                # 避免过碎（超长条分项除外）
CHILD_STRUCT_TARGET_MIN = 150
CHILD_STRUCT_TARGET_MAX = 400
PARENT_TARGET_MIN = 600
PARENT_TARGET_MAX = 1200
PARENT_HARD_MAX = 1500
PARENT_STRUCT_TARGET_MIN = 800
PARENT_STRUCT_TARGET_MAX = 1200
SHORT_DOC_THRESHOLD = 1000          # 超短文件整篇作为 child=parent
# 百炼 text-embedding 输入上限 8192；按字符严格留余量（避免 token 膨胀踩线）
EMBED_MAX_CHARS = 4000

_CN_NUM = r"零一二三四五六七八九十百千两〇Oo0-9"

# 法条起始：第X条 / 第X条之Y；后接空白或冒号；排除「本法第X条」类引用
ARTICLE_RE = re.compile(
    rf"(?<![法条款项编章节及其和与于见按依的本该前此])"
    rf"第(?P<num>[{_CN_NUM}]+)条(?:之(?P<sub>[{_CN_NUM}]+))?"
    rf"(?=[　\s：:]|$)",
)

CHAPTER_RE = re.compile(
    rf"(?m)^[　 \t]*(?:\#{{1,6}}[　 \t]*)?第(?P<num>[{_CN_NUM}]+)章"
    rf"(?P<title>[^\n]*)"
)
SECTION_RE = re.compile(
    rf"(?m)^[　 \t]*(?:\#{{1,6}}[　 \t]*)?第(?P<num>[{_CN_NUM}]+)节"
    rf"(?P<title>[^\n]*)"
)
PART_RE = re.compile(
    rf"(?m)^[　 \t]*(?:\#{{1,6}}[　 \t]*)?第(?P<num>[{_CN_NUM}]+)编"
    rf"(?P<title>[^\n]*)"
)

# 条内分项：（一）（二）或 一、
ITEM_RE = re.compile(r"(?=(?:（[一二三四五六七八九十百]+）|[（(][0-9]+[）)]))")
H1_RE = re.compile(r"(?m)^#\s+(.+)$")
H2_RE = re.compile(r"(?m)^(##)\s+(.+)$")
H3_RE = re.compile(r"(?m)^(###)\s+(.+)$")


@dataclass
class ChildChunk:
    child_id: str
    text: str
    parent_id: str
    law_name: str
    article_no: str
    chapter: str
    section: str
    source_file: str
    strategy: str
    start: int = 0
    end: int = 0

    def metadata(self) -> dict:
        """Chroma/ES 可用的扁平元数据。"""
        return {
            "source": self.source_file,
            "child_id": self.child_id,
            "parent_id": self.parent_id,
            "law_name": self.law_name,
            "article_no": self.article_no,
            "chapter": self.chapter,
            "section": self.section,
            "strategy": self.strategy,
        }


@dataclass
class ParentChunk:
    parent_id: str
    text: str
    law_name: str
    source_file: str
    chapter: str = ""
    section: str = ""
    article_nos: list[str] = field(default_factory=list)
    strategy: str = ""

    def to_store_record(self) -> dict:
        return asdict(self)


@dataclass
class SplitResult:
    children: list[ChildChunk]
    parents: list[ParentChunk]

    def child_texts(self) -> list[str]:
        return [c.text for c in self.children]


@dataclass
class _Article:
    article_no: str
    text: str
    start: int
    end: int
    chapter: str
    section: str
    part: str


def extract_law_name(text: str, source_file: str) -> str:
    m = H1_RE.search(text)
    if m:
        return m.group(1).strip()
    stem = Path(source_file).stem
    for prefix in (
        "法律_",
        "行政法规_",
        "有关决定_",
        "法律解释_",
        "修改、废止的决定_",
        "监察法规_",
        "地方性法规_",
    ):
        if stem.startswith(prefix):
            return stem[len(prefix) :]
    return stem


def _stable_id(*parts: str) -> str:
    raw = "::".join(parts)
    if len(raw) <= 200 and all(ord(c) < 128 or c.isalnum() or c in "_-.:/" for c in raw):
        # 含中文时改用 hash，避免个别后端对 id 字符集挑剔
        if any(ord(c) > 127 for c in raw):
            h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]
            safe = re.sub(r"[^\w.\-]+", "_", parts[0])[:40]
            return f"{safe}::{h}"
        return raw
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]
    safe = re.sub(r"[^\w.\-]+", "_", parts[0])[:40]
    return f"{safe}::{h}"


def _strip_trailing_structure(block: str) -> str:
    """去掉条末误吞的章/节/编标题。"""
    return re.sub(
        rf"(?s)\n[　 \t]*(?:\#{{1,6}}[　 \t]*)?第[{_CN_NUM}]+[章节编][^\n]*\s*$",
        "",
        block,
    ).strip()


def _assign_structure_context(text: str, positions: list[int]) -> list[tuple[str, str, str]]:
    """为每个 position 计算最近的 编/章/节 上下文。"""
    markers: list[tuple[int, str, str]] = []
    for m in PART_RE.finditer(text):
        title = (m.group("title") or "").strip()
        label = f"第{m.group('num')}编" + (f"　{title}" if title else "")
        markers.append((m.start(), "part", label))
    for m in CHAPTER_RE.finditer(text):
        title = (m.group("title") or "").strip()
        label = f"第{m.group('num')}章" + (f"　{title}" if title else "")
        markers.append((m.start(), "chapter", label))
    for m in SECTION_RE.finditer(text):
        title = (m.group("title") or "").strip()
        label = f"第{m.group('num')}节" + (f"　{title}" if title else "")
        markers.append((m.start(), "section", label))
    markers.sort(key=lambda x: x[0])

    out: list[tuple[str, str, str]] = []
    for pos in positions:
        part = chapter = section = ""
        for mpos, kind, label in markers:
            if mpos > pos:
                break
            if kind == "part":
                part = label
                chapter = ""
                section = ""
            elif kind == "chapter":
                chapter = label
                section = ""
            else:
                section = label
        out.append((part, chapter, section))
    return out


def _parse_articles(text: str) -> list[_Article]:
    matches = list(ARTICLE_RE.finditer(text))
    if not matches:
        return []

    starts = [m.start() for m in matches]
    contexts = _assign_structure_context(text, starts)
    articles: list[_Article] = []
    for i, m in enumerate(matches):
        num = m.group("num")
        sub = m.group("sub")
        article_no = f"第{num}条" + (f"之{sub}" if sub else "")
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw = _strip_trailing_structure(text[m.start() : end])
        if not raw:
            continue
        part, chapter, section = contexts[i]
        articles.append(
            _Article(
                article_no=article_no,
                text=raw,
                start=m.start(),
                end=m.start() + len(raw),
                chapter=chapter,
                section=section,
                part=part,
            )
        )
    return articles


def _split_long_article(article_text: str) -> list[str]:
    """单条 >400 字时按分项/句号切；尽量不产生 <40 字碎片（分项标记段除外）。"""
    # 优先按（一）（二）分项
    parts = [p for p in ITEM_RE.split(article_text) if p and p.strip()]
    if len(parts) <= 1:
        # 按句号切，保留句号
        parts = re.split(r"(?<=。)", article_text)
        parts = [p for p in parts if p and p.strip()]

    if len(parts) <= 1:
        return [article_text]

    merged: list[str] = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        is_item = bool(re.match(r"^[（(][一二三四五六七八九十百0-9]+[）)]", p))
        if not buf:
            buf = p
            continue
        if len(buf) < CHILD_MIN_CHARS and not is_item:
            buf += p
            continue
        if len(buf) + len(p) <= CHILD_LONG_ARTICLE_THRESHOLD:
            # 继续拼到接近阈值，减少过碎
            if len(buf) < CHILD_STRUCT_TARGET_MIN:
                buf += p
                continue
        merged.append(buf)
        buf = p
    if buf:
        if merged and len(buf) < CHILD_MIN_CHARS and not re.match(
            r"^[（(][一二三四五六七八九十百0-9]+[）)]", buf
        ):
            merged[-1] += buf
        else:
            merged.append(buf)

    # 若切完仍只有一块或切得无意义，返回原文
    if len(merged) <= 1:
        return [article_text]
    return merged


def _join_articles(arts: list[_Article]) -> str:
    return "\n\n".join(a.text.strip() for a in arts if a.text.strip())


def _neighbor_parent(articles: list[_Article], idx: int) -> tuple[str, list[str]]:
    """回退：本条 ±1。"""
    lo = max(0, idx - 1)
    hi = min(len(articles) - 1, idx + 1)
    selected = articles[lo : hi + 1]
    text = _join_articles(selected)
    if len(text) > PARENT_HARD_MAX:
        # 超限：本条 + 最近邻（优先更短的一侧）
        cur = articles[idx]
        cands: list[_Article] = [cur]
        neighbors = []
        if idx > 0:
            neighbors.append(articles[idx - 1])
        if idx + 1 < len(articles):
            neighbors.append(articles[idx + 1])
        neighbors.sort(key=lambda a: abs(len(a.text) - 0))
        for n in neighbors:
            trial = _join_articles(cands + [n] if n.start > cur.start else [n] + cands)
            # 保持文档顺序
            ordered = sorted(cands + [n], key=lambda a: a.start)
            trial = _join_articles(ordered)
            if len(trial) <= PARENT_HARD_MAX:
                cands = ordered
                text = trial
            else:
                break
        text = _join_articles(cands)
        selected = cands
    return text, [a.article_no for a in selected]


def _scope_indices(articles: list[_Article], idx: int) -> list[int]:
    cur = articles[idx]
    if cur.section:
        return [
            i
            for i, a in enumerate(articles)
            if a.section == cur.section and a.chapter == cur.chapter
        ]
    if cur.chapter:
        return [i for i, a in enumerate(articles) if a.chapter == cur.chapter]
    return list(range(len(articles)))


def _build_article_parent(articles: list[_Article], idx: int) -> tuple[str, list[str], str]:
    """构建某条的 Parent 文本。返回 (text, article_nos, strategy)。"""
    cur = articles[idx]
    has_structure = bool(cur.section or cur.chapter)

    if not has_structure:
        text, nos = _neighbor_parent(articles, idx)
        return text, nos, "neighbor_pm1"

    scope = _scope_indices(articles, idx)
    pos = scope.index(idx)
    left = right = pos

    def span_text(l: int, r: int) -> str:
        return _join_articles([articles[scope[j]] for j in range(l, r + 1)])

    # 在同节/章内扩展到目标 600～1200，硬上限 1500
    while True:
        cur_len = len(span_text(left, right))
        if cur_len >= PARENT_TARGET_MIN:
            break
        options: list[tuple[str, int, int]] = []
        if left > 0:
            new_len = len(span_text(left - 1, right))
            if new_len <= PARENT_HARD_MAX:
                options.append(("L", new_len, left - 1))
        if right < len(scope) - 1:
            new_len = len(span_text(left, right + 1))
            if new_len <= PARENT_HARD_MAX:
                options.append(("R", new_len, right + 1))
        if not options:
            break
        mid = (PARENT_TARGET_MIN + PARENT_TARGET_MAX) // 2
        # 优先扩展后更接近中位目标的一侧
        best = min(options, key=lambda x: (abs(x[1] - mid), x[1]))
        if best[0] == "L":
            left = best[2]
        else:
            right = best[2]
        # 已进入目标区间上限附近则停
        if len(span_text(left, right)) >= PARENT_TARGET_MAX:
            break

    text = span_text(left, right)

    # 同节仍过短：再按绝对邻条补（覆盖前款/定义在前条）
    if len(text) < PARENT_TARGET_MIN:
        abs_idxs = [scope[j] for j in range(left, right + 1)]
        lo, hi = min(abs_idxs), max(abs_idxs)
        while len(text) < PARENT_TARGET_MIN:
            added = False
            if lo > 0:
                ordered = articles[lo - 1 : hi + 1]
                trial = _join_articles(ordered)
                if len(trial) <= PARENT_HARD_MAX:
                    lo -= 1
                    text = trial
                    added = True
            if len(text) >= PARENT_TARGET_MIN:
                break
            if hi < len(articles) - 1:
                ordered = articles[lo : hi + 2]
                trial = _join_articles(ordered)
                if len(trial) <= PARENT_HARD_MAX:
                    hi += 1
                    text = trial
                    added = True
            if not added:
                break
        nos = [a.article_no for a in articles[lo : hi + 1]]
        return text, nos, "section_then_neighbor"

    if len(text) > PARENT_HARD_MAX:
        text, nos = _neighbor_parent(articles, idx)
        return text, nos, "hard_cap_neighbor"

    nos = [articles[scope[j]].article_no for j in range(left, right + 1)]
    return text, nos, "section_window"


def _split_by_articles(text: str, source_file: str, law_name: str) -> SplitResult | None:
    articles = _parse_articles(text)
    if len(articles) < 1:
        return None
    # 至少 1 条才走主路径；只有「条」字样极少时仍走
    if len(articles) == 1 and len(articles[0].text) < 40 and len(text) > SHORT_DOC_THRESHOLD:
        # 疑似误检
        return None

    parents: list[ParentChunk] = []
    children: list[ChildChunk] = []
    parent_by_article_idx: dict[int, str] = {}

    stem = Path(source_file).stem
    for idx, art in enumerate(articles):
        parent_text, article_nos, p_strategy = _build_article_parent(articles, idx)
        parent_id = _stable_id(stem, "parent", art.article_no, str(idx))
        parent_by_article_idx[idx] = parent_id
        parents.append(
            ParentChunk(
                parent_id=parent_id,
                text=parent_text,
                law_name=law_name,
                source_file=source_file,
                chapter=art.chapter,
                section=art.section,
                article_nos=article_nos,
                strategy=p_strategy,
            )
        )

        if len(art.text) > CHILD_LONG_ARTICLE_THRESHOLD:
            parts = _split_long_article(art.text)
            for pi, part in enumerate(parts):
                child_id = _stable_id(stem, "child", art.article_no, f"p{pi}")
                children.append(
                    ChildChunk(
                        child_id=child_id,
                        text=part,
                        parent_id=parent_id,
                        law_name=law_name,
                        article_no=art.article_no,
                        chapter=art.chapter,
                        section=art.section,
                        source_file=source_file,
                        strategy="article_part",
                        start=art.start,
                        end=art.end,
                    )
                )
        else:
            child_id = _stable_id(stem, "child", art.article_no, str(idx))
            children.append(
                ChildChunk(
                    child_id=child_id,
                    text=art.text,
                    parent_id=parent_id,
                    law_name=law_name,
                    article_no=art.article_no,
                    chapter=art.chapter,
                    section=art.section,
                    source_file=source_file,
                    strategy="article",
                    start=art.start,
                    end=art.end,
                )
            )

    return SplitResult(children=children, parents=parents)


def _iter_md_sections(text: str) -> list[tuple[str, str, int, int, str]]:
    """返回 [(level, title, start, end, block)]，level 为 ## 或 ###。"""
    headers = []
    for m in re.finditer(r"(?m)^(#{2,3})\s+(.+)$", text):
        headers.append((m.start(), m.group(1), m.group(2).strip(), m.end()))
    if not headers:
        return []
    sections: list[tuple[str, str, int, int, str]] = []
    for i, (pos, level, title, _content_start) in enumerate(headers):
        end = headers[i + 1][0] if i + 1 < len(headers) else len(text)
        block = text[pos:end].strip()
        sections.append((level, title, pos, end, block))
    return sections


def _pack_blocks(blocks: list[str], target_min: int, target_max: int) -> list[str]:
    """把小块合并到 [target_min, target_max] 附近。"""
    if not blocks:
        return []
    out: list[str] = []
    buf = ""
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        if not buf:
            buf = b
            continue
        if len(buf) < target_min or len(buf) + 2 + len(b) <= target_max:
            buf = buf + "\n\n" + b
            continue
        out.append(buf)
        buf = b
    if buf:
        if out and len(buf) < CHILD_MIN_CHARS:
            out[-1] = out[-1] + "\n\n" + buf
        else:
            out.append(buf)
    return out


def _structure_aware_slices(text: str, size_min: int = 300, size_max: int = 400) -> list[str]:
    """无条款结构时：按空行/标题块做结构感知切分。"""
    # 先按空行分段
    paras = re.split(r"\n\s*\n+", text.strip())
    paras = [p.strip() for p in paras if p.strip()]
    if not paras:
        return [text.strip()] if text.strip() else []

    chunks: list[str] = []
    buf = ""
    for p in paras:
        if not buf:
            buf = p
            continue
        if len(buf) < size_min or len(buf) + 2 + len(p) <= size_max:
            buf = buf + "\n\n" + p
        else:
            chunks.append(buf)
            buf = p
    if buf:
        if chunks and len(buf) < CHILD_MIN_CHARS:
            chunks[-1] = chunks[-1] + "\n\n" + buf
        else:
            chunks.append(buf)

    # 单段仍然过长：按句子再切
    final: list[str] = []
    for c in chunks:
        if len(c) <= size_max * 2:
            final.append(c)
            continue
        sents = re.split(r"(?<=[。！？；])", c)
        final.extend(_pack_blocks([s for s in sents if s.strip()], size_min, size_max))
    return final or ([text.strip()] if text.strip() else [])


def _split_markdown_platform(text: str, source_file: str, law_name: str) -> SplitResult | None:
    """平台规范：### 为 child，所属 ## 为 parent；无 ### 时对 ## 内结构切 child。"""
    sections = _iter_md_sections(text)
    if not sections:
        return None
    has_h2 = any(s[0] == "##" for s in sections)
    has_h3 = any(s[0] == "###" for s in sections)
    if not (has_h2 or has_h3):
        return None

    stem = Path(source_file).stem
    children: list[ChildChunk] = []
    parents: list[ParentChunk] = []

    # 建立 ## 块：每个 ## 到下一 ## 之前
    h2_blocks: list[tuple[str, str, int, int]] = []
    for i, (level, title, start, end, block) in enumerate(sections):
        if level != "##":
            continue
        # end 应扩到下一个 ##
        real_end = end
        for j in range(i + 1, len(sections)):
            if sections[j][0] == "##":
                real_end = sections[j][2]
                break
        else:
            real_end = len(text)
        h2_blocks.append((title, text[start:real_end].strip(), start, real_end))

    if not h2_blocks and has_h3:
        # 只有 ###：每个 ### 自己是 child，parent 合并相邻到 800～1200
        h3s = [(t, b, s, e) for (lv, t, s, e, b) in sections if lv == "###"]
        child_texts = []
        for title, block, start, end in h3s:
            body = block
            if len(body) > CHILD_STRUCT_TARGET_MAX:
                # 大 ### 再按列表项分组
                items = re.split(r"(?=\n- )", body)
                child_texts.extend(
                    (title, c, start, end)
                    for c in _pack_blocks(
                        [x.strip() for x in items if x.strip()],
                        CHILD_STRUCT_TARGET_MIN,
                        CHILD_STRUCT_TARGET_MAX,
                    )
                )
            else:
                child_texts.append((title, body, start, end))

        # parents: 相邻 child 合并
        packed_parents = _pack_blocks(
            [c[1] for c in child_texts],
            PARENT_STRUCT_TARGET_MIN,
            PARENT_STRUCT_TARGET_MAX,
        )
        # 映射每个 child 到包含它的 parent（简化：按顺序贪心归属）
        p_objs = []
        for pi, pt in enumerate(packed_parents):
            if len(pt) > PARENT_HARD_MAX:
                pt = pt[:PARENT_HARD_MAX]
            pid = _stable_id(stem, "parent", f"md{pi}")
            p_objs.append(
                ParentChunk(
                    parent_id=pid,
                    text=pt,
                    law_name=law_name,
                    source_file=source_file,
                    strategy="md_h3_merged",
                )
            )
            parents.append(p_objs[-1])

        # 为每个 child 找第一个包含其文本的 parent
        for ci, (title, ctext, start, end) in enumerate(child_texts):
            parent_id = p_objs[0].parent_id if p_objs else _stable_id(stem, "parent", "0")
            for p in p_objs:
                if ctext[:80] in p.text or ctext in p.text:
                    parent_id = p.parent_id
                    break
            children.append(
                ChildChunk(
                    child_id=_stable_id(stem, "child", f"h3_{ci}"),
                    text=ctext,
                    parent_id=parent_id,
                    law_name=law_name,
                    article_no="",
                    chapter=title,
                    section=title,
                    source_file=source_file,
                    strategy="markdown_h3",
                    start=start,
                    end=end,
                )
            )
        return SplitResult(children=children, parents=parents)

    for hi, (h2_title, h2_text, h2_start, h2_end) in enumerate(h2_blocks):
        parent_id = _stable_id(stem, "parent", f"h2_{hi}", h2_title)
        parent_body = h2_text
        if len(parent_body) > PARENT_HARD_MAX:
            # 硬上限：保留标题 + 截断（避免整章过大；平台规范通常不大）
            parent_body = parent_body[:PARENT_HARD_MAX]
        parents.append(
            ParentChunk(
                parent_id=parent_id,
                text=parent_body,
                law_name=law_name,
                source_file=source_file,
                chapter=h2_title,
                section=h2_title,
                strategy="markdown_h2",
            )
        )

        # 找该 ## 下的 ###
        inner_h3 = [
            (t, b, s, e)
            for (lv, t, s, e, b) in sections
            if lv == "###" and h2_start <= s < h2_end
        ]
        if inner_h3:
            for ci, (title, block, start, end) in enumerate(inner_h3):
                pieces = [block]
                if len(block) > CHILD_STRUCT_TARGET_MAX:
                    items = re.split(r"(?=\n- )", block)
                    pieces = _pack_blocks(
                        [x.strip() for x in items if x.strip()],
                        CHILD_STRUCT_TARGET_MIN,
                        CHILD_STRUCT_TARGET_MAX,
                    )
                for pi, piece in enumerate(pieces):
                    children.append(
                        ChildChunk(
                            child_id=_stable_id(stem, "child", f"h2{hi}_h3{ci}_{pi}"),
                            text=piece,
                            parent_id=parent_id,
                            law_name=law_name,
                            article_no="",
                            chapter=h2_title,
                            section=title,
                            source_file=source_file,
                            strategy="markdown_h3",
                            start=start,
                            end=end,
                        )
                    )
        else:
            # ## 下无 ###：结构感知切 child，共用该 ## parent
            body = re.sub(r"^##\s+.+\n?", "", h2_text, count=1).strip()
            pieces = _structure_aware_slices(
                body, CHILD_STRUCT_TARGET_MIN, CHILD_STRUCT_TARGET_MAX
            )
            if not pieces:
                pieces = [h2_text]
            for pi, piece in enumerate(pieces):
                children.append(
                    ChildChunk(
                        child_id=_stable_id(stem, "child", f"h2{hi}_{pi}"),
                        text=piece,
                        parent_id=parent_id,
                        law_name=law_name,
                        article_no="",
                        chapter=h2_title,
                        section=h2_title,
                        source_file=source_file,
                        strategy="markdown_h2_part",
                        start=h2_start,
                        end=h2_end,
                    )
                )

    if not children:
        return None
    return SplitResult(children=children, parents=parents)


def _split_structure_generic(text: str, source_file: str, law_name: str) -> SplitResult:
    """短决定/无条款：300～400 child；相邻合并 800～1200 parent。"""
    stem = Path(source_file).stem
    child_texts = _structure_aware_slices(
        text, size_min=300, size_max=400
    )
    if not child_texts:
        child_texts = [text.strip()]

    children: list[ChildChunk] = []
    parents: list[ParentChunk] = []

    # 为每个 child 建 parent：向两侧合并到 800～1200
    for i, ctext in enumerate(child_texts):
        lo = hi = i
        parent_text = ctext
        while len(parent_text) < PARENT_STRUCT_TARGET_MIN:
            expanded = False
            if lo > 0:
                trial = child_texts[lo - 1] + "\n\n" + parent_text
                if len(trial) <= PARENT_HARD_MAX:
                    lo -= 1
                    parent_text = trial
                    expanded = True
            if len(parent_text) >= PARENT_STRUCT_TARGET_MIN:
                break
            if hi < len(child_texts) - 1:
                trial = parent_text + "\n\n" + child_texts[hi + 1]
                if len(trial) <= PARENT_HARD_MAX:
                    hi += 1
                    parent_text = trial
                    expanded = True
            if not expanded:
                break
            if len(parent_text) >= PARENT_STRUCT_TARGET_MAX:
                break

        if len(parent_text) > PARENT_HARD_MAX:
            parent_text = parent_text[:PARENT_HARD_MAX]

        parent_id = _stable_id(stem, "parent", f"g{i}")
        parents.append(
            ParentChunk(
                parent_id=parent_id,
                text=parent_text,
                law_name=law_name,
                source_file=source_file,
                strategy="structure_merge",
            )
        )
        children.append(
            ChildChunk(
                child_id=_stable_id(stem, "child", f"g{i}"),
                text=ctext,
                parent_id=parent_id,
                law_name=law_name,
                article_no="",
                chapter="",
                section="",
                source_file=source_file,
                strategy="structure",
                start=0,
                end=0,
            )
        )
    return SplitResult(children=children, parents=parents)


def _split_whole_doc(text: str, source_file: str, law_name: str) -> SplitResult:
    stem = Path(source_file).stem
    parent_id = _stable_id(stem, "parent", "whole")
    child_id = _stable_id(stem, "child", "whole")
    body = text.strip()
    return SplitResult(
        children=[
            ChildChunk(
                child_id=child_id,
                text=body,
                parent_id=parent_id,
                law_name=law_name,
                article_no="",
                chapter="",
                section="",
                source_file=source_file,
                strategy="whole_doc",
                start=0,
                end=len(body),
            )
        ],
        parents=[
            ParentChunk(
                parent_id=parent_id,
                text=body,
                law_name=law_name,
                source_file=source_file,
                strategy="whole_doc",
            )
        ],
    )


def _hard_split_by_length(text: str, max_chars: int = EMBED_MAX_CHARS) -> list[str]:
    """最终兜底：保证单段不超过 embedding 上限。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    pieces = re.split(r"(?<=\n)|(?<=[。！？；])", text)
    out: list[str] = []
    buf = ""
    for p in pieces:
        if not p:
            continue
        if len(p) > max_chars:
            if buf:
                out.append(buf)
                buf = ""
            for i in range(0, len(p), max_chars):
                chunk = p[i : i + max_chars].strip()
                if chunk:
                    out.append(chunk)
            continue
        if not buf:
            buf = p
        elif len(buf) + len(p) <= max_chars:
            buf += p
        else:
            out.append(buf)
            buf = p
    if buf:
        out.append(buf)
    return out or [text[:max_chars]]


def _enforce_child_embed_limit(result: SplitResult) -> SplitResult:
    """把超长 child 再切，仍挂到原 parent_id（满足百炼 ≤8192）。"""
    if not result.children:
        return result
    new_children: list[ChildChunk] = []
    for c in result.children:
        parts = _hard_split_by_length(c.text, EMBED_MAX_CHARS)
        if len(parts) == 1:
            c.text = parts[0]
            new_children.append(c)
            continue
        for i, part in enumerate(parts):
            new_children.append(
                ChildChunk(
                    child_id=_stable_id(c.child_id, f"emb{i}"),
                    text=part,
                    parent_id=c.parent_id,
                    law_name=c.law_name,
                    article_no=c.article_no,
                    chapter=c.chapter,
                    section=c.section,
                    source_file=c.source_file,
                    strategy=(
                        c.strategy
                        if c.strategy.endswith("_emb_split")
                        else f"{c.strategy}_emb_split"
                    ),
                    start=c.start,
                    end=c.end,
                )
            )
    return SplitResult(children=new_children, parents=result.parents)


def split_parent_child(text: str, source_file: str = "unknown.md") -> SplitResult:
    """对单篇文档执行父子切分。

    优先级：
      1. 超短文件 (<1k) → 整篇 child=parent
      2. 有「第X条」→ 条级 child + 节/邻条 parent
      3. 有 ##/### → 平台规范路径
      4. 其它 → 结构感知 300～400 / parent 800～1200
    """
    text = text or ""
    if not text.strip():
        return SplitResult(children=[], parents=[])

    law_name = extract_law_name(text, source_file)

    if len(text.strip()) < SHORT_DOC_THRESHOLD:
        arts = _parse_articles(text)
        result = None
        if len(arts) >= 2:
            result = _split_by_articles(text, source_file, law_name)
        if not (result and result.children):
            result = _split_whole_doc(text, source_file, law_name)
        return _enforce_child_embed_limit(result)

    art_result = _split_by_articles(text, source_file, law_name)
    if art_result and art_result.children:
        return _enforce_child_embed_limit(art_result)

    md_result = _split_markdown_platform(text, source_file, law_name)
    if md_result and md_result.children:
        return _enforce_child_embed_limit(md_result)

    return _enforce_child_embed_limit(
        _split_structure_generic(text, source_file, law_name)
    )


def split_document(text: str, source_file: str = "unknown.md") -> SplitResult:
    """别名，供 indexer / admin 调用。"""
    return split_parent_child(text, source_file=source_file)
