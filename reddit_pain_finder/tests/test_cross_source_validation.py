"""
跨源验证功能集成测试

测试跨源验证的数据库查询、排序逻辑、徽章生成和评分加成
"""
import pytest
from utils.db import db
from pipeline.decision_shortlist import DecisionShortlistGenerator


class TestCrossSourceValidation:
    """跨源验证功能集成测试"""

    @pytest.fixture
    def shortlist_generator(self):
        """决策清单生成器"""
        return DecisionShortlistGenerator()

    def test_query_cross_source_validated_opportunities(self, shortlist_generator):
        """测试查询跨源验证机会"""
        # 测试查询所有
        opportunities = db.get_cross_source_validated_opportunities()
        assert isinstance(opportunities, list)

        # 如果有数据，验证字段
        if opportunities:
            opp = opportunities[0]
            assert 'cross_source_validation' in opp
            assert 'opportunity_name' in opp
            assert 'total_score' in opp

    def test_query_min_validation_level(self, shortlist_generator):
        """测试最低验证等级过滤"""
        # Level 1
        level1 = db.get_cross_source_validated_opportunities(
            min_validation_level=1
        )

        # Level 2
        level2 = db.get_cross_source_validated_opportunities(
            min_validation_level=2
        )

        # Level 1 应该包含 Level 2（或者更多）
        assert len(level1) >= len(level2)

    def test_sorting_priority(self, shortlist_generator):
        """测试排序优先级"""
        # 创建模拟数据
        mock_candidates = [
            {
                'opportunity_name': 'No Validation',
                'total_score': 9.0,
                'cluster_size': 100,
                'cross_source_validation': {
                    'has_cross_source': False,
                    'validation_level': 0
                }
            },
            {
                'opportunity_name': 'Level 2 Validation',
                'total_score': 7.0,
                'cluster_size': 50,
                'cross_source_validation': {
                    'has_cross_source': True,
                    'validation_level': 2
                }
            },
            {
                'opportunity_name': 'Level 1 Validation',
                'total_score': 8.0,
                'cluster_size': 30,
                'cross_source_validation': {
                    'has_cross_source': True,
                    'validation_level': 1
                }
            }
        ]

        # 应用排序
        sorted_candidates = sorted(
            mock_candidates,
            key=shortlist_generator._sort_priority_key
        )

        # 验证顺序：Level 1 > Level 2 > No Validation
        assert sorted_candidates[0]['opportunity_name'] == 'Level 1 Validation'
        assert sorted_candidates[1]['opportunity_name'] == 'Level 2 Validation'
        assert sorted_candidates[2]['opportunity_name'] == 'No Validation'

    def test_badge_generation(self, shortlist_generator):
        """测试徽章生成"""
        # Level 1
        badge1 = shortlist_generator._get_cross_source_badge({
            'has_cross_source': True,
            'validation_level': 1
        })
        assert 'INDEPENDENT VALIDATION ACROSS REDDIT + HACKER NEWS' in badge1

        # Level 2
        badge2 = shortlist_generator._get_cross_source_badge({
            'has_cross_source': True,
            'validation_level': 2
        })
        assert 'Multi-Subreddit Validation' in badge2

        # No validation
        badge0 = shortlist_generator._get_cross_source_badge({
            'has_cross_source': False
        })
        assert badge0 == ""

    def test_badge_text_generation(self, shortlist_generator):
        """测试徽章文本生成"""
        # Level 1
        text1 = shortlist_generator._get_cross_source_badge_text({
            'has_cross_source': True,
            'validation_level': 1
        })
        assert 'INDEPENDENT VALIDATION ACROSS REDDIT + HACKER NEWS' in text1

        # Level 2
        text2 = shortlist_generator._get_cross_source_badge_text({
            'has_cross_source': True,
            'validation_level': 2
        })
        assert 'Multi-Subreddit Validation' in text2

        # No validation
        text0 = shortlist_generator._get_cross_source_badge_text({
            'has_cross_source': False
        })
        assert text0 == ""

    def test_cross_source_boost_in_scoring(self, shortlist_generator):
        """测试跨源验证在评分中的加成"""
        # 模拟机会数据（使用较低的分数以避免达到上限）
        opportunity = {
            'viability_score': 5.0,
            'cluster_size': 10,
            'trust_level': 0.7
        }

        # 无跨源验证
        score1 = shortlist_generator._calculate_final_score(
            opportunity=opportunity,
            cross_source_info={
                'has_cross_source': False,
                'boost_score': 0.0
            }
        )

        # 有跨源验证 (Level 1, boost=2.0)
        score2 = shortlist_generator._calculate_final_score(
            opportunity=opportunity,
            cross_source_info={
                'has_cross_source': True,
                'boost_score': 2.0
            }
        )

        # 有跨源验证的评分应该更高
        assert score2 > score1, f"Score with boost ({score2}) should be > score without boost ({score1})"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
