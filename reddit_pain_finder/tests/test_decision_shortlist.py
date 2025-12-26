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


def test_check_cross_source_validation():
    """测试跨源验证逻辑"""
    generator = DecisionShortlistGenerator()

    # Test Level 1: source_type='aligned'
    mock_opp = {
        'cluster_id': 1,
        'cluster_name': 'test_cluster',
        'cluster_size': 15,
        'source_type': 'aligned',
        'pain_event_ids': [1, 2, 3, 4, 5]
    }

    result = generator._check_cross_source_validation(mock_opp)

    assert result['has_cross_source'] == True
    assert result['validation_level'] == 1
    assert result['boost_score'] == 2.0
    assert result['validated_problem'] == True
    assert result['evidence'] == "source_type='aligned'"


def test_cross_source_validation_no_pain_events():
    """测试没有 pain events 的情况"""
    generator = DecisionShortlistGenerator()

    mock_opp = {
        'cluster_id': 1,
        'cluster_name': 'test_cluster',
        'cluster_size': 15,
        'source_type': 'reddit',
        'pain_event_ids': []  # Empty list
    }

    result = generator._check_cross_source_validation(mock_opp)

    assert result['has_cross_source'] == False
    assert result['validation_level'] == 0
    assert result['boost_score'] == 0.0
    assert result['validated_problem'] == False
    assert result['evidence'] == "No pain events"


def test_cross_source_validation_level3():
    """测试 Level 3 验证（中等聚类，2个subreddit）"""
    generator = DecisionShortlistGenerator()

    # Create test data with multiple subreddits
    try:
        with db.get_connection("pain") as conn:
            # Create test posts from different subreddits
            conn.execute("""
                INSERT INTO filtered_posts (title, body, subreddit, url, score, num_comments, upvote_ratio, pain_score)
                VALUES
                    ('Test 1', 'Body 1', 'test_subreddit_1', 'http://test1.com', 10, 5, 0.8, 0.7),
                    ('Test 2', 'Body 2', 'test_subreddit_2', 'http://test2.com', 10, 5, 0.8, 0.7),
                    ('Test 3', 'Body 3', 'test_subreddit_1', 'http://test3.com', 10, 5, 0.8, 0.7),
                    ('Test 4', 'Body 4', 'test_subreddit_2', 'http://test4.com', 10, 5, 0.8, 0.7)
            """)
            conn.commit()

            # Get post IDs
            posts = conn.execute("SELECT id FROM filtered_posts ORDER BY id DESC LIMIT 4").fetchall()
            post_ids = [p['id'] for p in posts]

            # Create pain events
            for post_id in post_ids:
                conn.execute("""
                    INSERT INTO pain_events (post_id, problem, context)
                    VALUES (?, 'Test pain problem', 'Test context')
                """, (post_id,))
            conn.commit()

            # Get pain event IDs
            pain_events = conn.execute("SELECT id FROM pain_events ORDER BY id DESC LIMIT 4").fetchall()
            pain_event_ids = [pe['id'] for pe in pain_events]

            mock_opp = {
                'cluster_id': 1,
                'cluster_name': 'test_cluster',
                'cluster_size': 8,  # Meets Level 3 threshold
                'source_type': 'reddit',
                'pain_event_ids': pain_event_ids
            }

            result = generator._check_cross_source_validation(mock_opp)

            assert result['has_cross_source'] == True
            assert result['validation_level'] == 3
            assert result['boost_score'] == 0.5
            assert result['validated_problem'] == False  # Level 3 doesn't validate
            assert "Medium cluster" in result['evidence']
            assert "subreddits" in result['evidence']

            # Cleanup
            placeholders = ','.join('?' for _ in pain_event_ids)
            conn.execute(f"DELETE FROM pain_events WHERE id IN ({placeholders})", pain_event_ids)
            placeholders = ','.join('?' for _ in post_ids)
            conn.execute(f"DELETE FROM filtered_posts WHERE id IN ({placeholders})", post_ids)
            conn.commit()

    except Exception as e:
        pytest.fail(f"Test failed with exception: {e}")


def test_cross_source_validation_no_validation():
    """测试没有跨源验证的情况（小聚类）"""
    generator = DecisionShortlistGenerator()

    mock_opp = {
        'cluster_id': 1,
        'cluster_name': 'test_cluster',
        'cluster_size': 5,  # Below Level 3 threshold
        'source_type': 'reddit',
        'pain_event_ids': [1, 2]
    }

    result = generator._check_cross_source_validation(mock_opp)

    assert result['has_cross_source'] == False
    assert result['validation_level'] == 0
    assert result['boost_score'] == 0.0
    assert result['validated_problem'] == False
    assert result['evidence'] == "No cross-source validation"
