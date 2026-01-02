#!/usr/bin/env python3
"""
Clean Comment Data Script
安全清理comment相关数据，以便重新应用新的过滤阈值

Usage:
    python3 scripts/clean_comment_data.py [--dry-run] [--confirm]
"""
import os
import sys
import logging
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import db

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def show_pre_check_stats():
    """显示清理前的统计信息"""
    logger.info("=" * 80)
    logger.info("预检查 - 将要删除的数据统计")
    logger.info("=" * 80)

    with db.get_connection("filtered") as conn:
        # Filtered comments统计
        cursor = conn.execute("SELECT COUNT(*) FROM filtered_comments")
        filtered_count = cursor.fetchone()[0]
        logger.info(f"\n📊 Filtered comments: {filtered_count:,}条")

        # Pain score分布
        cursor = conn.execute("""
            SELECT
                CASE
                    WHEN pain_score < 0.3 THEN '0.2-0.3 (低质量)'
                    WHEN pain_score < 0.4 THEN '0.3-0.4 (中等)'
                    WHEN pain_score < 0.5 THEN '0.4-0.5 (良好)'
                    ELSE '0.5+ (高质量)'
                END as quality,
                COUNT(*) as count,
                ROUND(100.0 * COUNT(*) * 1.0 / (SELECT COUNT(*) FROM filtered_comments), 1) as pct
            FROM filtered_comments
            GROUP BY quality
            ORDER BY MIN(pain_score)
        """)
        logger.info("\nPain score分布:")
        for row in cursor.fetchall():
            logger.info(f"  {row[0]:20} {row[1]:6}条 ({row[2]:5}%)")

    with db.get_connection("pain") as conn:
        # Pain events from comments统计
        cursor = conn.execute("""
            SELECT COUNT(*)
            FROM pain_events
            WHERE source_type = 'comment'
        """)
        pain_events_count = cursor.fetchone()[0]
        logger.info(f"\n📊 Pain events from comments: {pain_events_count:,}条")

        # Pain events from posts统计（用于对比）
        cursor = conn.execute("""
            SELECT COUNT(*)
            FROM pain_events
            WHERE source_type = 'post' OR source_type IS NULL
        """)
        posts_pain_events_count = cursor.fetchone()[0]
        logger.info(f"📊 Pain events from posts: {posts_pain_events_count:,}条 (不受影响)")

    logger.info("\n" + "=" * 80)
    return filtered_count, pain_events_count

def clean_comment_data(dry_run=False):
    """执行清理操作"""
    filtered_count, pain_events_count = show_pre_check_stats()

    if dry_run:
        logger.info("🔍 DRY RUN模式 - 不会实际删除数据")
        logger.info("如需执行清理，请使用 --confirm 参数")
        return False

    logger.info("\n⚠️  即将删除以下数据:")
    logger.info(f"  - {filtered_count:,} 条 filtered_comments")
    logger.info(f"  - {pain_events_count:,} 条来自comments的pain_events")
    logger.info("\n✅ Posts的数据不会受影响")

    confirm = input("\n确认执行清理? (输入 'yes' 继续): ")
    if confirm.lower() != 'yes':
        logger.info("❌ 已取消清理操作")
        return False

    logger.info("\n" + "=" * 80)
    logger.info("开始清理...")
    logger.info("=" * 80)

    try:
        # 步骤1: 删除来自comments的pain_events
        logger.info("\n[1/3] 删除来自comments的pain_events...")
        with db.get_connection("pain") as conn:
            cursor = conn.execute("DELETE FROM pain_events WHERE source_type = 'comment'")
            deleted_pain_events = cursor.rowcount
            conn.commit()
            logger.info(f"  ✅ 已删除 {deleted_pain_events:,} 条pain_events")

        # 步骤2: 删除filtered_comments
        logger.info("\n[2/3] 删除filtered_comments...")
        with db.get_connection("filtered") as conn:
            cursor = conn.execute("DELETE FROM filtered_comments")
            deleted_filtered = cursor.rowcount
            conn.commit()
            logger.info(f"  ✅ 已删除 {deleted_filtered:,} 条filtered_comments")

        # 步骤3: 重置自增ID
        logger.info("\n[3/3] 重置自增ID...")
        with db.get_connection("filtered") as conn:
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'filtered_comments'")
            conn.commit()
            logger.info(f"  ✅ 已重置filtered_comments的自增ID")

        logger.info("\n" + "=" * 80)
        logger.info("✅ 清理完成!")
        logger.info("=" * 80)

        # 验证清理结果
        logger.info("\n验证清理结果:")
        with db.get_connection("filtered") as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM filtered_comments")
            remaining = cursor.fetchone()[0]
            logger.info(f"  剩余 filtered_comments: {remaining} (应为0)")

        with db.get_connection("pain") as conn:
            cursor = conn.execute("""
                SELECT COUNT(*)
                FROM pain_events
                WHERE source_type = 'comment'
            """)
            remaining = cursor.fetchone()[0]
            logger.info(f"  剩余 pain_events (comments): {remaining} (应为0)")

            cursor = conn.execute("""
                SELECT COUNT(*)
                FROM pain_events
                WHERE source_type = 'post' OR source_type IS NULL
            """)
            posts_remaining = cursor.fetchone()[0]
            logger.info(f"  剩余 pain_events (posts): {posts_remaining} (应保持不变)")

        logger.info("\n🎉 数据清理完成，可以重新运行filter_comments.py应用新阈值")
        return True

    except Exception as e:
        logger.error(f"\n❌ 清理过程中出错: {e}")
        logger.error("请检查数据库状态，可能需要回滚")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="清理comment相关数据，以便重新应用新的过滤阈值"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预检查模式，只显示将要删除的数据，不实际删除"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="确认执行清理（需要手动输入yes确认）"
    )
    args = parser.parse_args()

    try:
        if args.dry_run:
            clean_comment_data(dry_run=True)
        elif args.confirm:
            success = clean_comment_data(dry_run=False)
            sys.exit(0 if success else 1)
        else:
            logger.info("使用 --dry-run 预检查，或 --confirm 执行清理")
            parser.print_help()
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  用户中断操作")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
