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
                        o.raw_total_score as viability_score,
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
                    WHERE o.raw_total_score >= ?
                      AND c.cluster_size >= ?
                      AND o.trust_level >= ?
                      AND c.cluster_name NOT IN (
                        SELECT value FROM json_each(?)
                        WHERE json_valid(?) AND json_each.value IS NOT NULL
                      )
                    ORDER BY o.raw_total_score DESC
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

    def _calculate_final_score(self, opportunity: Dict, cross_source_info: Dict) -> float:
        """计算最终评分（使用对数尺度）

        Args:
            opportunity: 机会字典，包含 viability_score, cluster_size, trust_level
            cross_source_info: 跨源验证信息

        Returns:
            最终评分 (0-10)
        """
        weights = self.config['final_score_weights']

        viability_score = opportunity['viability_score']
        trust_level = opportunity['trust_level']
        cluster_size = opportunity['cluster_size']

        # 使用对数尺度，避免大cluster主导评分
        cluster_size_log = math.log10(max(cluster_size, 1))

        # 计算基础分数
        final_score = (
            viability_score * weights['viability_score'] +
            cluster_size_log * weights['cluster_size_log_factor'] +
            trust_level * weights['trust_level']
        )

        # 如果有跨源验证，加分
        if cross_source_info['has_cross_source']:
            boost = cross_source_info['boost_score']
            final_score += weights['cross_source_bonus'] * boost * 0.1

        # 限制在 0-10 范围内
        return min(max(final_score, 0), 10.0)

    def _get_default_prompt(self) -> str:
        """获取默认的 LLM prompt"""
        return """你是一个产品经理专家。请基于以下痛点聚类和机会信息，生成简洁明了的产品描述：

**机会名称**: {opportunity_name}

**问题描述**:
{cluster_summary}

**目标用户**: {target_users}

**缺失能力**: {missing_capability}

**现有方案不足**: {why_existing_fail}

请以 JSON 格式返回以下字段（不要包含 markdown 标记）：
{{
  "problem": "用1-2句话清晰描述核心痛点问题",
  "mvp": "描述最小可行产品的核心功能和解决方案",
  "why_now": "解释为什么现在是切入这个市场的最佳时机（技术成熟度、市场变化、用户需求等）"
}}

要求：
1. 问题描述要具体且击中用户痛点
2. MVP 要简洁可行，适合 solo developer
3. Why Now 要有说服力，体现市场机会
4. 每个字段控制在50字以内
5. 只返回 JSON，不要有其他内容
"""

    def _generate_readable_content(self, opportunity: Dict, cluster: Dict, cross_source_info: Dict) -> Dict[str, str]:
        """生成可读性内容（Problem, MVP, Why Now）

        Args:
            opportunity: 机会信息
            cluster: 聚类信息
            cross_source_info: 跨源验证信息

        Returns:
            包含 problem, mvp, why_now 的字典
        """
        try:
            prompt = self._get_default_prompt().format(
                opportunity_name=opportunity.get('opportunity_name', ''),
                cluster_summary=cluster.get('cluster_summary', opportunity.get('description', '')),
                target_users=opportunity.get('target_users', 'Unknown'),
                missing_capability=opportunity.get('missing_capability', 'Unknown'),
                why_existing_fail=opportunity.get('why_existing_fail', 'Unknown')
            )

            # 调用 LLM
            response = llm_client.generate(
                prompt=prompt,
                model="gpt-4o-mini",  # 使用更经济的模型
                temperature=0.7,
                max_tokens=500
            )

            # 解析 JSON 响应
            import json
            import re

            # 尝试提取 JSON（去除可能的 markdown 代码块标记）
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                content = json.loads(json_str)

                # 验证必需字段
                required_fields = ['problem', 'mvp', 'why_now']
                if all(field in content for field in required_fields):
                    logger.info(f"✅ LLM content generated for {opportunity['opportunity_name']}")
                    return {
                        'problem': content['problem'],
                        'mvp': content['mvp'],
                        'why_now': content['why_now']
                    }

            # 如果解析失败，使用 fallback
            logger.warning(f"Failed to parse LLM response, using fallback")
            return self._fallback_readable_content(opportunity, cluster)

        except Exception as e:
            logger.error(f"Error generating readable content: {e}")
            return self._fallback_readable_content(opportunity, cluster)

    def _fallback_readable_content(self, opportunity: Dict, cluster: Dict) -> Dict[str, str]:
        """生成可读性内容的 fallback 方案

        Args:
            opportunity: 机会信息
            cluster: 聚类信息

        Returns:
            包含 problem, mvp, why_now 的字典
        """
        cluster_name = cluster.get('cluster_name', 'Unknown')
        description = opportunity.get('description', '')
        target_users = opportunity.get('target_users', 'users')
        missing_capability = opportunity.get('missing_capability', 'capability')

        return {
            'problem': f"Users in {cluster_name} are struggling with {description[:100]}",
            'mvp': f"Build a tool that provides {missing_capability} for {target_users}",
            'why_now': f"High demand from {cluster.get('cluster_size', 0)} users indicates immediate market need"
        }

    def _sort_priority_key(self, candidate: Dict) -> tuple:
        """生成排序键，确保跨源验证的机会排在前面

        排序优先级：
        1. 跨源验证等级（Level 1 > Level 2 > Level 3 > No validation）
        2. 最终评分（降序）
        3. 聚类规模（降序）

        Args:
            candidate: 候选机会字典

        Returns:
            排序键元组
        """
        cross_source = candidate.get('cross_source_validation', {})
        validation_level = cross_source.get('validation_level', 0)

        # 验证等级：Level 1 最优先，Level 0（无验证）最低
        # 使用反向映射：1 -> 3, 2 -> 2, 3 -> 1, 0 -> 0
        if validation_level == 1:
            priority_score = 3
        elif validation_level == 2:
            priority_score = 2
        elif validation_level == 3:
            priority_score = 1
        else:
            priority_score = 0

        # 用负数实现降序：优先级高的排在前面
        priority_score = -priority_score

        # 最终评分降序
        final_score = -candidate.get('final_score', 0)

        # 聚类规模降序
        cluster_size = -candidate.get('cluster_size', 0)

        return (priority_score, final_score, cluster_size)

    def generate_shortlist(self) -> Dict[str, Any]:
        """生成决策清单（主方法）

        流程：
        1. 应用硬性过滤
        2. 对每个机会进行跨源验证和评分
        3. 按最终评分排序
        4. 选择 Top 3-5 候选
        5. 生成可读性内容
        6. 导出 markdown 和 JSON 报告

        Returns:
            包含 shortlist 的结果字典
        """
        logger.info("=== Decision Shortlist Generation Started ===")

        # 步骤 1: 应用硬性过滤
        logger.info("Step 1: Applying hard filters...")
        opportunities = self._apply_hard_filters()

        if not opportunities:
            logger.warning("No opportunities passed hard filters")
            return self._handle_empty_shortlist()

        logger.info(f"✅ {len(opportunities)} opportunities passed hard filters")

        # 步骤 2-3: 对每个机会进行跨源验证和评分
        logger.info("Step 2-3: Calculating final scores with cross-source validation...")
        scored_opportunities = []

        for opp in opportunities:
            # 跨源验证
            cross_source_info = self._check_cross_source_validation(opp)

            # 计算最终评分
            final_score = self._calculate_final_score(opp, cross_source_info)

            # 添加评分信息
            opp_with_score = {
                **opp,
                'final_score': final_score,
                'cross_source_validation': cross_source_info
            }

            scored_opportunities.append(opp_with_score)

        logger.info(f"✅ Scored {len(scored_opportunities)} opportunities")

        # 步骤 4: 按照优先级排序并选择 Top 候选
        logger.info("Step 4: Selecting top candidates...")
        # 按照优先级排序：跨源验证 > 最终评分 > 聚类规模
        scored_opportunities.sort(key=self._sort_priority_key)

        top_candidates = self._select_top_candidates_with_diversity(scored_opportunities)
        logger.info(f"✅ Selected {len(top_candidates)} top candidates")

        if not top_candidates:
            logger.warning("No candidates selected")
            return self._handle_empty_shortlist()

        # 步骤 5: 生成可读性内容
        logger.info("Step 5: Generating readable content...")
        for candidate in top_candidates:
            readable_content = self._generate_readable_content(
                candidate,
                candidate,
                candidate['cross_source_validation']
            )
            candidate['readable_content'] = readable_content
            logger.info(f"  - {candidate['opportunity_name']}: {readable_content['problem'][:50]}...")

        # 步骤 6: 导出报告
        logger.info("Step 6: Exporting reports...")
        markdown_path = self._export_markdown_report(top_candidates)
        json_path = self._export_json_report(top_candidates)

        result = {
            'shortlist_count': len(top_candidates),
            'shortlist': top_candidates,
            'markdown_report': markdown_path,
            'json_report': json_path,
            'generated_at': datetime.now().isoformat()
        }

        logger.info("=== Decision Shortlist Generation Complete ===")
        logger.info(f"📝 Markdown report: {markdown_path}")
        logger.info(f"📊 JSON report: {json_path}")

        return result

    def _select_top_candidates_with_diversity(self, scored_opportunities: List[Dict]) -> List[Dict]:
        """选择 Top 候选，考虑多样性

        Args:
            scored_opportunities: 已评分的机会列表

        Returns:
            选中的候选列表
        """
        config = self.config['output']
        min_candidates = config['min_candidates']
        max_candidates = config['max_candidates']

        # 简单策略：取前 N 个
        # TODO: 未来可以加入多样性考虑（不同的 cluster, 不同的问题类型等）
        selected_count = min(max_candidates, len(scored_opportunities))

        # 确保至少有 min_candidates 个
        if len(scored_opportunities) < min_candidates:
            logger.warning(f"Only {len(scored_opportunities)} candidates available, less than min {min_candidates}")
            selected_count = len(scored_opportunities)

        return scored_opportunities[:selected_count]

    def _get_cross_source_badge(self, cross_source: Dict) -> str:
        """生成跨源验证的徽章标识

        Args:
            cross_source: 跨源验证信息字典

        Returns:
            徽章字符串（Markdown格式）
        """
        if not cross_source.get('has_cross_source'):
            return ""

        validation_level = cross_source.get('validation_level', 0)

        if validation_level == 1:
            # Level 1: 最强信号 - 多平台独立验证
            return """
<div align="center">

### 🎯 INDEPENDENT VALIDATION ACROSS REDDIT + HACKER NEWS

**This pain point has been independently validated across multiple communities**

</div>
"""
        elif validation_level == 2:
            # Level 2: 中等信号 - 多 subreddit 验证
            return """
### ✓ Multi-Subreddit Validation
*Validated across 3+ subreddits with strong cluster size*
"""
        elif validation_level == 3:
            # Level 3: 弱信号
            return """
### ◐ Weak Cross-Source Signal
*Initial cross-community detection signal*
"""
        else:
            return ""

    def _get_cross_source_badge_text(self, cross_source: Dict) -> str:
        """获取跨源验证徽章的纯文本版本

        Args:
            cross_source: 跨源验证信息字典

        Returns:
            徽章文本
        """
        if not cross_source.get('has_cross_source'):
            return ""

        validation_level = cross_source.get('validation_level', 0)

        badge_texts = {
            1: "🎯 INDEPENDENT VALIDATION ACROSS REDDIT + HACKER NEWS",
            2: "✓ Multi-Subreddit Validation",
            3: "◐ Weak Cross-Source Signal"
        }

        return badge_texts.get(validation_level, "")

    def _export_markdown_report(self, shortlist: List[Dict]) -> str:
        """导出 Markdown 格式的报告

        Args:
            shortlist: 决策清单列表

        Returns:
            报告文件路径
        """
        config = self.config['output']
        output_dir = config['markdown_dir']

        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'decision_shortlist_{timestamp}.md'
        filepath = os.path.join(output_dir, filename)

        # 生成报告内容
        report_lines = [
            "# Decision Shortlist Report",
            f"\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Total Candidates**: {len(shortlist)}",
            "\n---\n"
        ]

        for idx, candidate in enumerate(shortlist, 1):
            content = candidate.get('readable_content', {})
            cross_source = candidate.get('cross_source_validation', {})

            report_lines.extend([
                f"## {idx}. {candidate['opportunity_name']}"
            ])

            # 添加跨源验证徽章（在最前面，最醒目）
            badge = self._get_cross_source_badge(cross_source)
            if badge:
                report_lines.extend([
                    f"\n{badge}",
                    f"**Validation Level**: {cross_source.get('validation_level', 0)}  ",
                    f"**Boost Applied**: +{cross_source.get('boost_score', 0.0):.1f} to final score",
                    ""
                ])

            report_lines.extend([
                f"**Final Score**: {candidate['final_score']:.2f}/10.0  ",
                f"**Viability Score**: {candidate['viability_score']:.1f}  ",
                f"**Cluster Size**: {candidate['cluster_size']}  ",
                f"**Trust Level**: {candidate['trust_level']:.2f}  ",
                f"**Validated Problem**: {'✅ Yes' if cross_source.get('validated_problem') else '❌ No'}"
            ])

            report_lines.extend([
                "\n### Problem",
                f"\n{content.get('problem', 'N/A')}",
                "\n### MVP Solution",
                f"\n{content.get('mvp', 'N/A')}",
                "\n### Why Now",
                f"\n{content.get('why_now', 'N/A')}",
                "\n### Additional Details",
                f"\n- **Target Users**: {candidate.get('target_users', 'N/A')}",
                f"- **Missing Capability**: {candidate.get('missing_capability', 'N/A')}",
                f"- **Why Existing Solutions Fail**: {candidate.get('why_existing_fail', 'N/A')}",
                "\n---\n"
            ])

        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))

        logger.info(f"✅ Markdown report exported: {filepath}")
        return filepath

    def _export_json_report(self, shortlist: List[Dict]) -> str:
        """导出 JSON 格式的报告

        Args:
            shortlist: 决策清单列表

        Returns:
            报告文件路径
        """
        config = self.config['output']
        output_dir = config['json_dir']

        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'decision_shortlist_{timestamp}.json'
        filepath = os.path.join(output_dir, filename)

        # 准备导出数据
        export_data = {
            'generated_at': datetime.now().isoformat(),
            'total_candidates': len(shortlist),
            'candidates': []
        }

        for candidate in shortlist:
            cross_source = candidate.get('cross_source_validation', {})

            export_candidate = {
                'opportunity_name': candidate.get('opportunity_name'),
                'final_score': candidate.get('final_score'),
                'viability_score': candidate.get('viability_score'),
                'cluster_size': candidate.get('cluster_size'),
                'trust_level': candidate.get('trust_level'),
                'target_users': candidate.get('target_users'),
                'missing_capability': candidate.get('missing_capability'),
                'why_existing_fail': candidate.get('why_existing_fail'),
                'readable_content': candidate.get('readable_content', {}),
                'cross_source_validation': {
                    'has_cross_source': cross_source.get('has_cross_source', False),
                    'validation_level': cross_source.get('validation_level', 0),
                    'validated_problem': cross_source.get('validated_problem', False),
                    'boost_score': cross_source.get('boost_score', 0.0),
                    'evidence': cross_source.get('evidence', ''),
                    'badge_text': self._get_cross_source_badge_text(cross_source)
                }
            }
            export_data['candidates'].append(export_candidate)

        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ JSON report exported: {filepath}")
        return filepath

    def _handle_empty_shortlist(self) -> Dict[str, Any]:
        """处理空清单的情况

        Returns:
            空结果字典
        """
        logger.warning("=== Empty Shortlist ===")

        result = {
            'shortlist_count': 0,
            'shortlist': [],
            'generated_at': datetime.now().isoformat(),
            'warning': 'No opportunities met the criteria'
        }

        return result
