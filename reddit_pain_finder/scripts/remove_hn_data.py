#!/usr/bin/env python3
"""
移除HN数据和aligned_problems表的脚本
Remove HackerNews data and aligned_problems table from database
"""
import sqlite3
import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def remove_hn_data(db_path: str = "data/wise_collection.db"):
    """移除HN相关数据

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

        # 1. 删除HN posts
        cursor.execute("SELECT COUNT(*) as count FROM posts WHERE source = 'hackernews'")
        hn_posts_count = cursor.fetchone()['count']
        logger.info(f"Found {hn_posts_count} HN posts")

        cursor.execute("DELETE FROM posts WHERE source = 'hackernews'")
        logger.info(f"✅ Deleted {cursor.rowcount} HN posts")

        # 2. 删除HN comments
        cursor.execute("SELECT COUNT(*) as count FROM comments WHERE source = 'hackernews'")
        hn_comments_count = cursor.fetchone()['count']
        logger.info(f"Found {hn_comments_count} HN comments")

        cursor.execute("DELETE FROM comments WHERE source = 'hackernews'")
        logger.info(f"✅ Deleted {cursor.rowcount} HN comments")

        # 3. 删除aligned_problems表
        cursor.execute("SELECT COUNT(*) as count FROM sqlite_master WHERE type='table' AND name='aligned_problems'")
        table_exists = cursor.fetchone()['count'] > 0

        if table_exists:
            cursor.execute("SELECT COUNT(*) as count FROM aligned_problems")
            aligned_count = cursor.fetchone()['count']
            logger.info(f"Found {aligned_count} aligned problems")

            cursor.execute("DROP TABLE IF EXISTS aligned_problems")
            logger.info(f"✅ Dropped aligned_problems table")
        else:
            logger.info("aligned_problems table does not exist, skipping")

        # 提交事务
        conn.commit()
        logger.info("✅ All changes committed successfully")

        # 验证清理结果
        cursor.execute("SELECT COUNT(*) as count FROM posts WHERE source = 'hackernews'")
        remaining_hn_posts = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM comments WHERE source = 'hackernews'")
        remaining_hn_comments = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM sqlite_master WHERE type='table' AND name='aligned_problems'")
        aligned_table_exists = cursor.fetchone()['count'] > 0

        logger.info("\n=== Cleanup Summary ===")
        logger.info(f"HN posts remaining: {remaining_hn_posts}")
        logger.info(f"HN comments remaining: {remaining_hn_comments}")
        logger.info(f"aligned_problems table exists: {aligned_table_exists}")
        logger.info(f"Backup saved to: {backup_path}")

        if remaining_hn_posts == 0 and remaining_hn_comments == 0 and not aligned_table_exists:
            logger.info("\n✅ All HN data and aligned_problems table removed successfully!")
            return True
        else:
            logger.warning("\n⚠️  Cleanup may not be complete, please check the summary above")
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
    logger.info("Starting HN data removal...")
    logger.info("=" * 60)

    success = remove_hn_data()

    if success:
        logger.info("\n✅ Script completed successfully")
        exit(0)
    else:
        logger.error("\n❌ Script completed with errors")
        exit(1)
