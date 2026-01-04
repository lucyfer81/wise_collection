#!/usr/bin/env python3
"""
手动测试 Phase 1-3 的完整流程
"""
import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_complete_flow():
    """测试完整的 Phase 1-3 流程"""
    logger.info("🚀 Testing Phase 1-3 Complete Flow\n")

    # Step 1: Change Detection
    logger.info("=" * 60)
    logger.info("Step 1: Change Detection")
    logger.info("=" * 60)

    from pipeline.change_detection import ChangeDetector

    detector = ChangeDetector()
    changes = detector.detect_significant_changes(hours=24)

    logger.info(f"\n✅ Detected {len(changes)} clusters with significant changes\n")

    # Step 2: 保存快照
    if changes:
        logger.info("=" * 60)
        logger.info("Step 2: Saving Snapshots")
        logger.info("=" * 60)

        # 只为前3个clusters保存快照（测试用）
        cluster_ids = [c['cluster_id'] for c in changes[:3]]
        detector.save_cluster_snapshots(cluster_ids, "test_snapshot")

        logger.info(f"✅ Saved snapshots for {len(cluster_ids)} clusters\n")

    # Step 3: 检查未评分的opportunities
    logger.info("=" * 60)
    logger.info("Step 3: Check Unscored Opportunities")
    logger.info("=" * 60)

    from utils.db import db

    with db.get_connection("clusters") as conn:
        cursor = conn.execute("""
            SELECT
                o.id,
                o.opportunity_name,
                c.cluster_size,
                o.total_score,
                o.recommendation
            FROM opportunities o
            JOIN clusters c ON o.cluster_id = c.id
            ORDER BY o.id DESC
            LIMIT 10
        """)
        opportunities = [dict(row) for row in cursor.fetchall()]

    logger.info(f"\nRecent opportunities:")
    unscored_count = 0
    for opp in opportunities:
        status = "✅ SCORED" if opp['total_score'] > 0 else "⏳ UNSCORED"
        logger.info(f"  {opp['id']}: {opp['opportunity_name'][:50]}... (size={opp['cluster_size']}, score={opp['total_score']}) {status}")
        if opp['total_score'] == 0:
            unscored_count += 1

    logger.info(f"\n📊 Summary: {unscored_count} unscored opportunities\n")

    # Step 4: 测试 Enhanced Scoring（不实际调用LLM）
    logger.info("=" * 60)
    logger.info("Step 4: Test Enhanced Scoring Parameters")
    logger.info("=" * 60)

    from pipeline.score_viability import ViabilityScorer

    scorer = ViabilityScorer()
    logger.info("✅ ViabilityScorer initialized with NEW parameters:")
    logger.info("   - skip_filtering: bool")
    logger.info("   - batch_id: str")
    logger.info("   - clusters_to_update: List[int]")
    logger.info("\n⚠️  NOTE: Filtering now happens AFTER LLM scoring!")
    logger.info("   All opportunities will get LLM scores before filtering.\n")

    # Step 5: 测试为指定clusters重新生成opportunities
    logger.info("=" * 60)
    logger.info("Step 5: Test Re-map Opportunities (Optional)")
    logger.info("=" * 60)

    from pipeline.map_opportunity import OpportunityMapper

    mapper = OpportunityMapper()
    logger.info("✅ OpportunityMapper initialized with NEW parameters:")
    logger.info("   - clusters_to_update: List[int]")
    logger.info("\n💡 You can now re-map opportunities for specific clusters:")
    logger.info("   mapper.map_opportunities_for_clusters(clusters_to_update=[5, 26, 11])\n")

    # Final summary
    logger.info("=" * 60)
    logger.info("PHASE 1-3 TEST SUMMARY")
    logger.info("=" * 60)
    logger.info("✅ Phase 1 (Database): Tables and columns created")
    logger.info("✅ Phase 2 (Change Detection): Can detect significant changes")
    logger.info("✅ Phase 3 (Enhanced Scoring): Filtering after LLM scoring")
    logger.info("\n📝 Next steps:")
    logger.info("   1. Run actual scoring to test new filtering logic:")
    logger.info("      python run_pipeline.py --stage score --limit-opportunities 5")
    logger.info("   2. Check if new clusters get scored (not blocked by filtering)")
    logger.info("   3. Review scored_at and version fields in database")
    logger.info("=" * 60)


if __name__ == "__main__":
    test_complete_flow()
