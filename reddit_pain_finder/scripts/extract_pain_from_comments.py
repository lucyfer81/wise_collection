#!/usr/bin/env python3
"""
Extract Pain from Comments Script - Phase 2: Include Comments
从过滤评论中提取痛点事件脚本

This script extracts pain points from filtered comments, treating them as
independent pain sources with parent post as context.

**NOTE**: This is a STANDALONE script for one-time migration or manual use.
For automated extraction, use the main pipeline:

    python3 run_pipeline.py --stage extract_pain --include-comments

Usage:
    python3 scripts/extract_pain_from_comments.py [options]
"""
import os
import sys
import logging
import argparse
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.extract_pain import PainPointExtractor
from utils.db import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主函数 - 从评论提取痛点"""
    parser = argparse.ArgumentParser(
        description="Extract pain points from filtered comments (Phase 2: Include Comments)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Limit number of comments to process (default: 10 for testing)"
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
        help="Simulate extraction without saving to database"
    )
    args = parser.parse_args()

    try:
        logger.info("=" * 80)
        logger.info("Starting pain extraction from comments - Phase 2: Include Comments")
        logger.info("=" * 80)

        # 1. 检查数据库schema是否已迁移
        logger.info("Checking database schema...")
        try:
            with db.get_connection("pain") as conn:
                cursor = conn.execute("PRAGMA table_info(pain_events)")
                columns = {row['name'] for row in cursor.fetchall()}

                required_columns = {'source_type', 'source_id', 'parent_post_id'}
                missing_columns = required_columns - columns

                if missing_columns:
                    logger.error(f"Database schema not migrated! Missing columns: {missing_columns}")
                    logger.error("Please run: python3 migrations/002_add_source_tracking_to_pain_events.py")
                    sys.exit(1)

                logger.info("✓ Database schema verified")

        except Exception as e:
            logger.error(f"Failed to verify database schema: {e}")
            sys.exit(1)

        # 2. 初始化抽取器
        logger.info("Initializing PainPointExtractor...")
        extractor = PainPointExtractor()

        # 3. 获取过滤后的评论
        logger.info(f"Fetching filtered comments (limit={args.limit})...")
        filtered_comments = db.get_all_filtered_comments(limit=args.limit)

        if not filtered_comments:
            logger.info("No filtered comments found. Run filter_comments.py first.")
            return

        logger.info(f"Found {len(filtered_comments)} comments to extract from")

        # 显示评论统计
        pain_scores = [c.get("pain_score", 0) for c in filtered_comments]
        comment_scores = [c.get("score", 0) for c in filtered_comments]
        logger.info(f"Pain score range: {min(pain_scores):.2f} - {max(pain_scores):.2f}")
        logger.info(f"Comment score range: {min(comment_scores)} - {max(comment_scores)}")
        logger.info(f"Average pain score: {sum(pain_scores) / len(pain_scores):.2f}")

        # 4. 应用最小分数阈值
        if args.min_score > 0:
            logger.info(f"Applying min_pain_score threshold: {args.min_score}")
            before_count = len(filtered_comments)
            filtered_comments = [c for c in filtered_comments
                                if c.get("pain_score", 0) >= args.min_score]
            after_count = len(filtered_comments)
            logger.info(f"Filtered out {before_count - after_count} comments below threshold")

        # 5. 抽取痛点事件
        if args.dry_run:
            logger.info("=" * 80)
            logger.info("DRY RUN - Results will NOT be saved to database")
            logger.info("=" * 80)

            # 只处理前3个评论作为示例
            sample_comments = filtered_comments[:3]
            logger.info(f"Processing {len(sample_comments)} sample comments...")

            for comment in sample_comments:
                logger.info(f"\nProcessing comment {comment['comment_id']}...")
                events = extractor._extract_from_single_comment(comment)
                logger.info(f"  Extracted {len(events)} pain events")
                for i, event in enumerate(events, 1):
                    logger.info(f"    {i}. {event['problem'][:80]}...")

            logger.info("\nDry run complete!")
            return

        # 正式处理
        logger.info("Starting pain extraction...")
        start_time = datetime.now()

        result = extractor.process_unextracted_comments(limit=len(filtered_comments))

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # 6. 输出统计信息
        logger.info("=" * 80)
        logger.info("Extraction Summary")
        logger.info("=" * 80)
        logger.info(f"Comments processed:  {result['processed']}")
        logger.info(f"Failed:               {result['failed']}")
        logger.info(f"Pain events extracted:{result['pain_events_extracted']}")
        logger.info(f"Pain events saved:    {result['pain_events_saved']}")
        logger.info(f"Processing time:      {duration:.1f}s ({duration/max(result['processed'], 1):.2f}s per comment)")
        logger.info("")

        # 显示抽取统计
        stats = result['extraction_stats']
        logger.info("Extraction Statistics:")
        logger.info(f"  - Avg confidence:    {stats.get('avg_confidence', 0):.2f}")
        logger.info(f"  - Events per comment:{stats.get('avg_events_per_post', 0):.2f}")  # Note: reusing post stats
        logger.info(f"  - Error rate:        {stats.get('extraction_errors', 0)}")

        # 显示LLM统计
        if 'llm_stats' in stats:
            llm_stats = stats['llm_stats']
            logger.info(f"\nLLM Statistics:")
            logger.info(f"  - Requests:          {llm_stats.get('requests', 0)}")
            logger.info(f"  - Tokens used:       {llm_stats.get('tokens_used', 0)}")
            logger.info(f"  - Errors:            {llm_stats.get('errors', 0)}")

        logger.info("=" * 80)

        # 7. Sample extracted pain events
        if result['pain_events_saved'] > 0:
            logger.info("\nVerifying: Querying recent pain_events from comments...")
            with db.get_connection("pain") as conn:
                cursor = conn.execute("""
                    SELECT problem, source_type, extraction_confidence
                    FROM pain_events
                    WHERE source_type = 'comment'
                    ORDER BY extracted_at DESC
                    LIMIT 5
                """)
                sample_events = cursor.fetchall()

                if sample_events:
                    logger.info("Sample of 5 extracted pain events from comments:")
                    for i, event in enumerate(sample_events, 1):
                        logger.info(f"\n{i}. {event['problem'][:100]}...")
                        logger.info(f"   Source: {event['source_type']} | Confidence: {event['extraction_confidence']:.2f}")

        logger.info("")
        logger.info("Extraction complete!")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
