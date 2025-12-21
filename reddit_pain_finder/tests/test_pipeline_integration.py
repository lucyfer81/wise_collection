"""
Test pipeline integration with cross-source alignment
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
from utils.db import WiseCollectionDB
from utils.llm_client import LLMClient
from pipeline.align_cross_sources import CrossSourceAligner

def test_pipeline_integration():
    """测试完整管道集成"""
    print("🧪 Testing pipeline integration with cross-source alignment...")

    # 初始化测试数据库
    db = WiseCollectionDB(':memory:', unified=True)
    db._init_unified_database()

    # 创建测试聚类数据
    test_clusters = [
        {
            'cluster_name': 'reddit_deployment_pain',
            'source_type': 'reddit',
            'centroid_summary': 'Developers struggling with complex deployment pipelines and manual processes',
            'common_pain': 'Manual deployment steps, configuration drift',
            'pain_event_ids': json.dumps(['1', '2', '3']),
            'cluster_size': 4
        },
        {
            'cluster_name': 'hn_deployment_challenges',
            'source_type': 'hn_ask',
            'centroid_summary': 'How do you handle deployments? Current process is painful and error-prone',
            'common_pain': 'Deployment automation issues',
            'pain_event_ids': json.dumps(['4', '5']),
            'cluster_size': 3
        },
        {
            'cluster_name': 'reddit_api_docs',
            'source_type': 'reddit',
            'centroid_summary': 'Poor API documentation making integration difficult',
            'common_pain': 'Missing examples, unclear endpoints',
            'pain_event_ids': json.dumps(['6']),
            'cluster_size': 2
        }
    ]

    # 插入测试聚类
    with db.get_connection("raw") as conn:
        for cluster in test_clusters:
            conn.execute("""
                INSERT INTO clusters (cluster_name, source_type, centroid_summary,
                                    common_pain, pain_event_ids, cluster_size)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                cluster['cluster_name'],
                cluster['source_type'],
                cluster['centroid_summary'],
                cluster['common_pain'],
                cluster['pain_event_ids'],
                cluster['cluster_size']
            ))
        conn.commit()

    print(f"✅ Created {len(test_clusters)} test clusters")

    # 测试对齐功能
    try:
        # Mock LLM client for testing
        class MockLLMClient:
            def get_completion(self, prompt, model_type="main", max_tokens=1000, temperature=0.1):
                # 模拟发现一个对齐
                return """[
                  {
                    "aligned_problem_id": "AP_01",
                    "sources": ["reddit", "hn_ask"],
                    "core_problem": "Complex deployment pipeline management challenges",
                    "why_they_look_different": "Reddit focuses on emotional frustration while HN asks for technical solutions",
                    "evidence": [
                      {
                        "source": "reddit",
                        "cluster_summary": "Developers struggling with complex deployment pipelines",
                        "evidence_quote": "Manual deployment steps, configuration drift"
                      },
                      {
                        "source": "hn_ask",
                        "cluster_summary": "Deployment challenges and automation issues",
                        "evidence_quote": "Current process is painful and error-prone"
                      }
                    ],
                    "original_cluster_ids": ["reddit_deployment_pain", "hn_deployment_challenges"]
                  }
                ]"""

        llm_client = MockLLMClient()
        aligner = CrossSourceAligner(db, llm_client)

        # 执行对齐
        aligner.process_alignments()
        print("✅ Alignment processing completed")

        # 验证对齐结果
        aligned_problems = db.get_aligned_problems()
        assert len(aligned_problems) > 0, "Should find at least one aligned problem"

        aligned_problem = aligned_problems[0]
        assert aligned_problem['aligned_problem_id'] == 'AP_01'
        assert set(aligned_problem['sources']) == {'reddit', 'hn_ask'}
        assert 'deployment' in aligned_problem['core_problem'].lower()

        print(f"✅ Found {len(aligned_problems)} aligned problems")
        print(f"   Primary alignment: {aligned_problem['aligned_problem_id']}")
        print(f"   Sources: {', '.join(aligned_problem['sources'])}")
        print(f"   Core problem: {aligned_problem['core_problem']}")

        # 测试聚类状态更新
        with db.get_connection("raw") as conn:
            cursor = conn.execute("""
                SELECT cluster_name, alignment_status, aligned_problem_id
                FROM clusters
                WHERE cluster_name IN (?, ?)
            """, ('reddit_deployment_pain', 'hn_deployment_challenges'))

            updated_clusters = cursor.fetchall()
            assert len(updated_clusters) == 2

            for cluster in updated_clusters:
                if cluster['alignment_status'] != 'aligned':
                    raise AssertionError(f"Cluster {cluster['cluster_name']} not marked as aligned")

            print("✅ Cluster alignment status updated correctly")

        # 测试机会映射集成
        opportunity_clusters = db.get_clusters_for_opportunity_mapping()
        assert len(opportunity_clusters) >= 3, "Should include original and aligned clusters"

        aligned_clusters = [c for c in opportunity_clusters if c['source_type'] == 'aligned']
        assert len(aligned_clusters) == 1, "Should have one aligned cluster for opportunity mapping"

        print(f"✅ Opportunity mapping ready with {len(opportunity_clusters)} total clusters")
        print(f"   Including {len(aligned_clusters)} aligned clusters")

        return True

    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_compatibility():
    """测试数据库兼容性"""
    print("\n🔍 Testing database compatibility...")

    db = WiseCollectionDB(':memory:', unified=True)
    db._init_unified_database()

    # 测试所有必需的方法存在
    required_methods = [
        'get_aligned_problems',
        'update_cluster_alignment_status',
        'insert_aligned_problem',
        'get_clusters_for_opportunity_mapping'
    ]

    for method in required_methods:
        if not hasattr(db, method):
            raise AssertionError(f"Missing method: {method}")

    print("✅ All required database methods available")

    # 测试基本操作
    try:
        # 插入测试对齐问题
        test_alignment = {
            'id': 'test_alignment_123',
            'aligned_problem_id': 'AP_TEST',
            'sources': ['reddit', 'hn_ask'],
            'core_problem': 'Test problem',
            'why_they_look_different': 'Test explanation',
            'evidence': [],
            'cluster_ids': ['test_cluster_1']
        }

        db.insert_aligned_problem(test_alignment)
        aligned_problems = db.get_aligned_problems()
        assert len(aligned_problems) == 1
        assert aligned_problems[0]['aligned_problem_id'] == 'AP_TEST'

        print("✅ Database operations working correctly")
        return True

    except Exception as e:
        print(f"❌ Database compatibility test failed: {e}")
        return False

def test_mock_alignment_workflow():
    """测试模拟对齐工作流程"""
    print("\n🔄 Testing mock alignment workflow...")

    # 模拟真实的管道数据
    mock_pipeline_data = {
        'clusters': [
            {
                'cluster_name': 'notification_reddit',
                'source_type': 'reddit',
                'centroid_summary': 'Critical alerts missed due to notification overload',
                'common_pain': 'Too many notifications, missing critical alerts',
                'pain_event_ids': json.dumps(['1', '2']),
                'cluster_size': 4
            },
            {
                'cluster_name': 'notification_hn',
                'source_type': 'hn_ask',
                'centroid_summary': 'Managing critical alerts in noisy notification systems',
                'common_pain': 'Cannot distinguish critical alerts from noise',
                'pain_event_ids': json.dumps(['3', '4']),
                'cluster_size': 3
            }
        ]
    }

    # 验证数据结构符合预期
    required_fields = ['cluster_name', 'source_type', 'centroid_summary', 'common_pain', 'pain_event_ids', 'cluster_size']
    for cluster in mock_pipeline_data['clusters']:
        for field in required_fields:
            if field not in cluster:
                raise AssertionError(f"Missing field {field} in cluster data")

    # 验证多源数据存在
    source_types = set(cluster['source_type'] for cluster in mock_pipeline_data['clusters'])
    assert len(source_types) > 1, "Should have multiple source types for alignment"

    print(f"✅ Mock workflow validation passed")
    print(f"   Found {len(mock_pipeline_data['clusters'])} clusters from {len(source_types)} sources")
    print(f"   Source types: {', '.join(source_types)}")

    return True

if __name__ == "__main__":
    print("🚀 Running pipeline integration tests...")
    print("=" * 60)

    tests = [
        test_database_compatibility,
        test_mock_alignment_workflow,
        test_pipeline_integration
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"❌ {test.__name__} failed")
        except Exception as e:
            print(f"❌ {test.__name__} crashed: {e}")

    print("\n" + "=" * 60)
    print(f"Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All pipeline integration tests passed!")
        print("✅ Cross-source alignment is ready for production")
    else:
        print("❌ Some tests failed - check implementation")
        sys.exit(1)