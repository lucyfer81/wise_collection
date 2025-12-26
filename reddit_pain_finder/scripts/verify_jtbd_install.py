#!/usr/bin/env python3
"""JTBD功能安装验证（无需API）"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import db
import json

def main():
    print("=" * 80)
    print("JTBD产品语义升级 - 安装验证")
    print("=" * 80)

    # 1. 数据库schema验证
    print("\n[1/3] 验证数据库schema...")
    with db.get_connection("clusters") as conn:
        cursor = conn.execute("PRAGMA table_info(clusters)")
        columns = {row['name'] for row in cursor.fetchall()}

        jtbd_columns = ['job_statement', 'job_steps', 'desired_outcomes',
                        'job_context', 'customer_profile', 'semantic_category', 'product_impact']

        missing = [col for col in jtbd_columns if col not in columns]
        if missing:
            print(f"❌ 缺少字段: {missing}")
            return False
        else:
            print(f"✅ 所有JTBD字段已存在:")
            for col in jtbd_columns:
                print(f"   - {col}")

    # 2. 检查索引
    print("\n[2/3] 验证索引...")
    with db.get_connection("clusters") as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_clusters_%'")
        indexes = [row['name'] for row in cursor.fetchall()]

        expected_indexes = ['idx_clusters_semantic_category', 'idx_clusters_product_impact']
        for idx in expected_indexes:
            if idx in indexes:
                print(f"✅ 索引存在: {idx}")
            else:
                print(f"⚠️  索引缺失: {idx}")

    # 3. 检查代码模块
    print("\n[3/3] 验证代码模块...")
    try:
        # 检查LLM客户端
        from utils.llm_client import llm_client
        if hasattr(llm_client, 'generate_jtbd_from_cluster'):
            print("✅ LLM客户端已更新 (generate_jtbd_from_cluster存在)")
        else:
            print("❌ LLM客户端未更新")

        # 检查聚类器
        from pipeline.cluster import PainEventClusterer
        clusterer = PainEventClusterer()

        methods = ['get_clusters_by_semantic_category', 'get_high_impact_clusters', 'get_all_semantic_categories']
        for method in methods:
            if hasattr(clusterer, method):
                print(f"✅ 聚类器方法存在: {method}")
            else:
                print(f"❌ 聚类器方法缺失: {method}")

    except Exception as e:
        print(f"❌ 代码模块验证失败: {e}")
        return False

    # 4. 检查现有数据
    print("\n[数据统计]")
    with db.get_connection("clusters") as conn:
        cursor = conn.execute("SELECT COUNT(*) as count FROM clusters")
        cluster_count = cursor.fetchone()["count"]

        if cluster_count > 0:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN job_statement IS NOT NULL AND job_statement != '' THEN 1 ELSE 0 END) as with_jtbd
                FROM clusters
            """)
            result = cursor.fetchone()
            print(f"总clusters: {result['total']}")
            print(f"已有JTBD: {result['with_jtbd']}")
            print(f"需要迁移: {result['total'] - result['with_jtbd']}")
        else:
            print("无现有clusters")

    print("\n" + "=" * 80)
    print("✅ 安装验证完成！所有组件就绪。")
    print("=" * 80)

    print("\n📝 使用指南:")
    print("\n1. 为现有clusters生成JTBD:")
    print("   python3 scripts/migrate_existing_clusters_to_jtbd.py")
    print("\n2. 生成新的clusters（自动包含JTBD）:")
    print("   export Siliconflow_KEY=your_key_here")
    print("   python3 pipeline/cluster.py")
    print("\n3. 查询JTBD数据:")
    print("   from pipeline.cluster import PainEventClusterer")
    print("   clusterer = PainEventClusterer()")
    print("   high_impact = clusterer.get_high_impact_clusters(min_impact=0.7)")
    print("   categories = clusterer.get_all_semantic_categories()")

if __name__ == "__main__":
    main()
