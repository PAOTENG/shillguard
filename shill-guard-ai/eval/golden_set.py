"""
评测黄金集：三类标注用例。

CascadeCase    — 直接测 pre_filter_node（无LLM，< 1ms/条）
RAGCase        — 测 retrieve() 召回质量（无LLM，异步 HTTP）
ModerationCase — 测完整审核链路输出（有LLM，慢）

设计原则：
  - 每条用例有可核验的期望值，不依赖"感觉对"
  - T1/T2 期望值可从 cascade.py 确定性规则精确推导
  - T3/Moderation 期望值来自人工标注
  - RAG 期望值来自 app/rag/sources/ 下约 1000 个法律法规文件的真实内容
"""
from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════
#  数据类定义
# ═══════════════════════════════════════════════════════════════

@dataclass
class CascadeCase:
    """级联层单条用例：期望值可从 cascade.py 规则确定性推导。"""
    id: str                          # 用例唯一标识，如 cascade_001
    content_list: list[str]          # 被审核内容（与 moderation API contentList 一致）
    report_category: int             # 0广告/1违法/2辱骂/3涉黄/4其他（Java 举报分类码）
    expected_verdict: str            # clear_violation / clear_normal / ambiguous
    expected_tier: str               # T1-blacklist / T1-whitelist / T2-weighted / T3-llm
    expected_score: Optional[float]  # T1/T2 精确分（可从规则推导）；T3 填 None
    description: str = ""            # 人工可读说明，便于失败时定位


@dataclass
class RAGCase:
    """RAG 召回单条用例：只测 retrieve()，不调 LLM。"""
    id: str
    query: str                       # 检索 query（通常模拟 judge 节点生成的检索词）
    expected_keywords: list[str]     # top-k 结果里至少命中一个关键词即 recall 成功
    all_required: bool = False       # True = 必须全部命中（严格模式）
    description: str = ""


@dataclass
class ModerationCase:
    """全链路审核单条用例：需调 LLM，期望值来自人工标注。"""
    id: str
    content_list: list[str]
    report_category: int
    expected_action: str             # none / manual_review / auto_mute（最终处置）
    expected_score_min: float        # anomaly_score 可接受区间下界
    expected_score_max: float        # anomaly_score 可接受区间上界
    expected_laws_contain: list[str] # evidence_detail 里应出现的法条关键词（至少一个）
    description: str = ""


# ═══════════════════════════════════════════════════════════════
#  已知合法法条集
#  来源：app/rag/sources/ 下约 1000 个法律法规文件 + SYSTEM_PROMPT 列举的法律
#  用于 citation_check：evidence_detail 里引用的法条必须在此集合中
#  匹配方式：子串匹配（处理全称/简称的映射，如"中华人民共和国刑法"→"刑法"）
# ═══════════════════════════════════════════════════════════════

KNOWN_LAWS: set[str] = {
    "网络安全法",
    "网络信息内容生态治理规定",
    "网络暴力信息治理规定",
    "治安管理处罚法",
    "刑法",
    "民法典",
    "个人信息保护法",
    "互联网信息服务管理办法",
    "两高",            # 两高网络诽谤司法解释（前缀匹配）
    "惩治网络暴力",    # 关于依法惩治网络暴力违法犯罪的指导意见
}


# ═══════════════════════════════════════════════════════════════
#  Cascade 黄金集（42 条）
#  期望值全部可从 cascade.py 的规则逻辑精确推导，确定性 100%
# ═══════════════════════════════════════════════════════════════

GOLDEN_CASCADE: list[CascadeCase] = [

    # ── T1-黑名单·涉黄（score 固定 0.92）──────────────────────
    CascadeCase("C-T1-B-01", ["想约炮加我微信abc123"], 3,
                "clear_violation", "T1-blacklist", 0.92,
                "涉黄关键词'约炮'"),
    CascadeCase("C-T1-B-02", ["妹妹裸聊视频私我"], 3,
                "clear_violation", "T1-blacklist", 0.92,
                "涉黄关键词'裸聊'"),
    CascadeCase("C-T1-B-03", ["色情服务联系一下"], 3,
                "clear_violation", "T1-blacklist", 0.92,
                "涉黄关键词'色情服务'"),
    CascadeCase("C-T1-B-04", ["同城一夜情找她"], 3,
                "clear_violation", "T1-blacklist", 0.92,
                "涉黄关键词'一夜情'"),
    CascadeCase("C-T1-B-05", ["找小姐同上联系"], 3,
                "clear_violation", "T1-blacklist", 0.92,
                "涉黄关键词'找小姐'"),

    # ── T1-黑名单·诈骗（score 固定 0.88）──────────────────────
    CascadeCase("C-T1-B-06", ["刷单兼职日入500"], 1,
                "clear_violation", "T1-blacklist", 0.88,
                "诈骗词'刷单兼职'"),
    CascadeCase("C-T1-B-07", ["日赚过千带你飞"], 1,
                "clear_violation", "T1-blacklist", 0.88,
                "诈骗词'日赚过千'"),
    CascadeCase("C-T1-B-08", ["投资返利稳赚项目"], 1,
                "clear_violation", "T1-blacklist", 0.88,
                "诈骗词'投资返利'"),
    CascadeCase("C-T1-B-09", ["稳赚不赔快上车"], 1,
                "clear_violation", "T1-blacklist", 0.88,
                "诈骗词'稳赚不赔'"),
    CascadeCase("C-T1-B-10", ["高息返本年化30%"], 1,
                "clear_violation", "T1-blacklist", 0.88,
                "诈骗词'高息返本'"),
    CascadeCase("C-T1-B-11", ["免费领红包点链接"], 1,
                "clear_violation", "T1-blacklist", 0.88,
                "诈骗词'免费领红包'"),
    CascadeCase("C-T1-B-12", ["点赞赚钱攻略分享"], 1,
                "clear_violation", "T1-blacklist", 0.88,
                "诈骗词'点赞赚钱'"),
    CascadeCase("C-T1-B-13", ["扫码领福利限时"], 1,
                "clear_violation", "T1-blacklist", 0.88,
                "诈骗词'扫码领福利'"),

    # ── T1-黑名单·违禁品（score 固定 0.85）────────────────────
    CascadeCase("C-T1-B-14", ["处方药代购便宜出"], 1,
                "clear_violation", "T1-blacklist", 0.85,
                "违禁品词'处方药代购'"),
    CascadeCase("C-T1-B-15", ["万艾可代购联系我"], 1,
                "clear_violation", "T1-blacklist", 0.85,
                "违禁品词'万艾可代购'"),
    CascadeCase("C-T1-B-16", ["电子烟批发量大"], 1,
                "clear_violation", "T1-blacklist", 0.85,
                "违禁品词'电子烟批发'"),
    CascadeCase("C-T1-B-17", ["香烟低价出售"], 1,
                "clear_violation", "T1-blacklist", 0.85,
                "违禁品词'香烟低价'"),
    CascadeCase("C-T1-B-18", ["野生动物制品回收"], 1,
                "clear_violation", "T1-blacklist", 0.85,
                "违禁品词'野生动物制品'"),

    # ── T1-黑名单·人肉搜索（score 固定 0.90）──────────────────
    CascadeCase("C-T1-B-19", ["大家一起人肉他"], 2,
                "clear_violation", "T1-blacklist", 0.90,
                "人肉词'人肉他'"),
    CascadeCase("C-T1-B-20", ["挂人避雷这骗子"], 2,
                "clear_violation", "T1-blacklist", 0.90,
                "人肉词'挂人'"),
    CascadeCase("C-T1-B-21", ["曝光他身份证123456789012345678"], 2,
                "clear_violation", "T1-blacklist", 0.90,
                "人肉词'曝光他身份证'"),
    CascadeCase("C-T1-B-22", ["扒他底细全部挂出来"], 2,
                "clear_violation", "T1-blacklist", 0.90,
                "人肉词'扒他底细'"),

    # ── T1-白名单（必须满足：len<15 + category=4 + 无任何信号）─
    CascadeCase("C-T1-W-01", ["好的"], 4,
                "clear_normal", "T1-whitelist", 0.1,
                "长度2<15，无信号，category=4，全部白名单条件满足"),
    CascadeCase("C-T1-W-02", ["谢谢"], 4,
                "clear_normal", "T1-whitelist", 0.1, "白名单"),
    CascadeCase("C-T1-W-03", ["已收到"], 4,
                "clear_normal", "T1-whitelist", 0.1, "白名单"),
    CascadeCase("C-T1-W-04", ["没问题"], 4,
                "clear_normal", "T1-whitelist", 0.1, "白名单"),
    CascadeCase("C-T1-W-05", ["嗯嗯"], 4,
                "clear_normal", "T1-whitelist", 0.1, "白名单"),
    CascadeCase("C-T1-W-06", ["收到啦"], 4,
                "clear_normal", "T1-whitelist", 0.1, "白名单，6字"),
    CascadeCase("C-T1-W-07", ["了解"], 4,
                "clear_normal", "T1-whitelist", 0.1, "白名单，2字"),
    CascadeCase("C-T1-W-08", ["这首歌真好听"], 4,
                "clear_normal", "T1-whitelist", 0.1,
                "长度7<15，无信号，category=4，满足白名单"),

    # ── T2-加权违规（期望分可从软信号权重手动计算）─────────────
    # 微信联系方式(+0.25)+有优惠(+0.10)+进群(+0.10)+代理(+0.10) = 0.55，恰好触发阈值
    CascadeCase("C-T2-01", ["加我微信abc12有优惠进群代理"], 0,
                "clear_violation", "T2-weighted", 0.55,
                "联系方式0.25+有优惠0.10+进群0.10+代理0.10=0.55，恰好触发"),
    # 去死(0.20)+废物(0.15)+脑残(0.15)+联系方式(0.25) = 0.75
    CascadeCase("C-T2-02", ["去死废物脑残加我微信abc123456"], 2,
                "clear_violation", "T2-weighted", 0.75,
                "辱骂叠加0.50+联系方式0.25=0.75"),
    # 脑子有病(0.15)+白痴(0.15)+去死(0.20)+联系方式(0.25) = 0.75
    CascadeCase("C-T2-03", ["脑子有病白痴去死加v:abc12345"], 2,
                "clear_violation", "T2-weighted", 0.75,
                "辱骂叠加0.50+v:联系方式0.25=0.75"),
    # 废物(0.15)+傻子(0.10)+去死(0.20)+脑子有病(0.15) = 0.60，纯辱骂超阈值
    CascadeCase("C-T2-04", ["废物傻子去死脑子有病"], 2,
                "clear_violation", "T2-weighted", 0.60,
                "纯辱骂叠加=0.60，无需联系方式"),

    # ── T3-退回LLM（ambiguous）──────────────────────────────
    CascadeCase("C-T3-01", ["你这个人真的很有意思"], 2,
                "ambiguous", "T3-llm", None,
                "无信号，category=2非其他，不满足白名单，退LLM"),
    CascadeCase("C-T3-02", ["我觉得这产品体验一般般"], 4,
                "ambiguous", "T3-llm", None,
                "长度>15，不满足白名单长度条件，退LLM"),
    CascadeCase("C-T3-03", ["你能不能别这样说话"], 2,
                "ambiguous", "T3-llm", None, "无信号，退LLM"),
    CascadeCase("C-T3-04", ["好的没问题"], 2,
                "ambiguous", "T3-llm", None,
                "正常内容但category=2，不满足白名单category条件，退LLM"),
    # 纯辱骂加权不足0.55（0.15+0.15=0.30），退LLM
    CascadeCase("C-T3-05", ["废物脑子有病"], 2,
                "ambiguous", "T3-llm", None,
                "辱骂加权0.30 < 0.55阈值，退LLM"),
]


# ═══════════════════════════════════════════════════════════════
#  RAG 黄金集（15 条）
#  期望关键词来自 app/rag/sources/ 下约 1000 个法律法规文件的真实内容
#  recall@5 = top-5 结果里至少命中一个 expected_keyword 即算成功
# ═══════════════════════════════════════════════════════════════

GOLDEN_RAG: list[RAGCase] = [
    RAGCase("R-01", "网络暴力法律法规",
            ["惩治网络暴力", "侮辱谩骂"],
            # 原关键词 "网络暴力信息治理规定" 仅在法规标题行出现1次，正文 chunk 不含此全称。
            # "惩治网络暴力" 在惩治网络暴力指导意见的各节标题中出现4次；
            # "侮辱谩骂" 在网络暴力信息治理规定第三十二条定义中出现，是内容级关键词。
            description="核心场景：查网暴法律，应召回两部核心法规"),

    RAGCase("R-02", "诽谤罪刑事追责500次转发",
            ["五千次", "五百次", "诽谤"],
            # 原关键词 "两高" 在源文件里不存在（全称是"最高人民法院、最高人民检察院"）；
            # "500次"/"5000次" 在源文件里是汉字"五百次"/"五千次"，阿拉伯数字版本出现0次。
            description="两高司法解释核心条款：转发500次/点击5000次门槛"),

    RAGCase("R-03", "人肉搜索侵犯个人信息",
            ["个人信息保护法", "侵犯公民个人信息"],
            description="人肉搜索应召回个保法和刑法"),

    RAGCase("R-04", "公然侮辱他人法律处罚",
            ["治安管理处罚法", "拘留", "罚款"],
            description="侮辱行为的行政处罚条款"),

    RAGCase("R-05", "平台封号删帖处置措施",
            ["关闭账号", "删除信息", "警示"],
            # 原关键词 "网络暴力信息治理规定" 只在标题行出现；
            # "限制功能" 在源文件里不存在，文档原文是"限制账号功能"（非子串匹配失败）。
            # 第二十一条原文："警示、删除信息、限制账号功能、关闭账号"，三个替换词均在此句。
            description="平台对违规用户的具体处置措施"),

    RAGCase("R-06", "发布色情淫秽内容处罚",
            ["互联网信息服务管理办法", "网络信息内容生态治理规定", "淫秽"],
            description="涉黄内容的法律依据"),

    RAGCase("R-07", "名誉权隐私权民事保护",
            ["民法典", "名誉权", "隐私权"],
            description="民法典人格权条款"),

    RAGCase("R-08", "互联网平台信息服务规范",
            ["互联网信息服务管理办法", "不得制作"],
            description="互联网信息服务管理办法禁止性条款"),

    RAGCase("R-09", "网络安全法平台义务",
            ["网络安全法", "网络运营者"],
            description="网络安全法对平台的义务要求"),

    RAGCase("R-10", "造谣传谣违法后果",
            ["网络安全法", "网络信息内容生态治理规定", "散布谣言"],
            description="造谣传谣的法律后果"),

    RAGCase("R-11", "广告引流违规平台规则",
            ["平台", "引流", "广告"],
            description="平台规则中关于引流广告的规定"),

    RAGCase("R-12", "诈骗信息刑事追责",
            ["刑法", "诈骗"],
            description="刑法诈骗罪条款"),

    RAGCase("R-13", "跟帖评论审核管理",
            ["跟帖评论", "弹幕"],
            # 原关键词 "网络暴力信息治理规定" 只在标题行出现，内容 chunk 不含。
            # 第十八条原文含 "跟帖评论" 和 "弹幕"，两词均为该条款独有，命中即说明召回正确。
            description="网暴治理规定第十八条跟帖评论管理"),

    RAGCase("R-14", "侮辱诽谤刑事处理",
            ["刑法", "侮辱", "诽谤"],
            description="刑法侮辱诽谤罪条款"),

    RAGCase("R-15", "账号信用管理降级封禁",
            ["信用记录", "列入黑名单"],
            # 原关键词 "网络暴力信息治理规定" 只在标题行出现；"信用" 和 "黑名单" 过于泛化。
            # 第十四条原文："记入用户信用记录"、"列入黑名单"，两词共现且高度专属。
            description="平台账号信用管理，网暴治理规定第十四条"),
]


# ═══════════════════════════════════════════════════════════════
#  Moderation 黄金集（12 条）
#  覆盖 T3-LLM 完整流程：classify→retrieve→judge→evidence→action
#  期望值由人工标注，score 用区间（LLM 输出有波动）
# ═══════════════════════════════════════════════════════════════

GOLDEN_MODERATION: list[ModerationCase] = [

    # ── 明确违规，应 auto_mute ─────────────────────────────
    ModerationCase("M-01",
                   ["你这种垃圾就该去死，反复发帖骚扰，脑子有病",
                    "废物东西，一次次来骚扰我，我要人肉你"],
                   2,
                   "auto_mute", 0.75, 1.0,
                   ["刑法", "治安管理处罚法", "网络暴力信息治理规定"],
                   "多条辱骂+人肉威胁，应 auto_mute(≥0.8)"),

    ModerationCase("M-02",
                   ["投资我的平台绝对稳赚，收益高达200%，零风险"],
                   1,
                   "auto_mute", 0.75, 1.0,
                   ["刑法", "诈骗"],
                   "虚假投资诈骗宣传，应 auto_mute"),

    ModerationCase("M-03",
                   ["XX省的人都是骗子，垃圾，根本不能信"],
                   2,
                   "manual_review", 0.55, 0.85,
                   ["网络暴力信息治理规定", "治安管理处罚法"],
                   "地域歧视，应 manual_review(0.6~0.8)"),

    # ── 明显违规，应 manual_review ─────────────────────────
    ModerationCase("M-04",
                   ["加我微信看看，这个产品效果不错，有需要的联系"],
                   0,
                   "manual_review", 0.50, 0.80,
                   ["互联网信息服务管理办法"],
                   "站外引流广告，应 manual_review"),

    ModerationCase("M-05",
                   ["某某某（真名），手机号138XXXX，住在XX小区XX室"],
                   2,
                   "auto_mute", 0.75, 1.0,
                   ["个人信息保护法", "刑法"],
                   "泄露他人真实个人信息，应 auto_mute"),

    ModerationCase("M-06",
                   ["这个博主是假的，他从来没做过慈善全是捏造的！"],
                   1,
                   "manual_review", 0.50, 0.80,
                   ["刑法", "民法典"],
                   "疑似造谣诽谤，但需人工核实"),

    # ── 边界模糊，需 LLM 判断 ─────────────────────────────
    ModerationCase("M-07",
                   ["你这说法根本站不住脚，逻辑有问题"],
                   2,
                   "none", 0.0, 0.50,
                   [],
                   "批评观点而非人身攻击，应 none"),

    ModerationCase("M-08",
                   ["这个功能真的很烂，产品经理是干什么吃的"],
                   2,
                   "none", 0.0, 0.55,
                   [],
                   "情绪化吐槽，边界内，应 none 或轻微"),

    ModerationCase("M-09",
                   ["这个内容感觉有点问题，大家注意一下"],
                   1,
                   "none", 0.0, 0.45,
                   [],
                   "模糊举报，内容本身无明显违规"),

    # ── 明确正常，应 none ─────────────────────────────────
    ModerationCase("M-10",
                   ["今天看了部电影，剧情还不错，推荐大家看"],
                   4,
                   "none", 0.0, 0.30,
                   [],
                   "明显正常内容，虽被举报应判 none"),

    ModerationCase("M-11",
                   ["网络暴力的危害很大，希望大家文明上网"],
                   2,
                   "none", 0.0, 0.30,
                   [],
                   "正向倡导内容，不违规"),

    ModerationCase("M-12",
                   ["请问平台对违规内容的处理流程是什么？"],
                   4,
                   "none", 0.0, 0.30,
                   [],
                   "咨询类内容，完全正常"),
]
