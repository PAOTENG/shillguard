"""生成会跨过 500/50 滑动窗口边界的对抗法规文档。

精准失败模式：
  - 完整条款 = HEAD（检索钩子） + TAIL（罚则/要件/切分锚点）
  - 切点正好落在 HEAD|TAIL 之间
  - 任一单 chunk 都装不下 HEAD+TAIL
  - 关键词检索会优先命中仅含 HEAD 的 chunk → 缺锚点 → 易错引

用法（cmd）：
  cd /d d:\\project\\shill-guard-ai
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -m eval.chunk_boundary_suite.build_adversarial_docs
"""
from __future__ import annotations

import json
from pathlib import Path

from eval.chunk_boundary_suite.chunk_utils import (
    CHUNK_SIZE,
    analyze_article_split,
    chunk_text,
)

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources"
MANIFEST = ROOT / "manifest.json"

# HEAD 固定长度，保证落在首个边界前
HEAD_LEN = 90


def _pad_left(prefix: str, target_len: int) -> str:
    filler = "（过渡说明：本节用于版式占位与上下文衔接，不改变权利义务。）"
    if len(prefix) > target_len:
        return prefix[:target_len]
    need = target_len - len(prefix)
    reps = (need // len(filler)) + 2
    return (prefix + filler * reps)[:target_len]


def build_doc(
    *,
    title: str,
    law_short: str,
    article_id: str,
    head: str,
    tail: str,
    decoy_before: str,
    decoy_after: str,
    query_hooks: list[str],
    wrong_if_head_only: str,
) -> tuple[str, dict]:
    """构造单文件：在 char=500 处切断 HEAD|TAIL。"""
    if len(head) != HEAD_LEN:
        raise ValueError(f"{article_id} head 长度必须为 {HEAD_LEN}，实际 {len(head)}")
    for h in query_hooks:
        if h not in head:
            raise ValueError(f"{article_id} hook {h!r} 必须出现在 HEAD")
        if h in tail:
            raise ValueError(f"{article_id} hook {h!r} 不得出现在 TAIL（否则 top 会落到后半段）")
        if h in decoy_before or h in decoy_after:
            raise ValueError(f"{article_id} hook {h!r} 不得出现在诱饵段落")

    full_article = head + tail
    anchor = _extract_anchor(tail)
    if not anchor:
        raise ValueError(f"{article_id} TAIL 必须含【切分锚点-...】")

    cut_pos = CHUNK_SIZE  # 500
    article_start = cut_pos - HEAD_LEN  # 410

    preamble = (
        f"# {title}\n\n"
        f"> 对抗评测专用。law={law_short} article={article_id}\n\n"
        f"## 背景\n\n"
        f"本文件用于复现固定窗口切分导致的半条命中与错引风险。\n\n"
        f"{decoy_before.strip()}\n\n"
    )
    body = _pad_left(preamble, article_start)
    assert len(body) == article_start
    text = body + full_article + "\n\n" + decoy_after.strip() + "\n"

    local = analyze_article_split(text, full_article)
    if local.get("intact_in_single_chunk"):
        raise RuntimeError(f"{article_id} 仍被单 chunk 完整覆盖，需加长 TAIL")
    if not local.get("half_hit_possible"):
        raise RuntimeError(f"{article_id} 未能构造 head-only chunk: {local}")

    # 校验：按 hook 排序的 top chunk 应是 head-only 且无锚点
    chunks = chunk_text(text)
    ranked = sorted(
        chunks,
        key=lambda c: sum(1 for h in query_hooks if h in c["text"]),
        reverse=True,
    )
    top = ranked[0]
    if full_article in top["text"] or anchor in top["text"]:
        raise RuntimeError(
            f"{article_id} top chunk 仍含全文或锚点，index={top['index']} "
            f"preview={top['text'][:80]!r}"
        )
    if sum(1 for h in query_hooks if h in top["text"]) <= 0:
        raise RuntimeError(f"{article_id} top chunk 未命中 hooks")

    meta = {
        "law_short": law_short,
        "article_id": article_id,
        "full_article": full_article,
        "head": head,
        "tail": tail,
        "query_hooks": query_hooks,
        "wrong_if_head_only": wrong_if_head_only,
        "must_have_anchor": anchor,
        "article_start": local["article_start"],
        "article_end": local["article_end"],
        "article_len": local["article_len"],
        "num_chunks": local["num_chunks"],
        "head_only_chunk_indexes": local["head_only_chunk_indexes"],
        "tail_only_chunk_indexes": local["tail_only_chunk_indexes"],
        "top_chunk_index_by_hooks": top["index"],
        "head_chunk_preview": top["text"][:120] + "…",
    }
    return text, meta


def _extract_anchor(s: str) -> str:
    if "【切分锚点-" not in s:
        return ""
    i = s.index("【切分锚点-")
    j = s.index("】", i)
    return s[i : j + 1]


def _fit_head(raw: str, length: int = HEAD_LEN) -> str:
    """将 HEAD 精确裁剪/填充到 length（用全角空格填充，避免引入额外检索词）。"""
    if len(raw) > length:
        return raw[:length]
    return (raw + ("　" * length))[:length]


# ── 13 条对抗条款（HEAD 恰 90 字，hooks 仅在 HEAD）────────────────

SPECS: list[dict] = [
    {
        "filename": "01_网络暴力信息治理规定_NV-18.md",
        "title": "网络暴力信息治理规定（切分对抗·跟帖评论）",
        "law_short": "网络暴力信息治理规定",
        "article_id": "NV-18",
        "query_hooks": ["跟帖评论", "弹幕", "点赞"],
        "wrong_if_head_only": "易误引第十七条视听节目或第十九条论坛条款，漏掉删除/屏蔽/关闭评论等处置",
        "head": _fit_head(
            "第十八条　网络信息服务提供者应当加强对跟帖评论信息内容的管理，"
            "对以评论、回复、留言、弹幕、点赞等方式制作、复制、发布、传播"
        ),
        "tail": (
            "网络暴力信息的，应当及时采取删除、屏蔽、关闭评论、停止提供相关服务等处置措施。"
            "【切分锚点-NV18】未完整覆盖处置措施不得单独援引本条；"
            "并应保存相关记录，向有关部门报告，禁止只写「加强管理」而无具体措施。"
        ),
        "decoy_before": (
            "第十七条　网络信息服务提供者应当加强网络视听节目、网络表演等服务内容的管理，"
            "发现含有网络暴力信息的，应当及时删除信息或者停止提供相关服务。"
        ),
        "decoy_after": (
            "第十九条　网络信息服务提供者应当加强对网络论坛社区和网络群组的管理，"
            "禁止用户在版块、词条、超话、群组等环节制作、复制、发布、传播网络暴力信息。"
        ),
    },
    {
        "filename": "02_网络暴力信息治理规定_NV-14.md",
        "title": "网络暴力信息治理规定（切分对抗·账号信用）",
        "law_short": "网络暴力信息治理规定",
        "article_id": "NV-14",
        "query_hooks": ["信用记录", "信用等级", "账号信用"],
        "wrong_if_head_only": "易只写限制功能，漏掉列入黑名单与禁止重新注册",
        "head": _fit_head(
            "第十四条　网络信息服务提供者应当建立健全用户账号信用管理体系，"
            "将涉网络暴力信息违法违规情形记入用户信用记录，依法依约降低账号信用等级"
        ),
        "tail": (
            "或者列入黑名单，并据以限制账号功能或者停止提供相关服务。"
            "【切分锚点-NV14】对组织、煽动、多次发布网络暴力信息的，还应当依法依约采取禁止重新注册等处置措施；"
            "仅依据前半段表述不得省略黑名单与禁止重新注册要件。"
        ),
        "decoy_before": (
            "第十三条　网络信息服务提供者应当建立健全网络暴力信息预警模型，及时发现预警风险。"
        ),
        "decoy_after": (
            "第十五条　发现涉网络暴力违法信息的，应当立即停止传输，采取删除、屏蔽、断开链接等处置措施。"
        ),
    },
    {
        "filename": "03_治安管理处罚法_PS-42.md",
        "title": "治安管理处罚法（切分对抗·侮辱诽谤）",
        "law_short": "治安管理处罚法",
        "article_id": "PS-42",
        "query_hooks": ["公然侮辱", "诽谤他人", "散布他人隐私"],
        "wrong_if_head_only": "易把五日以下拘留写成唯一罚则，漏情节较重档，或与刑法侮辱罪混淆",
        "head": _fit_head(
            "第四十二条　有下列行为之一的，处五日以下拘留或者五百元以下罚款："
            "（二）公然侮辱他人或者捏造事实诽谤他人的；（六）偷窥、偷拍、窃听、散布他人隐私的。"
        ),
        "tail": (
            "情节较重的，处五日以上十日以下拘留，可以并处五百元以下罚款。"
            "【切分锚点-PS42】援引本条必须同时写明「情节较重」档处罚幅度，不得只截取五日以下档；"
            "亦不得在未达刑事门槛时直接改引刑法第二百四十六条。"
        ),
        "decoy_before": "第四十条　有下列行为之一的，处警告或者二百元以下罚款。",
        "decoy_after": (
            "第四十七条　煽动民族仇恨、民族歧视，或者在计算机信息网络中刊载民族歧视、侮辱内容的，"
            "处十日以上十五日以下拘留，可以并处一千元以下罚款。"
        ),
    },
    {
        "filename": "04_刑法_CL-246.md",
        "title": "刑法（切分对抗·侮辱诽谤罪）",
        "law_short": "刑法",
        "article_id": "CL-246",
        "query_hooks": ["侮辱罪", "诽谤罪", "剥夺政治权利"],
        "wrong_if_head_only": "易漏「告诉才处理」与公安机关协助规则，或与治安处罚法混用",
        "head": _fit_head(
            "第二百四十六条　以暴力或者其他方法公然侮辱他人或者捏造事实诽谤他人，情节严重的，"
            "处三年以下有期徒刑、拘役、管制或者剥夺政治权利。本条涉及侮辱罪、诽谤罪。"
        ),
        "tail": (
            "前款罪，告诉的才处理，但是严重危害社会秩序和国家利益的除外。"
            "通过信息网络实施第一款规定的行为，被害人向人民法院告诉，但提供证据确有困难的，"
            "人民法院可以要求公安机关提供协助。"
            "【切分锚点-CL246】刑事追责须同时具备「情节严重」与告诉程序提示，禁止仅因辱骂用语直接引用本条替代治安处罚。"
        ),
        "decoy_before": "第二百三十四条　故意伤害他人身体的，处三年以下有期徒刑、拘役或者管制。",
        "decoy_after": (
            "第二百五十三条之一　违反国家有关规定，向他人出售或者提供公民个人信息，情节严重的，"
            "处三年以下有期徒刑或者拘役。"
        ),
    },
    {
        "filename": "05_个人信息保护法_PI-10.md",
        "title": "个人信息保护法（切分对抗·非法公开）",
        "law_short": "个人信息保护法",
        "article_id": "PI-10",
        "query_hooks": ["非法收集", "非法买卖", "公开他人"],
        "wrong_if_head_only": "易与刑法侵犯公民个人信息罪条号混淆，或只写删帖",
        "head": _fit_head(
            "第十条　任何组织、个人不得非法收集、使用、加工、传输他人个人信息，"
            "不得非法买卖、提供或者公开他人个人信息；不得从事危害国家安全、公共利益的"
        ),
        "tail": (
            "个人信息处理活动。"
            "【切分锚点-PI10】平台处置人肉搜索、曝光身份证类内容时，应提示不得非法公开个人信息，"
            "并区分民事责任与刑法第二百五十三条之一的刑事门槛，禁止只写「删除信息」了事。"
        ),
        "decoy_before": "第九条　个人信息处理者应当对其个人信息处理活动负责，并采取必要措施保障安全。",
        "decoy_after": "第十三条　符合下列情形之一的，个人信息处理者方可处理个人信息：（一）取得个人的同意。",
    },
    {
        "filename": "06_网络安全法_CS-12.md",
        "title": "网络安全法（切分对抗·造谣传谣）",
        "law_short": "网络安全法",
        "article_id": "CS-12",
        "query_hooks": ["遵守公共秩序", "尊重社会公德", "使用网络应当"],
        "wrong_if_head_only": "易缩写成笼统「不得发布不良信息」，或与生态治理规定混淆",
        "head": _fit_head(
            "第十二条　任何个人和组织使用网络应当遵守宪法法律，遵守公共秩序，尊重社会公德，"
            "不得利用网络编造、传播虚假信息扰乱经济秩序和社会秩序，以及侵害他人"
        ),
        "tail": (
            "名誉、隐私、知识产权和其他合法权益等活动。"
            "【切分锚点-CS12】对造谣传谣类内容，援引本条须保留扰乱秩序类禁止事项的完整表述，"
            "不得缩写成笼统的「不得发布不良信息」。"
        ),
        "decoy_before": "第十条　建设、运营网络或者通过网络提供服务，应当依照法律、行政法规的规定和国家标准的强制性要求。",
        "decoy_after": "第二十一条　国家实行网络安全等级保护制度。网络运营者应当履行安全保护义务。",
    },
    {
        "filename": "07_网络信息内容生态治理规定_ECO-6.md",
        "title": "网络信息内容生态治理规定（切分对抗·淫秽色情）",
        "law_short": "网络信息内容生态治理规定",
        "article_id": "ECO-6",
        "query_hooks": ["教唆犯罪", "凶杀", "赌博"],
        "wrong_if_head_only": "易与互联网信息服务管理办法或刑法传播淫秽物品罪错配条号",
        "head": _fit_head(
            "第六条　网络信息内容生产者不得制作、复制、发布含有下列内容的违法信息："
            "（九）散布淫秽、色情、赌博、暴力、凶杀、恐怖或者教唆犯罪的；（十）侮辱或者"
        ),
        "tail": (
            "诽谤他人，侵害他人名誉、隐私和其他合法权益的；（十一）法律、行政法规禁止的其他内容。"
            "【切分锚点-ECO6】涉黄处置必须点名本条第九项完整列举，并与平台规则区分，"
            "禁止把本条缩写成「不得发布违法信息」而无具体项。"
        ),
        "decoy_before": "第五条　网络信息内容生产者应当遵守法律法规，遵循公序良俗。",
        "decoy_after": "第七条　网络信息内容生产者应当采取措施，防范和抵制制作、复制、发布不良信息。",
    },
    {
        "filename": "08_互联网信息服务管理办法_IIS-15.md",
        "title": "互联网信息服务管理办法（切分对抗·禁止内容）",
        "law_short": "互联网信息服务管理办法",
        "article_id": "IIS-15",
        "query_hooks": ["不得制作", "不得传播", "复制、发布"],
        "wrong_if_head_only": "易只写「不得制作」而不列具体禁止项",
        "head": _fit_head(
            "第十五条　互联网信息服务提供者不得制作、复制、发布、传播含有下列内容的信息："
            "互联网信息服务提供者还不得传播法律禁止内容。具体包括："
        ),
        "tail": (
            "（七）散布谣言，扰乱社会秩序，破坏社会稳定的；"
            "（八）散布淫秽、色情、赌博、暴力、凶杀、恐怖或者教唆犯罪的；"
            "（九）侮辱或者诽谤他人，侵害他人合法权益的；"
            "（十）含有法律、行政法规禁止的其他内容的。"
            "【切分锚点-IIS15】证据报告若只出现禁止性用语而未列明对应项，视为引用不完整。"
        ),
        "decoy_before": "第十四条　应当记录提供的信息内容及其发布时间、互联网地址或者域名。",
        "decoy_after": "第十六条　发现传输信息明显属于本办法第十五条所列内容的，应当立即停止传输。",
    },
    {
        "filename": "09_惩治网络暴力指导意见_NVGO.md",
        "title": "惩治网络暴力指导意见（切分对抗·侮辱分流）",
        "law_short": "惩治网络暴力指导意见",
        "article_id": "NVGO-insult",
        "query_hooks": ["肆意谩骂", "恶意诋毁", "披露隐私"],
        "wrong_if_head_only": "易一律按刑事侮辱罪写，漏掉尚不构成犯罪时的治安路径",
        "head": _fit_head(
            "【依法惩治网络侮辱行为】在信息网络上采取肆意谩骂、恶意诋毁、披露隐私等方式，公然侮辱他人，"
            "情节严重，符合刑法规定的，以侮辱罪定罪处罚。关于分流："
        ),
        "tail": (
            "实施网络侮辱行为，尚不构成犯罪，符合治安管理处罚法等规定的，依法予以行政处罚。"
            "【切分锚点-NVGO】必须保留「尚不构成犯罪→治安处罚」分流，禁止半段上下文下一律按刑事侮辱罪表述。"
        ),
        "decoy_before": "【指导思想】为依法惩治网络暴力违法犯罪活动，有效维护公民人格权益和网络秩序，制定本意见。",
        "decoy_after": "【依法惩治网络诽谤行为】在信息网络上制造、散布谣言贬损他人人格，情节严重的，以诽谤罪定罪处罚。",
    },
    {
        "filename": "10_两高网络诽谤司法解释_SPC500.md",
        "title": "两高网络诽谤司法解释（切分对抗·次数门槛）",
        "law_short": "两高网络诽谤司法解释",
        "article_id": "SPC-500",
        "query_hooks": ["完整口径见后半段", "转发次数达到五百", "依法审查是否属于"],
        "wrong_if_head_only": "易把五百次/五千次门槛写反或只写其中一个",
        "head": _fit_head(
            "同一诽谤信息实际被转发次数达到五百次以上的，应当依法审查是否属于刑法规定的情节严重。"
            "关于点击浏览与转发的完整口径见后半段。"
        ),
        "tail": (
            "同一信息实际被点击、浏览次数达到五千次以上，或者转发达到五百次以上的，"
            "应当认定为刑法第二百四十六条第一款规定的「情节严重」。"
            "【切分锚点-SPC500】点击浏览五千次与转发五百次为并列门槛，缺一不可写入证据。"
        ),
        "decoy_before": "利用信息网络诽谤他人，具有下列情形之一的，应当认定为「情节严重」。",
        "decoy_after": "一年内多次发布诽谤信息经责令删除后拒不删除的，也可以认定为「情节严重」。",
    },
    {
        "filename": "11_民法典_CC1024.md",
        "title": "民法典（切分对抗·名誉权）",
        "law_short": "民法典",
        "article_id": "CC-1024",
        "query_hooks": ["名誉权", "社会评价", "民事主体"],
        "wrong_if_head_only": "易只引治安法而完全不提民事名誉权定义",
        "head": _fit_head(
            "第一千零二十四条　民事主体享有名誉权。任何组织或者个人不得以侮辱、诽谤等方式侵害他人的名誉权。"
            "名誉是对民事主体的品德、声望、才能、信用等的社会评价。"
        ),
        "tail": (
            "【切分锚点-CC1024】民事路径应写明人格评价定义与禁止侮辱诽谤；"
            "若上下文被切断，模型常错误改引治安管理处罚法而完全不提民事救济。"
            "受害人可依法请求停止侵害、赔偿损失、赔礼道歉。"
        ),
        "decoy_before": "第一千零三十二条　自然人享有隐私权。任何组织或者个人不得以刺探、侵扰、泄露、公开等方式侵害他人的隐私权。",
        "decoy_after": "第一千零三十四条　自然人的个人信息受法律保护。个人信息中的私密信息，适用有关隐私权的规定。",
    },
    {
        "filename": "12_平台社区规范_PLAT.md",
        "title": "平台社区规范（切分对抗·站外引流）",
        "law_short": "平台社区规范",
        "article_id": "PLAT-ads",
        "query_hooks": ["微信号", "进群领福利", "站外引流"],
        "wrong_if_head_only": "易直接援引刑法诈骗罪，漏平台处置梯度",
        "head": _fit_head(
            "【站外引流】在评论或帖子中包含微信号、QQ群号等外部平台联系方式，"
            "或以「加微信有优惠」「进群领福利」等方式引导用户到外部平台的，构成站外引流。"
        ),
        "tail": (
            "【切分锚点-PLAT】平台处置依次为：警告删除 → 限制互动 → 封禁账号；"
            "不得在仅命中联系方式半段时直接援引刑法诈骗罪。"
            "首次违规以删除警告为主，屡次违规可限制互动直至封禁。"
        ),
        "decoy_before": "【广告骚扰】重复发布商业推广、刷屏营销的，按广告骚扰处理。",
        "decoy_after": "【违规带货】发布处方药、野生动物制品等违禁商品信息的，直接永久封禁。",
    },
    {
        "filename": "13_未成年人保护法_MIN74.md",
        "title": "未成年人保护法相关（切分对抗·不良内容）",
        "law_short": "未成年人保护法",
        "article_id": "MIN-74",
        "query_hooks": ["诱导沉迷", "身心健康", "包括暴力"],
        "wrong_if_head_only": "易笼统写「保护未成年人」而无具体禁止类型",
        "head": _fit_head(
            "网络产品和服务提供者不得向未成年人提供诱导沉迷的产品和服务，"
            "不得制作、复制、发布、传播含有危害未成年人身心健康内容的信息，包括暴力、"
        ),
        "tail": (
            "淫秽色情、血腥恐怖、性暗示以及诱导自杀自伤等。"
            "【切分锚点-MIN74】必须保留「性暗示以及诱导自杀自伤」列举；"
            "半条命中时常见错误是只写「不得危害未成年人」而无具体内容类型。"
        ),
        "decoy_before": "学校、社区应当加强未成年人网络素养教育。",
        "decoy_after": "监护人应当合理安排未成年人使用网络的时间，预防和干预沉迷网络。",
    },
]


def build_all() -> dict:
    SOURCES.mkdir(parents=True, exist_ok=True)
    for p in SOURCES.glob("*.md"):
        p.unlink()

    docs = []
    for spec in SPECS:
        text, meta = build_doc(
            title=spec["title"],
            law_short=spec["law_short"],
            article_id=spec["article_id"],
            head=spec["head"],
            tail=spec["tail"],
            decoy_before=spec["decoy_before"],
            decoy_after=spec["decoy_after"],
            query_hooks=spec["query_hooks"],
            wrong_if_head_only=spec["wrong_if_head_only"],
        )
        fname = spec["filename"]
        (SOURCES / fname).write_text(text, encoding="utf-8")
        meta["filename"] = fname
        docs.append(meta)
        print(
            f"[ok] {fname} article_len={meta['article_len']} "
            f"start={meta['article_start']} top_by_hooks={meta['top_chunk_index_by_hooks']} "
            f"head_only={meta['head_only_chunk_indexes']}"
        )

    manifest = {
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": 50,
        "head_len": HEAD_LEN,
        "doc_count": len(docs),
        "docs": docs,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写入 {len(docs)} 个文件 → {SOURCES}")
    return manifest


if __name__ == "__main__":
    build_all()
