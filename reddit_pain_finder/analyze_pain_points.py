#!/usr/bin/env python3
"""
快速启动痛点分析脚本
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pain_point_analyzer import PainPointAnalyzer

if __name__ == "__main__":
    print("🎯 Reddit Pain Point Finder - 痛点机会分析器")
    print("=" * 60)

    # 可以通过命令行参数调整
    min_score = 0.8
    limit = 15

    if len(sys.argv) > 1:
        try:
            min_score = float(sys.argv[1])
        except:
            pass

    if len(sys.argv) > 2:
        try:
            limit = int(sys.argv[2])
        except:
            pass

    print(f"参数设置:")
    print(f"  • 最低机会评分: {min_score}")
    print(f"  • 最大分析数量: {limit}")
    print()

    try:
        analyzer = PainPointAnalyzer()
        analyzer.run_analysis(min_score=min_score, limit=limit)
    except KeyboardInterrupt:
        print("\n\n⚠️  分析被用户中断")
    except Exception as e:
        print(f"\n❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()