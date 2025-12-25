# Phase 3: 全面运行、评估与优化

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 在全量数据上部署新流程，评估最终"商业机会报告"的价值，并量化新流程带来的成本变化

**架构:** 创建性能监控脚本 → 运行全量数据处理 → 生成商业机会报告 → 分析成本与性能 → 输出评估报告

**Tech Stack:** Python 3.10+, SQLite, LLM API (SiliconFlow), Markdown reports

---

## 任务概述

Phase 3包含以下主要任务：

1. **性能监控脚本** - 跟踪LLM调用和成本
2. **全量数据处理** - 运行完整流水线
3. **商业价值评估** - 分析生成的机会报告
4. **成本性能报告** - 生成ROI分析

---

## Task 1: 创建性能监控装饰器

**Files:**
- Create: `utils/performance_monitor.py`

**Step 1: 创建性能监控基础类**

```python
"""
Performance monitoring utility for Phase 3
Tracks LLM calls, token usage, and execution time
"""
import time
import json
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from functools import wraps
import logging

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.metrics = {
            "start_time": None,
            "end_time": None,
            "stages": {},
            "llm_calls": {
                "total_calls": 0,
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_cost": 0.0,
                "calls_by_stage": {}
            }
        }

    def start_stage(self, stage_name: str):
        """开始一个阶段"""
        if stage_name not in self.metrics["stages"]:
            self.metrics["stages"][stage_name] = {
                "start_time": datetime.now().isoformat(),
                "end_time": None,
                "duration_seconds": 0,
                "items_processed": 0,
                "llm_calls": 0,
                "tokens_used": 0
            }
        else:
            # 如果已存在，更新开始时间
            self.metrics["stages"][stage_name]["start_time"] = datetime.now().isoformat()

    def end_stage(self, stage_name: str, items_processed: int = 0):
        """结束一个阶段"""
        if stage_name in self.metrics["stages"]:
            self.metrics["stages"][stage_name]["end_time"] = datetime.now().isoformat()

            # 计算持续时间
            start = datetime.fromisoformat(self.metrics["stages"][stage_name]["start_time"])
            end = datetime.fromisoformat(self.metrics["stages"][stage_name]["end_time"])
            self.metrics["stages"][stage_name]["duration_seconds"] = (end - start).total_seconds()
            self.metrics["stages"][stage_name]["items_processed"] = items_processed

    def record_llm_call(self, stage_name: str, usage: Dict[str, Any]):
        """记录LLM调用"""
        self.metrics["llm_calls"]["total_calls"] += 1

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        self.metrics["llm_calls"]["prompt_tokens"] += prompt_tokens
        self.metrics["llm_calls"]["completion_tokens"] += completion_tokens
        self.metrics["llm_calls"]["total_tokens"] += total_tokens

        # 更新阶段统计
        if stage_name not in self.metrics["llm_calls"]["calls_by_stage"]:
            self.metrics["llm_calls"]["calls_by_stage"][stage_name] = {
                "calls": 0,
                "tokens": 0
            }

        self.metrics["llm_calls"]["calls_by_stage"][stage_name]["calls"] += 1
        self.metrics["llm_calls"]["calls_by_stage"][stage_name]["tokens"] += total_tokens

        if stage_name in self.metrics["stages"]:
            self.metrics["stages"][stage_name]["llm_calls"] += 1
            self.metrics["stages"][stage_name]["tokens_used"] += total_tokens

    def calculate_cost(self, prompt_price_per_1k: float = 0.001,
                      completion_price_per_1k: float = 0.002):
        """计算成本（根据实际定价调整）"""
        prompt_cost = (self.metrics["llm_calls"]["prompt_tokens"] / 1000) * prompt_price_per_1k
        completion_cost = (self.metrics["llm_calls"]["completion_tokens"] / 1000) * completion_price_per_1k
        self.metrics["llm_calls"]["total_cost"] = prompt_cost + completion_cost

        return self.metrics["llm_calls"]["total_cost"]

    def get_summary(self) -> Dict[str, Any]:
        """获取统计摘要"""
        # 计算总时间
        if self.metrics["stages"]:
            total_duration = sum(
                stage["duration_seconds"]
                for stage in self.metrics["stages"].values()
            )
        else:
            total_duration = 0

        return {
            "total_duration_seconds": total_duration,
            "total_duration_minutes": round(total_duration / 60, 2),
            "total_llm_calls": self.metrics["llm_calls"]["total_calls"],
            "total_tokens": self.metrics["llm_calls"]["total_tokens"],
            "estimated_cost_usd": self.calculate_cost(),
            "stages_summary": {
                name: {
                    "duration_seconds": stage["duration_seconds"],
                    "items_processed": stage["items_processed"],
                    "llm_calls": stage["llm_calls"],
                    "tokens_used": stage["tokens_used"]
                }
                for name, stage in self.metrics["stages"].items()
            }
        }

    def save_metrics(self, filepath: str):
        """保存指标到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.metrics, f, indent=2, default=str)

    @classmethod
    def load_metrics(cls, filepath: str) -> 'PerformanceMonitor':
        """从文件加载指标"""
        monitor = cls()
        with open(filepath, 'r', encoding='utf-8') as f:
            monitor.metrics = json.load(f)
        return monitor


# 全局监控器实例
performance_monitor = PerformanceMonitor()
```

**Step 2: 测试性能监控类**

Run: `python3 -c "from utils.performance_monitor import PerformanceMonitor; pm = PerformanceMonitor(); pm.start_stage('test'); pm.end_stage('test', 10); print(pm.get_summary())"`

Expected: `{'total_duration_seconds': ..., 'stages_summary': {'test': {...}}}`

**Step 3: 提交**

```bash
git add utils/performance_monitor.py
git commit -m "feat: add performance monitor for Phase 3"
```

---

## Task 2: 集成性能监控到LLM客户端

**Files:**
- Modify: `utils/llm_client.py:91-178`

**Step 1: 修改chat_completion方法以集成监控**

在 `utils/llm_client.py` 顶部添加导入：
```python
from utils.performance_monitor import performance_monitor
```

修改 `chat_completion` 方法，在记录请求时间后添加：
```python
# 在第160行附近，response获取之后
performance_monitor.record_llm_call(
    stage_name=model_type,
    usage=result["usage"]
)
```

**Step 2: 测试监控集成**

Run: `python3 -c "from utils.llm_client import llm_client; from utils.performance_monitor import performance_monitor; llm_client.validate_pain_signal('test'); print(performance_monitor.get_summary())"`

Expected: 显示包含LLM调用统计的摘要

**Step 3: 提交**

```bash
git add utils/llm_client.py
git commit -m "feat: integrate performance monitor into LLM client"
```

---

## Task 3: 创建全量流水线运行脚本

**Files:**
- Create: `scripts/run_phase3_full_pipeline.py`

**Step 1: 创建脚本主框架**

```python
#!/usr/bin/env python3
"""
Phase 3: Full Pipeline Execution with Performance Monitoring
运行完整流水线并收集性能数据
"""
import sys
import os
import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pipeline.extract_pain import PainPointExtractor
from pipeline.embed import PainEventEmbedder
from pipeline.cluster import PainEventClusterer
from pipeline.score_viability import ViabilityScorer
from pipeline.map_opportunity import OpportunityMapper
from utils.performance_monitor import performance_monitor
from utils.db import db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_phase3_pipeline(limit_posts: int = 100, save_metrics: bool = True):
    """运行Phase 3完整流水线"""

    logger.info("=" * 60)
    logger.info("PHASE 3: Full Pipeline Execution")
    logger.info(f"Limit: {limit_posts} posts")
    logger.info("=" * 60)

    results = {}

    # Stage 1: Extract Pain Points
    logger.info("\n[Stage 1/5] Extracting pain points...")
    performance_monitor.start_stage("extract")

    try:
        extractor = PainPointExtractor()
        extract_result = extractor.process_unextracted_posts(limit=limit_posts)
        results["extract"] = extract_result

        performance_monitor.end_stage("extract", extract_result.get("processed", 0))
        logger.info(f"✓ Extracted {extract_result.get('pain_events_saved', 0)} pain events")
    except Exception as e:
        logger.error(f"✗ Extraction failed: {e}")
        performance_monitor.end_stage("extract", 0)
        results["extract"] = {"error": str(e)}

    # Stage 2: Create Embeddings
    logger.info("\n[Stage 2/5] Creating embeddings...")
    performance_monitor.start_stage("embed")

    try:
        embedder = PainEventEmbedder()
        embed_result = embedder.process_missing_embeddings(limit=limit_posts * 2)
        results["embed"] = embed_result

        performance_monitor.end_stage("embed", embed_result.get("embeddings_created", 0))
        logger.info(f"✓ Created {embed_result.get('embeddings_created', 0)} embeddings")
    except Exception as e:
        logger.error(f"✗ Embedding failed: {e}")
        performance_monitor.end_stage("embed", 0)
        results["embed"] = {"error": str(e)}

    # Stage 3: Cluster Pain Events
    logger.info("\n[Stage 3/5] Clustering pain events...")
    performance_monitor.start_stage("cluster")

    try:
        clusterer = PainEventClusterer()
        cluster_result = clusterer.cluster_pain_events(limit=limit_posts * 2)
        results["cluster"] = cluster_result

        performance_monitor.end_stage("cluster", cluster_result.get("clusters_created", 0))
        logger.info(f"✓ Created {cluster_result.get('clusters_created', 0)} clusters")
    except Exception as e:
        logger.error(f"✗ Clustering failed: {e}")
        performance_monitor.end_stage("cluster", 0)
        results["cluster"] = {"error": str(e)}

    # Stage 4: Map Opportunities
    logger.info("\n[Stage 4/5] Mapping opportunities...")
    performance_monitor.start_stage("map_opportunities")

    try:
        mapper = OpportunityMapper()
        map_result = mapper.map_opportunities_for_clusters(limit=50)
        results["map_opportunities"] = map_result

        performance_monitor.end_stage("map_opportunities", map_result.get("opportunities_created", 0))
        logger.info(f"✓ Mapped {map_result.get('opportunities_created', 0)} opportunities")
    except Exception as e:
        logger.error(f"✗ Opportunity mapping failed: {e}")
        performance_monitor.end_stage("map_opportunities", 0)
        results["map_opportunities"] = {"error": str(e)}

    # Stage 5: Score Viability
    logger.info("\n[Stage 5/5] Scoring viability...")
    performance_monitor.start_stage("score")

    try:
        scorer = ViabilityScorer()
        score_result = scorer.score_opportunities(limit=100)
        results["score"] = score_result

        performance_monitor.end_stage("score", score_result.get("opportunities_scored", 0))
        logger.info(f"✓ Scored {score_result.get('opportunities_scored', 0)} opportunities")
    except Exception as e:
        logger.error(f"✗ Viability scoring failed: {e}")
        performance_monitor.end_stage("score", 0)
        results["score"] = {"error": str(e)}

    # Generate Summary
    logger.info("\n" + "=" * 60)
    logger.info("PIPELINE COMPLETE - GENERATING SUMMARY")
    logger.info("=" * 60)

    summary = performance_monitor.get_summary()

    logger.info(f"\n📊 Performance Summary:")
    logger.info(f"   • Total Duration: {summary['total_duration_minutes']} minutes")
    logger.info(f"   • LLM Calls: {summary['total_llm_calls']}")
    logger.info(f"   • Total Tokens: {summary['total_tokens']:,}")
    logger.info(f"   • Est. Cost: ${summary['estimated_cost_usd']:.4f} USD")

    logger.info(f"\n📈 Stage Details:")
    for stage_name, stage_stats in summary['stages_summary'].items():
        logger.info(f"   • {stage_name}:")
        logger.info(f"     - Duration: {stage_stats['duration_seconds']:.1f}s")
        logger.info(f"     - Items: {stage_stats['items_processed']}")
        logger.info(f"     - Tokens: {stage_stats['tokens_used']:,}")

    # Save metrics
    if save_metrics:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        metrics_file = f"docs/reports/phase3_metrics_{timestamp}.json"
        os.makedirs(os.path.dirname(metrics_file), exist_ok=True)
        performance_monitor.save_metrics(metrics_file)
        logger.info(f"\n💾 Metrics saved to: {metrics_file}")

    return results, summary


def main():
    parser = argparse.ArgumentParser(description="Phase 3 Full Pipeline Execution")
    parser.add_argument("--limit-posts", type=int, default=100,
                       help="Number of posts to process (default: 100)")
    parser.add_argument("--no-save", action="store_true",
                       help="Don't save metrics to file")

    args = parser.parse_args()

    try:
        results, summary = run_phase3_pipeline(
            limit_posts=args.limit_posts,
            save_metrics=not args.no_save
        )

        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"docs/reports/phase3_results_{timestamp}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({"results": results, "summary": summary}, f, indent=2)

        logger.info(f"\n✅ All results saved to: {results_file}")

    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**Step 2: 赋予执行权限并测试**

Run: `chmod +x scripts/run_phase3_full_pipeline.py`

Run (dry run with small limit): `python3 scripts/run_phase3_full_pipeline.py --limit-posts 5`

Expected: Pipeline runs through all stages and generates metrics file

**Step 3: 提交**

```bash
git add scripts/run_phase3_full_pipeline.py
git commit -m "feat: add Phase 3 full pipeline script with monitoring"
```

---

## Task 4: 创建商业机会评估脚本

**Files:**
- Create: `scripts/evaluate_opportunity_reports.py`

**Step 1: 创建评估脚本**

```python
#!/usr/bin/env python3
"""
Phase 3: Evaluate Opportunity Reports
评估生成的商业机会报告质量
"""
import sys
import os
import argparse
import json
import re
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pain_point_analyzer import PainPointAnalyzer


class OpportunityReportEvaluator:
    """商业机会报告评估器"""

    def __init__(self):
        self.evaluation_metrics = {
            "total_reports": 0,
            "reports_with_comment_evidence": 0,
            "avg_problem_length": 0,
            "reports_with_mvp_suggestions": 0,
            "reports_with_target_users": 0,
            "reports_with_risk_analysis": 0,
            "top_opportunities": []
        }

    def analyze_report(self, report_path: str) -> dict:
        """分析单个报告文件"""
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()

        metrics = {
            "file_path": report_path,
            "has_comment_evidence": False,
            "problem_descriptions": [],
            "has_mvp_suggestion": False,
            "has_target_users": False,
            "has_risk_analysis": False,
            "opportunity_count": 0
        }

        # 检查是否引用评论作为证据
        comment_patterns = [
            r'评论|comment',
            r'evidence.*comment',
            r'来源.*评论|source.*comment'
        ]
        for pattern in comment_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                metrics["has_comment_evidence"] = True
                break

        # 提取问题描述（在典型痛点事件部分）
        problem_section = re.search(
            r'### 典型痛点事件.*?(?=###|---|$)',
            content,
            re.DOTALL
        )
        if problem_section:
            problems = re.findall(r'\*\*问题\*\*:\s*(.+?)(?=\n|$)', problem_section.group(0))
            metrics["problem_descriptions"] = [p.strip() for p in problems]

        # 检查MVP建议
        mvp_patterns = [
            r'MVP|mvp',
            r'最小可行产品',
            r'功能建议|feature.*suggest'
        ]
        for pattern in mvp_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                metrics["has_mvp_suggestion"] = True
                break

        # 检查目标用户
        user_patterns = [
            r'目标用户|target.*user',
            r'用户群体|user.*group',
            r'适用.*人|for.*who'
        ]
        for pattern in user_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                metrics["has_target_users"] = True
                break

        # 检查风险分析
        risk_patterns = [
            r'风险|risk',
            r'挑战|challenge',
            r'障碍|barrier'
        ]
        for pattern in risk_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                metrics["has_risk_analysis"] = True
                break

        # 计算机会数量
        opportunity_matches = re.findall(r'\*\*([^*]+)\*\*\s*\(评分:', content)
        metrics["opportunity_count"] = len(opportunity_matches)

        return metrics

    def evaluate_directory(self, reports_dir: str) -> dict:
        """评估目录中的所有报告"""
        reports_path = Path(reports_dir)
        if not reports_path.exists():
            print(f"❌ Reports directory not found: {reports_dir}")
            return {}

        markdown_files = list(reports_path.glob("*.md"))
        # 排除README文件
        markdown_files = [f for f in markdown_files if f.name.lower() != 'readme.md']

        print(f"📊 Found {len(markdown_files)} reports to evaluate")

        all_metrics = []

        for report_file in markdown_files:
            print(f"  • Analyzing: {report_file.name}")
            metrics = self.analyze_report(str(report_file))
            all_metrics.append(metrics)

        # 汇总统计
        if all_metrics:
            self.evaluation_metrics["total_reports"] = len(all_metrics)
            self.evaluation_metrics["reports_with_comment_evidence"] = sum(
                1 for m in all_metrics if m["has_comment_evidence"]
            )

            # 平均问题描述长度
            all_problems = []
            for m in all_metrics:
                all_problems.extend(m["problem_descriptions"])

            if all_problems:
                avg_length = sum(len(p) for p in all_problems) / len(all_problems)
                self.evaluation_metrics["avg_problem_length"] = round(avg_length, 1)

            self.evaluation_metrics["reports_with_mvp_suggestions"] = sum(
                1 for m in all_metrics if m["has_mvp_suggestion"]
            )
            self.evaluation_metrics["reports_with_target_users"] = sum(
                1 for m in all_metrics if m["has_target_users"]
            )
            self.evaluation_metrics["reports_with_risk_analysis"] = sum(
                1 for m in all_metrics if m["has_risk_analysis"]
            )

            # Top 3 opportunities (by opportunity count)
            all_metrics.sort(key=lambda x: x["opportunity_count"], reverse=True)
            self.evaluation_metrics["top_opportunities"] = [
                {
                    "file": m["file_path"],
                    "opportunity_count": m["opportunity_count"]
                }
                for m in all_metrics[:3]
            ]

        return self.evaluation_metrics

    def generate_evaluation_report(self) -> str:
        """生成评估报告"""
        metrics = self.evaluation_metrics

        if metrics["total_reports"] == 0:
            return "# No reports to evaluate\n"

        report = f"""# Phase 3: 商业机会报告质量评估

**评估时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**评估报告数量**: {metrics['total_reports']}

---

## 📊 总体评分

| 指标 | 数值 | 占比 |
|------|------|------|
| **总报告数** | {metrics['total_reports']} | 100% |
| **包含评论证据** | {metrics['reports_with_comment_evidence']} | {metrics['reports_with_comment_evidence']/max(metrics['total_reports'],1)*100:.1f}% |
| **包含MVP建议** | {metrics['reports_with_mvp_suggestions']} | {metrics['reports_with_mvp_suggestions']/max(metrics['total_reports'],1)*100:.1f}% |
| **明确目标用户** | {metrics['reports_with_target_users']} | {metrics['reports_with_target_users']/max(metrics['total_reports'],1)*100:.1f}% |
| **包含风险分析** | {metrics['reports_with_risk_analysis']} | {metrics['reports_with_risk_analysis']/max(metrics['total_reports'],1)*100:.1f}% |
| **平均问题描述长度** | {metrics['avg_problem_length']} 字符 | - |

---

## 🎯 关键发现

### 1. 市场证据质量
{'✅ 优秀' if metrics['reports_with_comment_evidence']/metrics['total_reports'] > 0.7 else '⚠️ 需改进'} \
- {metrics['reports_with_comment_evidence']}/{metrics['total_reports']} 份报告引用了评论作为市场证据
- 评论证据增强了报告的说服力

### 2. 可操作性评估
{'✅ 优秀' if metrics['reports_with_mvp_suggestions']/metrics['total_reports'] > 0.7 else '⚠️ 需改进'} \
- {metrics['reports_with_mvp_suggestions']}/{metrics['total_reports']} 份报告包含MVP功能建议
- {metrics['reports_with_target_users']}/{metrics['total_reports']} 份报告明确了目标用户群体

### 3. 问题描述质量
平均问题描述长度: **{metrics['avg_problem_length']}** 字符
{'✅ 优秀 (具体)' if metrics['avg_problem_length'] > 50 else '⚠️ 需改进 (过于简略)'}

### 4. 风险意识
{'✅ 优秀' if metrics['reports_with_risk_analysis']/metrics['total_reports'] > 0.5 else '⚠️ 需改进'} \
- {metrics['reports_with_risk_analysis']}/{metrics['total_reports']} 份报告包含风险分析

---

## 🏆 Top 3 机会报告

"""

        for i, opp in enumerate(metrics["top_opportunities"], 1):
            report_name = Path(opp["file"]).stem
            report_name = report_name.replace("_opportunity_analysis", "").replace("_", " ").title()
            report += f"{i}. **{report_name}**\n"
            report += f"   - 机会数量: {opp['opportunity_count']}\n"
            report += f"   - 文件: `{opp['file']}`\n\n"

        report += """---

## 📝 建议

### 立即可行动项
1. **优先级排序**: 根据机会评分和市场规模选择Top 3机会
2. **用户验证**: 针对Top 3机会进行用户访谈
3. **MVP规划**: 为最高价值机会制定3个月MVP开发计划

### 质量改进建议
"""

        if metrics['reports_with_comment_evidence'] / metrics['total_reports'] < 0.7:
            report += "- 提升评论证据引用率（当前<70%）\n"
        if metrics['avg_problem_length'] < 50:
            report += "- 增强问题描述的具体性（当前<50字符）\n"
        if metrics['reports_with_mvp_suggestions'] / metrics['total_reports'] < 0.7:
            report += "- 补充更多MVP功能建议\n"

        report += "\n---\n\n*本报告由 Phase 3 评估脚本自动生成*\n"

        return report


def main():
    parser = argparse.ArgumentParser(description="Evaluate Phase 3 opportunity reports")
    parser.add_argument("--reports-dir", type=str, default="pain_analysis_reports",
                       help="Path to reports directory (default: pain_analysis_reports)")
    parser.add_argument("--output", type=str, default=None,
                       help="Output report path (default: docs/reports/phase3_evaluation_YYYYMMDD.md)")

    args = parser.parse_args()

    print("🔍 Starting opportunity report evaluation...")
    print(f"   Reports directory: {args.reports_dir}")

    # Run evaluation
    evaluator = OpportunityReportEvaluator()
    metrics = evaluator.evaluate_directory(args.reports_dir)

    if not metrics:
        print("❌ No reports found or evaluation failed")
        sys.exit(1)

    # Generate report
    report_content = evaluator.generate_evaluation_report()

    # Save report
    if args.output is None:
        timestamp = datetime.now().strftime("%Y%m%d")
        args.output = f"docs/reports/phase3_evaluation_{timestamp}.md"

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report_content)

    print(f"\n✅ Evaluation complete!")
    print(f"   • Reports evaluated: {metrics['total_reports']}")
    print(f"   • Evaluation report: {args.output}")


if __name__ == "__main__":
    main()
```

**Step 2: 赋予执行权限**

Run: `chmod +x scripts/evaluate_opportunity_reports.py`

**Step 3: 测试脚本（需要先生成一些报告）**

Run: `python3 pain_point_analyzer.py --limit 5 --dry-run` （检查是否有数据）

**Step 4: 提交**

```bash
git add scripts/evaluate_opportunity_reports.py
git commit -m "feat: add opportunity report evaluation script"
```

---

## Task 5: 创建成本性能分析报告生成器

**Files:**
- Create: `scripts/generate_cost_performance_report.py`

**Step 1: 创建报告生成器**

```python
#!/usr/bin/env python3
"""
Phase 3: Generate Cost & Performance Analysis Report
生成成本与性能分析报告
"""
import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.performance_monitor import PerformanceMonitor


def generate_cost_performance_report(metrics_file: str, output_file: str = None) -> str:
    """生成成本与性能分析报告"""

    # Load metrics
    monitor = PerformanceMonitor.load_metrics(metrics_file)
    summary = monitor.get_summary()

    # Generate report
    report = f"""# Phase 3: 成本与性能分析报告

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**数据来源**: {metrics_file}

---

## 📊 执行摘要

本次Phase 3运行处理了完整的数据流水线，包括痛点抽取、向量化、聚类、机会映射和可行性评分。

### 关键指标

| 指标 | 数值 |
|------|------|
| **总运行时间** | {summary['total_duration_minutes']} 分钟 |
| **LLM API调用次数** | {summary['total_llm_calls']:,} |
| **Token消耗总量** | {summary['total_tokens']:,} |
| **预估成本** | ${summary['estimated_cost_usd']:.4f} USD |

---

## 🔍 阶段详细分析

"""

    # Stage breakdown
    for stage_name, stage_stats in summary['stages_summary'].items():
        stage_name_cn = {
            "extract": "痛点抽取",
            "embed": "向量化",
            "cluster": "聚类",
            "map_opportunities": "机会映射",
            "score": "可行性评分"
        }.get(stage_name, stage_name)

        report += f"""### {stage_name_cn} ({stage_name})

| 指标 | 数值 |
|------|------|
| **运行时长** | {stage_stats['duration_seconds']:.1f} 秒 |
| **处理项目数** | {stage_stats['items_processed']} |
| **LLM调用次数** | {stage_stats['llm_calls']} |
| **Token消耗** | {stage_stats['tokens_used']:,} |
| **每项目平均Token** | {stage_stats['tokens_used'] / max(stage_stats['items_processed'], 1):.0f} |
| **每项目平均时间** | {stage_stats['duration_seconds'] / max(stage_stats['items_processed'], 1):.2f} 秒 |

"""

    # Cost breakdown
    report += """---

## 💰 成本分析

### Token消耗分布（按阶段）

| 阶段 | Token消耗 | 占比 |
|------|----------|------|
"""

    total_tokens = summary['total_tokens']
    for stage_name, stage_stats in summary['stages_summary'].items():
        percentage = (stage_stats['tokens_used'] / total_tokens * 100) if total_tokens > 0 else 0
        stage_name_cn = {
            "extract": "痛点抽取",
            "embed": "向量化",
            "cluster": "聚类",
            "map_opportunities": "机会映射",
            "score": "可行性评分"
        }.get(stage_name, stage_name)
        report += f"| {stage_name_cn} | {stage_stats['tokens_used']:,} | {percentage:.1f}% |\n"

    report += f"| **总计** | **{total_tokens:,}** | **100%** |\n"

    # Cost estimation
    report += f"""

### 成本预估（基于SiliconFlow定价）

| 项目 | 数值 |
|------|------|
| **总成本** | ${summary['estimated_cost_usd']:.4f} USD |
| **每100个帖子成本** | ${(summary['estimated_cost_usd'] / max(summary['stages_summary'].get('extract', {}).get('items_processed', 1), 1)) * 100:.4f} USD |
| **每个机会成本** | ${(summary['estimated_cost_usd'] / max(summary['stages_summary'].get('map_opportunities', {}).get('items_processed', 1), 1)):.4f} USD |

---

## 📈 性能指标

### 处理效率

| 阶段 | 吞吐量 |
|------|--------|
"""

    for stage_name, stage_stats in summary['stages_summary'].items():
        if stage_stats['items_processed'] > 0 and stage_stats['duration_seconds'] > 0:
            throughput = stage_stats['items_processed'] / (stage_stats['duration_seconds'] / 60)
            stage_name_cn = {
                "extract": "痛点抽取",
                "embed": "向量化",
                "cluster": "聚类",
                "map_opportunities": "机会映射",
                "score": "可行性评分"
            }.get(stage_name, stage_name)
            report += f"| {stage_name_cn} | {throughput:.1f} 项目/分钟 |\n"

    report += """

---

## 🔄 Phase 1 vs Phase 2 vs Phase 3 对比

### 质量改进ROI分析

根据Phase 2质量分析结果：

| 指标 | Phase 1 (无评论) | Phase 2 (含评论) | 改进幅度 |
|------|-----------------|-----------------|----------|
| **每帖子痛点事件** | 0.2 | 1.8 | **+900%** |
| **问题描述长度** | 8.6 字符 | 67.4 字符 | **+684%** |
| **提取置信度** | 0.087 | 0.514 | **+491%** |
| **Token消耗** | ~600 | ~1,500 | +150% |
| **成本增加** | 基准 | ~2.5x | - |

### ROI计算

假设Phase 1处理100个帖子的成本为 $X：
- Phase 2成本: $2.5X
- 质量提升: 9倍痛点事件 × 684% 特异性提升
- **ROI**: (9 × 6.84) / 2.5 = **24.6x**

**结论**: Phase 2的额外投入带来了近25倍的回报（以质量产出计）。

---

## 📝 结论与建议

### 关键发现

1. **成本可控**: 每个帖子的完整处理成本约为 ${summary['estimated_cost_usd'] / max(summary['stages_summary'].get('extract', {}).get('items_processed', 1), 1):.4f} USD
2. **质量显著**: 评论感知提取带来了9倍的痛点事件发现率
3. **ROI优秀**: 质量提升幅度远超成本增长幅度

### 优化建议

#### 短期（立即可做）
1. **批量折扣**: 检查SiliconFlow是否有批量API折扣
2. **缓存策略**: 对相似帖子复用提取结果
3. **并行处理**: 在extract阶段使用多线程/协程

#### 中期（需要开发）
1. **模型选择**: 在早期阶段使用更便宜的模型进行筛选
2. **自适应采样**: 根据评论质量动态调整top_n参数
3. **增量更新**: 只处理新增/变化的帖子

#### 长期（需要架构调整）
1. **本地模型**: 考虑部署开源模型降低API成本
2. **分层处理**: 不同质量的帖子使用不同成本的策略
3. **结果缓存**: 建立缓存层避免重复计算

---

## 📊 原始数据

完整的性能指标已保存在: `{metrics_file}`

如需查看详细数据，请使用:
```bash
cat {metrics_file} | jq .
```

---

*本报告由 Phase 3 成本性能分析脚本自动生成*
"""

    return report


def main():
    parser = argparse.ArgumentParser(description="Generate Phase 3 cost & performance report")
    parser.add_argument("--metrics", type=str, required=True,
                       help="Path to metrics JSON file")
    parser.add_argument("--output", type=str, default=None,
                       help="Output report path (default: docs/reports/phase3_cost_performance_YYYYMMDD.md)")

    args = parser.parse_args()

    if not os.path.exists(args.metrics):
        print(f"❌ Metrics file not found: {args.metrics}")
        sys.exit(1)

    print("📊 Generating cost & performance report...")
    print(f"   Metrics file: {args.metrics}")

    # Generate report
    report_content = generate_cost_performance_report(args.metrics, args.output)

    # Save report
    if args.output is None:
        timestamp = datetime.now().strftime("%Y%m%d")
        args.output = f"docs/reports/phase3_cost_performance_{timestamp}.md"

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report_content)

    print(f"\n✅ Report generated successfully!")
    print(f"   Output: {args.output}")


if __name__ == "__main__":
    main()
```

**Step 2: 赋予执行权限**

Run: `chmod +x scripts/generate_cost_performance_report.py`

**Step 3: 提交**

```bash
git add scripts/generate_cost_performance_report.py
git commit -m "feat: add cost & performance report generator"
```

---

## Task 6: 创建Phase 3主执行脚本

**Files:**
- Create: `scripts/phase3_master.py`

**Step 1: 创建主执行脚本**

```python
#!/usr/bin/env python3
"""
Phase 3 Master Script
执行完整的Phase 3流程：数据处理 → 报告生成 → 质量评估 → 成本分析
"""
import sys
import os
import argparse
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_command(cmd: list, description: str) -> bool:
    """运行命令并显示进度"""
    print(f"\n{'='*60}")
    print(f"🔄 {description}")
    print(f"{'='*60}")

    result = subprocess.run(cmd, capture_output=False)
    success = result.returncode == 0

    if success:
        print(f"✅ {description} - 完成")
    else:
        print(f"❌ {description} - 失败")

    return success


def main():
    parser = argparse.ArgumentParser(description="Phase 3 Master: Complete Evaluation Pipeline")
    parser.add_argument("--limit-posts", type=int, default=100,
                       help="Number of posts to process (default: 100)")
    parser.add_argument("--skip-pipeline", action="store_true",
                       help="Skip pipeline execution (use existing metrics)")
    parser.add_argument("--metrics-file", type=str, default=None,
                       help="Path to existing metrics file (if --skip-pipeline)")
    parser.add_argument("--min-score", type=float, default=0.8,
                       help="Minimum opportunity score for reports (default: 0.8)")
    parser.add_argument("--report-limit", type=int, default=10,
                       help="Number of opportunity reports to generate (default: 10)")

    args = parser.parse_args()

    print("="*60)
    print("PHASE 3: 全面运行、评估与优化")
    print("="*60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"处理规模: {args.limit_posts} 个帖子")

    metrics_file = args.metrics_file
    steps_completed = []
    steps_failed = []

    # Step 1: Run full pipeline with monitoring
    if not args.skip_pipeline:
        if run_command(
            ["python3", "scripts/run_phase3_full_pipeline.py", "--limit-posts", str(args.limit_posts)],
            "步骤 1/4: 运行完整数据处理流水线"
        ):
            steps_completed.append("数据处理流水线")
            # Find the latest metrics file
            reports_dir = project_root / "docs" / "reports"
            if reports_dir.exists():
                metrics_files = list(reports_dir.glob("phase3_metrics_*.json"))
                if metrics_files:
                    metrics_file = str(max(metrics_files, key=os.path.getctime))
                    print(f"   📁 Metrics file: {metrics_file}")
        else:
            steps_failed.append("数据处理流水线")
            print("❌ 流水线执行失败，终止后续步骤")
            sys.exit(1)
    else:
        if not metrics_file or not os.path.exists(metrics_file):
            print(f"❌ Metrics file not found: {metrics_file}")
            sys.exit(1)
        print(f"   📁 Using existing metrics: {metrics_file}")
        steps_completed.append("数据处理流水线 (跳过)")

    # Step 2: Generate opportunity reports
    if run_command(
        ["python3", "pain_point_analyzer.py", "--limit", str(args.report_limit), "--min-score", str(args.min_score)],
        "步骤 2/4: 生成商业机会评估报告"
    ):
        steps_completed.append("商业机会报告生成")
    else:
        steps_failed.append("商业机会报告生成")

    # Step 3: Evaluate opportunity reports
    if run_command(
        ["python3", "scripts/evaluate_opportunity_reports.py"],
        "步骤 3/4: 评估商业机会报告质量"
    ):
        steps_completed.append("商业机会报告质量评估")
    else:
        steps_failed.append("商业机会报告质量评估")

    # Step 4: Generate cost & performance report
    if metrics_file and os.path.exists(metrics_file):
        if run_command(
            ["python3", "scripts/generate_cost_performance_report.py", "--metrics", metrics_file],
            "步骤 4/4: 生成成本与性能分析报告"
        ):
            steps_completed.append("成本与性能分析报告")
        else:
            steps_failed.append("成本与性能分析报告")
    else:
        print("⚠️  跳过成本分析（无metrics文件）")
        steps_failed.append("成本与性能分析报告 (跳过)")

    # Summary
    print("\n" + "="*60)
    print("PHASE 3 执行摘要")
    print("="*60)
    print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    print(f"\n✅ 完成的步骤 ({len(steps_completed)}):")
    for step in steps_completed:
        print(f"   • {step}")

    if steps_failed:
        print(f"\n❌ 失败的步骤 ({len(steps_failed)}):")
        for step in steps_failed:
            print(f"   • {step}")

    print(f"\n📁 生成的报告位于: docs/reports/")
    print(f"   • phase3_results_*.json - 流水线执行结果")
    print(f"   • phase3_metrics_*.json - 性能指标")
    print(f"   • phase3_evaluation_*.md - 商业机会报告质量评估")
    print(f"   • phase3_cost_performance_*.md - 成本与性能分析")
    print(f"   • pain_analysis_reports/ - 商业机会评估报告")

    print("\n🎉 Phase 3 执行完成！")

    # Return exit code based on failures
    sys.exit(0 if not steps_failed else 1)


if __name__ == "__main__":
    main()
```

**Step 2: 赋予执行权限**

Run: `chmod +x scripts/phase3_master.py`

**Step 3: 提交**

```bash
git add scripts/phase3_master.py
git commit -m "feat: add Phase 3 master execution script"
```

---

## Task 7: 执行Phase 3（小规模测试）

**Files:**
- Test: All created scripts

**Step 1: 准备测试环境**

Run: `ls -la pain_analysis_reports/` （检查是否有现有报告）

Run: `sqlite3 data/wise_collection.db "SELECT COUNT(*) FROM filtered_posts WHERE pain_score >= 0.3"` （检查可处理数据）

**Step 2: 运行小规模测试（5个帖子）**

Run: `python3 scripts/phase3_master.py --limit-posts 5 --report-limit 3`

Expected: 所有4个步骤成功完成，生成报告文件

**Step 3: 检查生成的报告**

Run: `ls -lah docs/reports/ | grep phase3`

Expected: 看到phase3相关的报告文件

**Step 4: 手动验证报告质量**

Run: `cat docs/reports/phase3_evaluation_*.md` （查看评估报告）

Run: `ls pain_analysis_reports/*.md | head -3` （查看生成的机会报告）

**Step 5: 提交测试结果**

```bash
git add docs/reports/
git commit -m "test: add Phase 3 small-scale test results"
```

---

## Task 8: 执行Phase 3（中等规模，100个帖子）

**Files:**
- Execution: Production run

**Step 1: 运行中等规模测试**

Run: `python3 scripts/phase3_master.py --limit-posts 100 --report-limit 10`

Expected Time: 约30-60分钟（取决于数据量和API响应速度）

**Step 2: 监控执行进度**

观察输出日志，确保每个阶段正常执行

**Step 3: 完成后检查结果**

Run: `cat docs/reports/phase3_evaluation_*.md`

Run: `cat docs/reports/phase3_cost_performance_*.md`

**Step 4: 生成最终摘要报告**

手动创建 `docs/reports/phase3_final_summary.md`，包含：
- 执行摘要
- 关键发现
- ROI分析
- 建议和下一步

**Step 5: 提交最终结果**

```bash
git add docs/reports/ pain_analysis_reports/
git commit -m "docs: add Phase 3 full evaluation results (100 posts)"
```

---

## Task 9: 文档和总结

**Files:**
- Create: `docs/reports/phase3_final_summary.md`

**Step 1: 创建最终总结报告**

```markdown
# Phase 3: 全面运行、评估与优化 - 最终总结报告

**执行日期**: 2025-12-25
**数据处理规模**: 100个帖子
**执行状态**: ✅ 完成

---

## 🎯 目标回顾

Phase 3的核心目标：
1. ✅ 在全量数据上部署新流程
2. ✅ 评估"商业机会报告"的价值
3. ✅ 量化新流程带来的成本变化

---

## 📊 主要成果

### 1. 全量数据处理

- **处理规模**: 100个Reddit/HN帖子
- **痛点事件**: [数量]个（Phase 2增强后）
- **聚类数量**: [数量]个
- **商业机会**: [数量]个

### 2. 商业价值评估

#### Top 3 商业机会（根据最终报告填写）

1. **[机会名称]** - 评分: [分数]
   - 目标用户: [用户群体]
   - 市场证据: [评论引用情况]

2. **[机会名称]** - 评分: [分数]
   - 目标用户: [用户群体]
   - 市场证据: [评论引用情况]

3. **[机会名称]** - 评分: [分数]
   - 目标用户: [用户群体]
   - 市场证据: [评论引用情况]

#### 报告质量指标

| 指标 | 数值 | 评价 |
|------|------|------|
| 包含评论证据 | [X]% | [优秀/需改进] |
| 平均问题描述长度 | [X] 字符 | [优秀/需改进] |
| 包含MVP建议 | [X]% | [优秀/需改进] |
| 明确目标用户 | [X]% | [优秀/需改进] |
| 包含风险分析 | [X]% | [优秀/需改进] |

### 3. 成本与性能分析

#### Token消耗

| 阶段 | Token消耗 | 占比 | 成本 |
|------|----------|------|------|
| 痛点抽取 | [数量] | [X]% | $[金额] |
| 向量化 | [数量] | [X]% | $[金额] |
| 聚类 | [数量] | [X]% | $[金额] |
| 机会映射 | [数量] | [X]% | $[金额] |
| 可行性评分 | [数量] | [X]% | $[金额] |
| **总计** | **[数量]** | **100%** | **$[金额]** |

#### 性能指标

- **总运行时间**: [X] 分钟
- **处理吞吐量**: [X] 帖子/分钟
- **LLM调用次数**: [X] 次
- **每帖子成本**: $[X] USD

---

## 📈 Phase 1 vs Phase 2 vs Phase 3 对比

### 质量提升

| 指标 | Phase 1 | Phase 2 | Phase 3 (实际) |
|------|---------|---------|---------------|
| 痛点事件/帖子 | 0.2 | 1.8 | [X] |
| 问题描述长度 | 8.6 | 67.4 | [X] |
| 提取置信度 | 0.087 | 0.514 | [X] |

### 成本变化

| 项目 | Phase 1 | Phase 2 | Phase 3 (实际) |
|------|---------|---------|---------------|
| Token/帖子 | ~600 | ~1,500 | [X] |
| 成本/帖子 | $[X] | $[X] | $[X] |
| 总成本 (100帖子) | $[X] | $[X] | $[X] |

### ROI分析

**Phase 2 ROI**: 24.6x (基于Phase 2数据)
**Phase 3 ROI**: [计算基于实际数据]

---

## ✅ 可验证成果

### 1. 全量机会报告
- 📁 位置: `pain_analysis_reports/`
- 📊 数量: [X] 份报告
- ⭐ 质量: [评价]

### 2. 性能与成本分析报告
- 📁 位置: `docs/reports/phase3_cost_performance_*.md`
- 📊 包含: Token消耗、成本分析、性能指标、ROI计算

### 3. 商业价值评估报告
- 📁 位置: `docs/reports/phase3_evaluation_*.md`
- 📊 包含: 质量指标、Top机会、改进建议

---

## 🎯 关键发现

### 1. 商业机会质量
[填写基于实际数据的发现]

### 2. 成本效益
[填写基于实际数据的发现]

### 3. 报告可操作性
[填写基于实际数据的发现]

---

## 💡 建议与下一步

### 立即可行
1. [基于实际数据的建议]
2. [基于实际数据的建议]
3. [基于实际数据的建议]

### 中期优化
1. [基于实际数据的建议]
2. [基于实际数据的建议]

### 长期规划
1. [基于实际数据的建议]
2. [基于实际数据的建议]

---

## 📝 结论

Phase 3成功完成了全面评估：

✅ **数据处理**: 在[数量]个帖子上验证了新流程
✅ **商业价值**: 生成了[数量]份高质量的商业机会报告
✅ **成本分析**: 量化了新流程的成本变化，ROI为[X]倍

**总体评价**: [成功/部分成功/需要改进]

[补充详细评价]

---

*报告生成时间: [datetime]*
*报告生成者: Phase 3 自动化流水线*
```

**Step 2: 提交最终文档**

```bash
git add docs/reports/phase3_final_summary.md
git commit -m "docs: add Phase 3 final summary report"
```

---

## 📋 验收标准

Phase 3完成需满足以下标准：

### 功能性
- ✅ 性能监控脚本正常工作
- ✅ 完整流水线可以成功运行
- ✅ 商业机会报告成功生成
- ✅ 评估脚本输出准确的质量指标
- ✅ 成本报告包含完整的Token和成本分析

### 质量性
- ✅ 至少生成5份以上的商业机会报告
- ✅ 报告质量评估显示：
  - >70%报告包含评论证据
  - 平均问题描述长度>50字符
  - >50%报告包含MVP建议

### 文档性
- ✅ 性能报告文档完整
- ✅ 成本分析数据准确
- ✅ 最终总结报告清晰

---

## 🎯 执行选项

完成计划后，提供执行选项：

**Plan complete and saved to `docs/plans/2025-12-25-phase3-full-evaluation.md`.**

**Two execution options:**

**1. Subagent-Driven (this session)** - 我分派任务给子代理，逐步执行并审查
   - 适合：需要逐步验证和调试
   - 时间：较慢，但更可控

**2. Direct Execution (I implement directly)** - 我直接按计划逐步实施
   - 适合：快速实施，任务明确
   - 时间：更快

**Which approach?**
