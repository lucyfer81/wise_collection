#!/bin/bash
# Complete Pipeline Test Script
# 完整Pipeline测试脚本

set -e  # 遇到错误立即退出

echo "=================================================="
echo "  Reddit Pain Finder - Full Pipeline Test"
echo "=================================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 记录开始时间
START_TIME=$(date +%s)

# 1. 环境检查
echo -e "${YELLOW}[1/6] Environment Check${NC}"
echo "-------------------------------------------"

# 检查Python版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $PYTHON_VERSION"

# 检查必要的包
echo "Checking dependencies..."
python3 -c "import chromadb" 2>/dev/null && echo "✓ chromadb installed" || echo "✗ chromadb missing"
python3 -c "import yaml" 2>/dev/null && echo "✓ yaml installed" || echo "✗ yaml missing"

# 检查配置文件
if [ -f "config/llm.yaml" ]; then
    echo "✓ config/llm.yaml found"
else
    echo -e "${RED}✗ config/llm.yaml not found${NC}"
    exit 1
fi

# 检查数据库
if [ -f "data/wise_collection.db" ]; then
    DB_SIZE=$(du -h data/wise_collection.db | cut -f1)
    echo "✓ Database exists (size: $DB_SIZE)"
else
    echo "✗ Database not found, creating..."
    mkdir -p data
    touch data/wise_collection.db
fi

# 检查Chroma
if [ -d "data/chroma_db" ]; then
    CHROMA_SIZE=$(du -sh data/chroma_db 2>/dev/null | cut -f1)
    echo "✓ Chroma data exists (size: $CHROMA_SIZE)"
else
    echo "ℹ Chroma data not found, will be created on first run"
fi

echo ""
echo -e "${GREEN}Environment check passed!${NC}"
echo ""

# 2. 备份数据
echo -e "${YELLOW}[2/6] Backup Data${NC}"
echo "-------------------------------------------"

BACKUP_DIR="backups/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 备份数据库
if [ -f "data/wise_collection.db" ]; then
    cp data/wise_collection.db "$BACKUP_DIR/"
    echo "✓ Database backed up to: $BACKUP_DIR"
fi

# 备份Chroma (如果存在)
if [ -d "data/chroma_db" ]; then
    tar -czf "$BACKUP_DIR/chroma_db.tar.gz" -C data/ chroma_db
    echo "✓ Chroma backed up to: $BACKUP_DIR/chroma_db.tar.gz"
fi

echo ""
echo -e "${GREEN}Backup completed!${NC}"
echo ""

# 3. 显示当前状态
echo -e "${YELLOW}[3/6] Current State${NC}"
echo "-------------------------------------------"

echo "Database statistics:"
sqlite3 data/wise_collection.db <<EOF
SELECT
    'Raw posts: ' || COUNT(*) as stat FROM posts
UNION ALL
SELECT
    'Filtered posts: ' || COUNT(*) FROM filtered_posts
UNION ALL
SELECT
    'Pain events: ' || COUNT(*) FROM pain_events
UNION ALL
SELECT
    'Clusters: ' || COUNT(*) FROM clusters
UNION ALL
SELECT
    'Opportunities: ' || COUNT(*) FROM opportunities;
EOF

echo ""
echo "Lifecycle state:"
sqlite3 data/wise_collection.db <<EOF
SELECT
    'Active events: ' || COUNT(*) FILTER (WHERE lifecycle_stage = 'active') as stat FROM pain_events
UNION ALL
SELECT
    'Orphan events: ' || COUNT(*) FILTER (WHERE lifecycle_stage = 'orphan') FROM pain_events
UNION ALL
SELECT
    'Retention rate: ' || ROUND(COUNT(*) FILTER (WHERE lifecycle_stage = 'active') * 100.0 / COUNT(*), 1) || '%' FROM pain_events;
EOF

echo ""
echo -e "${GREEN}Current state displayed${NC}"
echo ""

# 4. 运行Pipeline
echo -e "${YELLOW}[4/6] Running Pipeline${NC}"
echo "-------------------------------------------"
echo "This will take approximately 1-2 hours..."
echo ""

# 运行完整pipeline
if [ "$1" = "--process-all" ]; then
    echo "Mode: Process all data (full pipeline)"
    python3 run_pipeline.py --stage all --process-all --save-results --enable-monitoring
elif [ "$1" = "--incremental" ]; then
    echo "Mode: Incremental (only new data)"
    python3 run_pipeline.py --stage all --save-results --enable-monitoring
else
    echo "Mode: Default limits (test run)"
    echo "Use --process-all for full processing or --incremental for incremental"
    python3 run_pipeline.py --stage all --save-results --enable-monitoring
fi

PIPELINE_EXIT_CODE=$?

echo ""

# 5. 显示结果
echo -e "${YELLOW}[5/6] Results${NC}"
echo "-------------------------------------------"

# 计算运行时间
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

echo "Pipeline execution time: ${MINUTES}m ${SECONDS}s"
echo ""

if [ $PIPELINE_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ Pipeline completed successfully!${NC}"
else
    echo -e "${RED}✗ Pipeline failed with exit code: $PIPELINE_EXIT_CODE${NC}"
    echo "Check logs/pipeline.log for details"
    exit 1
fi

echo ""
echo "Updated statistics:"
sqlite3 data/wise_collection.db <<EOF
SELECT
    'Raw posts: ' || COUNT(*) as stat FROM posts
UNION ALL
SELECT
    'Filtered posts: ' || COUNT(*) FROM filtered_posts
UNION ALL
SELECT
    'Pain events: ' || COUNT(*) FROM pain_events
UNION ALL
SELECT
    'Clusters: ' || COUNT(*) FROM clusters
UNION ALL
SELECT
    'Opportunities: ' || COUNT(*) FROM opportunities;
EOF

echo ""
echo "Lifecycle state after:"
sqlite3 data/wise_collection.db <<EOF
SELECT
    'Active events: ' || COUNT(*) FILTER (WHERE lifecycle_stage = 'active') as stat FROM pain_events
UNION ALL
SELECT
    'Orphan events: ' || COUNT(*) FILTER (WHERE lifecycle_stage = 'orphan') FROM pain_events
UNION ALL
SELECT
    'Retention rate: ' || ROUND(COUNT(*) FILTER (WHERE lifecycle_stage = 'active') * 100.0 / COUNT(*), 1) || '%' FROM pain_events;
EOF

echo ""

# 6. 验证和推荐
echo -e "${YELLOW}[6/6] Verification & Recommendations${NC}"
echo "-------------------------------------------"

# 检查最新结果文件
LATEST_RESULTS=$(ls -t pipeline_results_*.json 2>/dev/null | head -1)
if [ -n "$LATEST_RESULTS" ]; then
    echo "✓ Results saved to: $LATEST_RESULTS"

    # 显示关键指标
    echo ""
    echo "Key performance metrics:"
    python3 <<EOF
import json
import sys
try:
    with open("$LATEST_RESULTS", 'r') as f:
        results = json.load(f)

    stage_results = results.get('stage_results', {})

    # Fetch stage
    fetch = stage_results.get('fetch', {})
    if fetch:
        print(f"  Posts fetched: {fetch.get('total_saved', 0)}")

    # Filter stage
    filter = stage_results.get('filter', {})
    if filter:
        posts = filter.get('posts', {})
        print(f"  Posts filtered: {posts.get('filtered', 0)}/{posts.get('processed', 0)}")

    # Extract stage
    extract = stage_results.get('extract', {})
    if extract:
        print(f"  Pain events extracted: {extract.get('pain_events_saved', 0)}")

    # Cluster stage
    cluster = stage_results.get('cluster', {})
    if cluster:
        print(f"  Clusters created/updated: {cluster.get('clusters_created', 0)}/{cluster.get('clusters_updated', 0)}")

    # Score stage
    score = stage_results.get('score', {})
    if score:
        print(f"  Opportunities scored: {score.get('opportunities_scored', 0)}")

    # Decision stage
    decision = stage_results.get('shortlist', {})
    if decision:
        print(f"  Decision shortlist: {decision.get('shortlist_count', 0)} candidates")

except Exception as e:
    print(f"  Warning: Could not parse results: {e}")
EOF
fi

echo ""
echo "Top opportunities:"
sqlite3 data/wise_collection.db <<EOF
SELECT
    '  ' || o.opportunity_name as "Opportunity (Score >= 7.0)"
FROM opportunities o
WHERE o.total_score >= 7.0
ORDER BY o.total_score DESC
LIMIT 5;
EOF

echo ""
echo "=================================================="
echo -e "${GREEN}✓ Pipeline Test Complete!${NC}"
echo "=================================================="
echo ""
echo "Next steps:"
echo "  1. Review logs: cat logs/pipeline.log"
echo "  2. Check results: cat $LATEST_RESULTS | jq ."
echo "  3. Run individual stages for debugging"
echo ""
echo "Backup location: $BACKUP_DIR"
echo "To restore if needed:"
echo "  cp $BACKUP_DIR/wise_collection.db data/wise_collection.db"
echo ""
