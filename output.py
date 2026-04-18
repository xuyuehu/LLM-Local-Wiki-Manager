#!/usr/bin/env python3
"""
执行知识库输出工作流 (Outputs Workflow)。

基于全部知识库内容分析、归纳并提纯目标，从而输出到指定目录的产出文件之中。

用法:
    python tools/output.py "为下周的目标课题养殖分享会做一份报告"
    python tools/output.py --type notes "提炼一篇关于基础节点孵化的资料笔记"
    
支持指定的产物类型:
    report        — 综合分析和总结报告 (默认)
    notes         — 信息学习和整理笔记
    qa            — Q&A 集结解疑
    presentation  — 给外界演示和教学的材料大纲
"""

import os
from dotenv import load_dotenv
load_dotenv()
import sys
import argparse
from pathlib import Path
from datetime import date
import re
import json

import google.generativeai as genai

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
LOG_DIR = REPO_ROOT / "logs"
OUTPUTS_DIR = REPO_ROOT / "outputs"

INDEX_FILE = WIKI_DIR / "index.md"
WIKI_LOG = WIKI_DIR / "log.md"
SYSTEM_LOG = LOG_DIR / "log.md"


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  已生成成果目标文件: {path.relative_to(REPO_ROOT)}")


def append_log(entry: str):
    existing_wiki = read_file(WIKI_LOG)
    if existing_wiki:
        write_file(WIKI_LOG, entry.strip() + "\n\n" + existing_wiki)
    
    existing_sys = read_file(SYSTEM_LOG)
    if existing_sys:
        write_file(SYSTEM_LOG, entry.strip() + "\n\n" + existing_sys)


def build_wiki_context(question: str, model_fast) -> tuple[str, list]:
    index_content = read_file(INDEX_FILE)
    if not index_content:
        return "", []

    print("  正通过 LLM 筛选所需的参考资料...")
    prompt_select = f"""给定以下来自知识库的索引内容:\n\n{index_content}\n\n对于需要回答下述的主题或意图: "{question}"，哪些页面的知识是必须参考总结的？\n\n请**仅返回** JSON 数组格式的相关文件相对路径（例如: ["sources/foo.md", "concepts/bar.md"]），请选择多达15个最关联深邃的内容，禁止输出除此之外的任何代码或文本。"""
    
    relevant_pages = []
    try:
        selection_response = model_fast.generate_content(prompt_select)
        raw = selection_response.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        
        paths = json.loads(raw)
        relevant_pages = [WIKI_DIR / p for p in paths if (WIKI_DIR / p).exists()]
    except Exception:
        # 万一解析失败，默认带上所有能匹配到的字词页面
        md_links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', index_content)
        question_lower = question.lower()
        for title, href in md_links:
            if any(word in question_lower for word in title.lower().split() if len(word) > 1):
                p = WIKI_DIR / href
                if p.exists():
                    relevant_pages.append(p)
    
    if not relevant_pages:
        return f"\n\n### wiki/index.md\n{index_content}", []

    pages_context = ""
    for p in relevant_pages[:15]:  # 只限制最高15页作为上下文传入大容量模型
        rel = p.relative_to(REPO_ROOT)
        pages_context += f"\n\n### {rel}\n{p.read_text(encoding='utf-8')[:3000]}" # 限制单篇大小

    return pages_context, relevant_pages


def create_output(request_text: str, output_type: str):
    api_key = os.environ.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    today = date.today()
    today_iso = today.isoformat()
    month_folder = today.strftime("%Y-%m")

    model_flash = genai.GenerativeModel("gemini-2.5-flash")
    model_pro = genai.GenerativeModel("gemini-2.5-pro")

    pages_context, pages_used = build_wiki_context(request_text, model_flash)

    print(f"  正在归纳总结生成类型定性为 `{output_type}` 的长篇文章，共参考 {len(pages_used)} 篇文档。请稍候...")
    
    schema = f"""
## 文件格式要求 (重要)

输出的内容不仅需要回答内容，更应直接按标准 Obsidian 的模板结构生成。请一字不落按照该模板打底，**千万不可包裹任何 `markdown` 围栏和标记**：

---
title: "提取到的输出标题"
type: "{output_type}"
tags: [output, 输出标签1]
created: {today_iso}
---

## 概述

[此处用一百字左右概括...]

## 详细内容

[基于现有知识进行的深加工、排列及合成。应当适当将部分内容分成不同的段落与块落，在文字段内部使用双链 [[相关页面]] 指涉溯源信息。]

## 知识来源

[使用列表点列出被参考的重要知识卡]
- [[页面1]] - 简述其帮助
- [[页面2]] - 简述其帮助

## 下一步行动

[留作延展提示或规划：]
- 第一项需要深研的事物...
- ...
"""

    prompt = f"""你是一名 Obsidian 系统的高级整理工具。要求你根据提供的一小部分知识库相关切片，结合用户的任务目标完成创作归纳成果。

当前任务指示：
用户请求目标: {request_text}
请撰写一篇类型为 {output_type} 的材料。({{'report':'深度报告形式', 'notes':'笔记总结形式', 'qa':'一问一答的归总', 'presentation':'幻灯演示准备和演讲大纲'}}.get(output_type, '综合形式'))

知识库内容依据如下：
{pages_context}

模板：
{schema}

严苛遵循其结构。输出你构建的全文即可，无需致谢。
"""

    response = model_pro.generate_content(prompt)
    answer = response.text

    # 抽取文件标题作为最终的输出保存标识
    title_match = re.search(r'^title:\s*"?([^"\n]+)"?', answer, re.MULTILINE)
    if title_match:
        safe_title = re.sub(r'[^\w\u4e00-\u9fff-]', '', title_match.group(1).replace(" ", "-"))
    else:
        safe_title = "未知生成成果"

    filename = f"{today_iso}-{safe_title}.md"
    save_path = OUTPUTS_DIR / month_folder / filename

    write_file(save_path, answer)

    # 索引及系统表
    # 将 output 这一步的行为日志归拢
    append_log(f"## [{today_iso}] output | 生成 {output_type} 报告\n\n针对任务 【{request_text[:40]}】 已生成，被保存到了 {month_folder}/{filename}。")

    print(f"\n操作完成。最终成果已就绪！")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="综合输出特定格式文档报告")
    parser.add_argument("request", help="您对此份报告、输出材料的需求概述，要求其产出什么结论")
    parser.add_argument("--type", choices=["report", "notes", "qa", "presentation"], 
                        default="report", help="需要的知识输出模式。默认 report。")
    args = parser.parse_args()
    
    create_output(args.request, args.type)
