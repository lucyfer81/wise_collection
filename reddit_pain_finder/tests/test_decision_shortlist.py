# tests/test_decision_shortlist.py
"""Tests for Decision Shortlist Generator"""
import pytest
import json
from pipeline.decision_shortlist import DecisionShortlistGenerator
from utils.db import db


def test_apply_hard_filters():
    """测试硬性过滤逻辑"""
    generator = DecisionShortlistGenerator()

    result = generator._apply_hard_filters()

    # 验证返回值是列表
    assert isinstance(result, list)

    # 验证每个机会都满足过滤条件
    for opp in result:
        assert opp['viability_score'] >= 7.0, f"viability {opp['viability_score']} < 7.0"
        assert opp['cluster_size'] >= 6, f"cluster_size {opp['cluster_size']} < 6"
        assert opp['trust_level'] >= 0.7, f"trust_level {opp['trust_level']} < 0.7"


def test_apply_hard_filters_with_test_data():
    """测试硬性过滤逻辑（使用测试数据）"""
    generator = DecisionShortlistGenerator()

    # 创建测试数据
    try:
        with db.get_connection("clusters") as conn:
            # 创建测试聚类
            conn.execute("""
                INSERT INTO clusters (cluster_name, cluster_description, source_type,
                                    centroid_summary, pain_event_ids, cluster_size)
                VALUES
                    ('high_quality_cluster', 'High quality cluster', 'reddit',
                     'Summary', '[1,2,3]', 10),
                    ('low_quality_cluster', 'Low quality cluster', 'reddit',
                     'Summary', '[4,5]', 3),
                    ('medium_quality_cluster', 'Medium quality cluster', 'reddit',
                     'Summary', '[6,7,8,9,10]', 5),
                    ('ignored_cluster', 'Should be ignored', 'reddit',
                     'Summary', '[11,12]', 8)
            """)
            conn.commit()

            # 获取聚类ID
            clusters = conn.execute("SELECT id, cluster_name FROM clusters").fetchall()
            cluster_map = {name: id for id, name in clusters}

            # 创建测试机会
            conn.execute("""
                INSERT INTO opportunities (cluster_id, opportunity_name, description,
                                         total_score, trust_level, target_users,
                                         missing_capability, why_existing_fail)
                VALUES
                    (?, 'High Viability Opportunity', 'Great opportunity',
                     8.5, 0.8, 'Users', 'Capability', 'Reason'),
                    (?, 'Low Viability Opportunity', 'Not viable',
                     5.0, 0.8, 'Users', 'Capability', 'Reason'),
                    (?, 'Low Trust Opportunity', 'Low trust',
                     8.0, 0.5, 'Users', 'Capability', 'Reason'),
                    (?, 'Ignored Cluster Opportunity', 'Should be ignored',
                     9.0, 0.9, 'Users', 'Capability', 'Reason')
            """, (
                cluster_map['high_quality_cluster'],
                cluster_map['low_quality_cluster'],
                cluster_map['medium_quality_cluster'],
                cluster_map['ignored_cluster']
            ))
            conn.commit()

            # 设置忽略的聚类
            generator.config['ignored_clusters'] = ['ignored_cluster']

            # 运行过滤
            result = generator._apply_hard_filters()

            # 验证结果
            assert len(result) == 1, f"Expected 1 opportunity, got {len(result)}"
            assert result[0]['opportunity_name'] == 'High Viability Opportunity'
            assert result[0]['viability_score'] == 8.5
            assert result[0]['cluster_size'] == 10
            assert result[0]['trust_level'] == 0.8

            # 清理测试数据
            conn.execute("DELETE FROM opportunities")
            conn.execute("DELETE FROM clusters")
            conn.commit()

    except Exception as e:
        pytest.fail(f"Test failed with exception: {e}")


def test_apply_hard_filters_error_handling():
    """测试硬性过滤的错误处理"""
    generator = DecisionShortlistGenerator()

    # 使用无效的数据库路径来测试错误处理
    original_config = generator.config
    generator.config['min_viability_score'] = 'invalid'  # 无效值

    # 应该返回空列表而不是抛出异常
    result = generator._apply_hard_filters()
    assert isinstance(result, list)
    assert len(result) == 0

    # 恢复配置
    generator.config = original_config
