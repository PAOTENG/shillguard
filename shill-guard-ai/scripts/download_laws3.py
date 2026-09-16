# -*- coding: utf-8 -*-
"""
从全国人大国家法律法规数据库正式下载法律文件。
来源：https://flk.npc.gov.cn（全国人大官网，政府公开数据）

API 说明（通过社区逆向工程验证）：
  列表接口：GET  https://flk.npc.gov.cn/api/
  详情接口：POST https://flk.npc.gov.cn/api/detail  (form data: id=xxx)
  下载基址：https://wb.flk.npc.gov.cn + path
"""
import io, sys, json, re, time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

SOURCES_DIR = Path("D:/Projects/shill-guard-ai/app/rag/sources")
SOURCES_DIR.mkdir(parents=True, exist_ok=True)
TARGET = 1000
DELAY  = 0.8   # 每次请求间隔，礼貌访问

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Referer":    "https://flk.npc.gov.cn/index.html",
    "Accept":     "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Origin":     "https://flk.npc.gov.cn",
}

# 法律类型代码 → 中文名称（优先级从高到低，最相关在前）
TYPES = [
    ("bmgz",   "部门规章",      400),   # 互联网信息服务各类管理规定（最相关）
    ("flfg",   "法律",          200),   # 全国人大立法
    ("xzfg",   "行政法规",      200),   # 国务院条例
    ("sfjs",   "司法解释",      100),   # 两高司法解释
    ("dfxfg",  "地方性法规",    100),   # 地方法规（补充量）
]

def clean(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|\r\n\t]', '_', str(s))[:60].strip()

def count() -> int:
    return len(list(SOURCES_DIR.glob("*.md")))

def fetch_list(type_code: str, page: int, size: int = 10) -> list:
    """列表接口 GET /api/"""
    params = {
        "type":        type_code,
        "searchType":  "title;vague",
        "sortTr":      "f_bbrq_s;desc",
        "gbrqStart":   "",
        "gbrqEnd":     "",
        "sxrqStart":   "",
        "sxrqEnd":     "",
        "sort":        "true",
        "page":        str(page),
        "size":        str(size),
        "_":           str(int(time.time() * 1000)),
    }
    try:
        resp = httpx.get("https://flk.npc.gov.cn/api/",
                         params=params, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return []
        data = resp.json()
        items = data.get("result", {}).get("data", [])
        return items if isinstance(items, list) else []
    except Exception as e:
        print(f"  [列表ERROR] page={page} type={type_code}: {e}")
        return []

def fetch_total(type_code: str) -> int:
    """获取某类型的总条数"""
    params = {
        "type": type_code, "searchType": "title;vague",
        "sortTr": "f_bbrq_s;desc", "page": "1", "size": "1",
        "_": str(int(time.time() * 1000)),
    }
    try:
        resp = httpx.get("https://flk.npc.gov.cn/api/",
                         params=params, headers=HEADERS, timeout=15)
        data = resp.json()
        return data.get("result", {}).get("totalSizes", 0)
    except Exception:
        return 0

def fetch_detail_links(law_id: str) -> dict:
    """详情接口 POST /api/detail，返回 {type: url} 下载链接"""
    try:
        resp = httpx.post("https://flk.npc.gov.cn/api/detail",
                          data={"id": law_id}, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        links = {}
        for doc in data.get("result", {}).get("body", []):
            path = doc.get("path") or doc.get("url") or ""
            if path:
                links[doc.get("type", "unknown")] = "https://wb.flk.npc.gov.cn" + path
        return links
    except Exception:
        return {}

def download_html_content(url: str) -> str:
    """下载 HTML 并提取纯文本"""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
        if resp.status_code != 200:
            return ""
        html = resp.text
        # 去除 script/style
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>',  '', html, flags=re.DOTALL)
        # 段落换行
        html = re.sub(r'<br\s*/?>', '\n', html)
        html = re.sub(r'</p>', '\n\n', html)
        # 去掉所有 HTML 标签
        text = re.sub(r'<[^>]+>', '', html)
        # 清理实体
        text = re.sub(r'&nbsp;',  ' ',  text)
        text = re.sub(r'&lt;',    '<',  text)
        text = re.sub(r'&gt;',    '>',  text)
        text = re.sub(r'&amp;',   '&',  text)
        text = re.sub(r'&ldquo;', '"',  text)
        text = re.sub(r'&rdquo;', '"',  text)
        text = re.sub(r'\n{4,}',  '\n\n', text)
        return text.strip()
    except Exception:
        return ""

def process_item(item: dict, type_cn: str) -> bool:
    """处理一条法律：获取下载链接 → 下载HTML → 保存为md"""
    title  = (item.get("title") or "").strip()
    law_id = item.get("id", "")
    if not title or not law_id:
        return False

    filename = f"{type_cn}_{clean(title)}.md"
    filepath = SOURCES_DIR / filename
    if filepath.exists():
        return False   # 已存在，跳过

    # 先尝试直接从列表数据拿内容（部分接口直接返回正文）
    content = item.get("body") or item.get("content") or ""

    # 没有内容，通过 detail 接口获取下载链接再下载
    if not content or len(content) < 200:
        links = fetch_detail_links(law_id)
        time.sleep(0.3)
        # 优先 HTML（纯文本最好提取），其次 WORD
        html_url = links.get("HTML") or links.get("html") or ""
        if html_url:
            content = download_html_content(html_url)
            time.sleep(0.3)

    # 组装 Markdown
    office   = item.get("office", "")
    pub_date = item.get("publish_date", "") or item.get("expiry", "")
    status   = item.get("status", "有效")

    md  = f"# {title}\n\n"
    md += f"**类型**：{type_cn}  \n"
    if office:   md += f"**发布机关**：{office}  \n"
    if pub_date: md += f"**发布日期**：{pub_date}  \n"
    md += f"**状态**：{status}  \n"
    md += f"**来源**：全国人大国家法律法规数据库 https://flk.npc.gov.cn\n"
    md += "\n---\n\n"

    if content and len(content) > 100:
        md += content
    else:
        md += f"（{title}，来源：全国人大国家法律法规数据库）"

    try:
        filepath.write_text(md, encoding="utf-8")
        return True
    except Exception as e:
        print(f"  [写文件ERROR] {filename}: {e}")
        return False


def main():
    print(f"当前 sources 目录：{count()} 个文件，目标 {TARGET} 个")
    print("数据源：全国人大国家法律法规数据库（flk.npc.gov.cn）\n")

    # 先测试 API 是否可达
    print("测试 API...")
    test = fetch_list("flfg", 1, 3)
    if not test:
        print("[ERROR] API 无响应，检查网络或尝试开代理")
        # 输出诊断信息
        try:
            r = httpx.get("https://flk.npc.gov.cn/api/",
                          params={"type":"flfg","page":"1","size":"3",
                                  "_":str(int(time.time()*1000))},
                          headers=HEADERS, timeout=15)
            print(f"  HTTP状态：{r.status_code}")
            print(f"  响应前200字：{r.text[:200]}")
        except Exception as ex:
            print(f"  连接异常：{ex}")
        return

    print(f"API 正常！第一条：{test[0].get('title','?')}\n")

    for type_code, type_cn, quota in TYPES:
        if count() >= TARGET:
            break

        total = fetch_total(type_code)
        print(f"=== 【{type_cn}】 共 {total} 条，本次取 {quota} 条 ===")
        type_saved = 0
        page = 1

        while type_saved < quota and count() < TARGET:
            items = fetch_list(type_code, page)
            if not items:
                print(f"  第 {page} 页无数据，结束本类型")
                break

            for item in items:
                if count() >= TARGET:
                    break
                if process_item(item, type_cn):
                    type_saved += 1
                    title_short = (item.get("title") or "?")[:25]
                    print(f"  [{count():4d}] {title_short}")

            page += 1
            time.sleep(DELAY)

        print(f"  [{type_cn}] 保存 {type_saved} 条，当前共 {count()} 个文件\n")

    final = count()
    print("=" * 50)
    print(f"完成！sources 目录共 {final} 个文件")
    if final >= TARGET:
        print(f"[OK] 已达到 {TARGET} 个目标！")
    else:
        print(f"[WARN] 实际 {final} 个（网络或API限制）")


if __name__ == "__main__":
    main()
