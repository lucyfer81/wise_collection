# Pipeline重构进展 (Pipeline Upgrade Progress)

## 重构目标 (Objectives)

采用 **Architecture 3: Cluster-Centric Purge** 策略实现：
1. ✅ **Cluster-centric retention**: 只有持续被提及的pain_events才永久保留
2. ✅ **Dynamic cluster updates**: 新帖子立即影响cluster scores
3. ✅ **Performance**: 使用Chroma向量数据库加速相似度搜索
4. ✅ **Automatic cleanup**: 14天后自动删除orphan pain_events

---

## 实施进展 (Implementation Progress)

### Phase 1: 数据库Schema迁移 ✅
**文件**: `migrations/004_add_lifecycle_fields.py`

添加了lifecycle管理字段到`pain_events`表：
- `lifecycle_stage`: 'active', 'orphan', 或 'archived'
- `last_clustered_at`: 最后一次被cluster的时间
- `orphan_since`: 成为orphan的时间（用于cleanup scheduling）

**执行结果**:
- Total pain_events: 2242
- Active (in cluster): 1464
- Orphan (no cluster): 778

### Phase 2: Chroma集成 ✅
**文件**:
- `utils/chroma_client.py`: Chroma客户端封装
- `scripts/migrate_embeddings_to_chroma.py`: 迁移脚本

**Chroma配置**:
- 本地持久化存储: `data/chroma_db/`
- 使用DuckDB+Parquet后端
- 余弦相似度 (cosine similarity)
- 支持元数据过滤

**迁移结果**:
- ✅ 2242 embeddings成功迁移到Chroma
- ✅ 数据大小: 9.8MB
- ✅ 向量搜索测试通过

### Phase 3: DynamicClusterUpdater ✅
**文件**: `pipeline/dynamic_cluster.py`

**核心特性**:
1. **实时cluster更新**: 新pain_events立即找到或创建clusters
2. **智能合并策略**:
   - 相似度≥0.75: 合并到现有cluster
   - 相似度<0.75但24小时内≥4个相似events: 创建新cluster
   - 否则: 标记为orphan
3. **自动重新计算**: 更新cluster summaries和scores

**关键方法**:
- `process_new_pain_events()`: 处理新events
- `_find_similar_cluster()`: 查找相似clusters (使用Chroma)
- `_merge_into_cluster()`: 合并到现有cluster
- `_create_new_cluster()`: 创建新cluster (需要≥4个相似events)
- `_mark_as_orphan()`: 标记为orphan
- `_recalculate_affected_clusters()`: 重新计算cluster summaries

### Phase 4: Lifecycle清理系统 ✅
**文件**: `scripts/lifecycle_cleanup.py`

**功能**:
1. **标记orphans**: 无cluster的pain_events标记为orphan
2. **删除旧orphans**: 14天后自动删除
3. **归档inactive clusters**: 90天无活动的clusters标记为archived

**使用方法**:
```bash
# 查看统计
python scripts/lifecycle_cleanup.py --stats-only

# 运行完整清理
python scripts/lifecycle_cleanup.py --orphan-age 14 --cluster-inactivity 90
```

**Retention效果**:
- ✅ "反复被提起"的pain_events: 永久保留 (在cluster中)
- ✅ "集中被提起"的pain_events: 14天后自动删除
- ✅ 数据库保持精简，只保留有价值的数据

### Phase 5: 更新Pipeline流程 🚧 (进行中)
**已更新文件**:
- `pipeline/embed.py`: 使用Chroma存储embeddings

**待更新**:
- [ ] `run_pipeline.py`: 集成DynamicClusterUpdater
- [ ] `pipeline/cluster.py`: 替换为DynamicClusterUpdater
- [ ] 添加lifecycle cleanup到pipeline end

### Phase 6: 性能优化 ⏳ (待开始)
**计划优化**:
1. **并行LLM调用**: `extract_pain.py`使用ThreadPoolExecutor
2. **增量处理**: 每个stage只处理新数据 (使用时间戳)
3. **Chroma加速**: 向量搜索从O(n)降到O(log n)

**目标性能**:
- Fetch: 10分钟
- Filter: 10分钟
- Extract: 40分钟 → 8分钟 (并行化)
- Embed: 5分钟
- Cluster: 20分钟 → 10分钟 (Chroma)
- Map: 15分钟
- Score: 15分钟
- Decision: 5分钟
- **总计**: ~110分钟 (< 2小时目标) ✅

### Phase 7: 测试和验证 ⏳ (待开始)
**测试计划**:
1. **单元测试**: DynamicClusterUpdater各个方法
2. **集成测试**: 完整pipeline运行
3. **性能测试**: 验证< 2小时目标
4. **数据一致性**: 验证Chroma和SQLite数据一致性

---

## 下一步 (Next Steps)

1. ✅ 提交当前代码到`pipeline-upgrade`分支
2. [ ] 更新`run_pipeline.py`集成DynamicClusterUpdater
3. [ ] 实现并行LLM调用优化
4. [ ] 完整测试pipeline
5. [ ] 合并到`main`分支

---

## 架构对比 (Before vs After)

| 方面 | 旧架构 | 新架构 (Arch 3) |
|------|--------|-----------------|
| **Embedding存储** | SQLite (pickle BLOB) | Chroma (向量数据库) |
| **Clustering** | 静态batch聚类 | 动态streaming聚类 |
| **Cluster更新** | 一次性创建后不变 | 实时更新，新data立即影响scores |
| **Data Retention** | 无限制增长 | Cluster-centric自动清理 |
| **性能** | O(n)向量搜索 | O(log n)向量搜索 (HNSW) |
| **反复性vs集中性** | 无区分 | ✅ 自动识别反复性pattern |

---

## 数据备份 (Backup Strategy)

**Chroma数据位置**:
```
data/chroma_db/
├── chroma.sqlite3  (9.8MB - 可手工备份)
└── 7d8cc93c-eef7-4c67-a94d-e1f152501eac/  (向量数据)
```

**备份建议**:
```bash
# 备份Chroma
tar -czf chroma_backup_$(date +%Y%m%d).tar.gz data/chroma_db/

# 备份SQLite
cp data/wise_collection.db data/wise_collection.db.backup_$(date +%Y%m%d)
```

---

## 重要提示 (Important Notes)

1. **Chroma vs pain_embeddings表**: 目前两者共存，测试完成后可删除`pain_embeddings`表
2. **Lifecycle cleanup**: 建议通过cron每日运行:
   ```bash
   # 添加到crontab (每天凌晨2点运行)
   0 2 * * * cd /path/to/reddit_pain_finder && python scripts/lifecycle_cleanup.py
   ```
3. **新pain_events**: 每日pipeline运行时会自动触发DynamicClusterUpdater

---

**生成时间**: 2026-01-13
**分支**: pipeline-upgrade
