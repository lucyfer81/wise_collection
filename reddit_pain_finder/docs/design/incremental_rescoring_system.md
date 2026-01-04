# 增量更新重新评分系统设计文档

**版本**: 1.0
**日期**: 2026-01-04
**作者**: Claude (UltraThink Mode)
**状态**: 设计阶段

---

## 📋 目录

1. [问题分析](#问题分析)
2. [设计目标](#设计目标)
3. [核心概念](#核心概念)
4. [系统架构](#系统架构)
5. [数据模型设计](#数据模型设计)
6. [触发检测机制](#触发检测机制)
7. [评分策略设计](#评分策略设计)
8. [实现计划](#实现计划)
9. [风险评估](#风险评估)
10. [性能考虑](#性能考虑)

---

## 问题分析

### 当前问题

从数据分析中发现的3个核心问题：

#### 问题1：增量更新的clusters被忽略

```sql
-- 最近24小时新增events的clusters
Cluster 5:  +62 events (1107 total) → raw_total_score = 8.31 (已评分)
Cluster 26: +16 events (30 total)   → raw_total_score = 7.67 (已评分)
Cluster 11: +11 events (52 total)   → raw_total_score = 7.27 (已评分)
Cluster 22: +10 events (32 total)   → raw_total_score = 0.0  (未评分)
```

**问题**：
- Cluster 5, 26, 11在今天获得了10-62个新events
- 它们已经有opportunities，所以map_opportunities跳过它们
- 即使获得了新数据，opportunity的评分仍然是旧的
- **无法反映最新的cluster状态**

#### 问题2：新创建的小clusters被过滤规则阻止评分

```sql
-- 新clusters（今天创建）
Cluster 35: 4 events → raw_total_score = 0.0 (abandon - 聚类规模过小)
Cluster 36: 4 events → raw_total_score = 0.0 (abandon - 聚类规模过小)
```

**问题**：
- Filtering rules在LLM评分**之前**应用
- 小clusters根本没有机会被评估
- 即使它们可能包含有价值的insights
- **31个opportunities（86%）没有被评分**

#### 问题3：Decision_shortlist只能显示历史数据

```python
# decision_shortlist.py:79
WHERE o.raw_total_score >= 6.0  # 新opportunities都是0.0
```

**问题**：
- 新opportunities的raw_total_score = 0.0，不满足阈值
- 只能返回历史评分的opportunities (ID: 2, 5)
- **Report反映的不是最新的cluster状态**

### 根本原因

**Pipeline设计没有考虑"增量更新"场景**：

1. `map_opportunities` 只为"没有opportunity的clusters"创建新opportunities
2. `score_viability` 的filtering rules在评分**之前**过滤
3. `decision_shortlist` 没有考虑"最近更新的clusters"

---

## 设计目标

### 核心目标

1. **检测显著变化**: 自动检测clusters的显著变化（新增events、跨源验证等）
2. **智能重新评分**: 为显著变化的clusters重新评分，而不是盲目重新评分所有clusters
3. **避免无限循环**: 防止每次pipeline运行都重新评分所有clusters
4. **保持历史记录**: 保留评分历史，便于分析趋势和回滚
5. **成本可控**: LLM调用成本要合理，不能因为重新评分导致成本爆炸

### 非目标（明确不做）

1. ~~实时更新~~ - 不需要实时，批量处理即可
2. ~~完全重写pipeline~~ - 在现有架构上增量改进
3. ~~自动删除旧opportunities~~ - 保留历史记录

---

## 核心概念

### 1. Cluster快照 (Cluster Snapshot)

在某个时间点记录cluster的关键指标，用于检测变化：

```python
{
    "cluster_id": 5,
    "snapshot_time": "2026-01-04 04:10:08",
    "cluster_size": 1107,
    "unique_authors": 523,
    "cross_subreddit_count": 63,
    "avg_frequency_score": 7.2,
    "latest_event_extracted_at": "2026-01-04 04:10:08"
}
```

### 2. 显著变化 (Significant Change)

满足以下**任一条件**即认为cluster发生了显著变化：

```yaml
# 触发阈值
significant_change_thresholds:
  min_new_events: 5              # 最少5个新events
  min_new_events_ratio: 0.1      # 或新增10%的events
  min_new_authors: 3             # 或最少3个新作者
  min_cross_subreddit_delta: 2   # 或跨subreddit数增加2
  min_days_since_last_score: 7   # 或距离上次评分已过7天
```

### 3. 评分批次 (Scoring Batch)

一组需要重新评分的opportunities，批量处理以提高效率：

```python
{
    "batch_id": "batch_20260104_122553",
    "trigger_type": "incremental_update",
    "clusters": [5, 26, 11, 22],
    "created_at": "2026-01-04 12:25:53",
    "status": "pending"
}
```

### 4. 评分版本 (Scoring Version)

opportunity的多个版本，保留评分历史：

```python
{
    "opportunity_id": 5,
    "version": 2,
    "raw_total_score": 8.5,  # 新评分
    "cluster_size_at_score": 1107,  # 评分时的cluster大小
    "scored_at": "2026-01-04 12:30:00",
    "change_reason": "Added 62 new events",
    "previous_version": 1
}
```

---

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Pipeline Run (Full/Incremental)          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │   Cluster Stage (Incremental Update)   │
        │   - 合并新events到已有clusters          │
        │   - 更新cluster快照                    │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  Change Detection Stage (NEW!)         │
        │  - 检测显著变化的clusters               │
        │  - 创建评分批次                        │
        └───────────────────────────────────────┘
                            │
                            ├─────────────────┬─────────────────┐
                            ▼                 ▼                 ▼
        ┌───────────────────────┐  ┌──────────────────┐  ┌──────────────────┐
        │  Map Opportunities     │  │  Update Existing │  │ Create New Opps │
        │  (为新clusters)        │  │  Opportunities   │  │ (新clusters)     │
        └───────────────────────┘  └──────────────────┘  └──────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │   Score Viability (Modified)           │
        │   - Filtering在评分之后应用              │
        │   - 为批次中的opps评分                  │
        │   - 保存评分版本                        │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │   Decision Shortlist (Enhanced)        │
        │   - 优先考虑最近评分的opportunities      │
        │   - 考虑cluster的freshness             │
        └───────────────────────────────────────┘
```

### 关键变更点

#### 1. 新增：Change Detection Stage

```python
# pipeline/change_detection.py (NEW!)

class ChangeDetector:
    """检测clusters的显著变化"""

    def detect_significant_changes(
        self,
        hours: int = 24  # 检查最近N小时的变化
    ) -> List[Dict[str, Any]]:
        """检测最近N小时内发生显著变化的clusters"""

        return [
            {
                "cluster_id": 5,
                "change_type": "significant_new_events",
                "new_events_count": 62,
                "new_events_ratio": 0.059,  # 62/1045
                "previous_snapshot": {...},
                "current_snapshot": {...}
            },
            ...
        ]
```

#### 2. 修改：Map Opportunities Stage

```python
# pipeline/map_opportunity.py (MODIFIED)

def map_opportunities_for_clusters(
    self,
    clusters_to_update: List[int] = None  # NEW: 指定需要更新的clusters
) -> Dict[str, Any]:
    """为clusters映射opportunities

    Args:
        clusters_to_update: 指定需要更新opportunities的cluster IDs
                           None表示只为新clusters创建（默认行为）
    """

    if clusters_to_update:
        # 为指定的clusters重新生成opportunities
        clusters = db.get_clusters_by_ids(clusters_to_update)
        # 删除旧的opportunities
        for cluster_id in clusters_to_update:
            db.delete_opportunities_for_cluster(cluster_id)
    else:
        # 默认行为：只为没有opportunities的clusters创建
        clusters = db.get_clusters_for_opportunity_mapping()
```

#### 3. 修改：Score Viability Stage

```python
# pipeline/score_viability.py (MODIFIED)

class ViabilityScorer:

    def score_opportunities(
        self,
        limit: int = 100,
        batch_id: str = None,  # NEW: 评分批次ID
        skip_filtering: bool = False  # NEW: 是否跳过filtering
    ) -> Dict[str, Any]:

        # 1. 先进行LLM评分（不受filtering影响）
        for opportunity in opportunities:
            enhanced = self._enhance_opportunity_data(opportunity)
            llm_result = self._score_with_llm(enhanced)
            # 保存评分结果
            self._save_scoring_version(opportunity, llm_result, batch_id)

        # 2. 然后应用filtering rules（只用于标记，不影响评分）
        if not skip_filtering and self.filtering_rules.get("enabled"):
            opportunities = self._apply_filtering_rules(opportunities)
```

#### 4. 增强：Decision Shortlist Stage

```python
# pipeline/decision_shortlist.py (ENHANCED)

class DecisionShortlistGenerator:

    def _apply_hard_filters(self) -> List[Dict[str, Any]]:
        """应用硬性过滤规则（考虑新鲜度）"""

        # NEW: 添加"新鲜度"加分
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("""
                SELECT
                    o.*,
                    c.cluster_size,
                    -- 新增：计算新鲜度分数
                    CASE
                        WHEN o.scored_at > datetime('now', '-24 hours') THEN 1.5
                        WHEN o.scored_at > datetime('now', '-3 days') THEN 1.2
                        WHEN o.scored_at > datetime('now', '-7 days') THEN 1.0
                        ELSE 0.8
                    END as freshness_factor
                FROM opportunities o
                JOIN clusters c ON o.cluster_id = c.id
                WHERE o.raw_total_score * freshness_factor >= ?
                ORDER BY o.raw_total_score * freshness_factor DESC
            """, (min_viability,))
```

---

## 数据模型设计

### 1. 新增表：`cluster_snapshots`

记录cluster的关键指标快照，用于检测变化：

```sql
CREATE TABLE cluster_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER NOT NULL,
    snapshot_time TIMESTAMP NOT NULL,

    -- Cluster指标
    cluster_size INTEGER NOT NULL,
    unique_authors INTEGER NOT NULL,
    cross_subreddit_count INTEGER NOT NULL,
    avg_frequency_score REAL,
    latest_event_extracted_at TIMESTAMP,

    -- 元数据
    snapshot_reason TEXT,  -- 'initial', 'before_rescoring', 'periodic'
    pipeline_run_id TEXT,

    FOREIGN KEY (cluster_id) REFERENCES clusters(id)
);

CREATE INDEX idx_cluster_snapshots_cluster_id
    ON cluster_snapshots(cluster_id, snapshot_time DESC);
```

### 2. 新增表：`scoring_batches`

记录评分批次：

```sql
CREATE TABLE scoring_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT UNIQUE NOT NULL,
    trigger_type TEXT NOT NULL,  -- 'incremental_update', 'full_rebuild', 'manual'

    -- 批次信息
    clusters_count INTEGER NOT NULL,
    cluster_ids TEXT NOT NULL,  -- JSON array

    -- 状态追踪
    status TEXT NOT NULL,  -- 'pending', 'in_progress', 'completed', 'failed'
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,

    -- 统计
    opportunities_scored INTEGER DEFAULT 0,
    opportunities_passed_filter INTEGER DEFAULT 0,
    avg_score REAL,

    FOREIGN KEY (batch_id) REFERENCES pipeline_run_results(batch_id)
);
```

### 3. 新增表：`opportunity_versions`

保留opportunity的评分历史：

```sql
CREATE TABLE opportunity_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER NOT NULL,
    version INTEGER NOT NULL,

    -- Cluster状态快照（评分时）
    cluster_size_at_score INTEGER NOT NULL,
    unique_authors_at_score INTEGER NOT NULL,
    cross_subreddit_at_score INTEGER NOT NULL,

    -- 评分结果
    raw_total_score REAL NOT NULL,
    total_score REAL NOT NULL,
    trust_level REAL NOT NULL,
    component_scores TEXT,  -- JSON
    killer_risks TEXT,  -- JSON array
    recommendation TEXT,

    -- 元数据
    scored_at TIMESTAMP NOT NULL,
    change_reason TEXT,  -- 为什么重新评分
    batch_id TEXT,  -- 关联到scoring_batches
    pipeline_run_id TEXT,

    FOREIGN KEY (opportunity_id) REFERENCES opportunities(id),
    FOREIGN KEY (batch_id) REFERENCES scoring_batches(batch_id)
);

CREATE INDEX idx_opportunity_versions_opp_id_version
    ON opportunity_versions(opportunity_id, version DESC);
```

### 4. 修改表：`opportunities`

添加新字段：

```sql
-- 添加新字段到opportunities表
ALTER TABLE opportunities ADD COLUMN current_version INTEGER DEFAULT 1;
ALTER TABLE opportunities ADD COLUMN last_rescored_at TIMESTAMP;
ALTER TABLE opportunities ADD COLUMN rescore_count INTEGER DEFAULT 0;
ALTER TABLE opportunities ADD COLUMN scored_at TIMESTAMP;
```

---

## 触发检测机制

### 算法设计

```python
# pipeline/change_detection.py

def detect_significant_changes(
    self,
    hours: int = 24
) -> List[Dict[str, Any]]:

    # 1. 获取阈值配置
    thresholds = self.config.get('significant_change_thresholds', {})

    # 2. 获取所有clusters的最新快照
    latest_snapshots = db.get_latest_cluster_snapshots()

    # 3. 对每个cluster检查变化
    significant_changes = []

    for cluster in db.get_all_clusters():
        cluster_id = cluster['id']

        # 3.1 获取上一个快照
        previous_snapshot = latest_snapshots.get(cluster_id)

        if not previous_snapshot:
            # 新cluster，需要首次评分
            significant_changes.append({
                "cluster_id": cluster_id,
                "change_type": "new_cluster",
                "reason": "First time scoring"
            })
            continue

        # 3.2 计算变化指标
        current_metrics = self._calculate_cluster_metrics(cluster_id)
        previous_metrics = previous_snapshot

        # 3.3 检查是否满足显著变化条件
        change_detected = False
        change_reasons = []

        # 检查1: 新增events数量
        new_events = current_metrics['cluster_size'] - previous_metrics['cluster_size']
        if (new_events >= thresholds['min_new_events'] or
            new_events / previous_metrics['cluster_size'] >= thresholds['min_new_events_ratio']):
            change_detected = True
            change_reasons.append(f"Added {new_events} new events")

        # 检查2: 新增作者
        new_authors = current_metrics['unique_authors'] - previous_metrics['unique_authors']
        if new_authors >= thresholds['min_new_authors']:
            change_detected = True
            change_reasons.append(f"Added {new_authors} new authors")

        # 检查3: 跨源验证增加
        cross_subreddit_delta = (current_metrics['cross_subreddit_count'] -
                                previous_metrics['cross_subreddit_count'])
        if cross_subreddit_delta >= thresholds['min_cross_subreddit_delta']:
            change_detected = True
            change_reasons.append(
                f"Cross-subreddit count increased by {cross_subreddit_delta}"
            )

        # 检查4: 距离上次评分的时间
        if previous_snapshot.get('last_scored_at'):
            days_since_last_score = (
                datetime.now() -
                datetime.fromisoformat(previous_snapshot['last_scored_at'])
            ).days
            if days_since_last_score >= thresholds['min_days_since_last_score']:
                change_detected = True
                change_reasons.append(
                    f"{days_since_last_score} days since last score"
                )

        if change_detected:
            significant_changes.append({
                "cluster_id": cluster_id,
                "change_type": "significant_update",
                "reasons": change_reasons,
                "previous_snapshot": previous_metrics,
                "current_snapshot": current_metrics
            })

    return significant_changes
```

### 触发条件配置

```yaml
# config/thresholds.yaml (新增)

# 显著变化检测阈值
significant_change_thresholds:
  # 新增events触发条件（满足任一即可）
  min_new_events: 5              # 绝对值：最少5个新events
  min_new_events_ratio: 0.1      # 相对值：新增10%的events

  # 新增作者触发条件
  min_new_authors: 3             # 最少3个新作者

  # 跨源验证触发条件
  min_cross_subreddit_delta: 2   # 跨subreddit数增加2

  # 时间触发条件
  min_days_since_last_score: 7   # 距离上次评分已过7天

  # 周期性全量更新
  periodic_full_rescore_days: 30  # 每30天全量重新评分一次
```

---

## 评分策略设计

### 策略1：增量更新评分

**适用场景**：Clusters获得了新的events或指标

**流程**：
```python
# 1. 检测变化
changes = detector.detect_significant_changes(hours=24)

# 2. 创建评分批次
batch_id = db.create_scoring_batch(
    trigger_type="incremental_update",
    cluster_ids=[c['cluster_id'] for c in changes]
)

# 3. 为这些clusters重新生成opportunities
mapper.map_opportunities_for_clusters(
    clusters_to_update=[c['cluster_id'] for c in changes]
)

# 4. 评分（跳过filtering，因为这是更新）
scorer.score_opportunities(
    batch_id=batch_id,
    skip_filtering=True  # 关键：跳过filtering
)

# 5. 保存评分版本
db.save_opportunity_versions(batch_id)
```

**关键点**：
- 只为显著变化的clusters重新评分
- 跳过filtering rules（因为是更新，不是新创建）
- 保留评分历史，便于回滚

### 策略2：首次评分（宽松filtering）

**适用场景**：新创建的clusters首次评分

**流程**：
```python
# 1. 获取新创建的clusters
new_clusters = db.get_new_clusters(hours=24)

# 2. 创建opportunities
mapper.map_opportunities_for_clusters(
    clusters_to_update=[c['id'] for c in new_clusters]
)

# 3. 评分（应用宽松的filtering）
scorer.score_opportunities(
    batch_id=batch_id,
    # 关键：使用宽松的filtering规则
    filtering_rules_override={
        "min_cluster_size": 3,        # 从5降至3
        "min_unique_authors": 2,      # 从4降至2
        "min_avg_frequency_score": 4.0  # 从5.0降至4.0
    }
)
```

**关键点**：
- 新clusters使用宽松的filtering规则
- 让更多opportunities进入评分流程
- 即使最终被标记为"abandon"，也有LLM评分结果

### 策略3：周期性全量更新

**适用场景**：定期全量重新评分

**流程**：
```python
# 每30天执行一次
if should_run_full_rescore():
    # 1. 标记所有opportunities需要更新
    all_clusters = db.get_all_cluster_ids()

    # 2. 创建全量评分批次
    batch_id = db.create_scoring_batch(
        trigger_type="full_rebuild",
        cluster_ids=all_clusters
    )

    # 3. 逐批处理（避免LLM API限流）
    for i in range(0, len(all_clusters), batch_size):
        batch = all_clusters[i:i+batch_size]
        mapper.map_opportunities_for_clusters(clusters_to_update=batch)
        scorer.score_opportunities(batch_id=batch_id, skip_filtering=True)
```

**关键点**：
- 定期全量更新，捕捉长期趋势变化
- 分批处理，避免API限流
- 可以在夜间或低峰期执行

---

## 实现计划

### Phase 1: 数据模型（1-2天）

**任务清单**：
- [ ] 创建`cluster_snapshots`表
- [ ] 创建`scoring_batches`表
- [ ] 创建`opportunity_versions`表
- [ ] 修改`opportunities`表（添加新字段）
- [ ] 编写数据库迁移脚本
- [ ] 编写单元测试（数据库操作）

**验收标准**：
- 所有表创建成功，索引正确
- 迁移脚本可以安全地升级现有数据库
- 单元测试覆盖所有CRUD操作

### Phase 2: Change Detection（2-3天）

**任务清单**：
- [ ] 实现`ChangeDetector`类
- [ ] 实现`detect_significant_changes()`方法
- [ ] 实现`_calculate_cluster_metrics()`方法
- [ ] 添加配置项到`thresholds.yaml`
- [ ] 编写单元测试（各种触发条件）
- [ ] 集成到pipeline（新增stage）

**验收标准**：
- 能正确检测新增events、作者、跨源等变化
- 单元测试覆盖所有触发条件
- 集成测试：pipeline能正常运行

### Phase 3: Enhanced Scoring（3-4天）

**任务清单**：
- [ ] 修改`ViabilityScorer.score_opportunities()`方法
  - [ ] 添加`skip_filtering`参数
  - [ ] 添加`batch_id`参数
  - [ ] 添加`filtering_rules_override`参数
- [ ] 实现`_save_scoring_version()`方法
- [ ] 修改`_apply_filtering_rules()`为评分后处理
- [ ] 编写单元测试（各种评分场景）

**验收标准**：
- Filtering在LLM评分**之后**应用
- 评分版本正确保存到`opportunity_versions`表
- 单元测试覆盖：首次评分、重新评分、filtering各种情况

### Phase 4: Enhanced Decision Shortlist（2天）

**任务清单**：
- [ ] 修改`DecisionShortlistGenerator._apply_hard_filters()`
- [ ] 添加新鲜度计算逻辑
- [ ] 更新排序算法（综合考虑分数和新鲜度）
- [ ] 添加配置项（新鲜度权重）
- [ ] 编写单元测试

**验收标准**：
- 最近评分的opportunities有更高优先级
- 可以配置新鲜度权重
- Report能反映最新数据

### Phase 5: Pipeline Integration（2-3天）

**任务清单**：
- [ ] 更新`pipeline/main.py`
- [ ] 添加`--rescore`参数（支持手动触发重新评分）
- [ ] 实现批次处理逻辑
- [ ] 添加进度报告和日志
- [ ] 编写集成测试

**验收标准**：
- `--stage full`自动包含change detection
- `--rescore cluster_id`支持手动触发单个cluster重新评分
- 集成测试端到端运行

### Phase 6: Testing & Validation（2-3天）

**任务清单**：
- [ ] 单元测试（目标覆盖率：80%+）
- [ ] 集成测试
- [ ] 性能测试（确保不显著变慢）
- [ ] 回归测试（确保现有功能不受影响）
- [ ] 手动测试（使用真实数据）

**验收标准**：
- 所有测试通过
- 性能测试：pipeline运行时间增加 < 20%
- 手动测试：Report能反映最近更新的clusters

### Phase 7: Documentation & Deployment（1-2天）

**任务清单**：
- [ ] 更新README（新功能说明）
- [ ] 编写使用文档（如何触发重新评分）
- [ ] 编写架构文档（系统设计）
- [ ] 准备部署脚本
- [ ] 准备回滚方案

**验收标准**：
- 文档完整、清晰
- 部署脚本测试通过
- 回滚方案验证

**总估算时间**: 13-19天

---

## 风险评估

### 风险1：LLM API成本增加

**风险等级**: 🔴 高

**描述**：
- 重新评分会增加LLM API调用
- 如果每次pipeline运行都触发大量重新评分，成本可能失控

**缓解措施**：
1. 设置每日/每月LLM调用预算上限
2. 使用更严格的触发阈值（减少不必要的重新评分）
3. 批量处理，减少API调用开销
4. 实现智能缓存（相似clusters复用评分结果）

**监控指标**：
- 每日LLM API调用次数
- 每日LLM API成本
- 每个pipeline运行的评分次数

### 风险2：评分不一致

**风险等级**: 🟡 中

**描述**：
- 同一个cluster在不同时间评分，可能得到不同的分数
- 用户可能会困惑：为什么同一个opportunity分数变了？

**缓解措施**：
1. 保留评分历史，可以看到变化趋势
2. 在opportunity中标注"上次评分时间"
3. 在Report中显示评分时间
4. 添加"评分变化原因"说明

**监控指标**：
- 评分方差（同一opportunity不同版本的分数差异）
- 用户反馈（是否对评分变化感到困惑）

### 风险3：数据库性能下降

**风险等级**: 🟡 中

**描述**：
- 新增3个表，可能增加查询时间
- `opportunity_versions`表会快速增长

**缓解措施**：
1. 添加适当的索引
2. 定期清理旧的评分版本（只保留最近N个版本）
3. 使用数据库查询优化（避免N+1查询）

**监控指标**：
- 数据库查询时间
- Pipeline各个stage的运行时间

### 风险4：Pipeline执行时间增加

**风险等级**: 🟢 低

**描述**：
- 新增Change Detection stage
- 重新评分会增加LLM API调用时间

**缓解措施**：
1. Change Detection使用纯SQL查询，应该很快（< 1秒）
2. 重新评分是并行的，可以控制并发数
3. 可以设置"最大重新评分数"上限

**监控指标**：
- Pipeline总运行时间
- 各stage运行时间占比

---

## 性能考虑

### 数据库查询优化

```sql
-- 1. 批量获取cluster指标（避免N+1查询）
WITH cluster_metrics AS (
    SELECT
        pe.cluster_id,
        COUNT(DISTINCT pe.id) as cluster_size,
        COUNT(DISTINCT fp.author) as unique_authors,
        COUNT(DISTINCT fp.subreddit) as cross_subreddit_count,
        MAX(pe.extracted_at) as latest_event_extracted_at
    FROM pain_events pe
    JOIN filtered_posts fp ON pe.post_id = fp.id
    WHERE pe.cluster_id IN (1, 2, 3, ...)  -- 批量查询
    GROUP BY pe.cluster_id
)
SELECT * FROM cluster_metrics;

-- 2. 使用索引加速查询
CREATE INDEX idx_pain_events_cluster_id
    ON pain_events(cluster_id);
CREATE INDEX idx_opportunities_cluster_id
    ON opportunities(cluster_id);
```

### LLM API调用优化

```python
# 1. 批量处理（减少API调用开销）
async def score_batch(opportunities: List[Dict]) -> List[Dict]:
    """批量评分，并发执行"""
    tasks = [
        llm_client.score_viability(opp)
        for opp in opportunities
    ]
    results = await asyncio.gather(*tasks)
    return results

# 2. 智能去重（相似clusters复用评分）
def is_similar_cluster(cluster1: Dict, cluster2: Dict) -> bool:
    """判断两个clusters是否相似（可以复用评分）"""
    # 基于cluster_name和centroid_summary的相似度
    similarity = calculate_text_similarity(
        cluster1['cluster_name'],
        cluster2['cluster_name']
    )
    return similarity > 0.9
```

### 并发控制

```python
# 3. 限制并发数（避免API限流）
MAX_CONCURRENT_LLM_CALLS = 5

async def score_with_rate_limit(opportunities: List[Dict]):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

    async def score_one(opp):
        async with semaphore:
            return await llm_client.score_viability(opp)

    tasks = [score_one(opp) for opp in opportunities]
    return await asyncio.gather(*tasks)
```

### 缓存策略

```python
# 4. 缓存cluster快照（减少重复计算）
from functools import lru_cache

@lru_cache(maxsize=128)
def get_cluster_metrics(cluster_id: int, snapshot_time: str) -> Dict:
    """获取cluster指标（带缓存）"""
    return db._calculate_cluster_metrics_uncached(cluster_id)
```

---

## 配置示例

### 完整的配置文件

```yaml
# config/thresholds.yaml (完整版)

# ... 现有配置 ...

# 显著变化检测阈值（新增）
significant_change_thresholds:
  # 新增events触发条件
  min_new_events: 5
  min_new_events_ratio: 0.1

  # 新增作者触发条件
  min_new_authors: 3

  # 跨源验证触发条件
  min_cross_subreddit_delta: 2

  # 时间触发条件
  min_days_since_last_score: 7

  # 周期性全量更新
  periodic_full_rescore_days: 30

# 增量评分配置（新增）
incremental_scoring:
  enabled: true

  # 是否自动触发重新评分
  auto_trigger_enabled: true

  # 每次pipeline运行最大重新评分数
  max_rescores_per_run: 10

  # 是否保留评分历史
  keep_scoring_history: true

  # 保留多少个历史版本
  max_history_versions: 5

  # 新clusters首次评分的宽松filtering规则
  new_cluster_filtering_override:
    min_cluster_size: 3
    min_unique_authors: 2
    min_cross_subreddit_count: 1
    min_avg_frequency_score: 4.0

# Decision shortlist配置（修改）
decision_shortlist:
  # 新增：新鲜度权重
  freshness:
    enabled: true
    weights:
      last_24h: 1.5      # 最近24小时评分的，权重×1.5
      last_3_days: 1.2   # 最近3天评分的，权重×1.2
      last_7_days: 1.0   # 最近7天评分的，权重×1.0
      older: 0.8         # 更早的，权重×0.8

  # 原有配置（保持不变）
  min_viability_score: 6.0
  min_cluster_size: 4
  min_trust_level: 0.5
  # ...
```

---

## 使用示例

### 示例1：自动增量更新

```bash
# 运行完整pipeline（自动检测并重新评分显著变化的clusters）
python pain_point_analyzer.py --stage full

# 日志输出：
# INFO: Detected 3 clusters with significant changes
# INFO:   - Cluster 5: Added 62 new events (5.9% increase)
# INFO:   - Cluster 26: Added 16 new events (114% increase)
# INFO:   - Cluster 11: Added 11 new events (26.8% increase)
# INFO: Created scoring batch: batch_20260104_122553
# INFO: Re-scoring 3 opportunities (skipping filtering for updates)
# INFO:   Opportunity 5: 8.31 → 8.45 (↑ 0.14)
# INFO:   Opportunity 26: 7.67 → 7.82 (↑ 0.15)
# INFO:   Opportunity 11: 7.27 → 7.35 (↑ 0.08)
```

### 示例2：手动触发重新评分

```bash
# 重新评分指定的cluster
python pain_point_analyzer.py --rescore 5

# 日志输出：
# INFO: Manual re-scoring triggered for cluster 5
# INFO: Cluster size: 1107 events
# INFO: Previous score: 8.31 (scored on 2025-12-31)
# INFO: Re-scoring...
# INFO: New score: 8.45 (↑ 0.14)
# INFO: Saved as version 2
```

### 示例3：查看评分历史

```bash
# 查看某个opportunity的评分历史
python -m utils.opportunity_history --opportunity-id 5

# 输出：
# Opportunity: LifeSpark (ID: 5)
#
# Version 2 (Current):
#   Score: 8.45
#   Cluster Size: 1107
#   Scored At: 2026-01-04 12:30:00
#   Change Reason: Added 62 new events
#
# Version 1:
#   Score: 8.31
#   Cluster Size: 1045
#   Scored At: 2025-12-31 12:09:36
#   Change Reason: Initial scoring
```

### 示例4：自定义触发阈值

```bash
# 使用更宽松的触发阈值
python pain_point_analyzer.py \
    --stage full \
    --min-new-events 3 \
    --min-new-events-ratio 0.05

# 日志输出：
# INFO: Using custom thresholds: min_new_events=3, min_new_events_ratio=0.05
# INFO: Detected 8 clusters with significant changes (with custom thresholds)
# ...
```

---

## 总结

### 核心设计原则

1. **渐进式增强**: 在现有架构上增量改进，不重写整个pipeline
2. **数据驱动**: 基于真实数据分析设计触发条件
3. **成本可控**: 通过阈值和批次控制LLM调用成本
4. **可观测性**: 保留评分历史，便于分析和调试
5. **向后兼容**: 不破坏现有功能，新功能可选启用

### 预期效果

**问题解决**：
- ✅ Clusters获得新events后，会自动触发重新评分
- ✅ 新创建的小clusters有机会被LLM评分（宽松filtering）
- ✅ Decision shortlist能反映最新的cluster状态

**性能影响**：
- ⏱️ Pipeline运行时间增加：估计10-20%（主要是新增stage和LLM调用）
- 💾 数据库大小增加：每个opportunity约增加5-10个版本记录/年
- 💰 LLM API成本增加：估计10-30%（取决于重新评分频率）

**下一步**：
1. Review并批准此设计文档
2. 开始Phase 1: 数据模型实现
3. 每个Phase完成后进行review和调整

---

**文档版本**: 1.0
**最后更新**: 2026-01-04
**作者**: Claude (UltraThink Mode)
