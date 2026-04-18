#!/usr/bin/env python3
"""
NC-BSF NotebookLM 导出与同步脚本
此脚本收集分散的知识库 Markdown，编译成极其干要的大文件，
以适应 Google NotebookLM 单个大文件的摄入喜好，并直接推送到本地 Google Drive。
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
GDrive_TARGET = Path("/Users/apple/Google Drive/我的云端硬盘/NC-BSF")

def build_overview_bundle():
    print("正在构建 [01-综合概览]...")
    parts = []
    
    index_file = WIKI_DIR / "index.md"
    if index_file.exists():
        parts.append(index_file.read_text(encoding="utf-8"))
        
    overview_file = WIKI_DIR / "overview.md"
    if overview_file.exists():
        parts.append(overview_file.read_text(encoding="utf-8"))
        
    return "\n\n---\n\n".join(parts)

def build_concepts_bundle():
    print("正在构建 [02-核心概念辞典]...")
    parts = ["# NC-BSF 核心概念百科全书\n\n"]
    concepts_dir = WIKI_DIR / "concepts"
    
    # 按照分类文件夹进行归拢
    if concepts_dir.exists():
        for category_dir in sorted(concepts_dir.iterdir()):
            if category_dir.is_dir():
                parts.append(f"## {category_dir.name}\n")
                for md_file in sorted(category_dir.glob("*.md")):
                    parts.append(f"### {md_file.stem}\n")
                    parts.append(md_file.read_text(encoding="utf-8"))
                    parts.append("\n\n---\n\n")
    return "".join(parts)

def build_sources_bundle():
    print("正在构建 [03-资料摘要文献集]...")
    parts = ["# NC-BSF 原始资料全量摘要\n\n"]
    sources_dir = WIKI_DIR / "sources"
    
    if sources_dir.exists():
        for md_file in sorted(sources_dir.glob("*.md")):
            # 去除文件开头多余的横线，使其更好融入主文档
            content = md_file.read_text(encoding="utf-8")
            parts.append(content)
            parts.append("\n\n#############################################\n\n")
    return "".join(parts)

def export():
    # 检查或新建 Google Drive 中的目标路径
    if not GDrive_TARGET.exists():
        print(f"正在本地 Google Drive 中创建目标文件夹: {GDrive_TARGET}")
        GDrive_TARGET.mkdir(parents=True, exist_ok=True)
        
    # 构建内容
    content_overview = build_overview_bundle()
    content_concepts = build_concepts_bundle()
    content_sources = build_sources_bundle()
    
    # 输出到目标
    if content_overview.strip():
        out1 = GDrive_TARGET / "NC-BSF-01-综合概览.md"
        out1.write_text(content_overview, encoding="utf-8")
        print(f"✅ 生成成功 -> {out1.name}")
        
    if content_concepts.strip() != "# NC-BSF 核心概念百科全书\n\n":
        out2 = GDrive_TARGET / "NC-BSF-02-核心概念辞典.md"
        out2.write_text(content_concepts, encoding="utf-8")
        print(f"✅ 生成成功 -> {out2.name}")
        
    if content_sources.strip() != "# NC-BSF 原始资料全量摘要\n\n":
        out3 = GDrive_TARGET / "NC-BSF-03-资料摘要文献集.md"
        out3.write_text(content_sources, encoding="utf-8")
        print(f"✅ 生成成功 -> {out3.name}")

    print(f"\n🎉 同步全量完成！所有知识结晶已被静默投递至: {GDrive_TARGET}")
    print("👉 (Mac 系统的 Google Drive 客户端通常会在后台于几秒内将其自动漫游至云端，供您的 NotebookLM 享用。)")

if __name__ == "__main__":
    export()
