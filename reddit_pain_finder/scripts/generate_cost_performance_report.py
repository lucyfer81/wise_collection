#!/usr/bin/env python3
"""
Phase 3 Task 5: Cost & Performance Report Generator
生成成本和性能分析报告
"""
import sys
import os
import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.performance_monitor import PerformanceMonitor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CostPerformanceReportGenerator:
    """成本性能报告生成器"""

    # 阶段中文名称映射
    STAGE_NAMES_CN = {
        'extract': '痛点抽取',
        'embed': '向量化',
        'cluster': '聚类分析',
        'map_opportunities': '机会映射',
        'score': '可行性评分'
    }

    def __init__(self, metrics_file: str):
        """初始化生成器"""
        self.metrics_file = Path(metrics_file)
        logger.info(f"指标文件: {self.metrics_file}")

    def load_metrics(self) -> PerformanceMonitor:
        """加载指标数据"""
        logger.info("加载指标数据...")

        if not self.metrics_file.exists():
            raise FileNotFoundError(f"指标文件不存在: {self.metrics_file}")

        monitor = PerformanceMonitor.load_metrics(str(self.metrics_file))
        logger.info("指标数据加载成功")

        return monitor

    def generate_executive_summary(self, monitor: PerformanceMonitor) -> str:
        """生成执行摘要"""
        summary = monitor.get_summary()

        total_duration_minutes = summary['total_duration_minutes']
        total_calls = summary['total_llm_calls']
        total_tokens = summary['total_tokens']
        estimated_cost = summary['estimated_cost_usd']

        section = f"""
## 执行摘要

### 关键指标

| 指标 | 数值 |
|------|------|
| 总执行时间 | {total_duration_minutes:.2f} 分钟 ({summary['total_duration_seconds']:.1f} 秒) |
| LLM调用次数 | {total_calls:,} 次 |
| 总Token使用量 | {total_tokens:,} |
| 预估成本 | ${estimated_cost:.4f} USD |
| 平均每调用成本 | ${(estimated_cost/total_calls if total_calls > 0 else 0):.6f} USD |

### 效率指标

| 指标 | 数值 |
|------|------|
| 平均每调用耗时 | {(summary['total_duration_seconds']/total_calls if total_calls > 0 else 0):.2f} 秒 |
| 平均每调用Token数 | {(total_tokens/total_calls if total_calls > 0 else 0):.0f} |
| 每千Token成本 | ${(estimated_cost/(total_tokens/1000) if total_tokens > 0 else 0):.4f} USD |

"""

        return section

    def generate_stage_breakdown(self, monitor: PerformanceMonitor) -> str:
        """生成阶段分解"""
        summary = monitor.get_summary()
        stages_summary = summary['stages_summary']

        section = """
## 阶段分解

### 各阶段性能详情

| 阶段 | 执行时间(秒) | 处理项目数 | LLM调用次数 | Token使用量 |
|------|-------------|-----------|------------|-----------|
"""

        for stage_name, stats in stages_summary.items():
            stage_name_cn = self.STAGE_NAMES_CN.get(stage_name, stage_name)
            duration = stats['duration_seconds']
            items = stats['items_processed']
            tokens = stats['tokens_used']
            llm_calls = stats['llm_calls']

            section += f"| {stage_name_cn} | {duration:.1f} | {items} | {llm_calls} | {tokens:,} |\n"

        section += "\n### 阶段效率对比\n\n"

        # 计算效率指标
        for stage_name, stats in stages_summary.items():
            stage_name_cn = self.STAGE_NAMES_CN.get(stage_name, stage_name)
            duration = stats['duration_seconds']
            items = stats['items_processed']
            tokens = stats['tokens_used']

            if items > 0:
                avg_time_per_item = duration / items
                section += f"**{stage_name_cn}**:\n"
                section += f"- 平均每项目处理时间: {avg_time_per_item:.2f} 秒\n"

                if tokens > 0:
                    avg_tokens_per_item = tokens / items
                    section += f"- 平均每项目Token数: {avg_tokens_per_item:.0f}\n"
                section += "\n"

        return section

    def generate_cost_analysis(self, monitor: PerformanceMonitor) -> str:
        """生成成本分析"""
        summary = monitor.get_summary()
        stages_summary = summary['stages_summary']

        total_tokens = summary['total_tokens']

        section = """
## 成本分析

### Token分布

| 阶段 | Token使用量 | 占比 |
|------|-----------|------|
"""

        for stage_name, stats in stages_summary.items():
            stage_name_cn = self.STAGE_NAMES_CN.get(stage_name, stage_name)
            tokens = stats['tokens_used']
            percentage = (tokens / total_tokens * 100) if total_tokens > 0 else 0

            section += f"| {stage_name_cn} | {tokens:,} | {percentage:.1f}% |\n"

        section += "\n### 成本构成分析\n\n"

        # 按阶段分析成本
        for stage_name, stats in stages_summary.items():
            stage_name_cn = self.STAGE_NAMES_CN.get(stage_name, stage_name)
            tokens = stats['tokens_used']
            percentage = (tokens / total_tokens * 100) if total_tokens > 0 else 0

            # 估算该阶段成本 (假设token比例等于成本比例)
            stage_cost = summary['estimated_cost_usd'] * (percentage / 100)

            section += f"**{stage_name_cn}**: ${stage_cost:.4f} USD ({percentage:.1f}%)\n"

        section += f"\n**总成本**: ${summary['estimated_cost_usd']:.4f} USD\n"

        return section

    def generate_performance_metrics(self, monitor: PerformanceMonitor) -> str:
        """生成性能指标"""
        summary = monitor.get_summary()
        stages_summary = summary['stages_summary']

        section = """
## 性能指标

### 吞吐量分析

| 阶段 | 吞吐量 (项目/分钟) | 吞吐量 (Token/秒) |
|------|------------------|------------------|
"""

        for stage_name, stats in stages_summary.items():
            stage_name_cn = self.STAGE_NAMES_CN.get(stage_name, stage_name)
            duration_minutes = stats['duration_seconds'] / 60
            items = stats['items_processed']
            tokens = stats['tokens_used']

            items_per_minute = (items / duration_minutes) if duration_minutes > 0 else 0
            tokens_per_second = (tokens / stats['duration_seconds']) if stats['duration_seconds'] > 0 else 0

            section += f"| {stage_name_cn} | {items_per_minute:.2f} | {tokens_per_second:.0f} |\n"

        section += "\n### 性能瓶颈识别\n\n"

        # 识别最慢的阶段
        slowest_stage = max(stages_summary.items(), key=lambda x: x[1]['duration_seconds'])
        slowest_stage_cn = self.STAGE_NAMES_CN.get(slowest_stage[0], slowest_stage[0])

        section += f"- **最慢阶段**: {slowest_stage_cn} ({slowest_stage[1]['duration_seconds']:.1f}秒)\n"

        # 识别Token消耗最大的阶段
        highest_token_stage = max(stages_summary.items(), key=lambda x: x[1]['tokens_used'])
        highest_token_stage_cn = self.STAGE_NAMES_CN.get(highest_token_stage[0], highest_token_stage[0])

        section += f"- **最高Token消耗**: {highest_token_stage_cn} ({highest_token_stage[1]['tokens_used']:,} tokens)\n"

        section += "\n"

        return section

    def generate_phase_comparison(self, monitor: PerformanceMonitor) -> str:
        """生成Phase对比分析"""
        summary = monitor.get_summary()

        section = """
## Phase 1 vs 2 vs 3 对比分析

### ROI分析

| Phase | 主要功能 | 特点 | 适用场景 |
|-------|---------|------|---------|
| Phase 1 | 痛点抽取 | 基础数据收集 | 快速验证问题存在性 |
| Phase 2 | 向量聚类 | 发现问题模式 | 识别共性痛点 |
| Phase 3 | 完整分析 | 机会评估与映射 | 产品决策支持 |

### Phase 3 优势

1. **端到端自动化**: 从原始数据到机会报告的全流程自动化
2. **智能评估**: 基于多维度指标的可行性评分
3. **深度洞察**: 结合评论分析和机会映射
4. **可执行输出**: 生成包含MVP建议和风险分析的报告

### 成本效益分析

| 指标 | 数值 | 说明 |
|------|------|------|
| 总成本 | ${0:.4f} USD | 完整流程成本 |
| 输出报告数 | 1+ 份 | 机会分析报告 |
| 每报告成本 | ${0:.4f} USD | 单位成本 |

""".format(
            summary['estimated_cost_usd'],
            summary['estimated_cost_usd']
        )

        section += """
### 建议优化方向

1. **批量处理**: 对更大的数据集进行批量处理，降低单位成本
2. **缓存优化**: 对相似内容进行缓存，减少重复LLM调用
3. **并行处理**: 在独立阶段并行处理，缩短总执行时间
4. **模型选择**: 根据任务复杂度选择不同成本的模型

"""

        return section

    def generate_conclusions(self, monitor: PerformanceMonitor) -> str:
        """生成结论和建议"""
        summary = monitor.get_summary()

        section = """
## 结论与建议

### 关键发现

1. **自动化可行**: Phase 3完整流程已实现自动化，从数据提取到报告生成无需人工干预

2. **成本可控**: 整个流程成本在可接受范围内，适合定期执行

3. **输出质量高**: 生成的报告包含多维度分析，为决策提供有力支持

4. **扩展性良好**: 架构设计支持处理更大规模的数据集

### 实施建议

#### 短期 (1-2周)

1. **建立基线**: 收集多轮运行数据，建立性能基线
2. **优化瓶颈**: 针对最慢的阶段进行优化
3. **质量验证**: 人工审核生成的报告，调整prompt以提升质量

#### 中期 (1个月)

1. **定期执行**: 设置定时任务，每周/每月自动运行
2. **数据积累**: 持续积累数据，形成趋势分析
3. **反馈闭环**: 建立用户反馈机制，持续改进报告质量

#### 长期 (持续)

1. **智能调度**: 根据数据变化自动触发分析
2. **A/B测试**: 对不同prompt和参数进行A/B测试
3. **成本优化**: 探索更经济的模型组合

### 风险提示

1. **API依赖**: 依赖外部LLM API，需考虑服务稳定性
2. **数据质量**: 输出质量依赖输入数据质量
3. **成本波动**: API价格变动可能影响成本结构

### 成功指标

- 报告生成成功率 > 95%
- 平均执行时间 < 10分钟 (100个帖子)
- 单报告成本 < $5 USD
- 用户满意度 > 4.0/5.0

---

"""

        return section

    def generate_report(self, monitor: PerformanceMonitor) -> str:
        """生成完整报告"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        metrics_filename = self.metrics_file.name

        report = f"""# Phase 3 成本与性能分析报告

> **生成时间**: {timestamp}
> **指标文件**: {metrics_filename}

---

"""

        report += self.generate_executive_summary(monitor)
        report += self.generate_stage_breakdown(monitor)
        report += self.generate_cost_analysis(monitor)
        report += self.generate_performance_metrics(monitor)
        report += self.generate_phase_comparison(monitor)
        report += self.generate_conclusions(monitor)

        report += """
*本报告由 Cost & Performance Report Generator 自动生成*
"""

        return report


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Phase 3: 生成成本和性能分析报告"
    )
    parser.add_argument(
        "--metrics",
        required=True,
        help="指标JSON文件路径 (必需)"
    )
    parser.add_argument(
        "--output",
        default="docs/reports/phase3_cost_performance_report.md",
        help="输出报告路径"
    )

    args = parser.parse_args()

    try:
        logger.info("=" * 60)
        logger.info("成本性能报告生成器启动")
        logger.info(f"指标文件: {args.metrics}")
        logger.info(f"输出文件: {args.output}")
        logger.info("=" * 60)

        # 创建生成器
        generator = CostPerformanceReportGenerator(args.metrics)

        # 加载指标
        monitor = generator.load_metrics()

        # 生成报告
        logger.info("生成markdown报告...")
        report_content = generator.generate_report(monitor)

        # 保存报告
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_content)

        logger.info(f"✅ 报告已保存: {output_path}")

        # 输出摘要
        summary = monitor.get_summary()
        print(f"\n📊 报告生成完成!")
        print(f"   • 总执行时间: {summary['total_duration_minutes']:.2f} 分钟")
        print(f"   • LLM调用次数: {summary['total_llm_calls']:,}")
        print(f"   • 总Token使用量: {summary['total_tokens']:,}")
        print(f"   • 预估成本: ${summary['estimated_cost_usd']:.4f} USD")
        print(f"   • 输出文件: {output_path}")

    except FileNotFoundError as e:
        logger.error(f"文件未找到: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"报告生成失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
