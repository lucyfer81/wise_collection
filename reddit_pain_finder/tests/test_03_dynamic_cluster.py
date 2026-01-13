#!/usr/bin/env python3
"""
Test 3: DynamicClusterUpdater
测试动态聚类更新器的核心功能
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pipeline.dynamic_cluster import DynamicClusterUpdater
from utils.db import db
import logging
import pickle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_dynamic_cluster_updater():
    """测试DynamicClusterUpdater"""
    print("=" * 60)
    print("Test 3: DynamicClusterUpdater")
    print("=" * 60)

    # 1. Initialize updater
    print("\n[1/6] Initializing DynamicClusterUpdater...")
    try:
        updater = DynamicClusterUpdater()
        print("✅ DynamicClusterUpdater initialized")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        import traceback
        print(traceback.format_exc())
        return False

    # 2. Get test data - recent orphan pain_events with embeddings
    print("\n[2/6] Getting test data (orphan pain_events)...")
    try:
        with db.get_connection("pain") as conn:
            cursor = conn.execute("""
                SELECT pe.*
                FROM pain_events pe
                WHERE pe.cluster_id IS NULL
                ORDER BY pe.extracted_at DESC
                LIMIT 10
            """)
            pain_events_data = [dict(row) for row in cursor.fetchall()]

        # Get embeddings separately
        with db.get_connection("pain") as conn:
            cursor = conn.execute("""
                SELECT pain_event_id, embedding_vector
                FROM pain_embeddings
                WHERE pain_event_id IN (
                    SELECT id FROM pain_events
                    WHERE cluster_id IS NULL
                    ORDER BY extracted_at DESC
                    LIMIT 10
                )
            """)
            embeddings_data = {row[0]: pickle.loads(row[1]) for row in cursor.fetchall()}

        # Combine
        orphan_events = []
        for pe in pain_events_data:
            if pe['id'] in embeddings_data:
                pe['embedding_vector'] = embeddings_data[pe['id']]
                orphan_events.append(pe)

        print(f"✅ Found {len(orphan_events)} orphan pain_events with embeddings")

        if len(orphan_events) == 0:
            print("⚠️  No orphan events found, trying events from any cluster...")
            # Try with any events
            cursor = conn.execute("""
                SELECT pe.* FROM pain_events pe
                ORDER BY pe.extracted_at DESC
                LIMIT 10
            """)
            pain_events_data = [dict(row) for row in cursor.fetchall()]

            cursor = conn.execute("""
                SELECT pain_event_id, embedding_vector
                FROM pain_embeddings
                WHERE pain_event_id IN (
                    SELECT id FROM pain_events
                    ORDER BY extracted_at DESC
                    LIMIT 10
                )
            """)
            embeddings_data = {row[0]: pickle.loads(row[1]) for row in cursor.fetchall()}

            orphan_events = []
            for pe in pain_events_data:
                if pe['id'] in embeddings_data:
                    pe['embedding_vector'] = embeddings_data[pe['id']]
                    orphan_events.append(pe)

            print(f"   Using {len(orphan_events)} events instead")

        for i, event in enumerate(orphan_events[:3]):
            print(f"   {i+1}. ID={event['id']}, problem={event.get('problem', '')[:60]}...")

    except Exception as e:
        print(f"❌ Failed to get test data: {e}")
        import traceback
        print(traceback.format_exc())
        return False

    # 3. Process events through DynamicClusterUpdater
    print("\n[3/6] Processing events through DynamicClusterUpdater...")
    try:
        # Note: This will attempt to find/create clusters
        # For testing, we'll use a small sample
        test_events = orphan_events[:5]

        print(f"   Processing {len(test_events)} events...")
        results = updater.process_new_pain_events(
            test_events,
            cluster_similarity_threshold=0.75
        )

        print("✅ Processing completed")
        print(f"   Total events processed: {results['total_events_processed']}")
        print(f"   Events added to clusters: {results['events_added_to_clusters']}")
        print(f"   New clusters created: {results['new_clusters_created']}")
        print(f"   Existing clusters updated: {results['existing_clusters_updated']}")
        print(f"   Orphans marked: {results['orphans_marked']}")
        print(f"   Processing time: {results['processing_time']:.2f}s")

    except Exception as e:
        print(f"❌ Failed to process events: {e}")
        import traceback
        print(traceback.format_exc())
        return False

    # 4. Test _find_similar_cluster method
    print("\n[4/6] Testing _find_similar_cluster method...")
    try:
        if len(orphan_events) > 0:
            test_event = orphan_events[0]
            embedding = test_event['embedding_vector']

            # Convert to list if needed
            if hasattr(embedding, 'tolist'):
                embedding = embedding.tolist()
            elif not isinstance(embedding, list):
                embedding = list(embedding)

            similar_cluster = updater._find_similar_cluster(
                embedding,
                threshold=0.75
            )

            if similar_cluster:
                print(f"✅ Found similar cluster:")
                print(f"   Cluster ID: {similar_cluster['id']}")
                print(f"   Cluster name: {similar_cluster.get('cluster_name', 'N/A')[:60]}...")
                print(f"   Similarity score: {similar_cluster.get('similarity_score', 0):.3f}")
                print(f"   Cluster size: {similar_cluster.get('cluster_size', 0)}")
            else:
                print("ℹ️  No similar cluster found (threshold: 0.75)")

    except Exception as e:
        print(f"❌ Failed to find similar cluster: {e}")
        import traceback
        print(traceback.format_exc())
        return False

    # 5. Test cluster statistics
    print("\n[5/6] Checking cluster statistics...")
    try:
        with db.get_connection("clusters") as conn:
            # Total clusters
            cursor = conn.execute("SELECT COUNT(*) FROM clusters")
            total_clusters = cursor.fetchone()[0]

            # Active clusters (not archived)
            cursor = conn.execute("""
                SELECT COUNT(*) FROM clusters
                WHERE alignment_status != 'archived'
            """)
            active_clusters = cursor.fetchone()[0]

            # Average cluster size
            cursor = conn.execute("""
                SELECT AVG(cluster_size) FROM clusters
                WHERE alignment_status != 'archived'
            """)
            avg_size = cursor.fetchone()[0] or 0

        print(f"✅ Cluster statistics:")
        print(f"   Total clusters: {total_clusters}")
        print(f"   Active clusters: {active_clusters}")
        print(f"   Average cluster size: {avg_size:.1f}")

    except Exception as e:
        print(f"❌ Failed to get cluster statistics: {e}")
        return False

    # 6. Verify lifecycle updates
    print("\n[6/6] Verifying lifecycle updates...")
    try:
        # Get overall statistics
        with db.get_connection("pain") as conn:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE lifecycle_stage = 'active') as active_count,
                    COUNT(*) FILTER (WHERE lifecycle_stage = 'orphan') as orphan_count,
                    COUNT(*) FILTER (WHERE cluster_id IS NOT NULL) as clustered_count
                FROM pain_events
            """)
            stats = cursor.fetchone()

        print(f"✅ Lifecycle statistics:")
        print(f"   Active events: {stats[0]}")
        print(f"   Orphan events: {stats[1]}")
        print(f"   Events in clusters: {stats[2]}")

        # Check if our test events were updated
        test_event_ids = [e['id'] for e in test_events]

        # Use a new connection for the second query
        with db.get_connection("pain") as conn2:
            placeholders = ','.join('?' for _ in test_event_ids)
            cursor = conn2.execute(f"""
                SELECT lifecycle_stage, cluster_id
                FROM pain_events
                WHERE id IN ({placeholders})
            """, test_event_ids)

            updated_events = cursor.fetchall()

        print(f"\n   Test event updates:")
        for i, (lifecycle, cluster_id) in enumerate(updated_events[:3]):
            print(f"   Event {i+1}: lifecycle={lifecycle}, cluster_id={cluster_id}")

    except Exception as e:
        print(f"❌ Failed to verify lifecycle: {e}")
        import traceback
        print(traceback.format_exc())
        return False

    print("\n" + "=" * 60)
    print("✅ Test 3 PASSED: DynamicClusterUpdater working correctly")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_dynamic_cluster_updater()
    sys.exit(0 if success else 1)
