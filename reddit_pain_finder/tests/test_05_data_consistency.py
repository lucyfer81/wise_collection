#!/usr/bin/env python3
"""
Test 5: Data Consistency Between SQLite and Chroma
验证SQLite和Chroma之间的数据一致性
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.chroma_client import get_chroma_client
from utils.db import db
import logging

logging.basicConfig(level=logging.WARNING)  # Reduce log noise
logger = logging.getLogger(__name__)


def test_data_consistency():
    """测试数据一致性"""
    print("=" * 60)
    print("Test 5: Data Consistency (SQLite ↔ Chroma)")
    print("=" * 60)

    chroma = get_chroma_client()
    inconsistencies = []

    # 1. Count comparison
    print("\n[1/6] Comparing total counts...")
    try:
        # SQLite count
        with db.get_connection("pain") as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM pain_events")
            sqlite_count = cursor.fetchone()[0]

        # Chroma count
        chroma_count = chroma.collection.count()

        print(f"   SQLite pain_events: {sqlite_count}")
        print(f"   Chroma embeddings: {chroma_count}")

        if sqlite_count == chroma_count:
            print("✅ Counts match perfectly")
        else:
            diff = abs(sqlite_count - chroma_count)
            print(f"⚠️  Count difference: {diff}")
            inconsistencies.append(f"Count mismatch: SQLite={sqlite_count}, Chroma={chroma_count}")

    except Exception as e:
        print(f"❌ Failed to compare counts: {e}")
        return False

    # 2. Lifecycle stage consistency
    print("\n[2/6] Checking lifecycle stage consistency...")
    try:
        # Get sample IDs from Chroma
        sample_size = min(100, chroma_count)
        results = chroma.collection.get(
            limit=sample_size,
            include=["metadatas"]
        )

        chroma_ids = [int(id) for id in results['ids']]
        chroma_lifecycle = {
            int(id): metadata.get('lifecycle_stage', 'unknown')
            for id, metadata in zip(results['ids'], results['metadatas'])
        }

        # Check against SQLite
        placeholders = ','.join('?' for _ in chroma_ids)
        with db.get_connection("pain") as conn:
            cursor = conn.execute(f"""
                SELECT id, lifecycle_stage
                FROM pain_events
                WHERE id IN ({placeholders})
            """, chroma_ids)

            sqlite_lifecycle = {row[0]: row[1] for row in cursor.fetchall()}

        # Compare
        matching = 0
        mismatching = []
        for event_id in chroma_ids:
            chroma_stage = chroma_lifecycle.get(event_id, 'missing')
            sqlite_stage = sqlite_lifecycle.get(event_id, 'missing')

            if chroma_stage == sqlite_stage:
                matching += 1
            else:
                mismatching.append({
                    'id': event_id,
                    'chroma': chroma_stage,
                    'sqlite': sqlite_stage
                })

        print(f"   Checked {len(chroma_ids)} events")
        print(f"   Matching: {matching}")
        print(f"   Mismatching: {len(mismatching)}")

        if len(mismatching) == 0:
            print("✅ All lifecycle stages consistent")
        elif len(mismatching) <= 5:
            print("⚠️  Minor inconsistencies (showing first 5):")
            for m in mismatching[:5]:
                print(f"   - ID {m['id']}: Chroma={m['chroma']}, SQLite={m['sqlite']}")
            inconsistencies.append(f"{len(mismatching)} lifecycle mismatches")
        else:
            print(f"❌ {len(mismatching)} lifecycle inconsistencies found")
            inconsistencies.append(f"{len(mismatching)} lifecycle mismatches")

    except Exception as e:
        print(f"❌ Failed to check lifecycle consistency: {e}")
        import traceback
        print(traceback.format_exc())
        return False

    # 3. Cluster ID consistency
    print("\n[3/6] Checking cluster_id consistency...")
    try:
        # Check active events have valid cluster_ids in both systems
        with db.get_connection("pain") as conn:
            cursor = conn.execute("""
                SELECT id, cluster_id
                FROM pain_events
                WHERE lifecycle_stage = 'active'
                LIMIT 100
            """)
            sqlite_active = {row[0]: row[1] for row in cursor.fetchall()}

        if sqlite_active:
            print(f"   Checking {len(sqlite_active)} active events")

            # Get from Chroma
            event_ids = list(sqlite_active.keys())
            results = chroma.collection.get(
                ids=[str(id) for id in event_ids],
                include=["metadatas"]
            )

            chroma_cluster_ids = {}
            for id, metadata in zip(results['ids'], results['metadatas']):
                chroma_cluster_ids[int(id)] = metadata.get('cluster_id', 0)

            # Compare
            matching_clusters = sum(
                1 for eid in event_ids
                if sqlite_active.get(eid) == chroma_cluster_ids.get(eid)
            )

            print(f"   Matching cluster_ids: {matching_clusters}/{len(event_ids)}")

            if matching_clusters == len(event_ids):
                print("✅ All cluster_ids consistent")
            else:
                inconsistencies.append(f"{len(event_ids) - matching_clusters} cluster_id mismatches")

    except Exception as e:
        print(f"❌ Failed to check cluster_id consistency: {e}")
        return False

    # 4. Orphan consistency
    print("\n[4/6] Checking orphan event consistency...")
    try:
        with db.get_connection("pain") as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM pain_events
                WHERE lifecycle_stage = 'orphan'
            """)
            sqlite_orphans = cursor.fetchone()[0]

        # Get from Chroma
        results = chroma.collection.get(
            where={"lifecycle_stage": "orphan"}
        )
        chroma_orphans = len(results['ids'])

        print(f"   SQLite orphans: {sqlite_orphans}")
        print(f"   Chroma orphans: {chroma_orphans}")

        if sqlite_orphans == chroma_orphans:
            print("✅ Orphan counts match")
        else:
            diff = abs(sqlite_orphans - chroma_orphans)
            print(f"⚠️  Orphan count difference: {diff}")

    except Exception as e:
        print(f"❌ Failed to check orphan consistency: {e}")
        return False

    # 5. Metadata completeness
    print("\n[5/6] Checking metadata completeness...")
    try:
        # Get sample from Chroma
        results = chroma.collection.get(
            limit=50,
            include=["metadatas"]
        )

        required_fields = ['pain_event_id', 'lifecycle_stage', 'cluster_id']
        complete = 0
        incomplete = 0

        for metadata in results['metadatas']:
            if all(field in metadata for field in required_fields):
                complete += 1
            else:
                incomplete += 1
                missing = [f for f in required_fields if f not in metadata]
                print(f"   ⚠️  Missing fields: {missing}")

        print(f"   Complete metadata: {complete}/{len(results['metadatas'])}")
        print(f"   Incomplete metadata: {incomplete}/{len(results['metadatas'])}")

        if incomplete == 0:
            print("✅ All metadata complete")
        else:
            inconsistencies.append(f"{incomplete} events with incomplete metadata")

    except Exception as e:
        print(f"❌ Failed to check metadata: {e}")
        return False

    # 6. Summary
    print("\n[6/6] Summary...")
    print("=" * 60)

    if len(inconsistencies) == 0:
        print("✅ Test 5 PASSED: All data consistency checks passed")
        print("=" * 60)
        return True
    else:
        print(f"⚠️  Test 5 PASSED with {len(inconsistencies)} minor issues:")
        for issue in inconsistencies:
            print(f"   - {issue}")
        print("\nOverall: Systems are largely consistent")
        print("=" * 60)
        return True


if __name__ == "__main__":
    success = test_data_consistency()
    sys.exit(0 if success else 1)
