#!/bin/bash
# check_pipeline_health.sh - 检查pipeline状态

echo "=== Pipeline Health Check - $(date) ==="

python3 << 'EOF'
from utils.db import db
import json
from datetime import datetime

# 获取统计信息
stats = db.get_statistics()

print("\n📊 Database Statistics:")
print(f"  Posts: {stats['raw_posts_count']}")
print(f"  Filtered posts: {stats['filtered_posts_count']}")
print(f"  Pain events: {stats['pain_events_count']}")
print(f"  Clusters: {stats['clusters_count']}")
print(f"  Opportunities: {stats['opportunities_count']}")

# 检查未处理的数据
import sqlite3
conn = sqlite3.connect('data/wise_collection.db')
conn.row_factory = sqlite3.Row

# Unprocessed posts
cursor = conn.execute("""
    SELECT COUNT(*) as count FROM posts
    WHERE NOT EXISTS (SELECT 1 FROM filtered_posts WHERE filtered_posts.id = posts.id)
""")
unprocessed_posts = cursor.fetchone()['count']

# Unextracted posts
cursor = conn.execute("""
    SELECT COUNT(*) as count FROM filtered_posts
    WHERE NOT EXISTS (SELECT 1 FROM pain_events WHERE pain_events.post_id = filtered_posts.id)
""")
unextracted_posts = cursor.fetchone()['count']

# Pain events without embeddings
cursor = conn.execute("""
    SELECT COUNT(*) as count FROM pain_events p
    WHERE NOT EXISTS (SELECT 1 FROM pain_embeddings e WHERE e.pain_event_id = p.id)
""")
no_embeddings = cursor.fetchone()['count']

# Clusters without opportunities
cursor = conn.execute("""
    SELECT COUNT(*) as count FROM clusters c
    WHERE NOT EXISTS (SELECT 1 FROM opportunities o WHERE o.cluster_id = c.id)
""")
no_opportunities = cursor.fetchone()['count']

print("\n⚠️  Unprocessed Data:")
print(f"  Unprocessed posts: {unprocessed_posts}")
print(f"  Unextracted posts: {unextracted_posts}")
print(f"  Pain events without embeddings: {no_embeddings}")
print(f"  Clusters without opportunities: {no_opportunities}")

# 健康评分
health_score = 100
issues = []

if unprocessed_posts > 100:
    health_score -= 10
    issues.append(f"Too many unprocessed posts ({unprocessed_posts})")
elif unprocessed_posts > 0:
    health_score -= 5
    issues.append(f"Some unprocessed posts ({unprocessed_posts})")

if unextracted_posts > 500:
    health_score -= 20
    issues.append(f"Too many unextracted posts ({unextracted_posts})")
elif unextracted_posts > 100:
    health_score -= 10
    issues.append(f"Many unextracted posts ({unextracted_posts})")

if no_embeddings > 1000:
    health_score -= 20
    issues.append(f"Too many pain events without embeddings ({no_embeddings})")
elif no_embeddings > 100:
    health_score -= 10
    issues.append(f"Many pain events without embeddings ({no_embeddings})")

if no_opportunities > 5:
    health_score -= 15
    issues.append(f"Too many clusters without opportunities ({no_opportunities})")
elif no_opportunities > 0:
    health_score -= 5
    issues.append(f"Some clusters without opportunities ({no_opportunities})")

print(f"\n🏥 Health Score: {health_score}/100")

if issues:
    print("\n⚠️  Issues Found:")
    for issue in issues:
        print(f"  - {issue}")
    print("\n💡 Recommendation: Run pipeline to process unprocessed data")
else:
    print("\n✅ All data processed!")

conn.close()
EOF

echo ""
echo "=== Health check complete ==="
