#!/usr/bin/env python3
"""
检查数据库状态
"""

import sqlite3
import os

def check_database(db_path: str, db_name: str):
    """检查指定的数据库"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        print(f"\n{db_name} 数据库状态:")
        print("-" * 40)

        # 检查每个表的记录数
        for table in tables:
            table_name = table[0]
            if table_name != 'sqlite_sequence':
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                print(f"  表 {table_name}: {count} 条记录")

        conn.close()

    except Exception as e:
        print(f"❌ 检查 {db_name} 数据库失败: {e}")

def main():
    """主函数"""
    db_dir = "data"
    databases = [
        ("raw_posts.db", "原始帖子"),
        ("filtered_posts.db", "过滤帖子"),
        ("pain_events.db", "痛点事件"),
        ("clusters.db", "聚类")
    ]

    print("数据库状态检查")
    print("=" * 50)

    for db_file, db_name in databases:
        db_path = os.path.join(db_dir, db_file)
        if os.path.exists(db_path):
            check_database(db_path, db_name)
        else:
            print(f"\n{db_name} 数据库: 文件不存在")

    print("\n" + "=" * 50)

if __name__ == "__main__":
    main()