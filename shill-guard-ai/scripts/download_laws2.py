# -*- coding: utf-8 -*-
"""
方案：从 GitHub 下载现成的中国法律语料，转成 1000 个 .md 文件
数据源1：twang2218/law-datasets（22552条法律，全国人大）
数据源2：Threekiii/Awesome-Laws（网络安全专项法规）
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

def count():
    return len(list(SOURCES_DIR.glob("*.md")))

def clean(s):
    return re.sub(r'[\\/:*?"<>|\r\n]', '_', str(s))[:60].strip()

def save_md(filename, title, meta, content):
    fp = SOURCES_DIR / filename
    if fp.exists():
        return False
    text = f"# {title}\n\n"
    for k, v in meta.items():
        if v:
            text += f"**{k}**：{v}  \n"
    text += "\n---\n\n" + content
    fp.write_text(text, encoding="utf-8")
    return True

# ============================================================
# 方案A：下载 laws.json（流式解析，避免全部加载到内存）
# 约 40MB，包含 22552 条法律全文
# ============================================================
def download_from_laws_json():
    print("=== 尝试下载 laws.json（22552条中国法律）===")
    url = "https://raw.githubusercontent.com/twang2218/law-datasets/main/law-and-regulations/laws.json"
    
    print("  正在下载（约40MB，请稍候）...")
    try:
        resp = httpx.get(url, timeout=120, follow_redirects=True)
        if resp.status_code != 200:
            print(f"  下载失败: HTTP {resp.status_code}")
            return 0
        
        laws = resp.json()
        print(f"  下载成功，共 {len(laws)} 条法律")
        saved = 0
        
        for law in laws:
            if count() >= TARGET:
                break
            title = (law.get("title") or "").strip()
            if not title:
                continue
            content = law.get("content") or law.get("body") or ""
            if not content:
                content = f"《{title}》全文"
            # 清理HTML
            content = re.sub(r'<[^>]+>', '', content)
            content = re.sub(r'&nbsp;', ' ', content)
            content = re.sub(r'\n{3,}', '\n\n', content)
            
            filename = f"law_{clean(title)}.md"
            meta = {
                "类型": law.get("type", ""),
                "发布机关": law.get("office", ""),
                "发布日期": law.get("publish_date", ""),
                "状态": law.get("status", ""),
            }
            if save_md(filename, title, meta, content):
                saved += 1
                if saved % 50 == 0:
                    print(f"  进度: {count()}/{TARGET}")
        
        print(f"  laws.json 完成，保存 {saved} 条，当前共 {count()} 个文件")
        return saved
    except Exception as e:
        print(f"  laws.json 失败: {e}")
        return 0

# ============================================================
# 方案B：克隆 Awesome-Laws 仓库里的 md 文件
# 每个法规是单独的 .md 文件
# ============================================================
def download_awesome_laws_files():
    print("=== 尝试从 Awesome-Laws 下载法规文件列表 ===")
    # 通过 GitHub API 获取文件列表（不需要 git clone）
    api = "https://api.github.com/repos/Threekiii/Awesome-Laws/git/trees/master?recursive=1"
    try:
        resp = httpx.get(api, timeout=30,
                         headers={"Accept": "application/vnd.github.v3+json"})
        if resp.status_code != 200:
            print(f"  GitHub API 失败: {resp.status_code}")
            return 0
        tree = resp.json().get("tree", [])
        md_files = [f for f in tree if f.get("path", "").endswith(".md")]
        print(f"  找到 {len(md_files)} 个 .md 文件")
        
        saved = 0
        base = "https://raw.githubusercontent.com/Threekiii/Awesome-Laws/master/"
        for f in md_files:
            if count() >= TARGET:
                break
            path = f["path"]
            name = Path(path).stem
            filename = f"awlaws_{clean(name)}.md"
            if (SOURCES_DIR / filename).exists():
                continue
            try:
                r = httpx.get(base + path, timeout=15)
                if r.status_code == 200 and len(r.text) > 100:
                    (SOURCES_DIR / filename).write_text(r.text, encoding="utf-8")
                    saved += 1
                    if saved % 20 == 0:
                        print(f"  进度: {count()}/{TARGET}")
                time.sleep(0.3)
            except Exception:
                pass
        
        print(f"  Awesome-Laws 完成，保存 {saved} 条，当前共 {count()} 个文件")
        return saved
    except Exception as e:
        print(f"  Awesome-Laws 失败: {e}")
        return 0

# ============================================================
# 方案C：从 Night-Cruise 下载 JSONL 语料
# 专为 RAG 设计的清洗语料
# ============================================================
def download_night_cruise():
    print("=== 尝试下载 Night-Cruise 法律语料（JSONL）===")
    urls = [
        "https://raw.githubusercontent.com/zararogers338-hash/Night-Cruise-Chinese-Legal-Corpus-/main/legal_corpus.jsonl",
        "https://raw.githubusercontent.com/zararogers338-hash/Night-Cruise-Chinese-Legal-Corpus-/main/corpus.jsonl",
    ]
    for url in urls:
        try:
            print(f"  尝试: {url}")
            resp = httpx.get(url, timeout=60, follow_redirects=True)
            if resp.status_code != 200:
                continue
            saved = 0
            for i, line in enumerate(resp.text.strip().split("\n")):
                if count() >= TARGET:
                    break
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    text = obj.get("text") or obj.get("content") or ""
                    if len(text) < 80:
                        continue
                    meta = obj.get("meta") or {}
                    source = meta.get("source", f"doc_{i}")
                    chunk_id = meta.get("chunk_id", str(i))
                    filename = f"nc_{clean(chunk_id)}.md"
                    if save_md(filename, source, {}, text):
                        saved += 1
                        if saved % 100 == 0:
                            print(f"  进度: {count()}/{TARGET}")
                except Exception:
                    continue
            print(f"  Night-Cruise 完成，保存 {saved} 条，当前共 {count()} 个文件")
            return saved
        except Exception as e:
            print(f"  失败: {e}")
    return 0

# ============================================================
# 方案D：CAC 网信办法规列表页面抓取
# ============================================================
def download_cac_laws():
    print("=== 从 CAC 网信办下载法规列表 ===")
    # 网信办法规列表 API
    saved = 0
    for page in range(1, 30):
        if count() >= TARGET:
            break
        url = f"https://www.cac.gov.cn/wxzw/zcfg/A093703index_{page}.htm"
        try:
            resp = httpx.get(url, timeout=15,
                             headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cac.gov.cn/"})
            if resp.status_code != 200:
                break
            # 提取链接
            links = re.findall(r'href="(/\d{4}-\d{2}/\d{2}/c_\w+\.htm)"', resp.text)
            for link in links:
                if count() >= TARGET:
                    break
                full_url = "https://www.cac.gov.cn" + link
                try:
                    r2 = httpx.get(full_url, timeout=15,
                                   headers={"User-Agent": "Mozilla/5.0"})
                    if r2.status_code != 200:
                        continue
                    # 提取标题和正文
                    title_m = re.search(r'<title>([^<]+)</title>', r2.text)
                    title = title_m.group(1).strip() if title_m else f"cac_doc_{count()}"
                    # 提取正文（去除 HTML 标签）
                    content = re.sub(r'<script[^>]*>.*?</script>', '', r2.text, flags=re.DOTALL)
                    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
                    content = re.sub(r'<[^>]+>', '', content)
                    content = re.sub(r'\s{3,}', '\n\n', content).strip()
                    if len(content) < 200:
                        continue
                    filename = f"cac_{clean(title)}.md"
                    if save_md(filename, title, {"来源": "国家互联网信息办公室"}, content[:5000]):
                        saved += 1
                        if saved % 10 == 0:
                            print(f"  进度: {count()}/{TARGET}")
                    time.sleep(0.5)
                except Exception:
                    pass
            time.sleep(1)
        except Exception as e:
            print(f"  第{page}页失败: {e}")
            break
    print(f"  CAC 完成，保存 {saved} 条，当前共 {count()} 个文件")
    return saved

def main():
    print(f"当前 sources 目录：{count()} 个文件，目标 {TARGET} 个\n")
    
    # 按优先级依次尝试各数据源
    if count() < TARGET:
        download_from_laws_json()   # 主力：22552条完整法律
    
    if count() < TARGET:
        download_awesome_laws_files()  # 补充：网络安全专项
    
    if count() < TARGET:
        download_night_cruise()    # 补充：RAG专用语料
    
    if count() < TARGET:
        download_cac_laws()        # 补充：网信办最新法规
    
    final = count()
    print(f"\n{'='*50}")
    print(f"全部完成！sources 目录共 {final} 个文件")
    if final >= TARGET:
        print(f"[OK] 已达到 {TARGET} 个目标！")
    else:
        print(f"[WARN] 实际获取 {final} 个（网络限制导致不足 {TARGET}）")

if __name__ == "__main__":
    main()
