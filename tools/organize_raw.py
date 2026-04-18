#!/usr/bin/env python3
import os
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
RAW_DIR = REPO_ROOT / "raw"

MAPPING = {
    "1. 基础理论与核心概念": ["Theory", "Concept", "Fundamental"],
    "2. 技术实现与算法": ["Algorithm", "Method", "Technique"],
    "3. 业务场景与应用": ["Application", "Use Case", "Scenario"],
    "4. 行业报告与竞品分析": ["Market", "Industry", "Report"],
    "5. 待归档实体与其他": ["Misc", "Other"]
}

def determine_category(filename: str):
    name_lower = filename.lower()
    for cat, keywords in MAPPING.items():
        for kw in keywords:
            if kw.lower() in name_lower:
                return cat
    return "12. 其他研发实验与文献"

def process_all():
    print("开始组织 raw/ 原始资料到子文件夹...")
    
    # 获取根目录下除了 "new" 以及子文件夹本身以外的所有文件
    files = [f for f in RAW_DIR.glob("*") if f.is_file() and f.name != ".DS_Store"]
    
    moves = 0
    for file_path in files:
        category = determine_category(file_path.name)
        target_dir = RAW_DIR / category
        target_dir.mkdir(exist_ok=True, parents=True)
        
        target_file = target_dir / file_path.name
        
        if target_file != file_path:
            # 避免直接覆盖（如果有重名文件）
            counter = 1
            while target_file.exists():
                target_file = target_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
                counter += 1
                
            shutil.move(str(file_path), str(target_file))
            print(f"移动 [{category}]: {file_path.name}")
            moves += 1
            
    print(f"整理完成！共将 {moves} 个原始资料文件分列到了不同类目之下。")

if __name__ == "__main__":
    process_all()
