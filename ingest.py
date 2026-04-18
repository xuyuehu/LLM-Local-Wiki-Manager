#!/usr/bin/env python3
"""
将源文档提取并纳入 LLM 知识库。

用法:
    python tools/ingest.py <源文件路径>
    python tools/ingest.py raw/articles/my-article.md

工作流执行:
  - 阅读源文档及 wiki 上下文
  - 创建 wiki/sources/<slug>.md (源文档摘要页)
  - 创建或更新概念页面 wiki/concepts/
  - 更新 wiki/index.md
  - 更新 wiki/overview.md
  - 标记可能的冲突
  - 在 wiki/log.md 以及 logs/log.md 追加记录
"""

import os
from dotenv import load_dotenv
load_dotenv()
import sys
import json
import hashlib
import re
import warnings
from pathlib import Path
from datetime import date

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", module="google")
warnings.filterwarnings("ignore", module="urllib3")

import google.generativeai as genai

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
LOG_DIR = REPO_ROOT / "logs"

WIKI_LOG = WIKI_DIR / "log.md"
SYSTEM_LOG = LOG_DIR / "log.md"
INDEX_FILE = WIKI_DIR / "index.md"
OVERVIEW_FILE = WIKI_DIR / "overview.md"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  已保存: {path.relative_to(REPO_ROOT)}")


def build_wiki_context() -> str:
    parts = []
    if INDEX_FILE.exists():
        parts.append(f"## wiki/index.md\n{read_file(INDEX_FILE)}")
    if OVERVIEW_FILE.exists():
        parts.append(f"## wiki/overview.md\n{read_file(OVERVIEW_FILE)}")
    # 包含几个近期的 sources 页面以检查矛盾
    sources_dir = WIKI_DIR / "sources"
    if sources_dir.exists():
        recent = sorted(sources_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
        for p in recent:
            parts.append(f"## {p.relative_to(REPO_ROOT)}\n{p.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(parts)


def parse_json_from_response(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("API 响应中未找到 JSON 对象")
    return json.loads(match.group())


def update_index(new_entry: str, section: str = "源文档"):
    content = read_file(INDEX_FILE)
    if not content:
        content = "# 知识库索引\n\n## 概览\n- [综合概览](overview.md) - 跨所有资料的动态综合\n\n## 源文档\n\n## 概念\n\n## 综合分析\n\n## 最近更新\n"
    section_header = f"## {section}"
    if section_header in content:
        content = content.replace(section_header + "\n", section_header + "\n" + new_entry + "\n")
    else:
        content += f"\n{section_header}\n{new_entry}\n"
    write_file(INDEX_FILE, content)


def append_log(entry: str):
    # 追加到 wiki/log.md
    existing_wiki = read_file(WIKI_LOG)
    write_file(WIKI_LOG, entry.strip() + "\n\n" + existing_wiki)
    
    # 追加到 logs/log.md
    existing_sys = read_file(SYSTEM_LOG)
    write_file(SYSTEM_LOG, entry.strip() + "\n\n" + existing_sys)


def extract_text_from_file(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            import pdfplumber
            text = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text.append(page_text)
            return "\n".join(text)
        except ImportError:
            print("警告: 缺少 pdfplumber 库，尝试继续但无法正确读取 PDF。请使用 pip install pdfplumber 安装。")
            return ""
        except Exception as e:
            print(f"读取 PDF 出错: {e}")
            return ""
    else:
        return read_file(path)


def ingest(source_path: str):
    api_key = os.environ.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)

    source = Path(source_path)
    if not source.exists():
        print(f"错误: 找不到文件 {source_path}")
        sys.exit(1)

    source_content = extract_text_from_file(source)
    if not source_content.strip():
        print(f"错误: 无法从 {source.name} 提取到有意义的文字，跳过解析。")
        return False

    source_hash = sha256(source_content)
    today = date.today().isoformat()

    print(f"\n正在提取知识: {source.name} (哈希: {source_hash})")

    wiki_context = build_wiki_context()

    schema = """
## 页面格式要求

建议每个源文档摘要页使用如下格式：

---
title: "源文档标题"
tags: [source, 主题标签]
date: YYYY-MM-DD
source_file: raw/[路径]/[文件名]
---

## 摘要
2-4句话的摘要。

## 核心观点
- 观点1
- 观点2

## 关键引用
> "引用内容" - 上下文说明

## 关联概念
- [[概念1]] - 关联方式说明
- [[概念2]] - 关联方式说明

## 潜在矛盾
- 与[[其他页面]]在以下方面存在矛盾：...
"""

    prompt = f"""你是一个运行在 Obsidian 环境下的知识库 AI 管理员。请阅读给定的原始文档材料，并将其知识提取到现有的知识库体系中。

模式和约定：
{schema}

当前的知识库上下文 (包含索引与近期页面):
{wiki_context if wiki_context else "(目前知识库为空 — 这是第一篇文档)"}

需要提取的新文档 (路径: {source.relative_to(REPO_ROOT) if source.is_relative_to(REPO_ROOT) else source.name}):
=== 文档开始 ===
{source_content}
=== 文档结束 ===

今天的日期：{today}

**必须且只能以合法的 JSON 格式返回结果（禁止任何外部文本或 markdown 代码块的包裹）**。使用的 JSON 必须符合以下结构，并包含详细的内容：
{{
  "title": "源文档的人类可读标题",
  "slug": "文件名对应的kebab-case标识符",
  "source_page": "完整的 wiki/sources/<slug>.md markdown 页面内容（严格遵循给定的『源文档页面格式』结构）",
  "index_entry": "- [源文档标题](sources/slug.md) - 一行摘要",
  "overview_update": "完整的修订后的 wiki/overview.md 内容（概览跨多个资料的全局综合总结）。如果当前无需更新，返回 null",
  "concept_pages": [
    {{"path": "concepts/概念名称.md", "content": "完整的概念页面 markdown 内容。格式应包含 tags、last_updated、核心概念解释及其他链接。"}}
  ],
  "contradictions": ["描述新材料与现有库内容在事实上的任何矛盾，若无则返回空列表"],
  "log_entry": "## [{today}] ingest | <title>\\n\\n添加了源文档并提取了核心观点。..."
}}
"""

    print("  请求 Gemini API 中...")
    model = genai.GenerativeModel("gemini-2.5-pro")
    
    try:
        response = model.generate_content(prompt)
        raw = response.text
        data = parse_json_from_response(raw)
    except Exception as e:
        print(f"调用 API 或解析模型输出失败: {e}")
        try:
            raw_text = response.text if 'response' in locals() else "None"
            Path("/tmp/ingest_debug.txt").write_text(raw_text)
            print("错误信息已保存至 /tmp/ingest_debug.txt")
        except:
             pass
        sys.exit(1)

    # 写入源文件摘要页
    slug = data["slug"]
    write_file(WIKI_DIR / "sources" / f"{slug}.md", data["source_page"])

    # 写入概念页面 (concepts)
    for page in data.get("concept_pages", []):
        write_file(WIKI_DIR / page["path"], page["content"])

    # 更新全局概览 (overview)
    if data.get("overview_update"):
        write_file(OVERVIEW_FILE, data["overview_update"])

    # 更新索引 (index)
    update_index(data["index_entry"], section="源文档")

    # 维护更新日志表
    update_index(f"- [{today}] 更新了源文档和相关概念页 - 提取自 {data['title']}", section="最近更新")

    # 追加详细操作日志
    append_log(data["log_entry"])

    # 反馈任何逻辑矛盾
    contradictions = data.get("contradictions", [])
    if contradictions:
        print("\n  ⚠️ 检测到内容矛盾:")
        for c in contradictions:
            print(f"     - {c}")

    print(f"\n完成。成功提取文档: {data['title']}")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python tools/ingest.py <源文件路径或包含新文件的文件夹路径>")
        sys.exit(1)
    
    target_path = Path(sys.argv[1])
    
    # 自动帮用户创建常用的批量收集文件夹（如果不存在的话）
    if not target_path.exists() and "new" in target_path.name:
        target_path.mkdir(parents=True, exist_ok=True)
        print(f"提示: 已为您自动创建了接收文件夹 {target_path}")
        print("请将收集到的所有新 .md 资料放进该文件夹后，重新运行此命令！")
        sys.exit(0)
    
    if target_path.is_file():
        ingest(str(target_path))
    elif target_path.is_dir():
        import shutil
        raw_dir = REPO_ROOT / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        
        md_files = list(target_path.rglob("*.md"))
        pdf_files = list(target_path.rglob("*.pdf"))
        # 同时支持大小写后缀
        PDF_files = list(target_path.rglob("*.PDF"))
        MD_files = list(target_path.rglob("*.MD"))
        all_files = md_files + MD_files + pdf_files + PDF_files
        
        if not all_files:
             print(f"文件夹 {target_path} 中没有找到任何 .md 或 .pdf 资料。")
             sys.exit(0)
             
        print(f"在 {target_path} 中找到 {len(all_files)} 个新资料，开始批量处理...")
        for count, f_path in enumerate(all_files, 1):
             print(f"\n[{count}/{len(all_files)}] ----------------------------------------")
             success = ingest(str(f_path))
             
             # 处理完成后，如果文件成功解析且不在 raw 的根目录下，则通过关键词路由法则将其放入特定的分类文件夹中
             if success and f_path.parent.resolve() != raw_dir.resolve():
                 try:
                     import sys
                     tools_dir = Path(__file__).parent.resolve()
                     if str(tools_dir) not in sys.path:
                         sys.path.append(str(tools_dir))
                     import organize_raw
                     cat = organize_raw.determine_category(f_path.name)
                 except Exception as e:
                     cat = ""
                 
                 target_dir = raw_dir / cat if cat else raw_dir
                 target_dir.mkdir(parents=True, exist_ok=True)
                 
                 dest = target_dir / f_path.name
                 # 处理重名
                 counter = 1
                 while dest.exists():
                     dest = target_dir / f"{f_path.stem}_{counter}{f_path.suffix}"
                     counter += 1
                 shutil.move(str(f_path), str(dest))
                 
                 if cat:
                     print(f"✅ 已将源文件 {f_path.name} 自动归档至细分类目 raw/{cat}/ 下。")
                 else:
                     print(f"✅ 已将源文件 {f_path.name} 自动归档至 raw/ 根目录。")
             elif not success:
                 print(f"⚠️ 解析跳过或中断，文件 {f_path.name} 仍保留在 {target_path} 目录中等待修复。")
                 
        print("\n🎉 批量录入工作流全部执行完毕！")
    else:
        print(f"错误: 找不到路径 {target_path}")
        sys.exit(1)
