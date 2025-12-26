#!/usr/bin/env python3
"""
Cross-Source Pain Points Viewer

显示所有跨源验证的痛点，回答："现阶段世界上'被不同社群独立提及'的痛点有哪些？"
"""

import argparse
import json
import logging
import sys
import os
from typing import List, Dict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def format_opportunity(opportunity: Dict, detailed: bool = False) -> str:
    """格式化单个机会显示

    Args:
        opportunity: 机会数据
        detailed: 是否显示详细信息

    Returns:
        格式化的字符串
    """
    cross_source = opportunity.get('cross_source_validation', {})
    validation_level = cross_source.get('validation_level', 0)

    # 验证等级徽章
    level_badges = {
        1: "LEVEL 1 - Multi-Platform Validation",
        2: "LEVEL 2 - Multi-Subreddit Validation",
        3: "LEVEL 3 - Weak Cross-Source Signal"
    }

    badge = level_badges.get(validation_level, "")

    lines = [
        f"\n{'='*80}",
        f"{opportunity['opportunity_name']}",
        f"{'='*80}",
        f"\n{badge}" if badge else "",
        f"\nScores:",
        # Note: 'total_score' matches the field name from the database schema (opportunities.total_score)
        f"  - Final Score: {opportunity.get('total_score', 0):.2f}/10.0",
        f"  - Cluster Size: {opportunity.get('cluster_size', 0)}",
        f"  - Trust Level: {opportunity.get('trust_level', 0):.2f}",
        f"\nValidation: {cross_source.get('evidence', 'N/A')}",
        f"  Boost Applied: +{cross_source.get('boost_score', 0.0):.1f}",
        f"  Validated Problem: {'Yes' if cross_source.get('validated_problem') else 'No'}",
    ]

    if detailed:
        lines.extend([
            f"\nTarget Users:",
            f"  {opportunity.get('target_users', 'N/A')}",
            f"\nMissing Capability:",
            f"  {opportunity.get('missing_capability', 'N/A')}",
            f"\nWhy Existing Solutions Fail:",
            f"  {opportunity.get('why_existing_fail', 'N/A')}",
            f"\nCluster Info:",
            f"  - Cluster Name: {opportunity.get('cluster_name', 'N/A')}",
            f"  - Source Type: {opportunity.get('source_type', 'N/A')}",
            f"  - Alignment Status: {opportunity.get('alignment_status', 'N/A')}",
        ])

    return '\n'.join(lines)


def print_summary(opportunities: List[Dict]):
    """打印统计摘要

    Args:
        opportunities: 机会列表
    """
    total = len(opportunities)

    if total == 0:
        print("\nNo cross-source validated pain points found.")
        return

    # 按等级统计
    level_counts = {1: 0, 2: 0, 3: 0}
    validated_count = 0

    for opp in opportunities:
        cs = opp.get('cross_source_validation', {})
        level = cs.get('validation_level', 0)
        if level in level_counts:
            level_counts[level] += 1
        if cs.get('validated_problem'):
            validated_count += 1

    print("\n" + "="*80)
    print("CROSS-SOURCE VALIDATED PAIN POINTS SUMMARY")
    print("="*80)
    print(f"\nTotal Opportunities: {total}")
    print(f"\n  Level 1 (Multi-Platform): {level_counts[1]}")
    print(f"  Level 2 (Multi-Subreddit): {level_counts[2]}")
    print(f"  Level 3 (Weak Signal): {level_counts[3]}")
    print(f"\n  Validated Problems: {validated_count}")
    print(f"  Not Validated: {total - validated_count}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Display cross-source validated pain points",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 显示所有跨源验证的痛点（摘要）
  python scripts/show_cross_source_pain_points.py

  # 显示详细信息
  python scripts/show_cross_source_pain_points.py --detailed

  # 仅显示 Level 1 的多平台验证
  python scripts/show_cross_source_pain_points.py --min-level 1

  # 包含未验证的痛点（validated_problem=False）
  python scripts/show_cross_source_pain_points.py --include-unvalidated

  # 导出到 JSON
  python scripts/show_cross_source_pain_points.py --export cross_source.json
        """
    )

    parser.add_argument(
        '--min-level',
        type=int,
        choices=[1, 2, 3],
        default=1,
        help='Minimum validation level (default: 1)'
    )

    parser.add_argument(
        '--include-unvalidated',
        action='store_true',
        help='Include opportunities with validated_problem=False (default: False - show only validated)'
    )

    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed information for each opportunity'
    )

    parser.add_argument(
        '--export',
        type=str,
        metavar='FILE',
        help='Export results to JSON file'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of results (default: show all)'
    )

    args = parser.parse_args()

    # 查询数据库
    logger.info("Querying cross-source validated pain points...")

    try:
        opportunities = db.get_cross_source_validated_opportunities(
            min_validation_level=args.min_level,
            include_validated_only=not args.include_unvalidated
        )

        # 应用限制
        if args.limit:
            opportunities = opportunities[:args.limit]

        # 打印摘要
        print_summary(opportunities)

        # 导出到 JSON
        if args.export:
            export_data = {
                'generated_at': __import__('datetime').datetime.now().isoformat(),
                'filter': {
                    'min_validation_level': args.min_level,
                    'validated_only': not args.include_unvalidated
                },
                'total_count': len(opportunities),
                'opportunities': opportunities
            }

            with open(args.export, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Exported to {args.export}")

        # 打印每个机会
        for opp in opportunities:
            print(format_opportunity(opp, detailed=args.detailed))

        print(f"\n{'='*80}\n")
        logger.info(f"Displayed {len(opportunities)} cross-source validated pain points")

    except Exception as e:
        logger.error(f"Error querying cross-source validated pain points: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
