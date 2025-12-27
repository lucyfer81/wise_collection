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
        self.thresholds = self._load_thresholds()
        self.stats = {
            "total_events_processed": 0,
            "clusters_created": 0,
            "llm_validations": 0,
            "processing_time": 0.0,
            "avg_cluster_size": 0.0
        }

    def _load_thresholds(self) -> Dict[str, Any]:
        """加载阈值配置"""
        try:
            import yaml
            with open("config/thresholds.yaml", 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config.get("clustering", {}).get("llm_validation", {})
        except Exception as e:
            logger.error(f"Failed to load clustering thresholds: {e}")
            # 返回默认值
            return {"workflow_similarity_threshold": 0.7}

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
        """Use LLM to validate cluster with JTBD extraction"""
        try:
            # Call LLM for cluster validation
            response = llm_client.cluster_pain_events(pain_events)
            validation_result = response["content"]

            # Extract workflow_similarity score
            workflow_similarity = validation_result.get("workflow_similarity", 0.0)

            # Use threshold from config for decision
            threshold = self.thresholds.get("workflow_similarity_threshold", 0.7)
            is_valid_cluster = workflow_similarity >= threshold

            return {
                "is_valid_cluster": is_valid_cluster,
                "workflow_similarity": workflow_similarity,  # NEW: Store raw score
                "cluster_name": validation_result.get("workflow_name", "Unnamed Cluster"),
                "cluster_description": validation_result.get("workflow_description", ""),
                "confidence": validation_result.get("confidence", 0.0),
                "reasoning": validation_result.get("reasoning", ""),
                # JTBD fields from validation
                "job_statement": validation_result.get("job_statement", ""),
                "customer_profile": validation_result.get("customer_profile", ""),
                "desired_outcomes": validation_result.get("desired_outcomes", [])
            }

        except Exception as e:
            logger.error(f"Failed to validate cluster with LLM: {e}")
            return {
                "is_valid_cluster": False,
                "workflow_similarity": 0.0,
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
        """保存聚类到数据库（包含JTBD字段）"""
        try:
            # 准备聚类数据 - 支持JTBD字段
            cluster_record = {
                "cluster_name": cluster_data["cluster_name"],
                "cluster_description": cluster_data["cluster_description"],
                "source_type": cluster_data.get("source_type", ""),
                "centroid_summary": cluster_data.get("centroid_summary", ""),
                "common_pain": cluster_data.get("common_pain", ""),
                "common_context": cluster_data.get("common_context", ""),
                "example_events": cluster_data.get("example_events", []),
                "pain_event_ids": cluster_data["pain_event_ids"],
                "cluster_size": cluster_data["cluster_size"],
                "avg_pain_score": cluster_data.get("avg_pain_score", 0.0),
                "workflow_confidence": cluster_data.get("workflow_confidence", 0.0),
                "workflow_similarity": cluster_data.get("workflow_similarity", 0.0),
                # JTBD fields
                "job_statement": cluster_data.get("job_statement", ""),
                "job_steps": cluster_data.get("job_steps", []),
                "desired_outcomes": cluster_data.get("desired_outcomes", []),
                "job_context": cluster_data.get("job_context", ""),
                "customer_profile": cluster_data.get("customer_profile", ""),
                "semantic_category": cluster_data.get("semantic_category", ""),
                "product_impact": cluster_data.get("product_impact", 0.0)
            }

            cluster_id = db.insert_cluster(cluster_record)
            return cluster_id

        except Exception as e:
            logger.error(f"Failed to save cluster to database: {e}")
            return None

    def cluster_pain_events(self, limit: int = 200) -> Dict[str, Any]:
        """聚类痛点事件 - 按source分组聚类"""
        logger.info(f"Starting source-aware clustering of up to {limit} pain events")

        start_time = time.time()

        try:
            # 获取所有有嵌入向量的痛点事件，并包含source信息
            pain_events = self._get_pain_events_with_source_and_embeddings()

            if len(pain_events) < 4:
                logger.info("Not enough pain events for clustering (need at least 4)")
                return {"clusters_created": 0, "events_processed": 0}

            # 限制处理数量
            if len(pain_events) > limit:
                pain_events = pain_events[:limit]

            logger.info(f"Processing {len(pain_events)} pain events for source-aware clustering")

            # 按source类型分组
            source_groups = self._group_events_by_source(pain_events)
            logger.info(f"Found {len(source_groups)} source groups: {list(source_groups.keys())}")

            # 对每个source组分别聚类
            final_clusters = []
            total_validated_clusters = 0

            for source_type, events_in_source in source_groups.items():
                if len(events_in_source) < 4:
                    logger.info(f"Skipping source {source_type}: not enough events ({len(events_in_source)} < 4)")
                    continue

                logger.info(f"\n=== Processing source: {source_type} ({len(events_in_source)} events) ===")

                # 使用向量聚类
                vector_clusters = pain_clustering.cluster_pain_events(events_in_source)

                if not vector_clusters:
                    logger.info(f"No clusters found for source {source_type}")
                    continue

                logger.info(f"Found {len(vector_clusters)} vector clusters for source {source_type}")

                # 验证和优化聚类
                source_clusters = self._process_source_clusters(
                    vector_clusters, source_type
                )

                final_clusters.extend(source_clusters)
                total_validated_clusters += len(source_clusters)

                logger.info(f"Source {source_type}: {len(source_clusters)} validated clusters")

            # 更新统计信息
            processing_time = time.time() - start_time
            self.stats["total_events_processed"] = len(pain_events)
            self.stats["clusters_created"] = total_validated_clusters
            self.stats["processing_time"] = processing_time

            if total_validated_clusters > 0:
                self.stats["avg_cluster_size"] = sum(len(cluster["pain_event_ids"]) for cluster in final_clusters) / total_validated_clusters

            logger.info(f"""
=== Source-Aware Clustering Summary ===
Pain events processed: {len(pain_events)}
Source groups processed: {len(source_groups)}
Validated clusters created: {total_validated_clusters}
Average cluster size: {self.stats['avg_cluster_size']:.1f}
Processing time: {processing_time:.2f}s
""")

            return {
                "clusters_created": total_validated_clusters,
                "events_processed": len(pain_events),
                "source_groups": len(source_groups),
                "final_clusters": final_clusters,
                "clustering_stats": self.get_statistics()
            }

        except Exception as e:
            logger.error(f"Failed to cluster pain events: {e}")
            raise

    def _get_pain_events_with_source_and_embeddings(self) -> List[Dict[str, Any]]:
        """获取有嵌入向量和source信息的痛点事件"""
        try:
            import pickle
            with db.get_connection("pain") as conn:
                # 如果是统一数据库，可以从posts表获取source信息
                if db.is_unified():
                    cursor = conn.execute("""
                        SELECT p.*, e.embedding_vector, e.embedding_model,
                               COALESCE(po.source, 'reddit') as source_type
                        FROM pain_events p
                        JOIN pain_embeddings e ON p.id = e.pain_event_id
                        LEFT JOIN filtered_posts fp ON p.post_id = fp.id
                        LEFT JOIN posts po ON p.post_id = po.id
                        ORDER BY p.extracted_at DESC
                    """)
                else:
                    # 多数据库模式，默认为reddit
                    cursor = conn.execute("""
                        SELECT p.*, e.embedding_vector, e.embedding_model,
                               'reddit' as source_type
                        FROM pain_events p
                        JOIN pain_embeddings e ON p.id = e.pain_event_id
                        ORDER BY p.extracted_at DESC
                    """)

                results = []
                for row in cursor.fetchall():
                    event_data = dict(row)
                    # 反序列化嵌入向量
                    if event_data["embedding_vector"]:
                        event_data["embedding_vector"] = pickle.loads(event_data["embedding_vector"])
                    results.append(event_data)
                return results
        except Exception as e:
            logger.error(f"Failed to get pain events with source and embeddings: {e}")
            return []

    def _group_events_by_source(self, pain_events: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """按source类型分组痛点事件"""
        source_groups = {}
        for event in pain_events:
            source = event.get('source_type', 'reddit')
            if source not in source_groups:
                source_groups[source] = []
            source_groups[source].append(event)
        return source_groups

    def _process_source_clusters(self, vector_clusters: List[Dict[str, Any]], source_type: str) -> List[Dict[str, Any]]:
        """处理单个source的聚类"""
        final_clusters = []
        cluster_counter = 1

        for i, cluster in enumerate(vector_clusters):
            logger.info(f"Validating {source_type} cluster {i+1}/{len(vector_clusters)} (size: {cluster['cluster_size']})")

            # 获取聚类中的事件
            cluster_events = cluster["events"]

            # 严格的跳过规则：至少4个事件
            if len(cluster_events) < 4:
                logger.debug(f"Skipping cluster {i+1}: too small ({len(cluster_events)} < 4 events)")
                continue

            # 对于大聚类，采样前20个事件进行验证和摘要
            events_for_processing = cluster_events
            if len(cluster_events) > 20:
                events_for_processing = cluster_events[:20]
                logger.info(f"Sampling first 20 events from large cluster of {len(cluster_events)} for processing")

            # 使用LLM验证聚类
            validation_result = self._validate_cluster_with_llm(events_for_processing)
            self.stats["llm_validations"] += 1

            # Log workflow_similarity score
            workflow_similarity = validation_result.get("workflow_similarity", 0.0)
            threshold = self.thresholds.get("workflow_similarity_threshold", 0.7)
            logger.info(f"Workflow similarity score: {workflow_similarity:.2f} (threshold: {threshold})")

            if validation_result["is_valid_cluster"]:
                # 使用Cluster Summarizer生成source内摘要
                summary_result = self._summarize_source_cluster(events_for_processing, source_type)

                # 生成标准化cluster ID
                cluster_id = f"{source_type.replace('-', '_')}_{cluster_counter:02d}"
                cluster_counter += 1

                # 准备最终聚类数据（包含JTBD字段）
                final_cluster = {
                    "cluster_name": f"{source_type}: {validation_result['cluster_name']}",
                    "cluster_description": validation_result["cluster_description"],
                    "source_type": source_type,
                    "cluster_id": cluster_id,
                    "centroid_summary": summary_result.get("centroid_summary", ""),
                    "common_pain": summary_result.get("common_pain", ""),
                    "common_context": summary_result.get("common_context", ""),
                    "example_events": summary_result.get("example_events", []),
                    "pain_event_ids": [event["id"] for event in cluster_events],
                    "cluster_size": len(cluster_events),
                    "workflow_confidence": validation_result["confidence"],
                    "workflow_similarity": workflow_similarity,
                    "validation_reasoning": validation_result["reasoning"],
                    # JTBD fields
                    "job_statement": summary_result.get("job_statement", validation_result.get("job_statement", "")),
                    "job_steps": summary_result.get("job_steps", []),
                    "desired_outcomes": summary_result.get("desired_outcomes", validation_result.get("desired_outcomes", [])),
                    "job_context": summary_result.get("job_context", ""),
                    "customer_profile": summary_result.get("customer_profile", validation_result.get("customer_profile", "")),
                    "semantic_category": summary_result.get("semantic_category", ""),
                    "product_impact": summary_result.get("product_impact", 0.0)
                }

                # 保存到数据库
                saved_cluster_id = self._save_cluster_to_database(final_cluster)
                if saved_cluster_id:
                    final_cluster["saved_cluster_id"] = saved_cluster_id
                    final_clusters.append(final_cluster)

                    logger.info(f"✅ Saved {cluster_id}: {validation_result['cluster_name']} ({len(cluster_events)} events, similarity: {workflow_similarity:.2f})")
            else:
                logger.warning(f"❌ Cluster {i+1} rejected by LLM: {validation_result['reasoning']} (similarity: {workflow_similarity:.2f})")

            # 添加延迟避免API限制
            time.sleep(1)

        return final_clusters

    def _summarize_source_cluster(self, pain_events: List[Dict[str, Any]], source_type: str) -> Dict[str, Any]:
        """使用Cluster Summarizer生成source内聚类摘要（包含JTBD）"""
        try:
            response = llm_client.summarize_source_cluster(pain_events, source_type)
            summary_result = response.get("content", {})

            # 提取JTBD字段（如果存在）
            jtbd_fields = {
                "job_statement": summary_result.get("job_statement", ""),
                "job_steps": summary_result.get("job_steps", []),
                "desired_outcomes": summary_result.get("desired_outcomes", []),
                "job_context": summary_result.get("job_context", ""),
                "customer_profile": summary_result.get("customer_profile", ""),
                "semantic_category": summary_result.get("semantic_category", ""),
                "product_impact": summary_result.get("product_impact", 0.0)
            }

            # 合并到原有结果
            summary_result.update(jtbd_fields)
            return summary_result

        except Exception as e:
            logger.error(f"Failed to summarize source cluster: {e}")
            return {
                "centroid_summary": "",
                "common_pain": "",
                "common_context": "",
                "example_events": [],
                "coherence_score": 0.0,
                "reasoning": f"Summary failed: {e}",
                # JTBD默认值
                "job_statement": "",
                "job_steps": [],
                "desired_outcomes": [],
                "job_context": "",
                "customer_profile": "",
                "semantic_category": "",
                "product_impact": 0.0
            }

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

            # 反序列化JTBD字段
            cluster_info["job_steps"] = json.loads(cluster_info.get("job_steps", "[]"))
            cluster_info["desired_outcomes"] = json.loads(cluster_info.get("desired_outcomes", "[]"))
            cluster_info["example_events"] = json.loads(cluster_info.get("example_events", "[]"))

            return cluster_info

        except Exception as e:
            logger.error(f"Failed to get cluster analysis: {e}")
            return None

    def get_all_clusters_summary(self) -> List[Dict[str, Any]]:
        """获取所有聚类的摘要"""
        try:
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT id, cluster_name, cluster_size, avg_pain_score, workflow_confidence, workflow_similarity, created_at
                    FROM clusters
                    ORDER BY cluster_size DESC, workflow_similarity DESC
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

    def get_clusters_by_semantic_category(self, category: str) -> List[Dict[str, Any]]:
        """按语义分类获取聚类"""
        try:
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT id, cluster_name, job_statement, customer_profile,
                           semantic_category, product_impact, cluster_size
                    FROM clusters
                    WHERE semantic_category = ?
                    ORDER BY product_impact DESC
                """, (category,))

                clusters = []
                for row in cursor.fetchall():
                    cluster = dict(row)
                    cluster["job_steps"] = json.loads(cluster.get("job_steps", "[]"))
                    clusters.append(cluster)

                return clusters

        except Exception as e:
            logger.error(f"Failed to get clusters by semantic category: {e}")
            return []

    def get_high_impact_clusters(self, min_impact: float = 0.7) -> List[Dict[str, Any]]:
        """获取高产品影响聚类"""
        try:
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT id, cluster_name, job_statement, customer_profile,
                           semantic_category, product_impact, cluster_size
                    FROM clusters
                    WHERE product_impact >= ?
                    ORDER BY product_impact DESC
                """, (min_impact,))

                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get high impact clusters: {e}")
            return []

    def get_all_semantic_categories(self) -> List[Dict[str, Any]]:
        """获取所有语义分类及其统计"""
        try:
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT semantic_category,
                           COUNT(*) as cluster_count,
                           AVG(product_impact) as avg_impact,
                           SUM(cluster_size) as total_events
                    FROM clusters
                    WHERE semantic_category IS NOT NULL AND semantic_category != ''
                    GROUP BY semantic_category
                    ORDER BY avg_impact DESC
                """)

                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get semantic categories: {e}")
            return []

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