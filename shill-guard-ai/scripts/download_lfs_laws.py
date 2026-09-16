# -*- coding: utf-8 -*-
"""
通过 Git LFS Batch API 下载 twang2218/law-datasets 的 laws.json.zip
该压缩包含 22,552 条从全国人大 flk.npc.gov.cn 采集的法律全文
"""
import io, sys, json, re, zipfile, time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

SOURCES_DIR = Path("D:/Projects/shill-guard-ai/app/rag/sources")
TMP_DIR     = Path("D:/Projects/shill-guard-ai/scripts/law_tmp")
ZIP_PATH    = TMP_DIR / "laws.json.zip"
JSON_PATH   = TMP_DIR / "laws.json"
TARGET      = 1000

SOURCES_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)

LFS_OID  = "59568b19cca17ffd9758bb052633dd645633bb5e032b34f1fa03a20fc12552f9"
LFS_SIZE = 102396322

def count():
    return len(list(SOURCES_DIR.glob("*.md")))

def clean(s):
    return re.sub(r'[\\/:*?"<>|\r\n\t]', '_', str(s))[:60].strip()

def get_lfs_download_url():
    """调用 GitHub LFS Batch API 获取真实下载地址"""
    url = "https://github.com/twang2218/law-datasets.git/info/lfs/objects/batch"
    payload = {
        "operation": "download",
        "transfer": ["basic"],
        "objects": [{"oid": LFS_OID, "size": LFS_SIZE}]
    }
    headers = {
        "Accept":       "application/vnd.git-lfs+json",
        "Content-Type": "application/vnd.git-lfs+json",
        "User-Agent":   "git-lfs/3.3.0",
    }
    print("请求 LFS Batch API...")
    resp = httpx.post(url, json=payload, headers=headers, timeout=30)
    print(f"  LFS API 状态: {resp.status_code}")
    if resp.status_code not in (200, 202):
        print(f"  响应: {resp.text[:500]}")
        return None
    data = resp.json()
    objs = data.get("objects", [])
    if not objs:
        return None
    obj = objs[0]
    actions = obj.get("actions", {})
    download = actions.get("download", {})
    href = download.get("href", "")
    print(f"  下载地址: {href[:80]}...")
    return href

def download_zip(url: str):
    """流式下载大文件（~100MB）"""
    print(f"开始下载 laws.json.zip (~97MB)，请耐心等待...")
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
    }
    # 已下载过就跳过
    if ZIP_PATH.exists() and ZIP_PATH.stat().st_size > 10_000_000:
        print(f"  ZIP 已存在（{ZIP_PATH.stat().st_size // 1024 // 1024}MB），跳过下载")
        return True

    with open(ZIP_PATH, "wb") as f:
        with httpx.stream("GET", url, headers=headers, timeout=300,
                          follow_redirects=True) as resp:
            if resp.status_code != 200:
                print(f"  下载失败: HTTP {resp.status_code}")
                return False
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            last_pct = -1
            for chunk in resp.iter_bytes(chunk_size=1024*1024):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    if pct != last_pct and pct % 10 == 0:
                        print(f"  进度: {pct}% ({downloaded//1024//1024}MB/{total//1024//1024}MB)")
                        last_pct = pct

    size_mb = ZIP_PATH.stat().st_size // 1024 // 1024
    print(f"  下载完成！文件大小: {size_mb}MB")
    return True

def extract_zip():
    """解压 ZIP 得到 laws.json"""
    if JSON_PATH.exists() and JSON_PATH.stat().st_size > 10_000_000:
        print(f"  laws.json 已存在（{JSON_PATH.stat().st_size // 1024 // 1024}MB），跳过解压")
        return True
    print("解压 laws.json.zip...")
    with zipfile.ZipFile(ZIP_PATH, 'r') as zf:
        names = zf.namelist()
        print(f"  压缩包内文件: {names}")
        for name in names:
            if name.endswith(".json"):
                print(f"  提取 {name}...")
                zf.extract(name, TMP_DIR)
                extracted = TMP_DIR / name
                if extracted != JSON_PATH:
                    extracted.rename(JSON_PATH)
                break
    size_mb = JSON_PATH.stat().st_size // 1024 // 1024
    print(f"  解压完成！laws.json 大小: {size_mb}MB")
    return True

def extract_to_md():
    """从 laws.json 提取前 TARGET 条，保存为 .md"""
    print(f"\n解析 laws.json，提取前 {TARGET} 条...")
    saved = 0
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        laws = json.load(f)

    print(f"  共 {len(laws)} 条法律")

    for law in laws:
        if count() >= TARGET:
            break
        title   = (law.get("title") or "").strip()
        if not title:
            continue
        content = law.get("content") or ""

        law_type = law.get("type", "")
        office   = law.get("office", "")
        pub_date = (law.get("publish_date") or law.get("publish") or "").strip()
        status   = law.get("status", "有效")
        src_url  = law.get("url", "")

        filename = f"{clean(law_type)}_{clean(title)}.md"
        fp = SOURCES_DIR / filename
        if fp.exists():
            continue

        md  = f"# {title}\n\n"
        md += f"**类型**：{law_type}  \n"
        if office:   md += f"**发布机关**：{office}  \n"
        if pub_date: md += f"**发布/修订日期**：{pub_date}  \n"
        md += f"**效力状态**：{status}  \n"
        if src_url:  md += f"**原文链接**：{src_url}  \n"
        md += "**数据来源**：全国人大国家法律法规数据库 flk.npc.gov.cn（2023年采集）  \n"
        md += "\n---\n\n"
        if content:
            md += re.sub(r'\n{4,}', '\n\n', content)
        else:
            md += f"（{title}，来源：全国人大国家法律法规数据库）"

        try:
            fp.write_text(md, encoding="utf-8")
            saved += 1
            if saved % 50 == 0 or saved <= 5:
                print(f"  [{count():4d}] {title[:30]}")
        except Exception as e:
            print(f"  写入失败: {e}")

    print(f"\n写入完成，共 {count()} 个文件")


def main():
    print(f"当前 sources 目录：{count()} 个文件，目标 {TARGET} 个")
    print("数据来源：全国人大国家法律法规数据库（twang2218 2023年采集，22552条法律）\n")

    # Step 1: 获取 LFS 真实下载地址
    dl_url = None
    if not (ZIP_PATH.exists() and ZIP_PATH.stat().st_size > 10_000_000):
        dl_url = get_lfs_download_url()
        if not dl_url:
            print("[ERROR] 无法获取 LFS 下载地址")
            print("请手动：git lfs install && git clone https://github.com/twang2218/law-datasets.git")
            return

    # Step 2: 下载 ZIP
    if dl_url:
        if not download_zip(dl_url):
            return

    # Step 3: 解压
    if not extract_zip():
        return

    # Step 4: 提取并保存 .md
    extract_to_md()

    final = count()
    print(f"\n{'='*50}")
    print(f"完成！sources 目录共 {final} 个文件")
    if final >= TARGET:
        print(f"[OK] 已达到 {TARGET} 个目标！")
    else:
        print(f"[WARN] 实际 {final} 个（laws.json 中有效条目不足？）")


if __name__ == "__main__":
    main()
