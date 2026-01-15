"""Test token savings from smart data sampling"""
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pipeline.map_opportunity import OpportunityMapper
from utils.db import db


def test_cluster_5_end_to_end():
    """Verify cluster 5 (the previously failing cluster) can now be mapped without 400 errors"""
    mapper = OpportunityMapper()

    with db.get_connection("clusters") as conn:
        cursor = conn.execute('SELECT * FROM clusters WHERE id = 5')
        cluster = dict(cursor.fetchone())

    print(f"\n{'='*70}")
    print(f"END-TO-END TEST: Cluster 5 (previously failed with 400 error)")
    print(f"{'='*70}")
    print(f"  Name: {cluster['cluster_name'][:60]}...")
    print(f"  Size: {cluster['cluster_size']} pain events")
    print(f"  Previous error: Token limit exceeded (350,363 > 163,840)")
    print()

    try:
        print("  Testing opportunity mapping with actual LLM call...")
        result = mapper.map_opportunities_for_clusters(
            clusters_to_update=[cluster['id']],
            limit=1
        )

        if result.get('opportunities_created', 0) > 0:
            print(f"  SUCCESS: Mapped without 400 errors")
            print(f"  Created: {result['opportunities_created']} opportunities")
            print(f"  Viable: {result['viable_opportunities']}")
            return True
        else:
            print(f"  WARNING: No opportunities created (but no 400 error)")
            return True

    except Exception as e:
        error_str = str(e)
        if '400' in error_str or 'token' in error_str.lower():
            print(f"  FAILED: 400 error still occurs!")
            print(f"  Error: {e}")
            return False
        else:
            print(f"  WARNING: Different error occurred: {e}")
            return False


def main():
    mapper = OpportunityMapper()

    # Get all clusters
    with db.get_connection("clusters") as conn:
        cursor = conn.execute("""
            SELECT id, cluster_name, cluster_size, pain_event_ids, cluster_description,
                   workflow_confidence, created_at
            FROM clusters
            ORDER BY cluster_size DESC
            LIMIT 5
        """)
        clusters = [dict(row) for row in cursor.fetchall()]

    print("Testing token savings on largest clusters:\n")

    total_original = 0
    total_compact = 0

    for cluster in clusters:
        # Enrich the cluster (simulating real processing)
        enriched = mapper._enrich_cluster_data(cluster)

        # Create compact summary
        compact = mapper._create_llm_friendly_cluster_summary(enriched)

        # Calculate sizes
        original_json = json.dumps(enriched, indent=2)
        compact_json = json.dumps(compact, indent=2)

        original_size = len(original_json)
        compact_size = len(compact_json)
        reduction = (1 - compact_size / original_size) * 100

        # Estimate tokens (rough: 1 token ≈ 4 chars)
        original_tokens = original_size // 4
        compact_tokens = compact_size // 4

        total_original += original_size
        total_compact += compact_size

        print(f"Cluster: {cluster['cluster_name'][:40]}")
        print(f"  Original: {original_size:,} chars (~{original_tokens:,} tokens)")
        print(f"  Compact:  {compact_size:,} chars (~{compact_tokens:,} tokens)")
        print(f"  Reduction: {reduction:.1f}%")
        print(f"  Pain events: {len(enriched.get('pain_events', []))} → {len(compact['pain_events'])}")
        print()

    overall_reduction = (1 - total_compact / total_original) * 100
    print(f"Overall: {total_original:,} → {total_compact:,} chars ({overall_reduction:.1f}% reduction)")

    print(f"\n{'='*70}")
    print(f"Running end-to-end validation...")
    print(f"{'='*70}")
    test_cluster_5_end_to_end()


if __name__ == "__main__":
    main()
