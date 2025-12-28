#!/usr/bin/env python3
"""
Quality Validation Script for Filtered Comments
验证过滤评论的质量
"""
import sqlite3
import json
import random
from pathlib import Path

DB_PATH = "data/wise_collection.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 获取统计信息
    print("=" * 80)
    print("PHASE 1: INCLUDE COMMENTS - QUALITY VALIDATION REPORT")
    print("=" * 80)
    print()

    # 1. 总体统计
    cursor.execute("SELECT COUNT(*) FROM filtered_comments")
    total = cursor.fetchone()[0]
    print(f"Total Filtered Comments: {total}")
    print()

    # 2. Pain score分布
    cursor.execute("""
        SELECT
            MIN(pain_score) as min_score,
            MAX(pain_score) as max_score,
            AVG(pain_score) as avg_score,
            MEDIAN(pain_score) as median_score
        FROM filtered_comments
    """)
    stats = cursor.fetchone()
    print(f"Pain Score Distribution:")
    print(f"  - Min:    {stats['min_score']:.2f}")
    print(f"  - Max:    {stats['max_score']:.2f}")
    print(f"  - Average: {stats['avg_score']:.2f}")
    print()

    # 3. Score分布
    cursor.execute("""
        SELECT
            MIN(score) as min_score,
            MAX(score) as max_score,
            AVG(score) as avg_score
        FROM filtered_comments
    """)
    score_stats = cursor.fetchone()
    print(f"Comment Score (Upvotes) Distribution:")
    print(f"  - Min:    {score_stats['min_score']}")
    print(f"  - Max:    {score_stats['max_score']}")
    print(f"  - Average: {score_stats['avg_score']:.1f}")
    print()

    # 4. Top keywords
    cursor.execute("""
        SELECT pain_keywords
        FROM filtered_comments
        WHERE pain_keywords IS NOT NULL AND pain_keywords != ''
        LIMIT 1000
    """)
    keyword_freq = {}
    for row in cursor.fetchall():
        try:
            keywords = json.loads(row['pain_keywords'])
            for kw in keywords:
                if ':' in kw:
                    category = kw.split(':')[0]
                    keyword_freq[category] = keyword_freq.get(category, 0) + 1
        except:
            pass

    print("Top Pain Keyword Categories:")
    sorted_cats = sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    for cat, count in sorted_cats:
        print(f"  - {cat}: {count}")
    print()

    # 5. 随机样本（手动审查用）
    print("=" * 80)
    print("RANDOM SAMPLE FOR MANUAL QUALITY REVIEW")
    print("=" * 80)
    print()

    cursor.execute("""
        SELECT
            fc.comment_id,
            fc.score as upvotes,
            ROUND(fc.pain_score, 2) as pain_score,
            substr(fc.body, 1, 200) as body_preview,
            fc.pain_keywords
        FROM filtered_comments fc
        ORDER BY RANDOM()
        LIMIT 10
    """)

    samples = cursor.fetchall()
    for i, sample in enumerate(samples, 1):
        print(f"{i}. Comment ID: {sample['comment_id']}")
        print(f"   Upvotes: {sample['upvotes']} | Pain Score: {sample['pain_score']}")
        print(f"   Body: {sample['body_preview']}...")

        # 显示前3个关键词
        try:
            keywords = json.loads(sample['pain_keywords'])
            if keywords:
                print(f"   Keywords: {', '.join(keywords[:3])}")
        except:
            pass
        print()

    # 6. 质量指标
    print("=" * 80)
    print("QUALITY METRICS")
    print("=" * 80)
    print()

    # 检查是否有明显误判（例如过短的评论）
    cursor.execute("""
        SELECT COUNT(*) FROM filtered_comments
        WHERE LENGTH(body) < 30
    """)
    too_short = cursor.fetchone()[0]
    print(f"Potentially Low Quality (body < 30 chars): {too_short} ({too_short/total*100:.1f}%)")

    # 检查是否有高质量评论（pain_score > 0.6）
    cursor.execute("""
        SELECT COUNT(*) FROM filtered_comments
        WHERE pain_score > 0.6
    """)
    high_quality = cursor.fetchone()[0]
    print(f"High Quality (pain_score > 0.6): {high_quality} ({high_quality/total*100:.1f}%)")

    # 检查高分评论
    cursor.execute("""
        SELECT COUNT(*) FROM filtered_comments
        WHERE score >= 100
    """)
    high_upvotes = cursor.fetchone()[0]
    print(f"High Upvotes (score >= 100): {high_upvotes} ({high_upvotes/total*100:.1f}%)")
    print()

    print("=" * 80)
    print("VALIDATION COMPLETE")
    print("=" * 80)

    conn.close()

if __name__ == "__main__":
    main()
