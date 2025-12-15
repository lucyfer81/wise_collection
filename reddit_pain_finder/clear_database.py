#!/usr/bin/env python3
"""
清空Reddit痛点发现系统的所有数据库
"""

import sqlite3
import os
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def clear_database(db_path: str, db_name: str):
    """清空指定的数据库"""
    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        logger.info(f"\n清空 {db_name} 数据库...")

        # 清空每个表
        for table in tables:
            table_name = table[0]
            if table_name != 'sqlite_sequence':  # 跳过系统表
                cursor.execute(f"DELETE FROM {table_name}")
                rows_deleted = cursor.rowcount
                logger.info(f"  - 表 {table_name}: 删除了 {rows_deleted} 行")

        # 重置自增ID
        cursor.execute("DELETE FROM sqlite_sequence")

        # 提交更改
        conn.commit()
        conn.close()

        logger.info(f"✅ {db_name} 数据库已成功清空")

    except Exception as e:
        logger.error(f"❌ 清空 {db_name} 数据库失败: {e}")

def main():
    """主函数"""
    # 数据库目录
    db_dir = "data"

    # 数据库文件列表
    databases = [
        ("raw_posts.db", "原始帖子"),
        ("filtered_posts.db", "过滤帖子"),
        ("pain_events.db", "痛点事件"),
        ("clusters.db", "聚类")
    ]

    print("=" * 50)
    print("⚠️  准备清空所有数据库数据")
    print("=" * 50)

    # 检查数据库文件是否存在
    for db_file, db_name in databases:
        db_path = os.path.join(db_dir, db_file)
        if os.path.exists(db_path):
            print(f"✓ 找到 {db_name} 数据库: {db_path}")
        else:
            print(f"✗ 未找到 {db_name} 数据库: {db_path}")

    # 确认操作
    confirm = input("\n确定要清空所有数据库吗？(输入 'YES' 确认): ")
    if confirm != "YES":
        print("操作已取消")
        return

    # 清空每个数据库
    for db_file, db_name in databases:
        db_path = os.path.join(db_dir, db_file)
        if os.path.exists(db_path):
            clear_database(db_path, db_name)
        else:
            logger.warning(f"数据库文件不存在: {db_path}")

    print("\n" + "=" * 50)
    print("✅ 所有数据库已清空完成！")
    print("=" * 50)

if __name__ == "__main__":
    main()