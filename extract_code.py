#!/usr/bin/env python3
"""
Extract all relevant code from reddit_pain_finder directory
提取reddit_pain_finder目录中的相关代码文件到all_code.md
"""

import os
import sys
from datetime import datetime
from pathlib import Path

def add_file_to_markdown(md_file, filepath, relative_path):
    """将文件内容添加到markdown文件中"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        md_file.write(f"\n\n{'='*80}\n")
        md_file.write(f"文件: {relative_path}\n")
        md_file.write(f"{'='*80}\n\n")
        md_file.write("```python\n")
        md_file.write(content)
        md_file.write("\n```\n")

        return True
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return False

def main():
    """主函数"""
    # 定义源目录
    source_dir = Path("reddit_pain_finder")

    # 定义要包含的文件和目录
    files_to_include = [
        "run_pipeline.py",
        "pain_point_analyzer.py"
    ]

    dirs_to_include = [
        "pipeline",
        "utils"
    ]

    # 输出文件
    output_file = Path("all_code.md")

    print("开始提取代码文件...")

    with open(output_file, 'w', encoding='utf-8') as md_file:
        # 写入标题
        md_file.write("# Reddit Pain Finder - 代码汇总\n\n")
        md_file.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        md_file.write("本文档包含 reddit_pain_finder 项目的核心代码文件：\n")
        md_file.write("- Pipeline处理模块 (pipeline/)\n")
        md_file.write("- 工具模块 (utils/)\n")
        md_file.write("- 主要执行脚本\n\n")

        file_count = 0

        # 处理根目录的Python文件
        for filename in files_to_include:
            filepath = source_dir / filename
            if filepath.exists():
                print(f"处理文件: {filename}")
                if add_file_to_markdown(md_file, filepath, filename):
                    file_count += 1
            else:
                print(f"文件不存在: {filepath}")

        # 处理pipeline目录
        pipeline_dir = source_dir / "pipeline"
        if pipeline_dir.exists():
            print("\n处理pipeline目录...")
            for py_file in sorted(pipeline_dir.glob("*.py")):
                if py_file.name != "__init__.py":
                    relative_path = f"pipeline/{py_file.name}"
                    print(f"  - {py_file.name}")
                    if add_file_to_markdown(md_file, py_file, relative_path):
                        file_count += 1

        # 处理utils目录
        utils_dir = source_dir / "utils"
        if utils_dir.exists():
            print("\n处理utils目录...")
            for py_file in sorted(utils_dir.glob("*.py")):
                if py_file.name != "__init__.py":
                    relative_path = f"utils/{py_file.name}"
                    print(f"  - {py_file.name}")
                    if add_file_to_markdown(md_file, py_file, relative_path):
                        file_count += 1

        # 写入总结
        md_file.write(f"\n\n{'='*80}\n")
        md_file.write(f"提取完成\n")
        md_file.write(f"{'='*80}\n")
        md_file.write(f"总共提取了 {file_count} 个文件\n")

    print(f"\n✅ 代码提取完成！")
    print(f"输出文件: {output_file.absolute()}")
    print(f"提取的文件数: {file_count}")

if __name__ == "__main__":
    main()