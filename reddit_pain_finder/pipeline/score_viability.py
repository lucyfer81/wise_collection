"""
Score Viability module for Reddit Pain Point Finder
可行性评分模块 - 针对一人公司的可行性评估
"""
import json
import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
import yaml
from pathlib import Path

from utils.llm_client import llm_client
from utils.db import db

logger = logging.getLogger(__name__)

class ViabilityScorer:
    """可行性评分器"""

    def __init__(self):
        """初始化评分器"""
        self.stats = {
            "total_opportunities_scored": 0,
            "viable_opportunities": 0,
            "good_opportunities": 0,
            "excellent_opportunities": 0,
            "processing_time": 0.0,
            "avg_total_score": 0.0,
            "skipped_clusters": 0
        }

        # 加载配置
        self.config = self._load_config()
        self.filtering_rules = self.config.get("filtering_rules", {})

        logger.info(f"ViabilityScorer initialized with filtering rules enabled: {self.filtering_rules.get('enabled', False)}")

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            config_path = Path(__file__).parent.parent / "config" / "thresholds.yaml"
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {config_path}")
            return config
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            return {"filtering_rules": {"enabled": False}}

    def _calculate_unique_authors(self, pain_event_ids: List[int]) -> int:
        """计算独立作者数量"""
        if not pain_event_ids:
            return 0

        try:
            with db.get_connection("pain") as conn:
                placeholders = ','.join(['?' for _ in pain_event_ids])
                cursor = conn.execute(f"""
                    SELECT COUNT(DISTINCT fp.author) as unique_count
                    FROM pain_events pe
                    JOIN filtered_posts fp ON pe.post_id = fp.id
                    WHERE pe.id IN ({placeholders})
                """, pain_event_ids)
                result = cursor.fetchone()
                return result['unique_count'] if result else 0
        except Exception as e:
            logger.error(f"Failed to calculate unique authors: {e}")
            return 0

    def _calculate_cross_subreddit_count(self, pain_event_ids: List[int]) -> int:
        """计算跨子版块数量"""
        if not pain_event_ids:
            return 0

        try:
            with db.get_connection("pain") as conn:
                placeholders = ','.join(['?' for _ in pain_event_ids])
                cursor = conn.execute(f"""
                    SELECT COUNT(DISTINCT fp.subreddit) as subreddit_count
                    FROM pain_events pe
                    JOIN filtered_posts fp ON pe.post_id = fp.id
                    WHERE pe.id IN ({placeholders})
                """, pain_event_ids)
                result = cursor.fetchone()
                return result['subreddit_count'] if result else 0
        except Exception as e:
            logger.error(f"Failed to calculate cross-subreddit count: {e}")
            return 0

    def _calculate_avg_frequency_score(self, pain_event_ids: List[int]) -> float:
        """计算平均频率评分"""
        if not pain_event_ids:
            return 0.0

        try:
            with db.get_connection("pain") as conn:
                placeholders = ','.join(['?' for _ in pain_event_ids])
                cursor = conn.execute(f"""
                    SELECT pe.frequency
                    FROM pain_events pe
                    WHERE pe.id IN ({placeholders})
                """, pain_event_ids)

                frequencies = [row['frequency'] or '' for row in cursor.fetchall()]
                return self._frequency_to_score(frequencies)
        except Exception as e:
            logger.error(f"Failed to calculate average frequency score: {e}")
            return 0.0

    def _calculate_cluster_trust_level(self, pain_event_ids: List[int]) -> float:
        """计算聚类中所有帖子的平均信任度"""
        if not pain_event_ids:
            return 0.5  # 默认中等信任度

        try:
            with db.get_connection("pain") as conn:
                placeholders = ','.join(['?' for _ in pain_event_ids])
                cursor = conn.execute(f"""
                    SELECT AVG(fp.trust_level) as avg_trust
                    FROM pain_events pe
                    JOIN filtered_posts fp ON pe.post_id = fp.id
                    WHERE pe.id IN ({placeholders})
                """, pain_event_ids)
                result = cursor.fetchone()
                return result['avg_trust'] if result and result['avg_trust'] else 0.5
        except Exception as e:
            logger.error(f"Failed to calculate cluster trust level: {e}")
            return 0.5

    def _frequency_to_score(self, frequencies: List[str]) -> float:
        """将频率文本转换为评分"""
        if not frequencies:
            return 0.0

        score_map = self.filtering_rules.get("frequency_score_mapping", {
            'daily': 10, '每天': 10, 'day': 9,
            'weekly': 8, '每周': 8, 'week': 7,
            'monthly': 6, '每月': 6, 'month': 5,
            'often': 7, '经常': 7, 'frequently': 8,
            'sometimes': 5, '有时': 5, 'occasionally': 4,
            'rarely': 3, '很少': 3, 'seldom': 2,
            'always': 9, '总是': 9, 'constantly': 8,
            'never': 1, '从不': 1, 'default': 4
        })

        scores = []
        for freq in frequencies:
            if not freq:
                scores.append(score_map.get('default', 4))
                continue

            freq_lower = freq.lower()
            matched = False
            for key, score in score_map.items():
                if key == 'default':
                    continue
                if key in freq_lower:
                    scores.append(score)
                    matched = True
                    break

            if not matched:
                scores.append(score_map.get('default', 4))

        return sum(scores) / len(scores) if scores else 0.0

    def should_skip_solution_design(self, cluster_data: Dict[str, Any]) -> tuple[bool, str]:
        """判断是否应该跳过解决方案设计"""
        if not self.filtering_rules.get("enabled", False):
            return False, ""

        # 1. 检查聚类大小
        cluster_size = cluster_data.get('cluster_size', 0)
        min_cluster_size = self.filtering_rules.get("min_cluster_size", 8)
        if cluster_size < min_cluster_size:
            reason = self.filtering_rules.get("skip_reasons", {}).get("cluster_size",
                    f"聚类规模过小 ({cluster_size} < {min_cluster_size})")
            formatted_reason = reason.format(actual=cluster_size, required=min_cluster_size)
            if self.filtering_rules.get("log_skipped_clusters", True):
                logger.info(f"Skipping cluster due to size: {formatted_reason}")
            return True, formatted_reason

        # 2. 检查独立作者数
        pain_event_ids = cluster_data.get('pain_event_ids', [])
        if isinstance(pain_event_ids, str):
            import json
            try:
                pain_event_ids = json.loads(pain_event_ids)
            except:
                pain_event_ids = []

        unique_authors = self._calculate_unique_authors(pain_event_ids)
        min_unique_authors = self.filtering_rules.get("min_unique_authors", 5)
        if unique_authors < min_unique_authors:
            reason = self.filtering_rules.get("skip_reasons", {}).get("unique_authors",
                    f"独立作者不足 ({unique_authors} < {min_unique_authors})")
            formatted_reason = reason.format(actual=unique_authors, required=min_unique_authors)
            if self.filtering_rules.get("log_skipped_clusters", True):
                logger.info(f"Skipping cluster due to unique authors: {formatted_reason}")
            return True, formatted_reason

        # 3. 检查跨子版块数量
        cross_subreddit_count = self._calculate_cross_subreddit_count(pain_event_ids)
        min_cross_subreddit_count = self.filtering_rules.get("min_cross_subreddit_count", 2)
        if cross_subreddit_count < min_cross_subreddit_count:
            reason = self.filtering_rules.get("skip_reasons", {}).get("cross_subreddit",
                    f"跨子版块数量不足 ({cross_subreddit_count} < {min_cross_subreddit_count})")
            formatted_reason = reason.format(actual=cross_subreddit_count, required=min_cross_subreddit_count)
            if self.filtering_rules.get("log_skipped_clusters", True):
                logger.info(f"Skipping cluster due to cross-subreddit: {formatted_reason}")
            return True, formatted_reason

        # 4. 检查平均频率评分
        avg_frequency_score = self._calculate_avg_frequency_score(pain_event_ids)
        min_avg_frequency_score = self.filtering_rules.get("min_avg_frequency_score", 6)
        if avg_frequency_score < min_avg_frequency_score:
            reason = self.filtering_rules.get("skip_reasons", {}).get("frequency_score",
                    f"痛点频率不够高 ({avg_frequency_score:.1f} < {min_avg_frequency_score})")
            formatted_reason = reason.format(actual=avg_frequency_score, required=min_avg_frequency_score)
            if self.filtering_rules.get("log_skipped_clusters", True):
                logger.info(f"Skipping cluster due to frequency score: {formatted_reason}")
            return True, formatted_reason

        if self.filtering_rules.get("log_detailed_metrics", False):
            logger.info(f"Cluster passed filtering checks - size: {cluster_size}, "
                       f"authors: {unique_authors}, subreddits: {cross_subreddit_count}, "
                       f"frequency: {avg_frequency_score:.1f}")

        return False, ""

    def _calculate_market_size_score(self, pain_event_ids: List[int]) -> float:
        """基于硬数据计算市场规模评分 (0-10)"""
        try:
            # 1. 获取独立作者数
            unique_authors = self._calculate_unique_authors(pain_event_ids)

            # 2. 获取涉及的subreddit数量
            cross_subreddit = self._calculate_cross_subreddit_count(pain_event_ids)

            # 3. 基于作者数和subreddit数计算评分
            # 作者数评分 (最高5分)
            author_score = min(unique_authors / 10, 5.0)  # 10+作者=5分

            # 跨度评分 (最高5分)
            subreddit_score = min(cross_subreddit * 1.5, 5.0)  # 3+subreddit=5分

            total_score = author_score + subreddit_score
            return min(total_score, 10.0)

        except Exception as e:
            logger.error(f"Failed to calculate market size score: {e}")
            return 3.0  # 默认中等偏下

    def _calculate_pain_frequency_score_data_driven(self, pain_event_ids: List[int]) -> float:
        """基于频率数据计算痛点频率评分 (0-10) - 数据驱动"""
        # 直接复用现有的 _calculate_avg_frequency_score
        return self._calculate_avg_frequency_score(pain_event_ids)

    def _update_opportunities_recommendation(self, cluster_id: int, recommendation: str, skip_reason: str = "") -> bool:
        """更新聚类下所有机会的推荐状态"""
        try:
            with db.get_connection("clusters") as conn:
                # 获取所有相关机会
                cursor = conn.execute("""
                    SELECT id FROM opportunities WHERE cluster_id = ?
                """, (cluster_id,))
                opportunity_ids = [row['id'] for row in cursor.fetchall()]

                # 更新每个机会的推荐
                for opp_id in opportunity_ids:
                    full_recommendation = f"abandon - {skip_reason}" if skip_reason else recommendation
                    conn.execute("""
                        UPDATE opportunities
                        SET recommendation = ?
                        WHERE id = ?
                    """, (full_recommendation, opp_id))

                conn.commit()
                logger.info(f"Updated {len(opportunity_ids)} opportunities with recommendation: {full_recommendation}")
                return True

        except Exception as e:
            logger.error(f"Failed to update opportunities recommendation: {e}")
            return False

    def _apply_filtering_rules(self, opportunities: List[Dict[str, Any]], processed_clusters: set) -> List[Dict[str, Any]]:
        """应用过滤规则"""
        filtered_opportunities = []
        skipped_count = 0

        for opportunity in opportunities:
            cluster_id = opportunity["cluster_id"]

            # 避免重复处理同一个聚类
            if cluster_id in processed_clusters:
                filtered_opportunities.append(opportunity)
                continue

            # 获取聚类数据
            try:
                with db.get_connection("clusters") as conn:
                    cursor = conn.execute("""
                        SELECT * FROM clusters WHERE id = ?
                    """, (cluster_id,))
                    cluster_data = cursor.fetchone()
                    cluster_data = dict(cluster_data) if cluster_data else None

                if cluster_data:
                    # 检查过滤规则
                    should_skip, skip_reason = self.should_skip_solution_design(cluster_data)

                    if should_skip:
                        # 跳过该聚类的所有机会
                        self._update_opportunities_recommendation(cluster_id, "abandon", skip_reason)
                        processed_clusters.add(cluster_id)
                        skipped_count += 1
                        self.stats["skipped_clusters"] += 1

                        # 统计跳过的机会数量
                        with db.get_connection("clusters") as conn:
                            cursor = conn.execute("""
                                SELECT COUNT(*) as count FROM opportunities WHERE cluster_id = ?
                            """, (cluster_id,))
                            opp_count = cursor.fetchone()['count']
                            logger.info(f"Skipped {opp_count} opportunities from cluster {cluster_id}: {skip_reason}")

                        continue
                    else:
                        # 聚类通过过滤，保留其机会
                        processed_clusters.add(cluster_id)
                        filtered_opportunities.append(opportunity)
                        logger.info(f"Cluster {cluster_id} passed filtering checks")
                else:
                    logger.warning(f"Cluster {cluster_id} not found, including opportunity")
                    filtered_opportunities.append(opportunity)

            except Exception as e:
                logger.error(f"Error processing cluster {cluster_id}: {e}")
                filtered_opportunities.append(opportunity)

        logger.info(f"Filtering applied: {skipped_count} clusters skipped, {len(filtered_opportunities)} opportunities remaining")
        return filtered_opportunities

    def _enhance_opportunity_data(self, opportunity_data: Dict[str, Any]) -> Dict[str, Any]:
        """增强机会数据"""
        try:
            # 获取聚类信息
            cluster_id = opportunity_data["cluster_id"]
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT * FROM clusters WHERE id = ?
                """, (cluster_id,))
                cluster_data = cursor.fetchone()

            if not cluster_data:
                return opportunity_data

            cluster_info = dict(cluster_data)

            # 获取聚类中的痛点事件
            pain_event_ids = json.loads(cluster_info.get("pain_event_ids", "[]"))
            pain_events = []

            with db.get_connection("pain") as conn:
                for event_id in pain_event_ids:
                    cursor = conn.execute("""
                        SELECT * FROM pain_events WHERE id = ?
                    """, (event_id,))
                    event_data = cursor.fetchone()
                    if event_data:
                        pain_events.append(dict(event_data))

            # 增强机会数据
            enhanced_opportunity = opportunity_data.copy()
            enhanced_opportunity.update({
                "cluster_info": {
                    "cluster_name": cluster_info["cluster_name"],
                    "cluster_description": cluster_info["cluster_description"],
                    "cluster_size": cluster_info["cluster_size"],
                    "workflow_confidence": cluster_info.get("workflow_confidence", 0.0),
                    "pain_events": pain_events
                }
            })

            # 添加市场规模估算
            self._estimate_market_size(enhanced_opportunity)

            # 添加竞争分析
            self._analyze_competition(enhanced_opportunity)

            return enhanced_opportunity

        except Exception as e:
            logger.error(f"Failed to enhance opportunity data: {e}")
            return opportunity_data

    def _estimate_market_size(self, opportunity_data: Dict[str, Any]):
        """估算市场规模"""
        try:
            cluster_info = opportunity_data.get("cluster_info", {})
            pain_events = cluster_info.get("pain_events", [])

            # 基于子版块分布估算用户群体
            subreddit_distribution = {}
            for event in pain_events:
                with db.get_connection("filtered") as conn:
                    cursor = conn.execute("""
                        SELECT subreddit FROM filtered_posts WHERE id = ?
                    """, (event["post_id"],))
                    post_data = cursor.fetchone()
                    if post_data:
                        subreddit = post_data[0]
                        subreddit_distribution[subreddit] = subreddit_distribution.get(subreddit, 0) + 1

            # 估算用户基数
            subreddit_estimates = {
                "programming": 5000000,  # 500万开发者
                "MachineLearning": 2000000,  # 200万ML从业者
                "Entrepreneur": 1000000,  # 100万创业者
                "startups": 2000000,  # 200万初创公司人员
                "dataisbeautiful": 500000,  # 50万数据爱好者
                "webdev": 3000000,  # 300万Web开发者
                "sysadmin": 1500000,  # 150万系统管理员
                "ChatGPT": 10000000,  # 1000万ChatGPT用户
                "LocalLLaMA": 500000,  # 50万本地LLM用户
            }

            # 计算总市场规模
            total_estimated_users = 0
            for subreddit, count in subreddit_distribution.items():
                estimated_users = subreddit_estimates.get(subreddit, 100000)  # 默认10万
                weight = count / len(pain_events)  # 基于出现频率的权重
                total_estimated_users += estimated_users * weight

            # 市场渗透率估算（保守估计）
            penetration_rate = 0.001  # 0.1%的市场渗透率
            addressable_market = total_estimated_users * penetration_rate

            opportunity_data["market_analysis"] = {
                "subreddit_distribution": subreddit_distribution,
                "estimated_total_users": int(total_estimated_users),
                "conservative_penetration_rate": penetration_rate,
                "addressable_market_size": int(addressable_market),
                "market_tier": self._get_market_tier(addressable_market)
            }

        except Exception as e:
            logger.error(f"Failed to estimate market size: {e}")

    def _get_market_tier(self, market_size: int) -> str:
        """获取市场层级"""
        if market_size > 100000:  # 10万+
            return "large"
        elif market_size > 50000:  # 5万-10万
            return "medium"
        elif market_size > 10000:  # 1万-5万
            return "small"
        else:  # 1万以下
            return "niche"

    def _analyze_competition(self, opportunity_data: Dict[str, Any]):
        """分析竞争情况"""
        try:
            opportunity_name = opportunity_data.get("opportunity_name", "").lower()
            description = opportunity_data.get("description", "").lower()
            target_users = opportunity_data.get("target_users", "").lower()

            # 竞争对手关键词（简化版本）
            competitor_keywords = {
                "automation": ["zapier", "ifttt", "integromat", "make.com"],
                "data_analysis": ["tableau", "power bi", "looker", "metabase"],
                "project_management": ["jira", "trello", "asana", "monday.com"],
                "documentation": ["notion", "confluence", "obsidian", "roam research"],
                "api_tools": ["postman", "insomnia", "swagger", "openapi"],
                "monitoring": ["datadog", "new relic", "grafana", "prometheus"],
                "testing": ["jest", "cypress", "selenium", "playwright"],
                "development": ["vs code", "github", "gitlab", "intellij"],
                "communication": ["slack", "discord", "teams", "zoom"]
            }

            # 检测竞争对手
            detected_competitors = []
            for category, competitors in competitor_keywords.items():
                for competitor in competitors:
                    if (competitor in opportunity_name or
                        competitor in description or
                        competitor in target_users):
                        detected_competitors.append({
                            "name": competitor,
                            "category": category
                        })

            # 竞争强度评估
            if len(detected_competitors) == 0:
                competition_level = "low"
                competition_score = 2  # 1-10分，越低越好
            elif len(detected_competitors) <= 2:
                competition_level = "medium"
                competition_score = 5
            else:
                competition_level = "high"
                competition_score = 8

            opportunity_data["competition_analysis"] = {
                "detected_competitors": detected_competitors,
                "competition_level": competition_level,
                "competition_score": competition_score,
                "differentiation_opportunity": self._identify_differentiation_opportunity(opportunity_data, detected_competitors)
            }

        except Exception as e:
            logger.error(f"Failed to analyze competition: {e}")

    def _identify_differentiation_opportunity(self, opportunity_data: Dict[str, Any], competitors: List[Dict[str, Any]]) -> str:
        """识别差异化机会"""
        try:
            # 简单的差异化分析
            if not competitors:
                return "No direct competitors detected"

            opportunity_name = opportunity_data.get("opportunity_name", "").lower()

            # 检查是否有细分市场机会
            niche_indicators = ["for startups", "for indie", "for solo", "for small", "simple", "lightweight", "minimal"]
            for indicator in niche_indicators:
                if indicator in opportunity_name:
                    return f"Niche focus on {indicator}"

            return "Generic space, needs clear differentiation"

        except Exception as e:
            logger.error(f"Failed to identify differentiation opportunity: {e}")
            return "Unable to determine"

    def _score_with_llm(self, opportunity_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """使用LLM进行可行性评分"""
        try:
            # 构建机会描述文本
            description = f"""
Opportunity: {opportunity_data.get('opportunity_name', '')}

Description: {opportunity_data.get('description', '')}

Target Users: {opportunity_data.get('target_users', '')}

Current Tools: {opportunity_data.get('current_tools', '')}

Missing Capability: {opportunity_data.get('missing_capability', '')}

Why Existing Tools Fail: {opportunity_data.get('why_existing_fail', '')}

Market Analysis: {opportunity_data.get('market_analysis', {})}

Competition Analysis: {opportunity_data.get('competition_analysis', {})}
"""

            # 调用LLM进行评分
            response = llm_client.score_viability(description)

            scoring_result = response["content"]

            return scoring_result

        except Exception as e:
            logger.error(f"Failed to score with LLM: {e}")
            return None

    def _combine_scores(self, llm_scores: Dict[str, Any], opportunity_data: Dict[str, Any]) -> Dict[str, Any]:
        """结合LLM评分和规则评分（Phase 3：添加trust_level加权）"""
        try:
            # 获取聚类信息和信任度
            cluster_info = opportunity_data.get("cluster_info", {})
            pain_events = cluster_info.get("pain_events", [])
            pain_event_ids = [pe['id'] for pe in pain_events]

            cluster_trust_level = self._calculate_cluster_trust_level(pain_event_ids)

            # LLM评分（主观维度）
            llm_component_scores = llm_scores.get("scores", {})
            llm_total_score = llm_scores.get("total_score", 0.0)

            # 数据驱动评分
            data_driven_scores = {
                "pain_frequency": self._calculate_pain_frequency_score_data_driven(pain_event_ids),
                "market_size": self._calculate_market_size_score(pain_event_ids),
            }

            # 规则评分
            market_analysis = opportunity_data.get("market_analysis", {})
            competition_analysis = opportunity_data.get("competition_analysis", {})

            # 竞争评分 (0-10, 越低越好)
            competition_score = competition_analysis.get("competition_score", 8)
            competition_normalized = max(10 - competition_score, 1)  # 转换为越高越好

            # 聚类大小评分 (0-10)
            cluster_size = cluster_info.get("cluster_size", 0)
            cluster_score = min(cluster_size, 10)

            # 综合评分计算
            final_component_scores = {
                **data_driven_scores,  # 数据驱动评分
                "clear_buyer": llm_component_scores.get("pain_frequency", 5),  # LLM评分
                "mvp_buildable": llm_component_scores.get("mvp_buildable", 5),
                "crowded_market": competition_normalized,
                "integration": llm_component_scores.get("integration", 5),
                "cluster_strength": cluster_score,
                "trust_level": cluster_trust_level * 10  # 转换为0-10分
            }

            # 计算加权总分
            weights = {
                "pain_frequency": 0.15,
                "market_size": 0.15,
                "clear_buyer": 0.15,
                "mvp_buildable": 0.20,
                "crowded_market": 0.15,
                "integration": 0.10,
                "cluster_strength": 0.10
            }

            weighted_total = sum(
                final_component_scores[component] * weight
                for component, weight in weights.items()
            )

            # 方案B：软性trust_level惩罚（而非硬性乘数）
            # trust_level ≥ 0.7: 不惩罚
            # 0.5 ≤ trust_level < 0.7: 0.85倍惩罚
            # trust_level < 0.5: 0.7倍惩罚
            if cluster_trust_level >= 0.7:
                trust_adjusted_total = weighted_total  # 不惩罚
            elif cluster_trust_level >= 0.5:
                trust_adjusted_total = weighted_total * 0.85  # 轻度惩罚
            else:
                trust_adjusted_total = weighted_total * 0.7  # 中度惩罚

            # 确保分数在0-10范围内
            final_total_score = min(max(trust_adjusted_total, 0), 10)

            # 生成杀手风险（包含trust_level风险）
            killer_risks = self._generate_killer_risks(final_component_scores, opportunity_data, cluster_trust_level)

            return {
                "component_scores": final_component_scores,
                "total_score": final_total_score,
                "raw_total_score": weighted_total,  # 加权前的原始分数
                "trust_level": cluster_trust_level,
                "llm_total_score": llm_total_score,
                "killer_risks": killer_risks,
                "recommendation": self._generate_recommendation(final_total_score, killer_risks)
            }

        except Exception as e:
            logger.error(f"Failed to combine scores: {e}")
            return {"total_score": 0.0, "component_scores": {}, "killer_risks": [], "recommendation": "Error in scoring"}

    def _generate_killer_risks(self, component_scores: Dict[str, Any], opportunity_data: Dict[str, Any], trust_level: float = 0.5) -> List[str]:
        """生成杀手风险（Phase 3：考虑trust_level）"""
        risks = []

        # 基于分项评分生成风险
        if component_scores.get("market_size", 0) < 4:
            risks.append("Small market size may not sustain business")

        if component_scores.get("crowded_market", 0) < 4:
            risks.append("Highly competitive market with established players")

        if component_scores.get("mvp_buildable", 0) < 4:
            risks.append("Technical complexity too high for solo founder")

        if component_scores.get("clear_buyer", 0) < 4:
            risks.append("Unclear who will pay for this solution")

        if component_scores.get("pain_frequency", 0) < 4:
            risks.append("Problem may not be frequent enough to drive adoption")

        if component_scores.get("integration", 0) < 4:
            risks.append("Difficult integration with existing workflows")

        # Phase 3: 新增trust_level风险
        if trust_level < 0.5:
            risks.append(f"Low trust data sources (trust_level: {trust_level:.2f}) - signals may not be reliable")
        elif trust_level < 0.7:
            risks.append(f"Moderate trust data sources (trust_level: {trust_level:.2f}) - validate with additional research")

        # 基于竞争分析生成风险
        competition_analysis = opportunity_data.get("competition_analysis", {})
        if competition_analysis.get("competition_level") == "high":
            risks.append("Direct competition with well-funded incumbents")

        # 基于市场分析生成风险
        market_analysis = opportunity_data.get("market_analysis", {})
        if market_analysis.get("market_tier") == "niche":
            risks.append("Very niche market may limit growth potential")

        return risks[:3]  # 最多返回3个风险

    def _generate_recommendation(self, total_score: float, killer_risks: List[str]) -> str:
        """生成建议"""
        if total_score >= 8.0:
            return "pursue - Strong opportunity with high potential"
        elif total_score >= 6.5:
            return "pursue - Good opportunity with manageable risks"
        elif total_score >= 5.0:
            return "modify - Viable with some adjustments needed"
        elif total_score >= 3.5:
            return "research - Needs more validation before pursuing"
        else:
            return "abandon - Too many risks or unclear value proposition"

    def _update_opportunity_in_database(self, opportunity_id: int, scoring_result: Dict[str, Any]) -> bool:
        """更新数据库中的机会评分（Phase 3：支持raw_total_score、trust_level和版本字段）"""
        try:
            from datetime import datetime

            with db.get_connection("clusters") as conn:
                # 检查是否存在新列
                cursor = conn.execute("PRAGMA table_info(opportunities)")
                existing_columns = {row['name'] for row in cursor.fetchall()}

                # 获取当前opportunity的version
                cursor.execute("SELECT current_version, rescore_count FROM opportunities WHERE id = ?", (opportunity_id,))
                current_opp = cursor.fetchone()
                current_version = current_opp['current_version'] if current_opp else 1
                rescore_count = current_opp['rescore_count'] if current_opp else 0

                # 基础更新语句（适用于旧schema）
                update_sql = """
                    UPDATE opportunities
                    SET pain_frequency_score = ?,
                        market_size_score = ?,
                        mvp_complexity_score = ?,
                        competition_risk_score = ?,
                        integration_complexity_score = ?,
                        total_score = ?,
                        killer_risks = ?,
                        recommendation = ?
                """

                update_values = [
                    scoring_result["component_scores"].get("pain_frequency", 0),
                    scoring_result["component_scores"].get("market_size", 0),
                    scoring_result["component_scores"].get("mvp_buildable", 0),
                    scoring_result["component_scores"].get("crowded_market", 0),
                    scoring_result["component_scores"].get("integration", 0),
                    scoring_result["total_score"],
                    json.dumps(scoring_result["killer_risks"]),
                    scoring_result.get("recommendation", ""),
                ]

                # 如果存在新列，添加到更新语句
                if "raw_total_score" in existing_columns:
                    update_sql = update_sql.rstrip() + ",\nraw_total_score = ?"
                    update_values.append(scoring_result.get("raw_total_score", scoring_result["total_score"]))

                if "trust_level" in existing_columns:
                    update_sql = update_sql.rstrip() + ",\ntrust_level = ?"
                    update_values.append(scoring_result.get("trust_level", 0.5))

                if "scoring_breakdown" in existing_columns:
                    update_sql = update_sql.rstrip() + ",\nscoring_breakdown = ?"
                    breakdown = {
                        "component_scores": scoring_result["component_scores"],
                        "raw_total_score": scoring_result.get("raw_total_score", scoring_result["total_score"]),
                        "trust_level": scoring_result.get("trust_level", 0.5)
                    }
                    update_values.append(json.dumps(breakdown))

                # Phase 3: 添加版本和时间戳字段
                if "scored_at" in existing_columns:
                    update_sql = update_sql.rstrip() + ",\nscored_at = ?"
                    update_values.append(datetime.now().isoformat())

                if "current_version" in existing_columns:
                    update_sql = update_sql.rstrip() + ",\ncurrent_version = ?"
                    update_values.append(current_version + 1)

                if "last_rescored_at" in existing_columns:
                    update_sql = update_sql.rstrip() + ",\nlast_rescored_at = ?"
                    update_values.append(datetime.now().isoformat())

                if "rescore_count" in existing_columns:
                    update_sql = update_sql.rstrip() + ",\nrescore_count = ?"
                    update_values.append(rescore_count + 1)

                update_sql = update_sql.rstrip() + "\nWHERE id = ?"
                update_values.append(opportunity_id)

                conn.execute(update_sql, tuple(update_values))
                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Failed to update opportunity in database: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def score_opportunities(
        self,
        limit: int = 100,
        skip_filtering: bool = False,
        batch_id: str = None,
        clusters_to_update: List[int] = None
    ) -> Dict[str, Any]:
        """为机会评分（Phase 3改进：filtering在LLM评分之后）

        Args:
            limit: 最多评分的机会数量
            skip_filtering: 是否跳过filtering rules（用于重新评分已存在的opportunities）
            batch_id: 评分批次ID（用于追踪）
            clusters_to_update: 指定需要重新评分的cluster IDs（None表示评分所有未评分的）

        Returns:
            评分结果统计
        """
        logger.info(f"Scoring up to {limit} opportunities (skip_filtering={skip_filtering})")

        if batch_id:
            logger.info(f"Batch ID: {batch_id}")

        if clusters_to_update:
            logger.info(f"Re-scoring {len(clusters_to_update)} specified clusters")

        start_time = time.time()

        try:
            # 获取需要评分的机会
            if clusters_to_update:
                # 为指定的clusters重新评分（包括已评分的）
                with db.get_connection("clusters") as conn:
                    placeholders = ','.join('?' for _ in clusters_to_update)
                    cursor = conn.execute(f"""
                        SELECT * FROM opportunities
                        WHERE cluster_id IN ({placeholders})
                        ORDER BY cluster_id DESC
                    """, clusters_to_update)
                    opportunities = [dict(row) for row in cursor.fetchall()]
            else:
                # 默认：获取未评分的机会
                with db.get_connection("clusters") as conn:
                    cursor = conn.execute("""
                        SELECT * FROM opportunities
                        WHERE total_score = 0 OR total_score IS NULL
                        ORDER BY cluster_id DESC
                        LIMIT ?
                    """, (limit,))
                    opportunities = [dict(row) for row in cursor.fetchall()]

            if not opportunities:
                logger.info("No opportunities found to score")
                return {"opportunities_scored": 0, "viable_opportunities": 0}

            logger.info(f"Found {len(opportunities)} opportunities to score")

            # ⚠️ Phase 3 关键改动：移除这里的filtering，改到LLM评分之后
            # 之前：filtering在LLM评分之前，阻止了新clusters被评分
            # 现在：先让所有opportunities被LLM评分，然后应用filtering标记
            processed_clusters = set()

            scored_opportunities = []
            viable_count = 0
            good_count = 0
            excellent_count = 0

            for i, opportunity in enumerate(opportunities):
                logger.info(f"Scoring opportunity {i+1}/{len(opportunities)}: {opportunity['opportunity_name']}")

                try:
                    # 增强机会数据
                    enhanced_opportunity = self._enhance_opportunity_data(opportunity)

                    # LLM评分
                    llm_result = self._score_with_llm(enhanced_opportunity)

                    if llm_result:
                        # 结合评分
                        final_scores = self._combine_scores(llm_result, enhanced_opportunity)

                        # 更新数据库
                        if self._update_opportunity_in_database(opportunity["id"], final_scores):
                            # 统计
                            total_score = final_scores["total_score"]
                            if total_score >= 8.5:
                                excellent_count += 1
                            elif total_score >= 7.0:
                                good_count += 1
                            elif total_score >= 5.0:
                                viable_count += 1

                            opportunity_summary = {
                                "opportunity_id": opportunity["id"],
                                "opportunity_name": opportunity["opportunity_name"],
                                "total_score": total_score,
                                "recommendation": final_scores["recommendation"],
                                "killer_risks": final_scores["killer_risks"]
                            }

                            scored_opportunities.append(opportunity_summary)

                            logger.info(f"Scored: {opportunity['opportunity_name']} - {total_score:.1f}/10 ({final_scores['recommendation']})")
                        else:
                            logger.error(f"Failed to update opportunity {opportunity['id']} in database")

                except Exception as e:
                    logger.error(f"Failed to score opportunity {opportunity['opportunity_name']}: {e}")
                    continue

                # 添加延迟避免API限制
                time.sleep(2)

            # ⚠️ Phase 3 关键改动：LLM评分完成后，应用filtering rules（如果启用）
            # 此时所有opportunities都已经有LLM评分了
            if not skip_filtering and self.filtering_rules.get("enabled", False):
                logger.info("Applying filtering rules after LLM scoring...")
                # 获取所有已评分的opportunities
                scored_opportunity_ids = [opp["opportunity_id"] for opp in scored_opportunities]

                # 重新获取完整的opportunity数据（包含评分结果）
                with db.get_connection("clusters") as conn:
                    placeholders = ','.join('?' for _ in scored_opportunity_ids)
                    cursor = conn.execute(f"""
                        SELECT * FROM opportunities
                        WHERE id IN ({placeholders})
                    """, scored_opportunity_ids)
                    filtered_opportunities = [dict(row) for row in cursor.fetchall()]

                # 应用filtering rules（只更新标记，不删除）
                filtered_count = 0
                for opp in filtered_opportunities:
                    cluster_id = opp["cluster_id"]
                    if cluster_id in processed_clusters:
                        continue

                    # 获取cluster数据
                    cursor = conn.execute("""
                        SELECT * FROM clusters WHERE id = ?
                    """, (cluster_id,))
                    cluster_data = dict(cursor.fetchone()) if cursor.rowcount > 0 else None

                    if cluster_data:
                        should_skip, skip_reason = self.should_skip_solution_design(cluster_data)
                        if should_skip:
                            # 更新recommendation为"abandon"，但保留评分结果
                            self._update_opportunities_recommendation(
                                cluster_id, "abandon", skip_reason
                            )
                            processed_clusters.add(cluster_id)
                            filtered_count += 1
                            logger.info(f"  Filtered: {opp['opportunity_name']} - {skip_reason}")
                        else:
                            processed_clusters.add(cluster_id)

                logger.info(f"Filtering applied: {filtered_count} opportunities marked as abandon")

            # 更新统计信息
            processing_time = time.time() - start_time
            self.stats["total_opportunities_scored"] = len(scored_opportunities)
            self.stats["viable_opportunities"] = viable_count
            self.stats["good_opportunities"] = good_count
            self.stats["excellent_opportunities"] = excellent_count
            self.stats["processing_time"] = processing_time

            if scored_opportunities:
                self.stats["avg_total_score"] = sum(opp["total_score"] for opp in scored_opportunities) / len(scored_opportunities)

            logger.info(f"""
=== Viability Scoring Summary ===
Opportunities scored: {len(scored_opportunities)}
Viable opportunities (5.0+): {viable_count}
Good opportunities (7.0+): {good_count}
Excellent opportunities (8.5+): {excellent_count}
Average score: {self.stats['avg_total_score']:.2f}
Processing time: {processing_time:.2f}s
""")

            return {
                "opportunities_scored": len(scored_opportunities),
                "viable_opportunities": viable_count,
                "good_opportunities": good_count,
                "excellent_opportunities": excellent_count,
                "scored_opportunities": scored_opportunities,
                "scoring_stats": self.get_statistics()
            }

        except Exception as e:
            logger.error(f"Failed to score opportunities: {e}")
            raise

    def get_top_opportunities(self, min_score: float = 5.0, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最高分的机会"""
        try:
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT o.*, c.cluster_name, c.cluster_size
                    FROM opportunities o
                    JOIN clusters c ON o.cluster_id = c.id
                    WHERE o.total_score >= ?
                    ORDER BY o.total_score DESC
                    LIMIT ?
                """, (min_score, limit))
                opportunities = [dict(row) for row in cursor.fetchall()]

            return opportunities

        except Exception as e:
            logger.error(f"Failed to get top opportunities: {e}")
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """获取评分统计信息"""
        stats = self.stats.copy()

        if stats["total_opportunities_scored"] > 0:
            stats["viable_rate"] = stats["viable_opportunities"] / stats["total_opportunities_scored"]
            stats["good_rate"] = stats["good_opportunities"] / stats["total_opportunities_scored"]
            stats["excellent_rate"] = stats["excellent_opportunities"] / stats["total_opportunities_scored"]
            stats["processing_rate"] = stats["total_opportunities_scored"] / max(stats["processing_time"], 1)
        else:
            stats["viable_rate"] = 0
            stats["good_rate"] = 0
            stats["excellent_rate"] = 0
            stats["processing_rate"] = 0

        return stats

    def reset_statistics(self):
        """重置统计信息"""
        self.stats = {
            "total_opportunities_scored": 0,
            "viable_opportunities": 0,
            "good_opportunities": 0,
            "excellent_opportunities": 0,
            "processing_time": 0.0,
            "avg_total_score": 0.0
        }

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Score opportunity viability for solo founders")
    parser.add_argument("--limit", type=int, default=100, help="Limit number of opportunities to score")
    parser.add_argument("--min-score", type=float, default=5.0, help="Minimum score for top opportunities")
    parser.add_argument("--list", action="store_true", help="List top scored opportunities")
    args = parser.parse_args()

    try:
        logger.info("Starting viability scoring...")

        scorer = ViabilityScorer()

        if args.list:
            # 列出最高分的机会
            top_opportunities = scorer.get_top_opportunities(min_score=args.min_score)
            print(json.dumps(top_opportunities, indent=2, default=str))

        else:
            # 为机会评分
            result = scorer.score_opportunities(limit=args.limit)

            logger.info(f"""
=== Viability Scoring Complete ===
Opportunities scored: {result['opportunities_scored']}
Viable opportunities: {result['viable_opportunities']}
Good opportunities: {result['good_opportunities']}
Excellent opportunities: {result['excellent_opportunities']}
Scoring stats: {result['scoring_stats']}
""")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()