#!/usr/bin/env python3
"""
移除comments数据和相关表的脚本
Remove comments data and related tables from database
"""
import sqlite3
import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def remove_comments_data(db_path: str = "data/wise_collection.db"):
    """移除comments相关数据

    Args:
        db_path: 数据库路径
    """
    if not os.path.exists(db_path):
        logger.error(f"Database not found: {db_path}")
        return False

    # 备份数据库
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info(f"Creating backup: {backup_path}")

    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        logger.info(f"✅ Backup created successfully")
    except Exception as e:
        logger.error(f"❌ Failed to create backup: {e}")
        return False

    # 连接数据库并执行清理
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 开始事务
        conn.execute("BEGIN TRANSACTION")

        # 1. 检查并统计comments表
        cursor.execute("SELECT COUNT(*) as count FROM sqlite_master WHERE type='table' AND name='comments'")
        comments_exists = cursor.fetchone()['count'] > 0
        comments_count = 0

        if comments_exists:
            cursor.execute("SELECT COUNT(*) as count FROM comments")
            comments_count = cursor.fetchone()['count']
            logger.info(f"Found {comments_count} comments")
        else:
            logger.info("comments table does not exist")

        # 2. 检查并统计filtered_comments表
        cursor.execute("SELECT COUNT(*) as count FROM sqlite_master WHERE type='table' AND name='filtered_comments'")
        filtered_comments_exists = cursor.fetchone()['count'] > 0
        filtered_comments_count = 0

        if filtered_comments_exists:
            cursor.execute("SELECT COUNT(*) as count FROM filtered_comments")
            filtered_comments_count = cursor.fetchone()['count']
            logger.info(f"Found {filtered_comments_count} filtered_comments")
        else:
            logger.info("filtered_comments table does not exist")

        # 3. 删除表（如果存在）
        cursor.execute("DROP TABLE IF EXISTS filtered_comments")
        if filtered_comments_exists:
            logger.info(f"✅ Dropped filtered_comments table")

        cursor.execute("DROP TABLE IF EXISTS comments")
        if comments_exists:
            logger.info(f"✅ Dropped comments table")

        # 提交事务
        conn.commit()
        logger.info("✅ All changes committed successfully")

        # 验证清理结果
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%comment%'")
        remaining_tables = cursor.fetchall()

        logger.info("\n=== Cleanup Summary ===")
        logger.info(f"Deleted comments table: {comments_count} records")
        logger.info(f"Deleted filtered_comments table: {filtered_comments_count} records")
        logger.info(f"Remaining comment-related tables: {len(remaining_tables)}")
        logger.info(f"Backup saved to: {backup_path}")

        if remaining_tables:
            logger.warning(f"\n⚠️  Still have {len(remaining_tables)} comment-related tables:")
            for table in remaining_tables:
                logger.warning(f"  - {table[0]}")

        # 检查关键表是否已删除
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('comments', 'filtered_comments')")
        key_tables_remaining = cursor.fetchall()

        if len(key_tables_remaining) == 0:
            logger.info("\n✅ All comment-related tables removed successfully!")
            return True
        else:
            logger.error(f"\n❌ Key comment tables still exist: {[t[0] for t in key_tables_remaining]}")
            return False

    except Exception as e:
        logger.error(f"❌ Error during cleanup: {e}")
        logger.error("Rolling back changes...")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    logger.info("Starting comments data removal...")
    logger.info("=" * 60)

    success = remove_comments_data()

    if success:
        logger.info("\n✅ Script completed successfully")
        exit(0)
    else:
        logger.error("\n❌ Script completed with errors")
        exit(1)
