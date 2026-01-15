"""Test token savings from smart data sampling"""
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pipeline.map_opportunity import OpportunityMapper
from utils.db import db


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


if __name__ == "__main__":
    main()
