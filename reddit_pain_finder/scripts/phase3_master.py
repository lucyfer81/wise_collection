#!/usr/bin/env python3
"""
Phase 3 Task 6: Master Execution Script
编排完整的Phase 3工作流程
"""
import sys
import os
import argparse
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Phase3Master:
    """Phase 3主执行器"""

    def __init__(
        self,
        project_root: Path,
        limit_posts: int = 100,
        skip_pipeline: bool = False,
        metrics_file: str = None,
        min_score: float = 0.8,
        report_limit: int = 15
    ):
        """初始化主执行器"""
        self.project_root = project_root
        self.limit_posts = limit_posts
        self.skip_pipeline = skip_pipeline
        self.metrics_file = metrics_file
        self.min_score = min_score
        self.report_limit = report_limit

        self.scripts_dir = project_root / "scripts"
        self.execution_log = []

        logger.info("=" * 60)
        logger.info("Phase 3 Master Execution")
        logger.info(f"Project Root: {project_root}")
        logger.info(f"Limit Posts: {limit_posts}")
        logger.info(f"Skip Pipeline: {skip_pipeline}")
        logger.info(f"Min Score: {min_score}")
        logger.info(f"Report Limit: {report_limit}")
        logger.info("=" * 60)

    def run_script(self, script_name: str, args: List[str], step_name: str) -> Tuple[bool, str]:
        """运行脚本"""
        script_path = self.scripts_dir / script_name

        if not script_path.exists():
            error_msg = f"脚本不存在: {script_path}"
            logger.error(error_msg)
            return False, error_msg

        cmd = [sys.executable, str(script_path)] + args
        cmd_str = " ".join(cmd)

        logger.info(f"\n{'='*60}")
        logger.info(f"[执行] {step_name}")
        logger.info(f"命令: {cmd_str}")
        logger.info(f"{'='*60}")

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=3600  # 1小时超时
            )

            success = result.returncode == 0

            if success:
                logger.info(f"✅ {step_name} - 成功")
                output = result.stdout
            else:
                logger.error(f"❌ {step_name} - 失败")
                logger.error(f"STDOUT:\n{result.stdout}")
                logger.error(f"STDERR:\n{result.stderr}")
                output = result.stderr

            # 记录执行日志
            self.execution_log.append({
                'step': step_name,
                'script': script_name,
                'success': success,
                'timestamp': datetime.now().isoformat(),
                'output': output[-1000:] if len(output) > 1000 else output  # 只保留最后1000字符
            })

            return success, output

        except subprocess.TimeoutExpired:
            error_msg = f"{step_name} - 超时(1小时)"
            logger.error(error_msg)
            self.execution_log.append({
                'step': step_name,
                'script': script_name,
                'success': False,
                'timestamp': datetime.now().isoformat(),
                'error': error_msg
            })
            return False, error_msg

        except Exception as e:
            error_msg = f"{step_name} - 异常: {e}"
            logger.error(error_msg)
            self.execution_log.append({
                'step': step_name,
                'script': script_name,
                'success': False,
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            })
            return False, str(e)

    def step1_run_pipeline(self) -> Tuple[bool, str]:
        """Step 1: 运行完整流水线"""
        logger.info("\n" + "="*60)
        logger.info("STEP 1: 运行完整流水线")
        logger.info("="*60)

        if self.skip_pipeline:
            logger.info("⏭️ 跳过流水线执行 (使用现有指标)")

            if not self.metrics_file:
                error = "跳过流水线但未指定metrics文件"
                logger.error(error)
                return False, error

            return True, f"使用现有指标文件: {self.metrics_file}"

        args = [
            "--limit-posts", str(self.limit_posts)
        ]

        success, output = self.run_script(
            "run_phase3_full_pipeline.py",
            args,
            "Step 1: 运行完整流水线"
        )

        if not success:
            return False, output

        # 查找最新的metrics文件
        if not self.metrics_file:
            reports_dir = self.project_root / "docs" / "reports"
            metrics_files = sorted(
                reports_dir.glob("phase3_metrics_*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )

            if metrics_files:
                self.metrics_file = str(metrics_files[0])
                logger.info(f"自动找到metrics文件: {self.metrics_file}")
            else:
                error = "未找到metrics文件"
                logger.error(error)
                return False, error

        return True, f"流水线完成，metrics文件: {self.metrics_file}"

    def step2_analyze_pain_points(self) -> Tuple[bool, str]:
        """Step 2: 分析痛点并生成报告"""
        logger.info("\n" + "="*60)
        logger.info("STEP 2: 分析痛点并生成报告")
        logger.info("="*60)

        args = [
            "--min-score", str(self.min_score),
            "--limit", str(self.report_limit)
        ]

        # pain_point_analyzer.py is in project root, not scripts directory
        script_path = self.project_root / "pain_point_analyzer.py"

        cmd = [sys.executable, str(script_path)] + args
        cmd_str = " ".join(cmd)

        logger.info(f"\n{'='*60}")
        logger.info(f"[执行] Step 2: 分析痛点并生成报告")
        logger.info(f"命令: {cmd_str}")
        logger.info(f"{'='*60}")

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=3600  # 1小时超时
            )

            success = result.returncode == 0

            if success:
                logger.info(f"✅ Step 2: 分析痛点并生成报告 - 成功")
                output = result.stdout
            else:
                logger.error(f"❌ Step 2: 分析痛点并生成报告 - 失败")
                logger.error(f"STDOUT:\n{result.stdout}")
                logger.error(f"STDERR:\n{result.stderr}")
                output = result.stderr

            # 记录执行日志
            self.execution_log.append({
                'step': "Step 2: 分析痛点并生成报告",
                'script': "pain_point_analyzer.py",
                'success': success,
                'timestamp': datetime.now().isoformat(),
                'output': output[-1000:] if len(output) > 1000 else output
            })

            return success, output

        except subprocess.TimeoutExpired:
            error_msg = "Step 2: 分析痛点并生成报告 - 超时(1小时)"
            logger.error(error_msg)
            self.execution_log.append({
                'step': "Step 2: 分析痛点并生成报告",
                'script': "pain_point_analyzer.py",
                'success': False,
                'timestamp': datetime.now().isoformat(),
                'error': error_msg
            })
            return False, error_msg

        except Exception as e:
            error_msg = f"Step 2: 分析痛点并生成报告 - 异常: {e}"
            logger.error(error_msg)
            self.execution_log.append({
                'step': "Step 2: 分析痛点并生成报告",
                'script': "pain_point_analyzer.py",
                'success': False,
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            })
            return False, str(e)

    def step3_evaluate_reports(self) -> Tuple[bool, str]:
        """Step 3: 评估机会报告"""
        logger.info("\n" + "="*60)
        logger.info("STEP 3: 评估机会报告")
        logger.info("="*60)

        args = [
            "--reports-dir", "pain_analysis_reports",
            "--output", "docs/reports/opportunity_report_evaluation.md"
        ]

        return self.run_script(
            "evaluate_opportunity_reports.py",
            args,
            "Step 3: 评估机会报告"
        )

    def step4_generate_cost_report(self) -> Tuple[bool, str]:
        """Step 4: 生成成本性能报告"""
        logger.info("\n" + "="*60)
        logger.info("STEP 4: 生成成本性能报告")
        logger.info("="*60)

        if not self.metrics_file:
            error = "未指定metrics文件，无法生成成本报告"
            logger.error(error)
            return False, error

        args = [
            "--metrics", self.metrics_file,
            "--output", "docs/reports/phase3_cost_performance_report.md"
        ]

        return self.run_script(
            "generate_cost_performance_report.py",
            args,
            "Step 4: 生成成本性能报告"
        )

    def run_workflow(self) -> Dict[str, Any]:
        """运行完整工作流"""
        logger.info("\n" + "🚀"*30)
        logger.info("开始执行 Phase 3 完整工作流")
        logger.info("🚀"*30)

        start_time = datetime.now()

        # Step 1: 运行流水线
        step1_success, step1_output = self.step1_run_pipeline()
        if not step1_success:
            logger.error("Step 1 失败，终止工作流")
            return self.generate_summary(start_time)

        # Step 2: 分析痛点
        step2_success, step2_output = self.step2_analyze_pain_points()
        if not step2_success:
            logger.warning("Step 2 失败，继续执行后续步骤")

        # Step 3: 评估报告
        step3_success, step3_output = self.step3_evaluate_reports()
        if not step3_success:
            logger.warning("Step 3 失败，继续执行后续步骤")

        # Step 4: 生成成本报告
        step4_success, step4_output = self.step4_generate_cost_report()
        if not step4_success:
            logger.warning("Step 4 失败")

        return self.generate_summary(start_time)

    def generate_summary(self, start_time: datetime) -> Dict[str, Any]:
        """生成执行摘要"""
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        summary = {
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': duration,
            'duration_minutes': round(duration / 60, 2),
            'steps_completed': sum(1 for log in self.execution_log if log['success']),
            'steps_total': len(self.execution_log),
            'steps_failed': sum(1 for log in self.execution_log if not log['success']),
            'execution_log': self.execution_log
        }

        return summary

    def print_summary(self, summary: Dict[str, Any]):
        """打印执行摘要"""
        logger.info("\n" + "="*60)
        logger.info("工作流执行摘要")
        logger.info("="*60)

        logger.info(f"\n⏱️ 执行时间:")
        logger.info(f"   • 开始时间: {summary['start_time']}")
        logger.info(f"   • 结束时间: {summary['end_time']}")
        logger.info(f"   • 总耗时: {summary['duration_minutes']} 分钟")

        logger.info(f"\n📊 步骤统计:")
        logger.info(f"   • 总步骤数: {summary['steps_total']}")
        logger.info(f"   • 成功: {summary['steps_completed']}")
        logger.info(f"   • 失败: {summary['steps_failed']}")

        logger.info(f"\n📋 详细结果:")
        for log in summary['execution_log']:
            status = "✅" if log['success'] else "❌"
            logger.info(f"   {status} {log['step']}")

        if summary['steps_failed'] > 0:
            logger.warning(f"\n⚠️ 有 {summary['steps_failed']} 个步骤失败，请检查日志")
        else:
            logger.info(f"\n🎉 所有步骤执行成功!")

        logger.info("="*60)

    def save_execution_log(self, summary: Dict[str, Any]):
        """保存执行日志"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.project_root / "docs" / "reports" / f"phase3_execution_log_{timestamp}.json"

        log_file.parent.mkdir(parents=True, exist_ok=True)

        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"💾 执行日志已保存: {log_file}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Phase 3: 主执行脚本 - 编排完整工作流"
    )
    parser.add_argument(
        "--limit-posts",
        type=int,
        default=100,
        help="处理的帖子数量 (默认: 100)"
    )
    parser.add_argument(
        "--skip-pipeline",
        action="store_true",
        help="跳过流水线执行，使用现有metrics文件"
    )
    parser.add_argument(
        "--metrics-file",
        type=str,
        default=None,
        help="指定metrics文件路径 (与--skip-pipeline配合使用)"
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.8,
        help="最低机会评分 (默认: 0.8)"
    )
    parser.add_argument(
        "--report-limit",
        type=int,
        default=15,
        help="最大报告数量 (默认: 15)"
    )

    args = parser.parse_args()

    try:
        # 获取项目根目录
        project_root = Path(__file__).parent.parent

        # 创建主执行器
        master = Phase3Master(
            project_root=project_root,
            limit_posts=args.limit_posts,
            skip_pipeline=args.skip_pipeline,
            metrics_file=args.metrics_file,
            min_score=args.min_score,
            report_limit=args.report_limit
        )

        # 运行工作流
        summary = master.run_workflow()

        # 打印摘要
        master.print_summary(summary)

        # 保存执行日志
        master.save_execution_log(summary)

        # 返回退出码
        if summary['steps_failed'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断执行")
        sys.exit(130)
    except Exception as e:
        logger.error(f"执行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
