#!/usr/bin/env python3
"""
跨源对齐实现验证脚本
检查所有组件是否正确集成和配置
"""
import json
import sys
from utils.db import db

def check_database_schema():
    """检查数据库架构是否正确创建"""
    print("🔍 检查数据库架构...")

    with db.get_connection("raw") as conn:
        # 检查clusters表是否有对齐相关列
        cursor = conn.execute("PRAGMA table_info(clusters)")
        columns = {row['name'] for row in cursor.fetchall()}

        required_columns = ['alignment_status', 'aligned_problem_id']
        missing_columns = [col for col in required_columns if col not in columns]

        if missing_columns:
            print(f"❌ clusters表缺少列: {missing_columns}")
            return False
        else:
            print("✅ clusters表架构正确")

        # 检查aligned_problems表是否存在
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='aligned_problems'")
        aligned_problems_exists = cursor.fetchone() is not None

        if aligned_problems_exists:
            print("✅ aligned_problems表已创建")
        else:
            print("❌ aligned_problems表不存在")
            return False

        # 检查aligned_problems表结构
        cursor = conn.execute("PRAGMA table_info(aligned_problems)")
        aligned_columns = {row['name'] for row in cursor.fetchall()}

        required_aligned_columns = [
            'id', 'aligned_problem_id', 'sources', 'core_problem',
            'why_they_look_different', 'evidence', 'cluster_ids', 'created_at'
        ]
        missing_aligned_columns = [col for col in required_aligned_columns if col not in aligned_columns]

        if missing_aligned_columns:
            print(f"❌ aligned_problems表缺少列: {missing_aligned_columns}")
            return False
        else:
            print("✅ aligned_problems表架构正确")

        # 检查索引
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE '%alignment%'")
        alignment_indexes = [row['name'] for row in cursor.fetchall()]

        expected_indexes = ['idx_clusters_alignment_status', 'idx_clusters_aligned_problem_id']
        missing_indexes = [idx for idx in expected_indexes if idx not in alignment_indexes]

        if missing_indexes:
            print(f"⚠️  缺少索引: {missing_indexes}")
        else:
            print("✅ 对齐相关索引已创建")

    return True

def check_module_imports():
    """检查模块导入是否正常"""
    print("\n🔍 检查模块导入...")

    try:
        from pipeline.align_cross_sources import CrossSourceAligner
        print("✅ CrossSourceAligner导入成功")

        # 检查关键方法
        required_methods = [
            'get_unprocessed_clusters',
            'prepare_cluster_for_alignment',
            'align_clusters_across_sources',
            'process_alignments'
        ]

        for method in required_methods:
            if hasattr(CrossSourceAligner, method):
                print(f"✅ 方法 {method} 存在")
            else:
                print(f"❌ 方法 {method} 不存在")
                return False

    except ImportError as e:
        print(f"❌ CrossSourceAligner导入失败: {e}")
        return False

    return True

def check_database_methods():
    """检查数据库方法是否可用"""
    print("\n🔍 检查数据库方法...")

    try:
        required_methods = [
            'get_aligned_problems',
            'update_cluster_alignment_status',
            'insert_aligned_problem',
            'get_clusters_for_opportunity_mapping',
            'get_clusters_for_aligned_problem'
        ]

        for method in required_methods:
            if hasattr(db, method):
                print(f"✅ 数据库方法 {method} 存在")
            else:
                print(f"❌ 数据库方法 {method} 不存在")
                return False

        # 测试基本方法调用
        try:
            aligned_problems = db.get_aligned_problems()
            print(f"✅ get_aligned_problems调用成功，返回 {len(aligned_problems)} 个结果")
        except Exception as e:
            print(f"❌ get_aligned_problems调用失败: {e}")
            return False

    except Exception as e:
        print(f"❌ 数据库方法检查失败: {e}")
        return False

    return True

def check_data_compatibility():
    """检查数据兼容性"""
    print("\n🔍 检查数据兼容性...")

    try:
        # 检查聚类数据
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) as total_clusters,
                       COUNT(DISTINCT source_type) as distinct_sources,
                       COUNT(CASE WHEN alignment_status IS NULL THEN 1 END) as null_status_clusters
                FROM clusters
            """)

            result = cursor.fetchone()
            total_clusters = result['total_clusters']
            distinct_sources = result['distinct_sources']
            null_status_clusters = result['null_status_clusters']

            print(f"✅ 总聚类数: {total_clusters}")
            print(f"✅ 不同源类型: {distinct_sources}")
            print(f"✅ 需要状态更新的聚类: {null_status_clusters}")

            if total_clusters > 0:
                # 显示源类型分布
                cursor = conn.execute("""
                    SELECT source_type, COUNT(*) as count
                    FROM clusters
                    GROUP BY source_type
                """)

                print("📊 源类型分布:")
                for row in cursor.fetchall():
                    print(f"   {row['source_type']}: {row['count']} 个聚类")

                # 显示对齐状态分布
                cursor = conn.execute("""
                    SELECT
                        COALESCE(alignment_status, 'NULL') as status,
                        COUNT(*) as count
                    FROM clusters
                    GROUP BY alignment_status
                """)

                print("📊 对齐状态分布:")
                for row in cursor.fetchall():
                    print(f"   {row['status']}: {row['count']} 个聚类")

    except Exception as e:
        print(f"❌ 数据兼容性检查失败: {e}")
        return False

    return True

def check_llm_integration():
    """检查LLM集成"""
    print("\n🔍 检查LLM集成...")

    try:
        from utils.llm_client import LLMClient
        print("✅ LLMClient导入成功")

        # 检查配置文件
        try:
            llm_client = LLMClient('config/llm.yaml')
            print("✅ LLM配置加载成功")
        except Exception as e:
            print(f"⚠️  LLM配置加载失败（可能需要API密钥）: {e}")
            print("   这在测试环境中是正常的，实际使用时需要有效的API密钥")

    except ImportError as e:
        print(f"❌ LLMClient导入失败: {e}")
        return False

    return True

def generate_verification_report():
    """生成验证报告"""
    print("\n📋 生成验证报告...")

    results = {
        'database_schema': check_database_schema(),
        'module_imports': check_module_imports(),
        'database_methods': check_database_methods(),
        'data_compatibility': check_data_compatibility(),
        'llm_integration': check_llm_integration()
    }

    print("\n" + "="*60)
    print("📊 跨源对齐实现验证报告")
    print("="*60)

    passed = 0
    total = len(results)

    for check, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{check.replace('_', ' ').title()}: {status}")
        if result:
            passed += 1

    print(f"\n总体结果: {passed}/{total} 项检查通过")

    if passed == total:
        print("🎉 跨源对齐功能实现验证通过！")
        print("\n🚀 下一步:")
        print("   1. 配置有效的LLM API密钥")
        print("   2. 运行完整的数据管道: python run_pipeline.py")
        print("   3. 检查对齐结果: 从数据库查询 aligned_problems 表")
        return True
    else:
        print("❌ 存在问题需要修复")
        return False

if __name__ == "__main__":
    success = generate_verification_report()
    sys.exit(0 if success else 1)