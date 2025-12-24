#!/usr/bin/env python3
"""
Validation script for Phase 2: Trust-Aware Filtering & Aspiration Signals
验证脚本 - 检查Phase 2升级是否成功
"""
import sys
import yaml
import sqlite3
from pathlib import Path

def check_config_changes():
    """检查配置文件修改"""
    print("=== Checking Configuration Changes ===")

    config_path = Path("config/subreddits.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Check 1: Ignore list should NOT contain programming subreddits
    ignore_list = config.get("ignore", [])
    removed_subs = ["programming", "learnprogramming", "ChatGPT", "OpenAI"]
    still_ignored = [sub for sub in removed_subs if sub in ignore_list]

    if still_ignored:
        print(f"❌ FAIL: Subreddits still in ignore list: {still_ignored}")
        return False
    else:
        print(f"✅ PASS: Programming subreddits removed from ignore list")

    # Check 2: noisy_tech category should exist
    if "noisy_tech" not in config:
        print("❌ FAIL: noisy_tech category not found")
        return False
    print("✅ PASS: noisy_tech category exists")

    # Check 3: noisy_tech should have trust_level 0.4
    noisy_tech = config["noisy_tech"]
    if noisy_tech.get("trust_level") != 0.4:
        print(f"❌ FAIL: noisy_tech trust_level is {noisy_tech.get('trust_level')}, expected 0.4")
        return False
    print("✅ PASS: noisy_tech has trust_level 0.4")

    # Check 4: aspiration_keywords should exist
    if "aspiration_keywords" not in config:
        print("❌ FAIL: aspiration_keywords not found")
        return False
    print("✅ PASS: aspiration_keywords exists")

    # Check 5: Exclude patterns should be relaxed
    exclude_patterns = config.get("exclude_patterns", {})
    question_patterns = exclude_patterns.get("question", [])
    off_topic_patterns = exclude_patterns.get("off_topic", [])

    forbidden_question = ["how do i", "what is the best"]
    forbidden_off_topic = ["discussion"]

    found_forbidden = []
    for pattern in forbidden_question:
        if pattern in question_patterns:
            found_forbidden.append(f"question:{pattern}")

    for pattern in forbidden_off_topic:
        if pattern in off_topic_patterns:
            found_forbidden.append(f"off_topic:{pattern}")

    if found_forbidden:
        print(f"❌ FAIL: Forbidden patterns still in exclude list: {found_forbidden}")
        return False
    print("✅ PASS: Exclude patterns relaxed correctly")

    return True

def check_database_state(db_path="data/wise_collection.db"):
    """检查数据库状态（需要先运行pipeline）"""
    print("\n=== Checking Database State ===")

    if not Path(db_path).exists():
        print(f"⚠️  SKIP: Database not found at {db_path}")
        print("   Run the pipeline first: python -m pipeline.fetch && python -m pipeline.filter_signal")
        return True

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check 1: Posts table should have trust_level column
    cursor.execute("PRAGMA table_info(posts)")
    columns = {row["name"] for row in cursor.fetchall()}
    if "trust_level" not in columns:
        print("❌ FAIL: posts table missing trust_level column")
        return False
    print("✅ PASS: posts table has trust_level column")

    # Check 2: Check if posts from new subreddits exist
    new_subreddits = ["programming", "learnprogramming", "ChatGPT", "OpenAI"]
    placeholders = ",".join("?" * len(new_subreddits))
    cursor.execute(f"SELECT COUNT(*) as count FROM posts WHERE subreddit IN ({placeholders})", new_subreddits)
    count = cursor.fetchone()["count"]

    if count > 0:
        print(f"✅ PASS: Found {count} posts from newly added subreddits")
    else:
        print(f"⚠️  INFO: No posts from new subreddits yet (run fetch first)")

    # Check 3: Check for aspiration-based filtered posts
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM filtered_posts
        WHERE filter_reason LIKE '%aspiration%'
    """)
    aspiration_count = cursor.fetchone()["count"]

    # Note: This requires schema update to filter_reason or new column
    print(f"ℹ️  INFO: Aspiration-based filtering count: {aspiration_count}")

    # Check 4: Trust level distribution
    cursor.execute("""
        SELECT trust_level, COUNT(*) as count
        FROM posts
        WHERE trust_level IS NOT NULL
        GROUP BY trust_level
        ORDER BY trust_level
    """)
    print("\n   Trust level distribution:")
    for row in cursor.fetchall():
        print(f"     {row['trust_level']}: {row['count']} posts")

    conn.close()
    return True

def main():
    """主函数"""
    print("Phase 2 Validation Script")
    print("=" * 50)

    config_ok = check_config_changes()
    db_ok = check_database_state()

    print("\n" + "=" * 50)
    if config_ok and db_ok:
        print("✅ VALIDATION PASSED")
        return 0
    else:
        print("❌ VALIDATION FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
