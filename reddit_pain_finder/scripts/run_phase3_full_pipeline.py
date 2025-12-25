#!/usr/bin/env python3
"""
Phase 3: Full Pipeline Execution with Performance Monitoring
运行完整流水线并收集性能数据
"""
import sys
import os
import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pipeline.extract_pain import PainPointExtractor
from pipeline.embed import PainEventEmbedder
from pipeline.cluster import PainEventClusterer
from pipeline.score_viability import ViabilityScorer
from pipeline.map_opportunity import OpportunityMapper
from utils.performance_monitor import performance_monitor
from utils.db import db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_phase3_pipeline(limit_posts: int = 100, save_metrics: bool = True):
    """运行Phase 3完整流水线"""

    logger.info("=" * 60)
    logger.info("PHASE 3: Full Pipeline Execution")
    logger.info(f"Limit: {limit_posts} posts")
    logger.info("=" * 60)

    results = {}

    # Stage 1: Extract Pain Points
    logger.info("\n[Stage 1/5] Extracting pain points...")
    performance_monitor.start_stage("extract")

    try:
        extractor = PainPointExtractor()
        extract_result = extractor.process_unextracted_posts(limit=limit_posts)
        results["extract"] = extract_result

        performance_monitor.end_stage("extract", extract_result.get("processed", 0))
        logger.info(f"✓ Extracted {extract_result.get('pain_events_saved', 0)} pain events")
    except Exception as e:
        logger.error(f"✗ Extraction failed: {e}")
        performance_monitor.end_stage("extract", 0)
        results["extract"] = {"error": str(e)}

    # Stage 2: Create Embeddings
    logger.info("\n[Stage 2/5] Creating embeddings...")
    performance_monitor.start_stage("embed")

    try:
        embedder = PainEventEmbedder()
        embed_result = embedder.process_missing_embeddings(limit=limit_posts * 2)
        results["embed"] = embed_result

        performance_monitor.end_stage("embed", embed_result.get("embeddings_created", 0))
        logger.info(f"✓ Created {embed_result.get('embeddings_created', 0)} embeddings")
    except Exception as e:
        logger.error(f"✗ Embedding failed: {e}")
        performance_monitor.end_stage("embed", 0)
        results["embed"] = {"error": str(e)}

    # Stage 3: Cluster Pain Events
    logger.info("\n[Stage 3/5] Clustering pain events...")
    performance_monitor.start_stage("cluster")

    try:
        clusterer = PainEventClusterer()
        cluster_result = clusterer.cluster_pain_events(limit=limit_posts * 2)
        results["cluster"] = cluster_result

        performance_monitor.end_stage("cluster", cluster_result.get("clusters_created", 0))
        logger.info(f"✓ Created {cluster_result.get('clusters_created', 0)} clusters")
    except Exception as e:
        logger.error(f"✗ Clustering failed: {e}")
        performance_monitor.end_stage("cluster", 0)
        results["cluster"] = {"error": str(e)}

    # Stage 4: Map Opportunities
    logger.info("\n[Stage 4/5] Mapping opportunities...")
    performance_monitor.start_stage("map_opportunities")

    try:
        mapper = OpportunityMapper()
        map_result = mapper.map_opportunities_for_clusters(limit=50)
        results["map_opportunities"] = map_result

        performance_monitor.end_stage("map_opportunities", map_result.get("opportunities_created", 0))
        logger.info(f"✓ Mapped {map_result.get('opportunities_created', 0)} opportunities")
    except Exception as e:
        logger.error(f"✗ Opportunity mapping failed: {e}")
        performance_monitor.end_stage("map_opportunities", 0)
        results["map_opportunities"] = {"error": str(e)}

    # Stage 5: Score Viability
    logger.info("\n[Stage 5/5] Scoring viability...")
    performance_monitor.start_stage("score")

    try:
        scorer = ViabilityScorer()
        score_result = scorer.score_opportunities(limit=100)
        results["score"] = score_result

        performance_monitor.end_stage("score", score_result.get("opportunities_scored", 0))
        logger.info(f"✓ Scored {score_result.get('opportunities_scored', 0)} opportunities")
    except Exception as e:
        logger.error(f"✗ Viability scoring failed: {e}")
        performance_monitor.end_stage("score", 0)
        results["score"] = {"error": str(e)}

    # Generate Summary
    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE COMPLETE - GENERATING SUMMARY")
    logger.info("=" * 60)

    summary = performance_monitor.get_summary()

    logger.info(f"\n📊 Performance Summary:")
    logger.info(f"   • Total Duration: {summary['total_duration_minutes']} minutes")
    logger.info(f"   • LLM Calls: {summary['total_llm_calls']}")
    logger.info(f"   • Total Tokens: {summary['total_tokens']:,}")
    logger.info(f"   • Est. Cost: ${summary['estimated_cost_usd']:.4f} USD")

    logger.info(f"\n📈 Stage Details:")
    for stage_name, stage_stats in summary['stages_summary'].items():
        logger.info(f"   • {stage_name}:")
        logger.info(f"     - Duration: {stage_stats['duration_seconds']:.1f}s")
        logger.info(f"     - Items: {stage_stats['items_processed']}")
        logger.info(f"     - Tokens: {stage_stats['tokens_used']:,}")

    # Save metrics
    if save_metrics:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        metrics_file = f"docs/reports/phase3_metrics_{timestamp}.json"
        os.makedirs(os.path.dirname(metrics_file), exist_ok=True)
        performance_monitor.save_metrics(metrics_file)
        logger.info(f"\n💾 Metrics saved to: {metrics_file}")

    return results, summary


def main():
    parser = argparse.ArgumentParser(description="Phase 3 Full Pipeline Execution")
    parser.add_argument("--limit-posts", type=int, default=100,
                       help="Number of posts to process (default: 100)")
    parser.add_argument("--no-save", action="store_true",
                       help="Don't save metrics to file")

    args = parser.parse_args()

    try:
        results, summary = run_phase3_pipeline(
            limit_posts=args.limit_posts,
            save_metrics=not args.no_save
        )

        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"docs/reports/phase3_results_{timestamp}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({"results": results, "summary": summary}, f, indent=2)

        logger.info(f"\n✅ All results saved to: {results_file}")

    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
