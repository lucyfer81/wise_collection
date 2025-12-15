#!/usr/bin/env python3
"""
Quick Start Script for Reddit Pain Point Finder
快速启动脚本 - 一键运行简化版pipeline
"""
import os
import sys
import logging

# 设置项目根目录
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def quick_test():
    """快速测试系统是否准备就绪"""
    print("🧪 Quick System Test")
    print("=" * 40)

    # 检查环境变量
    required_vars = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "Siliconflow_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        print("\nPlease set these variables in your .env file:")
        for var in missing:
            print(f"   {var}=your_{var.lower()}_here")
        return False

    print("✅ Environment variables OK")

    # 检查配置文件
    config_files = ["config/subreddits.yaml", "config/llm.yaml", "config/thresholds.yaml"]
    for config_file in config_files:
        if os.path.exists(config_file):
            print(f"✅ {config_file} exists")
        else:
            print(f"❌ {config_file} missing")
            return False

    # 测试导入
    try:
        from utils.db import db
        from utils.llm_client import llm_client
        print("✅ Core modules import OK")
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

    return True

def mini_pipeline():
    """运行mini pipeline测试"""
    print("\n🚀 Running Mini Pipeline")
    print("=" * 40)

    try:
        # 1. 抓取少量数据
        print("\n📥 Step 1: Fetching data...")
        from pipeline.fetch import RedditPainFetcher
        fetcher = RedditPainFetcher()
        result = fetcher.fetch_all(limit_subreddits=2)
        print(f"   Fetched {result.get('total_saved', 0)} posts")

        # 2. 过滤信号
        print("\n🔍 Step 2: Filtering signals...")
        from pipeline.filter_signal import PainSignalFilter
        from utils.db import db

        unfiltered = db.get_unprocessed_posts(limit=20)
        filter_obj = PainSignalFilter()
        filtered = filter_obj.filter_posts_batch(unfiltered)

        # 保存过滤结果
        saved = 0
        for post in filtered:
            if db.insert_filtered_post(post):
                saved += 1

        print(f"   Filtered {saved} posts with pain signals")

        # 3. 显示统计
        print("\n📊 Mini Pipeline Results:")
        stats = db.get_statistics()
        print(f"   Raw posts: {stats.get('raw_posts_count', 0)}")
        print(f"   Filtered posts: {stats.get('filtered_posts_count', 0)}")
        print(f"   Pain events: {stats.get('pain_events_count', 0)}")

        if saved > 0:
            print("\n🎉 Mini pipeline completed successfully!")
            print("💡 You can now run the full pipeline with:")
            print("   python run_pipeline.py --stage all")
        else:
            print("\n⚠️  No pain signals found. Try running with more subreddits.")
            print("   python run_pipeline.py --stage fetch --limit-subreddits 10")

        return True

    except Exception as e:
        print(f"\n❌ Mini pipeline failed: {e}")
        print("💡 Check the logs for detailed error information")
        return False

def show_next_steps():
    """显示后续步骤"""
    print("\n" + "=" * 50)
    print("🎯 NEXT STEPS")
    print("=" * 50)

    print("\n1. Run the full pipeline:")
    print("   python run_pipeline.py --stage all")

    print("\n2. Or run specific stages:")
    print("   python run_pipeline.py --stage fetch      # Fetch more data")
    print("   python run_pipeline.py --stage extract    # Extract pain points")
    print("   python run_pipeline.py --stage cluster    # Cluster pain events")
    print("   python run_pipeline.py --stage map        # Map opportunities")

    print("\n3. View results:")
    print("   python -c \"from utils.db import db; print(db.get_statistics())\"")

    print("\n4. Save results:")
    print("   python run_pipeline.py --stage all --save-results")

    print("\n5. Get help:")
    print("   python run_pipeline.py --help")

def main():
    """主函数"""
    print("🔥 Reddit Pain Point Finder - Quick Start")
    print("=" * 50)

    # 快速测试
    if not quick_test():
        print("\n❌ System not ready. Please fix the issues above.")
        sys.exit(1)

    # 运行mini pipeline
    if mini_pipeline():
        show_next_steps()
    else:
        print("\n💡 Try running the test suite for detailed diagnostics:")
        print("   python test_pipeline.py")

if __name__ == "__main__":
    main()