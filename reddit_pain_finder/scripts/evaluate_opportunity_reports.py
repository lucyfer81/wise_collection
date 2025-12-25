#!/usr/bin/env python3
"""
Phase 3 Task 4: Opportunity Report Evaluator
评估机会分析报告的质量和完整性
"""
import sys
import os
import argparse
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OpportunityReportEvaluator:
    """机会报告评估器"""

    def __init__(self, reports_dir: str):
        """初始化评估器"""
        self.reports_dir = Path(reports_dir)
        logger.info(f"报告目录: {self.reports_dir}")

    def load_reports(self) -> List[Path]:
        """加载所有markdown报告"""
        logger.info("扫描报告文件...")
        md_files = list(self.reports_dir.glob("*.md"))
        # 排除README.md
        md_files = [f for f in md_files if f.name != "README.md"]
        logger.info(f"找到 {len(md_files)} 个报告文件")
        return md_files

    def evaluate_report(self, filepath: Path) -> Dict[str, Any]:
        """评估单个报告"""
        logger.debug(f"评估报告: {filepath.name}")

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        report_name = filepath.stem
        evaluation = {
            'file': filepath.name,
            'report_name': report_name,
            'metrics': {}
        }

        # 1. 检查评论证据 (comment|评论|evidence.*comment)
        comment_patterns = [
            r'评论|comment',
            r'evidence.*comment',
            r'comment.*evidence',
            r'反馈|feedback',
            r'用户反馈|user feedback'
        ]
        evaluation['metrics']['has_comment_evidence'] = any(
            re.search(pattern, content, re.IGNORECASE)
            for pattern in comment_patterns
        )

        # 2. 检查问题描述 (**问题**)
        problem_patterns = [
            r'\*\*问题\*\*',
            r'问题[:：]',
            r'核心问题',
            r'主要问题',
            r'问题分析',
            r'problem analysis',
            r'key problem'
        ]
        problem_matches = []
        for pattern in problem_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            problem_matches.extend(matches)

        evaluation['metrics']['has_problem_description'] = len(problem_matches) > 0
        evaluation['metrics']['problem_description_count'] = len(problem_matches)

        # 3. 检查MVP建议 (MVP|mvp|最小可行产品|feature.*suggest)
        mvp_patterns = [
            r'\bMVP\b',
            r'mvp',
            r'最小可行产品',
            r'feature.*suggest',
            r'suggest.*feature',
            r'功能建议',
            r'MVP功能',
            r'核心功能'
        ]
        evaluation['metrics']['has_mvp_suggestions'] = any(
            re.search(pattern, content, re.IGNORECASE)
            for pattern in mvp_patterns
        )

        # 4. 检查目标用户 (目标用户|target.*user|用户群体|user.*group)
        user_patterns = [
            r'目标用户',
            r'target.*user',
            r'用户群体',
            r'user.*group',
            r'目标受众',
            r'目标客户',
            r'user profile',
            r'user persona'
        ]
        evaluation['metrics']['has_target_users'] = any(
            re.search(pattern, content, re.IGNORECASE)
            for pattern in user_patterns
        )

        # 5. 检查风险分析 (风险|risk|挑战|challenge|障碍|barrier)
        risk_patterns = [
            r'风险',
            r'\brisk\b',
            r'挑战',
            r'\bchallenge\b',
            r'障碍',
            r'\bbarrier\b',
            r'潜在风险',
            r'主要风险',
            r'风险应对',
            r'killer risk'
        ]
        evaluation['metrics']['has_risk_analysis'] = any(
            re.search(pattern, content, re.IGNORECASE)
            for pattern in risk_patterns
        )

        # 6. 提取机会数量 (**<name>** (评分:)
        opportunity_pattern = r'\*\*([^*]+)\*\*\s*\(评分:\s*([\d.]+)\)'
        opportunity_matches = re.findall(opportunity_pattern, content)
        evaluation['metrics']['opportunity_count'] = len(opportunity_matches)

        # 提取机会名称和评分
        evaluation['opportunities'] = [
            {'name': name.strip(), 'score': float(score)}
            for name, score in opportunity_matches
        ]

        # 7. 文件大小和字符数
        evaluation['metrics']['file_size_bytes'] = filepath.stat().st_size
        evaluation['metrics']['char_count'] = len(content)
        evaluation['metrics']['line_count'] = len(content.split('\n'))

        # 8. 检查关键章节
        section_patterns = {
            'has_overview_section': r'聚类概览|概述|overview',
            'has_analysis_section': r'深度分析|详细分析|analysis',
            'has_design_section': r'产品设计|方案设计|design',
            'has_action_section': r'行动计划|可执行|action',
            'has_data_section': r'原始数据|数据|data'
        }

        for key, pattern in section_patterns.items():
            evaluation['metrics'][key] = bool(re.search(pattern, content, re.IGNORECASE))

        return evaluation

    def calculate_aggregated_metrics(self, evaluations: List[Dict]) -> Dict[str, Any]:
        """计算聚合指标"""
        total_reports = len(evaluations)

        if total_reports == 0:
            return {}

        aggregated = {
            'total_reports': total_reports,
            'completeness_scores': {},
            'content_metrics': {},
            'section_coverage': {}
        }

        # 完整性评分
        completeness_fields = [
            'has_comment_evidence',
            'has_problem_description',
            'has_mvp_suggestions',
            'has_target_users',
            'has_risk_analysis'
        ]

        for field in completeness_fields:
            count = sum(1 for e in evaluations if e['metrics'].get(field, False))
            aggregated['completeness_scores'][field] = {
                'count': count,
                'percentage': round(count / total_reports * 100, 2)
            }

        # 内容指标
        aggregated['content_metrics'] = {
            'avg_file_size': round(sum(e['metrics']['file_size_bytes'] for e in evaluations) / total_reports, 2),
            'avg_char_count': round(sum(e['metrics']['char_count'] for e in evaluations) / total_reports, 2),
            'avg_line_count': round(sum(e['metrics']['line_count'] for e in evaluations) / total_reports, 2),
            'total_opportunities': sum(e['metrics']['opportunity_count'] for e in evaluations),
            'avg_opportunities_per_report': round(sum(e['metrics']['opportunity_count'] for e in evaluations) / total_reports, 2)
        }

        # 章节覆盖率
        section_fields = [
            'has_overview_section',
            'has_analysis_section',
            'has_design_section',
            'has_action_section',
            'has_data_section'
        ]

        for field in section_fields:
            count = sum(1 for e in evaluations if e['metrics'].get(field, False))
            aggregated['section_coverage'][field] = {
                'count': count,
                'percentage': round(count / total_reports * 100, 2)
            }

        return aggregated

    def generate_markdown_report(self, evaluations: List[Dict], aggregated: Dict) -> str:
        """生成markdown报告"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        report = f"""# 机会分析报告质量评估

> **生成时间**: {timestamp}
> **评估报告数**: {aggregated.get('total_reports', 0)}

---

## 📊 总体概览

本次评估共分析了 {aggregated.get('total_reports', 0)} 份机会分析报告，从完整性、内容质量和章节覆盖三个维度进行评估。

---

## ✅ 完整性分析

### 关键要素覆盖情况

| 要素 | 报告数 | 覆盖率 |
|------|--------|--------|
"""

        for field, stats in aggregated.get('completeness_scores', {}).items():
            field_name_cn = {
                'has_comment_evidence': '评论证据',
                'has_problem_description': '问题描述',
                'has_mvp_suggestions': 'MVP建议',
                'has_target_users': '目标用户',
                'has_risk_analysis': '风险分析'
            }.get(field, field)

            report += f"| {field_name_cn} | {stats['count']} | {stats['percentage']}% |\n"

        report += f"""
---

## 📈 内容质量指标

### 文件规模

| 指标 | 数值 |
|------|------|
| 平均文件大小 | {aggregated.get('content_metrics', {}).get('avg_file_size', 0):.0f} bytes |
| 平均字符数 | {aggregated.get('content_metrics', {}).get('avg_char_count', 0):.0f} |
| 平均行数 | {aggregated.get('content_metrics', {}).get('avg_line_count', 0):.0f} |
| 机会总数 | {aggregated.get('content_metrics', {}).get('total_opportunities', 0)} |
| 平均每报告机会数 | {aggregated.get('content_metrics', {}).get('avg_opportunities_per_report', 0):.1f} |

---

## 📋 章节覆盖情况

### 必备章节完整性

| 章节 | 报告数 | 覆盖率 |
|------|--------|--------|
"""

        for field, stats in aggregated.get('section_coverage', {}).items():
            field_name_cn = {
                'has_overview_section': '聚类概览',
                'has_analysis_section': '深度分析',
                'has_design_section': '产品设计',
                'has_action_section': '行动计划',
                'has_data_section': '原始数据'
            }.get(field, field)

            report += f"| {field_name_cn} | {stats['count']} | {stats['percentage']}% |\n"

        report += """
---

## 📄 详细报告列表

### 各报告评估结果

"""

        for i, eval_result in enumerate(evaluations, 1):
            metrics = eval_result['metrics']

            completeness_count = sum([
                metrics.get('has_comment_evidence', False),
                metrics.get('has_problem_description', False),
                metrics.get('has_mvp_suggestions', False),
                metrics.get('has_target_users', False),
                metrics.get('has_risk_analysis', False)
            ])

            completeness_pct = round(completeness_count / 5 * 100, 1)

            report += f"""
#### {i}. {eval_result['report_name']}

**文件**: `{eval_result['file']}`
**完整性**: {completeness_pct}% ({completeness_count}/5)
**文件大小**: {metrics['file_size_bytes']} bytes
**字符数**: {metrics['char_count']}
**行数**: {metrics['line_count']}
**机会数**: {metrics['opportunity_count']}

**关键要素**:
- 评论证据: {'✅' if metrics.get('has_comment_evidence') else '❌'}
- 问题描述: {'✅' if metrics.get('has_problem_description') else '❌'}
- MVP建议: {'✅' if metrics.get('has_mvp_suggestions') else '❌'}
- 目标用户: {'✅' if metrics.get('has_target_users') else '❌'}
- 风险分析: {'✅' if metrics.get('has_risk_analysis') else '❌'}

"""

            if eval_result.get('opportunities'):
                report += "**识别的机会**:\n"
                for opp in eval_result['opportunities'][:5]:
                    report += f"- {opp['name']} (评分: {opp['score']:.2f})\n"
                report += "\n"

        report += """
---

## 💡 改进建议

### 短期改进 (1-2周)

1. **提升评论证据覆盖率**: 在报告中增加更多来自用户评论的直接引用和证据
2. **完善问题描述**: 确保每份报告都有清晰、具体的问题描述
3. **强化MVP建议**: 为每个机会提供更具体的MVP功能建议

### 中期优化 (1个月)

1. **标准化报告结构**: 确保所有报告包含完整的6个章节
2. **增强风险分析**: 深入分析每个机会的潜在风险和应对措施
3. **细化目标用户**: 提供更精确的用户画像和使用场景

### 长期提升 (持续)

1. **建立质量基准**: 设定最低质量标准，未达标报告需重新生成
2. **自动化检查**: 将评估指标集成到生成流程中，实时反馈
3. **持续迭代**: 根据用户反馈和市场需求调整分析维度

---

*本报告由 Opportunity Report Evaluator 自动生成*
"""

        return report

    def evaluate_all(self) -> Tuple[List[Dict], Dict[str, Any]]:
        """评估所有报告"""
        logger.info("开始评估所有报告...")

        report_files = self.load_reports()
        if not report_files:
            logger.warning("未找到任何报告文件")
            return [], {}

        evaluations = []
        for filepath in report_files:
            try:
                evaluation = self.evaluate_report(filepath)
                evaluations.append(evaluation)
                logger.debug(f"完成评估: {filepath.name}")
            except Exception as e:
                logger.error(f"评估失败 {filepath.name}: {e}")

        aggregated = self.calculate_aggregated_metrics(evaluations)

        logger.info(f"评估完成: {len(evaluations)} 份报告")
        return evaluations, aggregated


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Phase 3: 评估机会分析报告的质量和完整性"
    )
    parser.add_argument(
        "--reports-dir",
        default="pain_analysis_reports",
        help="报告目录路径 (默认: pain_analysis_reports)"
    )
    parser.add_argument(
        "--output",
        default="docs/reports/opportunity_report_evaluation.md",
        help="输出报告路径"
    )

    args = parser.parse_args()

    try:
        logger.info("=" * 60)
        logger.info("机会报告评估器启动")
        logger.info(f"报告目录: {args.reports_dir}")
        logger.info(f"输出文件: {args.output}")
        logger.info("=" * 60)

        # 创建评估器
        evaluator = OpportunityReportEvaluator(args.reports_dir)

        # 执行评估
        evaluations, aggregated = evaluator.evaluate_all()

        if not evaluations:
            logger.warning("未找到可评估的报告")
            return

        # 生成报告
        logger.info("生成markdown报告...")
        report_content = evaluator.generate_markdown_report(evaluations, aggregated)

        # 保存报告
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_content)

        logger.info(f"✅ 报告已保存: {output_path}")

        # 输出摘要
        print(f"\n📊 评估完成!")
        print(f"   • 评估报告数: {aggregated.get('total_reports', 0)}")
        print(f"   • 平均完整性: 计算中...")
        print(f"   • 输出文件: {output_path}")

        # 同时保存JSON数据
        json_path = output_path.with_suffix('.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                'evaluations': evaluations,
                'aggregated': aggregated,
                'timestamp': datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ JSON数据已保存: {json_path}")

    except Exception as e:
        logger.error(f"评估失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
