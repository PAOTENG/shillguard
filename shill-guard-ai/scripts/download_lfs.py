# -*- coding: utf-8 -*-
"""
通过 Git LFS Batch API 下载 twang2218/law-datasets 中的 laws.json.zip
该数据集 22,552 条法律全文，来源：全国人大国家法律法规数据库 flk.npc.gov.cn
"""
import io, sys, json, re, zipfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx

SOURCES_DIR = Path("D:/Projects/shill-guard-ai/app/rag/sources")
TMP_ZIP     = Path("D:/Projects/shill-guard-ai/scripts/law_tmp/laws.json.zip")
TMP_ZIP.parent.mkdir(parents=True, exist_ok=True)
SOURCES_DIR.mkdir(parents=True, exist_ok=True)
TARGET = 1000

LFS_OID  = "59568b19cca17ffd9758bb052633dd645633bb5e032b34f1fa03a20fc12552f9"
LFS_SIZE = 102396322

def count():
    return len(list(SOURCES_DIR.glob("*.md")))

def clean(s):
    return re.sub(r'[\\/:*?"<>|\r\n\t]', '_', str(s))[:60].strip()

def get_lfs_url():
    """通过 GitHub LFS Batch API 获取真实下载地址"""
    url = "https://github.com/twang2218/law-datasets.git/info/lfs/objects/batch"
    headers = {
        "Content-Type": "application/vnd.git-lfs+json",
        "Accept": "application/vnd.git-lfs+json",
        "User-Agent": "git-lfs/3.4.0",
    }
    payload = {
        "operation": "download",
        "transfers": ["basic"],
        "objects": [{"oid": LFS_OID, "size": LFS_SIZE}]
    }
    r = httpx.post(url, json=payload, headers=headers, timeout=30)
    print(f"  LFS batch 状态: {r.status_code}")
    data = r.json()
    obj = data.get("objects", [{}])[0]
    if "error" in obj:
        print(f"  LFS 错误: {obj['error']}")
        return None
    dl = obj.get("actions", {}).get("download", {})
    href = dl.get("href", "")
    print(f"  下载URL: {href[:80]}...")
    return href, dl.get("header", {})

def download_zip(url, headers_extra):
    print(f"开始下载 laws.json.zip ({LFS_SIZE // 1024 // 1024} MB)...")
    with httpx.stream("GET", url, headers=headers_extra, timeout=600,
                      follow_redirects=True) as r:
        total = int(r.headers.get("content-length", LFS_SIZE))
        downloaded = 0
        with open(TMP_ZIP, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=64*1024):
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded % (5 * 1024 * 1024) < 64 * 1024:
                    pct = downloaded * 100 // total
                    print(f"  进度: {downloaded // 1024 // 1024}MB / {total // 1024 // 1024}MB ({pct}%)")
    print(f"下载完成: {TMP_ZIP.stat().st_size // 1024 // 1024} MB")

def extract_to_md():
    print(f"解压并转换为 .md 文件...")
    with zipfile.ZipFile(TMP_ZIP, "r") as zf:
        names = zf.namelist()
        print(f"  压缩包内文件: {names}")
        json_name = next((n for n in names if n.endswith(".json")), None)
        if not json_name:
            print("  [ERROR] 找不到 .json 文件")
            return
        print(f"  解析 {json_name}...")
        with zf.open(json_name) as jf:
            laws = json.load(jf)
    print(f"  共 {len(laws)} 条法律，转换为 .md 文件...")
    saved = 0
    for law in laws:
        if count() >= TARGET:
            break
        title = (law.get("title") or "").strip()
        if not title:
            continue
        content = law.get("content") or ""
        law_type = law.get("type", "")
        office   = law.get("office", "")
        pub_date = law.get("publish_date") or law.get("publish", "")
        status   = law.get("status", "有效")
        filename = f"{clean(law_type)}_{clean(title)}.md"
        fp = SOURCES_DIR / filename
        if fp.exists():
            continue
        md  = f"# {title}\n\n"
        md += f"**类型**：{law_type}  \n"
        if office:   md += f"**发布机关**：{office}  \n"
        if pub_date: md += f"**发布日期**：{pub_date}  \n"
        md += f"**状态**：{status}  \n"
        md += "**来源**：全国人大国家法律法规数据库（flk.npc.gov.cn）\n"
        md += "\n---\n\n"
        md += re.sub(r'\n{4,}', '\n\n', content) if content else f"（{title}）"
        try:
            fp.write_text(md, encoding="utf-8")
            saved += 1
            if saved % 100 == 0:
                print(f"  进度: {count()}/{TARGET}")
        except Exception as e:
            print(f"  写入失败: {e}")
    print(f"转换完成，共 {count()} 个文件")

def main():
    print(f"当前 sources 目录: {count()} 个文件\n")
    if TMP_ZIP.exists() and TMP_ZIP.stat().st_size > 1_000_000:
        print("已有本地 laws.json.zip，直接解压")
    else:
        result = get_lfs_url()
        if not result:
            print("[ERROR] 无法获取 LFS 下载地址")
            return
        dl_url, extra_headers = result
        download_zip(dl_url, extra_headers)
    extract_to_md()
    final = count()
    print(f"\n{'='*50}")
    print(f"完成！sources 目录共 {final} 个 .md 文件")
    if final >= TARGET:
        print(f"[OK] 已达到 {TARGET} 个目标！")
    else:
        print(f"[WARN] 实际 {final} 个")

if __name__ == "__main__":
    main()
