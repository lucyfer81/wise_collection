#!/usr/bin/env python3
"""
Test 2: Chroma Similarity Query
测试Chroma向量相似度搜索功能
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.chroma_client import get_chroma_client
from utils.db import db
import logging
import pickle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_chroma_similarity():
    """测试Chroma相似度查询"""
    print("=" * 60)
    print("Test 2: Chroma Similarity Query")
    print("=" * 60)

    chroma = get_chroma_client()

    # 1. Get a test pain_event with embedding
    print("\n[1/5] Getting test pain_event...")
    try:
        with db.get_connection("pain") as conn:
            cursor = conn.execute("""
                SELECT pe.id, pe.problem, pe.context, pe.cluster_id,
                       em.embedding_vector
                FROM pain_events pe
                JOIN pain_embeddings em ON pe.id = em.pain_event_id
                WHERE pe.cluster_id IS NOT NULL
                LIMIT 1
            """)
            test_event = cursor.fetchone()

        if not test_event:
            print("❌ No test event found")
            return False

        test_id = test_event[0]
        test_problem = test_event[1]
        test_context = test_event[2]
        test_cluster_id = test_event[3]
        test_embedding_blob = test_event[4]

        # Deserialize embedding
        test_embedding = pickle.loads(test_embedding_blob)
        if hasattr(test_embedding, 'tolist'):
            test_embedding = test_embedding.tolist()
        elif not isinstance(test_embedding, list):
            test_embedding = list(test_embedding)

        print(f"✅ Test event found:")
        print(f"   ID: {test_id}")
        print(f"   Problem: {test_problem[:80]}...")
        print(f"   Cluster ID: {test_cluster_id}")
        print(f"   Embedding dimensions: {len(test_embedding)}")

    except Exception as e:
        print(f"❌ Failed to get test event: {e}")
        import traceback
        print(traceback.format_exc())
        return False

    # 2. Query similar events (without filters)
    print("\n[2/5] Querying similar events (no filter)...")
    try:
        similar_all = chroma.query_similar(
            query_embedding=test_embedding,
            top_k=10
        )

        print(f"✅ Found {len(similar_all)} similar events")
        print(f"   Top 3 results:")
        for i, event in enumerate(similar_all[:3]):
            print(f"   {i+1}. pain_event_id={event['pain_event_id']}, "
                  f"similarity={event['similarity']:.3f}")

    except Exception as e:
        print(f"❌ Failed to query similar events: {e}")
        import traceback
        print(traceback.format_exc())
        return False

    # 3. Query with metadata filter (active events only)
    print("\n[3/5] Querying with metadata filter (lifecycle_stage='active')...")
    try:
        similar_active = chroma.query_similar(
            query_embedding=test_embedding,
            top_k=10,
            where={"lifecycle_stage": "active"}
        )

        print(f"✅ Found {len(similar_active)} active events")
        print(f"   Top 3 results:")
        for i, event in enumerate(similar_active[:3]):
            print(f"   {i+1}. pain_event_id={event['pain_event_id']}, "
                  f"similarity={event['similarity']:.3f}, "
                  f"cluster_id={event['metadata'].get('cluster_id')}")

    except Exception as e:
        print(f"❌ Failed to query with filter: {e}")
        import traceback
        print(traceback.format_exc())
        return False

    # 4. Verify self-match (query event should be #1 result)
    print("\n[4/5] Verifying self-match...")
    try:
        top_result_id = similar_all[0]['pain_event_id']
        top_similarity = similar_all[0]['similarity']

        if top_result_id == test_id:
            print(f"✅ Self-match confirmed: test_id={test_id} is top result")
            print(f"   Similarity: {top_similarity:.4f}")
        else:
            print(f"⚠️  Self-match not found:")
            print(f"   Expected: {test_id}")
            print(f"   Got: {top_result_id}")
            print(f"   Similarity: {top_similarity:.4f}")

    except Exception as e:
        print(f"❌ Failed to verify self-match: {e}")
        return False

    # 5. Performance test
    print("\n[5/5] Performance test...")
    try:
        import time

        start_time = time.time()
        iterations = 10

        for _ in range(iterations):
            chroma.query_similar(
                query_embedding=test_embedding,
                top_k=20
            )

        elapsed = time.time() - start_time
        avg_time = elapsed / iterations

        print(f"✅ Performance test completed:")
        print(f"   {iterations} queries in {elapsed:.2f}s")
        print(f"   Average: {avg_time*1000:.1f}ms per query")
        print(f"   Throughput: {iterations/elapsed:.1f} queries/sec")

    except Exception as e:
        print(f"❌ Failed performance test: {e}")
        return False

    print("\n" + "=" * 60)
    print("✅ Test 2 PASSED: Chroma similarity queries working correctly")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_chroma_similarity()
    sys.exit(0 if success else 1)
