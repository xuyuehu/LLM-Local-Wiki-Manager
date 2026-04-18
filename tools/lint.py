#!/usr/bin/env python3
"""
检查 LLM 知识库（Wiki）的健康状态。

用法:
    python tools/lint.py
    python tools/lint.py --save          # 生成报告并保存到 wiki/lint-report.md

检查内容:
  - 孤立页面 (没有任何 wiki 入站链接)
  - 断裂链接 (指向了不存在的页面)
  - 缺少的概念页 (某个概念被提到了 3+ 次却没有创建专有的分类页)
  - 内容事实层面的矛盾
  - 数据缺口及过时的总结
"""

import re
import sys
import os
from dotenv import load_dotenv
load_dotenv()
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import date

import google.generativeai as genai

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
LOG_DIR = REPO_ROOT / "logs"

WIKI_LOG = WIKI_DIR / "log.md"
SYSTEM_LOG = LOG_DIR / "log.md"


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def all_wiki_pages() -> list[Path]:
    return [p for p in WIKI_DIR.rglob("*.md")
            if p.name not in ("index.md", "log.md", "lint-report.md")]


def extract_wikilinks(content: str) -> list[str]:
    return re.findall(r'\[\[([^\]]+)\]\]', content)


def page_name_to_path(name: str) -> list[Path]:
    candidates = []
    for p in all_wiki_pages():
        if p.stem.lower() == name.lower() or p.stem == name:
            candidates.append(p)
    return candidates


def find_orphans(pages: list[Path]) -> list[Path]:
    inbound = defaultdict(int)
    for p in pages:
        content = read_file(p)
        for link in extract_wikilinks(content):
            resolved = page_name_to_path(link)
            for r in resolved:
                inbound[r] += 1
    return [p for p in pages if inbound[p] == 0 and p != WIKI_DIR / "overview.md"]


def find_broken_links(pages: list[Path]) -> list[tuple[Path, str]]:
    broken = []
    for p in pages:
        content = read_file(p)
        for link in extract_wikilinks(content):
            if not page_name_to_path(link):
                broken.append((p, link))
    return broken


def find_missing_concepts(pages: list[Path]) -> list[str]:
    """如某个概念被双链引用达到 3 次以上，却没有独立的 MD 文件，进行提示."""
    mention_counts: dict[str, int] = defaultdict(int)
    existing_pages = {p.stem.lower() for p in pages}
    for p in pages:
        content = read_file(p)
        links = extract_wikilinks(content)
        for link in links:
            if link.lower() not in existing_pages:
                mention_counts[link] += 1
    return [name for name, count in mention_counts.items() if count >= 3]


def run_lint():
    pages = all_wiki_pages()
    today = date.today().isoformat()

    if not pages:
        print("当前知识库为空，暂无检查内容。")
        return ""

    print(f"正在诊断 {len(pages)} 篇知识库页面的健康状态...")

    # 1. 结构化自动检测
    orphans = find_orphans(pages)
    broken = find_broken_links(pages)
    missing_concepts = find_missing_concepts(pages)

    print(f"  > 检测到 {len(orphans)} 个孤立页面")
    print(f"  > 检测到 {len(broken)} 个断裂的无效双链")
    print(f"  > 检测到 {len(missing_concepts)} 个高频提及但缺失的概念页")

    sample = pages[:20]
    pages_context = ""
    for p in sample:
        rel = p.relative_to(REPO_ROOT)
        pages_context += f"\n\n### {rel}\n{read_file(p)[:1500]}" 

    # 2. 语义逻辑化检测
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("未检测到 GEMINI_API_KEY 环境变量，已跳过基于 LLM 的语义冲突检查。")
        semantic_report = "*LLM 逻辑检测由于缺少 API KEY 已跳过。*"
    else:
        print("  > 正在调用 Gemini 寻找页面间的事实矛盾与数据缺口...")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-pro")
        
        prompt = f"""你是一位 Obsidian 本地知识库的 AI 检测专家。请阅读随机抽样提供的一组知识库文件，并指出其中可能存在的问题。
关注以下几个方面：
1. **内容矛盾**：不同页面中的声明是否存在冲突与悖论？
2. **过时摘要**：有没有看起来已经被新页面覆盖却还停留在旧事实的文字？
3. **数据缺口**：本知识库当前似乎欠缺或无法解答什么核心信息？可提供收集新材料的建议。
4. **不足概念**：有哪些只提及了一点而明显需要创建专页做深度的条目？

评估内容（{len(sample)} 篇文件样本）:
{pages_context}

请使用以下格式返回中文报告内容：
## 内容矛盾
## 过时内容与摘要
## 数据缺口与新源文档建议
## 页面深度与扩写建议

在说明时必须指明涉及的具体事实或文件。
"""
        response = model.generate_content(prompt)
        semantic_report = response.text


    report_lines = [
        f"# 知识库健康诊断报告 (Lint Report) — {today}",
        "",
        f"本次扫描文件总数: {len(pages)}",
        "",
        "## 结构化健康状态",
        "",
    ]

    if orphans:
        report_lines.append("### 孤立页面 (无任何页面链接至它)")
        for p in orphans:
            report_lines.append(f"- `{p.relative_to(REPO_ROOT)}`")
        report_lines.append("")

    if broken:
        report_lines.append("### 断裂链接 (双链指向不存在的文件)")
        for page, link in broken:
            report_lines.append(f"- `{page.relative_to(REPO_ROOT)}` 包含链向 `[[{link}]]` ，但该文件不存在。")
        report_lines.append("")

    if missing_concepts:
        report_lines.append("### 频繁提及却缺如的概念页 (被关联超过3次以上)")
        for name in missing_concepts:
            report_lines.append(f"- `[[{name}]]`")
        report_lines.append("")

    if not orphans and not broken and not missing_concepts:
        report_lines.append("✓ 在结构上极其健康，没有发现任何双链问题或孤立节点。")
        report_lines.append("")

    report_lines.append("---")
    report_lines.append("")
    report_lines.append(semantic_report)

    report = "\n".join(report_lines)
    print("\n" + report)
    return report


def append_log(entry: str):
    existing_wiki = read_file(WIKI_LOG)
    write_file(WIKI_LOG, entry.strip() + "\n\n" + existing_wiki)
    existing_sys = read_file(SYSTEM_LOG)
    write_file(SYSTEM_LOG, entry.strip() + "\n\n" + existing_sys)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="环境与知识库健康检查Lint工具")
    parser.add_argument("--save", action="store_true", help="保存诊断报告为 wiki/lint-report.md")
    args = parser.parse_args()

    report = run_lint()

    if args.save and report:
        report_path = WIKI_DIR / "lint-report.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"\n已将报告保存为: {report_path.relative_to(REPO_ROOT)}")

    today = date.today().isoformat()
    append_log(f"## [{today}] lint | 知识库健康扫描\n\n执行了分析诊断，共发现了如报告所示的结构与语义状态。")
