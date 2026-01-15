"""
Pipeline State Tracker for Reddit Pain Point Finder
Pipeline运行状态追踪 - 支持增量处理

功能：
- 记录每个stage的最后运行时间
- 支持增量处理（只处理新数据）
- 自动创建和管理pipeline_state表
"""
import sqlite3
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class PipelineState:
    """Pipeline运行状态追踪器"""

    def __init__(self, db_path: str = "data/wise_collection.db"):
        """初始化状态追踪器

        Args:
            db_path: 数据库路径（默认使用统一数据库）
        """
        self.db_path = db_path
        self._init_state_table()

    def _init_state_table(self):
        """初始化pipeline_state表"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 创建表（如果不存在）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_state (
                    stage TEXT PRIMARY KEY,
                    last_run_at TIMESTAMP,
                    last_processed_count INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_pipeline_state_updated_at
                ON pipeline_state(updated_at)
            """)

            conn.commit()
            conn.close()

            logger.debug("Pipeline state table initialized")

        except Exception as e:
            logger.error(f"Failed to initialize pipeline_state table: {e}")
            raise

    def get_last_run_time(self, stage: str) -> Optional[str]:
        """获取某stage的最后运行时间

        Args:
            stage: Stage名称 (如 'filter', 'extract', 'embed', 'cluster')

        Returns:
            ISO格式时间戳，如果从未运行则返回None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT last_run_at FROM pipeline_state
                WHERE stage = ?
            """, (stage,))

            row = cursor.fetchone()
            conn.close()

            return row[0] if row else None

        except Exception as e:
            logger.error(f"Failed to get last run time for stage '{stage}': {e}")
            return None

    def get_last_processed_count(self, stage: str) -> int:
        """获取某stage最后处理的数量

        Args:
            stage: Stage名称

        Returns:
            最后处理的数量，如果从未运行则返回0
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT last_processed_count FROM pipeline_state
                WHERE stage = ?
            """, (stage,))

            row = cursor.fetchone()
            conn.close()

            return row[0] if row else 0

        except Exception as e:
            logger.error(f"Failed to get last processed count for stage '{stage}': {e}")
            return 0

    def update_stage_run(
        self,
        stage: str,
        processed_count: int = 0,
        custom_time: Optional[str] = None
    ) -> bool:
        """更新stage运行状态

        Args:
            stage: Stage名称
            processed_count: 本次处理的数据数量
            custom_time: 自定义时间戳（可选，默认使用当前时间）

        Returns:
            是否成功更新
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 使用当前时间或自定义时间
            now = custom_time or datetime.now().isoformat()

            # INSERT OR REPLACE 会覆盖已存在的记录
            cursor.execute("""
                INSERT OR REPLACE INTO pipeline_state (stage, last_run_at, last_processed_count, updated_at)
                VALUES (?, ?, ?, ?)
            """, (stage, now, processed_count, now))

            conn.commit()
            conn.close()

            logger.debug(f"Updated pipeline state: stage='{stage}', count={processed_count}, time='{now}'")
            return True

        except Exception as e:
            logger.error(f"Failed to update pipeline state for stage '{stage}': {e}")
            return False

    def get_all_stage_status(self) -> dict:
        """获取所有stage的状态

        Returns:
            Dict: {stage_name: {"last_run_at": ..., "last_processed_count": ...}}
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT stage, last_run_at, last_processed_count, updated_at
                FROM pipeline_state
                ORDER BY stage
            """)

            result = {}
            for row in cursor.fetchall():
                stage, last_run, count, updated = row
                result[stage] = {
                    "last_run_at": last_run,
                    "last_processed_count": count,
                    "updated_at": updated
                }

            conn.close()
            return result

        except Exception as e:
            logger.error(f"Failed to get all stage status: {e}")
            return {}

    def reset_stage(self, stage: str) -> bool:
        """重置某个stage的状态（强制全量处理）

        Args:
            stage: Stage名称

        Returns:
            是否成功重置
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                DELETE FROM pipeline_state
                WHERE stage = ?
            """, (stage,))

            conn.commit()
            conn.close()

            logger.info(f"Reset pipeline state for stage '{stage}'")
            return True

        except Exception as e:
            logger.error(f"Failed to reset stage '{stage}': {e}")
            return False

    def reset_all_stages(self) -> bool:
        """重置所有stage状态（强制全量处理所有数据）

        Returns:
            是否成功重置
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("DELETE FROM pipeline_state")

            conn.commit()
            conn.close()

            logger.info("Reset all pipeline stages (will force full processing)")
            return True

        except Exception as e:
            logger.error(f"Failed to reset all stages: {e}")
            return False


# 单例实例
_pipeline_state: Optional[PipelineState] = None


def get_pipeline_state() -> PipelineState:
    """获取PipelineState单例实例

    Returns:
        PipelineState实例
    """
    global _pipeline_state
    if _pipeline_state is None:
        _pipeline_state = PipelineState()
    return _pipeline_state


def main():
    """测试命令"""
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline状态管理工具")
    parser.add_argument("--status", action="store_true", help="查看所有stage状态")
    parser.add_argument("--reset", type=str, help="重置指定stage (或使用'all'重置所有)")
    parser.add_argument("--get", type=str, help="获取指定stage的最后运行时间")
    args = parser.parse_args()

    state = get_pipeline_state()

    if args.status:
        print("\n=== Pipeline Stage Status ===")
        all_status = state.get_all_stage_status()
        if all_status:
            for stage, info in sorted(all_status.items()):
                print(f"\n{stage}:")
                print(f"  Last run: {info['last_run_at']}")
                print(f"  Processed: {info['last_processed_count']} items")
                print(f"  Updated: {info['updated_at']}")
        else:
            print("No stage runs recorded yet")
        print()

    elif args.reset:
        if args.reset.lower() == 'all':
            if state.reset_all_stages():
                print("✅ All stages reset successfully")
            else:
                print("❌ Failed to reset stages")
        else:
            if state.reset_stage(args.reset):
                print(f"✅ Stage '{args.reset}' reset successfully")
            else:
                print(f"❌ Failed to reset stage '{args.reset}'")

    elif args.get:
        last_run = state.get_last_run_time(args.get)
        count = state.get_last_processed_count(args.get)
        if last_run:
            print(f"Stage '{args.get}':")
            print(f"  Last run: {last_run}")
            print(f"  Processed: {count} items")
        else:
            print(f"Stage '{args.get}' has never been run")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
