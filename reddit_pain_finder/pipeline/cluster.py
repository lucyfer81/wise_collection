"""
Cluster module for Reddit Pain Point Finder
工作流级聚类模块 - 发现相似的痛点模式
"""
import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np

from utils.embedding import pain_clustering
from utils.llm_client import llm_client
from utils.db import db

logger = logging.getLogger(__name__)

class PainEventClusterer:
    """痛点事件聚类器"""

    def __init__(self):
        """初始化聚类器"""
        self.stats = {
            "total_events_processed": 0,
            "clusters_created": 0,
            "llm_validations": 0,
            "processing_time": 0.0,
            "avg_cluster_size": 0.0
        }

    def _find_similar_events(
        self,
        target_event: Dict[str, Any],
        candidate_events: List[Dict[str, Any]],
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """找到与目标事件相似的事件"""
        try:
            # 使用相似度搜索找到相似事件
            similar_events = pain_clustering.find_similar_events(
                target_event=target_event,
                candidate_events=candidate_events,
                threshold=threshold,
                top_k=20
            )

            return similar_events

        except Exception as e:
            logger.error(f"Failed to find similar events: {e}")
            return []

    def _validate_cluster_with_llm(
        self,
        pain_events: List[Dict[str, Any]],
        cluster_name: str = None
    ) -> Dict[str, Any]:
        """使用LLM验证聚类是否属于同一工作流"""
        try:
            # 调用LLM进行聚类验证
            response = llm_client.cluster_pain_events(pain_events)

            validation_result = response["content"]

            # 检查LLM是否认为这些事件属于同一工作流
            if validation_result.get("same_workflow", False):
                return {
                    "is_valid_cluster": True,
                    "cluster_name": validation_result.get("workflow_name", "Unnamed Cluster"),
                    "cluster_description": validation_result.get("workflow_description", ""),
                    "confidence": validation_result.get("confidence", 0.0),
                    "reasoning": validation_result.get("reasoning", "")
                }
            else:
                return {
                    "is_valid_cluster": False,
                    "reasoning": validation_result.get("reasoning", "Not same workflow")
                }

        except Exception as e:
            logger.error(f"Failed to validate cluster with LLM: {e}")
            return {
                "is_valid_cluster": False,
                "reasoning": f"Validation error: {e}"
            }

    def _create_cluster_summary(self, pain_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """创建聚类摘要"""
        if not pain_events:
            return {}

        try:
            # 统计信息
            cluster_size = len(pain_events)
            subreddits = list(set(event.get("subreddit", "") for event in pain_events))

            # 痛点类型统计
            pain_types = []
            for event in pain_events:
                types = event.get("pain_types", [])
                if isinstance(types, list):
                    pain_types.extend(types)

            pain_type_counts = {}
            for pain_type in pain_types:
                pain_type_counts[pain_type] = pain_type_counts.get(pain_type, 0) + 1

            # 主要痛点类型
            primary_pain_type = max(pain_type_counts.items(), key=lambda x: x[1])[0] if pain_type_counts else "general"

            # 情绪信号统计
            emotional_signals = [event.get("emotional_signal", "") for event in pain_events]
            emotion_counts = {}
            for signal in emotional_signals:
                if signal:
                    emotion_counts[signal] = emotion_counts.get(signal, 0) + 1

            # 频率分数统计
            frequency_scores = [event.get("frequency_score", 5) for event in pain_events]
            avg_frequency_score = np.mean(frequency_scores) if frequency_scores else 5.0

            # 提到的工具
            mentioned_tools = []
            for event in pain_events:
                tools = event.get("mentioned_tools", [])
                if isinstance(tools, list):
                    mentioned_tools.extend(tools)

            tool_counts = {}
            for tool in mentioned_tools:
                tool_counts[tool] = tool_counts.get(tool, 0) + 1

            # 提取代表性的问题
            problems = [event.get("problem", "") for event in pain_events if event.get("problem")]
            representative_problems = sorted(problems, key=len, reverse=True)[:5]

            # 提取代表性工作方式
            workarounds = [event.get("current_workaround", "") for event in pain_events if event.get("current_workaround")]
            representative_workarounds = [w for w in workarounds if w][:3]

            return {
                "cluster_size": cluster_size,
                "subreddits": subreddits,
                "primary_pain_type": primary_pain_type,
                "pain_type_distribution": pain_type_counts,
                "emotional_signals": emotion_counts,
                "avg_frequency_score": avg_frequency_score,
                "mentioned_tools": tool_counts,
                "representative_problems": representative_problems,
                "representative_workarounds": representative_workarounds,
                "total_pain_score": sum(event.get("post_pain_score", 0) for event in pain_events)
            }

        except Exception as e:
            logger.error(f"Failed to create cluster summary: {e}")
            return {}

    def _save_cluster_to_database(self, cluster_data: Dict[str, Any]) -> Optional[int]:
        """保存聚类到数据库"""
        try:
            # 准备聚类数据
            cluster_record = {
                "cluster_name": cluster_data["cluster_name"],
                "cluster_description": cluster_data["cluster_description"],
                "pain_event_ids": json.dumps(cluster_data["pain_event_ids"]),
                "cluster_size": cluster_data["cluster_size"],
                "avg_pain_score": cluster_data.get("avg_pain_score", 0.0),
                "workflow_confidence": cluster_data.get("workflow_confidence", 0.0)
            }

            cluster_id = db.insert_cluster(cluster_record)
            return cluster_id

        except Exception as e:
            logger.error(f"Failed to save cluster to database: {e}")
            return None

    def cluster_pain_events(self, limit: int = 200) -> Dict[str, Any]:
        """聚类痛点事件"""
        logger.info(f"Starting clustering of up to {limit} pain events")

        start_time = time.time()

        try:
            # 获取所有有嵌入向量的痛点事件
            pain_events = db.get_all_pain_events_with_embeddings()

            if len(pain_events) < 2:
                logger.info("Not enough pain events for clustering")
                return {"clusters_created": 0, "events_processed": 0}

            # 限制处理数量
            if len(pain_events) > limit:
                pain_events = pain_events[:limit]

            logger.info(f"Processing {len(pain_events)} pain events for clustering")

            # 使用向量聚类
            vector_clusters = pain_clustering.cluster_pain_events(pain_events)

            if not vector_clusters:
                logger.info("No clusters found")
                return {"clusters_created": 0, "events_processed": len(pain_events)}

            logger.info(f"Found {len(vector_clusters)} vector clusters")

            # 验证和优化聚类
            final_clusters = []
            validated_clusters = 0

            for i, cluster in enumerate(vector_clusters):
                logger.info(f"Validating cluster {i+1}/{len(vector_clusters)} (size: {cluster['cluster_size']})")

                # 获取聚类中的事件
                cluster_events = cluster["events"]

                # 跳过太小的聚类
                if len(cluster_events) < 2:
                    logger.debug(f"Skipping cluster {i+1}: too small ({len(cluster_events)} events)")
                    continue

                # 对于大聚类，采样前20个事件进行验证
                events_for_validation = cluster_events
                if len(cluster_events) > 20:
                    events_for_validation = cluster_events[:20]
                    logger.info(f"Sampling first 20 events from large cluster of {len(cluster_events)} for validation")

                # 使用LLM验证聚类
                validation_result = self._validate_cluster_with_llm(events_for_validation)
                self.stats["llm_validations"] += 1

                if validation_result["is_valid_cluster"]:
                    # 创建聚类摘要
                    cluster_summary = self._create_cluster_summary(cluster_events)

                    # 准备最终聚类数据
                    final_cluster = {
                        "cluster_name": validation_result["cluster_name"],
                        "cluster_description": validation_result["cluster_description"],
                        "pain_event_ids": [event["id"] for event in cluster_events],
                        "cluster_size": len(cluster_events),
                        "workflow_confidence": validation_result["confidence"],
                        "cluster_summary": cluster_summary,
                        "validation_reasoning": validation_result["reasoning"]
                    }

                    # 保存到数据库
                    cluster_id = self._save_cluster_to_database(final_cluster)
                    if cluster_id:
                        final_cluster["cluster_id"] = cluster_id
                        final_clusters.append(final_cluster)
                        validated_clusters += 1

                        logger.info(f"Saved cluster: {validation_result['cluster_name']} ({len(cluster_events)} events)")
                else:
                    logger.warning(f"Cluster {i+1} rejected by LLM: {validation_result['reasoning']}")

                # 添加延迟避免API限制
                time.sleep(1)

            # 更新统计信息
            processing_time = time.time() - start_time
            self.stats["total_events_processed"] = len(pain_events)
            self.stats["clusters_created"] = validated_clusters
            self.stats["processing_time"] = processing_time

            if validated_clusters > 0:
                self.stats["avg_cluster_size"] = sum(len(cluster["pain_event_ids"]) for cluster in final_clusters) / validated_clusters

            logger.info(f"""
=== Clustering Summary ===
Pain events processed: {len(pain_events)}
Vector clusters found: {len(vector_clusters)}
Validated clusters created: {validated_clusters}
Average cluster size: {self.stats['avg_cluster_size']:.1f}
Processing time: {processing_time:.2f}s
""")

            return {
                "clusters_created": validated_clusters,
                "events_processed": len(pain_events),
                "vector_clusters": len(vector_clusters),
                "final_clusters": final_clusters,
                "clustering_stats": self.get_statistics()
            }

        except Exception as e:
            logger.error(f"Failed to cluster pain events: {e}")
            raise

    def get_cluster_analysis(self, cluster_id: int) -> Optional[Dict[str, Any]]:
        """获取聚类详细分析"""
        try:
            # 从数据库获取聚类信息
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT * FROM clusters WHERE id = ?
                """, (cluster_id,))
                cluster_data = cursor.fetchone()

            if not cluster_data:
                return None

            cluster_info = dict(cluster_data)

            # 获取聚类中的痛点事件
            pain_event_ids = json.loads(cluster_info["pain_event_ids"])
            pain_events = []

            with db.get_connection("pain") as conn:
                for event_id in pain_event_ids:
                    cursor = conn.execute("""
                        SELECT * FROM pain_events WHERE id = ?
                    """, (event_id,))
                    event_data = cursor.fetchone()
                    if event_data:
                        pain_events.append(dict(event_data))

            cluster_info["pain_events"] = pain_events

            # 重新计算聚类摘要
            cluster_summary = self._create_cluster_summary(pain_events)
            cluster_info["cluster_summary"] = cluster_summary

            return cluster_info

        except Exception as e:
            logger.error(f"Failed to get cluster analysis: {e}")
            return None

    def get_all_clusters_summary(self) -> List[Dict[str, Any]]:
        """获取所有聚类的摘要"""
        try:
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT id, cluster_name, cluster_size, avg_pain_score, workflow_confidence, created_at
                    FROM clusters
                    ORDER BY cluster_size DESC, workflow_confidence DESC
                """)
                clusters = [dict(row) for row in cursor.fetchall()]

            return clusters

        except Exception as e:
            logger.error(f"Failed to get clusters summary: {e}")
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """获取聚类统计信息"""
        stats = self.stats.copy()

        if stats["total_events_processed"] > 0:
            stats["clustering_rate"] = stats["clusters_created"] / stats["total_events_processed"]
            stats["processing_rate"] = stats["total_events_processed"] / max(stats["processing_time"], 1)
        else:
            stats["clustering_rate"] = 0
            stats["processing_rate"] = 0

        # 添加嵌入客户端统计
        embedding_stats = pain_clustering.embedding_client.get_embedding_statistics()
        stats["embedding_stats"] = embedding_stats

        return stats

    def reset_statistics(self):
        """重置统计信息"""
        self.stats = {
            "total_events_processed": 0,
            "clusters_created": 0,
            "llm_validations": 0,
            "processing_time": 0.0,
            "avg_cluster_size": 0.0
        }

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Cluster pain events into workflow groups")
    parser.add_argument("--limit", type=int, default=200, help="Limit number of pain events to process")
    parser.add_argument("--analyze", type=int, help="Analyze specific cluster ID")
    parser.add_argument("--list", action="store_true", help="List all clusters summary")
    args = parser.parse_args()

    try:
        logger.info("Starting pain event clustering...")

        clusterer = PainEventClusterer()

        if args.analyze:
            # 分析特定聚类
            cluster_analysis = clusterer.get_cluster_analysis(args.analyze)
            if cluster_analysis:
                print(json.dumps(cluster_analysis, indent=2))
            else:
                logger.error(f"Cluster {args.analyze} not found")

        elif args.list:
            # 列出所有聚类
            clusters_summary = clusterer.get_all_clusters_summary()
            print(json.dumps(clusters_summary, indent=2))

        else:
            # 执行聚类
            result = clusterer.cluster_pain_events(limit=args.limit)

            logger.info(f"""
=== Clustering Complete ===
Clusters created: {result['clusters_created']}
Events processed: {result['events_processed']}
Clustering stats: {result['clustering_stats']}
""")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()