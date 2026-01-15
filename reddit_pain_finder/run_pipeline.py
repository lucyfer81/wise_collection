#!/usr/bin/env python3
"""
Wise Collection - Main Pipeline Runner
主要的pipeline执行脚本 - 一键运行整个数据收集流程
"""
import os
import sys
import argparse
import logging
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

# 设置项目根目录
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# 导入pipeline模块
from pipeline.fetch import RedditSourceFetcher
from pipeline.filter_signal import PainSignalFilter
from pipeline.extract_pain import PainPointExtractor
from pipeline.embed import PainEventEmbedder
from pipeline.cluster import PainEventClusterer
from pipeline.score_viability import ViabilityScorer
from pipeline.map_opportunity import OpportunityMapper
from pipeline.decision_shortlist import DecisionShortlistGenerator

# 导入工具模块
from utils.db import db
from utils.llm_client import LLMClient
from utils.performance_monitor import performance_monitor

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/pipeline.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class WiseCollectionPipeline:
    """Wise Collection数据收集Pipeline"""

    def __init__(self, enable_monitoring: bool = True):
        """初始化pipeline"""
        self.pipeline_start_time = datetime.now()
        self.enable_monitoring = enable_monitoring
        self.stats = {
            "start_time": self.pipeline_start_time.isoformat(),
            "stages_completed": [],
            "stages_failed": [],
            "stage_results": {},
            "total_runtime_seconds": 0,
            "final_summary": {}
        }

        # 确保日志目录存在
        os.makedirs("logs", exist_ok=True)

        # 重置性能监控器
        if self.enable_monitoring:
            performance_monitor.reset()

    def _load_config(self, config_path: str = "config/llm.yaml") -> Dict[str, Any]:
        """加载配置文件"""
        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
            # 返回默认配置
            return {
                'database': {'path': 'data/wise_collection.db'},
                'llm': {
                    'models': {
                        'main': 'gpt-4',
                        'medium': 'gpt-3.5-turbo',
                        'small': 'gpt-3.5-turbo'
                    }
                }
            }

    def run_stage_fetch(self, limit_sources: Optional[int] = None,
                       sources: Optional[List[str]] = None) -> Dict[str, Any]:
        """阶段1: 数据抓取（支持多数据源）"""
        logger.info("=" * 50)
        logger.info("STAGE 1: Multi-Source Posts Fetcher")
        logger.info("=" * 50)

        if self.enable_monitoring:
            performance_monitor.start_stage("fetch")

        try:
            from pipeline.fetch import MultiSourceFetcher

            # 使用指定的数据源，默认为 reddit
            fetch_sources = sources or ['reddit']
            fetcher = MultiSourceFetcher(sources=fetch_sources)
            result = fetcher.fetch_all(limit_sources=limit_sources)

            self.stats["stages_completed"].append("fetch")
            self.stats["stage_results"]["fetch"] = result

            if self.enable_monitoring:
                performance_monitor.end_stage("fetch", result.get('total_saved', 0))

            logger.info(f"✅ Stage 1 completed: Found {result['total_saved']} posts from {len(result['sources_processed'])} sources")

            # 输出各数据源统计
            for source, stats in result.get("source_stats", {}).items():
                if "error" not in stats:
                    logger.info(f"   - {source}: {stats.get('total_saved', 0)} posts")
                else:
                    logger.error(f"   - {source}: ERROR - {stats['error']}")

            return result

        except Exception as e:
            logger.error(f"❌ Stage 1 failed: {e}")
            self.stats["stages_failed"].append("fetch")
            if self.enable_monitoring:
                performance_monitor.end_stage("fetch", 0)
            raise

    def run_stage_filter(self, limit_posts: Optional[int] = None, process_all: bool = False) -> Dict[str, Any]:
        """阶段2: 信号过滤（Posts）- 支持增量处理

        Args:
            limit_posts: 限制处理帖子数量
            process_all: 处理所有未过滤数据
        """
        logger.info("=" * 50)
        logger.info("STAGE 2: Filtering pain signals (Incremental)")
        logger.info("=" * 50)

        if self.enable_monitoring:
            performance_monitor.start_stage("filter")

        try:
            from utils.pipeline_state import get_pipeline_state

            # 获取上次运行时间（增量处理）
            last_run = get_pipeline_state().get_last_run_time("filter")
            if last_run:
                logger.info(f"Last run: {last_run}")
                logger.info("Processing posts collected since then...")

            filter = PainSignalFilter()

            # 获取未过滤的帖子（支持增量）
            # 如果 process_all=True 且未指定 limit，则处理所有数据
            if process_all and limit_posts is None:
                limit_posts = 1000000  # 处理所有数据
            elif limit_posts is None:
                limit_posts = 1000

            unfiltered_posts = db.get_unprocessed_posts(limit=limit_posts, since=last_run)

            # 初始化计数器
            saved_count = 0
            failed_count = 0
            failed_posts = []

            # ============ 处理Posts ============
            if not unfiltered_posts:
                logger.info("No posts to filter")
                post_result = {"processed": 0, "filtered": 0, "failed": 0}
                if self.enable_monitoring:
                    performance_monitor.end_stage("filter", 0)
            else:
                logger.info(f"Filtering {len(unfiltered_posts)} posts")
                logger.info("Using incremental save mode - each post is saved immediately after processing")

                # 改进：逐个处理并立即保存，避免批量失败导致数据丢失
                for i, post in enumerate(unfiltered_posts):
                    if i % 100 == 0:
                        logger.info(f"Processed {i}/{len(unfiltered_posts)} posts, saved: {saved_count}, failed: {failed_count}")

                    try:
                        # 过滤单个帖子
                        passed, filter_result = filter.filter_post(post)

                        if passed:
                            # 为帖子添加过滤结果
                            filtered_post = post.copy()
                            filtered_post.update({
                                "pain_score": filter_result["pain_score"],
                                "pain_keywords": filter_result.get("matched_keywords", []),
                                "pain_patterns": filter_result.get("matched_patterns", []),
                                "emotional_intensity": filter_result.get("emotional_intensity", 0.0),
                                "filter_reason": "pain_signal_passed",
                                "aspiration_keywords": filter_result.get("matched_aspirations", []),
                                "aspiration_score": filter_result.get("aspiration_score", 0.0),
                                "pass_type": filter_result.get("pass_type", "pain"),
                                "engagement_score": filter_result.get("engagement_score", 0.0),
                                "trust_level": filter_result.get("trust_level", 0.5)
                            })

                            # 立即保存到数据库
                            if db.insert_filtered_post(filtered_post):
                                saved_count += 1
                            else:
                                logger.warning(f"Failed to save post {post.get('id')}")
                                failed_count += 1
                                failed_posts.append(post.get('id'))
                        # 如果未通过过滤，不保存（这是正常的）

                    except Exception as e:
                        logger.error(f"Error processing post {post.get('id')}: {e}")
                        failed_count += 1
                        failed_posts.append(post.get('id'))
                        # 继续处理下一个帖子，不中断整个流程
                        continue

                post_result = {
                    "processed": len(unfiltered_posts),
                    "filtered": saved_count,
                    "failed": failed_count,
                    "failed_posts": failed_posts[:10],  # 只记录前10个失败的
                    "filter_stats": filter.get_statistics()
                }

            # ============ 返回结果 ============
            result = {
                "posts": post_result
            }

            if self.enable_monitoring:
                performance_monitor.end_stage("filter", saved_count)

            self.stats["stages_completed"].append("filter")
            self.stats["stage_results"]["filter"] = result

            # 输出总结
            logger.info("")
            logger.info("=" * 50)
            logger.info("Filter Stage Summary")
            logger.info("=" * 50)
            logger.info(f"Posts:   {post_result['filtered']}/{post_result['processed']} passed")
            logger.info("=" * 50)

            if failed_count > 0:
                logger.warning(f"⚠️  {failed_count} posts failed to process and will be retried next run")

            # 更新pipeline状态
            get_pipeline_state().update_stage_run("filter", saved_count)

            return result

        except Exception as e:
            logger.error(f"❌ Stage 2 failed: {e}")
            self.stats["stages_failed"].append("filter")
            if self.enable_monitoring:
                performance_monitor.end_stage("filter", 0)
            raise

    def run_stage_extract(self, limit_posts: Optional[int] = None, process_all: bool = False) -> Dict[str, Any]:
        """阶段3: 痛点抽取 - 支持增量处理

        Args:
            limit_posts: 限制处理帖子数量
            process_all: 处理所有未过滤数据
        """
        logger.info("=" * 50)
        logger.info("STAGE 3: Extracting pain points (Incremental)")
        logger.info("=" * 50)

        if self.enable_monitoring:
            performance_monitor.start_stage("extract")

        try:
            from utils.pipeline_state import get_pipeline_state

            # 获取上次运行时间（增量处理）
            last_run = get_pipeline_state().get_last_run_time("extract")
            if last_run:
                logger.info(f"Last run: {last_run}")
                logger.info("Processing posts filtered since then...")

            extractor = PainPointExtractor()

            # ============ 处理Posts ============
            # 如果 process_all=True 且未指定 limit，则处理所有数据
            if process_all and limit_posts is None:
                limit_posts = 1000000  # 处理所有数据
            elif limit_posts is None:
                limit_posts = 100

            # 使用并行处理（max_workers=8）
            post_result = extractor.process_unextracted_posts(limit=limit_posts, max_workers=8)

            logger.info(f"✅ Posts: Extracted {post_result.get('pain_events_saved', 0)} pain events")

            # ============ 返回结果 ============
            result = {
                "posts": post_result,
                "total_events": post_result.get('pain_events_saved', 0)
            }

            self.stats["stages_completed"].append("extract")
            self.stats["stage_results"]["extract"] = result

            if self.enable_monitoring:
                events_saved = result.get('total_events', 0)
                performance_monitor.end_stage("extract", events_saved)

            # 输出总结
            logger.info("")
            logger.info("=" * 50)
            logger.info("Extract Stage Summary")
            logger.info("=" * 50)
            logger.info(f"Total events: {result.get('total_events', 0)}")
            logger.info("=" * 50)

            # 更新pipeline状态
            get_pipeline_state().update_stage_run("extract", result.get('total_events', 0))

            return result

        except Exception as e:
            logger.error(f"❌ Stage 3 failed: {e}")
            self.stats["stages_failed"].append("extract")
            if self.enable_monitoring:
                performance_monitor.end_stage("extract", 0)
            raise

    def run_stage_embed(self, limit_events: Optional[int] = None, process_all: bool = False) -> Dict[str, Any]:
        """阶段4: 向量化"""
        logger.info("=" * 50)
        logger.info("STAGE 4: Creating embeddings")
        logger.info("=" * 50)

        if self.enable_monitoring:
            performance_monitor.start_stage("embed")

        try:
            embedder = PainEventEmbedder()

            # 如果 process_all=True 且未指定 limit，则处理所有数据
            if process_all and limit_events is None:
                limit_events = 1000000  # 处理所有数据
            elif limit_events is None:
                limit_events = 200

            result = embedder.process_missing_embeddings(limit=limit_events)

            self.stats["stages_completed"].append("embed")
            self.stats["stage_results"]["embed"] = result

            if self.enable_monitoring:
                performance_monitor.end_stage("embed", result.get('embeddings_created', 0))

            logger.info(f"✅ Stage 4 completed: Created {result['embeddings_created']} embeddings")
            return result

        except Exception as e:
            logger.error(f"❌ Stage 4 failed: {e}")
            self.stats["stages_failed"].append("embed")
            if self.enable_monitoring:
                performance_monitor.end_stage("embed", 0)
            raise

    def run_stage_cluster(self, limit_events: Optional[int] = None, process_all: bool = False) -> Dict[str, Any]:
        """阶段5: 动态聚类更新 (Dynamic Clustering) - 支持增量处理"""
        logger.info("=" * 50)
        logger.info("STAGE 5: Dynamic Clustering (Real-time)")
        logger.info("=" * 50)

        if self.enable_monitoring:
            performance_monitor.start_stage("cluster")

        try:
            from pipeline.dynamic_cluster import DynamicClusterUpdater
            from utils.pipeline_state import get_pipeline_state
            import pickle

            # 初始化动态聚类器
            clusterer = DynamicClusterUpdater()

            # 获取需要处理的pain_events (新增的或unclustered的)
            with db.get_connection("pain") as conn:
                # 策略：处理所有未clustered的events
                if process_all and limit_events is None:
                    # 处理所有unclustered events
                    cursor = conn.execute("""
                        SELECT pe.*, em.embedding_vector
                        FROM pain_events pe
                        JOIN pain_embeddings em ON pe.id = em.pain_event_id
                        WHERE pe.cluster_id IS NULL
                        ORDER BY pe.extracted_at DESC
                    """)
                    rows = cursor.fetchall()
                else:
                    # 限制处理数量
                    limit = limit_events if limit_events else 200
                    cursor = conn.execute("""
                        SELECT pe.*, em.embedding_vector
                        FROM pain_events pe
                        JOIN pain_embeddings em ON pe.id = em.pain_event_id
                        WHERE pe.cluster_id IS NULL
                        ORDER BY pe.extracted_at DESC
                        LIMIT ?
                    """, (limit,))
                    rows = cursor.fetchall()

                # 反序列化embedding_vector (pickle BLOB -> list)
                new_events = []
                for row in rows:
                    event = dict(row)
                    if event.get('embedding_vector'):
                        try:
                            event['embedding_vector'] = pickle.loads(event['embedding_vector'])
                        except Exception as e:
                            logger.warning(f"Failed to deserialize embedding for event {event.get('id')}: {e}")
                            event['embedding_vector'] = None
                    new_events.append(event)

            logger.info(f"Found {len(new_events)} events to process")

            if not new_events:
                logger.info("No new events to cluster")
                result = {
                    'clusters_created': 0,
                    'clusters_updated': 0,
                    'events_processed': 0
                }
            else:
                # 使用DynamicClusterUpdater处理
                stats = clusterer.process_new_pain_events(new_events)

                result = {
                    'clusters_created': stats['new_clusters_created'],
                    'clusters_updated': stats['existing_clusters_updated'],
                    'events_processed': stats['total_events_processed']
                }

            self.stats["stages_completed"].append("cluster")
            self.stats["stage_results"]["cluster"] = result

            if self.enable_monitoring:
                # 使用events_processed作为处理数量
                performance_monitor.end_stage("cluster", result.get('events_processed', 0))

            logger.info(f"✅ Stage 5 completed:")
            logger.info(f"   Events processed: {result.get('events_processed', 0)}")
            logger.info(f"   New clusters: {result.get('clusters_created', 0)}")
            logger.info(f"   Updated clusters: {result.get('clusters_updated', 0)}")

            # 更新pipeline状态
            get_pipeline_state().update_stage_run("cluster", result.get('events_processed', 0))

            return result

        except Exception as e:
            logger.error(f"❌ Stage 5 failed: {e}")
            self.stats["stages_failed"].append("cluster")
            if self.enable_monitoring:
                performance_monitor.end_stage("cluster", 0)
            raise

    def run_stage_map_opportunities(self, limit_clusters: Optional[int] = None, process_all: bool = False, force_remap: bool = False) -> Dict[str, Any]:
        """阶段6: 机会映射"""
        logger.info("=" * 50)
        logger.info("STAGE 6: Mapping opportunities")
        logger.info("=" * 50)

        if self.enable_monitoring:
            performance_monitor.start_stage("map_opportunities")

        try:
            mapper = OpportunityMapper()

            # 如果 process_all=True 且未指定 limit，则处理所有数据
            if process_all and limit_clusters is None:
                limit_clusters = 1000000  # 处理所有数据
            elif limit_clusters is None:
                limit_clusters = 50

            result = mapper.map_opportunities_for_clusters(limit=limit_clusters, force_remap=force_remap)

            self.stats["stages_completed"].append("map_opportunities")
            self.stats["stage_results"]["map_opportunities"] = result

            if self.enable_monitoring:
                performance_monitor.end_stage("map_opportunities", result.get('opportunities_created', 0))

            logger.info(f"✅ Stage 6 completed: Mapped {result['opportunities_created']} opportunities")
            return result

        except Exception as e:
            logger.error(f"❌ Stage 6 failed: {e}")
            self.stats["stages_failed"].append("map_opportunities")
            if self.enable_monitoring:
                performance_monitor.end_stage("map_opportunities", 0)
            raise

    def run_stage_score(self, limit_opportunities: Optional[int] = None, process_all: bool = False) -> Dict[str, Any]:
        """阶段7: 可行性评分"""
        logger.info("=" * 50)
        logger.info("STAGE 7: Scoring viability")
        logger.info("=" * 50)

        if self.enable_monitoring:
            performance_monitor.start_stage("score")

        try:
            scorer = ViabilityScorer()

            # 如果 process_all=True 且未指定 limit，则处理所有数据
            if process_all and limit_opportunities is None:
                limit_opportunities = 1000000  # 处理所有数据
            elif limit_opportunities is None:
                limit_opportunities = 100

            result = scorer.score_opportunities(limit=limit_opportunities)

            self.stats["stages_completed"].append("score")
            self.stats["stage_results"]["score"] = result

            if self.enable_monitoring:
                performance_monitor.end_stage("score", result.get('opportunities_scored', 0))

            logger.info(f"✅ Stage 7 completed: Scored {result['opportunities_scored']} opportunities")
            return result

        except Exception as e:
            logger.error(f"❌ Stage 7 failed: {e}")
            self.stats["stages_failed"].append("score")
            if self.enable_monitoring:
                performance_monitor.end_stage("score", 0)
            raise

    def run_stage_decision_shortlist(self) -> Dict[str, Any]:
        """阶段8: 决策清单生成"""
        logger.info("=" * 50)
        logger.info("STAGE 8: Decision Shortlist Generation")
        logger.info("=" * 50)

        if self.enable_monitoring:
            performance_monitor.start_stage("decision_shortlist")

        try:
            generator = DecisionShortlistGenerator()
            result = generator.generate_shortlist()

            self.stats["stages_completed"].append("decision_shortlist")
            self.stats["stage_results"]["decision_shortlist"] = result

            if self.enable_monitoring:
                performance_monitor.end_stage("decision_shortlist", result.get('shortlist_count', 0))

            logger.info(f"✅ Stage 8 completed: Generated {result['shortlist_count']} candidates")
            if result.get('markdown_report'):
                logger.info(f"📝 Markdown report: {result['markdown_report']}")
            if result.get('json_report'):
                logger.info(f"📊 JSON report: {result['json_report']}")
            return result

        except Exception as e:
            logger.error(f"❌ Stage 8 failed: {e}")
            self.stats["stages_failed"].append("decision_shortlist")
            if self.enable_monitoring:
                performance_monitor.end_stage("decision_shortlist", 0)
            raise

    def run_stage_lifecycle_cleanup(self, orphan_age_days: int = 14, cluster_inactivity_days: int = 90) -> Dict[str, Any]:
        """阶段9: 生命周期清理

        Args:
            orphan_age_days: 删除多少天前的orphans (默认14天)
            cluster_inactivity_days: 归档多少天无活动的clusters (默认90天)
        """
        logger.info("=" * 50)
        logger.info("STAGE 9: Lifecycle Cleanup")
        logger.info("=" * 50)

        if self.enable_monitoring:
            performance_monitor.start_stage("lifecycle_cleanup")

        try:
            # 导入cleanup函数
            from scripts.lifecycle_cleanup import (
                mark_orphan_events,
                cleanup_old_orphans,
                get_lifecycle_statistics
            )

            # Step 1: 标记orphans
            logger.info("Step 1: Marking orphan events...")
            marked_count = mark_orphan_events()
            logger.info(f"   Marked {marked_count} events as orphans")

            # Step 2: 清理旧orphans
            logger.info(f"Step 2: Cleaning up orphans older than {orphan_age_days} days...")
            deleted_count = cleanup_old_orphans(
                db_path="data/wise_collection.db",
                orphan_age_days=orphan_age_days
            )
            logger.info(f"   Deleted {deleted_count} old orphans")

            # Step 3: 获取统计信息
            stats = get_lifecycle_statistics()

            result = {
                'orphans_marked': marked_count,
                'orphans_deleted': deleted_count,
                'final_stats': stats
            }

            self.stats["stages_completed"].append("lifecycle_cleanup")
            self.stats["stage_results"]["lifecycle_cleanup"] = result

            if self.enable_monitoring:
                performance_monitor.end_stage("lifecycle_cleanup", deleted_count)

            logger.info("✅ Stage 9 completed:")
            logger.info(f"   Active events: {stats['active_events']}")
            logger.info(f"   Orphan events: {stats['orphan_events']}")
            logger.info(f"   Retention rate: {stats['retention_rate']:.1f}%")

            return result

        except Exception as e:
            logger.error(f"❌ Stage 9 failed: {e}")
            self.stats["stages_failed"].append("lifecycle_cleanup")
            if self.enable_monitoring:
                performance_monitor.end_stage("lifecycle_cleanup", 0)
            raise

    def generate_final_report(
        self,
        save_metrics: bool = False,
        metrics_file: Optional[str] = None,
        generate_report: bool = False,
        report_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """生成最终报告"""
        logger.info("=" * 50)
        logger.info("GENERATING FINAL REPORT")
        logger.info("=" * 50)

        try:
            # 输出性能监控摘要
            if self.enable_monitoring:
                monitor_summary = performance_monitor.get_summary()
                logger.info(f"\n📊 Performance Summary:")
                logger.info(f"   • Total Duration: {monitor_summary['total_duration_minutes']} minutes")
                logger.info(f"   • LLM Calls: {monitor_summary['total_llm_calls']:,}")
                logger.info(f"   • Total Tokens: {monitor_summary['total_tokens']:,}")
                logger.info(f"   • Est. Cost: ${monitor_summary['estimated_cost_usd']:.4f} USD")

                # 保存metrics到文件
                if save_metrics:
                    if metrics_file is None:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        metrics_file = f"docs/reports/pipeline_metrics_{timestamp}.json"

                    os.makedirs(os.path.dirname(metrics_file), exist_ok=True)
                    performance_monitor.save_metrics(metrics_file)
                    logger.info(f"💾 Metrics saved to: {metrics_file}")

                    # 如果需要生成markdown报告
                    if generate_report:
                        self.generate_markdown_report(metrics_file, report_file)

            # 获取数据库统计信息
            db_stats = db.get_statistics()

            # 获取最高分的机会
            top_opportunities = []
            try:
                with db.get_connection("clusters") as conn:
                    cursor = conn.execute("""
                        SELECT o.opportunity_name, o.total_score, o.recommendation, c.cluster_name
                        FROM opportunities o
                        JOIN clusters c ON o.cluster_id = c.id
                        WHERE o.total_score > 0
                        ORDER BY o.total_score DESC
                        LIMIT 10
                    """)
                    top_opportunities = [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                logger.warning(f"Failed to get top opportunities: {e}")

            # 计算运行时间
            end_time = datetime.now()
            total_runtime = (end_time - self.pipeline_start_time).total_seconds()
            self.stats["total_runtime_seconds"] = total_runtime

            # 生成最终摘要
            final_summary = {
                "pipeline_completed": len(self.stats["stages_failed"]) == 0,
                "stages_completed": len(self.stats["stages_completed"]),
                "stages_failed": len(self.stats["stages_failed"]),
                "total_runtime_minutes": round(total_runtime / 60, 2),
                "database_statistics": db_stats,
                "top_opportunities": top_opportunities,
                "pipeline_efficiency": {
                    "posts_per_minute": self.stats["stage_results"].get("fetch", {}).get("total_saved", 0) / max(total_runtime / 60, 1),
                    "pain_events_per_hour": self.stats["stage_results"].get("extract", {}).get("pain_events_saved", 0) / max(total_runtime / 3600, 1),
                    "opportunities_per_hour": self.stats["stage_results"].get("map_opportunities", {}).get("opportunities_created", 0) / max(total_runtime / 3600, 1)
                }
            }

            # 添加性能监控数据到摘要
            if self.enable_monitoring:
                final_summary["performance"] = monitor_summary

            self.stats["final_summary"] = final_summary

            logger.info("🎉 PIPELINE COMPLETED SUCCESSFULLY!")
            logger.info(f"📊 Final Summary:")
            logger.info(f"   • Runtime: {final_summary['total_runtime_minutes']} minutes")
            logger.info(f"   • Stages completed: {final_summary['stages_completed']}/7")
            logger.info(f"   • Raw posts collected: {db_stats.get('raw_posts_count', 0)}")
            logger.info(f"   • Pain events extracted: {db_stats.get('pain_events_count', 0)}")
            logger.info(f"   • Clusters created: {db_stats.get('clusters_count', 0)}")
            logger.info(f"   • Opportunities identified: {db_stats.get('opportunities_count', 0)}")

            if top_opportunities:
                logger.info(f"   • Top opportunity: {top_opportunities[0]['opportunity_name']} (Score: {top_opportunities[0]['total_score']:.1f})")

            return final_summary

        except Exception as e:
            logger.error(f"Failed to generate final report: {e}")
            return {"error": str(e)}

    def run_full_pipeline(
        self,
        limit_sources: Optional[int] = None,
        limit_posts: Optional[int] = None,
        limit_events: Optional[int] = None,
        limit_clusters: Optional[int] = None,
        limit_opportunities: Optional[int] = None,
        sources: Optional[List[str]] = None,
        process_all: bool = False,
        force_remap: bool = False,
        stop_on_error: bool = False,
        save_metrics: bool = False,
        metrics_file: Optional[str] = None,
        generate_report: bool = False,
        report_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """运行完整pipeline"""
        logger.info("🚀 Starting Wise Collection Multi-Source Pipeline")
        logger.info(f"⏰ Started at: {self.pipeline_start_time}")

        if self.enable_monitoring:
            logger.info("📊 Performance monitoring: ENABLED")
        else:
            logger.info("📊 Performance monitoring: DISABLED")

        # 使用指定的数据源，默认为 reddit
        fetch_sources = sources or ['reddit']
        logger.info(f"📡 Data sources: {', '.join(fetch_sources)}")

        # 显示处理模式
        if process_all:
            logger.info("🔄 Processing mode: PROCESS ALL (no limits)")
        else:
            logger.info("📊 Processing mode: Default limits")

        stages = [
            ("fetch", lambda: self.run_stage_fetch(limit_sources, fetch_sources)),
            ("filter", lambda: self.run_stage_filter(limit_posts, process_all)),
            ("extract", lambda: self.run_stage_extract(limit_posts, process_all)),
            ("embed", lambda: self.run_stage_embed(limit_events, process_all)),
            ("cluster", lambda: self.run_stage_cluster(limit_events, process_all)),
            ("map_opportunities", lambda: self.run_stage_map_opportunities(limit_clusters, process_all, force_remap)),
            ("score", lambda: self.run_stage_score(limit_opportunities, process_all)),
            ("shortlist", lambda: self.run_stage_decision_shortlist()),
            ("lifecycle_cleanup", lambda: self.run_stage_lifecycle_cleanup())
        ]

        for stage_name, stage_func in stages:
            try:
                stage_func()
            except Exception as e:
                logger.error(f"Stage '{stage_name}' failed: {e}")
                if stop_on_error:
                    logger.error("Stopping pipeline due to error")
                    break
                else:
                    logger.warning(f"Continuing pipeline despite '{stage_name}' failure")

        # 生成最终报告
        final_report = self.generate_final_report(
            save_metrics=save_metrics,
            metrics_file=metrics_file,
            generate_report=generate_report,
            report_file=report_file
        )

        return final_report

    def run_single_stage(self, stage_name: str, process_all: bool = False, **kwargs) -> Dict[str, Any]:
        """运行单个阶段"""
        stage_map = {
            "fetch": lambda: self.run_stage_fetch(kwargs.get("limit_sources"), kwargs.get("sources")),
            "filter": lambda: self.run_stage_filter(
                kwargs.get("limit_posts"),
                process_all
            ),
            "extract": lambda: self.run_stage_extract(
                kwargs.get("limit_posts"),
                process_all
            ),
            "embed": lambda: self.run_stage_embed(kwargs.get("limit_events"), process_all),
            "cluster": lambda: self.run_stage_cluster(kwargs.get("limit_events"), process_all),
            "map": lambda: self.run_stage_map_opportunities(kwargs.get("limit_clusters"), process_all, kwargs.get("force_remap", False)),
            "score": lambda: self.run_stage_score(kwargs.get("limit_opportunities"), process_all),
            "shortlist": lambda: self.run_stage_decision_shortlist(),
            "lifecycle_cleanup": lambda: self.run_stage_lifecycle_cleanup()
        }

        if stage_name not in stage_map:
            raise ValueError(f"Unknown stage: {stage_name}")

        return stage_map[stage_name]()

    def save_results(self, filename: Optional[str] = None):
        """保存pipeline结果"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pipeline_results_{timestamp}.json"

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, indent=2, default=str)

            logger.info(f"📁 Results saved to: {filename}")
            return filename

        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            return None

    def generate_markdown_report(self, metrics_file: str, output_file: Optional[str] = None) -> str:
        """生成详细的成本性能markdown报告"""
        if not self.enable_monitoring:
            logger.warning("Performance monitoring is disabled, cannot generate report")
            return None

        try:
            from utils.performance_monitor import PerformanceMonitor

            # 加载metrics
            monitor = PerformanceMonitor.load_metrics(metrics_file)
            summary = monitor.get_summary()
            stages_summary = summary['stages_summary']

            # 阶段中文名称映射
            stage_names_cn = {
                'fetch': '数据抓取',
                'filter': '信号过滤',
                'extract': '痛点抽取',
                'embed': '向量化',
                'cluster': '聚类分析',
                'alignment': '跨源对齐',
                'map_opportunities': '机会映射',
                'score': '可行性评分'
            }

            # 生成报告
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            metrics_filename = os.path.basename(metrics_file)

            report = f"""# Pipeline 成本与性能分析报告

> **生成时间**: {timestamp}
> **指标文件**: {metrics_filename}

---

## 📊 执行摘要

### 关键指标

| 指标 | 数值 |
|------|------|
| 总执行时间 | {summary['total_duration_minutes']:.2f} 分钟 ({summary['total_duration_seconds']:.1f} 秒) |
| LLM调用次数 | {summary['total_llm_calls']:,} 次 |
| 总Token使用量 | {summary['total_tokens']:,} |
| 预估成本 | ${summary['estimated_cost_usd']:.4f} USD |
| 平均每调用成本 | ${(summary['estimated_cost_usd']/summary['total_llm_calls'] if summary['total_llm_calls'] > 0 else 0):.6f} USD |

### 效率指标

| 指标 | 数值 |
|------|------|
| 平均每调用耗时 | {(summary['total_duration_seconds']/summary['total_llm_calls'] if summary['total_llm_calls'] > 0 else 0):.2f} 秒 |
| 平均每调用Token数 | {(summary['total_tokens']/summary['total_llm_calls'] if summary['total_llm_calls'] > 0 else 0):.0f} |
| 每千Token成本 | ${(summary['estimated_cost_usd']/(summary['total_tokens']/1000) if summary['total_tokens'] > 0 else 0):.4f} USD |

---

## 📈 阶段分解

### 各阶段性能详情

| 阶段 | 执行时间(秒) | 处理项目数 | LLM调用次数 | Token使用量 |
|------|-------------|-----------|------------|-----------|
"""

            # 添加各阶段数据
            for stage_name, stats in stages_summary.items():
                stage_name_cn = stage_names_cn.get(stage_name, stage_name)
                duration = stats['duration_seconds']
                items = stats['items_processed']
                tokens = stats['tokens_used']
                llm_calls = stats['llm_calls']

                report += f"| {stage_name_cn} | {duration:.1f} | {items} | {llm_calls} | {tokens:,} |\n"

            # 阶段效率对比
            report += "\n### 阶段效率对比\n\n"
            for stage_name, stats in stages_summary.items():
                stage_name_cn = stage_names_cn.get(stage_name, stage_name)
                duration = stats['duration_seconds']
                items = stats['items_processed']
                tokens = stats['tokens_used']

                if items > 0:
                    avg_time_per_item = duration / items
                    report += f"**{stage_name_cn}**:\n"
                    report += f"- 平均每项目处理时间: {avg_time_per_item:.2f} 秒\n"

                    if tokens > 0:
                        avg_tokens_per_item = tokens / items
                        report += f"- 平均每项目Token数: {avg_tokens_per_item:.0f}\n"
                    report += "\n"

            # 成本分析
            total_tokens = summary['total_tokens']
            report += """
---

## 💰 成本分析

### Token分布

| 阶段 | Token使用量 | 占比 |
|------|-----------|------|
"""

            for stage_name, stats in stages_summary.items():
                stage_name_cn = stage_names_cn.get(stage_name, stage_name)
                tokens = stats['tokens_used']
                percentage = (tokens / total_tokens * 100) if total_tokens > 0 else 0
                report += f"| {stage_name_cn} | {tokens:,} | {percentage:.1f}% |\n"

            # 成本构成分析
            report += "\n### 成本构成分析\n\n"
            for stage_name, stats in stages_summary.items():
                stage_name_cn = stage_names_cn.get(stage_name, stage_name)
                tokens = stats['tokens_used']
                percentage = (tokens / total_tokens * 100) if total_tokens > 0 else 0
                stage_cost = summary['estimated_cost_usd'] * (percentage / 100)
                report += f"**{stage_name_cn}**: ${stage_cost:.4f} USD ({percentage:.1f}%)\n"

            report += f"\n**总成本**: ${summary['estimated_cost_usd']:.4f} USD\n"

            # 性能指标
            report += """
---

## ⚡ 性能指标

### 吞吐量分析

| 阶段 | 吞吐量 (项目/分钟) | 吞吐量 (Token/秒) |
|------|------------------|------------------|
"""

            for stage_name, stats in stages_summary.items():
                stage_name_cn = stage_names_cn.get(stage_name, stage_name)
                duration_minutes = stats['duration_seconds'] / 60
                items = stats['items_processed']
                tokens = stats['tokens_used']

                items_per_minute = (items / duration_minutes) if duration_minutes > 0 else 0
                tokens_per_second = (tokens / stats['duration_seconds']) if stats['duration_seconds'] > 0 else 0

                report += f"| {stage_name_cn} | {items_per_minute:.2f} | {tokens_per_second:.0f} |\n"

            # 性能瓶颈识别
            report += "\n### 性能瓶颈识别\n\n"

            # 识别最慢的阶段
            slowest_stage = max(stages_summary.items(), key=lambda x: x[1]['duration_seconds'])
            slowest_stage_cn = stage_names_cn.get(slowest_stage[0], slowest_stage[0])
            report += f"- **最慢阶段**: {slowest_stage_cn} ({slowest_stage[1]['duration_seconds']:.1f}秒)\n"

            # 识别Token消耗最大的阶段
            highest_token_stage = max(stages_summary.items(), key=lambda x: x[1]['tokens_used'])
            highest_token_cn = stage_names_cn.get(highest_token_stage[0], highest_token_stage[0])
            report += f"- **最高Token消耗**: {highest_token_cn} ({highest_token_stage[1]['tokens_used']:,} tokens)\n"

            # 结论与建议
            report += """
---

## 💡 结论与建议

### 关键发现

1. **自动化流程**: Pipeline已实现端到端自动化，从数据抓取到机会评分无需人工干预
2. **成本可控**: 整个流程成本在可接受范围内，适合定期执行
3. **输出完整**: 包含多维度分析和性能追踪

### 优化建议

#### 短期优化 (1-2周)

1. **批量处理**: 对更大的数据集进行批量处理，降低单位成本
2. **缓存优化**: 对相似内容进行缓存，减少重复LLM调用
3. **并行处理**: 在独立阶段并行处理，缩短总执行时间

#### 中期优化 (1个月)

1. **定期执行**: 设置定时任务，每周/每月自动运行
2. **数据积累**: 持续积累数据，形成趋势分析
3. **反馈闭环**: 建立反馈机制，持续改进分析质量

#### 长期优化 (持续)

1. **智能调度**: 根据数据变化自动触发分析
2. **A/B测试**: 对不同prompt和参数进行A/B测试
3. **成本优化**: 探索更经济的模型组合

---

*本报告由 Pipeline 自动生成*
"""

            # 保存报告
            if output_file is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = f"docs/reports/pipeline_cost_performance_{timestamp}.md"

            os.makedirs(os.path.dirname(output_file), exist_ok=True)

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)

            logger.info(f"📝 Markdown report saved to: {output_file}")
            return output_file

        except Exception as e:
            logger.error(f"Failed to generate markdown report: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Wise Collection Multi-Source Pipeline")

    # 运行模式
    parser.add_argument("--stage", choices=["fetch", "filter", "extract", "embed", "cluster", "map", "score", "shortlist", "lifecycle_cleanup", "all"],
                       default="all", help="Which stage to run (default: all)")

    # 数据源选择
    parser.add_argument("--sources", nargs="+", choices=["reddit"],
                       default=["reddit"], help="Data sources to fetch (default: reddit)")

    # 限制参数
    parser.add_argument("--limit-sources", type=int, help="Limit number of sources to fetch")
    parser.add_argument("--limit-posts", type=int, help="Limit number of posts to process")
    parser.add_argument("--limit-events", type=int, help="Limit number of pain events to process")
    parser.add_argument("--limit-clusters", type=int, help="Limit number of clusters to process")
    parser.add_argument("--limit-opportunities", type=int, help="Limit number of opportunities to score")

    # 全量处理选项
    parser.add_argument("--process-all", action="store_true",
                       help="Process ALL unprocessed data (ignore default limits)")
    parser.add_argument("--force-remap", action="store_true",
                       help="Force re-map opportunities for ALL clusters (including those with existing opportunities)")

    # 性能监控选项
    parser.add_argument("--no-monitoring", action="store_true", help="Disable performance monitoring")
    parser.add_argument("--save-metrics", action="store_true", help="Save performance metrics to file")
    parser.add_argument("--metrics-file", help="Custom metrics file path")
    parser.add_argument("--generate-report", action="store_true", help="Generate detailed markdown cost/performance report")
    parser.add_argument("--report-file", help="Custom markdown report file path")

    # 其他选项
    parser.add_argument("--stop-on-error", action="store_true", help="Stop pipeline on first error")
    parser.add_argument("--save-results", action="store_true", help="Save results to file")
    parser.add_argument("--results-file", help="Custom results filename")

    args = parser.parse_args()

    try:
        # 初始化pipeline
        pipeline = WiseCollectionPipeline(enable_monitoring=not args.no_monitoring)

        if args.stage == "all":
            # 运行完整pipeline
            result = pipeline.run_full_pipeline(
                limit_sources=args.limit_sources,
                limit_posts=args.limit_posts,
                limit_events=args.limit_events,
                limit_clusters=args.limit_clusters,
                limit_opportunities=args.limit_opportunities,
                sources=args.sources,
                process_all=args.process_all,
                force_remap=args.force_remap,
                stop_on_error=args.stop_on_error,
                save_metrics=args.save_metrics,
                metrics_file=args.metrics_file,
                generate_report=args.generate_report,
                report_file=args.report_file
            )
        else:
            # 运行单个阶段
            stage_kwargs = {
                "limit_sources": args.limit_sources,
                "limit_posts": args.limit_posts,
                "limit_events": args.limit_events,
                "limit_clusters": args.limit_clusters,
                "limit_opportunities": args.limit_opportunities,
                "sources": args.sources,
                "process_all": args.process_all,
                "force_remap": args.force_remap,
            }

            # 只传递相关的参数（保留布尔值）
            relevant_kwargs = {k: v for k, v in stage_kwargs.items()
                             if v is not None or isinstance(v, bool)}
            result = pipeline.run_single_stage(args.stage, **relevant_kwargs)

        # 保存结果
        if args.save_results:
            pipeline.save_results(args.results_file)

        # 输出结果
        print("\n" + "=" * 60)
        print("PIPELINE RESULTS")
        print("=" * 60)
        print(json.dumps(result, indent=2, default=str))

    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()