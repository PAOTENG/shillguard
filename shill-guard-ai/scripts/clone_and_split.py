# -*- coding: utf-8 -*-
"""
从 GitHub twang2218/law-datasets 克隆已整理的国家法律法规数据
该数据集于 2023 年从 flk.npc.gov.cn 官方下载，22,552 条法律全文
克隆后从 laws.json 中提取，保存为 1000 个 .md 文件
"""
import io, sys, json, re, subprocess
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SOURCES_DIR = Path("D:/Projects/shill-guard-ai/app/rag/sources")
CLONE_DIR   = Path("D:/Projects/shill-guard-ai/scripts/law_tmp")
TARGET = 1000

SOURCES_DIR.mkdir(parents=True, exist_ok=True)
CLONE_DIR.mkdir(parents=True, exist_ok=True)

def count():
    return len(list(SOURCES_DIR.glob("*.md")))

def clean(s):
    return re.sub(r'[\\/:*?"<>|\r\n\t]', '_', str(s))[:60].strip()

def extract_from_json(json_path: Path):
    print(f"解析 {json_path.name}（可能较大，请稍候）...")
    with open(json_path, "r", encoding="utf-8") as f:
        laws = json.load(f)
    print(f"共 {len(laws)} 条法律，开始写入 .md 文件...")
    saved = 0
    for law in laws:
        if count() >= TARGET:
            break
        title = (law.get("title") or "").strip()
        if not title:
            continue
        content = law.get("content") or ""
        content = re.sub(r'\n{4,}', '\n\n', content)

        law_type = law.get("type", "")
        office   = law.get("office", "")
        pub_date = law.get("publish_date", "") or law.get("publish", "")
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
        md += "**来源**：全国人大国家法律法规数据库（2023年采集）  \n"
        md += "\n---\n\n"
        md += content if content else f"（{title}）"

        try:
            fp.write_text(md, encoding="utf-8")
            saved += 1
            if saved % 100 == 0:
                print(f"  进度：{count()}/{TARGET}")
        except Exception as e:
            print(f"  写入失败：{e}")

    print(f"写入完成，共 {count()} 个文件")

def main():
    print(f"当前 sources 目录：{count()} 个文件，目标 {TARGET} 个\n")

    laws_json = CLONE_DIR / "law-datasets" / "law-and-regulations" / "laws.json"

    if laws_json.exists():
        print("已有本地 laws.json，直接解析")
        extract_from_json(laws_json)
    else:
        print("开始克隆 twang2218/law-datasets...")
        print("（数据来源：全国人大 flk.npc.gov.cn，2023年官方采集，22552条法律）\n")

        repo_url = "https://github.com/twang2218/law-datasets.git"
        clone_cmd = [
            "git", "clone",
            "--depth", "1",          # 只克隆最新版本（省带宽）
            "--filter=blob:none",    # 不下载文件内容（sparse）
            repo_url,
            str(CLONE_DIR / "law-datasets")
        ]
        print(f"执行: {' '.join(clone_cmd)}")
        result = subprocess.run(clone_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"克隆失败（尝试完整克隆）: {result.stderr}")
            # 降级：完整克隆
            clone_cmd2 = ["git", "clone", "--depth", "1",
                          repo_url, str(CLONE_DIR / "law-datasets")]
            result2 = subprocess.run(clone_cmd2, capture_output=True, text=True)
            if result2.returncode != 0:
                print(f"完整克隆也失败: {result2.stderr}")
                print("\n请手动执行：")
                print(f"  git clone --depth 1 {repo_url} {CLONE_DIR / 'law-datasets'}")
                print("然后重新运行此脚本")
                return
        print("克隆成功！")

        # checkout 实际文件
        checkout_cmd = [
            "git", "-C", str(CLONE_DIR / "law-datasets"),
            "sparse-checkout", "set", "law-and-regulations/"
        ]
        subprocess.run(checkout_cmd, capture_output=True)
        subprocess.run(
            ["git", "-C", str(CLONE_DIR / "law-datasets"), "checkout"],
            capture_output=True
        )

        if laws_json.exists():
            print(f"laws.json 已就绪（{laws_json.stat().st_size // 1024 // 1024}MB）")
            extract_from_json(laws_json)
        else:
            print(f"[WARN] laws.json 不在预期路径：{laws_json}")
            # 查找 json 文件
            jsons = list((CLONE_DIR / "law-datasets").rglob("*.json"))
            print(f"  找到的 JSON 文件：{[str(j) for j in jsons]}")

    final = count()
    print(f"\n{'='*50}")
    print(f"完成！sources 目录共 {final} 个文件")
    if final >= TARGET:
        print(f"[OK] 已达到 {TARGET} 个目标！")
    else:
        print(f"[WARN] 实际 {final} 个")

if __name__ == "__main__":
    main()
