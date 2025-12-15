#!/usr/bin/env python3
"""
测试过滤规则功能
"""
import sys
import logging
from pathlib import Path

# 添加模块路径
sys.path.append(str(Path(__file__).parent))

from pipeline.score_viability import ViabilityScorer
from utils.db import db
import json

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_filtering_rules():
    """测试过滤规则功能"""
    print("🧪 测试过滤规则功能...")

    try:
        # 初始化评分器
        scorer = ViabilityScorer()

        # 检查过滤规则是否启用
        if not scorer.filtering_rules.get("enabled", False):
            print("❌ 过滤规则未启用，请检查配置文件")
            return False

        print(f"✅ 过滤规则已启用")
        print(f"   - 最小聚类大小: {scorer.filtering_rules.get('min_cluster_size')}")
        print(f"   - 最小独立作者: {scorer.filtering_rules.get('min_unique_authors')}")
        print(f"   - 最小子版块数: {scorer.filtering_rules.get('min_cross_subreddit_count')}")
        print(f"   - 最小频率评分: {scorer.filtering_rules.get('min_avg_frequency_score')}")

        # 获取一些聚类进行测试
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("""
                SELECT c.*, COUNT(o.id) as opportunity_count
                FROM clusters c
                LEFT JOIN opportunities o ON c.id = o.cluster_id
                GROUP BY c.id
                ORDER BY c.id
                LIMIT 10
            """)
            clusters = [dict(row) for row in cursor.fetchall()]

        if not clusters:
            print("❌ 没有找到聚类数据")
            return False

        print(f"\n📊 找到 {len(clusters)} 个聚类进行测试")

        # 测试每个聚类
        passed_count = 0
        skipped_count = 0

        for i, cluster in enumerate(clusters, 1):
            print(f"\n[{i}/{len(clusters)}] 测试聚类: {cluster['cluster_name'][:50]}...")
            print(f"   聚类大小: {cluster['cluster_size']}")
            print(f"   机会数量: {cluster['opportunity_count']}")

            # 应用过滤规则
            should_skip, skip_reason = scorer.should_skip_solution_design(cluster)

            if should_skip:
                print(f"   ❌ 跳过: {skip_reason}")
                skipped_count += 1
            else:
                print(f"   ✅ 通过")
                passed_count += 1

            # 计算并显示详细指标
            pain_event_ids = json.loads(cluster.get("pain_event_ids", "[]"))
            if pain_event_ids:
                unique_authors = scorer._calculate_unique_authors(pain_event_ids)
                cross_subreddits = scorer._calculate_cross_subreddit_count(pain_event_ids)
                avg_frequency = scorer._calculate_avg_frequency_score(pain_event_ids)

                print(f"   📈 详细指标:")
                print(f"      - 独立作者: {unique_authors}")
                print(f"      - 子版块数: {cross_subreddits}")
                print(f"      - 频率评分: {avg_frequency:.1f}")

        print(f"\n📋 测试总结:")
        print(f"   - 总聚类数: {len(clusters)}")
        print(f"   - 通过过滤: {passed_count}")
        print(f"   - 被跳过: {skipped_count}")
        print(f"   - 跳过率: {skipped_count/len(clusters)*100:.1f}%")

        # 测试频率评分映射
        print(f"\n🎯 测试频率评分映射:")
        test_frequencies = [
            ["daily", "weekly", "monthly"],
            ["sometimes", "often", "rarely"],
            ["每天", "每周", "很少"],
            ["", "unknown", "invalid"]
        ]

        for freq_list in test_frequencies:
            score = scorer._frequency_to_score(freq_list)
            print(f"   {freq_list} -> {score:.1f}")

        return True

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_loading():
    """测试配置加载"""
    print("\n🔧 测试配置加载...")

    try:
        scorer = ViabilityScorer()

        # 检查配置是否正确加载
        print(f"✅ 配置加载成功")
        print(f"   过滤规则: {scorer.filtering_rules}")

        # 检查频率映射
        freq_mapping = scorer.filtering_rules.get("frequency_score_mapping", {})
        if freq_mapping:
            print(f"✅ 频率映射配置: {len(freq_mapping)} 个映射")
        else:
            print("⚠️ 频率映射配置为空")

        return True

    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return False

def main():
    """主函数"""
    print("🚀 开始测试过滤规则功能\n")

    success = True

    # 测试配置加载
    success &= test_config_loading()

    # 测试过滤规则
    success &= test_filtering_rules()

    if success:
        print("\n✅ 所有测试通过！")
        print("\n💡 使用建议:")
        print("   1. 运行 python pipeline/score_viability.py --limit 50 来应用过滤规则")
        print("   2. 检查日志中的跳过原因来调整阈值")
        print("   3. 可以通过修改 config/thresholds.yaml 来调整过滤规则")
    else:
        print("\n❌ 测试失败，请检查错误信息")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())