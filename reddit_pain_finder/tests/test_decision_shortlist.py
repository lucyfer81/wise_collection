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


def test_calculate_final_score():
    """测试最终评分计算"""
    generator = DecisionShortlistGenerator()

    # Test case from specification: viability_score=8.0, cluster_size=50, trust_level=0.8, boost=2.0
    opportunity = {
        'viability_score': 8.0,
        'cluster_size': 50,
        'trust_level': 0.8
    }

    cross_source_info = {
        'has_cross_source': True,
        'boost_score': 2.0
    }

    result = generator._calculate_final_score(opportunity, cross_source_info)

    # Expected calculation:
    # log10(50) ≈ 1.7
    # base = 8.0 * 1.0 + 1.7 * 2.5 + 0.8 * 1.5 = 8.0 + 4.25 + 1.2 = 13.45
    # bonus = 5.0 * 2.0 * 0.1 = 1.0
    # total = 13.45 + 1.0 = 14.45 → capped at 10.0
    assert result == 10.0, f"Expected 10.0 (capped), got {result}"


def test_calculate_final_score_no_cross_source():
    """测试没有跨源验证的评分计算"""
    generator = DecisionShortlistGenerator()

    opportunity = {
        'viability_score': 7.0,
        'cluster_size': 10,
        'trust_level': 0.7
    }

    cross_source_info = {
        'has_cross_source': False,
        'boost_score': 0.0
    }

    result = generator._calculate_final_score(opportunity, cross_source_info)

    # Expected calculation:
    # log10(10) = 1.0
    # base = 7.0 * 1.0 + 1.0 * 2.5 + 0.7 * 1.5 = 7.0 + 2.5 + 1.05 = 10.55 → capped at 10.0
    assert result == 10.0, f"Expected 10.0 (capped), got {result}"


def test_calculate_final_score_minimum():
    """测试最低评分"""
    generator = DecisionShortlistGenerator()

    opportunity = {
        'viability_score': 0.0,
        'cluster_size': 1,
        'trust_level': 0.0
    }

    cross_source_info = {
        'has_cross_source': False,
        'boost_score': 0.0
    }

    result = generator._calculate_final_score(opportunity, cross_source_info)

    # log10(1) = 0
    # base = 0.0 * 1.0 + 0.0 * 2.5 + 0.0 * 1.5 = 0.0
    assert result == 0.0, f"Expected 0.0, got {result}"


def test_get_cross_source_badge_level1():
    """测试 Level 1 徽章生成"""
    generator = DecisionShortlistGenerator()

    cross_source = {
        'has_cross_source': True,
        'validation_level': 1,
        'boost_score': 2.0
    }

    badge = generator._get_cross_source_badge(cross_source)

    assert 'INDEPENDENT VALIDATION ACROSS REDDIT + HACKER NEWS' in badge
    assert '🎯' in badge
    assert 'multiple communities' in badge


def test_get_cross_source_badge_level2():
    """测试 Level 2 徽章生成"""
    generator = DecisionShortlistGenerator()

    cross_source = {
        'has_cross_source': True,
        'validation_level': 2,
        'boost_score': 1.0
    }

    badge = generator._get_cross_source_badge(cross_source)

    assert 'Multi-Subreddit Validation' in badge
    assert '✓' in badge
    assert '3+ subreddits' in badge
    assert 'strong cluster size' in badge


def test_get_cross_source_badge_level3():
    """测试 Level 3 徽章生成"""
    generator = DecisionShortlistGenerator()

    cross_source = {
        'has_cross_source': True,
        'validation_level': 3,
        'boost_score': 0.5
    }

    badge = generator._get_cross_source_badge(cross_source)

    assert 'Weak Cross-Source Signal' in badge
    assert '◐' in badge
    assert 'Initial cross-community detection' in badge


def test_get_cross_source_badge_no_validation():
    """测试没有跨源验证时徽章为空"""
    generator = DecisionShortlistGenerator()

    cross_source = {
        'has_cross_source': False,
        'validation_level': 0,
        'boost_score': 0.0
    }

    badge = generator._get_cross_source_badge(cross_source)

    assert badge == ""


def test_markdown_report_includes_badges(tmp_path):
    """测试 Markdown 报告包含徽章"""
    import os
    import tempfile

    generator = DecisionShortlistGenerator()

    # Create a mock shortlist with cross-source validation
    shortlist = [
        {
            'opportunity_name': 'Test Opportunity',
            'final_score': 9.0,
            'viability_score': 8.5,
            'cluster_size': 50,
            'trust_level': 0.85,
            'target_users': 'Test users',
            'missing_capability': 'Test capability',
            'why_existing_fail': 'Test reason',
            'readable_content': {
                'problem': 'Test problem',
                'mvp': 'Test MVP',
                'why_now': 'Test timing'
            },
            'cross_source_validation': {
                'has_cross_source': True,
                'validation_level': 1,
                'boost_score': 2.0,
                'validated_problem': True
            }
        }
    ]

    # Temporarily override the output directory
    original_dir = generator.config['output']['markdown_dir']
    generator.config['output']['markdown_dir'] = tmp_path

    # Generate the report
    report_path = generator._export_markdown_report(shortlist)

    # Read the report content
    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Restore original directory
    generator.config['output']['markdown_dir'] = original_dir

    # Verify badge is in the report
    assert 'INDEPENDENT VALIDATION ACROSS REDDIT + HACKER NEWS' in content
    assert '🎯' in content
    assert 'Validation Level**: 1' in content
    assert 'Boost Applied**: +2.0' in content
    assert 'Validated Problem**: ✅ Yes' in content


def test_markdown_report_no_badge_without_validation(tmp_path):
    """测试没有跨源验证时不显示徽章"""
    generator = DecisionShortlistGenerator()

    # Create a mock shortlist without cross-source validation
    shortlist = [
        {
            'opportunity_name': 'Test Opportunity',
            'final_score': 7.5,
            'viability_score': 7.5,
            'cluster_size': 10,
            'trust_level': 0.75,
            'target_users': 'Test users',
            'missing_capability': 'Test capability',
            'why_existing_fail': 'Test reason',
            'readable_content': {
                'problem': 'Test problem',
                'mvp': 'Test MVP',
                'why_now': 'Test timing'
            },
            'cross_source_validation': {
                'has_cross_source': False,
                'validation_level': 0,
                'boost_score': 0.0,
                'validated_problem': False
            }
        }
    ]

    # Temporarily override the output directory
    original_dir = generator.config['output']['markdown_dir']
    generator.config['output']['markdown_dir'] = tmp_path

    # Generate the report
    report_path = generator._export_markdown_report(shortlist)

    # Read the report content
    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Restore original directory
    generator.config['output']['markdown_dir'] = original_dir

    # Verify no badge is in the report
    assert 'INDEPENDENT VALIDATION' not in content
    assert 'Multi-Subreddit Validation' not in content
    assert 'Weak Cross-Source Signal' not in content
    assert 'Validated Problem**: ❌ No' in content


def test_sort_priority_key():
    """测试跨源验证排序键函数"""
    generator = DecisionShortlistGenerator()

    # Create test candidates with different validation levels
    candidates = [
        {
            'opportunity_name': 'No Validation - Low Score',
            'final_score': 6.0,
            'cluster_size': 10,
            'cross_source_validation': {'validation_level': 0}
        },
        {
            'opportunity_name': 'Level 3 - High Score',
            'final_score': 9.0,
            'cluster_size': 20,
            'cross_source_validation': {'validation_level': 3}
        },
        {
            'opportunity_name': 'Level 1 - Medium Score',
            'final_score': 8.0,
            'cluster_size': 15,
            'cross_source_validation': {'validation_level': 1}
        },
        {
            'opportunity_name': 'Level 2 - High Score',
            'final_score': 8.5,
            'cluster_size': 25,
            'cross_source_validation': {'validation_level': 2}
        },
        {
            'opportunity_name': 'No Validation - High Score',
            'final_score': 9.5,
            'cluster_size': 30,
            'cross_source_validation': {'validation_level': 0}
        }
    ]

    # Sort using the priority key function
    sorted_candidates = sorted(candidates, key=generator._sort_priority_key)

    # Verify order: Level 1 > Level 2 > Level 3 > No validation
    assert sorted_candidates[0]['opportunity_name'] == 'Level 1 - Medium Score'
    assert sorted_candidates[1]['opportunity_name'] == 'Level 2 - High Score'
    assert sorted_candidates[2]['opportunity_name'] == 'Level 3 - High Score'
    assert sorted_candidates[3]['opportunity_name'] == 'No Validation - High Score'
    assert sorted_candidates[4]['opportunity_name'] == 'No Validation - Low Score'


def test_sort_priority_key_same_level():
    """测试同一验证等级内按最终评分和聚类大小排序"""
    generator = DecisionShortlistGenerator()

    # Create candidates with same validation level but different scores
    candidates = [
        {
            'opportunity_name': 'Level 1 - Low Score - Small Cluster',
            'final_score': 7.0,
            'cluster_size': 10,
            'cross_source_validation': {'validation_level': 1}
        },
        {
            'opportunity_name': 'Level 1 - High Score - Large Cluster',
            'final_score': 9.0,
            'cluster_size': 30,
            'cross_source_validation': {'validation_level': 1}
        },
        {
            'opportunity_name': 'Level 1 - Medium Score - Medium Cluster',
            'final_score': 8.0,
            'cluster_size': 20,
            'cross_source_validation': {'validation_level': 1}
        }
    ]

    # Sort using the priority key function
    sorted_candidates = sorted(candidates, key=generator._sort_priority_key)

    # Within same validation level, sort by final_score (desc), then cluster_size (desc)
    assert sorted_candidates[0]['opportunity_name'] == 'Level 1 - High Score - Large Cluster'
    assert sorted_candidates[1]['opportunity_name'] == 'Level 1 - Medium Score - Medium Cluster'
    assert sorted_candidates[2]['opportunity_name'] == 'Level 1 - Low Score - Small Cluster'


def test_sort_priority_key_same_score_different_cluster():
    """测试相同最终评分时按聚类大小排序"""
    generator = DecisionShortlistGenerator()

    # Create candidates with same final score but different cluster sizes
    candidates = [
        {
            'opportunity_name': 'Level 2 - Small Cluster',
            'final_score': 8.0,
            'cluster_size': 10,
            'cross_source_validation': {'validation_level': 2}
        },
        {
            'opportunity_name': 'Level 2 - Large Cluster',
            'final_score': 8.0,
            'cluster_size': 30,
            'cross_source_validation': {'validation_level': 2}
        },
        {
            'opportunity_name': 'Level 2 - Medium Cluster',
            'final_score': 8.0,
            'cluster_size': 20,
            'cross_source_validation': {'validation_level': 2}
        }
    ]

    # Sort using the priority key function
    sorted_candidates = sorted(candidates, key=generator._sort_priority_key)

    # Same final score, sort by cluster_size (desc)
    assert sorted_candidates[0]['opportunity_name'] == 'Level 2 - Large Cluster'
    assert sorted_candidates[1]['opportunity_name'] == 'Level 2 - Medium Cluster'
    assert sorted_candidates[2]['opportunity_name'] == 'Level 2 - Small Cluster'
