# Reddit Pain Finder - 代码汇总

生成时间: 2025-12-15 20:43:12

本文档包含 reddit_pain_finder 项目的核心代码文件：
- Pipeline处理模块 (pipeline/)
- 工具模块 (utils/)
- 主要执行脚本



================================================================================
文件: run_pipeline.py
================================================================================

```python
#!/usr/bin/env python3
"""
Reddit Pain Point Finder - Main Pipeline Runner
主要的pipeline执行脚本 - 一键运行整个痛点发现流程
"""
import os
import sys
import argparse
import logging
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional

# 设置项目根目录
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# 导入pipeline模块
from pipeline.fetch import RedditPainFetcher
from pipeline.filter_signal import PainSignalFilter
from pipeline.extract_pain import PainPointExtractor
from pipeline.embed import PainEventEmbedder
from pipeline.cluster import PainEventClusterer
from pipeline.score_viability import ViabilityScorer
from pipeline.map_opportunity import OpportunityMapper

# 导入工具模块
from utils.db import db

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

class RedditPainPipeline:
    """Reddit痛点发现Pipeline"""

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

    def run_stage_fetch(self, limit_subreddits: Optional[int] = None) -> Dict[str, Any]:
        """阶段1: 数据抓取"""
        logger.info("=" * 50)
        logger.info("STAGE 1: Fetching Reddit posts")
        logger.info("=" * 50)

        try:
            fetcher = RedditPainFetcher()
            result = fetcher.fetch_all(limit_subreddits=limit_subreddits)

            self.stats["stages_completed"].append("fetch")
            self.stats["stage_results"]["fetch"] = result

            logger.info(f"✅ Stage 1 completed: Found {result['total_saved']} posts")
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
        limit_subreddits: Optional[int] = None,
        limit_posts: Optional[int] = None,
        limit_events: Optional[int] = None,
        limit_clusters: Optional[int] = None,
        limit_opportunities: Optional[int] = None,
        stop_on_error: bool = False
    ) -> Dict[str, Any]:
        """运行完整pipeline"""
        logger.info("🚀 Starting Reddit Pain Point Finder Pipeline")
        logger.info(f"⏰ Started at: {self.pipeline_start_time}")

        stages = [
            ("fetch", lambda: self.run_stage_fetch(limit_subreddits)),
            ("filter", lambda: self.run_stage_filter(limit_posts)),
            ("extract", lambda: self.run_stage_extract(limit_posts)),
            ("embed", lambda: self.run_stage_embed(limit_events)),
            ("cluster", lambda: self.run_stage_cluster(limit_events)),
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
            "fetch": lambda: self.run_stage_fetch(kwargs.get("limit_subreddits")),
            "filter": lambda: self.run_stage_filter(kwargs.get("limit_posts")),
            "extract": lambda: self.run_stage_extract(kwargs.get("limit_posts")),
            "embed": lambda: self.run_stage_embed(kwargs.get("limit_events")),
            "cluster": lambda: self.run_stage_cluster(kwargs.get("limit_events")),
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
    parser = argparse.ArgumentParser(description="Reddit Pain Point Finder Pipeline")

    # 运行模式
    parser.add_argument("--stage", choices=["fetch", "filter", "extract", "embed", "cluster", "map", "score", "all"],
                       default="all", help="Which stage to run (default: all)")

    # 限制参数
    parser.add_argument("--limit-subreddits", type=int, help="Limit number of subreddits to fetch")
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
        pipeline = RedditPainPipeline()

        if args.stage == "all":
            # 运行完整pipeline
            result = pipeline.run_full_pipeline(
                limit_subreddits=args.limit_subreddits,
                limit_posts=args.limit_posts,
                limit_events=args.limit_events,
                limit_clusters=args.limit_clusters,
                limit_opportunities=args.limit_opportunities,
                stop_on_error=args.stop_on_error
            )
        else:
            # 运行单个阶段
            stage_kwargs = {
                "limit_subreddits": args.limit_subreddits,
                "limit_posts": args.limit_posts,
                "limit_events": args.limit_events,
                "limit_clusters": args.limit_clusters,
                "limit_opportunities": args.limit_opportunities
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
```


================================================================================
文件: pain_point_analyzer.py
================================================================================

```python
#!/usr/bin/env python3
"""
痛点应用分析器

针对每个痛点聚类生成综合分析报告，包含：
1. 痛点分析
2. 应用设计方案
3. 可执行机会清单

每个聚类生成一个独立的markdown文件
"""

import os
import sqlite3
import json
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional
import re
from pathlib import Path
import logging
import sys

# 加载.env文件
def load_env():
    """加载.env文件"""
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # 输出到控制台
        logging.FileHandler('pain_point_analyzer.log', encoding='utf-8')  # 同时输出到文件
    ]
)

logger = logging.getLogger(__name__)

# 加载环境变量
logger.info("开始加载环境变量...")
load_env()
logger.info("环境变量加载完成")


class PainPointAnalyzer:
    def __init__(self):
        """初始化分析器"""
        logger.info("初始化 PainPointAnalyzer...")

        self.base_url = os.getenv('Siliconflow_Base_URL', 'https://api.siliconflow.cn/v1')
        self.api_key = os.getenv('Siliconflow_KEY')
        self.model = os.getenv('Siliconflow_AI_Model_Default', 'deepseek-ai/DeepSeek-V3.2')

        logger.info(f"配置信息: base_url={self.base_url}, model={self.model}")
        logger.info(f"API key {'已设置' if self.api_key else '未设置'}")

        if not self.api_key:
            logger.error("SiliconFlow API key not found in environment variables")
            raise ValueError("SiliconFlow API key not found in environment variables")

        # 创建输出目录
        self.output_dir = "pain_analysis_reports"
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info(f"输出目录已创建: {self.output_dir}")

        print(f"🔧 初始化分析器")
        print(f"   • API模型: {self.model}")
        print(f"   • 输出目录: {self.output_dir}")

    def get_db_connection(self, db_file: str) -> sqlite3.Connection:
        """获取数据库连接"""
        logger.debug(f"尝试连接数据库: {db_file}")

        if not os.path.exists(db_file):
            logger.error(f"数据库文件不存在: {db_file}")
            raise FileNotFoundError(f"数据库文件不存在: {db_file}")

        try:
            conn = sqlite3.connect(db_file)
            conn.row_factory = sqlite3.Row
            logger.debug(f"数据库连接成功: {db_file}")
            return conn
        except Exception as e:
            logger.error(f"连接数据库失败: {db_file}, 错误: {e}")
            raise

    def call_llm(self, prompt: str, temperature: float = 0.3, max_retries: int = 3) -> str:
        """调用LLM"""
        logger.info(f"开始调用LLM: model={self.model}, temperature={temperature}, max_retries={max_retries}")
        logger.debug(f"prompt长度: {len(prompt)} 字符")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一位资深的产品分析师和技术顾问，专门分析用户痛点并设计创新的解决方案。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": 4000
        }

        for attempt in range(max_retries):
            try:
                print(f"  🤖 调用LLM (尝试 {attempt + 1}/{max_retries})...")
                logger.info(f"尝试第 {attempt + 1}/{max_retries} 次LLM调用")

                url = f"{self.base_url}/chat/completions"
                logger.debug(f"请求URL: {url}")

                response = requests.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=180  # 增加到3分钟
                )

                logger.debug(f"响应状态码: {response.status_code}")

                response.raise_for_status()
                result = response.json()

                if 'choices' not in result or len(result['choices']) == 0:
                    logger.error("LLM响应中没有choices字段")
                    return "LLM响应格式错误: 没有choices"

                content = result['choices'][0]['message']['content'].strip()
                logger.debug(f"LLM响应长度: {len(content)} 字符")
                print(f"  ✅ LLM响应成功")
                logger.info("LLM调用成功")
                return content

            except requests.exceptions.Timeout:
                error_msg = f"LLM调用超时 (尝试 {attempt + 1}/{max_retries})"
                logger.warning(error_msg)
                print(f"  ⚠️ {error_msg}")
                if attempt < max_retries - 1:
                    continue
                logger.error(f"LLM调用超时，已重试{max_retries}次")
                return f"LLM调用超时: 已重试{max_retries}次"

            except requests.exceptions.HTTPError as e:
                error_msg = f"HTTP错误: {e}"
                logger.error(error_msg)
                logger.error(f"响应内容: {response.text if 'response' in locals() else 'N/A'}")
                print(f"  ❌ {error_msg}")
                if attempt < max_retries - 1:
                    print(f"  🔄 正在重试...")
                    continue
                return f"LLM HTTP错误: {str(e)}"

            except Exception as e:
                error_msg = f"LLM调用失败: {e}"
                logger.error(error_msg)
                import traceback
                logger.error(traceback.format_exc())
                print(f"  ❌ {error_msg}")
                if attempt < max_retries - 1:
                    print(f"  🔄 正在重试...")
                    continue
                return f"LLM调用失败: {str(e)}"

    def get_top_clusters(self, min_score: float = 0.8, limit: int = 10) -> List[Dict]:
        """获取高分聚类"""
        logger.info(f"获取高分聚类: min_score={min_score}, limit={limit}")
        clusters = []

        try:
            conn = self.get_db_connection('data/clusters.db')
            cursor = conn.cursor()

            logger.debug("执行聚类查询SQL...")

            cursor.execute("""
                SELECT c.id, c.cluster_name, c.cluster_description, c.avg_pain_score,
                       c.cluster_size, c.pain_event_ids,
                       COUNT(o.id) as opportunity_count,
                       MAX(o.total_score) as max_opportunity_score,
                       GROUP_CONCAT(o.opportunity_name, ' | ') as opportunity_names
                FROM clusters c
                LEFT JOIN opportunities o ON c.id = o.cluster_id
                GROUP BY c.id
                HAVING opportunity_count > 0 AND max_opportunity_score >= ?
                ORDER BY max_opportunity_score DESC, c.avg_pain_score DESC
                LIMIT ?
            """, (min_score, limit))

            logger.debug(f"查询执行完成，开始处理结果...")
            rows = cursor.fetchall()
            logger.info(f"查询到 {len(rows)} 个聚类")

            for i, row in enumerate(rows, 1):
                logger.debug(f"处理第 {i}/{len(rows)} 个聚类: {row['cluster_name'][:50]}...")
                # 获取该聚类的所有机会
                logger.debug(f"获取聚类 {row['id']} 的机会数据...")
                cursor.execute("""
                    SELECT opportunity_name, description, total_score, recommendation,
                           current_tools, missing_capability, why_existing_fail,
                           target_users, killer_risks
                    FROM opportunities
                    WHERE cluster_id = ?
                    ORDER BY total_score DESC
                """, (row['id'],))

                opportunities = []
                opp_rows = cursor.fetchall()
                logger.debug(f"聚类 {row['id']} 有 {len(opp_rows)} 个机会")

                for opp_row in opp_rows:
                    opportunities.append({
                        'name': opp_row['opportunity_name'],
                        'description': opp_row['description'],
                        'score': opp_row['total_score'],
                        'recommendation': opp_row['recommendation'],
                        'current_tools': opp_row['current_tools'],
                        'missing_capability': opp_row['missing_capability'],
                        'why_existing_fail': opp_row['why_existing_fail'],
                        'target_users': opp_row['target_users'],
                        'killer_risks': json.loads(opp_row['killer_risks']) if opp_row['killer_risks'] else []
                    })

                # 获取痛点事件样本
                try:
                    pain_event_ids = json.loads(row['pain_event_ids'])
                    logger.debug(f"聚类 {row['id']} 痛点事件IDs: {len(pain_event_ids)} 个")
                    sample_pains = self.get_sample_pain_events(pain_event_ids[:5])
                except json.JSONDecodeError as e:
                    logger.warning(f"聚类 {row['id']} pain_event_ids JSON解析失败: {e}")
                    sample_pains = []

                clusters.append({
                    'id': row['id'],
                    'name': row['cluster_name'],
                    'description': row['cluster_description'],
                    'avg_pain_score': row['avg_pain_score'],
                    'cluster_size': row['cluster_size'],
                    'opportunity_count': row['opportunity_count'],
                    'max_opportunity_score': row['max_opportunity_score'],
                    'opportunities': opportunities,
                    'sample_pains': sample_pains
                })

            conn.close()
            logger.info(f"成功获取 {len(clusters)} 个聚类数据")
            return clusters

        except Exception as e:
            logger.error(f"获取聚类数据失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def get_sample_pain_events(self, pain_event_ids: List[int]) -> List[Dict]:
        """获取痛点事件样本"""
        logger.debug(f"获取 {len(pain_event_ids)} 个痛点事件样本: {pain_event_ids}")
        pains = []

        if not pain_event_ids:
            logger.warning("pain_event_ids 为空，返回空列表")
            return []

        try:
            conn = self.get_db_connection('data/pain_events.db')
            cursor = conn.cursor()

            placeholders = ','.join(['?' for _ in pain_event_ids])
            logger.debug(f"执行痛点事件查询，IDs: {pain_event_ids}")

            cursor.execute(f"""
                SELECT problem, current_workaround, frequency, emotional_signal, mentioned_tools
                FROM pain_events
                WHERE id IN ({placeholders})
            """, pain_event_ids)

            rows = cursor.fetchall()
            logger.debug(f"查询到 {len(rows)} 个痛点事件")

            for row in rows:
                pains.append({
                    'problem': row['problem'],
                    'workaround': row['current_workaround'],
                    'frequency': row['frequency'],
                    'emotion': row['emotional_signal'],
                    'tools': row['mentioned_tools']
                })

            conn.close()
            logger.debug(f"成功获取 {len(pains)} 个痛点事件")
            return pains

        except Exception as e:
            logger.error(f"获取痛点事件失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def generate_basic_analysis(self, cluster: Dict) -> str:
        """生成基础分析（当LLM调用失败时）"""
        pain_context = "\n".join([
            f"• {pain['problem']}" + chr(10) + f"  当前解决方案: {pain['workaround']}" + chr(10) + f"  发生频率: {pain['frequency']}" + chr(10) + f"  情绪信号: {pain['emotion']}"
            for pain in cluster['sample_pains']
        ])

        opp_analysis = ""
        for opp in cluster['opportunities'][:3]:
            opp_analysis += f"""
### {opp['name']} (评分: {opp['score']:.2f})

**问题描述**: {opp['description']}

**关键机会分析**:
- 市场需求: 通过{cluster['cluster_size']}个相关帖子验证了强烈需求
- 目标用户: {opp['target_users'] or '中小企业、个人开发者、自由职业者'}
- 竞争优势: {opp['missing_capability'] or '填补现有工具的功能空白'}

**MVP功能建议**:
1. 核心功能实现{opp['current_tools'] and f"，整合{opp['current_tools']}的工作流"}
2. 简化用户界面，降低学习成本
3. 快速部署和集成能力

**商业化建议**:
- 免费基础版吸引初始用户
- Pro版本月费$10-20
- 企业定制版支持
"""

        return f"""## 痛点深度分析

### 核心问题
{cluster['description']}

### 影响范围
- 受影响用户群体: {cluster['cluster_size']}个真实用户反馈
- 痛点强度: {cluster['avg_pain_score']:.2f}/1.0

### 典型痛点事件
{pain_context}

## 市场机会评估

### 市场规模
基于Reddit讨论热度，该问题影响了大量用户，具有明确的付费意愿。

### 机会数量
已识别{cluster['opportunity_count']}个具体机会，最高评分{cluster['max_opportunity_score']:.2f}

## 产品设计方案

{opp_analysis}

## 可执行行动计划

### 立即行动（1个月内）
1. 验证目标用户需求，进行深度用户访谈
2. 开发最小可行产品(MVP)原型
3. 建立用户反馈渠道

### 短期目标（3个月内）
1. 发布MVP版本并获取首批100个用户
2. 基于反馈迭代产品功能
3. 探索盈利模式

### 成功指标
- 用户留存率 > 60%
- 月活跃用户增长 > 20%
- NPS得分 > 40
"""

    def analyze_cluster(self, cluster: Dict) -> str:
        """分析单个聚类并生成完整报告"""

        # 构建分析prompt
        pain_context = "\n".join([
            f"• {pain['problem']} (当前解决方案: {pain['workaround']}, 频率: {pain['frequency']}, 情绪: {pain['emotion']})"
            for pain in cluster['sample_pains']
        ])

        opportunities_context = "\n".join([
            f"• {opp['name']} (评分: {opp['score']:.2f})"
            f"  描述: {opp['description'][:100]}..."
            for opp in cluster['opportunities'][:3]
        ])

        prompt = f"""
请分析以下痛点聚类并生成综合报告：

## 聚类信息
- **聚类名称**: {cluster['name']}
- **聚类描述**: {cluster['description']}
- **痛点数量**: {cluster['cluster_size']}
- **平均痛点强度**: {cluster['avg_pain_score']:.2f}
- **机会数量**: {cluster['opportunity_count']}

## 典型痛点样本
{pain_context}

## 已识别的机会
{opportunities_context}

## 分析要求
请按照以下结构生成详细分析报告：

### 1. 痛点深度分析
- 核心问题本质
- 影响范围和严重程度
- 用户特征和使用场景
- 现有解决方案的不足

### 2. 市场机会评估
- 市场规模估算
- 用户付费意愿
- 竞争格局分析
- 进入壁垒评估

### 3. 产品设计方案
- MVP功能定义
- 技术架构建议
- 用户体验设计要点
- 差异化竞争策略

### 4. 商业化路径
- 盈利模式设计
- 获客策略
- 定价策略
- 发展路线图

### 5. 可执行行动计划
- 近期行动项（1-3个月）
- 中期目标（3-6个月）
- 关键成功指标
- 风险应对措施

请确保分析深入、具体且可操作。使用markdown格式输出。
"""

        print(f"🤖 正在分析聚类: {cluster['name'][:50]}...")

        # 尝试调用LLM
        analysis = self.call_llm(prompt, temperature=0.4)

        # 如果LLM调用失败，使用基础分析
        if "LLM调用" in analysis:
            print(f"  ⚠️ 使用基础分析替代")
            analysis = self.generate_basic_analysis(cluster)

        return analysis

    def generate_cluster_report(self, cluster: Dict, analysis: str) -> str:
        """生成聚类报告文件"""
        logger.info(f"生成聚类报告: {cluster['name'][:50]}...")

        # 清理文件名
        safe_name = re.sub(r'[^\w\s-]', '', cluster['name']).strip()
        safe_name = re.sub(r'[-\s]+', '_', safe_name)
        filename = f"{safe_name}_opportunity_analysis.md"
        filepath = os.path.join(self.output_dir, filename)

        logger.debug(f"报告文件路径: {filepath}")

        # 构建完整报告
        report_content = f"""# {cluster['name']} - 机会分析报告

> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> **聚类ID**: {cluster['id']}
> **痛点数量**: {cluster['cluster_size']}
> **平均痛点强度**: {cluster['avg_pain_score']:.2f}
> **机会数量**: {cluster['opportunity_count']}

---

## 📊 聚类概览

**聚类描述**: {cluster['description']}

### 🎯 顶级机会
{chr(10).join([f"- **{opp['name']}** (评分: {opp['score']:.2f})" for opp in cluster['opportunities'][:5]])}

---

## 🔍 深度分析

{analysis}

---

## 📋 原始数据

### 典型痛点事件
{chr(10).join([f"**问题**: {pain['problem']}" + chr(10) + f"- 当前方案: {pain['workaround']}" + chr(10) + f"- 发生频率: {pain['frequency']}" + chr(10) + f"- 情绪信号: {pain['emotion']}" + chr(10) for pain in cluster['sample_pains']])}

### 已识别机会详情
{chr(10).join([f"**{opp['name']}** (评分: {opp['score']:.2f})" + chr(10) + f"- 描述: {opp['description']}" + chr(10) + f"- 推荐建议: {opp['recommendation']}" + chr(10) + (f"- 目标用户: {opp['target_users']}" if opp['target_users'] else "") + chr(10) for opp in cluster['opportunities']])}

---

*本报告由 Reddit Pain Point Finder 自动生成*
"""

        # 写入文件
        try:
            logger.debug(f"开始写入报告文件: {filepath}")
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report_content)
            logger.info(f"报告生成成功: {filepath}")
            print(f"✅ 报告已生成: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"报告生成失败: {filepath}, 错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            print(f"❌ 报告生成失败: {e}")
            return None

    def generate_summary_index(self, report_files: List[str]) -> str:
        """生成总结索引文件"""
        logger.info(f"生成总结索引，包含 {len(report_files)} 个报告")

        index_content = f"""# 痛点机会分析报告索引

> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> **分析数量**: {len(report_files)}

---

## 📈 分析概览

本次共分析了 {len(report_files)} 个高价值痛点聚类，每个聚类都包含详细的痛点分析、应用设计方案和可执行行动计划。

---

## 📋 报告列表

{chr(10).join([f"- [{os.path.basename(f)}]({f})" for f in report_files])}

---

## 🎯 下一步行动建议

1. **优先级排序**: 根据机会评分和市场规模确定产品开发优先级
2. **用户验证**: 针对Top 3机会进行用户访谈和需求验证
3. **MVP开发**: 选择最高价值的机会启动MVP开发
4. **持续监控**: 定期更新Reddit数据，跟踪新的痛点趋势

---

*使用方法: 点击上方链接查看具体的机会分析报告*
"""

        index_path = os.path.join(self.output_dir, "README.md")
        try:
            logger.debug(f"开始写入索引文件: {index_path}")
            with open(index_path, 'w', encoding='utf-8') as f:
                f.write(index_content)
            logger.info(f"索引文件生成成功: {index_path}")
            print(f"📑 索引文件已生成: {index_path}")
            return index_path
        except Exception as e:
            logger.error(f"索引文件生成失败: {index_path}, 错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            print(f"❌ 索引文件生成失败: {e}")
            return None

    def run_analysis(self, min_score: float = 0.8, limit: int = 10):
        """运行完整分析"""
        logger.info(f"开始运行完整分析: min_score={min_score}, limit={limit}")
        print(f"\n🚀 开始痛点机会分析...")
        print(f"   • 最低机会评分: {min_score}")
        print(f"   • 最大分析数量: {limit}")
        print("="*60)

        # 获取聚类数据
        logger.info("开始获取聚类数据...")
        clusters = self.get_top_clusters(min_score, limit)
        if not clusters:
            logger.warning("未找到符合条件的聚类数据")
            print("❌ 未找到符合条件的聚类数据")
            return

        logger.info(f"成功获取 {len(clusters)} 个聚类")
        print(f"📊 找到 {len(clusters)} 个高价值聚类")

        # 分析每个聚类
        report_files = []
        for i, cluster in enumerate(clusters, 1):
            logger.info(f"开始分析第 {i}/{len(clusters)} 个聚类: {cluster['name'][:50]}...")
            print(f"\n[{i}/{len(clusters)}] 分析聚类: {cluster['name'][:50]}...")

            # 执行分析
            logger.debug("执行聚类分析...")
            analysis = self.analyze_cluster(cluster)

            # 生成报告
            logger.debug("生成聚类报告...")
            report_path = self.generate_cluster_report(cluster, analysis)
            if report_path:
                report_files.append(report_path)
                logger.info(f"报告已添加到列表: {report_path}")

            logger.info(f"聚类 {i} 分析完成")
            print(f"✅ 完成: {cluster['name'][:50]}")

        # 生成索引文件
        if report_files:
            logger.info("开始生成总结索引...")
            self.generate_summary_index(report_files)

        logger.info(f"分析完成，生成了 {len(report_files)} 个报告")
        print(f"\n🎉 分析完成！")
        print(f"   • 生成报告: {len(report_files)} 份")
        print(f"   • 输出目录: {self.output_dir}")
        print(f"   • 查看索引: {self.output_dir}/README.md")


def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("痛点分析器开始运行")
    logger.info("=" * 50)

    try:
        logger.info("初始化 PainPointAnalyzer...")
        analyzer = PainPointAnalyzer()
        logger.info("开始运行分析...")
        analyzer.run_analysis(min_score=0.8, limit=15)
        logger.info("程序执行完成")
    except Exception as e:
        logger.error(f"程序执行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        print(f"❌ 程序执行失败: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
```


================================================================================
文件: analyze_pain_points.py
================================================================================

```python
#!/usr/bin/env python3
"""
快速启动痛点分析脚本
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pain_point_analyzer import PainPointAnalyzer

if __name__ == "__main__":
    print("🎯 Reddit Pain Point Finder - 痛点机会分析器")
    print("=" * 60)

    # 可以通过命令行参数调整
    min_score = 0.8
    limit = 15

    if len(sys.argv) > 1:
        try:
            min_score = float(sys.argv[1])
        except:
            pass

    if len(sys.argv) > 2:
        try:
            limit = int(sys.argv[2])
        except:
            pass

    print(f"参数设置:")
    print(f"  • 最低机会评分: {min_score}")
    print(f"  • 最大分析数量: {limit}")
    print()

    try:
        analyzer = PainPointAnalyzer()
        analyzer.run_analysis(min_score=min_score, limit=limit)
    except KeyboardInterrupt:
        print("\n\n⚠️  分析被用户中断")
    except Exception as e:
        print(f"\n❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()
```


================================================================================
文件: pipeline/cluster.py
================================================================================

```python
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
```


================================================================================
文件: pipeline/embed.py
================================================================================

```python
"""
Embed module for Reddit Pain Point Finder
痛点事件向量化模块 - 为聚类做准备
"""
import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from utils.embedding import embedding_client
from utils.db import db

logger = logging.getLogger(__name__)

class PainEventEmbedder:
    """痛点事件向量化器"""

    def __init__(self):
        """初始化向量化器"""
        self.stats = {
            "total_processed": 0,
            "embeddings_created": 0,
            "errors": 0,
            "processing_time": 0.0,
            "cache_hits": 0
        }

    def _create_embedding_text(self, pain_event: Dict[str, Any]) -> str:
        """创建用于嵌入的文本"""
        text_parts = []

        # 核心要素
        if pain_event.get("actor"):
            text_parts.append(pain_event["actor"])

        if pain_event.get("context"):
            text_parts.append(pain_event["context"])

        if pain_event.get("problem"):
            text_parts.append(pain_event["problem"])

        if pain_event.get("current_workaround"):
            text_parts.append(pain_event["current_workaround"])

        # 用连接符保持语义结构
        embedding_text = " | ".join(text_parts)

        # 检查文本长度
        if len(embedding_text) > 2000:
            logger.warning(f"Embedding text too long ({len(embedding_text)} chars), truncating")
            # 优先保留problem和context
            core_text = f"{pain_event.get('context', '')} | {pain_event.get('problem', '')}"
            if len(core_text) > 1000:
                # 进一步截断
                embedding_text = core_text[:1000]
            else:
                embedding_text = core_text

        return embedding_text

    def embed_single_event(self, pain_event: Dict[str, Any]) -> Optional[List[float]]:
        """为单个痛点事件创建嵌入向量"""
        try:
            # 创建嵌入文本
            embedding_text = self._create_embedding_text(pain_event)

            if not embedding_text:
                logger.warning(f"Empty embedding text for pain event {pain_event.get('id')}")
                return None

            # 创建嵌入向量
            embedding = embedding_client.create_embedding(embedding_text)

            self.stats["embeddings_created"] += 1
            return embedding

        except Exception as e:
            logger.error(f"Failed to create embedding for pain event {pain_event.get('id')}: {e}")
            self.stats["errors"] += 1
            return None

    def save_embedding(self, pain_event_id: int, embedding: List[float]) -> bool:
        """保存嵌入向量到数据库"""
        try:
            success = db.insert_pain_embedding(
                pain_event_id=pain_event_id,
                embedding_vector=embedding,
                model_name=embedding_client.model_name
            )
            return success

        except Exception as e:
            logger.error(f"Failed to save embedding for pain event {pain_event_id}: {e}")
            return False

    def process_pain_events_batch(self, pain_events: List[Dict[str, Any]], batch_size: int = 20) -> int:
        """批量处理痛点事件的向量化"""
        logger.info(f"Creating embeddings for {len(pain_events)} pain events")

        start_time = time.time()
        saved_count = 0

        for i, event in enumerate(pain_events):
            if i % 10 == 0:
                logger.info(f"Processed {i}/{len(pain_events)} pain events")

            # 创建嵌入向量
            embedding = self.embed_single_event(event)
            if embedding is None:
                continue

            # 保存到数据库
            if self.save_embedding(event["id"], embedding):
                saved_count += 1

            # 批量处理延迟
            if i % batch_size == 0 and i > 0:
                time.sleep(1)  # 避免API限制

        # 更新统计信息
        processing_time = time.time() - start_time
        self.stats["total_processed"] = len(pain_events)
        self.stats["processing_time"] = processing_time

        # 添加嵌入客户端统计
        embedding_stats = embedding_client.get_embedding_statistics()
        self.stats["cache_hits"] = embedding_stats.get("cache_hits", 0)

        logger.info(f"Embedding complete: {saved_count}/{len(pain_events)} embeddings saved")
        logger.info(f"Processing time: {processing_time:.2f}s")

        return saved_count

    def process_missing_embeddings(self, limit: int = 100) -> Dict[str, Any]:
        """处理缺失嵌入向量的痛点事件"""
        logger.info(f"Processing up to {limit} pain events without embeddings")

        try:
            # 获取没有嵌入向量的痛点事件
            pain_events = db.get_pain_events_without_embeddings(limit=limit)

            if not pain_events:
                logger.info("No pain events without embeddings found")
                return {"processed": 0, "embeddings_created": 0}

            logger.info(f"Found {len(pain_events)} pain events to embed")

            # 批量创建嵌入向量
            saved_count = self.process_pain_events_batch(pain_events)

            return {
                "processed": len(pain_events),
                "embeddings_created": saved_count,
                "embedding_stats": self.get_statistics()
            }

        except Exception as e:
            logger.error(f"Failed to process missing embeddings: {e}")
            raise

    def get_embedding_statistics(self) -> Dict[str, Any]:
        """获取向量化统计信息"""
        stats = self.stats.copy()

        if stats["total_processed"] > 0:
            stats["success_rate"] = stats["embeddings_created"] / stats["total_processed"]
            stats["processing_rate"] = stats["total_processed"] / max(stats["processing_time"], 1)
        else:
            stats["success_rate"] = 0
            stats["processing_rate"] = 0

        # 添加嵌入客户端统计
        embedding_stats = embedding_client.get_embedding_statistics()
        stats["embedding_client_stats"] = embedding_stats

        return stats

    def reset_statistics(self):
        """重置统计信息"""
        self.stats = {
            "total_processed": 0,
            "embeddings_created": 0,
            "errors": 0,
            "processing_time": 0.0,
            "cache_hits": 0
        }

    def verify_embeddings(self, limit: int = 50) -> Dict[str, Any]:
        """验证嵌入向量的质量"""
        logger.info(f"Verifying {limit} embeddings")

        try:
            # 获取所有有嵌入向量的痛点事件
            pain_events = db.get_all_pain_events_with_embeddings()

            if len(pain_events) > limit:
                pain_events = pain_events[:limit]

            if not pain_events:
                return {"verified": 0, "issues": []}

            issues = []
            verified_count = 0

            for event in pain_events:
                try:
                    embedding = event.get("embedding_vector")
                    if not embedding:
                        issues.append(f"Event {event['id']}: Missing embedding vector")
                        continue

                    # 检查维度
                    if len(embedding) == 0:
                        issues.append(f"Event {event['id']}: Empty embedding vector")
                        continue

                    # 检查是否包含有效数值
                    if not all(isinstance(x, (int, float)) for x in embedding):
                        issues.append(f"Event {event['id']}: Invalid embedding data types")
                        continue

                    # 检查是否全为零（异常）
                    if all(abs(x) < 1e-6 for x in embedding):
                        issues.append(f"Event {event['id']}: All-zero embedding vector")
                        continue

                    verified_count += 1

                except Exception as e:
                    issues.append(f"Event {event.get('id', 'unknown')}: Verification error - {e}")

            logger.info(f"Embedding verification complete: {verified_count}/{len(pain_events)} passed")

            return {
                "verified": verified_count,
                "total": len(pain_events),
                "issues": issues
            }

        except Exception as e:
            logger.error(f"Failed to verify embeddings: {e}")
            return {"verified": 0, "issues": [f"Verification failed: {e}"]}

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.stats.copy()
        if stats["total_processed"] > 0:
            stats["success_rate"] = stats["embeddings_created"] / stats["total_processed"]
        else:
            stats["success_rate"] = 0.0
        return stats

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Create embeddings for pain events")
    parser.add_argument("--limit", type=int, default=100, help="Limit number of pain events to process")
    parser.add_argument("--verify", action="store_true", help="Verify existing embeddings")
    parser.add_argument("--batch-size", type=int, default=20, help="Batch size for processing")
    args = parser.parse_args()

    try:
        logger.info("Starting pain event embedding...")

        embedder = PainEventEmbedder()

        if args.verify:
            # 验证现有嵌入
            result = embedder.verify_embeddings(limit=args.limit)
            logger.info(f"Verification result: {result}")
        else:
            # 处理缺失的嵌入
            result = embedder.process_missing_embeddings(limit=args.limit)

            logger.info(f"""
=== Embedding Summary ===
Pain events processed: {result['processed']}
Embeddings created: {result['embeddings_created']}
Embedding stats: {result['embedding_stats']}
""")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()
```


================================================================================
文件: pipeline/extract_pain.py
================================================================================

```python
"""
Extract Pain module for Reddit Pain Point Finder
痛点事件抽取模块 - 使用LLM进行结构化抽取
"""
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import time

from utils.llm_client import llm_client
from utils.db import db

logger = logging.getLogger(__name__)

class PainPointExtractor:
    """痛点事件抽取器"""

    def __init__(self):
        """初始化抽取器"""
        self.stats = {
            "total_processed": 0,
            "total_pain_events": 0,
            "extraction_errors": 0,
            "avg_confidence": 0.0,
            "processing_time": 0.0
        }

    def _extract_from_single_post(self, post_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从单个帖子抽取痛点事件"""
        try:
            title = post_data.get("title", "")
            body = post_data.get("body", "")
            subreddit = post_data.get("subreddit", "")
            upvotes = post_data.get("score", 0)
            comments_count = post_data.get("num_comments", 0)

            # 调用LLM进行抽取
            response = llm_client.extract_pain_points(
                title=title,
                body=body,
                subreddit=subreddit,
                upvotes=upvotes,
                comments_count=comments_count
            )

            extraction_result = response["content"]
            pain_events = extraction_result.get("pain_events", [])

            # 为每个痛点事件添加元数据
            for event in pain_events:
                event.update({
                    "post_id": post_data["id"],
                    "subreddit": subreddit,
                    "original_score": upvotes,
                    "extraction_model": response["model"],
                    "extraction_timestamp": datetime.now().isoformat(),
                    "confidence": event.get("confidence", 0.0)
                })

            self.stats["total_pain_events"] += len(pain_events)
            logger.debug(f"Extracted {len(pain_events)} pain events from post {post_data['id']}")

            return pain_events

        except Exception as e:
            logger.error(f"Failed to extract pain from post {post_data.get('id')}: {e}")
            self.stats["extraction_errors"] += 1
            return []

    def _validate_pain_event(self, pain_event: Dict[str, Any]) -> bool:
        """验证痛点事件的质量"""
        try:
            # 检查必需字段
            required_fields = ["problem", "post_id"]
            for field in required_fields:
                if not pain_event.get(field):
                    logger.warning(f"Missing required field '{field}' in pain event")
                    return False

            # 检查问题描述长度
            problem = pain_event.get("problem", "")
            if len(problem) < 10:
                logger.warning(f"Problem description too short: {problem}")
                return False

            if len(problem) > 1000:
                logger.warning(f"Problem description too long: {len(problem)} characters")
                return False

            # 检查置信度
            confidence = pain_event.get("confidence", 0.0)
            if confidence < 0.3:
                logger.warning(f"Low confidence pain event: {confidence}")
                return False

            # 检查是否过于泛泛
            generic_problems = [
                "it's slow", "it's bad", "it doesn't work", "it's broken",
                "i don't like it", "it's annoying", "it's frustrating"
            ]
            problem_lower = problem.lower()
            for generic in generic_problems:
                if problem_lower == generic:
                    logger.warning(f"Too generic problem: {problem}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating pain event: {e}")
            return False

    def _enhance_pain_event(self, pain_event: Dict[str, Any], post_data: Dict[str, Any]) -> Dict[str, Any]:
        """增强痛点事件信息"""
        try:
            enhanced = pain_event.copy()

            # 添加帖子上下文
            enhanced.update({
                "post_title": post_data.get("title", ""),
                "post_category": post_data.get("category", ""),
                "post_pain_score": post_data.get("pain_score", 0.0),
                "post_comments": post_data.get("num_comments", 0)
            })

            # 分析痛点类型
            problem_text = enhanced.get("problem", "").lower()
            context_text = enhanced.get("context", "").lower()
            full_text = f"{problem_text} {context_text}"

            # 痛点类型分类
            pain_types = {
                "workflow": ["workflow", "process", "flow", "pipeline", "automation"],
                "technical": ["code", "programming", "development", "technical", "bug"],
                "efficiency": ["slow", "time", "inefficient", "productivity", "performance"],
                "complexity": ["complex", "complicated", "difficult", "hard", "confusing"],
                "integration": ["integration", "connect", "api", "compatibility", "sync"],
                "cost": ["expensive", "cost", "price", "pricing", "budget"],
                "user_experience": ["ui", "ux", "interface", "usability", "experience"],
                "data": ["data", "database", "storage", "backup", "analysis"]
            }

            detected_types = []
            for pain_type, keywords in pain_types.items():
                if any(keyword in full_text for keyword in keywords):
                    detected_types.append(pain_type)

            enhanced["pain_types"] = detected_types
            enhanced["primary_pain_type"] = detected_types[0] if detected_types else "general"

            # 提取提到的工具
            mentioned_tools = enhanced.get("mentioned_tools", [])
            if not isinstance(mentioned_tools, list):
                mentioned_tools = []

            # 从文本中提取更多工具名（简单规则）
            common_tools = [
                "excel", "google sheets", "slack", "discord", "jira", "trello", "asana",
                "github", "gitlab", "vscode", "intellij", "docker", "kubernetes", "aws",
                "azure", "gcp", "mysql", "postgresql", "mongodb", "redis", "figma",
                "sketch", "photoshop", "wordpress", "shopify", "salesforce"
            ]

            for tool in common_tools:
                if tool in full_text and tool not in mentioned_tools:
                    mentioned_tools.append(tool)

            enhanced["mentioned_tools"] = mentioned_tools

            # 分析频率
            frequency = enhanced.get("frequency", "").lower()
            if "daily" in frequency or "every day" in frequency:
                enhanced["frequency_score"] = 10
            elif "weekly" in frequency or "every week" in frequency:
                enhanced["frequency_score"] = 8
            elif "monthly" in frequency or "every month" in frequency:
                enhanced["frequency_score"] = 6
            elif "often" in frequency or "frequent" in frequency:
                enhanced["frequency_score"] = 7
            elif "sometimes" in frequency or "occasional" in frequency:
                enhanced["frequency_score"] = 4
            elif "rarely" in frequency:
                enhanced["frequency_score"] = 2
            else:
                enhanced["frequency_score"] = 5  # 默认中等频率

            return enhanced

        except Exception as e:
            logger.error(f"Error enhancing pain event: {e}")
            return pain_event

    def extract_from_posts_batch(self, posts: List[Dict[str, Any]], batch_size: int = 10) -> List[Dict[str, Any]]:
        """批量从帖子中抽取痛点事件"""
        logger.info(f"Extracting pain points from {len(posts)} posts")

        all_pain_events = []
        start_time = time.time()

        for i, post in enumerate(posts):
            if i % 10 == 0:
                logger.info(f"Processed {i}/{len(posts)} posts")

            # 抽取痛点事件
            pain_events = self._extract_from_single_post(post)

            # 验证和增强每个痛点事件
            for event in pain_events:
                if self._validate_pain_event(event):
                    enhanced_event = self._enhance_pain_event(event, post)
                    all_pain_events.append(enhanced_event)

            # 添加延迟避免API限制
            time.sleep(0.5)

        # 更新统计信息
        processing_time = time.time() - start_time
        self.stats["total_processed"] = len(posts)
        self.stats["processing_time"] = processing_time

        if all_pain_events:
            avg_confidence = sum(event.get("confidence", 0) for event in all_pain_events) / len(all_pain_events)
            self.stats["avg_confidence"] = avg_confidence

        logger.info(f"Extraction complete: {len(all_pain_events)} pain events from {len(posts)} posts")
        logger.info(f"Processing time: {processing_time:.2f}s, Avg per post: {processing_time/len(posts):.2f}s")

        return all_pain_events

    def save_pain_events(self, pain_events: List[Dict[str, Any]]) -> int:
        """保存痛点事件到数据库"""
        saved_count = 0

        for event in pain_events:
            try:
                # 准备数据库记录
                event_data = {
                    "post_id": event["post_id"],
                    "actor": event.get("actor", ""),
                    "context": event.get("context", ""),
                    "problem": event["problem"],
                    "current_workaround": event.get("current_workaround", ""),
                    "frequency": event.get("frequency", ""),
                    "emotional_signal": event.get("emotional_signal", ""),
                    "mentioned_tools": event.get("mentioned_tools", []),
                    "extraction_confidence": event.get("confidence", 0.0)
                }

                # 保存到数据库
                pain_event_id = db.insert_pain_event(event_data)
                if pain_event_id:
                    saved_count += 1
                    logger.debug(f"Saved pain event {pain_event_id}: {event['problem'][:50]}...")

            except Exception as e:
                logger.error(f"Failed to save pain event: {e}")

        logger.info(f"Saved {saved_count}/{len(pain_events)} pain events to database")
        return saved_count

    def process_unextracted_posts(self, limit: int = 100) -> Dict[str, Any]:
        """处理未抽取的帖子"""
        logger.info(f"Processing up to {limit} unextracted posts")

        try:
            # 获取未处理的过滤帖子
            unextracted_posts = db.get_filtered_posts(limit=limit, min_pain_score=0.3)

            if not unextracted_posts:
                logger.info("No unextracted posts found")
                return {"processed": 0, "pain_events": 0}

            logger.info(f"Found {len(unextracted_posts)} posts to extract from")

            # 抽取痛点事件
            pain_events = self.extract_from_posts_batch(unextracted_posts)

            # 保存到数据库
            saved_count = self.save_pain_events(pain_events)

            return {
                "processed": len(unextracted_posts),
                "pain_events_extracted": len(pain_events),
                "pain_events_saved": saved_count,
                "extraction_stats": self.get_statistics()
            }

        except Exception as e:
            logger.error(f"Failed to process unextracted posts: {e}")
            raise

    def get_statistics(self) -> Dict[str, Any]:
        """获取抽取统计信息"""
        stats = self.stats.copy()
        if stats["total_processed"] > 0:
            stats["avg_events_per_post"] = stats["total_pain_events"] / stats["total_processed"]
            stats["processing_rate"] = stats["total_processed"] / max(stats["processing_time"], 1)
        else:
            stats["avg_events_per_post"] = 0
            stats["processing_rate"] = 0

        # 添加LLM客户端统计
        llm_stats = llm_client.get_statistics()
        stats["llm_stats"] = llm_stats

        return stats

    def reset_statistics(self):
        """重置统计信息"""
        self.stats = {
            "total_processed": 0,
            "total_pain_events": 0,
            "extraction_errors": 0,
            "avg_confidence": 0.0,
            "processing_time": 0.0
        }

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Extract pain points from filtered Reddit posts")
    parser.add_argument("--limit", type=int, default=100, help="Limit number of posts to process")
    parser.add_argument("--min-score", type=float, default=0.3, help="Minimum pain score threshold")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for processing")
    args = parser.parse_args()

    try:
        logger.info("Starting pain point extraction...")

        extractor = PainPointExtractor()

        # 处理未抽取的帖子
        result = extractor.process_unextracted_posts(limit=args.limit)

        logger.info(f"""
=== Extraction Summary ===
Posts processed: {result['processed']}
Pain events extracted: {result['pain_events_extracted']}
Pain events saved: {result['pain_events_saved']}
Extraction stats: {result['extraction_stats']}
""")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()
```


================================================================================
文件: pipeline/fetch.py
================================================================================

```python
"""
Fetch module for Reddit Pain Point Finder
基于原有reddit_collection.py优化的Reddit数据抓取模块
"""
import os
import json
import sys
import time
import logging
import praw
import yaml
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 导入工具模块
try:
    from utils.db import db
except ImportError:
    logger.warning("Could not import db utility, will use local file storage")

class RedditPainFetcher:
    """Reddit痛点数据抓取器"""

    def __init__(self, config_path: str = "config/subreddits.yaml"):
        """初始化抓取器"""
        self.config = self._load_config(config_path)
        self.reddit_client = self._init_reddit_client()
        self.processed_posts = set()
        self.stats = {
            "total_fetched": 0,
            "total_saved": 0,
            "filtered_out": 0,
            "errors": 0,
            "start_time": None
        }

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise

    def _init_reddit_client(self) -> praw.Reddit:
        """初始化Reddit客户端"""
        try:
            # 从环境变量获取API凭证
            client_id = os.getenv('REDDIT_CLIENT_ID')
            client_secret = os.getenv('REDDIT_CLIENT_SECRET')

            if not client_id or not client_secret:
                raise ValueError("Reddit API credentials not found in environment variables")

            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent="python:PainPointFinder:v1.0",
                read_only=True
            )

            # 测试认证
            test_subreddit = reddit.subreddit('test')
            test_subreddit.display_name
            logger.info("Reddit authentication successful")

            return reddit

        except Exception as e:
            logger.error(f"Failed to initialize Reddit client: {e}")
            raise

    def _load_processed_posts(self):
        """加载已处理的帖子ID"""
        try:
            # 尝试从数据库加载
            if 'db' in globals():
                # 从数据库获取已处理的帖子ID
                with db.get_connection("raw") as conn:
                    cursor = conn.execute("SELECT id FROM posts")
                    self.processed_posts = {row[0] for row in cursor.fetchall()}
            else:
                # 从文件加载（备用方案）
                processed_file = "data/processed_posts.json"
                if os.path.exists(processed_file):
                    with open(processed_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.processed_posts = set(data.get("processed_ids", []))

            logger.info(f"Loaded {len(self.processed_posts)} previously processed post IDs")

        except Exception as e:
            logger.error(f"Failed to load processed posts: {e}")
            self.processed_posts = set()

    def _save_processed_posts(self):
        """保存已处理的帖子ID"""
        try:
            if 'db' in globals():
                # 数据库模式不需要额外保存，因为每条记录都单独存储
                pass
            else:
                # 保存到文件（备用方案）
                processed_file = "data/processed_posts.json"
                os.makedirs(os.path.dirname(processed_file), exist_ok=True)
                with open(processed_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "processed_ids": list(self.processed_posts),
                        "last_updated": datetime.now().isoformat()
                    }, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save processed posts: {e}")

    def _build_search_query(self, subreddit_config: Dict[str, Any]) -> str:
        """构建搜索查询"""
        search_focus = subreddit_config.get("search_focus", [])
        pain_keywords = self.config.get("pain_keywords", {})

        query_parts = []
        for category in search_focus:
            if category in pain_keywords:
                # 使用引号确保精确匹配
                category_keywords = pain_keywords[category][:5]  # 限制关键词数量
                quoted_keywords = [f'"{kw}"' for kw in category_keywords]
                query_parts.append(f"({' OR '.join(quoted_keywords)})")

        return " OR ".join(query_parts) if query_parts else ""

    def _calculate_pain_score(self, submission, subreddit_config: Dict[str, Any]) -> float:
        """计算帖子痛点分数"""
        score = 0.0

        # 1. 质量基础分
        thresholds = subreddit_config.get("thresholds", {})
        min_upvotes = thresholds.get("min_upvotes", 5)
        min_comments = thresholds.get("min_comments", 3)

        if submission.score >= min_upvotes:
            score += 0.3
        if submission.num_comments >= min_comments:
            score += 0.2

        # 2. 痛点关键词匹配
        title = (submission.title or "").lower()
        body = (submission.selftext or "").lower()
        full_text = f"{title} {body}"

        pain_keywords = self.config.get("pain_keywords", {})
        keyword_matches = 0

        for category_keywords in pain_keywords.values():
            for keyword in category_keywords:
                if keyword.lower() in full_text:
                    keyword_matches += 1
                    score += 0.1

        # 3. 长度分析（更长的帖子可能包含更多痛点细节）
        if len(full_text) > 200:
            score += 0.1
        if len(full_text) > 500:
            score += 0.1

        # 4. 情绪信号检测（简单规则）
        emotion_indicators = ["frustrated", "annoying", "struggling", "can't", "doesn't work", "broken"]
        emotion_count = sum(1 for indicator in emotion_indicators if indicator in full_text)
        score += emotion_count * 0.05

        return min(score, 1.0)  # 限制在0-1范围内

    def _is_pain_post(self, submission, subreddit_config: Dict[str, Any]) -> bool:
        """判断是否为痛点帖子"""
        # 1. 基础质量检查
        if submission.score < subreddit_config.get("min_upvotes", 5):
            return False
        if submission.num_comments < subreddit_config.get("min_comments", 3):
            return False

        # 2. 痛点关键词检查
        title = (submission.title or "").lower()
        body = (submission.selftext or "").lower()
        full_text = f"{title} {body}"

        pain_keywords = self.config.get("pain_keywords", {})
        keyword_matches = 0

        for category_keywords in pain_keywords.values():
            for keyword in category_keywords:
                if keyword.lower() in full_text:
                    keyword_matches += 1
                    if keyword_matches >= 1:  # 至少匹配一个关键词
                        return True

        # 3. 排除模式检查
        exclude_patterns = self.config.get("exclude_patterns", {})
        for pattern_category, patterns in exclude_patterns.items():
            for pattern in patterns:
                if pattern.lower() in full_text:
                    logger.debug(f"Excluded post due to {pattern_category}: {pattern}")
                    return False

        return False

    def _extract_post_data(self, submission, subreddit_config: Dict[str, Any]) -> Dict[str, Any]:
        """提取帖子数据"""
        try:
            # 获取评论
            comments = []
            try:
                submission.comment_sort = "top"
                submission.comments.replace_more(limit=0)
                for comment in submission.comments.list()[:20]:  # 获取前20条评论
                    if hasattr(comment, 'author') and comment.author:
                        comments.append({
                            "author": comment.author.name,
                            "body": comment.body,
                            "score": comment.score
                        })
            except Exception as e:
                logger.warning(f"Failed to fetch comments for {submission.id}: {e}")

            # 计算痛点分数
            pain_score = self._calculate_pain_score(submission, subreddit_config)

            return {
                "id": submission.id,
                "title": submission.title,
                "body": submission.selftext,
                "subreddit": subreddit_config["name"],
                "category": subreddit_config["category"],
                "url": submission.url,
                "score": submission.score,
                "num_comments": submission.num_comments,
                "upvote_ratio": getattr(submission, 'upvote_ratio', 0.0),
                "is_self": getattr(submission, 'is_self', False),
                "created_utc": submission.created_utc,
                "author": submission.author.name if submission.author else "[deleted]",
                "comments": comments,
                "pain_score": pain_score,
                "collected_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to extract data for submission {submission.id}: {e}")
            return None

    def _process_submission(self, submission, subreddit_config: Dict[str, Any]) -> bool:
        """处理单个帖子"""
        try:
            # 检查是否已处理
            if submission.id in self.processed_posts:
                return False

            # 检查是否为痛点帖子
            if not self._is_pain_post(submission, subreddit_config):
                self.stats["filtered_out"] += 1
                return False

            # 提取帖子数据
            post_data = self._extract_post_data(submission, subreddit_config)
            if not post_data:
                self.stats["errors"] += 1
                return False

            # 保存到数据库
            if 'db' in globals():
                success = db.insert_raw_post(post_data)
            else:
                # 备用文件存储方案
                success = self._save_post_to_file(post_data)

            if success:
                self.processed_posts.add(submission.id)
                self.stats["total_saved"] += 1
                logger.info(f"Saved post: {submission.title[:60]}... (Score: {submission.score}, Pain: {post_data['pain_score']:.2f})")
                return True
            else:
                self.stats["errors"] += 1
                return False

        except Exception as e:
            logger.error(f"Failed to process submission: {e}")
            self.stats["errors"] += 1
            return False

    def _save_post_to_file(self, post_data: Dict[str, Any]) -> bool:
        """保存帖子到文件（备用方案）"""
        try:
            output_dir = "data/raw_posts"
            os.makedirs(output_dir, exist_ok=True)
            file_path = os.path.join(output_dir, f"{post_data['id']}.json")

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(post_data, f, indent=2, ensure_ascii=False)

            return True
        except Exception as e:
            logger.error(f"Failed to save post to file: {e}")
            return False

    def fetch_subreddit(self, subreddit_config: Dict[str, Any]) -> int:
        """抓取单个子版块"""
        subreddit_name = subreddit_config["name"]
        category = subreddit_config["category"]
        methods = subreddit_config.get("methods", ["hot"])

        logger.info(f"Fetching from r/{subreddit_name} (Category: {category})")

        try:
            subreddit = self.reddit_client.subreddit(subreddit_name)
            total_found = 0

            # 构建搜索查询
            search_query = self._build_search_query(subreddit_config)
            if search_query:
                logger.debug(f"Search query for r/{subreddit_name}: {search_query}")

            # 获取帖子限制
            max_results = self.config.get("search_strategy", {}).get("max_results_per_method", 100)

            for method in methods:
                logger.debug(f"Using method: {method}")

                try:
                    submissions = []

                    if method == "hot":
                        submissions = subreddit.hot(limit=max_results)
                    elif method == "new":
                        submissions = subreddit.new(limit=max_results)
                    elif method == "rising":
                        submissions = subreddit.rising(limit=max_results)
                    elif method == "controversial":
                        submissions = subreddit.controversial('week', limit=max_results)
                    elif method.startswith("top_"):
                        time_filter = method.split("_", 1)[1] if "_" in method else "week"
                        submissions = subreddit.top(time_filter=time_filter, limit=max_results)
                    elif method == "search" and search_query:
                        submissions = subreddit.search(search_query, sort='new', limit=max_results)
                    else:
                        logger.warning(f"Unknown method: {method}")
                        continue

                    # 处理帖子
                    method_count = 0
                    for submission in submissions:
                        if self._process_submission(submission, subreddit_config):
                            method_count += 1

                    total_found += method_count
                    logger.info(f"Method {method}: found {method_count} posts in r/{subreddit_name}")

                    # 添加延迟避免API限制
                    time.sleep(1)

                except Exception as e:
                    logger.error(f"Error with method {method} in r/{subreddit_name}: {e}")
                    continue

            return total_found

        except Exception as e:
            logger.error(f"Failed to fetch subreddit r/{subreddit_name}: {e}")
            return 0

    def fetch_all(self, limit_subreddits: Optional[int] = None) -> Dict[str, Any]:
        """抓取所有配置的子版块"""
        self.stats["start_time"] = datetime.now()

        logger.info("Starting Reddit pain point fetching...")

        # 加载已处理的帖子
        self._load_processed_posts()

        # 从配置中构建 subreddit 列表
        subreddits = []

        # 处理所有分组中的 subreddits
        for group_name, group_data in self.config.items():
            if group_name in ["ignore", "search_strategy"]:
                continue  # 跳过忽略列表和搜索策略配置

            if isinstance(group_data, dict):
                for subreddit_name, subreddit_config in group_data.items():
                    if isinstance(subreddit_config, dict):
                        # 构建期望的配置格式
                        subreddit_data = {
                            "name": subreddit_name,
                            "category": group_name,
                            "min_upvotes": subreddit_config.get("min_upvotes", 0),
                            "min_comments": subreddit_config.get("min_comments", 0),
                            "methods": ["hot", "new", "top_week"]  # 默认使用这些方法
                        }
                        subreddits.append(subreddit_data)

        # 如果指定了限制，则截取列表
        if limit_subreddits:
            subreddits = subreddits[:limit_subreddits]

        logger.info(f"Will fetch from {len(subreddits)} subreddits")

        total_found = 0
        for i, subreddit_config in enumerate(subreddits, 1):
            logger.info(f"Processing subreddit {i}/{len(subreddits)}")
            found = self.fetch_subreddit(subreddit_config)
            total_found += found

        # 保存已处理的帖子
        self._save_processed_posts()

        # 计算运行时间
        runtime = datetime.now() - self.stats["start_time"]

        # 更新统计
        self.stats["total_fetched"] = total_found
        self.stats["runtime_seconds"] = runtime.total_seconds()

        # 输出总结
        logger.info(f"""
=== Fetch Summary ===
Total subreddits processed: {len(subreddits)}
Total posts found: {total_found}
Total posts saved: {self.stats["total_saved"]}
Posts filtered out: {self.stats["filtered_out"]}
Errors encountered: {self.stats["errors"]}
Runtime: {runtime}
Posts per minute: {self.stats["total_saved"] / max(runtime.total_seconds() / 60, 1):.1f}
""")

        return self.stats.copy()

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Fetch Reddit posts for pain point discovery")
    parser.add_argument("--limit", type=int, help="Limit number of subreddits to process")
    parser.add_argument("--config", default="config/subreddits.yaml", help="Config file path")
    args = parser.parse_args()

    try:
        fetcher = RedditPainFetcher(args.config)
        stats = fetcher.fetch_all(limit_subreddits=args.limit)

        # 输出JSON格式的统计信息（用于脚本集成）
        print(json.dumps(stats, indent=2))

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```


================================================================================
文件: pipeline/filter_signal.py
================================================================================

```python
"""
Filter Signal module for Reddit Pain Point Finder
痛点信号过滤模块 - 冷血守门员
"""
import os
import json
import logging
import re
import yaml
from typing import List, Dict, Any, Set, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class PainSignalFilter:
    """痛点信号过滤器"""

    def __init__(self, config_path: str = "config/thresholds.yaml"):
        """初始化过滤器"""
        self.thresholds = self._load_thresholds(config_path)
        self.subreddits_config = self._load_subreddits_config("config/subreddits.yaml")
        self.stats = {
            "total_processed": 0,
            "passed_filter": 0,
            "filtered_out": 0,
            "filter_reasons": {}
        }

    def _load_thresholds(self, config_path: str) -> Dict[str, Any]:
        """加载阈值配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load thresholds from {config_path}: {e}")
            return {}

    def _load_subreddits_config(self, config_path: str) -> Dict[str, Any]:
        """加载子版块配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load subreddits config from {config_path}: {e}")
            return {}

    def _check_quality_thresholds(self, post_data: Dict[str, Any]) -> Tuple[bool, str]:
        """检查质量阈值"""
        quality_config = self.thresholds.get("reddit_quality", {})
        base_thresholds = quality_config.get("base", {})

        score = post_data.get("score", 0)
        comments = post_data.get("num_comments", 0)
        upvote_ratio = post_data.get("upvote_ratio", 0.0)
        text_length = len(post_data.get("title", "") + " " + post_data.get("body", ""))

        # 检查基础阈值
        if score < base_thresholds.get("min_upvotes", 5):
            return False, f"Too few upvotes: {score} < {base_thresholds.get('min_upvotes')}"

        if comments < base_thresholds.get("min_comments", 3):
            return False, f"Too few comments: {comments} < {base_thresholds.get('min_comments')}"

        if upvote_ratio < base_thresholds.get("min_upvote_ratio", 0.1):
            return False, f"Too low upvote ratio: {upvote_ratio:.2f} < {base_thresholds.get('min_upvote_ratio')}"

        if text_length < base_thresholds.get("min_post_length", 50):
            return False, f"Post too short: {text_length} < {base_thresholds.get('min_post_length')}"

        if text_length > base_thresholds.get("max_post_length", 5000):
            return False, f"Post too long: {text_length} > {base_thresholds.get('max_post_length')}"

        return True, "Passed quality thresholds"

    def _check_pain_keywords(self, post_data: Dict[str, Any]) -> Tuple[bool, List[str], float]:
        """检查痛点关键词"""
        title = (post_data.get("title", "")).lower()
        body = (post_data.get("body", "")).lower()
        full_text = f"{title} {body}"

        pain_keywords = self.subreddits_config.get("pain_keywords", {})
        matched_keywords = []
        keyword_scores = {}

        # 统计各类别关键词匹配
        for category, keywords in pain_keywords.items():
            category_matches = 0
            category_weight = {"frustration": 1.0, "inefficiency": 0.8, "complexity": 0.7, "workflow": 0.9, "cost": 0.6}.get(category, 0.5)

            for keyword in keywords:
                if keyword.lower() in full_text:
                    matched_keywords.append(f"{category}:{keyword}")
                    category_matches += 1
                    keyword_scores[keyword] = category_weight

            # 计算该类别的得分
            if category_matches > 0:
                keyword_scores[f"category_{category}"] = category_matches * category_weight

        # 计算总痛点分数
        total_score = sum(score for score in keyword_scores.values() if isinstance(score, (int, float)))

        # 标准化分数（0-1范围）
        normalized_score = min(total_score / 5.0, 1.0)  # 假设5分为满分

        return len(matched_keywords) > 0, matched_keywords, normalized_score

    def _check_pain_patterns(self, post_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """检查痛点句式模式"""
        title = (post_data.get("title", "")).lower()
        body = (post_data.get("body", "")).lower()
        full_text = f"{title} {body}"

        pain_config = self.thresholds.get("pain_signal", {})
        required_patterns = pain_config.get("pain_patterns", {}).get("required_patterns", [])
        strong_signals = pain_config.get("pain_patterns", {}).get("strong_signals", [])

        matched_patterns = []
        matched_strong = []

        # 检查必须匹配的句式
        for pattern in required_patterns:
            if pattern.lower() in full_text:
                matched_patterns.append(pattern)

        # 检查强化信号句式
        for pattern in strong_signals:
            if pattern.lower() in full_text:
                matched_strong.append(pattern)

        # 判断是否通过模式检查
        min_pattern_matches = pain_config.get("pain_patterns", {}).get("min_pattern_matches", 1)
        min_strong_signals = pain_config.get("pain_patterns", {}).get("min_strong_signals", 0)

        has_required = len(matched_patterns) >= min_pattern_matches
        has_strong = len(matched_strong) >= min_strong_signals

        all_matches = matched_patterns + matched_strong

        return (has_required or has_strong), all_matches

    def _check_exclusion_patterns(self, post_data: Dict[str, Any]) -> Tuple[bool, str]:
        """检查排除模式"""
        title = (post_data.get("title", "")).lower()
        body = (post_data.get("body", "")).lower()
        full_text = f"{title} {body}"

        exclude_patterns = self.subreddits_config.get("exclude_patterns", {})

        for category, patterns in exclude_patterns.items():
            for pattern in patterns:
                if pattern.lower() in full_text:
                    return False, f"Excluded due to {category}: {pattern}"

        return True, "No exclusion patterns matched"

    def _calculate_emotional_intensity(self, post_data: Dict[str, Any]) -> float:
        """计算情绪强度"""
        title = (post_data.get("title", "")).lower()
        body = (post_data.get("body", "")).lower()
        full_text = f"{title} {body}"

        # 高强度情绪词汇
        high_intensity_words = [
            "frustrated", "frustrating", "annoying", "annoyed", "hate", "terrible",
            "awful", "horrible", "disaster", "catastrophe", "nightmare", "hell",
            "impossible", "useless", "worthless", "broken", "crashed", "failed"
        ]

        # 中强度情绪词汇
        medium_intensity_words = [
            "difficult", "hard", "struggling", "trouble", "problem", "issue",
            "challenge", "confusing", "complicated", "complex", "slow", "tedious"
        ]

        # 低强度情绪词汇
        low_intensity_words = [
            "annoyance", "minor", "slight", "inconvenient", "suboptimal", "could be better"
        ]

        high_count = sum(1 for word in high_intensity_words if word in full_text)
        medium_count = sum(1 for word in medium_intensity_words if word in full_text)
        low_count = sum(1 for word in low_intensity_words if word in full_text)

        # 计算加权情绪强度
        intensity = (high_count * 1.0 + medium_count * 0.6 + low_count * 0.3) / max(len(full_text.split()) / 100, 1)
        return min(intensity, 1.0)

    def _check_post_type_specific(self, post_data: Dict[str, Any]) -> Tuple[bool, str]:
        """检查特定类型帖子的阈值"""
        subreddit = post_data.get("subreddit", "").lower()
        score = post_data.get("score", 0)
        comments = post_data.get("num_comments", 0)

        quality_config = self.thresholds.get("reddit_quality", {})
        type_specific = quality_config.get("type_specific", {})

        # 根据子版块类别判断类型
        post_type = "general"  # 默认类型
        if any(keyword in subreddit for keyword in ["programming", "sysadmin", "webdev", "technical"]):
            post_type = "technical"
        elif any(keyword in subreddit for keyword in ["entrepreneur", "startups", "business"]):
            post_type = "business"
        elif "discussion" in subreddit or comments > score * 2:
            post_type = "discussion"

        if post_type in type_specific:
            type_config = type_specific[post_type]
            if score < type_config.get("min_upvotes", 0):
                return False, f"Type {post_type}: too few upvotes: {score} < {type_config.get('min_upvotes')}"
            if comments < type_config.get("min_comments", 0):
                return False, f"Type {post_type}: too few comments: {comments} < {type_config.get('min_comments')}"

        return True, f"Type {post_type} check passed"

    def filter_post(self, post_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """过滤单个帖子"""
        self.stats["total_processed"] += 1

        filter_result = {
            "post_id": post_data.get("id"),
            "passed": False,
            "pain_score": 0.0,
            "reasons": [],
            "matched_keywords": [],
            "matched_patterns": [],
            "emotional_intensity": 0.0,
            "filter_summary": {}
        }

        # 1. 质量阈值检查
        quality_passed, quality_reason = self._check_quality_thresholds(post_data)
        if not quality_passed:
            self.stats["filtered_out"] += 1
            self.stats["filter_reasons"][quality_reason] = self.stats["filter_reasons"].get(quality_reason, 0) + 1
            filter_result["reasons"].append(quality_reason)
            filter_result["filter_summary"] = {"reason": "quality_threshold", "details": quality_reason}
            return False, filter_result

        # 2. 排除模式检查
        exclusion_passed, exclusion_reason = self._check_exclusion_patterns(post_data)
        if not exclusion_passed:
            self.stats["filtered_out"] += 1
            self.stats["filter_reasons"][exclusion_reason] = self.stats["filter_reasons"].get(exclusion_reason, 0) + 1
            filter_result["reasons"].append(exclusion_reason)
            filter_result["filter_summary"] = {"reason": "exclusion_pattern", "details": exclusion_reason}
            return False, filter_result

        # 3. 痛点关键词检查
        has_keywords, matched_keywords, keyword_score = self._check_pain_keywords(post_data)
        filter_result["matched_keywords"] = matched_keywords

        # 4. 痛点句式检查
        has_patterns, matched_patterns = self._check_pain_patterns(post_data)
        filter_result["matched_patterns"] = matched_patterns

        # 5. 情绪强度计算
        emotional_intensity = self._calculate_emotional_intensity(post_data)
        filter_result["emotional_intensity"] = emotional_intensity

        # 6. 类型特定检查
        type_passed, type_reason = self._check_post_type_specific(post_data)
        if not type_passed:
            self.stats["filtered_out"] += 1
            self.stats["filter_reasons"][type_reason] = self.stats["filter_reasons"].get(type_reason, 0) + 1
            filter_result["reasons"].append(type_reason)
            filter_result["filter_summary"] = {"reason": "type_specific", "details": type_reason}
            return False, filter_result

        # 计算综合痛点分数
        pain_score = 0.0

        # 关键词分数 (40%)
        pain_score += keyword_score * 0.4

        # 句式分数 (30%)
        pattern_score = min(len(matched_patterns) / 3.0, 1.0) * 0.3
        pain_score += pattern_score

        # 情绪强度分数 (20%)
        pain_score += emotional_intensity * 0.2

        # 基础质量分数 (10%)
        score_normalized = min(post_data.get("score", 0) / 100.0, 1.0)
        comments_normalized = min(post_data.get("num_comments", 0) / 50.0, 1.0)
        quality_score = (score_normalized + comments_normalized) / 2.0 * 0.1
        pain_score += quality_score

        # 确保分数在0-1范围内
        pain_score = min(max(pain_score, 0.0), 1.0)

        filter_result["pain_score"] = pain_score

        # 判断是否通过痛点信号检查
        pain_config = self.thresholds.get("pain_signal", {})
        min_keyword_matches = pain_config.get("keyword_match", {}).get("min_matches", 1)
        min_emotional_intensity = pain_config.get("emotional_intensity", {}).get("min_score", 0.3)

        # 最终判断
        passed = (
            has_keywords and
            len(matched_keywords) >= min_keyword_matches and
            emotional_intensity >= min_emotional_intensity and
            pain_score >= 0.3  # 综合分数阈值
        )

        if passed:
            self.stats["passed_filter"] += 1
            filter_result["passed"] = True
            filter_result["filter_summary"] = {
                "reason": "passed",
                "pain_score": pain_score,
                "components": {
                    "keywords": keyword_score,
                    "patterns": pattern_score,
                    "emotion": emotional_intensity,
                    "quality": quality_score
                }
            }
        else:
            self.stats["filtered_out"] += 1
            failure_reasons = []
            if not has_keywords or len(matched_keywords) < min_keyword_matches:
                failure_reasons.append("insufficient_keywords")
            if emotional_intensity < min_emotional_intensity:
                failure_reasons.append("low_emotional_intensity")
            if pain_score < 0.3:
                failure_reasons.append("low_overall_score")

            reason_str = "; ".join(failure_reasons)
            self.stats["filter_reasons"][reason_str] = self.stats["filter_reasons"].get(reason_str, 0) + 1
            filter_result["reasons"].append(f"Failed: {reason_str}")
            filter_result["filter_summary"] = {"reason": "failed", "details": failure_reasons}

        return passed, filter_result

    def filter_posts_batch(self, posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量过滤帖子"""
        logger.info(f"Filtering {len(posts)} posts through pain signal detector")

        filtered_posts = []
        for i, post in enumerate(posts):
            if i % 100 == 0:
                logger.info(f"Processed {i}/{len(posts)} posts")

            passed, result = self.filter_post(post)

            if passed:
                # 为帖子添加过滤结果
                filtered_post = post.copy()
                filtered_post.update({
                    "pain_score": result["pain_score"],
                    "pain_keywords": result["matched_keywords"],
                    "pain_patterns": result["matched_patterns"],
                    "emotional_intensity": result["emotional_intensity"],
                    "filter_reason": "pain_signal_passed"
                })
                filtered_posts.append(filtered_post)

        logger.info(f"Filter complete: {len(filtered_posts)}/{len(posts)} posts passed")
        return filtered_posts

    def get_statistics(self) -> Dict[str, Any]:
        """获取过滤统计信息"""
        stats = self.stats.copy()
        if stats["total_processed"] > 0:
            stats["pass_rate"] = stats["passed_filter"] / stats["total_processed"]
        else:
            stats["pass_rate"] = 0.0
        return stats

    def reset_statistics(self):
        """重置统计信息"""
        self.stats = {
            "total_processed": 0,
            "passed_filter": 0,
            "filtered_out": 0,
            "filter_reasons": {}
        }

def main():
    """主函数 - 过滤原始帖子"""
    import argparse
    from utils.db import db

    parser = argparse.ArgumentParser(description="Filter Reddit posts for pain signals")
    parser.add_argument("--limit", type=int, default=1000, help="Limit number of posts to process")
    parser.add_argument("--min-score", type=float, default=0.0, help="Minimum pain score threshold")
    args = parser.parse_args()

    try:
        logger.info("Starting pain signal filtering...")

        # 初始化过滤器
        filter = PainSignalFilter()

        # 获取未过滤的帖子
        logger.info(f"Fetching up to {args.limit} unprocessed posts...")
        unfiltered_posts = db.get_unprocessed_posts(limit=args.limit)

        if not unfiltered_posts:
            logger.info("No unprocessed posts found")
            return

        logger.info(f"Found {len(unfiltered_posts)} posts to filter")

        # 批量过滤
        filtered_posts = filter.filter_posts_batch(unfiltered_posts)

        # 应用最小分数阈值
        if args.min_score > 0:
            filtered_posts = [p for p in filtered_posts if p.get("pain_score", 0) >= args.min_score]
            logger.info(f"After applying min_score threshold: {len(filtered_posts)} posts")

        # 保存过滤结果
        saved_count = 0
        for post in filtered_posts:
            if db.insert_filtered_post(post):
                saved_count += 1

        logger.info(f"Saved {saved_count}/{len(filtered_posts)} filtered posts to database")

        # 输出统计信息
        stats = filter.get_statistics()
        logger.info(f"""
=== Filter Summary ===
Total processed: {stats['total_processed']}
Passed filter: {stats['passed_filter']}
Filtered out: {stats['filtered_out']}
Pass rate: {stats['pass_rate']:.2%}
Filter reasons: {stats['filter_reasons']}
""")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()
```


================================================================================
文件: pipeline/map_opportunity.py
================================================================================

```python
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
                return opportunity_data
            else:
                logger.info(f"No viable opportunity found for cluster {cluster_data['cluster_name']}")
                return None

        except Exception as e:
            logger.error(f"Failed to map opportunity with LLM: {e}")
            return None

    def _evaluate_opportunity_quality(self, opportunity_data: Dict[str, Any], cluster_data: Dict[str, Any]) -> Dict[str, Any]:
        """评估机会质量"""
        try:
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

    def _save_opportunity_to_database(self, cluster_id: int, opportunity_data: Dict[str, Any], quality_result: Dict[str, Any]) -> Optional[int]:
        """保存机会到数据库"""
        try:
            opportunity = opportunity_data.get("opportunity", {})

            # 准备机会数据
            opportunity_record = {
                "cluster_id": cluster_id,
                "opportunity_name": opportunity.get("name", ""),
                "description": opportunity.get("description", ""),
                "current_tools": json.dumps(opportunity_data.get("current_tools", [])),
                "missing_capability": opportunity_data.get("missing_capability", ""),
                "why_existing_fail": opportunity_data.get("why_existing_fail", ""),
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
            # 获取聚类
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT * FROM clusters
                    ORDER BY cluster_size DESC, workflow_confidence DESC
                    LIMIT ?
                """, (limit,))
                clusters = [dict(row) for row in cursor.fetchall()]

            if not clusters:
                logger.info("No clusters found for opportunity mapping")
                return {"opportunities_identified": 0, "clusters_processed": 0}

            logger.info(f"Processing {len(clusters)} clusters for opportunity mapping")

            opportunities_created = []
            viable_opportunities = 0

            for i, cluster in enumerate(clusters):
                logger.info(f"Processing cluster {i+1}/{len(clusters)}: {cluster['cluster_name']}")

                try:
                    # 丰富聚类数据
                    enriched_cluster = self._enrich_cluster_data(cluster)

                    # 使用LLM映射机会
                    opportunity_data = self._map_opportunity_with_llm(enriched_cluster)

                    if opportunity_data:
                        # 评估机会质量
                        quality_result = self._evaluate_opportunity_quality(opportunity_data, enriched_cluster)

                        if quality_result["is_viable"]:
                            # 保存到数据库
                            opportunity_id = self._save_opportunity_to_database(
                                cluster["id"], opportunity_data, quality_result
                            )

                            if opportunity_id:
                                opportunity_summary = {
                                    "opportunity_id": opportunity_id,
                                    "cluster_id": cluster["id"],
                                    "cluster_name": cluster["cluster_name"],
                                    "opportunity_name": opportunity_data["opportunity"]["name"],
                                    "opportunity_description": opportunity_data["opportunity"]["description"],
                                    "quality_score": quality_result["quality_score"],
                                    "quality_reasons": quality_result["quality_reasons"]
                                }

                                opportunities_created.append(opportunity_summary)
                                viable_opportunities += 1

                                logger.info(f"Created opportunity: {opportunity_data['opportunity']['name']} (Score: {quality_result['quality_score']:.2f})")
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
```


================================================================================
文件: pipeline/score_viability.py
================================================================================

```python
"""
Score Viability module for Reddit Pain Point Finder
可行性评分模块 - 针对一人公司的可行性评估
"""
import json
import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

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
            "avg_total_score": 0.0
        }

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
        """结合LLM评分和规则评分"""
        try:
            # LLM评分
            llm_component_scores = llm_scores.get("scores", {})
            llm_total_score = llm_scores.get("total_score", 0.0)

            # 规则评分
            market_analysis = opportunity_data.get("market_analysis", {})
            competition_analysis = opportunity_data.get("competition_analysis", {})

            # 市场规模评分 (0-10)
            market_tier = market_analysis.get("market_tier", "niche")
            market_score_by_tier = {
                "large": 9,
                "medium": 7,
                "small": 5,
                "niche": 3
            }
            market_score = market_score_by_tier.get(market_tier, 3)

            # 竞争评分 (0-10, 越低越好)
            competition_score = competition_analysis.get("competition_score", 8)
            competition_normalized = max(10 - competition_score, 1)  # 转换为越高越好

            # 聚类大小评分 (0-10)
            cluster_info = opportunity_data.get("cluster_info", {})
            cluster_size = cluster_info.get("cluster_size", 0)
            cluster_score = min(cluster_size, 10)  # 每个事件1分，最多10分

            # 工作流置信度评分 (0-10)
            workflow_confidence = cluster_info.get("workflow_confidence", 0.0)
            workflow_score = workflow_confidence * 10

            # 综合评分计算
            final_component_scores = {
                "pain_frequency": llm_component_scores.get("pain_frequency", 5),
                "clear_buyer": llm_component_scores.get("clear_buyer", 5),
                "mvp_buildable": llm_component_scores.get("mvp_buildable", 5),
                "crowded_market": competition_normalized,
                "integration": llm_component_scores.get("integration", 5),
                "market_size": market_score,
                "cluster_strength": cluster_score,
                "workflow_confidence": workflow_score
            }

            # 计算加权总分
            weights = {
                "pain_frequency": 0.15,
                "clear_buyer": 0.15,
                "mvp_buildable": 0.20,
                "crowded_market": 0.15,
                "integration": 0.10,
                "market_size": 0.10,
                "cluster_strength": 0.10,
                "workflow_confidence": 0.05
            }

            weighted_total = sum(
                final_component_scores[component] * weight
                for component, weight in weights.items()
            )

            # 确保分数在0-10范围内
            final_total_score = min(max(weighted_total, 0), 10)

            # 生成杀手风险
            killer_risks = self._generate_killer_risks(final_component_scores, opportunity_data)

            return {
                "component_scores": final_component_scores,
                "total_score": final_total_score,
                "llm_total_score": llm_total_score,
                "killer_risks": killer_risks,
                "recommendation": self._generate_recommendation(final_total_score, killer_risks)
            }

        except Exception as e:
            logger.error(f"Failed to combine scores: {e}")
            return {"total_score": 0.0, "component_scores": {}, "killer_risks": [], "recommendation": "Error in scoring"}

    def _generate_killer_risks(self, component_scores: Dict[str, Any], opportunity_data: Dict[str, Any]) -> List[str]:
        """生成杀手风险"""
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
        """更新数据库中的机会评分"""
        try:
            with db.get_connection("clusters") as conn:
                conn.execute("""
                    UPDATE opportunities
                    SET pain_frequency_score = ?,
                        market_size_score = ?,
                        mvp_complexity_score = ?,
                        competition_risk_score = ?,
                        integration_complexity_score = ?,
                        total_score = ?,
                        killer_risks = ?,
                        recommendation = ?
                    WHERE id = ?
                """, (
                    scoring_result["component_scores"].get("pain_frequency", 0),
                    scoring_result["component_scores"].get("market_size", 0),
                    scoring_result["component_scores"].get("mvp_buildable", 0),
                    scoring_result["component_scores"].get("crowded_market", 0),
                    scoring_result["component_scores"].get("integration", 0),
                    scoring_result["total_score"],
                    json.dumps(scoring_result["killer_risks"]),
                    scoring_result.get("recommendation", ""),
                    opportunity_id
                ))
                conn.commit()
                return True

        except Exception as e:
            logger.error(f"Failed to update opportunity in database: {e}")
            return False

    def score_opportunities(self, limit: int = 100) -> Dict[str, Any]:
        """为机会评分"""
        logger.info(f"Scoring up to {limit} opportunities")

        start_time = time.time()

        try:
            # 获取未评分的机会
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT * FROM opportunities
                    WHERE total_score = 0 OR total_score IS NULL
                    ORDER BY cluster_id DESC
                    LIMIT ?
                """, (limit,))
                opportunities = [dict(row) for row in cursor.fetchall()]

            if not opportunities:
                logger.info("No unscored opportunities found")
                return {"opportunities_scored": 0, "viable_opportunities": 0}

            logger.info(f"Found {len(opportunities)} opportunities to score")

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
```


================================================================================
文件: utils/db.py
================================================================================

```python
"""
Database utilities for Reddit Pain Point Finder
SQLite数据库操作工具
"""
import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
import os

logger = logging.getLogger(__name__)

class PainPointDB:
    """Reddit痛点发现系统数据库管理器"""

    def __init__(self, db_dir: str = "data"):
        """初始化数据库连接"""
        self.db_dir = db_dir
        os.makedirs(db_dir, exist_ok=True)

        # 数据库文件路径
        self.raw_db_path = os.path.join(db_dir, "raw_posts.db")
        self.filtered_db_path = os.path.join(db_dir, "filtered_posts.db")
        self.pain_db_path = os.path.join(db_dir, "pain_events.db")
        self.clusters_db_path = os.path.join(db_dir, "clusters.db")

        # 初始化所有数据库
        self._init_databases()

    @contextmanager
    def get_connection(self, db_type: str = "raw"):
        """获取数据库连接的上下文管理器"""
        db_paths = {
            "raw": self.raw_db_path,
            "filtered": self.filtered_db_path,
            "pain": self.pain_db_path,
            "clusters": self.clusters_db_path
        }

        if db_type not in db_paths:
            raise ValueError(f"Invalid db_type: {db_type}")

        conn = None
        try:
            conn = sqlite3.connect(db_paths[db_type])
            conn.row_factory = sqlite3.Row
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def _init_databases(self):
        """初始化所有数据库表结构"""
        self._init_raw_posts_db()
        self._init_filtered_posts_db()
        self._init_pain_events_db()
        self._init_clusters_db()

    def _init_raw_posts_db(self):
        """初始化原始帖子数据库"""
        with self.get_connection("raw") as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT,
                    subreddit TEXT NOT NULL,
                    url TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    num_comments INTEGER NOT NULL,
                    upvote_ratio REAL NOT NULL,
                    is_self INTEGER NOT NULL,
                    created_utc REAL NOT NULL,
                    author TEXT,
                    category TEXT,
                    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    raw_data TEXT  -- 原始JSON数据
                )
            """)

            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_score ON posts(score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_collected_at ON posts(collected_at)")
            conn.commit()

    def _init_filtered_posts_db(self):
        """初始化过滤后的帖子数据库"""
        with self.get_connection("filtered") as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS filtered_posts (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT,
                    subreddit TEXT NOT NULL,
                    url TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    num_comments INTEGER NOT NULL,
                    upvote_ratio REAL NOT NULL,
                    pain_score REAL NOT NULL,
                    pain_keywords TEXT,
                    filtered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    filter_reason TEXT
                )
            """)

            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filtered_pain_score ON filtered_posts(pain_score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filtered_subreddit ON filtered_posts(subreddit)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filtered_at ON filtered_posts(filtered_at)")
            conn.commit()

    def _init_pain_events_db(self):
        """初始化痛点事件数据库"""
        with self.get_connection("pain") as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pain_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT NOT NULL,
                    actor TEXT,
                    context TEXT,
                    problem TEXT NOT NULL,
                    current_workaround TEXT,
                    frequency TEXT,
                    emotional_signal TEXT,
                    mentioned_tools TEXT,
                    extraction_confidence REAL,
                    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES filtered_posts(id)
                )
            """)

            # 创建嵌入向量表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pain_embeddings (
                    pain_event_id INTEGER PRIMARY KEY,
                    embedding_vector BLOB NOT NULL,
                    embedding_model TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (pain_event_id) REFERENCES pain_events(id)
                )
            """)

            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pain_post_id ON pain_events(post_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pain_problem ON pain_events(problem)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pain_extracted_at ON pain_events(extracted_at)")
            conn.commit()

    def _init_clusters_db(self):
        """初始化聚类数据库"""
        with self.get_connection("clusters") as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_name TEXT NOT NULL,
                    cluster_description TEXT,
                    pain_event_ids TEXT NOT NULL,  -- JSON数组
                    cluster_size INTEGER NOT NULL,
                    avg_pain_score REAL,
                    workflow_confidence REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建机会表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_id INTEGER NOT NULL,
                    opportunity_name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    current_tools TEXT,
                    missing_capability TEXT,
                    why_existing_fail TEXT,
                    target_users TEXT,
                    pain_frequency_score REAL,
                    market_size_score REAL,
                    mvp_complexity_score REAL,
                    competition_risk_score REAL,
                    integration_complexity_score REAL,
                    total_score REAL,
                    killer_risks TEXT,  -- JSON数组
                    recommendation TEXT,  -- AI建议：pursue/modify/abandon with reason
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (cluster_id) REFERENCES clusters(id)
                )
            """)

            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_size ON clusters(cluster_size)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities(total_score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_cluster_id ON opportunities(cluster_id)")
            conn.commit()

    # Raw posts operations
    def insert_raw_post(self, post_data: Dict[str, Any]) -> bool:
        """插入原始帖子数据"""
        try:
            with self.get_connection("raw") as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO posts
                    (id, title, body, subreddit, url, score, num_comments,
                     upvote_ratio, is_self, created_utc, author, category, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    post_data["id"],
                    post_data["title"],
                    post_data.get("body", ""),
                    post_data["subreddit"],
                    post_data["url"],
                    post_data["score"],
                    post_data["num_comments"],
                    post_data.get("upvote_ratio", 0.0),
                    int(post_data.get("is_self", False)),
                    post_data.get("created_utc", 0),
                    post_data.get("author", ""),
                    post_data.get("category", ""),
                    json.dumps(post_data)
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to insert raw post {post_data.get('id')}: {e}")
            return False

    def get_unprocessed_posts(self, limit: int = 100) -> List[Dict]:
        """获取未处理的帖子"""
        try:
            # 首先获取所有已处理的帖子ID
            with self.get_connection("filtered") as conn:
                cursor = conn.execute("SELECT id FROM filtered_posts")
                processed_ids = {row['id'] for row in cursor.fetchall()}

            # 然后获取未处理的帖子
            with self.get_connection("raw") as conn:
                if processed_ids:
                    # 如果有已处理的帖子，排除它们
                    placeholders = ','.join('?' * len(processed_ids))
                    cursor = conn.execute(f"""
                        SELECT * FROM posts
                        WHERE id NOT IN ({placeholders})
                        ORDER BY collected_at DESC
                        LIMIT ?
                    """, list(processed_ids) + [limit])
                else:
                    # 如果没有已处理的帖子，直接获取
                    cursor = conn.execute("""
                        SELECT * FROM posts
                        ORDER BY collected_at DESC
                        LIMIT ?
                    """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get unprocessed posts: {e}")
            return []

    # Filtered posts operations
    def insert_filtered_post(self, post_data: Dict[str, Any]) -> bool:
        """插入过滤后的帖子"""
        try:
            with self.get_connection("filtered") as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO filtered_posts
                    (id, title, body, subreddit, url, score, num_comments,
                     upvote_ratio, pain_score, pain_keywords, filter_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    post_data["id"],
                    post_data["title"],
                    post_data.get("body", ""),
                    post_data["subreddit"],
                    post_data["url"],
                    post_data["score"],
                    post_data["num_comments"],
                    post_data.get("upvote_ratio", 0.0),
                    post_data.get("pain_score", 0.0),
                    json.dumps(post_data.get("pain_keywords", [])),
                    post_data.get("filter_reason", "")
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to insert filtered post {post_data.get('id')}: {e}")
            return False

    def get_filtered_posts(self, limit: int = 100, min_pain_score: float = 0.0) -> List[Dict]:
        """获取过滤后的帖子"""
        try:
            # 首先获取所有已提取的帖子ID
            with self.get_connection("pain") as conn:
                cursor = conn.execute("SELECT DISTINCT post_id FROM pain_events")
                extracted_ids = {row['post_id'] for row in cursor.fetchall()}

            # 然后获取过滤后的帖子
            with self.get_connection("filtered") as conn:
                if extracted_ids:
                    # 如果有已提取的帖子，排除它们
                    placeholders = ','.join('?' * len(extracted_ids))
                    cursor = conn.execute(f"""
                        SELECT * FROM filtered_posts
                        WHERE pain_score >= ?
                        AND id NOT IN ({placeholders})
                        ORDER BY pain_score DESC
                        LIMIT ?
                    """, [min_pain_score] + list(extracted_ids) + [limit])
                else:
                    # 如果没有已提取的帖子，直接获取
                    cursor = conn.execute("""
                        SELECT * FROM filtered_posts
                        WHERE pain_score >= ?
                        ORDER BY pain_score DESC
                        LIMIT ?
                    """, (min_pain_score, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get filtered posts: {e}")
            return []

    # Pain events operations
    def insert_pain_event(self, pain_data: Dict[str, Any]) -> Optional[int]:
        """插入痛点事件"""
        try:
            with self.get_connection("pain") as conn:
                cursor = conn.execute("""
                    INSERT INTO pain_events
                    (post_id, actor, context, problem, current_workaround,
                     frequency, emotional_signal, mentioned_tools, extraction_confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pain_data["post_id"],
                    pain_data.get("actor", ""),
                    pain_data.get("context", ""),
                    pain_data["problem"],
                    pain_data.get("current_workaround", ""),
                    pain_data.get("frequency", ""),
                    pain_data.get("emotional_signal", ""),
                    json.dumps(pain_data.get("mentioned_tools", [])),
                    pain_data.get("extraction_confidence", 0.0)
                ))
                pain_event_id = cursor.lastrowid
                conn.commit()
                return pain_event_id
        except Exception as e:
            logger.error(f"Failed to insert pain event: {e}")
            return None

    def insert_pain_embedding(self, pain_event_id: int, embedding_vector: List[float], model_name: str) -> bool:
        """插入痛点嵌入向量"""
        try:
            import pickle
            embedding_blob = pickle.dumps(embedding_vector)

            with self.get_connection("pain") as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO pain_embeddings
                    (pain_event_id, embedding_vector, embedding_model)
                    VALUES (?, ?, ?)
                """, (pain_event_id, embedding_blob, model_name))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to insert pain embedding for event {pain_event_id}: {e}")
            return False

    def get_pain_events_without_embeddings(self, limit: int = 100) -> List[Dict]:
        """获取没有嵌入向量的痛点事件"""
        try:
            with self.get_connection("pain") as conn:
                cursor = conn.execute("""
                    SELECT p.* FROM pain_events p
                    LEFT JOIN pain_embeddings e ON p.id = e.pain_event_id
                    WHERE e.pain_event_id IS NULL
                    ORDER BY p.extracted_at DESC
                    LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get pain events without embeddings: {e}")
            return []

    def get_all_pain_events_with_embeddings(self) -> List[Dict]:
        """获取所有有嵌入向量的痛点事件"""
        try:
            import pickle
            with self.get_connection("pain") as conn:
                cursor = conn.execute("""
                    SELECT p.*, e.embedding_vector, e.embedding_model
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
            logger.error(f"Failed to get pain events with embeddings: {e}")
            return []

    # Clusters operations
    def insert_cluster(self, cluster_data: Dict[str, Any]) -> Optional[int]:
        """插入聚类"""
        try:
            with self.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    INSERT INTO clusters
                    (cluster_name, cluster_description, pain_event_ids, cluster_size,
                     avg_pain_score, workflow_confidence)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    cluster_data["cluster_name"],
                    cluster_data.get("cluster_description", ""),
                    json.dumps(cluster_data["pain_event_ids"]),
                    cluster_data["cluster_size"],
                    cluster_data.get("avg_pain_score", 0.0),
                    cluster_data.get("workflow_confidence", 0.0)
                ))
                cluster_id = cursor.lastrowid
                conn.commit()
                return cluster_id
        except Exception as e:
            logger.error(f"Failed to insert cluster: {e}")
            return None

    def insert_opportunity(self, opportunity_data: Dict[str, Any]) -> Optional[int]:
        """插入机会"""
        try:
            with self.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    INSERT INTO opportunities
                    (cluster_id, opportunity_name, description, current_tools,
                     missing_capability, why_existing_fail, target_users,
                     pain_frequency_score, market_size_score, mvp_complexity_score,
                     competition_risk_score, integration_complexity_score, total_score, killer_risks, recommendation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    opportunity_data["cluster_id"],
                    opportunity_data["opportunity_name"],
                    opportunity_data["description"],
                    opportunity_data.get("current_tools", ""),
                    opportunity_data.get("missing_capability", ""),
                    opportunity_data.get("why_existing_fail", ""),
                    opportunity_data.get("target_users", ""),
                    opportunity_data.get("pain_frequency_score", 0.0),
                    opportunity_data.get("market_size_score", 0.0),
                    opportunity_data.get("mvp_complexity_score", 0.0),
                    opportunity_data.get("competition_risk_score", 0.0),
                    opportunity_data.get("integration_complexity_score", 0.0),
                    opportunity_data.get("total_score", 0.0),
                    json.dumps(opportunity_data.get("killer_risks", [])),
                    opportunity_data.get("recommendation", "")
                ))
                opportunity_id = cursor.lastrowid
                conn.commit()
                return opportunity_id
        except Exception as e:
            logger.error(f"Failed to insert opportunity: {e}")
            return None

    def get_top_opportunities(self, limit: int = 20) -> List[Dict]:
        """获取最高分的机会"""
        try:
            with self.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT o.*, c.cluster_name, c.cluster_description
                    FROM opportunities o
                    JOIN clusters c ON o.cluster_id = c.id
                    ORDER BY o.total_score DESC
                    LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get top opportunities: {e}")
            return []

    # Statistics operations
    def get_statistics(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        stats = {}

        try:
            # Raw posts count
            with self.get_connection("raw") as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM posts")
                stats["raw_posts_count"] = cursor.fetchone()["count"]

            # Filtered posts count
            with self.get_connection("filtered") as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM filtered_posts")
                stats["filtered_posts_count"] = cursor.fetchone()["count"]

                cursor = conn.execute("SELECT AVG(pain_score) as avg_score FROM filtered_posts")
                stats["avg_pain_score"] = cursor.fetchone()["avg_score"] or 0

            # Pain events count
            with self.get_connection("pain") as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM pain_events")
                stats["pain_events_count"] = cursor.fetchone()["count"]

            # Clusters count
            with self.get_connection("clusters") as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM clusters")
                stats["clusters_count"] = cursor.fetchone()["count"]

                cursor = conn.execute("SELECT COUNT(*) as count FROM opportunities")
                stats["opportunities_count"] = cursor.fetchone()["count"]

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")

        return stats

# 全局数据库实例
db = PainPointDB()
```


================================================================================
文件: utils/embedding.py
================================================================================

```python
"""
Embedding utilities for Reddit Pain Point Finder
向量化工具，用于痛点事件聚类
"""
import os
import logging
import pickle
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import DBSCAN
import yaml
from openai import OpenAI
import backoff

logger = logging.getLogger(__name__)

class EmbeddingClient:
    """嵌入向量客户端"""

    def __init__(self, config_path: str = "config/llm.yaml"):
        """初始化嵌入客户端"""
        self.config = self._load_config(config_path)
        self.client = self._init_client()
        self.model_name = self._get_model_name()
        self.embedding_cache = {}
        self.stats = {
            "embeddings_created": 0,
            "cache_hits": 0,
            "total_tokens": 0
        }

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise

    def _init_client(self) -> OpenAI:
        """初始化OpenAI客户端"""
        api_key = os.getenv(self.config['api']['api_key_env'])
        if not api_key:
            raise ValueError(f"API key not found: {self.config['api']['api_key_env']}")

        return OpenAI(
            api_key=api_key,
            base_url=self.config['api']['base_url']
        )

    def _get_model_name(self) -> str:
        """获取嵌入模型名称"""
        embedding_config = self.config.get("embedding", {})
        env_name = embedding_config.get("env_name")
        if env_name and os.getenv(env_name):
            return os.getenv(env_name)
        return embedding_config.get("model", "text-embedding-ada-002")

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        base=1,
        max_value=60
    )
    def create_embedding(self, text: str) -> List[float]:
        """创建文本嵌入向量"""
        try:
            # 检查缓存
            if text in self.embedding_cache:
                self.stats["cache_hits"] += 1
                return self.embedding_cache[text]

            # 调用API
            response = self.client.embeddings.create(
                model=self.model_name,
                input=text
            )

            embedding = response.data[0].embedding

            # 更新统计
            self.stats["embeddings_created"] += 1
            self.stats["total_tokens"] += response.usage.total_tokens

            # 缓存结果
            self.embedding_cache[text] = embedding

            logger.info(f"Created embedding for text length {len(text)}: {len(embedding)} dimensions")
            return embedding

        except Exception as e:
            logger.error(f"Failed to create embedding: {e}")
            raise

    def create_batch_embeddings(self, texts: List[str], batch_size: int = None) -> List[List[float]]:
        """批量创建嵌入向量"""
        if batch_size is None:
            batch_size = self.config.get("embedding", {}).get("batch_size", 32)

        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(texts) + batch_size - 1)//batch_size}")

            for text in batch:
                embedding = self.create_embedding(text)
                embeddings.append(embedding)

        return embeddings

    def create_pain_event_embedding(self, pain_event: Dict[str, Any]) -> List[float]:
        """为痛点事件创建嵌入向量"""
        # 构建嵌入文本，重点关注问题的本质
        text_parts = []

        if pain_event.get("actor"):
            text_parts.append(pain_event["actor"])

        if pain_event.get("context"):
            text_parts.append(pain_event["context"])

        if pain_event.get("problem"):
            text_parts.append(pain_event["problem"])

        if pain_event.get("current_workaround"):
            text_parts.append(pain_event["current_workaround"])

        # 用 " | " 连接各个部分，保持语义结构
        embedding_text = " | ".join(text_parts)

        return self.create_embedding(embedding_text)

    def calculate_similarity_matrix(self, embeddings: List[List[float]]) -> np.ndarray:
        """计算相似度矩阵"""
        return cosine_similarity(embeddings)

    def find_similar_events(
        self,
        target_embedding: List[float],
        candidate_embeddings: List[List[float]],
        threshold: float = 0.7,
        top_k: int = 10
    ) -> List[Tuple[int, float]]:
        """找到相似的痛点事件"""
        similarities = cosine_similarity([target_embedding], candidate_embeddings)[0]

        # 筛选超过阈值的结果
        results = []
        for idx, similarity in enumerate(similarities):
            if similarity >= threshold:
                results.append((idx, similarity))

        # 按相似度排序，返回top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def cluster_embeddings(
        self,
        embeddings: List[List[float]],
        eps: float = 0.5,
        min_samples: int = 3
    ) -> Dict[int, List[int]]:
        """使用DBSCAN聚类嵌入向量"""
        if len(embeddings) < min_samples:
            return {0: list(range(len(embeddings)))}  # 如果样本太少，归为一类

        dbscan = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
        cluster_labels = dbscan.fit_predict(embeddings)

        # 构建聚类字典
        clusters = {}
        for idx, label in enumerate(cluster_labels):
            if label == -1:  # 噪声点
                continue
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(idx)

        return clusters

    def analyze_cluster(
        self,
        cluster_indices: List[int],
        embeddings: List[List[float]],
        pain_events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """分析一个聚类"""
        if not cluster_indices:
            return {}

        # 计算聚类中心
        cluster_embeddings = [embeddings[i] for i in cluster_indices]
        centroid = np.mean(cluster_embeddings, axis=0)

        # 计算每个点到中心的距离
        distances_to_center = [
            1 - cosine_similarity([embeddings[i]], [centroid])[0][0]
            for i in cluster_indices
        ]

        # 计算聚类的内聚性（平均距离）
        cohesion = 1 - np.mean(distances_to_center)

        # 获取该聚类的痛点事件
        cluster_events = [pain_events[i] for i in cluster_indices]

        return {
            "size": len(cluster_indices),
            "centroid": centroid.tolist(),
            "cohesion": cohesion,
            "events": cluster_events,
            "avg_distance_to_center": np.mean(distances_to_center),
            "max_distance_to_center": np.max(distances_to_center)
        }

    def get_embedding_statistics(self) -> Dict[str, Any]:
        """获取嵌入统计信息"""
        return self.stats.copy()

    def save_embedding_cache(self, cache_path: str):
        """保存嵌入缓存"""
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(self.embedding_cache, f)
            logger.info(f"Saved embedding cache to {cache_path}")
        except Exception as e:
            logger.error(f"Failed to save embedding cache: {e}")

    def load_embedding_cache(self, cache_path: str):
        """加载嵌入缓存"""
        try:
            if os.path.exists(cache_path):
                with open(cache_path, 'rb') as f:
                    self.embedding_cache = pickle.load(f)
                logger.info(f"Loaded embedding cache from {cache_path}: {len(self.embedding_cache)} entries")
        except Exception as e:
            logger.error(f"Failed to load embedding cache: {e}")

class PainEventClustering:
    """痛点事件聚类工具"""

    def __init__(self, embedding_client: EmbeddingClient):
        """初始化聚类工具"""
        self.embedding_client = embedding_client
        self.clustering_config = self._load_clustering_config()

    def _load_clustering_config(self) -> Dict[str, Any]:
        """加载聚类配置"""
        try:
            config_path = "config/clustering.yaml"
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            logger.error(f"Failed to load clustering config: {e}")
            # 返回默认配置
            return {
                "vector_similarity": {"similarity_threshold": 0.8, "top_k": 10},
                "dbscan": {"eps": 0.3, "min_samples": 2},
                "llm_validation": {"max_events_per_validation": 10, "confidence_threshold": 0.7},
                "post_processing": {"min_cluster_size": 2, "max_cluster_size": 15}
            }

    def cluster_pain_events(self, pain_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """聚类痛点事件"""
        if len(pain_events) < 2:
            return []

        logger.info(f"Clustering {len(pain_events)} pain events")

        # 1. 创建嵌入向量
        logger.info("Creating embeddings for pain events...")
        embeddings = []
        for event in pain_events:
            embedding = self.embedding_client.create_pain_event_embedding(event)
            embeddings.append(embedding)

        # 2. 使用向量相似度进行初步聚类
        logger.info("Performing vector similarity clustering...")
        similarity_threshold = self.clustering_config.get(
            "vector_similarity", {}
        ).get("similarity_threshold", 0.7)

        dbscan_eps = self.clustering_config.get(
            "dbscan", {}
        ).get("eps", 0.5)
        min_samples = self.clustering_config.get(
            "dbscan", {}
        ).get("min_samples", 3)

        # DBSCAN聚类
        clusters = self.embedding_client.cluster_embeddings(
            embeddings, eps=dbscan_eps, min_samples=min_samples
        )

        # 3. 分析每个聚类
        logger.info(f"Found {len(clusters)} clusters")
        cluster_results = []

        for cluster_id, indices in clusters.items():
            if len(indices) < 2:  # 跳过单个事件的聚类
                continue

            cluster_analysis = self.embedding_client.analyze_cluster(
                indices, embeddings, pain_events
            )

            cluster_result = {
                "cluster_id": cluster_id,
                "pain_event_ids": indices,
                "cluster_size": len(indices),
                "cohesion": cluster_analysis["cohesion"],
                "events": cluster_analysis["events"]
            }

            cluster_results.append(cluster_result)

        # 按聚类大小排序
        cluster_results.sort(key=lambda x: x["cluster_size"], reverse=True)

        logger.info(f"Successfully created {len(cluster_results)} clusters")
        return cluster_results

    def find_similar_events(
        self,
        target_event: Dict[str, Any],
        candidate_events: List[Dict[str, Any]],
        threshold: float = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """找到与目标事件相似的候选事件"""
        if threshold is None:
            threshold = self.clustering_config.get(
                "vector_similarity", {}
            ).get("similarity_threshold", 0.7)

        # 创建目标事件的嵌入
        target_embedding = self.embedding_client.create_pain_event_embedding(target_event)

        # 创建候选事件的嵌入
        candidate_embeddings = []
        for event in candidate_events:
            embedding = self.embedding_client.create_pain_event_embedding(event)
            candidate_embeddings.append(embedding)

        # 找到相似事件
        similar_indices = self.embedding_client.find_similar_events(
            target_embedding, candidate_embeddings, threshold, top_k
        )

        # 返回相似事件及其相似度
        results = []
        for idx, similarity in similar_indices:
            result = candidate_events[idx].copy()
            result["similarity_score"] = similarity
            results.append(result)

        return results

# 全局嵌入客户端实例
embedding_client = EmbeddingClient()
pain_clustering = PainEventClustering(embedding_client)
```


================================================================================
文件: utils/llm_client.py
================================================================================

```python
"""
LLM Client for Reddit Pain Point Finder
基于SiliconFlow API的LLM客户端
"""
import os
import json
import logging
import time
from typing import Dict, List, Any, Optional, Union
import yaml
from openai import OpenAI
import backoff
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

class LLMClient:
    """SiliconFlow LLM客户端"""

    def __init__(self, config_path: str = "config/llm.yaml"):
        """初始化LLM客户端"""
        self.config = self._load_config(config_path)
        self.client = self._init_client()
        self.stats = {
            "requests": 0,
            "tokens_used": 0,
            "cost": 0.0,
            "errors": 0
        }

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载LLM配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load LLM config from {config_path}: {e}")
            raise

    def _init_client(self) -> OpenAI:
        """初始化OpenAI客户端"""
        api_key = os.getenv(self.config['api']['api_key_env'])
        if not api_key:
            raise ValueError(f"API key not found in environment variable: {self.config['api']['api_key_env']}")

        return OpenAI(
            api_key=api_key,
            base_url=self.config['api']['base_url']
        )

    def get_model_name(self, model_type: str = "main") -> str:
        """获取指定类型的模型名称"""
        if model_type in self.config.get("models", {}):
            model_config = self.config["models"][model_type]
            # 如果有环境变量配置，优先使用
            env_name = model_config.get("env_name")
            if env_name and os.getenv(env_name):
                return os.getenv(env_name)
            return model_config["name"]

        # 从task_mapping中查找
        task_mapping = self.config.get("task_mapping", {})
        if model_type in task_mapping:
            mapped_model = task_mapping[model_type]["model"]
            return self.get_model_name(mapped_model)

        # 默认返回main模型
        return self.config["models"]["main"]["name"]

    def get_model_config(self, model_type: str = "main") -> Dict[str, Any]:
        """获取模型配置"""
        # 从task_mapping中查找
        task_mapping = self.config.get("task_mapping", {})
        if model_type in task_mapping:
            mapped_model = task_mapping[model_type]["model"]
            base_config = self.config["models"][mapped_model].copy()
            # 覆盖任务特定配置
            base_config.update(task_mapping[model_type])
            return base_config

        # 直接从models中查找
        if model_type in self.config.get("models", {}):
            return self.config["models"][model_type].copy()

        # 默认返回main模型配置
        return self.config["models"]["main"].copy()

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        base=1,
        max_value=60
    )
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model_type: str = "main",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False
    ) -> Dict[str, Any]:
        """聊天补全请求"""
        try:
            model_config = self.get_model_config(model_type)
            model_name = self.get_model_name(model_type)

            # 参数配置
            params = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature if temperature is not None else model_config.get("temperature", 0.1),
                "max_tokens": max_tokens if max_tokens is not None else model_config.get("max_tokens", 2000),
                "timeout": model_config.get("timeout", 30)
            }

            # JSON模式
            if json_mode:
                params["response_format"] = {"type": "json_object"}

            # 记录请求开始时间
            start_time = time.time()

            # 发送请求
            response = self.client.chat.completions.create(**params)

            # 计算请求时间
            request_time = time.time() - start_time

            # 更新统计信息
            self.stats["requests"] += 1
            if hasattr(response.usage, 'total_tokens'):
                self.stats["tokens_used"] += response.usage.total_tokens

            # 提取响应内容
            content = response.choices[0].message.content

            # 如果是JSON模式，尝试解析
            if json_mode:
                try:
                    content = json.loads(content)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response: {e}")
                    logger.error(f"Raw content: {content}")
                    # 尝试修复JSON
                    content = self._try_fix_json(content)

            result = {
                "content": content,
                "model": model_name,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0
                },
                "request_time": request_time
            }

            logger.info(f"LLM request completed: {result['usage']['total_tokens']} tokens in {request_time:.2f}s")
            return result

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"LLM request failed: {e}")
            raise

    def _try_fix_json(self, content: str) -> Dict[str, Any]:
        """尝试修复损坏的JSON"""
        try:
            # 尝试提取JSON部分
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                return json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
        except Exception as e:
            logger.error(f"Failed to fix JSON: {e}")
            return {"error": "Failed to parse JSON", "raw_content": content}

    def extract_pain_points(
        self,
        title: str,
        body: str,
        subreddit: str,
        upvotes: int,
        comments_count: int
    ) -> Dict[str, Any]:
        """从Reddit帖子中提取痛点"""
        prompt = self._get_pain_extraction_prompt()

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"""
Title: {title}
Body: {body}
Subreddit: {subreddit}
Upvotes: {upvotes}
Comments: {comments_count}
"""}
        ]

        return self.chat_completion(
            messages=messages,
            model_type="pain_extraction",
            json_mode=True
        )

    def cluster_pain_events(
        self,
        pain_events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """聚类痛点事件"""
        prompt = self._get_workflow_clustering_prompt()

        # 构建痛点事件文本
        events_text = "\n\n".join([
            f"Event {i+1}: {event.get('problem', '')} (Context: {event.get('context', '')}, Workaround: {event.get('current_workaround', '')})"
            for i, event in enumerate(pain_events)
        ])

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Pain events:\n{events_text}"}
        ]

        return self.chat_completion(
            messages=messages,
            model_type="clustering",
            json_mode=True
        )

    def map_opportunity(
        self,
        cluster_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """从痛点聚类映射机会"""
        prompt = self._get_opportunity_mapping_prompt()

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Pain cluster:\n{json.dumps(cluster_summary, indent=2)}"}
        ]

        return self.chat_completion(
            messages=messages,
            model_type="opportunity_mapping",
            json_mode=True
        )

    def score_viability(
        self,
        opportunity_description: str
    ) -> Dict[str, Any]:
        """评估机会可行性"""
        prompt = self._get_viability_scoring_prompt()

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Idea:\n{opportunity_description}"}
        ]

        return self.chat_completion(
            messages=messages,
            model_type="viability_scoring",
            json_mode=True
        )

    def validate_pain_signal(
        self,
        text: str
    ) -> Dict[str, Any]:
        """验证痛点信号"""
        prompt = self._get_signal_validation_prompt()

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ]

        return self.chat_completion(
            messages=messages,
            model_type="signal_validation",
            json_mode=True
        )

    def _get_pain_extraction_prompt(self) -> str:
        """获取痛点抽取提示"""
        return """You are an information extraction engine.

Your task:
From the following Reddit post, extract concrete PAIN EVENTS.
A pain event is a specific recurring problem experienced by the author,
not opinions, not general complaints.

Rules:
- Do NOT summarize the post
- Do NOT give advice
- If no concrete pain exists, return an empty list
- Be literal and conservative
- Focus on actionable problems people face repeatedly

Output JSON only with this format:
{
  "pain_events": [
    {
      "actor": "who experiences the problem",
      "context": "what they are trying to do",
      "problem": "the concrete difficulty",
      "current_workaround": "how they currently cope (if any)",
      "frequency": "how often it happens (explicit or inferred)",
      "emotional_signal": "frustration, anxiety, exhaustion, etc.",
      "mentioned_tools": ["tool1", "tool2"],
      "confidence": 0.8
    }
  ],
  "extraction_summary": "brief summary of findings"
}

Fields explanation:
- actor: who has this problem (developer, manager, user, etc.)
- context: the situation or workflow where the problem occurs
- problem: specific, concrete issue (not "things are slow" but "compilation takes 30 minutes")
- current_workaround: current solutions people use (if mentioned)
- frequency: how often this happens (daily, weekly, occasionally, etc.)
- emotional_signal: the emotion expressed (frustration, anger, disappointment, etc.)
- mentioned_tools: tools, software, or methods explicitly mentioned
- confidence: how confident you are this is a real pain point (0-1)"""

    def _get_workflow_clustering_prompt(self) -> str:
        """获取工作流聚类提示"""
        return """You are analyzing user pain events.

Given the following pain events, determine whether they belong to THE SAME UNDERLYING WORKFLOW problem.

A workflow means:
- the same repeated activity
- where different people fail in similar ways
- with similar root causes

If they belong to the same workflow:
- give the workflow a short descriptive name
- provide a brief description of the workflow
- estimate confidence (0-1)

If they should NOT be clustered:
- say they should not be clustered
- explain why briefly

Return JSON only with this format:
{
  "same_workflow": true/false,
  "workflow_name": "name if same workflow",
  "workflow_description": "description if same workflow",
  "confidence": 0.8,
  "reasoning": "brief explanation"
}

Be conservative - only cluster if they're clearly the same workflow."""

    def _get_opportunity_mapping_prompt(self) -> str:
        """获取机会映射提示"""
        return """You are a brutally practical product thinker for solo founders.

Given a cluster of pain events that belong to the same workflow:

1. Identify what tools people CURRENTLY use to survive this problem
2. Identify what capability is missing
3. Explain why existing tools fail (too heavy, too generic, etc.)
4. Propose ONE narrow micro-tool opportunity

Rules:
- No platforms (unless you can justify the MVP)
- No marketplaces
- Assume a solo founder building an MVP in 1-3 months
- Focus on specific, painful problems with clear solutions
- If no viable tool opportunity exists, say so

Return JSON only with this format:
{
  "current_tools": ["tool1", "tool2", "manual methods"],
  "missing_capability": "what's missing that would solve this",
  "why_existing_fail": "why current solutions don't work well",
  "opportunity": {
    "name": "short descriptive name",
    "description": "what the micro-tool does",
    "target_users": "who would use this",
    "pain_frequency": "how often this pain occurs (1-10)",
    "market_size": "how many people have this problem (1-10)",
    "mvp_complexity": "how hard to build MVP (1-10, lower is better)",
    "competition_risk": "risk of competitors (1-10, lower is better)",
    "integration_complexity": "how hard to integrate (1-10, lower is better)"
  }
}

Focus on narrow, specific problems that a solo founder can actually solve."""

    def _get_viability_scoring_prompt(self) -> str:
        """获取可行性评分提示"""
        return """You are an experienced solo-founder investor.

Score the following idea for a ONE-PERSON COMPANY.

Criteria:
- Pain frequency: How often does this pain occur? (daily=10, rarely=1)
- Clear buyer: Can we easily identify who would pay? (clear=10, vague=1)
- MVP buildable: Can one person build MVP in 1-3 months? (easy=10, hard=1)
- Crowded market: How competitive is this space? (empty=10, saturated=1)
- Integration: How easy to integrate with existing tools? (easy=10, hard=1)

Score each criteria 0-10, then calculate total score.

Also list the TOP 3 killer risks that could kill this project.

Return JSON only with this format:
{
  "scores": {
    "pain_frequency": 8,
    "clear_buyer": 7,
    "mvp_buildable": 6,
    "crowded_market": 5,
    "integration": 7
  },
  "total_score": 6.6,
  "killer_risks": [
    "Risk 1: specific and concrete",
    "Risk 2: specific and concrete",
    "Risk 3: specific and concrete"
  ],
  "recommendation": "pursue/modify/abandon with brief reason"
}

Be realistic and conservative in scoring."""

    def _get_signal_validation_prompt(self) -> str:
        """获取信号验证提示"""
        return """You are a pain signal validator.

Given this text, determine if it contains a genuine pain point.

A genuine pain point:
- Describes a specific problem or difficulty
- Shows frustration or struggle
- Is not just venting or seeking help
- Represents a recurring issue

Return JSON only with this format:
{
  "is_pain_point": true/false,
  "confidence": 0.8,
  "pain_type": "frustration/inefficiency/complexity/workflow/cost/other",
  "specificity": 0.9,  # How specific is the problem (0-1)
  "emotional_intensity": 0.7,  # How strong is the emotion (0-1)
  "keywords": ["struggling", "frustrated", "can't figure out"]
}

Be conservative - only flag clear pain points."""

    def get_statistics(self) -> Dict[str, Any]:
        """获取使用统计"""
        return self.stats.copy()

    def reset_statistics(self):
        """重置统计"""
        self.stats = {
            "requests": 0,
            "tokens_used": 0,
            "cost": 0.0,
            "errors": 0
        }

# 全局LLM客户端实例
llm_client = LLMClient()
```


================================================================================
提取完成
================================================================================
总共提取了 13 个文件
