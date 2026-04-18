#!/usr/bin/env python3
"""
查询 LLM 知识库并进行综合分析。

用法:
    python tools/query.py "关于目标课题的主要研究成果有哪些？"
    python tools/query.py "昆虫蛋白与常见饲料有什么区别？" --save
    python tools/query.py "总结所有的核心研究节点" --save syntheses/my-analysis.md

参数与标记:
    --save              将答案保存回知识库的 syntheses 目录（提示输入文件名）
    --save <path>       将答案保存到知识库特定路径
"""

import os
from dotenv import load_dotenv
load_dotenv()
import sys
import re
import json
import argparse
from pathlib import Path
from datetime import date

import google.generativeai as genai

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
LOG_DIR = REPO_ROOT / "logs"

INDEX_FILE = WIKI_DIR / "index.md"
WIKI_LOG = WIKI_DIR / "log.md"
SYSTEM_LOG = LOG_DIR / "log.md"


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  已保存: {path.relative_to(REPO_ROOT)}")


def find_relevant_pages(question: str, index_content: str) -> list[Path]:
    """通过匹配关键字从索引提取可能相关的页面."""
    md_links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', index_content)
    question_lower = question.lower()
    relevant = []
    for title, href in md_links:
        # 简单字词匹配
        if any(word in question_lower for word in title.lower().split() if len(word) > 1):
            p = WIKI_DIR / href
            if p.exists():
                relevant.append(p)
    
    overview = WIKI_DIR / "overview.md"
    if overview.exists() and overview not in relevant:
        relevant.insert(0, overview)
    return relevant[:12]  # 最多使用 12 个页面，防止超长上下文


def append_log(entry: str):
    existing_wiki = read_file(WIKI_LOG)
    write_file(WIKI_LOG, entry.strip() + "\n\n" + existing_wiki)
    existing_sys = read_file(SYSTEM_LOG)
    write_file(SYSTEM_LOG, entry.strip() + "\n\n" + existing_sys)


def query(question: str, save_path: str | None = None):
    api_key = os.environ.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    today = date.today().isoformat()
    model_haiku = genai.GenerativeModel("gemini-2.5-flash") # 使用小模型进行快速决策
    model_sonnet = genai.GenerativeModel("gemini-2.5-pro") # 使用大模型进行深度综合

    index_content = read_file(INDEX_FILE)
    if not index_content:
        print("知识库当前为空，先使用: python tools/ingest.py <源文件> 进行资料提取。")
        sys.exit(1)

    relevant_pages = find_relevant_pages(question, index_content)

    if not relevant_pages or len(relevant_pages) <= 1:
        print("  正在通过 LLM 分析索引以确定关联文件...")
        prompt_select = f"""给定以下来自知识库的索引内容:\n\n{index_content}\n\n对于回答下述问题: "{question}"，哪些页面最具关联性？\n\n请**仅返回** JSON 数组格式的相关文件相对路径（即在索引中包含的路径），例如: ["sources/foo.md", "concepts/bar.md"]。最多选择10个文件，不得输出除此之外的文本。"""
        
        try:
            selection_response = model_haiku.generate_content(prompt_select)
            raw = selection_response.text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            
            paths = json.loads(raw)
            relevant_pages = [WIKI_DIR / p for p in paths if (WIKI_DIR / p).exists()]
        except Exception:
            pass

    pages_context = ""
    for p in relevant_pages:
        rel = p.relative_to(REPO_ROOT)
        pages_context += f"\n\n### {rel}\n{p.read_text(encoding='utf-8')}"

    if not pages_context:
        pages_context = f"\n\n### wiki/index.md\n{index_content}"

    schema = """
建议的回答格式：
根据知识库内容，关于[主题]的信息如下：
1. 主要观点...
    - 支持证据：[[相关页面1]]
    - 详细说明：[[相关页面2]]
2. 相关知识...
    - [[概念A]]与此相关
    - [[概念B]]提供补充
3. 如有矛盾之处...
    - [[页面X]]与[[页面Y]]在...方面存在差异
"""

    print(f"  正在综合 {len(relevant_pages)} 个知识库页面的内容以生成回答...")
    
    prompt_answer = f"""你正在查询一个基于本地 Markdown 构建的 LLM 知识库系统，你需要综合以下相关页面的内容，针对用户的给定问题进行详尽、客观和准确的总结解答。

必须遵循的指引：
{schema}
在文本内使用 Obsidian 的双链引用规范 [[页面名称]] 指明信息出处。

知识库页面内容:
{pages_context}

用户问题: {question}

请用 Markdown 撰写一篇结构良好、包含标题、项目列表以及内联 [[wikilink]] 双链引用的回答。并在结尾附上一节「## 相关来源」列出本答案借用的主要资料。
"""

    response = model_sonnet.generate_content(prompt_answer)
    answer = response.text
    
    print("\n" + "=" * 60)
    print(answer)
    print("=" * 60)

    if save_path is not None:
        if save_path == "":
            slug = input("\n请指定要保存的文件名 (例如 'my-analysis'): ").strip()
            if not slug:
                print("取消保存。")
                return
            save_path = f"syntheses/{slug}.md"

        full_save_path = WIKI_DIR / save_path
        frontmatter = f"""---
title: "{question[:80]}"
type: synthesis
tags: [synthesis, query]
last_updated: {today}
---

"""
        write_file(full_save_path, frontmatter + answer)

        index_content = read_file(INDEX_FILE)
        entry = f"- [{question[:60]}]({save_path}) - 综合分析问答"
        if "## 综合分析" in index_content:
            index_content = index_content.replace("## 综合分析\n", f"## 综合分析\n{entry}\n")
            INDEX_FILE.write_text(index_content, encoding="utf-8")
        print(f"  已将该分析加入索引: {save_path}")

    append_log(f"## [{today}] query | {question[:80]}\n\n综合作答，共参考 {len(relevant_pages)} 个相关页面。" +
               (f" 结果已保存至 {save_path}。" if save_path else ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="综合查询知识库")
    parser.add_argument("question", help="待解答的详细问题")
    parser.add_argument("--save", nargs="?", const="", default=None,
                        help="将回答存储到 wiki 知识库 (也可直接指定如 'syntheses/topic.md')")
    args = parser.parse_args()
    query(args.question, args.save)
