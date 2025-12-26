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
