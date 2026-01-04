"""
Database Migration: Add Incremental Rescoring System Tables
迁移脚本：添加增量重新评分系统的表

Version: 1.0
Date: 2026-01-04
Description:
    - Add cluster_snapshots table
    - Add scoring_batches table
    - Add opportunity_versions table
    - Add new columns to opportunities table
"""
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class Migration_AddIncrementalRescoringTables:
    """增量重新评分系统表迁移"""

    def __init__(self, db_path: str = "data/wise_collection.db"):
        self.db_path = db_path
        self.migration_name = "add_incremental_rescoring_tables"
        self.migration_version = "001"

    def run(self):
        """执行迁移"""
        logger.info(f"Starting migration: {self.migration_name} v{self.migration_version}")

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 执行迁移步骤
            self._create_cluster_snapshots_table(cursor)
            self._create_scoring_batches_table(cursor)
            self._create_opportunity_versions_table(cursor)
            self._add_columns_to_opportunities_table(cursor)
            self._create_indexes(cursor)

            conn.commit()
            conn.close()

            logger.info(f"Migration {self.migration_name} completed successfully")
            return True

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _create_cluster_snapshots_table(self, cursor):
        """创建cluster快照表"""
        logger.info("Creating cluster_snapshots table...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cluster_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_id INTEGER NOT NULL,
                snapshot_time TIMESTAMP NOT NULL,

                -- Cluster指标
                cluster_size INTEGER NOT NULL,
                unique_authors INTEGER NOT NULL,
                cross_subreddit_count INTEGER NOT NULL,
                avg_frequency_score REAL,
                latest_event_extracted_at TIMESTAMP,

                -- 元数据
                snapshot_reason TEXT,  -- 'initial', 'before_rescoring', 'periodic'
                pipeline_run_id TEXT,

                FOREIGN KEY (cluster_id) REFERENCES clusters(id)
            )
        """)

        logger.info("✓ cluster_snapshots table created")

    def _create_scoring_batches_table(self, cursor):
        """创建评分批次表"""
        logger.info("Creating scoring_batches table...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scoring_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT UNIQUE NOT NULL,
                trigger_type TEXT NOT NULL,  -- 'incremental_update', 'full_rebuild', 'manual'

                -- 批次信息
                clusters_count INTEGER NOT NULL,
                cluster_ids TEXT NOT NULL,  -- JSON array

                -- 状态追踪
                status TEXT NOT NULL,  -- 'pending', 'in_progress', 'completed', 'failed'
                created_at TIMESTAMP NOT NULL,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,

                -- 统计
                opportunities_scored INTEGER DEFAULT 0,
                opportunities_passed_filter INTEGER DEFAULT 0,
                avg_score REAL,

                FOREIGN KEY (batch_id) REFERENCES pipeline_run_results(batch_id)
            )
        """)

        logger.info("✓ scoring_batches table created")

    def _create_opportunity_versions_table(self, cursor):
        """创建opportunity版本历史表"""
        logger.info("Creating opportunity_versions table...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunity_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id INTEGER NOT NULL,
                version INTEGER NOT NULL,

                -- Cluster状态快照（评分时）
                cluster_size_at_score INTEGER NOT NULL,
                unique_authors_at_score INTEGER NOT NULL,
                cross_subreddit_at_score INTEGER NOT NULL,

                -- 评分结果
                raw_total_score REAL NOT NULL,
                total_score REAL NOT NULL,
                trust_level REAL NOT NULL,
                component_scores TEXT,  -- JSON
                killer_risks TEXT,  -- JSON array
                recommendation TEXT,

                -- 元数据
                scored_at TIMESTAMP NOT NULL,
                change_reason TEXT,  -- 为什么重新评分
                batch_id TEXT,  -- 关联到scoring_batches
                pipeline_run_id TEXT,

                FOREIGN KEY (opportunity_id) REFERENCES opportunities(id),
                FOREIGN KEY (batch_id) REFERENCES scoring_batches(batch_id)
            )
        """)

        logger.info("✓ opportunity_versions table created")

    def _add_columns_to_opportunities_table(self, cursor):
        """为opportunities表添加新列"""
        logger.info("Adding new columns to opportunities table...")

        # 检查现有列
        cursor.execute("PRAGMA table_info(opportunities)")
        existing_columns = {row['name'] for row in cursor.fetchall()}

        # 添加新列（如果不存在）
        new_columns = {
            'current_version': 'INTEGER DEFAULT 1',
            'last_rescored_at': 'TIMESTAMP',
            'rescore_count': 'INTEGER DEFAULT 0',
            'scored_at': 'TIMESTAMP'
        }

        for column_name, column_def in new_columns.items():
            if column_name not in existing_columns:
                try:
                    cursor.execute(f"""
                        ALTER TABLE opportunities
                        ADD COLUMN {column_name} {column_def}
                    """)
                    logger.info(f"  ✓ Added column: {column_name}")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e):
                        logger.info(f"  ○ Column already exists: {column_name}")
                    else:
                        raise

    def _create_indexes(self, cursor):
        """创建索引"""
        logger.info("Creating indexes...")

        # cluster_snapshots表索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cluster_snapshots_cluster_id
            ON cluster_snapshots(cluster_id, snapshot_time DESC)
        """)

        # opportunity_versions表索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opportunity_versions_opp_id_version
            ON opportunity_versions(opportunity_id, version DESC)
        """)

        # opportunities表索引（新字段）
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opportunities_scored_at
            ON opportunities(scored_at DESC)
        """)

        logger.info("✓ All indexes created")


def main():
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 确定数据库路径
    db_path = "data/wise_collection.db"

    # 检查数据库是否存在
    if not Path(db_path).exists():
        logger.error(f"Database not found at {db_path}")
        return False

    # 执行迁移
    migration = Migration_AddIncrementalRescoringTables(db_path)
    success = migration.run()

    if success:
        logger.info("=" * 60)
        logger.info("Migration completed successfully!")
        logger.info("=" * 60)
        return 0
    else:
        logger.error("=" * 60)
        logger.error("Migration failed!")
        logger.error("=" * 60)
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
