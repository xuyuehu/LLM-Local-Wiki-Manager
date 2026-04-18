#!/usr/bin/env python3
import os
import re
import shutil
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
    return "12. 其他核心概念"

def process_all():
    print("开始组织 wiki/concepts/ 概念到子文件夹...")
    
    # 查找所有的 .md (包括可能已经在子目录中的, 虽然目前没有)
    files = list(CONCEPTS_DIR.rglob("*.md"))
    total = len(files)
    
    moves = 0
    for file_path in files:
        if file_path.name in ["index.md", "log.md"]:
            continue
            
        content = file_path.read_text(encoding="utf-8")
        
        # 移除旧的 category (以防编号或名字有变)
        content = re.sub(r'^category:.*\n', '', content, flags=re.MULTILINE)
        
        # 确定新的分类
        category = determine_category(file_path.name)
        
        # 创建目标文件夹
        target_dir = CONCEPTS_DIR / category
        target_dir.mkdir(exist_ok=True, parents=True)
        
        target_file = target_dir / file_path.name
        
        # 重新注入 category 到 frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                frontmatter = frontmatter.rstrip() + f'\ncategory: "{category}"\n'
                new_content = f"---{frontmatter}---{parts[2]}"
            else:
                new_content = content
        else:
            new_frontmatter = f"---\ntitle: \"{file_path.stem}\"\ncategory: \"{category}\"\n---\n"
            new_content = new_frontmatter + content
            
        # 写入目标文件
        if target_file != file_path:
            target_file.write_text(new_content, encoding="utf-8")
            file_path.unlink() # 删除原文件
            moves += 1
        else:
            # 如果文件已经在正确的文件夹下，只更新内容
            target_file.write_text(new_content, encoding="utf-8")
            
    print(f"整理完成！共移动和归类了 {moves} 个概念文件。")
    
    # 清理空的旧文件夹(如果存在)
    for dir_path in CONCEPTS_DIR.glob("*"):
        if dir_path.is_dir() and not list(dir_path.glob("*")):
            dir_path.rmdir()

if __name__ == "__main__":
    process_all()
