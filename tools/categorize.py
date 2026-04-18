#!/usr/bin/env python3
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
WIKI_DIR = REPO_ROOT / "wiki"
CONCEPTS_DIR = WIKI_DIR / "concepts"

MAPPING = {
    "1. 基础理论与核心概念": ["Theory", "Concept", "Fundamental"],
    "2. 技术实现与算法": ["Algorithm", "Method", "Technique"],
    "3. 业务场景与应用": ["Application", "Use Case", "Scenario"],
    "4. 行业报告与竞品分析": ["Market", "Industry", "Report"],
    "5. 待归档实体与其他": ["Misc", "Other"]
}

def determine_category(filename: str):
    for cat, keywords in MAPPING.items():
        for kw in keywords:
            if kw.lower() in filename.lower():
                return cat
    return "11. 其他核心概念"

def process_all():
    print("开始快速分类 wiki/concepts/ 目录下的概念...")
    files = list(CONCEPTS_DIR.glob("*.md"))
    total = len(files)
    
    for i, file_path in enumerate(files):
        content = file_path.read_text(encoding="utf-8")
        
        # Remove any existing category frontmatter to avoid duplicates
        content = re.sub(r'^category:.*\n', '', content, flags=re.MULTILINE)
        
        # Identify category
        category = determine_category(file_path.name)
        print(f"[{i+1}/{total}] {file_path.name} -> {category}")
        
        # Inject category
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                frontmatter = frontmatter.rstrip() + f'\ncategory: "{category}"\n'
                new_content = f"---{frontmatter}---{parts[2]}"
                file_path.write_text(new_content, encoding="utf-8")
            else:
                pass
        else:
            new_frontmatter = f"---\ntitle: \"{file_path.stem}\"\ncategory: \"{category}\"\n---\n"
            file_path.write_text(new_frontmatter + content, encoding="utf-8")
            
    print("全部分类处理完成！")

if __name__ == "__main__":
    process_all()
