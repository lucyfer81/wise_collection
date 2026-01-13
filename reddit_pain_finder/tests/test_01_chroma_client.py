#!/usr/bin/env python3
"""
Test 1: Chroma Client Initialization and Statistics
验证Chroma客户端初始化和数据统计
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.chroma_client import get_chroma_client
from utils.db import db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_chroma_client():
    """测试Chroma客户端"""
    print("=" * 60)
    print("Test 1: Chroma Client Initialization")
    print("=" * 60)

    # 1. Initialize Chroma client
    print("\n[1/4] Initializing Chroma client...")
    try:
        chroma = get_chroma_client()
        print("✅ Chroma client initialized successfully")
        print(f"   Persist directory: {chroma.persist_directory}")
    except Exception as e:
        print(f"❌ Failed to initialize Chroma: {e}")
        return False

    # 2. Get collection statistics
    print("\n[2/4] Getting collection statistics...")
    try:
        stats = chroma.get_statistics()
        print(f"✅ Collection stats:")
        print(f"   Total embeddings: {stats['total_embeddings']}")
        print(f"   Collection name: {stats['collection_name']}")
        print(f"   Persist directory: {stats['persist_directory']}")
    except Exception as e:
        print(f"❌ Failed to get statistics: {e}")
        return False

    # 3. Compare with SQLite pain_events count
    print("\n[3/4] Comparing with SQLite pain_events...")
    try:
        with db.get_connection("pain") as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM pain_events")
            sqlite_count = cursor.fetchone()[0]

        chroma_count = stats['total_embeddings']

        print(f"   SQLite pain_events: {sqlite_count}")
        print(f"   Chroma embeddings: {chroma_count}")

        if abs(sqlite_count - chroma_count) <= 100:  # Allow small variance
            print("✅ Counts match (within acceptable variance)")
        else:
            print(f"⚠️  Count mismatch: {abs(sqlite_count - chroma_count)} difference")

    except Exception as e:
        print(f"❌ Failed to compare with SQLite: {e}")
        return False

    # 4. Sample retrieval test
    print("\n[4/4] Testing sample retrieval...")
    try:
        # Get first few IDs
        with db.get_connection("pain") as conn:
            cursor = conn.execute("""
                SELECT id FROM pain_events
                WHERE cluster_id IS NOT NULL
                LIMIT 3
            """)
            test_ids = [row[0] for row in cursor.fetchall()]

        if not test_ids:
            print("⚠️  No pain_events found to test")
            return True

        # Try to get from Chroma
        results = chroma.get_by_ids(test_ids)

        print(f"✅ Retrieved {len(results)} pain_events from Chroma")
        for result in results[:2]:
            print(f"   - pain_event_id: {result['pain_event_id']}")
            print(f"     lifecycle_stage: {result['metadata'].get('lifecycle_stage')}")
            print(f"     cluster_id: {result['metadata'].get('cluster_id')}")

    except Exception as e:
        print(f"❌ Failed to retrieve samples: {e}")
        import traceback
        print(traceback.format_exc())
        return False

    print("\n" + "=" * 60)
    print("✅ Test 1 PASSED: Chroma client is working correctly")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_chroma_client()
    sys.exit(0 if success else 1)
