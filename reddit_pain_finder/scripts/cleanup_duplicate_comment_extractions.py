#!/usr/bin/env python3
"""
清理重复抽取的comment pain events
删除重复的comment抽取记录，只保留每个comment最早抽取的那一条
"""
import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def analyze_duplicates():
    """分析重复抽取情况"""
    with db.get_connection("pain") as conn:
        cursor = conn.execute("""
            SELECT source_id, COUNT(*) as count, MIN(extracted_at) as first_extracted
            FROM pain_events
            WHERE source_type = 'comment'
            GROUP BY source_id
            HAVING count > 1
            ORDER BY count DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def cleanup_duplicates(dry_run=True):
    """清理重复抽取

    Args:
        dry_run: 如果为True，只分析不实际删除

    Returns:
        清理统计信息
    """
    logger.info("=" * 80)
    logger.info("清理重复抽取的comment pain events")
    if dry_run:
        logger.info("DRY RUN MODE - 不会实际删除数据")
    logger.info("=" * 80)

    # 1. 分析重复情况
    duplicates = analyze_duplicates()

    if not duplicates:
        logger.info("✅ 没有发现重复抽取的comments")
        return {
            "duplicates_found": 0,
            "total_events": 0,
            "to_keep": 0,
            "to_delete": 0
        }

    total_duplicate_events = sum(d["count"] for d in duplicates)
    to_keep = len(duplicates)
    to_delete = total_duplicate_events - to_keep

    logger.info(f"\n发现 {len(duplicates)} 条comments被重复抽取")
    logger.info(f"总重复事件数: {total_duplicate_events}")
    logger.info(f"需要保留: {to_keep} 条（每个comment最早的一条）")
    logger.info(f"需要删除: {to_delete} 条")
    logger.info("")

    # 2. 显示重复详情（前10条）
    logger.info("重复抽取详情（前10条）:")
    logger.info("-" * 80)
    for i, d in enumerate(duplicates[:10], 1):
        logger.info(f'{i}. comment_id={d["source_id"]}: {d["count"]}次抽取, 最早={d["first_extracted"]}')

    if len(duplicates) > 10:
        logger.info(f"... 还有 {len(duplicates) - 10} 条")

    # 3. 执行清理（如果不是dry run）
    if dry_run:
        logger.info("\n" + "=" * 80)
        logger.info("DRY RUN完成 - 实际运行时将删除以上重复数据")
        logger.info("=" * 80)
        return {
            "duplicates_found": len(duplicates),
            "total_events": total_duplicate_events,
            "to_keep": to_keep,
            "to_delete": to_delete
        }

    # 实际删除
    logger.info("\n" + "=" * 80)
    logger.info("开始清理...")
    logger.info("=" * 80)

    deleted_count = 0
    with db.get_connection("pain") as conn:
        for i, dup in enumerate(duplicates, 1):
            comment_id = dup["source_id"]

            # 找到该comment_id最小的ID（保留）
            cursor = conn.execute("""
                SELECT MIN(id) as keep_id
                FROM pain_events
                WHERE source_type = 'comment' AND source_id = ?
            """, (comment_id,))
            result = cursor.fetchone()
            keep_id = result["keep_id"] if result else None

            if not keep_id:
                logger.warning(f"⚠️ comment {comment_id} 没有找到记录，跳过")
                continue

            # 删除该comment_id下，ID不是最小ID的所有记录
            cursor = conn.execute("""
                DELETE FROM pain_events
                WHERE source_type = 'comment'
                  AND source_id = ?
                  AND id != ?
            """, (comment_id, keep_id))

            rows_deleted = cursor.rowcount
            deleted_count += rows_deleted

            if i % 5 == 0 or i == len(duplicates):
                logger.info(f"进度: {i}/{len(duplicates)} comments, 已删除: {deleted_count} 条")

        conn.commit()

    logger.info("\n" + "=" * 80)
    logger.info("✅ 清理完成!")
    logger.info("=" * 80)

    return {
        "duplicates_found": len(duplicates),
        "total_events": total_duplicate_events,
        "to_keep": to_keep,
        "to_delete": to_delete,
        "deleted_count": deleted_count
    }


def verify_cleanup():
    """验证清理结果"""
    logger.info("\n验证清理结果...")

    with db.get_connection("pain") as conn:
        # 检查是否还有重复
        cursor = conn.execute("""
            SELECT source_id, COUNT(*) as count
            FROM pain_events
            WHERE source_type = 'comment'
            GROUP BY source_id
            HAVING count > 1
        """)
        remaining_duplicates = cursor.fetchall()

        if remaining_duplicates:
            logger.warning(f"⚠️ 仍有 {len(remaining_duplicates)} 条comments存在重复抽取!")
            return False
        else:
            logger.info("✅ 没有重复抽取的comments")

        # 统计当前的comment events
        cursor = conn.execute("""
            SELECT COUNT(DISTINCT source_id) as unique_comments, COUNT(*) as total_events
            FROM pain_events
            WHERE source_type = 'comment'
        """)
        stats = cursor.fetchone()

        logger.info(f"当前统计:")
        logger.info(f"  唯一评论数: {stats['unique_comments']}")
        logger.info(f"  总事件数: {stats['total_events']}")

        return True


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="清理重复抽取的comment pain events"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="分析但不实际删除（默认启用）"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行清理（默认只分析）"
    )

    args = parser.parse_args()

    try:
        # 如果用户指定了 --execute，则关闭 dry_run
        dry_run = not args.execute

        # 执行清理
        result = cleanup_duplicates(dry_run=dry_run)

        # 如果不是dry run，验证结果
        if not dry_run:
            verify_cleanup()

        # 输出摘要
        logger.info("\n" + "=" * 80)
        logger.info("清理摘要")
        logger.info("=" * 80)
        logger.info(f"发现的重复comments: {result['duplicates_found']}")
        logger.info(f"总事件数（清理前）: {result['total_events']}")
        logger.info(f"保留: {result['to_keep']}")
        logger.info(f"删除: {result.get('deleted_count', result['to_delete'])}")
        logger.info("=" * 80)

        if dry_run:
            logger.info("\n💡 提示: 这是DRY RUN，没有实际删除数据")
            logger.info("💡 要实际执行清理，请运行:")
            logger.info("   python3 scripts/cleanup_duplicate_comment_extractions.py --execute")

    except Exception as e:
        logger.error(f"清理失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
