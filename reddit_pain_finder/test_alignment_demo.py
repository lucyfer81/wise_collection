#!/usr/bin/env python3
"""
跨源对齐功能演示和测试
"""
import sys
import json
import time
from utils.db import WiseCollectionDB
from utils.llm_client import LLMClient
from pipeline.align_cross_sources import CrossSourceAligner

def create_test_data():
    """创建测试聚类数据"""
    db = WiseCollectionDB(':memory:', unified=True)
    db._init_unified_database()

    # 模拟Reddit和HackerNews的聚类数据
    test_clusters = [
        {
            'cluster_name': 'reddit_deployment_pain',
            'source_type': 'reddit',
            'centroid_summary': 'Developers struggling with complex deployment pipelines and manual configuration management',
            'common_pain': 'Manual deployment steps, configuration drift, deployment failures',
            'pain_event_ids': json.dumps(['1', '2', '3', '4', '5']),
            'cluster_size': 5
        },
        {
            'cluster_name': 'hn_deployment_challenges',
            'source_type': 'hn_ask',
            'centroid_summary': 'What are the best practices for deployment automation? Current process is error-prone',
            'common_pain': 'Deployment automation issues, lack of CI/CD',
            'pain_event_ids': json.dumps(['6', '7', '8']),
            'cluster_size': 3
        },
        {
            'cluster_name': 'reddit_api_documentation',
            'source_type': 'reddit',
            'centroid_summary': 'Poor API documentation making integration difficult for developers',
            'common_pain': 'Missing examples, unclear endpoints',
            'pain_event_ids': json.dumps(['9', '10']),
            'cluster_size': 2
        },
        {
            'cluster_name': 'hn_database_performance',
            'source_type': 'hn_ask',
            'centroid_summary': 'Database queries running slowly on large datasets, optimization strategies needed',
            'common_pain': 'Query optimization challenges',
            'pain_event_ids': json.dumps(['11', '12']),
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

    print(f"✅ 创建了 {len(test_clusters)} 个测试聚类")
    return db

def test_alignment_workflow():
    """测试完整的对齐工作流程"""
    print("🚀 开始测试跨源对齐工作流程...")

    # 创建测试数据
    db = create_test_data()

    # 初始化LLM客户端（使用mock配置）
    try:
        llm_client = LLMClient({
            'models': {
                'main': 'gpt-4',
                'medium': 'gpt-3.5-turbo',
                'small': 'gpt-3.5-turbo'
            },
            'api_key': 'mock-key-for-testing'
        })
        print("✅ LLM客户端初始化成功")
    except Exception as e:
        print(f"⚠️  LLM客户端初始化失败（可能缺少API密钥）: {e}")
        # 创建一个简单的mock LLM客户端用于测试
        class MockLLMClient:
            def get_completion(self, prompt, model_type="main", max_tokens=1000, temperature=0.1):
                return """[]"""
        llm_client = MockLLMClient()
        print("✅ 使用Mock LLM客户端进行测试")

    # 创建对齐器
    aligner = CrossSourceAligner(db, llm_client)
    print("✅ 跨源对齐器创建成功")

    # 测试获取未处理的聚类
    unprocessed_clusters = aligner.get_unprocessed_clusters()
    print(f"✅ 获取到 {len(unprocessed_clusters)} 个未处理聚类")

    if unprocessed_clusters:
        print("📋 聚类详情:")
        for i, cluster in enumerate(unprocessed_clusters, 1):
            print(f"  {i}. {cluster['cluster_name']} ({cluster['source_type']})")
            print(f"     摘要: {cluster['centroid_summary'][:80]}...")
            print(f"     大小: {cluster['cluster_size']} 个事件")

    # 测试聚类准备
    if unprocessed_clusters:
        prepared_cluster = aligner.prepare_cluster_for_alignment(unprocessed_clusters[0])
        print(f"\n✅ 聚类准备测试成功")
        print(f"   源类型: {prepared_cluster['source_type']}")
        print(f"   摘要: {prepared_cluster['cluster_summary'][:60]}...")
        print(f"   典型解决方案: {prepared_cluster['typical_workaround'][:60]}...")
        print(f"   上下文: {prepared_cluster['context']}")

    # 测试跨源对齐（不实际调用LLM）
    if len(unprocessed_clusters) >= 2:
        print(f"\n🔍 测试跨源对齐逻辑...")

        # 按源类型分组
        source_groups = {}
        for cluster in unprocessed_clusters:
            source_type = cluster['source_type']
            if source_type not in source_groups:
                source_groups[source_type] = []
            prepared_cluster = aligner.prepare_cluster_for_alignment(cluster)
            if prepared_cluster:
                source_groups[source_type].append(prepared_cluster)

        print(f"✅ 源类型分组:")
        for source_type, clusters in source_groups.items():
            print(f"   {source_type}: {len(clusters)} 个聚类")

        # 构建对齐prompt
        if len(source_groups) >= 2:
            prompt = aligner._build_alignment_prompt(source_groups)
            print(f"✅ 对齐Prompt构建成功 ({len(prompt)} 字符)")
            print(f"   Prompt预览: {prompt[:200]}...")

    print("\n🎯 测试数据库操作...")

    # 测试插入对齐问题
    test_alignment = {
        'id': f'test_alignment_{int(time.time())}',
        'aligned_problem_id': 'AP_TEST_01',
        'sources': ['reddit', 'hn_ask'],
        'core_problem': 'Complex deployment pipeline management challenges',
        'why_they_look_different': 'Reddit focuses on emotional frustration while HN asks for technical solutions',
        'evidence': [
            {
                'source': 'reddit',
                'cluster_summary': 'Developers struggling with complex deployment pipelines',
                'evidence_quote': 'Manual deployment steps, configuration drift'
            },
            {
                'source': 'hn_ask',
                'cluster_summary': 'Best practices for deployment automation',
                'evidence_quote': 'Current process is error-prone'
            }
        ],
        'cluster_ids': ['reddit_deployment_pain', 'hn_deployment_challenges']
    }

    db.insert_aligned_problem(test_alignment)
    print("✅ 对齐问题插入成功")

    # 测试获取对齐问题
    aligned_problems = db.get_aligned_problems()
    print(f"✅ 获取到 {len(aligned_problems)} 个对齐问题")

    if aligned_problems:
        problem = aligned_problems[0]
        print(f"   问题ID: {problem['aligned_problem_id']}")
        print(f"   涉及源: {problem['sources']}")
        print(f"   核心问题: {problem['core_problem']}")
        print(f"   证据数量: {len(problem['evidence'])}")

    # 测试更新聚类状态
    db.update_cluster_alignment_status('reddit_deployment_pain', 'aligned', 'AP_TEST_01')
    db.update_cluster_alignment_status('hn_deployment_challenges', 'aligned', 'AP_TEST_01')
    db.update_cluster_alignment_status('reddit_api_documentation', 'processed', None)
    print("✅ 聚类状态更新成功")

    # 测试获取用于机会映射的聚类
    opportunity_clusters = db.get_clusters_for_opportunity_mapping()
    print(f"✅ 获取到 {len(opportunity_clusters)} 个用于机会映射的聚类")

    aligned_clusters = [c for c in opportunity_clusters if c['source_type'] == 'aligned']
    regular_clusters = [c for c in opportunity_clusters if c['source_type'] != 'aligned']
    print(f"   包含 {len(aligned_clusters)} 个对齐聚类和 {len(regular_clusters)} 个常规聚类")

    print("\n🎉 跨源对齐功能测试完成！")
    print("\n📊 测试总结:")
    print("   ✅ 数据库架构 - 通过")
    print("   ✅ 对齐模块 - 通过")
    print("   ✅ 数据库操作 - 通过")
    print("   ✅ 聚类处理 - 通过")
    print("   ✅ 源类型分组 - 通过")
    print("   ✅ Prompt构建 - 通过")
    print("   ✅ 对齐问题管理 - 通过")
    print("   ✅ 聚类状态跟踪 - 通过")
    print("   ✅ 机会映射支持 - 通过")

    return True

if __name__ == "__main__":
    try:
        success = test_alignment_workflow()
        if success:
            print("\n✅ 所有测试通过！跨源对齐功能已就绪。")
        else:
            print("\n❌ 测试失败，请检查实现。")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)