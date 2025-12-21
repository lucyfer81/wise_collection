"""
Test alignment database operations
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
from utils.db import WiseCollectionDB

def test_alignment_status_update():
    """测试对齐状态更新"""
    db = WiseCollectionDB(':memory:', unified=True)
    db._init_unified_database()

    # 创建测试聚类
    with db.get_connection("raw") as conn:
        conn.execute("""
            INSERT INTO clusters (cluster_name, source_type, centroid_summary,
                                 common_pain, pain_event_ids, cluster_size)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'test_cluster',
            'reddit',
            'Test summary',
            'Test pain',
            json.dumps(['1', '2']),
            2
        ))
        conn.commit()

    # 测试对齐状态更新
    db.update_cluster_alignment_status('test_cluster', 'aligned', 'AP_01')

    # 验证更新
    with db.get_connection("raw") as conn:
        cursor = conn.execute(
            "SELECT alignment_status, aligned_problem_id FROM clusters WHERE cluster_name = ?",
            ('test_cluster',)
        )
        result = cursor.fetchone()

        assert result['alignment_status'] == 'aligned'
        assert result['aligned_problem_id'] == 'AP_01'

def test_insert_aligned_problem():
    """测试插入对齐问题"""
    db = WiseCollectionDB(':memory:', unified=True)
    db._init_unified_database()

    # 创建测试对齐问题
    aligned_problem_data = {
        'id': 'test_aligned_AP_01_1234567890',
        'aligned_problem_id': 'AP_01',
        'sources': ['reddit', 'hn_ask'],
        'core_problem': 'Test problem description',
        'why_they_look_different': 'Test explanation',
        'evidence': [
            {
                'source': 'reddit',
                'cluster_summary': 'Test summary',
                'evidence_quote': 'Test evidence'
            }
        ],
        'cluster_ids': ['test_cluster_1', 'test_cluster_2']
    }

    # 插入对齐问题
    db.insert_aligned_problem(aligned_problem_data)

    # 验证插入
    with db.get_connection("raw") as conn:
        cursor = conn.execute(
            "SELECT * FROM aligned_problems WHERE aligned_problem_id = ?",
            ('AP_01',)
        )
        result = cursor.fetchone()

        assert result is not None
        assert result['aligned_problem_id'] == 'AP_01'
        assert result['core_problem'] == 'Test problem description'

        # 验证JSON字段正确解析
        sources = json.loads(result['sources'])
        assert sources == ['reddit', 'hn_ask']

        evidence = json.loads(result['evidence'])
        assert len(evidence) == 1
        assert evidence[0]['source'] == 'reddit'

def test_get_aligned_problems():
    """测试获取对齐问题"""
    db = WiseCollectionDB(':memory:', unified=True)
    db._init_unified_database()

    # 插入测试数据（使用唯一的aligned_problem_id）
    aligned_problem_data = {
        'id': 'test_aligned_AP_05_1234567890',
        'aligned_problem_id': 'AP_05',
        'sources': ['hn_ask', 'hn_show'],
        'core_problem': 'Another test problem',
        'why_they_look_different': 'Another explanation',
        'evidence': [],
        'cluster_ids': ['test_cluster_3']
    }

    db.insert_aligned_problem(aligned_problem_data)

    # 获取对齐问题
    aligned_problems = db.get_aligned_problems()

    assert len(aligned_problems) == 1
    problem = aligned_problems[0]
    assert problem['aligned_problem_id'] == 'AP_05'
    assert problem['sources'] == ['hn_ask', 'hn_show']
    assert problem['core_problem'] == 'Another test problem'

def test_get_clusters_for_opportunity_mapping():
    """测试获取用于机会映射的聚类"""
    db = WiseCollectionDB(':memory:', unified=True)
    db._init_unified_database()

    # 创建测试聚类
    with db.get_connection("raw") as conn:
        conn.execute("""
            INSERT INTO clusters (cluster_name, source_type, centroid_summary,
                                 common_pain, pain_event_ids, cluster_size)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'test_cluster_for_opp',
            'reddit',
            'Test summary for opportunity',
            'Test pain for opportunity',
            json.dumps(['1', '2']),
            3
        ))
        conn.commit()

        # 插入对齐问题
        conn.execute("""
            INSERT INTO aligned_problems (id, aligned_problem_id, sources, core_problem,
                                         why_they_look_different, evidence, cluster_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            'test_aligned_AP_06_1234567890',
            'AP_06',
            json.dumps(['reddit', 'hn_ask']),
            'Aligned test problem',
            'Test alignment explanation',
            json.dumps([]),
            json.dumps(['test_cluster_for_opp'])
        ))
        conn.commit()

    # 获取用于机会映射的聚类
    clusters = db.get_clusters_for_opportunity_mapping()

    assert len(clusters) == 2  # 1个原始聚类 + 1个对齐问题

    # 验证原始聚类
    original_clusters = [c for c in clusters if c['source_type'] != 'aligned']
    assert len(original_clusters) == 1
    assert original_clusters[0]['cluster_name'] == 'test_cluster_for_opp'

    # 验证对齐问题作为聚类
    aligned_clusters = [c for c in clusters if c['source_type'] == 'aligned']
    assert len(aligned_clusters) == 1
    assert aligned_clusters[0]['cluster_name'] == 'AP_06'

if __name__ == "__main__":
    test_alignment_status_update()
    test_insert_aligned_problem()
    test_get_aligned_problems()
    test_get_clusters_for_opportunity_mapping()
    print("✅ All alignment database tests passed")