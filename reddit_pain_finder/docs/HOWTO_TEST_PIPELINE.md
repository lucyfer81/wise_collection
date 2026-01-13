# 如何测试全流程Pipeline (How to Test Full Pipeline)

**文档版本**: v1.0
**最后更新**: 2026-01-13

---

## 🚀 快速开始

### 方法1: 使用自动化测试脚本 (推荐)

```bash
# 运行完整测试 (默认limits，适合快速验证)
./scripts/run_full_pipeline_test.sh

# 运行完整测试 (处理所有数据)
./scripts/run_full_pipeline_test.sh --process-all

# 运行增量测试 (只处理新数据)
./scripts/run_full_pipeline_test.sh --incremental
```

**脚本会自动**:
1. ✅ 检查环境 (Python版本、依赖、配置文件)
2. ✅ 备份当前数据
3. ✅ 显示当前数据库状态
4. ✅ 运行完整pipeline
5. ✅ 显示结果统计
6. ✅ 验证和推荐

---

### 方法2: 手动运行Pipeline

#### Step 1: 检查环境

```bash
# 检查Python版本 (需要 >= 3.10)
python --version

# 检查依赖
python -c "import chromadb; print('ChromaDB OK')"
python -c "import yaml; print('PyYAML OK')"

# 检查配置文件
ls -lh config/llm.yaml
ls -lh config/thresholds.yaml

# 检查数据库
ls -lh data/wise_collection.db
ls -lh data/chroma_db/
```

#### Step 2: 备份数据 (重要!)

```bash
# 创建备份目录
mkdir -p backups/backup_$(date +%Y%m%d_%H%M%S)

# 备份数据库
cp data/wise_collection.db backups/backup_$(date +%Y%m%d_%H%M%S)/

# 备份Chroma (如果存在)
tar -czf backups/backup_$(date +%Y%m%d_%H%M%S)/chroma_db.tar.gz -C data/ chroma_db

echo "Backup completed!"
```

#### Step 3: 查看当前状态

```bash
# 查看数据库统计
sqlite3 data/wise_collection.db <<EOF
SELECT
    'Raw posts: ' || COUNT(*) as stat FROM posts
UNION ALL
SELECT '    Filtered: ' || COUNT(*) FROM filtered_posts
UNION ALL
SELECT '    Pain events: ' || COUNT(*) FROM pain_events
UNION ALL
SELECT '    Clusters: ' || COUNT(*) FROM clusters
UNION ALL
SELECT '    Opportunities: ' || COUNT(*) FROM opportunities;
EOF

# 查看lifecycle状态
sqlite3 data/wise_collection.db <<EOF
SELECT
    lifecycle_stage,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM pain_events), 1) || '%' as percentage
FROM pain_events
GROUP BY lifecycle_stage;
EOF
```

#### Step 4: 运行Pipeline

```bash
# 选项A: 运行完整pipeline (推荐)
python run_pipeline.py --stage all --process-all --save-results --enable-monitoring

# 选项B: 运行pipeline (使用默认limits，更快)
python run_pipeline.py --stage all --save-results --enable-monitoring

# 选项C: 运行pipeline (增量模式，只处理新数据)
python run_pipeline.py --stage all --save-results --enable-monitoring
```

**参数说明**:
- `--stage all`: 运行所有stage (fetch → filter → extract → embed → cluster → map → score → decision)
- `--process-all`: 处理所有数据 (不使用默认limits)
- `--save-results`: 保存运行结果到JSON文件
- `--enable-monitoring`: 启用性能监控 (LLM调用次数、token使用、成本)

#### Step 5: 监控运行进度

**在另一个终端窗口中**:

```bash
# 实时查看日志
tail -f logs/pipeline.log

# 或查看最后50行
tail -n 50 logs/pipeline.log

# 监控数据库大小变化
watch -n 30 'du -sh data/wise_collection.db data/chroma_db/'

# 监控进程
ps aux | grep run_pipeline

# 监控系统资源
htop
# 或
top
```

#### Step 6: 检查结果

```bash
# 查看最新结果文件
ls -lt pipeline_results_*.json | head -1
LATEST=$(ls -t pipeline_results_*.json | head -1)

# 查看结果摘要
cat $LATEST | jq '.final_summary'

# 查看各stage统计
cat $LATEST | jq '.stage_results'

# 查看性能指标
cat $LATEST | jq '.performance'

# 查看top opportunities
cat $LATEST | jq '.final_summary.top_opportunities'
```

---

## 📊 验证检查清单

### 1. 数据完整性检查

```bash
# 检查posts是否增加
sqlite3 data/wise_collection.db "SELECT COUNT(*) FROM posts;"

# 检查filtered_posts是否增加
sqlite3 data/wise_collection.db "SELECT COUNT(*) FROM filtered_posts;"

# 检查pain_events是否增加
sqlite3 data/wise_collection.db "SELECT COUNT(*) FROM pain_events;"

# 检查clusters是否更新
sqlite3 data/wise_collection.db "SELECT COUNT(*) FROM clusters;"

# 检查opportunities是否增加
sqlite3 data/wise_collection.db "SELECT COUNT(*) FROM opportunities;"
```

### 2. Lifecycle状态检查

```bash
# 检查active vs orphan比例
sqlite3 data/wise_collection.db <<EOF
SELECT
    'Active (in clusters): ' || COUNT(*) FILTER (WHERE lifecycle_stage = 'active') as stat
FROM pain_events
UNION ALL
SELECT
    'Orphans (will be deleted): ' || COUNT(*) FILTER (WHERE lifecycle_stage = 'orphan')
FROM pain_events
UNION ALL
SELECT
    'Retention rate: ' || ROUND(COUNT(*) FILTER (WHERE lifecycle_stage = 'active') * 100.0 / COUNT(*), 1) || '%'
FROM pain_events;
EOF
```

**预期结果**:
- Active events应该占60-70%
- Orphan events应该占30-40%
- Retention rate应该在60-70%

### 3. Chroma数据一致性

```bash
# 运行一致性测试
python tests/test_05_data_consistency.py
```

**预期结果**: ✅ All checks passed

### 4. 性能指标检查

```bash
# 从结果文件中提取性能数据
LATEST=$(ls -t pipeline_results_*.json | head -1)
python <<EOF
import json

with open('$LATEST', 'r') as f:
    results = json.load(f)

perf = results.get('performance', {})
print(f"Total duration: {perf.get('total_duration_minutes', 0):.1f} minutes")
print(f"LLM calls: {perf.get('total_llm_calls', 0):,}")
print(f"Total tokens: {perf.get('total_tokens', 0):,}")
print(f"Estimated cost: ${perf.get('estimated_cost_usd', 0):.4f} USD")

# 各stage耗时
stages = perf.get('stages_summary', {})
print("\nStage breakdown:")
for stage, stats in stages.items():
    print(f"  {stage}: {stats.get('duration_seconds', 0):.1f}s ({stats.get('items_processed', 0)} items)")
EOF
```

### 5. Top Opportunities验证

```bash
# 查看得分>=7.0的opportunities
sqlite3 data/wise_collection.db <<EOF
SELECT
    o.opportunity_name,
    o.total_score,
    o.recommendation,
    c.cluster_name
FROM opportunities o
JOIN clusters c ON o.cluster_id = c.id
WHERE o.total_score >= 7.0
ORDER BY o.total_score DESC
LIMIT 10;
EOF
```

---

## 🐛 故障排查

### 问题1: ImportError: No module named 'chromadb'

**解决方案**:
```bash
pip install chromadb
```

### 问题2: Database is locked

**解决方案**:
```bash
# 检查是否有其他进程在使用
ps aux | grep python

# 停止其他pipeline进程
pkill -f run_pipeline

# 等待几秒后重试
sleep 5
python run_pipeline.py --stage all
```

### 问题3: LLM API rate limit exceeded

**解决方案**:
```bash
# 修改config/llm.yaml，降低并发
# 或等待一段时间后重试

# 查看失败日志
grep -i "rate limit" logs/pipeline.log
```

### 问题4: Pipeline运行时间过长 (>2小时)

**解决方案**:
```bash
# 使用默认limits而不是--process-all
python run_pipeline.py --stage all --save-results

# 或只运行特定stage
python run_pipeline.py --stage extract
python run_pipeline.py --stage cluster
```

### 问题5: 内存不足 (Out of memory)

**解决方案**:
```bash
# 监控内存使用
/usr/bin/time -v python run_pipeline.py --stage all

# 如果超过4GB，考虑减少并发或batch size

# 或分stage运行
for stage in fetch filter extract embed cluster; do
    python run_pipeline.py --stage $stage
done
```

---

## 📈 性能基准

### 预期运行时间 (使用当前代码)

| 模式 | 数据量 | 预期时间 | 说明 |
|------|--------|----------|------|
| **测试模式** (默认limits) | ~100 posts | ~30-45分钟 | 快速验证 |
| **首次运行** (--process-all) | 全部数据 | ~2-3小时 | 处理所有历史数据 |
| **后续运行** (增量) | 新数据 | ~30-60分钟 | 只处理新数据 |

### 各Stage预期耗时

| Stage | 预期时间 | 说明 |
|-------|----------|------|
| Fetch | 5-10 min | 取决于网络和subreddits |
| Filter | 5-10 min | LLM调用 |
| Extract | 30-40 min | **最慢** (大量LLM调用) |
| Embed | 3-5 min | 本地embedding |
| Cluster | 15-20 min | Chroma查询 + LLM验证 |
| Map | 10-15 min | LLM调用 |
| Score | 10-15 min | LLM调用 |
| Decision | 3-5 min | LLM调用 |
| Cleanup | <1 min | 数据库操作 |

---

## 🎯 成功标准

运行pipeline后，应该看到：

### 1. 日志输出

```
✅ Stage 1 completed: Found X posts
✅ Stage 2 completed: Y/X posts passed
✅ Stage 3 completed: Extracted Z pain events
✅ Stage 4 completed: Created Z embeddings
✅ Stage 5 completed:
   Events processed: N
   New clusters: M
   Updated clusters: K
✅ Stage 6 completed: Mapped O opportunities
✅ Stage 7 completed: Scored P opportunities
✅ Stage 8 completed: Generated S candidates
✅ Stage 9 completed:
   Active events: A
   Orphan events: O
   Retention rate: R%
```

### 2. 数据增长

```
Before:
  Raw posts: 2330
  Pain events: 2242
  Clusters: 36

After (假设新增100 posts):
  Raw posts: 2430 (+100)
  Pain events: ~2342 (+100)
  Clusters: 36-38 (可能新增)
```

### 3. Lifecycle状态

```
Active events: ~1500-1600 (60-70%)
Orphan events: ~700-900 (30-40%)
Retention rate: 60-70%
```

### 4. 新发现的机会

```
Top opportunities (score >= 7.0):
  1. [Opportunity name] - Score: 8.5
  2. [Opportunity name] - Score: 7.8
  3. ...
```

---

## 📝 测试报告模板

完成测试后，建议记录：

```markdown
## Pipeline测试报告

**测试日期**: YYYY-MM-DD
**测试模式**: [默认/全量/增量]
**测试人员**: [Your name]

### 环境信息
- Python版本:
- 分支:
- Commit:

### 运行结果
- 总运行时间: X分钟
- 新增posts: X
- 新增pain_events: Y
- 新增clusters: Z

### 性能指标
- LLM调用次数: N
- Token使用量: T
- 预估成本: $X.XX

### 发现的问题
- [如有]

### Top Opportunities
1. [Opportunity 1]
2. [Opportunity 2]

### 下一步
- [ ] Phase 5: 更新run_pipeline.py
- [ ] Phase 6: 性能优化
- [ ] 其他
```

---

## 🔍 高级调试技巧

### 1. 单独运行某个Stage

```bash
# 只运行fetch stage
python run_pipeline.py --stage fetch --limit-sources 5

# 只运行filter stage
python run_pipeline.py --stage filter --limit-posts 10

# 只运行extract stage
python run_pipeline.py --stage extract --limit-posts 10

# 只运行cluster stage
python run_pipeline.py --stage cluster

# 只运行lifecycle cleanup
python run_pipeline.py --stage lifecycle_cleanup
```

### 2. 查看详细日志

```bash
# 修改logging level为DEBUG
# 在run_pipeline.py中修改:
# logging.basicConfig(level=logging.DEBUG)

# 重新运行
python run_pipeline.py --stage all 2>&1 | tee pipeline_debug.log
```

### 3. 使用Python Profiler

```bash
# 性能分析
python -m cProfile -o pipeline.prof run_pipeline.py --stage all

# 查看结果
python -m pstats pipeline.prof
# 进入交互界面后：
# > stats 10  # 查看top 10最慢的函数
# > callers run_stage_cluster  # 查看谁调用了cluster stage
```

### 4. 数据库查询分析

```bash
# 启用SQLite查询日志
export SQLITE_TRACE="1"
python run_pipeline.py --stage cluster

# 或在代码中添加:
# import sqlite3
# sqlite3.connect('...', check_same_thread=False).set_trace_callback(print)
```

---

## ✅ 完成测试后

### 1. 清理临时文件

```bash
# 查看临时文件
ls -lh pipeline_results_*.json
ls -lh docs/reports/pipeline_metrics_*.json

# 保留最近的，删除旧的
ls -t pipeline_results_*.json | tail -n +6 | xargs rm -
```

### 2. 提交代码

```bash
# 如果有修改
git status
git add .
git commit -m "test: Run full pipeline test"
```

### 3. 准备下一步

根据测试结果，决定：

**如果测试通过** ✅:
- 继续Phase 5: 更新run_pipeline.py
- 或先在真实环境运行几次验证

**如果测试失败** ❌:
- 查看日志找出问题
- 单独运行失败的stage调试
- 参考本文档的"故障排查"部分

---

## 📞 获取帮助

如果遇到问题：

1. 查看日志: `cat logs/pipeline.log`
2. 查看本文档的"故障排查"部分
3. 运行测试套件验证: `python tests/test_*.py`
4. 检查已知问题: `docs/PHASE_5_6_DEV_GUIDE.md`

---

**文档作者**: Claude Sonnet 4.5
**最后更新**: 2026-01-13
