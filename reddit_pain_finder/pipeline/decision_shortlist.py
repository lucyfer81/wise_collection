# pipeline/decision_shortlist.py
"""
Decision Shortlist Generator
从所有评分机会中筛选出 Top 3-5 个最值得执行的产品机会
"""
import json
import logging
import math
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

import yaml

from utils.llm_client import llm_client
from utils.db import db

logger = logging.getLogger(__name__)


class DecisionShortlistGenerator:
    """决策清单生成器"""

    def __init__(self, config_path: str = "config/thresholds.yaml"):
        """初始化生成器"""
        self.config = self._load_config(config_path)
        self.pipeline_run_id = f"pipeline_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info("DecisionShortlistGenerator initialized")

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config.get('decision_shortlist', {})
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """返回默认配置"""
        return {
            'min_viability_score': 7.0,
            'min_cluster_size': 6,
            'min_trust_level': 0.7,
            'ignored_clusters': [],
            'final_score_weights': {
                'viability_score': 1.0,
                'cluster_size_log_factor': 2.5,
                'trust_level': 1.5,
                'cross_source_bonus': 5.0
            },
            'output': {
                'min_candidates': 3,
                'max_candidates': 5,
                'markdown_dir': 'reports',
                'json_dir': 'data'
            }
        }

    def _apply_hard_filters(self) -> List[Dict[str, Any]]:
        """应用硬性过滤规则

        Returns:
            通过所有过滤的机会列表
        """
        config = self.config

        min_viability = config['min_viability_score']
        min_cluster_size = config['min_cluster_size']
        min_trust = config['min_trust_level']
        ignored_clusters = set(config.get('ignored_clusters', []))

        logger.info(f"Applying hard filters: viability>={min_viability}, "
                    f"cluster_size>={min_cluster_size}, trust>={min_trust}")

        try:
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT
                        o.id as opportunity_id,
                        o.opportunity_name,
                        o.description,
                        o.total_score as viability_score,
                        o.trust_level as trust_level,
                        o.target_users,
                        o.missing_capability,
                        o.why_existing_fail,
                        c.id as cluster_id,
                        c.cluster_name,
                        c.cluster_size,
                        c.source_type,
                        c.pain_event_ids,
                        c.centroid_summary as cluster_summary
                    FROM opportunities o
                    JOIN clusters c ON o.cluster_id = c.id
                    WHERE o.total_score >= ?
                      AND c.cluster_size >= ?
                      AND o.trust_level >= ?
                      AND c.cluster_name NOT IN (
                        SELECT value FROM json_each(?)
                        WHERE json_valid(?) AND json_each.value IS NOT NULL
                      )
                    ORDER BY o.total_score DESC
                """, (min_viability, min_cluster_size, min_trust,
                      json.dumps(list(ignored_clusters)),
                      json.dumps(list(ignored_clusters))))

                opportunities = [dict(row) for row in cursor.fetchall()]

                # 解析 pain_event_ids JSON
                for opp in opportunities:
                    if opp.get('pain_event_ids'):
                        try:
                            opp['pain_event_ids'] = json.loads(opp['pain_event_ids'])
                        except:
                            opp['pain_event_ids'] = []

                logger.info(f"Hard filters: {len(opportunities)} opportunities passed")
                return opportunities

        except Exception as e:
            logger.error(f"Failed to apply hard filters: {e}")
            return []

    def _check_cross_source_validation(self, opportunity: Dict) -> Dict[str, Any]:
        """检查跨源验证，返回验证信息和加分

        三层优先级：
        - Level 1 (强信号): source_type='aligned' 或在 aligned_problems 表中
        - Level 2 (中等信号): cluster_size >= 10 AND 跨 >=3 subreddits
        - Level 3 (弱信号): cluster_size >= 8 AND 跨 >=2 subreddits
        """
        cluster = opportunity

        # Level 1: 检查 source_type
        if cluster.get('source_type') == 'aligned':
            return {
                "has_cross_source": True,
                "validation_level": 1,
                "boost_score": 2.0,
                "validated_problem": True,
                "evidence": "source_type='aligned'"
            }

        # Level 1: 检查 aligned_problems 表
        aligned_problem = self._check_aligned_problems_table(cluster['cluster_name'])
        if aligned_problem:
            return {
                "has_cross_source": True,
                "validation_level": 1,
                "boost_score": 2.0,
                "validated_problem": True,
                "evidence": f"Found in aligned_problems: {aligned_problem['aligned_problem_id']}"
            }

        # Level 2 & 3: 检查 cluster_size + 跨 subreddit
        pain_event_ids = cluster.get('pain_event_ids', [])
        if not pain_event_ids:
            return {
                "has_cross_source": False,
                "validation_level": 0,
                "boost_score": 0.0,
                "validated_problem": False,
                "evidence": "No pain events"
            }

        subreddit_count = self._count_subreddits(pain_event_ids)
        cluster_size = cluster['cluster_size']

        # Level 2
        if cluster_size >= 10 and subreddit_count >= 3:
            return {
                "has_cross_source": True,
                "validation_level": 2,
                "boost_score": 1.0,
                "validated_problem": True,
                "evidence": f"Large cluster ({cluster_size}) across {subreddit_count} subreddits"
            }

        # Level 3
        if cluster_size >= 8 and subreddit_count >= 2:
            return {
                "has_cross_source": True,
                "validation_level": 3,
                "boost_score": 0.5,
                "validated_problem": False,
                "evidence": f"Medium cluster ({cluster_size}) across {subreddit_count} subreddits"
            }

        # 无跨源验证
        return {
            "has_cross_source": False,
            "validation_level": 0,
            "boost_score": 0.0,
            "validated_problem": False,
            "evidence": "No cross-source validation"
        }

    def _check_aligned_problems_table(self, cluster_name: str) -> Optional[Dict]:
        """检查 cluster 是否在 aligned_problems 表中"""
        try:
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT aligned_problem_id, sources, alignment_score
                    FROM aligned_problems
                    WHERE cluster_ids LIKE ?
                """, (f'%{cluster_name}%',))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Failed to check aligned_problems: {e}")
            return None

    def _count_subreddits(self, pain_event_ids: List[int]) -> int:
        """计算涉及的不同 subreddit 数量"""
        try:
            with db.get_connection("pain") as conn:
                placeholders = ','.join('?' for _ in pain_event_ids)
                cursor = conn.execute(f"""
                    SELECT COUNT(DISTINCT fp.subreddit) as count
                    FROM pain_events pe
                    JOIN filtered_posts fp ON pe.post_id = fp.id
                    WHERE pe.id IN ({placeholders})
                """, pain_event_ids)
                return cursor.fetchone()['count']
        except Exception as e:
            logger.error(f"Failed to count subreddits: {e}")
            return 1  # 默认为 1，避免 0

    def generate_shortlist(self) -> Dict[str, Any]:
        """生成决策清单（主方法）"""
        logger.info("=== Decision Shortlist Generation Started ===")

        # TODO: 实现各个步骤
        result = {
            'shortlist_count': 0,
            'shortlist': [],
            'generated_at': datetime.now().isoformat()
        }

        return result
