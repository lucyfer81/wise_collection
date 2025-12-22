"""
Map Opportunity module for Reddit Pain Point Finder
机会映射模块 - 从痛点聚类中发现工具机会
"""
import json
import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from utils.llm_client import llm_client
from utils.db import db

logger = logging.getLogger(__name__)

class OpportunityMapper:
    """机会映射器"""

    def __init__(self):
        """初始化机会映射器"""
        self.stats = {
            "total_clusters_processed": 0,
            "opportunities_identified": 0,
            "viable_opportunities": 0,
            "processing_time": 0.0,
            "avg_opportunity_score": 0.0
        }

    def _enrich_cluster_data(self, cluster_data: Dict[str, Any]) -> Dict[str, Any]:
        """丰富聚类数据"""
        try:
            # 获取聚类中的痛点事件详情
            pain_event_ids = json.loads(cluster_data.get("pain_event_ids", "[]"))

            pain_events = []
            with db.get_connection("pain") as conn:
                for event_id in pain_event_ids:
                    cursor = conn.execute("""
                        SELECT * FROM pain_events WHERE id = ?
                    """, (event_id,))
                    event_data = cursor.fetchone()
                    if event_data:
                        pain_events.append(dict(event_data))

            # 添加原始帖子信息
            for event in pain_events:
                with db.get_connection("filtered") as conn:
                    cursor = conn.execute("""
                        SELECT title, subreddit, score, num_comments, pain_score
                        FROM filtered_posts WHERE id = ?
                    """, (event["post_id"],))
                    post_data = cursor.fetchone()
                    if post_data:
                        event.update(dict(post_data))

            # 构建丰富的聚类摘要
            enriched_cluster = {
                "cluster_id": cluster_data["id"],
                "cluster_name": cluster_data["cluster_name"],
                "cluster_description": cluster_data["cluster_description"],
                "cluster_size": cluster_data["cluster_size"],
                "workflow_confidence": cluster_data.get("workflow_confidence", 0.0),
                "pain_events": pain_events,
                "created_at": cluster_data["created_at"]
            }

            # 分析聚类特征
            self._analyze_cluster_characteristics(enriched_cluster)

            return enriched_cluster

        except Exception as e:
            logger.error(f"Failed to enrich cluster data: {e}")
            return cluster_data

    def _analyze_cluster_characteristics(self, cluster_data: Dict[str, Any]):
        """分析聚类特征"""
        try:
            pain_events = cluster_data.get("pain_events", [])

            if not pain_events:
                return

            # 统计子版块分布
            subreddits = {}
            for event in pain_events:
                subreddit = event.get("subreddit", "unknown")
                subreddits[subreddit] = subreddits.get(subreddit, 0) + 1

            # 统计提到的工具
            mentioned_tools = []
            for event in pain_events:
                tools = event.get("mentioned_tools", [])
                if isinstance(tools, list):
                    mentioned_tools.extend(tools)
                elif isinstance(tools, str):
                    mentioned_tools.append(tools)

            tool_counts = {}
            for tool in mentioned_tools:
                if tool:
                    tool_counts[tool] = tool_counts.get(tool, 0) + 1

            # 统计情绪信号
            emotional_signals = {}
            for event in pain_events:
                signal = event.get("emotional_signal", "")
                if signal:
                    emotional_signals[signal] = emotional_signals.get(signal, 0) + 1

            # 统计频率分数
            frequency_scores = [event.get("frequency_score", 5) for event in pain_events if event.get("frequency_score")]
            avg_frequency_score = sum(frequency_scores) / len(frequency_scores) if frequency_scores else 5.0

            # 提取代表性问题
            problems = [event.get("problem", "") for event in pain_events if event.get("problem")]
            unique_problems = list(set(problems))

            # 提取工作方式
            workarounds = [event.get("current_workaround", "") for event in pain_events if event.get("current_workaround")]
            unique_workarounds = [w for w in set(workarounds) if w]

            # 更新聚类数据
            cluster_data.update({
                "subreddit_distribution": subreddits,
                "mentioned_tools": tool_counts,
                "emotional_signals": emotional_signals,
                "avg_frequency_score": avg_frequency_score,
                "representative_problems": unique_problems[:10],  # 最多10个
                "representative_workarounds": unique_workarounds[:5],  # 最多5个
                "total_pain_score": sum(event.get("post_pain_score", 0) for event in pain_events)
            })

        except Exception as e:
            logger.error(f"Failed to analyze cluster characteristics: {e}")

    def _map_opportunity_with_llm(self, cluster_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """使用LLM映射机会"""
        try:
            # 调用LLM进行机会映射
            response = llm_client.map_opportunity(cluster_data)

            opportunity_data = response["content"]

            # 检查是否找到机会
            if "opportunity" in opportunity_data and opportunity_data["opportunity"]:
                # 为了保持一致性，包装在content中
                return {"content": opportunity_data}
            else:
                logger.info(f"No viable opportunity found for cluster {cluster_data['cluster_name']}")
                return None

        except Exception as e:
            logger.error(f"Failed to map opportunity with LLM: {e}")
            return None

    def _evaluate_opportunity_quality(self, opportunity_data: Dict[str, Any], cluster_data: Dict[str, Any]) -> Dict[str, Any]:
        """评估机会质量"""
        try:
            # 处理可能的数据结构差异
            if "content" in opportunity_data:
                opportunity = opportunity_data["content"].get("opportunity", {})
            else:
                opportunity = opportunity_data.get("opportunity", {})

            if not opportunity:
                return {"is_viable": False, "reason": "No opportunity data"}

            # 基础质量检查
            required_fields = ["name", "description", "target_users"]
            for field in required_fields:
                if not opportunity.get(field):
                    return {"is_viable": False, "reason": f"Missing required field: {field}"}

            # 质量评分
            quality_score = 0.0
            reasons = []

            # 痛点频率 (20%)
            pain_frequency = opportunity.get("pain_frequency", 0)
            if pain_frequency >= 7:
                quality_score += 0.2
                reasons.append("High pain frequency")
            elif pain_frequency >= 5:
                quality_score += 0.1
                reasons.append("Medium pain frequency")

            # 市场规模 (20%)
            market_size = opportunity.get("market_size", 0)
            if market_size >= 7:
                quality_score += 0.2
                reasons.append("Large market size")
            elif market_size >= 5:
                quality_score += 0.1
                reasons.append("Medium market size")

            # MVP复杂度 (25%) - 越低越好
            mvp_complexity = opportunity.get("mvp_complexity", 10)
            if mvp_complexity <= 4:
                quality_score += 0.25
                reasons.append("Simple MVP")
            elif mvp_complexity <= 6:
                quality_score += 0.15
                reasons.append("Moderate MVP complexity")

            # 竞争风险 (20%) - 越低越好
            competition_risk = opportunity.get("competition_risk", 10)
            if competition_risk <= 4:
                quality_score += 0.2
                reasons.append("Low competition")
            elif competition_risk <= 6:
                quality_score += 0.1
                reasons.append("Moderate competition")

            # 集成难度 (15%) - 越低越好
            integration_complexity = opportunity.get("integration_complexity", 10)
            if integration_complexity <= 5:
                quality_score += 0.15
                reasons.append("Easy integration")
            elif integration_complexity <= 7:
                quality_score += 0.08
                reasons.append("Moderate integration")

            # 聚类大小加分
            cluster_size = cluster_data.get("cluster_size", 0)
            if cluster_size >= 10:
                quality_score += 0.1
                reasons.append("Large cluster size")

            # 总分范围：0-1
            total_score = min(quality_score, 1.0)

            # 判断是否可行
            is_viable = total_score >= 0.4  # 40%以上认为可行

            return {
                "is_viable": is_viable,
                "quality_score": total_score,
                "quality_reasons": reasons,
                "detailed_scores": {
                    "pain_frequency": pain_frequency,
                    "market_size": market_size,
                    "mvp_complexity": mvp_complexity,
                    "competition_risk": competition_risk,
                    "integration_complexity": integration_complexity
                }
            }

        except Exception as e:
            logger.error(f"Failed to evaluate opportunity quality: {e}")
            return {"is_viable": False, "reason": f"Evaluation error: {e}"}

    def _process_aligned_cluster(self, aligned_cluster: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理对齐问题聚类"""
        try:
            # 获取支持聚类信息
            supporting_clusters = db.get_clusters_for_aligned_problem(
                aligned_cluster['cluster_name']
            )

            # 创建多源验证的机会
            opportunity_data = {
                "content": {
                    "opportunity": {
                        "name": f"Multi-Source: {aligned_cluster['centroid_summary'][:50]}...",
                        "description": f"This opportunity is validated by multiple communities across different platforms. Core problem: {aligned_cluster['centroid_summary']}",
                        "target_users": f"Users from {len(supporting_clusters)} different communities",
                        "pain_frequency": 9,  # High frequency due to multi-source validation
                        "market_size": 9,  # Large market due to cross-platform demand
                        "mvp_complexity": 6,  # Moderate complexity
                        "competition_risk": 4,  # Lower risk due to validated demand
                        "integration_complexity": 5,  # Moderate integration complexity
                        "source_diversity": len(supporting_clusters),
                        "platform_insights": self._extract_platform_insights(supporting_clusters),
                        "current_tools": self._aggregate_current_tools(supporting_clusters),
                        "missing_capability": aligned_cluster['centroid_summary']
                    }
                }
            }

            logger.info(f"Created multi-source opportunity for aligned problem {aligned_cluster['cluster_name']}")
            return opportunity_data

        except Exception as e:
            logger.error(f"Failed to process aligned cluster {aligned_cluster['cluster_name']}: {e}")
            return None

    def _extract_platform_insights(self, supporting_clusters: List[Dict]) -> List[str]:
        """提取平台洞察"""
        insights = []
        for cluster in supporting_clusters:
            source_type = cluster.get('source_type', 'unknown')
            summary = cluster.get('centroid_summary', '')[:100]
            insights.append(f"{source_type}: {summary}")
        return insights

    def _aggregate_current_tools(self, supporting_clusters: List[Dict]) -> List[str]:
        """聚合当前工具"""
        tools = set()
        for cluster in supporting_clusters:
            common_pain = cluster.get('common_pain', '')
            # 简单的工具提取逻辑
            if 'slack' in common_pain.lower():
                tools.add('Slack')
            if 'email' in common_pain.lower():
                tools.add('Email')
            if 'discord' in common_pain.lower():
                tools.add('Discord')
        return list(tools)

    def _save_opportunity_to_database(self, cluster_id: int, opportunity_data: Dict[str, Any], quality_result: Dict[str, Any]) -> Optional[int]:
        """保存机会到数据库"""
        try:
            # 处理可能的数据结构差异
            if "content" in opportunity_data:
                content = opportunity_data["content"]
                opportunity = content.get("opportunity", {})
                current_tools = content.get("current_tools", [])
                missing_capability = content.get("missing_capability", "")
                why_existing_fail = content.get("why_existing_fail", "")
            else:
                opportunity = opportunity_data.get("opportunity", {})
                current_tools = opportunity_data.get("current_tools", [])
                missing_capability = opportunity_data.get("missing_capability", "")
                why_existing_fail = opportunity_data.get("why_existing_fail", "")

            # 准备机会数据
            opportunity_record = {
                "cluster_id": cluster_id,
                "opportunity_name": opportunity.get("name", ""),
                "description": opportunity.get("description", ""),
                "current_tools": json.dumps(current_tools),
                "missing_capability": missing_capability,
                "why_existing_fail": why_existing_fail,
                "target_users": opportunity.get("target_users", ""),
                "pain_frequency_score": opportunity.get("pain_frequency", 0),
                "market_size_score": opportunity.get("market_size", 0),
                "mvp_complexity_score": opportunity.get("mvp_complexity", 0),
                "competition_risk_score": opportunity.get("competition_risk", 0),
                "integration_complexity_score": opportunity.get("integration_complexity", 0),
                "total_score": quality_result["quality_score"],
                "killer_risks": json.dumps([]),  # 稍后在viability scoring中填充
                "recommendation": ""  # 稍后在viability scoring中填充
            }

            opportunity_id = db.insert_opportunity(opportunity_record)
            return opportunity_id

        except Exception as e:
            logger.error(f"Failed to save opportunity to database: {e}")
            return None

    def map_opportunities_for_clusters(self, limit: int = 50) -> Dict[str, Any]:
        """为聚类映射机会"""
        logger.info(f"Mapping opportunities for up to {limit} clusters")

        start_time = time.time()

        try:
            # 获取聚类（包括对齐的虚拟聚类）
            clusters = db.get_clusters_for_opportunity_mapping()

            # 如果有指定限制，截取
            if limit and len(clusters) > limit:
                clusters = clusters[:limit]

            if not clusters:
                logger.info("No clusters found for opportunity mapping")
                return {"opportunities_identified": 0, "clusters_processed": 0}

            logger.info(f"Processing {len(clusters)} clusters for opportunity mapping")

            opportunities_created = []
            viable_opportunities = 0

            for i, cluster in enumerate(clusters):
                logger.info(f"Processing cluster {i+1}/{len(clusters)}: {cluster['cluster_name']}")

                try:
                    # 检查是否是对齐的虚拟聚类
                    if cluster.get('source_type') == 'aligned':
                        # 处理对齐问题聚类
                        opportunity_data = self._process_aligned_cluster(cluster)
                    else:
                        # 原始聚类处理
                        enriched_cluster = self._enrich_cluster_data(cluster)
                        opportunity_data = self._map_opportunity_with_llm(enriched_cluster)

                    if opportunity_data:
                        # 评估机会质量
                        if cluster.get('source_type') == 'aligned':
                            # 对齐聚类使用预设的高质量评分
                            quality_result = {
                                "is_viable": True,
                                "quality_score": 0.95,  # 高质量评分
                                "quality_reasons": [
                                    "Multi-source validation",
                                    "Large market size",
                                    "High pain frequency",
                                    "Moderate competition"
                                ]
                            }
                        else:
                            # 原始聚类使用标准评估
                            quality_result = self._evaluate_opportunity_quality(opportunity_data, enriched_cluster)

                        if quality_result["is_viable"]:
                            # 保存到数据库
                            cluster_id = cluster.get("id", 0)  # 对齐聚类可能没有id
                            opportunity_id = self._save_opportunity_to_database(
                                cluster_id, opportunity_data, quality_result
                            )

                            if opportunity_id:
                                opportunity_summary = {
                                    "opportunity_id": opportunity_id,
                                    "cluster_id": cluster_id,
                                    "cluster_name": cluster["cluster_name"],
                                    "opportunity_name": opportunity_data["content"]["opportunity"]["name"],
                                    "opportunity_description": opportunity_data["content"]["opportunity"]["description"],
                                    "quality_score": quality_result["quality_score"],
                                    "quality_reasons": quality_result["quality_reasons"]
                                }

                                opportunities_created.append(opportunity_summary)
                                viable_opportunities += 1

                                logger.info(f"Created opportunity: {opportunity_data['content']['opportunity']['name']} (Score: {quality_result['quality_score']:.2f})")
                        else:
                            logger.debug(f"Opportunity not viable: {quality_result.get('reason', 'Unknown')}")
                    else:
                        logger.debug(f"No opportunity found for cluster {cluster['cluster_name']}")

                except Exception as e:
                    logger.error(f"Failed to process cluster {cluster['cluster_name']}: {e}")
                    continue

                # 添加延迟避免API限制
                time.sleep(2)

            # 更新统计信息
            processing_time = time.time() - start_time
            self.stats["total_clusters_processed"] = len(clusters)
            self.stats["opportunities_identified"] = len(opportunities_created)
            self.stats["viable_opportunities"] = viable_opportunities
            self.stats["processing_time"] = processing_time

            if opportunities_created:
                self.stats["avg_opportunity_score"] = sum(opp["quality_score"] for opp in opportunities_created) / len(opportunities_created)

            logger.info(f"""
=== Opportunity Mapping Summary ===
Clusters processed: {len(clusters)}
Opportunities identified: {len(opportunities_created)}
Viable opportunities: {viable_opportunities}
Average opportunity score: {self.stats['avg_opportunity_score']:.2f}
Processing time: {processing_time:.2f}s
""")

            return {
                "opportunities_created": len(opportunities_created),
                "viable_opportunities": viable_opportunities,
                "clusters_processed": len(clusters),
                "opportunity_details": opportunities_created,
                "mapping_stats": self.get_statistics()
            }

        except Exception as e:
            logger.error(f"Failed to map opportunities: {e}")
            raise

    def get_opportunities_summary(self, min_score: float = 0.0, limit: int = 50) -> List[Dict[str, Any]]:
        """获取机会摘要"""
        try:
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT o.*, c.cluster_name, c.cluster_description, c.cluster_size
                    FROM opportunities o
                    JOIN clusters c ON o.cluster_id = c.id
                    WHERE o.total_score >= ?
                    ORDER BY o.total_score DESC
                    LIMIT ?
                """, (min_score, limit))
                opportunities = [dict(row) for row in cursor.fetchall()]

            return opportunities

        except Exception as e:
            logger.error(f"Failed to get opportunities summary: {e}")
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """获取映射统计信息"""
        stats = self.stats.copy()

        if stats["total_clusters_processed"] > 0:
            stats["opportunity_rate"] = stats["opportunities_identified"] / stats["total_clusters_processed"]
            stats["viable_rate"] = stats["viable_opportunities"] / stats["total_clusters_processed"]
            stats["processing_rate"] = stats["total_clusters_processed"] / max(stats["processing_time"], 1)
        else:
            stats["opportunity_rate"] = 0
            stats["viable_rate"] = 0
            stats["processing_rate"] = 0

        return stats

    def reset_statistics(self):
        """重置统计信息"""
        self.stats = {
            "total_clusters_processed": 0,
            "opportunities_identified": 0,
            "viable_opportunities": 0,
            "processing_time": 0.0,
            "avg_opportunity_score": 0.0
        }

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Map opportunities from pain point clusters")
    parser.add_argument("--limit", type=int, default=50, help="Limit number of clusters to process")
    parser.add_argument("--min-score", type=float, default=0.0, help="Minimum opportunity score")
    parser.add_argument("--list", action="store_true", help="List existing opportunities")
    args = parser.parse_args()

    try:
        logger.info("Starting opportunity mapping...")

        mapper = OpportunityMapper()

        if args.list:
            # 列出现有机会
            opportunities = mapper.get_opportunities_summary(min_score=args.min_score)
            print(json.dumps(opportunities, indent=2, default=str))

        else:
            # 映射新机会
            result = mapper.map_opportunities_for_clusters(limit=args.limit)

            logger.info(f"""
=== Opportunity Mapping Complete ===
Opportunities created: {result['opportunities_created']}
Viable opportunities: {result['viable_opportunities']}
Clusters processed: {result['clusters_processed']}
Mapping stats: {result['mapping_stats']}
""")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()