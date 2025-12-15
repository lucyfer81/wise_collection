#!/usr/bin/env python3
"""重新生成报告，使用基础分析替代失败的LLM调用"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pain_point_analyzer import PainPointAnalyzer

# 创建分析器
analyzer = PainPointAnalyzer()

# 获取前3个聚类进行测试
clusters = analyzer.get_top_clusters(min_score=0.8, limit=3)

print(f"找到 {len(clusters)} 个聚类")

for i, cluster in enumerate(clusters[:1], 1):  # 只处理第一个
    print(f"\n[{i}] 处理聚类: {cluster['name'][:50]}...")

    # 使用基础分析
    analysis = analyzer.generate_basic_analysis(cluster)

    # 生成报告
    report_path = analyzer.generate_cluster_report(cluster, analysis)

    if report_path:
        print(f"✅ 报告已更新: {report_path}")

        # 显示部分内容
        print("\n--- 分析内容预览 ---")
        print(analysis[:500] + "...")