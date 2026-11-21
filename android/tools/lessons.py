"""从桌面图解与积木字典取出适合离线制卡的教学内容。"""
import re
import shutil
from pathlib import Path

BOOK = Path(__file__).resolve().parents[2] / "diy_workbench" / "handbook"
DESKTOP_ONLY = re.compile(r"MDPro|沙盒|脚本|伊格尼斯|\bLua\b|引擎|检查页|执行详情", re.I)


def lessons(output):
    diagrams = output / "fig"
    diagrams.mkdir(exist_ok=True)
    chapters = []
    for topic in ("基础", "召唤", "判定"):
        text = (BOOK / f"规则-{topic}.md").read_text("utf-8")
        for chapter in re.split(r"^## ", text, flags=re.M)[1:]:
            title, body = chapter.strip().split("\n", 1)
            sections = []
            for paragraph in body.strip().split("\n\n"):
                if DESKTOP_ONLY.search(paragraph):
                    continue
                match = re.fullmatch(r"!\[([^]]*)\]\(图/(.+?\.svg)\)", paragraph.strip())
                if match:
                    alt, name = match.groups()
                    shutil.copyfile(BOOK / "图" / name, diagrams / name)
                    sections.append({"image": "fig/" + name, "alt": alt})
                else:
                    text = re.sub(r"\[([^]]+)\]\(https?://[^)]+\)", r"\1", paragraph)
                    sections.append({"text": text.replace("**", "").strip()})
            chapters.append({"group": topic, "title": title, "body": sections})
    return chapters


def block_help():
    entries = {}
    for path in BOOK.glob("积木-*.txt"):
        for line in path.read_text("utf-8").splitlines():
            parts = line.split("|")
            if len(parts) == 4:
                entries[parts[0]] = [s for s in parts[1:] if s and not DESKTOP_ONLY.search(s)]
    return entries
