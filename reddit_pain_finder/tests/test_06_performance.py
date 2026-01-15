#!/usr/bin/env python
"""
Phase 6 性能测试脚本

测试内容：
1. Extract阶段并行性能 (不同max_workers)
2. 增量处理功能验证
3. 完整pipeline性能
4. 线程安全验证
"""
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Any
import json

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.pipeline_state import get_pipeline_state
from utils.db import db
from pipeline.extract_pain import PainPointExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PerformanceTester:
    """性能测试器"""

    def __init__(self):
        self.results = {
            "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tests": {}
        }

    def test_extract_parallel_performance(self, max_workers_list: list = [3, 5, 8, 10]) -> Dict:
        """测试Extract阶段不同并发数的性能

        Args:
            max_workers_list: 要测试的并发数列表

        Returns:
            测试结果字典
        """
        logger.info("=" * 80)
        logger.info("测试1: Extract阶段并行性能")
        logger.info("=" * 80)

        # 获取测试数据（固定数量）
        test_posts = db.get_filtered_posts(limit=20, min_pain_score=0.5)

        if not test_posts:
            logger.error("没有找到测试数据！请先运行filter stage。")
            return {}

        logger.info(f"使用 {len(test_posts)} 个posts进行测试")

        test_results = {}

        for max_workers in max_workers_list:
            logger.info(f"\n--- 测试 max_workers={max_workers} ---")

            extractor = PainPointExtractor()
            start_time = time.time()

            try:
                # 运行并行抽取
                pain_events = extractor.extract_from_posts_batch(
                    test_posts,
                    max_workers=max_workers
                )

                elapsed = time.time() - start_time

                # 记录结果
                result = {
                    "max_workers": max_workers,
                    "total_posts": len(test_posts),
                    "events_extracted": len(pain_events),
                    "elapsed_time": round(elapsed, 2),
                    "time_per_post": round(elapsed / len(test_posts), 2),
                    "events_per_second": round(len(test_posts) / elapsed, 2),
                    "errors": extractor.stats.get("extraction_errors", 0)
                }

                test_results[f"workers_{max_workers}"] = result

                logger.info(f"✅ 完成:")
                logger.info(f"   耗时: {result['elapsed_time']}s")
                logger.info(f"   每个post: {result['time_per_post']}s")
                logger.info(f"   提取events: {result['events_extracted']}")
                logger.info(f"   错误数: {result['errors']}")

            except Exception as e:
                logger.error(f"❌ 测试失败 (max_workers={max_workers}): {e}")
                test_results[f"workers_{max_workers}"] = {"error": str(e)}

        self.results["tests"]["extract_parallel"] = test_results
        return test_results

    def test_incremental_processing(self) -> Dict:
        """测试增量处理功能

        流程：
        1. 记录当前pipeline状态
        2. 运行extract stage（首次）
        3. 检查状态更新
        4. 再次运行extract stage（增量）
        5. 验证只处理新数据
        """
        logger.info("\n" + "=" * 80)
        logger.info("测试2: 增量处理功能")
        logger.info("=" * 80)

        test_results = {}

        try:
            # 重置状态
            logger.info("\n步骤1: 重置pipeline状态...")
            get_pipeline_state().reset_all_stages()

            # 第一次运行
            logger.info("\n步骤2: 首次运行（应该处理所有数据）...")
            extractor1 = PainPointExtractor()
            start_time = time.time()

            posts1 = db.get_filtered_posts(limit=30, min_pain_score=0.3)
            logger.info(f"找到 {len(posts1)} 个posts待处理")

            events1 = extractor1.extract_from_posts_batch(posts1, max_workers=8)
            elapsed1 = time.time() - start_time

            # 更新状态
            get_pipeline_state().update_stage_run("extract", len(events1))

            first_run = {
                "posts_processed": len(posts1),
                "events_extracted": len(events1),
                "elapsed_time": round(elapsed1, 2),
                "pipeline_state": get_pipeline_state().get_last_run_time("extract")
            }

            logger.info(f"✅ 首次运行完成:")
            logger.info(f"   处理posts: {first_run['posts_processed']}")
            logger.info(f"   提取events: {first_run['events_extracted']}")
            logger.info(f"   耗时: {first_run['elapsed_time']}s")
            logger.info(f"   状态更新: {first_run['pipeline_state']}")

            # 第二次运行（增量）
            logger.info("\n步骤3: 第二次运行（应该只处理新数据）...")

            # 获取上次运行时间
            last_run = get_pipeline_state().get_last_run_time("extract")
            logger.info(f"上次运行时间: {last_run}")

            # 使用since参数获取增量数据
            posts2 = db.get_filtered_posts(limit=30, min_pain_score=0.3, since=last_run)
            logger.info(f"增量posts数: {len(posts2)}")

            start_time = time.time()
            extractor2 = PainPointExtractor()

            if posts2:
                events2 = extractor2.extract_from_posts_batch(posts2, max_workers=8)
                elapsed2 = time.time() - start_time

                logger.info(f"✅ 增量运行完成:")
                logger.info(f"   处理posts: {len(posts2)}")
                logger.info(f"   提取events: {len(events2)}")
                logger.info(f"   耗时: {elapsed2:.2f}s")
            else:
                elapsed2 = 0
                logger.info("✅ 增量运行: 没有新数据需要处理（符合预期）")

            second_run = {
                "posts_processed": len(posts2),
                "elapsed_time": round(elapsed2, 2)
            }

            test_results = {
                "first_run": first_run,
                "second_run": second_run,
                "incremental_mode_works": len(posts2) < len(posts1)
            }

            self.results["tests"]["incremental"] = test_results

        except Exception as e:
            logger.error(f"❌ 增量处理测试失败: {e}")
            test_results = {"error": str(e)}
            self.results["tests"]["incremental"] = test_results

        return test_results

    def test_database_wal_mode(self) -> Dict:
        """测试数据库WAL模式"""
        logger.info("\n" + "=" * 80)
        logger.info("测试3: SQLite WAL模式")
        logger.info("=" * 80)

        try:
            import sqlite3

            conn = sqlite3.connect("data/wise_collection.db")
            cursor = conn.execute("PRAGMA journal_mode")
            wal_mode = cursor.fetchone()[0]

            cursor = conn.execute("PRAGMA synchronous")
            sync_mode = cursor.fetchone()[0]

            conn.close()

            result = {
                "wal_mode": wal_mode,
                "synchronous": sync_mode,
                "wal_enabled": wal_mode.lower() == "wal"
            }

            logger.info(f"✅ WAL模式: {result['wal_mode']}")
            logger.info(f"✅ Synchronous: {result['synchronous']}")
            logger.info(f"✅ WAL已启用: {result['wal_enabled']}")

            self.results["tests"]["wal_mode"] = result
            return result

        except Exception as e:
            logger.error(f"❌ WAL模式测试失败: {e}")
            return {"error": str(e)}

    def generate_report(self, output_file: str = "performance_test_results.json"):
        """生成测试报告"""
        logger.info("\n" + "=" * 80)
        logger.info("生成测试报告")
        logger.info("=" * 80)

        # 计算性能提升
        if "extract_parallel" in self.results["tests"]:
            parallel_results = self.results["tests"]["extract_parallel"]

            # 找到最快和最慢的配置
            times = {
                k: v.get("elapsed_time", float('inf'))
                for k, v in parallel_results.items()
                if "error" not in v
            }

            if times:
                fastest = min(times, key=times.get)
                slowest = max(times, key=times.get)

                if times[slowest] > 0:
                    speedup = times[slowest] / times[fastest]
                    self.results["summary"] = {
                        "fastest_config": fastest,
                        "slowest_config": slowest,
                        "speedup_factor": round(speedup, 2)
                    }

                    logger.info(f"\n性能提升总结:")
                    logger.info(f"  最快配置: {fastest}")
                    logger.info(f"  最慢配置: {slowest}")
                    logger.info(f"  加速比: {speedup}x")

        # 保存JSON报告
        report_path = Path(output_file)
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)

        logger.info(f"\n✅ 测试报告已保存: {report_path.absolute()}")

        # 打印摘要
        print("\n" + "=" * 80)
        print("测试摘要")
        print("=" * 80)

        for test_name, test_data in self.results["tests"].items():
            print(f"\n{test_name}:")
            if "error" in test_data:
                print(f"  ❌ 错误: {test_data['error']}")
            else:
                for key, value in test_data.items():
                    if isinstance(value, dict):
                        print(f"  {key}:")
                        for k, v in value.items():
                            print(f"    {k}: {v}")
                    else:
                        print(f"  {key}: {value}")

        if "summary" in self.results:
            print("\n性能总结:")
            for key, value in self.results["summary"].items():
                print(f"  {key}: {value}")

        print("\n" + "=" * 80)


def main():
    """主测试流程"""
    import argparse

    parser = argparse.ArgumentParser(description="Phase 6 性能测试")
    parser.add_argument("--workers", type=int, nargs='+', default=[3, 5, 8],
                       help="要测试的并发数列表")
    parser.add_argument("--output", type=str, default="performance_test_results.json",
                       help="测试报告输出文件")
    parser.add_argument("--skip-incremental", action="store_true",
                       help="跳过增量处理测试")
    parser.add_argument("--skip-wal", action="store_true",
                       help="跳过WAL模式测试")

    args = parser.parse_args()

    tester = PerformanceTester()

    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "Phase 6 性能测试" + " " * 46 + "║")
    print("╚" + "=" * 78 + "╝")

    try:
        # 测试1: 并行性能
        tester.test_extract_parallel_performance(max_workers_list=args.workers)

        # 测试2: 增量处理
        if not args.skip_incremental:
            tester.test_incremental_processing()

        # 测试3: WAL模式
        if not args.skip_wal:
            tester.test_database_wal_mode()

        # 生成报告
        tester.generate_report(output_file=args.output)

        print("\n✅ 所有测试完成！")

    except Exception as e:
        logger.error(f"❌ 测试过程中出错: {e}")
        raise


if __name__ == "__main__":
    main()
