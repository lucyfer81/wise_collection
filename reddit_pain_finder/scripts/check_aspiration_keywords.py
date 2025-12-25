#!/usr/bin/env python3
"""
检查现有数据中是否包含愿望关键词
Check if existing posts contain aspiration keywords
"""
import sys
import yaml
import sqlite3
import json
from pathlib import Path

def load_aspiration_keywords():
    """加载愿望关键词配置"""
    config_path = Path("config/subreddits.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config.get("aspiration_keywords", {})

def check_text_for_aspirations(text, aspiration_keywords):
    """检查文本是否包含愿望关键词"""
    if not text:
        return []

    text_lower = text.lower()
    matched = []

    for category, keywords in aspiration_keywords.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                matched.append({
                    "category": category,
                    "keyword": keyword
                })

    return matched

def main():
    """主函数"""
    print("=== Aspiration Keywords Checker ===\n")

    # 加载愿望关键词
    aspiration_keywords = load_aspiration_keywords()
    total_keywords = sum(len(kws) for kws in aspiration_keywords.values())

    print(f"Loaded {len(aspiration_keywords)} categories with {total_keywords} keywords:")
    for category, keywords in aspiration_keywords.items():
        print(f"  - {category}: {len(keywords)} keywords")
    print()

    # 连接数据库
    db_path = "data/wise_collection.db"
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 检查 posts 表
    print("=== Checking posts table ===")
    cursor.execute("""
        SELECT id, title, body, subreddit, score, num_comments
        FROM posts
        ORDER BY collected_at DESC
        LIMIT 500
    """)
    posts = cursor.fetchall()
    print(f"Total posts to check: {len(posts)}")

    posts_with_aspirations = 0
    total_matches = 0

    for post in posts:
        title = post["title"] if post["title"] else ""
        body = post["body"] if post["body"] else ""
        full_text = f"{title} {body}"

        matches = check_text_for_aspirations(full_text, aspiration_keywords)

        if matches:
            posts_with_aspirations += 1
            total_matches += len(matches)

            print(f"\n📌 Post found in r/{post['subreddit']} (ID: {post['id']})")
            print(f"   Score: {post['score']} | Comments: {post['num_comments']}")
            print(f"   Title: {title[:100]}...")
            print(f"   Matched keywords: {len(matches)}")
            for match in matches[:3]:  # Show first 3 matches
                print(f"     - [{match['category']}] {match['keyword']}")
            if len(matches) > 3:
                print(f"     ... and {len(matches) - 3} more")

    print(f"\n=== Summary ===")
    print(f"Posts with aspiration keywords: {posts_with_aspirations} / {len(posts)} ({posts_with_aspirations/len(posts)*100:.1f}%)")
    print(f"Total keyword matches: {total_matches}")

    # 检查 filtered_posts 表
    print("\n=== Checking filtered_posts table ===")
    cursor.execute("""
        SELECT id, title, body, subreddit, pass_type, aspiration_score
        FROM filtered_posts
        ORDER BY filtered_at DESC
        LIMIT 500
    """)
    filtered_posts = cursor.fetchall()
    print(f"Total filtered posts: {len(filtered_posts)}")

    # 按 pass_type 分组统计
    cursor.execute("""
        SELECT pass_type, COUNT(*) as count
        FROM filtered_posts
        GROUP BY pass_type
    """)
    print("\nPass type distribution:")
    for row in cursor.fetchall():
        print(f"  - {row['pass_type']}: {row['count']} posts")

    # 检查 aspiration_score 分布
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            AVG(aspiration_score) as avg_score,
            MAX(aspiration_score) as max_score
        FROM filtered_posts
        WHERE aspiration_score > 0
    """)
    row = cursor.fetchone()
    if row and row['total'] > 0:
        print(f"\nPosts with aspiration_score > 0:")
        print(f"  - Count: {row['total']}")
        print(f"  - Avg score: {row['avg_score']:.3f}")
        print(f"  - Max score: {row['max_score']:.3f}")
    else:
        print("\nNo posts with aspiration_score > 0")

    conn.close()

    return 0

if __name__ == "__main__":
    sys.exit(main())
