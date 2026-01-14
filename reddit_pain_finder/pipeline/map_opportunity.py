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

    def _validate_opportunity_data(self, opportunity_data: Dict[str, Any]) -> Dict[str, Any]:
        """验证机会数据（Phase 3：只做基础验证，不评分）"""
        try:
            # 处理可能的数据结构差异
            if "content" in opportunity_data:
                opportunity = opportunity_data["content"].get("opportunity", {})
            else:
                opportunity = opportunity_data.get("opportunity", {})

            if not opportunity:
                return {"is_valid": False, "reason": "No opportunity data"}

            # 基础字段验证
            required_fields = ["name", "description", "target_users"]
            for field in required_fields:
                if not opportunity.get(field):
                    return {"is_valid": False, "reason": f"Missing required field: {field}"}

            # 简单质量检查：描述长度
            description = opportunity.get("description", "")
            if len(description) < 20:
                return {"is_valid": False, "reason": f"Description too short ({len(description)} < 20 chars)"}

            # 名称长度检查
            name = opportunity.get("name", "")
            if len(name) < 3:
                return {"is_valid": False, "reason": f"Name too short ({len(name)} < 3 chars)"}

            # 目标用户长度检查
            target_users = opportunity.get("target_users", "")
            if len(target_users) < 10:
                return {"is_valid": False, "reason": f"Target users too short ({len(target_users)} < 10 chars)"}

            return {"is_valid": True, "reason": "Valid opportunity structure"}

        except Exception as e:
            logger.error(f"Failed to validate opportunity: {e}")
            return {"is_valid": False, "reason": f"Validation error: {e}"}

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

    def _save_opportunity_to_database(self, cluster_id: int, opportunity_data: Dict[str, Any]) -> Optional[int]:
        """保存机会到数据库（Phase 3：评分字段设为占位符，由score_viability.py计算）"""
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

            # 准备机会数据 - 评分字段使用占位符值
            opportunity_record = {
                "cluster_id": cluster_id,
                "opportunity_name": opportunity.get("name", ""),
                "description": opportunity.get("description", ""),
                "current_tools": json.dumps(current_tools),
                "missing_capability": missing_capability,
                "why_existing_fail": why_existing_fail,
                "target_users": opportunity.get("target_users", ""),
                # 占位符值：由 score_viability.py 计算并更新
                "pain_frequency_score": 0.0,
                "market_size_score": 0.0,
                "mvp_complexity_score": 0.0,
                "competition_risk_score": 0.0,
                "integration_complexity_score": 0.0,
                "total_score": 0.0,
                "killer_risks": json.dumps([]),
                "recommendation": ""
            }

            opportunity_id = db.insert_opportunity(opportunity_record)
            return opportunity_id

        except Exception as e:
            logger.error(f"Failed to save opportunity to database: {e}")
            return None

    def map_opportunities_for_clusters(
        self,
        limit: int = 50,
        clusters_to_update: List[int] = None,
        force_remap: bool = False
    ) -> Dict[str, Any]:
        """为聚类映射机会（Phase 3改进：支持为指定的clusters重新生成opportunities）

        Args:
            limit: 最多处理的clusters数量
            clusters_to_update: 指定需要更新opportunities的cluster IDs
                              None表示只为新clusters创建（默认行为）
            force_remap: 如果为True，强制重新映射所有符合条件的clusters（包括已有opportunities的）
                        如果为False，只处理尚未有opportunities的clusters（默认行为）

        Returns:
            映射结果统计
        """
        if clusters_to_update:
            logger.info(f"Re-mapping opportunities for {len(clusters_to_update)} specified clusters")
        elif force_remap:
            logger.info(f"Force re-mapping opportunities for all eligible clusters (including those with existing opportunities)")
        else:
            logger.info(f"Mapping opportunities for up to {limit} new clusters")

        start_time = time.time()

        try:
            # 获取聚类
            if clusters_to_update:
                # 为指定的clusters重新生成opportunities
                clusters = self._get_clusters_by_ids(clusters_to_update)

                # 删除这些clusters的旧opportunities
                for cluster_id in clusters_to_update:
                    deleted_count = self._delete_opportunities_for_cluster(cluster_id)
                    if deleted_count > 0:
                        logger.info(f"  Deleted {deleted_count} old opportunities for cluster {cluster_id}")
            else:
                # 获取clusters进行映射
                clusters = db.get_clusters_for_opportunity_mapping(force=force_remap)

                # 如果是强制重新映射模式，删除所有clusters的旧opportunities
                if force_remap and clusters:
                    logger.info(f"Force remap mode: deleting old opportunities for {len(clusters)} clusters...")
                    for cluster in clusters:
                        cluster_id = cluster.get("id")
                        if cluster_id:
                            deleted_count = self._delete_opportunities_for_cluster(cluster_id)
                            if deleted_count > 0:
                                logger.debug(f"  Deleted {deleted_count} old opportunities for cluster {cluster_id}")

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
                        # 验证机会数据（Phase 3：只验证结构，不评分）
                        if cluster.get('source_type') == 'aligned':
                            # 对齐聚群默认通过验证
                            validation_result = {"is_valid": True, "reason": "Aligned cluster auto-pass"}
                        else:
                            # 原始聚类使用标准验证
                            validation_result = self._validate_opportunity_data(opportunity_data)

                        if validation_result["is_valid"]:
                            # 保存到数据库
                            cluster_id = cluster.get("id", 0)  # 对齐聚类可能没有id
                            opportunity_id = self._save_opportunity_to_database(
                                cluster_id, opportunity_data
                            )

                            if opportunity_id:
                                opportunity_summary = {
                                    "opportunity_id": opportunity_id,
                                    "cluster_id": cluster_id,
                                    "cluster_name": cluster["cluster_name"],
                                    "opportunity_name": opportunity_data["content"]["opportunity"]["name"],
                                    "opportunity_description": opportunity_data["content"]["opportunity"]["description"],
                                    "validation_reason": validation_result.get("reason", "")
                                }

                                opportunities_created.append(opportunity_summary)
                                viable_opportunities += 1

                                logger.info(f"Created opportunity: {opportunity_data['content']['opportunity']['name']}")
                        else:
                            logger.debug(f"Opportunity validation failed: {validation_result.get('reason', 'Unknown')}")
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

            # Quality scoring is now handled by score_viability.py stage
            # No need to calculate avg_opportunity_score here

            logger.info(f"""
=== Opportunity Mapping Summary ===
Clusters processed: {len(clusters)}
Opportunities identified: {len(opportunities_created)}
Viable opportunities: {viable_opportunities}
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

    def _get_clusters_by_ids(self, cluster_ids: List[int]) -> List[Dict[str, Any]]:
        """根据cluster IDs获取clusters（Phase 3新增）"""
        try:
            if not cluster_ids:
                return []

            with db.get_connection("clusters") as conn:
                placeholders = ','.join('?' for _ in cluster_ids)
                cursor = conn.execute(f"""
                    SELECT id, cluster_name, source_type, centroid_summary,
                           common_pain, pain_event_ids, cluster_size,
                           cluster_description, workflow_confidence, created_at
                    FROM clusters
                    WHERE id IN ({placeholders})
                """, cluster_ids)

                clusters = [dict(row) for row in cursor.fetchall()]
                return clusters

        except Exception as e:
            logger.error(f"Failed to get clusters by IDs: {e}")
            return []

    def _delete_opportunities_for_cluster(self, cluster_id: int) -> int:
        """删除指定cluster的所有opportunities（Phase 3新增）"""
        try:
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    DELETE FROM opportunities
                    WHERE cluster_id = ?
                """, (cluster_id,))

                deleted_count = cursor.rowcount
                conn.commit()
                return deleted_count

        except Exception as e:
            logger.error(f"Failed to delete opportunities for cluster {cluster_id}: {e}")
            return 0


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
