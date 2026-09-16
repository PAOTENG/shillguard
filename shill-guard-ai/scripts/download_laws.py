# -*- coding: utf-8 -*-
"""
从全国人大法律法规数据库下载法律文件到 sources 目录。
来源：flk.npc.gov.cn（全国人大官网，政府公开数据，合法访问）
"""
import io
import sys
import json
import time
import re
from pathlib import Path

# 强制 stdout 使用 utf-8，避免 Windows GBK 编码错误
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
DELAY = 0.6

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Referer": "https://flk.npc.gov.cn/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

def clean_filename(title: str) -> str:
    title = re.sub(r'[\\/:*?"<>|\r\n]', '_', title)
    return title[:60].strip()

def fetch_page(page: int, size: int = 10) -> list:
    """分页获取所有法律（不过滤类型）"""
    url = "https://flk.npc.gov.cn/api/"
    params = {"page": page, "size": size}
    try:
        resp = httpx.get(url, params=params, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"  [WARN] HTTP {resp.status_code} page={page}")
            return []
        data = resp.json()
        # API 返回结构：{"result": {"data": [...], "totalSizes": N}}
        result = data.get("result", {})
        items = result.get("data", [])
        return items if isinstance(items, list) else []
    except Exception as e:
        print(f"  [ERROR] page={page}: {e}")
        return []

def fetch_detail(law_id: str) -> str:
    """获取单条法律的完整正文"""
    url = "https://flk.npc.gov.cn/api/detail"
    params = {"id": law_id}
    try:
        resp = httpx.get(url, params=params, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return ""
        data = resp.json()
        body = data.get("result", {}).get("body", "")
        return body or ""
    except Exception:
        return ""

def save_item(item: dict) -> bool:
    title = (item.get("title") or "").strip()
    if not title:
        return False

    law_type = item.get("type", "")
    filename = f"{law_type}_{clean_filename(title)}.md" if law_type else f"{clean_filename(title)}.md"
    filepath = SOURCES_DIR / filename
    if filepath.exists():
        return False

    # 尝试获取正文内容
    content = item.get("body", "") or item.get("content", "") or ""

    # 若正文为空，尝试通过 detail API 获取
    if not content or len(content) < 100:
        law_id = item.get("id", "")
        if law_id:
            content = fetch_detail(law_id)
            time.sleep(0.3)

    office = item.get("office", "")
    pub_date = item.get("publish_date", "") or ""
    status = item.get("status", "有效")

    md = f"# {title}\n\n"
    md += f"**法规类型**：{law_type}  \n"
    if office:
        md += f"**发布机关**：{office}  \n"
    if pub_date:
        md += f"**发布日期**：{pub_date}  \n"
    md += f"**状态**：{status}  \n"
    md += "\n---\n\n"

    if content and len(content) > 80:
        # 去掉 HTML 标签
        content = re.sub(r'<[^>]+>', '', content)
        content = re.sub(r'&nbsp;', ' ', content)
        content = re.sub(r'&lt;', '<', content)
        content = re.sub(r'&gt;', '>', content)
        content = re.sub(r'&amp;', '&', content)
        md += content
    else:
        md += f"（{title}）\n\n来源：全国人大法律法规数据库 https://flk.npc.gov.cn/"

    try:
        filepath.write_text(md, encoding="utf-8")
        return True
    except Exception as e:
        print(f"  [WARN] 写文件失败: {e}")
        return False

def count_existing() -> int:
    return len(list(SOURCES_DIR.glob("*.md")))

def main():
    existing = count_existing()
    print(f"当前 sources 目录已有 {existing} 个 .md 文件")
    print(f"目标：{TARGET} 个，还需下载约 {max(0, TARGET - existing)} 个")
    print(f"来源：全国人大法律法规数据库（flk.npc.gov.cn）\n")

    # 先探测第一页，了解数据结构
    print("探测 API 结构...")
    test = fetch_page(1, 10)
    if not test:
        print("[ERROR] API 无响应，请检查网络连接")
        return
    print(f"API 正常，第1页返回 {len(test)} 条，开始批量下载...\n")

    total_saved = 0
    page = 1

    while count_existing() < TARGET:
        items = fetch_page(page, size=10)
        if not items:
            print(f"第 {page} 页无数据，停止")
            break

        page_saved = 0
        for item in items:
            if save_item(item):
                page_saved += 1
                total_saved += 1
                current = count_existing()
                title = (item.get("title") or "?")[:28]
                law_type = item.get("type", "")
                print(f"  [{current:4d}] [{law_type}] {title}")

                if current >= TARGET:
                    break

        if page % 10 == 0:
            print(f"--- 已处理第 {page} 页，累计 {count_existing()} 个文件 ---")

        page += 1
        time.sleep(DELAY)

    final = count_existing()
    print(f"\n{'='*50}")
    print(f"下载完成！sources 目录共 {final} 个文件")
    if final < TARGET:
        print(f"[WARN] 未达 {TARGET} 个（实际 {final} 个）")
        print("可能原因：API 返回总条数不足，或部分条目重复跳过")
    else:
        print(f"[OK] 已达到 {TARGET} 个目标！")

if __name__ == "__main__":
    main()
