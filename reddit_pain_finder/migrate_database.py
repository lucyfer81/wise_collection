#!/usr/bin/env python3
"""
Database Migration Script
迁移现有Reddit数据到新的多数据源schema
"""
import os
import sys
import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Dict, Any

# 设置项目根目录
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from utils.db import WiseCollectionDB

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseMigrator:
    """数据库迁移器"""

    def __init__(self, db_path: str = "data/reddit_pain_finder.db"):
        """初始化迁移器"""
        self.db_path = db_path
        self.db = WiseCollectionDB()
        self.migration_stats = {
            "posts_migrated": 0,
            "posts_failed": 0,
            "backup_created": False,
            "migration_completed": False
        }

    def create_backup(self) -> bool:
        """创建数据库备份"""
        try:
            backup_path = f"{self.db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # 连接数据库执行备份
            source = sqlite3.connect(self.db_path)
            backup = sqlite3.connect(backup_path)

            source.backup(backup)
            source.close()
            backup.close()

            logger.info(f"Database backup created at: {backup_path}")
            self.migration_stats["backup_created"] = True
            return True

        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return False

    def check_migration_needed(self) -> bool:
        """检查是否需要迁移"""
        try:
            with self.db.get_connection("raw") as conn:
                # 检查是否存在新字段
                cursor = conn.execute("PRAGMA table_info(posts)")
                columns = [row['name'] for row in cursor.fetchall()]

                needed_columns = ['source', 'source_id', 'platform_data', 'created_at']
                missing_columns = [col for col in needed_columns if col not in columns]

                if missing_columns:
                    logger.info(f"Migration needed. Missing columns: {missing_columns}")
                    return True
                else:
                    logger.info("Database schema already up to date")
                    return False

        except Exception as e:
            logger.error(f"Failed to check migration status: {e}")
            return False

    def add_new_columns(self) -> bool:
        """添加新的数据列"""
        try:
            with self.db.get_connection("raw") as conn:
                # 检查现有列
                cursor = conn.execute("PRAGMA table_info(posts)")
                existing_columns = {row['name'] for row in cursor.fetchall()}

                # 添加新列（如果不存在）
                new_columns = [
                    ("source", "TEXT NOT NULL DEFAULT 'reddit'"),
                    ("source_id", "TEXT NOT NULL"),
                    ("platform_data", "TEXT"),
                    ("created_at", "TIMESTAMP NOT NULL")
                ]

                for col_name, col_def in new_columns:
                    if col_name not in existing_columns:
                        logger.info(f"Adding column: {col_name}")
                        conn.execute(f"ALTER TABLE posts ADD COLUMN {col_name} {col_def}")

                # 添加唯一约束（可能需要先处理重复数据）
                try:
                    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_posts_unique_source ON posts(source, source_id)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_source ON posts(source)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_source_created ON posts(source, created_at)")
                except Exception as e:
                    logger.warning(f"Could not create unique constraint (will handle duplicates): {e}")

                conn.commit()
                logger.info("New columns added successfully")
                return True

        except Exception as e:
            logger.error(f"Failed to add new columns: {e}")
            return False

    def migrate_posts(self) -> bool:
        """迁移现有帖子数据"""
        try:
            with self.db.get_connection("raw") as conn:
                # 获取所有需要迁移的帖子（没有source_id的旧数据）
                cursor = conn.execute("""
                    SELECT id, subreddit, upvote_ratio, is_self, created_utc, url, title, body,
                           score, num_comments, author, category, raw_data
                    FROM posts
                    WHERE source_id IS NULL OR source_id = ''
                """)

                posts = cursor.fetchall()
                logger.info(f"Found {len(posts)} posts to migrate")

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

                        self.migration_stats["posts_migrated"] += 1

                        if self.migration_stats["posts_migrated"] % 100 == 0:
                            logger.info(f"Migrated {self.migration_stats['posts_migrated']} posts...")

                    except Exception as e:
                        logger.error(f"Failed to migrate post {post.get('id')}: {e}")
                        self.migration_stats["posts_failed"] += 1
                        continue

                conn.commit()
                logger.info(f"Migration completed. Success: {self.migration_stats['posts_migrated']}, Failed: {self.migration_stats['posts_failed']}")
                return True

        except Exception as e:
            logger.error(f"Failed to migrate posts: {e}")
            return False

    def update_filtered_posts(self) -> bool:
        """更新filtered_posts表的ID引用"""
        try:
            with self.db.get_connection("filtered") as conn:
                # 获取所有filtered posts
                cursor = conn.execute("SELECT DISTINCT id FROM filtered_posts")
                filtered_ids = [row['id'] for row in cursor.fetchall()]

                logger.info(f"Updating {len(filtered_ids)} filtered post references")

                updated_count = 0
                for old_id in filtered_ids:
                    try:
                        new_id = f"reddit_{old_id}"
                        conn.execute("UPDATE filtered_posts SET id = ? WHERE id = ?", (new_id, old_id))
                        updated_count += 1
                    except Exception as e:
                        logger.error(f"Failed to update filtered post {old_id}: {e}")
                        continue

                conn.commit()
                logger.info(f"Updated {updated_count} filtered post references")
                return True

        except Exception as e:
            logger.error(f"Failed to update filtered posts: {e}")
            return False

    def update_pain_events(self) -> bool:
        """更新pain_events表的post_id引用"""
        try:
            with self.db.get_connection("pain") as conn:
                # 获取所有pain events
                cursor = conn.execute("SELECT DISTINCT post_id FROM pain_events")
                post_ids = [row['post_id'] for row in cursor.fetchall()]

                logger.info(f"Updating {len(post_ids)} pain event references")

                updated_count = 0
                for old_id in post_ids:
                    try:
                        new_id = f"reddit_{old_id}"
                        conn.execute("UPDATE pain_events SET post_id = ? WHERE post_id = ?", (new_id, old_id))
                        updated_count += 1
                    except Exception as e:
                        logger.error(f"Failed to update pain events for post {old_id}: {e}")
                        continue

                conn.commit()
                logger.info(f"Updated {updated_count} pain event references")
                return True

        except Exception as e:
            logger.error(f"Failed to update pain events: {e}")
            return False

    def verify_migration(self) -> bool:
        """验证迁移结果"""
        try:
            with self.db.get_connection("raw") as conn:
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

                if unmigrated_count == 0:
                    logger.info("✅ Migration successful!")
                    return True
                else:
                    logger.warning(f"⚠️ Migration incomplete: {unmigrated_count} posts still unmigrated")
                    return False

        except Exception as e:
            logger.error(f"Failed to verify migration: {e}")
            return False

    def run_migration(self) -> bool:
        """执行完整迁移流程"""
        logger.info("🚀 Starting database migration...")

        # 1. 创建备份
        if not self.create_backup():
            logger.error("❌ Migration failed: Could not create backup")
            return False

        # 2. 检查是否需要迁移
        if not self.check_migration_needed():
            logger.info("✅ Migration not needed - schema already up to date")
            return True

        # 3. 添加新列
        if not self.add_new_columns():
            logger.error("❌ Migration failed: Could not add new columns")
            return False

        # 4. 迁移帖子数据
        if not self.migrate_posts():
            logger.error("❌ Migration failed: Could not migrate posts")
            return False

        # 5. 更新引用
        if not self.update_filtered_posts():
            logger.error("❌ Migration failed: Could not update filtered posts")
            return False

        if not self.update_pain_events():
            logger.error("❌ Migration failed: Could not update pain events")
            return False

        # 6. 验证迁移
        if not self.verify_migration():
            logger.error("❌ Migration failed: Verification failed")
            return False

        # 7. 重新创建索引
        try:
            with self.db.get_connection("raw") as conn:
                conn.execute("DROP INDEX IF EXISTS idx_posts_unique_source")
                conn.execute("CREATE UNIQUE INDEX idx_posts_unique_source ON posts(source, source_id)")
                conn.commit()
            logger.info("✅ Indexes recreated successfully")
        except Exception as e:
            logger.warning(f"Could not recreate unique index: {e}")

        self.migration_stats["migration_completed"] = True

        # 输出最终统计
        logger.info("=" * 50)
        logger.info("MIGRATION SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Posts migrated: {self.migration_stats['posts_migrated']}")
        logger.info(f"Posts failed: {self.migration_stats['posts_failed']}")
        logger.info(f"Backup created: {self.migration_stats['backup_created']}")
        logger.info(f"Migration completed: {self.migration_stats['migration_completed']}")
        logger.info("=" * 50)

        return True

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate database to multi-source schema")
    parser.add_argument("--db-path", default="data/reddit_pain_finder.db", help="Database file path")
    parser.add_argument("--force", action="store_true", help="Force migration even if not needed")
    args = parser.parse_args()

    try:
        migrator = DatabaseMigrator(args.db_path)

        if not args.force and not migrator.check_migration_needed():
            print("Database schema already up to date. Use --force to run migration anyway.")
            return

        success = migrator.run_migration()

        if success:
            print("✅ Migration completed successfully!")
            sys.exit(0)
        else:
            print("❌ Migration failed!")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Migration failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()