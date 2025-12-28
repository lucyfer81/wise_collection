#!/usr/bin/env python3
"""
Filter Comments Script - Phase 1: Include Comments
过滤评论脚本 - 将评论作为独立pain source进行过滤

This script filters Reddit/HN comments through the pain signal detector,
treating comments as independent pain sources (not post dependencies).
"""
import os
import sys
import logging
import argparse
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.filter_signal import PainSignalFilter
from utils.db import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主函数 - 过滤评论"""
    parser = argparse.ArgumentParser(
        description="Filter comments for pain signals (Phase 1: Include Comments)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of comments to process (default: all)"
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Minimum pain score threshold (default: 0.0)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate filtering without saving to database"
    )
    args = parser.parse_args()

    try:
        logger.info("=" * 80)
        logger.info("Starting comment filtering - Phase 1: Include Comments")
        logger.info("=" * 80)

        # 1. 初始化过滤器
        logger.info("Initializing PainSignalFilter...")
        filter = PainSignalFilter()

        # 2. 获取未过滤的评论
        logger.info(f"Fetching unfiltered comments (limit={args.limit or 'all'})...")
        comments = db.get_all_comments_for_filtering(limit=args.limit)

        if not comments:
            logger.info("No unfiltered comments found. All comments may have been processed.")
            return

        logger.info(f"Found {len(comments)} comments to filter")

        # 显示评论统计
        scores = [c.get("score", 0) for c in comments]
        logger.info(f"Score range: {min(scores)} - {max(scores)}")
        logger.info(f"Average score: {sum(scores) / len(scores):.1f}")

        # 3. 批量过滤
        logger.info("Starting pain signal filtering...")
        start_time = datetime.now()

        filtered_comments = filter.filter_comments_batch(comments)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # 4. 应用最小分数阈值
        if args.min_score > 0:
            logger.info(f"Applying min_score threshold: {args.min_score}")
            before_count = len(filtered_comments)
            filtered_comments = [c for c in filtered_comments
                                if c.get("pain_score", 0) >= args.min_score]
            after_count = len(filtered_comments)
            logger.info(f"Filtered out {before_count - after_count} comments below threshold")

        # 5. 保存结果（或显示dry run结果）
        if args.dry_run:
            logger.info("=" * 80)
            logger.info("DRY RUN - Results will NOT be saved to database")
            logger.info("=" * 80)
        else:
            logger.info("Saving filtered comments to database...")
            saved_count = db.save_filtered_comments(filtered_comments)
            logger.info(f"Successfully saved {saved_count}/{len(filtered_comments)} filtered comments")

        # 6. 输出统计信息
        stats = filter.get_statistics()
        logger.info("=" * 80)
        logger.info("Filter Summary")
        logger.info("=" * 80)
        logger.info(f"Total processed:     {stats['total_processed']}")
        logger.info(f"Passed filter:       {stats['passed_filter']}")
        logger.info(f"Filtered out:        {stats['filtered_out']}")
        logger.info(f"Pass rate:           {stats['pass_rate']:.2%}")
        logger.info(f"Processing time:     {duration:.1f}s ({duration/max(len(comments), 1):.2f}s per comment)")
        logger.info("")

        # Top filter reasons
        if stats['filter_reasons']:
            logger.info("Top Filter Reasons:")
            sorted_reasons = sorted(stats['filter_reasons'].items(),
                                   key=lambda x: x[1], reverse=True)[:5]
            for reason, count in sorted_reasons:
                logger.info(f"  - {reason}: {count}")

        # Pain score distribution
        if filtered_comments:
            pain_scores = [c.get("pain_score", 0) for c in filtered_comments]
            logger.info("")
            logger.info("Pain Score Distribution (filtered comments):")
            logger.info(f"  - Min:    {min(pain_scores):.2f}")
            logger.info(f"  - Max:    {max(pain_scores):.2f}")
            logger.info(f"  - Average: {sum(pain_scores) / len(pain_scores):.2f}")

        logger.info("=" * 80)

        # 7. Sample filtered comments（for quality check）
        if filtered_comments and not args.dry_run:
            logger.info("")
            logger.info("Sample of 5 filtered comments:")
            logger.info("-" * 80)
            for i, comment in enumerate(filtered_comments[:5], 1):
                logger.info(f"\n{i}. Comment ID: {comment['comment_id']}")
                logger.info(f"   Score: {comment['score']} | Pain Score: {comment['pain_score']:.2f}")
                logger.info(f"   Body: {comment['body'][:150]}...")
                logger.info(f"   Keywords: {comment.get('pain_keywords', [])[:3]}")

        logger.info("")
        logger.info("Filter complete!")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
