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
from pipeline.align_cross_sources import CrossSourceAligner

# 导入工具模块
from utils.db import db
from utils.llm_client import LLMClient

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

    def __init__(self):
        """初始化pipeline"""
        self.pipeline_start_time = datetime.now()
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

        try:
            from pipeline.fetch import MultiSourceFetcher

            # 使用指定的数据源，默认为 reddit + hackernews
            fetch_sources = sources or ['reddit', 'hackernews']
            fetcher = MultiSourceFetcher(sources=fetch_sources)
            result = fetcher.fetch_all(limit_sources=limit_sources)

            self.stats["stages_completed"].append("fetch")
            self.stats["stage_results"]["fetch"] = result

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
            raise

    def run_stage_filter(self, limit_posts: Optional[int] = None) -> Dict[str, Any]:
        """阶段2: 信号过滤"""
        logger.info("=" * 50)
        logger.info("STAGE 2: Filtering pain signals")
        logger.info("=" * 50)

        try:
            filter = PainSignalFilter()

            # 获取未过滤的帖子
            unfiltered_posts = db.get_unprocessed_posts(limit=limit_posts or 1000)

            if not unfiltered_posts:
                logger.info("No posts to filter")
                result = {"processed": 0, "filtered": 0}
            else:
                logger.info(f"Filtering {len(unfiltered_posts)} posts")
                filtered_posts = filter.filter_posts_batch(unfiltered_posts)

                # 保存过滤结果
                saved_count = 0
                for post in filtered_posts:
                    if db.insert_filtered_post(post):
                        saved_count += 1

                result = {
                    "processed": len(unfiltered_posts),
                    "filtered": len(filtered_posts),
                    "saved": saved_count,
                    "filter_stats": filter.get_statistics()
                }

            self.stats["stages_completed"].append("filter")
            self.stats["stage_results"]["filter"] = result

            logger.info(f"✅ Stage 2 completed: Filtered {result['saved']} posts")
            return result

        except Exception as e:
            logger.error(f"❌ Stage 2 failed: {e}")
            self.stats["stages_failed"].append("filter")
            raise

    def run_stage_extract(self, limit_posts: Optional[int] = None) -> Dict[str, Any]:
        """阶段3: 痛点抽取"""
        logger.info("=" * 50)
        logger.info("STAGE 3: Extracting pain points")
        logger.info("=" * 50)

        try:
            extractor = PainPointExtractor()
            result = extractor.process_unextracted_posts(limit=limit_posts or 100)

            self.stats["stages_completed"].append("extract")
            self.stats["stage_results"]["extract"] = result

            logger.info(f"✅ Stage 3 completed: Extracted {result['pain_events_saved']} pain events")
            return result

        except Exception as e:
            logger.error(f"❌ Stage 3 failed: {e}")
            self.stats["stages_failed"].append("extract")
            raise

    def run_stage_embed(self, limit_events: Optional[int] = None) -> Dict[str, Any]:
        """阶段4: 向量化"""
        logger.info("=" * 50)
        logger.info("STAGE 4: Creating embeddings")
        logger.info("=" * 50)

        try:
            embedder = PainEventEmbedder()
            result = embedder.process_missing_embeddings(limit=limit_events or 200)

            self.stats["stages_completed"].append("embed")
            self.stats["stage_results"]["embed"] = result

            logger.info(f"✅ Stage 4 completed: Created {result['embeddings_created']} embeddings")
            return result

        except Exception as e:
            logger.error(f"❌ Stage 4 failed: {e}")
            self.stats["stages_failed"].append("embed")
            raise

    def run_stage_cluster(self, limit_events: Optional[int] = None) -> Dict[str, Any]:
        """阶段5: 聚类"""
        logger.info("=" * 50)
        logger.info("STAGE 5: Clustering pain events")
        logger.info("=" * 50)

        try:
            clusterer = PainEventClusterer()
            result = clusterer.cluster_pain_events(limit=limit_events or 200)

            self.stats["stages_completed"].append("cluster")
            self.stats["stage_results"]["cluster"] = result

            logger.info(f"✅ Stage 5 completed: Created {result['clusters_created']} clusters")
            return result

        except Exception as e:
            logger.error(f"❌ Stage 5 failed: {e}")
            self.stats["stages_failed"].append("cluster")
            raise

    def run_stage_cross_source_alignment(self) -> Dict[str, Any]:
        """阶段5.5: 跨源对齐"""
        logger.info("=" * 50)
        logger.info("STAGE 5.5: Cross-Source Alignment")
        logger.info("=" * 50)

        try:
            # 初始化对齐器
            llm_client = LLMClient()  # Uses default config path
            aligner = CrossSourceAligner(db, llm_client)

            # 执行跨源对齐
            logger.info("Processing cross-source alignment...")
            aligner.process_alignments()

            # 获取对齐结果
            aligned_problems = db.get_aligned_problems()

            result = {
                "aligned_problems_count": len(aligned_problems),
                "aligned_problems": aligned_problems
            }

            self.stats["stages_completed"].append("alignment")
            self.stats["stage_results"]["alignment"] = result

            logger.info(f"✅ Stage 5.5 completed: Found {len(aligned_problems)} aligned problems")

            # 显示对齐摘要
            if aligned_problems:
                logger.info("\nAlignment Summary:")
                logger.info(f"- Total aligned problems: {len(aligned_problems)}")
                for problem in aligned_problems[:3]:  # 显示前3个
                    logger.info(f"  {problem['aligned_problem_id']}: {problem['core_problem'][:100]}...")
                    logger.info(f"  Sources: {', '.join(problem['sources'])}")
            else:
                logger.info("No cross-source alignments found in this run")

            return result

        except Exception as e:
            logger.error(f"❌ Stage 5.5 failed: {e}")
            self.stats["stages_failed"].append("alignment")
            raise

    def run_stage_map_opportunities(self, limit_clusters: Optional[int] = None) -> Dict[str, Any]:
        """阶段6: 机会映射"""
        logger.info("=" * 50)
        logger.info("STAGE 6: Mapping opportunities")
        logger.info("=" * 50)

        try:
            mapper = OpportunityMapper()
            result = mapper.map_opportunities_for_clusters(limit=limit_clusters or 50)

            self.stats["stages_completed"].append("map_opportunities")
            self.stats["stage_results"]["map_opportunities"] = result

            logger.info(f"✅ Stage 6 completed: Mapped {result['opportunities_created']} opportunities")
            return result

        except Exception as e:
            logger.error(f"❌ Stage 6 failed: {e}")
            self.stats["stages_failed"].append("map_opportunities")
            raise

    def run_stage_score(self, limit_opportunities: Optional[int] = None) -> Dict[str, Any]:
        """阶段7: 可行性评分"""
        logger.info("=" * 50)
        logger.info("STAGE 7: Scoring viability")
        logger.info("=" * 50)

        try:
            scorer = ViabilityScorer()
            result = scorer.score_opportunities(limit=limit_opportunities or 100)

            self.stats["stages_completed"].append("score")
            self.stats["stage_results"]["score"] = result

            logger.info(f"✅ Stage 7 completed: Scored {result['opportunities_scored']} opportunities")
            return result

        except Exception as e:
            logger.error(f"❌ Stage 7 failed: {e}")
            self.stats["stages_failed"].append("score")
            raise

    def generate_final_report(self) -> Dict[str, Any]:
        """生成最终报告"""
        logger.info("=" * 50)
        logger.info("GENERATING FINAL REPORT")
        logger.info("=" * 50)

        try:
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
        stop_on_error: bool = False
    ) -> Dict[str, Any]:
        """运行完整pipeline"""
        logger.info("🚀 Starting Wise Collection Multi-Source Pipeline")
        logger.info(f"⏰ Started at: {self.pipeline_start_time}")

        # 使用指定的数据源，默认为 reddit + hackernews
        fetch_sources = sources or ['reddit', 'hackernews']
        logger.info(f"📡 Data sources: {', '.join(fetch_sources)}")

        stages = [
            ("fetch", lambda: self.run_stage_fetch(limit_sources, fetch_sources)),
            ("filter", lambda: self.run_stage_filter(limit_posts)),
            ("extract", lambda: self.run_stage_extract(limit_posts)),
            ("embed", lambda: self.run_stage_embed(limit_events)),
            ("cluster", lambda: self.run_stage_cluster(limit_events)),
            ("alignment", lambda: self.run_stage_cross_source_alignment()),
            ("map_opportunities", lambda: self.run_stage_map_opportunities(limit_clusters)),
            ("score", lambda: self.run_stage_score(limit_opportunities))
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
        final_report = self.generate_final_report()

        return final_report

    def run_single_stage(self, stage_name: str, **kwargs) -> Dict[str, Any]:
        """运行单个阶段"""
        stage_map = {
            "fetch": lambda: self.run_stage_fetch(kwargs.get("limit_sources"), kwargs.get("sources")),
            "filter": lambda: self.run_stage_filter(kwargs.get("limit_posts")),
            "extract": lambda: self.run_stage_extract(kwargs.get("limit_posts")),
            "embed": lambda: self.run_stage_embed(kwargs.get("limit_events")),
            "cluster": lambda: self.run_stage_cluster(kwargs.get("limit_events")),
            "alignment": lambda: self.run_stage_cross_source_alignment(),
            "map": lambda: self.run_stage_map_opportunities(kwargs.get("limit_clusters")),
            "score": lambda: self.run_stage_score(kwargs.get("limit_opportunities"))
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

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Wise Collection Multi-Source Pipeline")

    # 运行模式
    parser.add_argument("--stage", choices=["fetch", "filter", "extract", "embed", "cluster", "alignment", "map", "score", "all"],
                       default="all", help="Which stage to run (default: all)")

    # 数据源选择
    parser.add_argument("--sources", nargs="+", choices=["reddit", "hackernews"],
                       default=["reddit", "hackernews"], help="Data sources to fetch (default: reddit hackernews)")

    # 限制参数
    parser.add_argument("--limit-sources", type=int, help="Limit number of sources to fetch")
    parser.add_argument("--limit-posts", type=int, help="Limit number of posts to process")
    parser.add_argument("--limit-events", type=int, help="Limit number of pain events to process")
    parser.add_argument("--limit-clusters", type=int, help="Limit number of clusters to process")
    parser.add_argument("--limit-opportunities", type=int, help="Limit number of opportunities to score")

    # 其他选项
    parser.add_argument("--stop-on-error", action="store_true", help="Stop pipeline on first error")
    parser.add_argument("--save-results", action="store_true", help="Save results to file")
    parser.add_argument("--results-file", help="Custom results filename")

    args = parser.parse_args()

    try:
        # 初始化pipeline
        pipeline = WiseCollectionPipeline()

        if args.stage == "all":
            # 运行完整pipeline
            result = pipeline.run_full_pipeline(
                limit_sources=args.limit_sources,
                limit_posts=args.limit_posts,
                limit_events=args.limit_events,
                limit_clusters=args.limit_clusters,
                limit_opportunities=args.limit_opportunities,
                sources=args.sources,
                stop_on_error=args.stop_on_error
            )
        else:
            # 运行单个阶段
            stage_kwargs = {
                "limit_sources": args.limit_sources,
                "limit_posts": args.limit_posts,
                "limit_events": args.limit_events,
                "limit_clusters": args.limit_clusters,
                "limit_opportunities": args.limit_opportunities,
                "sources": args.sources
            }

            # 只传递相关的参数
            relevant_kwargs = {k: v for k, v in stage_kwargs.items() if v is not None}
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