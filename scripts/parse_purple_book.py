#!/usr/bin/env python3
"""解析本体论紫皮书 PDF 提取文本 → 结构化 Markdown。

输入：.purple_book_extracted/pages/page_XXXX.txt（由 pdf skill 的 extract_pages.py 产出）
处理：去页眉页脚 / NFKC 归一化（康熙部首 → 常规汉字）/ 章节标题识别
输出：刘焕勇.老刘说NLP技术社区.本体论紫皮书：四.md
"""
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = ROOT / ".purple_book_extracted" / "pages"
OUT_FILE = ROOT / "刘焕勇.老刘说NLP技术社区.本体论紫皮书：四.md"

HEADER_RE = re.compile(r"^2026/\d+/\d+ \d+:\d+ .{0,40}$")
FOOTER_RE = re.compile(r"^file:///.*\d+/153\s*$")
PART_RE = re.compile(r"^第[一二三四五六七八九十]+部分$")
CHAPTER_RE = re.compile(r"^第.{1,3}章(\s*·\s*.*)?$")
SECTION_RE = re.compile(r"^(\d{1,2}\.\d{1,2})\s*(\S.*)$")


def clean_page(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = unicodedata.normalize("NFKC", raw).strip()
        if not line:
            lines.append("")
            continue
        if HEADER_RE.match(line) or FOOTER_RE.match(line):
            continue
        if re.fullmatch(r"\d{1,3}/153", line):
            continue
        lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def to_markdown(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        if PART_RE.match(line):
            out.append(f"\n## {line}\n")
        elif CHAPTER_RE.match(line):
            out.append(f"\n### {line}\n")
        else:
            m = SECTION_RE.match(line)
            if m and len(m.group(2)) > 4:
                out.append(f"\n#### {m.group(1)} {m.group(2)}\n")
            else:
                out.append(line)
    return out


def main():
    files = sorted(PAGES_DIR.glob("page_*.txt"))
    if not files:
        raise SystemExit(f"no page files in {PAGES_DIR}")

    md = [
        "# 本体论紫皮书：四种 Ontology 的技术本质、实践案例与选型决策",
        "",
        "> 作者：老刘说NLP技术社区 · 刘焕勇（liuhuanyong）· 2026 年 8 月 第一版",
        "> 本文档由 PDF 脚本解析生成（scripts/parse_purple_book.py），仅供项目内部参考。",
        "",
    ]
    for i, f in enumerate(files, 1):
        lines = clean_page(f.read_text(encoding="utf-8"))
        md.extend(to_markdown(lines))
        if i < len(files):
            md.append("")
            md.append(f"<!-- page {i} -->")
            md.append("")

    OUT_FILE.write_text("\n".join(md), encoding="utf-8")
    size_kb = OUT_FILE.stat().st_size / 1024
    print(f"OK: {len(files)} pages -> {OUT_FILE.name} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
