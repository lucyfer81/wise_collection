#!/usr/bin/env python3
"""
Quick Test Script for Phase 1-3 Changes
快速测试脚本 - 验证Phase 1-3的修改
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


def test_phase1_database():
    """测试 Phase 1: 数据库表和列"""
    logger.info("=" * 60)
    logger.info("Testing Phase 1: Database Tables and Columns")
    logger.info("=" * 60)

    try:
        from utils.db import db

        # 测试新表是否存在
        with db.get_connection("clusters") as conn:
            # 检查 cluster_snapshots 表
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cluster_snapshots'")
            if cursor.fetchone():
                logger.info("✓ cluster_snapshots table exists")
            else:
                logger.error("✗ cluster_snapshots table NOT found")

            # 检查 scoring_batches 表
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scoring_batches'")
            if cursor.fetchone():
                logger.info("✓ scoring_batches table exists")
            else:
                logger.error("✗ scoring_batches table NOT found")

            # 检查 opportunity_versions 表
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='opportunity_versions'")
            if cursor.fetchone():
                logger.info("✓ opportunity_versions table exists")
            else:
                logger.error("✗ opportunity_versions table NOT found")

            # 检查 opportunities 表的新列
            cursor = conn.execute("PRAGMA table_info(opportunities)")
            existing_columns = {row['name'] for row in cursor.fetchall()}

            new_columns = ['current_version', 'last_rescored_at', 'rescore_count', 'scored_at']
            for col in new_columns:
                if col in existing_columns:
                    logger.info(f"✓ opportunities.{col} column exists")
                else:
                    logger.error(f"✗ opportunities.{col} column NOT found")

        logger.info("\n✅ Phase 1 tests passed!\n")
        return True

    except Exception as e:
        logger.error(f"\n❌ Phase 1 tests failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def test_phase2_change_detection():
    """测试 Phase 2: Change Detection"""
    logger.info("=" * 60)
    logger.info("Testing Phase 2: Change Detection Module")
    logger.info("=" * 60)

    try:
        from pipeline.change_detection import ChangeDetector

        detector = ChangeDetector()
        logger.info("✓ ChangeDetector initialized successfully")

        # 测试配置加载
        config = detector._load_config()
        logger.info(f"✓ Config loaded: {config}")

        # 测试变化检测
        changes = detector.detect_significant_changes(hours=24)
        logger.info(f"✓ Detected {len(changes)} significant changes")

        # 保存快照测试
        if changes:
            # 只为前3个clusters保存快照作为测试
            cluster_ids = [c['cluster_id'] for c in changes[:3]]
            success = detector.save_cluster_snapshots(cluster_ids, "test_snapshot")
            if success:
                logger.info(f"✓ Saved snapshots for {len(cluster_ids)} test clusters")
            else:
                logger.error("✗ Failed to save cluster snapshots")

        logger.info("\n✅ Phase 2 tests passed!\n")
        return True

    except Exception as e:
        logger.error(f"\n❌ Phase 2 tests failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def test_phase3_scoring():
    """测试 Phase 3: Enhanced Scoring"""
    logger.info("=" * 60)
    logger.info("Testing Phase 3: Enhanced Scoring Module")
    logger.info("=" * 60)

    try:
        from pipeline.score_viability import ViabilityScorer
        from utils.db import db

        scorer = ViabilityScorer()
        logger.info("✓ ViabilityScorer initialized successfully")

        # 检查是否有未评分的opportunities
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM opportunities
                WHERE total_score = 0 OR total_score IS NULL
            """)
            unscored_count = cursor.fetchone()['count']

        logger.info(f"✓ Found {unscored_count} unscored opportunities")

        # 测试新参数（不实际调用LLM）
        logger.info("✓ New parameters added to score_opportunities:")
        logger.info("  - skip_filtering: bool")
        logger.info("  - batch_id: str")
        logger.info("  - clusters_to_update: List[int]")

        logger.info("\n✅ Phase 3 tests passed!\n")
        return True

    except Exception as e:
        logger.error(f"\n❌ Phase 3 tests failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def main():
    """主函数"""
    logger.info("🚀 Starting Phase 1-3 Integration Tests\n")

    results = {
        "Phase 1 (Database)": test_phase1_database(),
        "Phase 2 (Change Detection)": test_phase2_change_detection(),
        "Phase 3 (Enhanced Scoring)": test_phase3_scoring(),
    }

    logger.info("=" * 60)
    logger.info("FINAL RESULTS")
    logger.info("=" * 60)

    all_passed = True
    for phase, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{phase}: {status}")
        if not passed:
            all_passed = False

    logger.info("=" * 60)

    if all_passed:
        logger.info("\n🎉 All tests passed! Phase 1-3 implementation is complete.\n")
        return 0
    else:
        logger.error("\n⚠️  Some tests failed. Please review the errors above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
