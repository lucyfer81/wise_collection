#!/usr/bin/env python3
"""
Simple Database Migration Script
直接迁移现有数据库到新的多数据源schema，不依赖修改后的代码
"""
import os
import sqlite3
import json
import logging
from datetime import datetime

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def migrate_database(db_path: str) -> bool:
    """迁移数据库到新的schema"""
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        # 1. 创建备份
        logger.info(f"Creating backup at {backup_path}")
        source = sqlite3.connect(db_path)
        backup = sqlite3.connect(backup_path)
        source.backup(backup)
        backup.close()
        source.close()
        logger.info("Backup created successfully")

        # 2. 连接数据库执行迁移
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # 3. 检查现有表结构
        cursor = conn.execute("PRAGMA table_info(posts)")
        existing_columns = {row['name'] for row in cursor.fetchall()}
        logger.info(f"Existing columns: {existing_columns}")

        # 4. 添加新列（如果不存在）- 先添加为可空，然后再填充
        new_columns = [
            ("source", "TEXT DEFAULT 'reddit'"),
            ("source_id", "TEXT"),
            ("platform_data", "TEXT"),
            ("created_at", "TIMESTAMP")
        ]

        for col_name, col_def in new_columns:
            if col_name not in existing_columns:
                logger.info(f"Adding column: {col_name}")
                conn.execute(f"ALTER TABLE posts ADD COLUMN {col_name} {col_def}")

        # 5. 迁移数据
        cursor = conn.execute("SELECT * FROM posts WHERE source_id IS NULL OR source_id = ''")
        posts = cursor.fetchall()

        logger.info(f"Found {len(posts)} posts to migrate")

        migrated_count = 0
        for post in posts:
            try:
                # 提取数据
                reddit_id = post['id']
                unified_id = f"reddit_{reddit_id}"

                # 构建platform_data
                platform_data = {
                    "subreddit": post['subreddit'],
                    "upvote_ratio": post['upvote_ratio'],
                    "is_self": bool(post['is_self']),
                    "reddit_url": post['url']
                }

                # 标准化时间
                created_at = datetime.fromtimestamp(post['created_utc']).isoformat() + "Z"

                # 更新记录
                conn.execute("""
                    UPDATE posts SET
                        id = ?,
                        source = 'reddit',
                        source_id = ?,
                        platform_data = ?,
                        created_at = ?
                    WHERE id = ?
                """, (
                    unified_id,
                    reddit_id,
                    json.dumps(platform_data),
                    created_at,
                    reddit_id  # 原始ID
                ))

                migrated_count += 1

                if migrated_count % 100 == 0:
                    logger.info(f"Migrated {migrated_count} posts...")

            except Exception as e:
                logger.error(f"Failed to migrate post {post.get('id')}: {e}")
                continue

        # 6. 更新filtered_posts表
        cursor = conn.execute("SELECT DISTINCT id FROM filtered_posts")
        filtered_ids = [row['id'] for row in cursor.fetchall()]

        logger.info(f"Updating {len(filtered_ids)} filtered post references")

        for old_id in filtered_ids:
            try:
                new_id = f"reddit_{old_id}"
                conn.execute("UPDATE filtered_posts SET id = ? WHERE id = ?", (new_id, old_id))
            except Exception as e:
                logger.error(f"Failed to update filtered post {old_id}: {e}")
                continue

        # 7. 更新pain_events表
        cursor = conn.execute("SELECT DISTINCT post_id FROM pain_events")
        post_ids = [row['post_id'] for row in cursor.fetchall()]

        logger.info(f"Updating {len(post_ids)} pain event references")

        for old_id in post_ids:
            try:
                new_id = f"reddit_{old_id}"
                conn.execute("UPDATE pain_events SET post_id = ? WHERE post_id = ?", (new_id, old_id))
            except Exception as e:
                logger.error(f"Failed to update pain events for post {old_id}: {e}")
                continue

        # 8. 创建索引
        try:
            logger.info("Creating new indexes")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_source ON posts(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_source_created ON posts(source, created_at)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_posts_unique_source ON posts(source, source_id)")
            logger.info("Indexes created successfully")
        except Exception as e:
            logger.warning(f"Could not create unique index: {e}")

        conn.commit()
        conn.close()

        logger.info(f"Migration completed successfully!")
        logger.info(f"Migrated {migrated_count} posts")
        logger.info(f"Backup saved at: {backup_path}")

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False

def verify_migration(db_path: str) -> bool:
    """验证迁移结果"""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # 检查是否还有未迁移的帖子
        cursor = conn.execute("SELECT COUNT(*) as count FROM posts WHERE source_id IS NULL OR source_id = ''")
        unmigrated_count = cursor.fetchone()['count']

        # 检查总数
        cursor = conn.execute("SELECT COUNT(*) as total FROM posts")
        total_count = cursor.fetchone()['total']

        # 检查按数据源分组
        cursor = conn.execute("SELECT source, COUNT(*) as count FROM posts GROUP BY source")
        source_counts = {row['source']: row['count'] for row in cursor.fetchall()}

        logger.info(f"Migration verification:")
        logger.info(f"  Total posts: {total_count}")
        logger.info(f"  Unmigrated posts: {unmigrated_count}")
        logger.info(f"  Posts by source: {source_counts}")

        conn.close()

        if unmigrated_count == 0:
            logger.info("✅ Migration successful!")
            return True
        else:
            logger.warning(f"⚠️ Migration incomplete: {unmigrated_count} posts still unmigrated")
            return False

    except Exception as e:
        logger.error(f"Failed to verify migration: {e}")
        return False

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Simple database migration")
    parser.add_argument("--db-path", default="data/reddit_pain_finder.db", help="Database file path")
    args = parser.parse_args()

    if not os.path.exists(args.db_path):
        logger.error(f"Database file not found: {args.db_path}")
        return False

    logger.info(f"Starting migration of database: {args.db_path}")

    if migrate_database(args.db_path):
        if verify_migration(args.db_path):
            logger.info("✅ Migration completed successfully!")
            return True
        else:
            logger.error("❌ Migration verification failed!")
            return False
    else:
        logger.error("❌ Migration failed!")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1)