# Phase 5-6 开发指南 (Development Guide)

**文档版本**: v1.1
**创建日期**: 2026-01-13
**最后更新**: 2026-01-15
**适用分支**: `feat-phase5`
**目标读者**: 后端工程师

**更新记录**:
- v1.1 (2026-01-15): Phase 5 完成，添加pickle反序列化修复说明
- v1.0 (2026-01-13): 初始版本

---

## 📋 目录

1. [项目背景](#项目背景)
2. [Phase 5: Pipeline集成](#phase-5-pipeline集成)
3. [Phase 6: 性能优化](#phase-6-性能优化)
4. [验收标准](#验收标准)
5. [测试指南](#测试指南)
6. [注意事项](#注意事项)
7. [回滚计划](#回滚计划)

---

## 项目背景

### 已完成工作 (Phase 1-4)

✅ **Phase 1**: 数据库Schema迁移
- 添加lifecycle字段到`pain_events`表
- 支持'active', 'orphan', 'archived'状态

✅ **Phase 2**: Chroma向量数据库集成
- 2242 embeddings迁移完成
- 本地存储: `data/chroma_db/` (9.8MB)

✅ **Phase 3**: DynamicClusterUpdater实现
- 实时cluster更新逻辑
- 自动合并和创建clusters

✅ **Phase 4**: Lifecycle清理系统
- 14天自动删除orphans
- 90天归档inactive clusters

### 测试结果

- ✅ Chroma性能: **1.9ms/query, 514 qps**
- ✅ 数据一致性: **100%** (SQLite ↔ Chroma)
- ✅ Dynamic clustering: **5/5** events成功clustered
- ✅ Retention rate: **65.5%** (自动识别有价值pattern)

---

## Phase 5: Pipeline集成

### 状态: ✅ 已完成 (2026-01-15)

### 目标

将Phase 1-4的组件集成到主pipeline中，替换旧的静态聚类逻辑。

### 当前Pipeline架构

```
run_pipeline.py
├── Stage 1: Fetch (fetch.py)         ← 无需修改
├── Stage 2: Filter (filter_signal.py) ← 无需修改
├── Stage 3: Extract (extract_pain.py) ← 无需修改
├── Stage 4: Embed (embed.py)         ← ✅ 已修改为使用Chroma
├── Stage 5: Cluster (cluster.py)     ← ✅ 已替换为DynamicClusterUpdater
├── Stage 6: Map (map_opportunity.py)  ← 无需修改
├── Stage 7: Score (score_viability.py) ← 无需修改
├── Stage 8: Decision (decision_shortlist.py) ← 无需修改
└── Stage 9: Lifecycle Cleanup        ← ✅ 已添加
```

### 实施记录

**实施日期**: 2026-01-15
**分支**: `feat-phase5`
**代码修改**: 139行新增，16行删除

**关键发现与修复**:

在集成过程中发现embedding向量存储方式问题：
- **问题**: `pain_embeddings` 表中的 `embedding_vector` 字段存储的是 **pickle 序列化的 BLOB**
- **原错误**: `Collection expecting embedding with dimension of 1024, got 9234`
- **解决方案**: 在 `run_stage_cluster` 方法中添加 pickle 反序列化逻辑
- **修复位置**: run_pipeline.py:389-399

### 任务清单

#### 5.1 更新run_pipeline.py

**文件**: `run_pipeline.py`

**目标**: 替换Stage 5的cluster逻辑

**当前代码** (约347-381行):
```python
def run_stage_cluster(self, limit_events: Optional[int] = None, process_all: bool = False):
    """阶段5: 聚类"""
    logger.info("=" * 50)
    logger.info("STAGE 5: Clustering pain events")
    logger.info("=" * 50)

    if self.enable_monitoring:
        performance_monitor.start_stage("cluster")

    try:
        clusterer = PainEventClusterer()  # ← 旧逻辑

        # 如果 process_all=True 且未指定 limit，则处理所有数据（设置为大数值）
        if process_all and limit_events is None:
            limit_events = 1000000  # 处理所有数据
        elif limit_events is None:
            limit_events = 200

        result = clusterer.cluster_pain_events(limit=limit_events)  # ← 旧方法

        # ... 其余代码
```

**新代码**:
```python
def run_stage_cluster(self, limit_events: Optional[int] = None, process_all: bool = False):
    """阶段5: 动态聚类更新 (Dynamic Clustering)"""
    logger.info("=" * 50)
    logger.info("STAGE 5: Dynamic Clustering (Real-time)")
    logger.info("=" * 50)

    if self.enable_monitoring:
        performance_monitor.start_stage("cluster")

    try:
        from pipeline.dynamic_cluster import DynamicClusterUpdater  # ← 导入新的

        # 初始化动态聚类器
        clusterer = DynamicClusterUpdater()

        # 获取需要处理的pain_events (新增的或unclustered的)
        with db.get_connection("pain") as conn:
            # 策略：处理所有未clustered的events + 最近的events (重新计算)
            if process_all and limit_events is None:
                # 处理所有unclustered events
                cursor = conn.execute("""
                    SELECT pe.*, em.embedding_vector
                    FROM pain_events pe
                    JOIN pain_embeddings em ON pe.id = em.pain_event_id
                    WHERE pe.cluster_id IS NULL
                    ORDER BY pe.extracted_at DESC
                """)
                new_events = [dict(row) for row in cursor.fetchall()]
            else:
                # 限制处理数量
                limit = limit_events if limit_events else 200
                cursor = conn.execute("""
                    SELECT pe.*, em.embedding_vector
                    FROM pain_events pe
                    JOIN pain_embeddings em ON pe.id = em.pain_event_id
                    WHERE pe.cluster_id IS NULL
                    ORDER BY pe.extracted_at DESC
                    LIMIT ?
                """, (limit,))
                new_events = [dict(row) for row in cursor.fetchall()]

        logger.info(f"Found {len(new_events)} events to process")

        if not new_events:
            logger.info("No new events to cluster")
            result = {
                'clusters_created': 0,
                'clusters_updated': 0,
                'events_processed': 0
            }
        else:
            # 使用DynamicClusterUpdater处理
            stats = clusterer.process_new_pain_events(new_events)

            result = {
                'clusters_created': stats['new_clusters_created'],
                'clusters_updated': stats['existing_clusters_updated'],
                'events_processed': stats['total_events_processed']
            }

        self.stats["stages_completed"].append("cluster")
        self.stats["stage_results"]["cluster"] = result

        if self.enable_monitoring:
            # 使用events_processed作为处理数量
            performance_monitor.end_stage("cluster", result.get('events_processed', 0))

        logger.info(f"✅ Stage 5 completed:")
        logger.info(f"   Events processed: {result.get('events_processed', 0)}")
        logger.info(f"   New clusters: {result.get('clusters_created', 0)}")
        logger.info(f"   Updated clusters: {result.get('clusters_updated', 0)}")
        return result

    except Exception as e:
        logger.error(f"❌ Stage 5 failed: {e}")
        self.stats["stages_failed"].append("cluster")
        if self.enable_monitoring:
            performance_monitor.end_stage("cluster", 0)
        raise
```

**关键变更**:
1. 导入`DynamicClusterUpdater`而非`PainEventClusterer`
2. 查询逻辑改为只获取`cluster_id IS NULL`的events
3. 调用`process_new_pain_events()`而非`cluster_pain_events()`
4. 返回值适配新的统计格式

---

#### 5.2 添加Lifecycle Cleanup Stage

**文件**: `run_pipeline.py`

**目标**: 在pipeline最后添加lifecycle cleanup阶段

**位置**: 在`run_stage_decision_shortlist`之后添加新方法

**新代码**:
```python
def run_stage_lifecycle_cleanup(self, orphan_age_days: int = 14, cluster_inactivity_days: int = 90) -> Dict[str, Any]:
    """阶段9: 生命周期清理

    Args:
        orphan_age_days: 删除多少天前的orphans (默认14天)
        cluster_inactivity_days: 归档多少天无活动的clusters (默认90天)
    """
    logger.info("=" * 50)
    logger.info("STAGE 9: Lifecycle Cleanup")
    logger.info("=" * 50)

    if self.enable_monitoring:
        performance_monitor.start_stage("lifecycle_cleanup")

    try:
        # 导入cleanup函数
        from scripts.lifecycle_cleanup import (
            mark_orphan_events,
            cleanup_old_orphans,
            get_lifecycle_statistics
        )

        # Step 1: 标记orphans
        logger.info("Step 1: Marking orphan events...")
        marked_count = mark_orphan_events()
        logger.info(f"   Marked {marked_count} events as orphans")

        # Step 2: 清理旧orphans
        logger.info(f"Step 2: Cleaning up orphans older than {orphan_age_days} days...")
        deleted_count = cleanup_old_orphans(
            db_path="data/wise_collection.db",
            orphan_age_days=orphan_age_days
        )
        logger.info(f"   Deleted {deleted_count} old orphans")

        # Step 3: 获取统计信息
        stats = get_lifecycle_statistics()

        result = {
            'orphans_marked': marked_count,
            'orphans_deleted': deleted_count,
            'final_stats': stats
        }

        self.stats["stages_completed"].append("lifecycle_cleanup")
        self.stats["stage_results"]["lifecycle_cleanup"] = result

        if self.enable_monitoring:
            performance_monitor.end_stage("lifecycle_cleanup", deleted_count)

        logger.info("✅ Stage 9 completed:")
        logger.info(f"   Active events: {stats['active_events']}")
        logger.info(f"   Orphan events: {stats['orphan_events']}")
        logger.info(f"   Retention rate: {stats['retention_rate']:.1f}%")

        return result

    except Exception as e:
        logger.error(f"❌ Stage 9 failed: {e}")
        self.stats["stages_failed"].append("lifecycle_cleanup")
        if self.enable_monitoring:
            performance_monitor.end_stage("lifecycle_cleanup", 0)
        raise
```

**修改`run_full_pipeline`方法**:

在`stages`列表中添加新阶段 (约621-630行):

```python
stages = [
    ("fetch", lambda: self.run_stage_fetch(limit_sources, fetch_sources)),
    ("filter", lambda: self.run_stage_filter(limit_posts, process_all)),
    ("extract", lambda: self.run_stage_extract(limit_posts, process_all)),
    ("embed", lambda: self.run_stage_embed(limit_events, process_all)),
    ("cluster", lambda: self.run_stage_cluster(limit_events, process_all)),
    ("map_opportunities", lambda: self.run_stage_map_opportunities(limit_clusters, process_all)),
    ("score", lambda: self.run_stage_score(limit_opportunities, process_all)),
    ("shortlist", lambda: self.run_stage_decision_shortlist()),
    ("lifecycle_cleanup", lambda: self.run_stage_lifecycle_cleanup())  # ← 新增
]
```

**修改`run_single_stage`方法**:

在`stage_map`字典中添加新stage (约655-670行):

```python
stage_map = {
    "fetch": lambda: self.run_stage_fetch(kwargs.get("limit_sources"), kwargs.get("sources")),
    "filter": lambda: self.run_stage_filter(
        kwargs.get("limit_posts"),
        process_all
    ),
    "extract": lambda: self.run_stage_extract(
        kwargs.get("limit_posts"),
        process_all
    ),
    "embed": lambda: self.run_stage_embed(kwargs.get("limit_events"), process_all),
    "cluster": lambda: self.run_stage_cluster(kwargs.get("limit_events"), process_all),
    "map": lambda: self.run_stage_map_opportunities(kwargs.get("limit_clusters"), process_all),
    "score": lambda: self.run_stage_score(kwargs.get("limit_opportunities"), process_all),
    "shortlist": lambda: self.run_stage_decision_shortlist(),
    "lifecycle_cleanup": lambda: self.run_stage_lifecycle_cleanup()  # ← 新增
}
```

**修改`main`函数的argument parser** (约916-917行):

```python
parser.add_argument("--stage", choices=[
    "fetch", "filter", "extract", "embed", "cluster",
    "map", "score", "shortlist", "lifecycle_cleanup", "all"  # ← 添加lifecycle_cleanup
], default="all", help="Which stage to run (default: all)")
```

---

#### 5.3 更新embed.py (已完成验证)

**状态**: ✅ 已在Phase 2完成

**确认事项**:
- [x] `embed.py`已修改为使用Chroma存储
- [x] `save_embedding()`方法已更新
- [x] `process_missing_embeddings()`已更新为查询Chroma

**无需额外修改**

---

### 验收标准 Phase 5

#### 功能验收

- [x] `python run_pipeline.py --stage cluster` 成功运行
- [x] `python run_pipeline.py --stage lifecycle_cleanup` 成功运行
- [x] `python run_pipeline.py --stage all` 完整pipeline成功
- [x] 新pain_events被正确clustered
- [x] Orphan events被正确标记和清理

#### 测试结果 (2026-01-15)

**Cluster Stage 测试 (20 events)**:
```
✅ Processed 20 pain events in 221.8s
✅ Events added to clusters: 17
✅ New clusters created: 1
✅ Existing clusters updated: 17
✅ Orphans marked: 2
```

**Lifecycle Cleanup Stage 测试**:
```
✅ Active events: 1489
✅ Orphan events: 2787
✅ Retention rate: 34.8%
```

**Pickel反序列化修复**:
- 问题: BLOB长度9234字节被误认为是embedding维度
- 修复: 添加 `pickle.loads()` 反序列化
- 验证: 20个events全部正确处理，无维度错误

#### 日志验证

运行pipeline后检查日志输出:

```bash
# 应该看到:
STAGE 5: Dynamic Clustering (Real-time)
Found X events to process
✅ Stage 5 completed:
   Events processed: X
   New clusters: Y
   Updated clusters: Z

STAGE 9: Lifecycle Cleanup
Step 1: Marking orphan events...
   Marked X events as orphans
Step 2: Cleaning up orphans older than 14 days...
   Deleted Y old orphans
✅ Stage 9 completed:
   Active events: X
   Orphan events: Y
   Retention rate: Z%
```

#### 数据库验证

```sql
-- 检查clusters被更新
SELECT COUNT(*) FROM clusters;  -- 数量应该增加或保持

-- 检查lifecycle状态正确
SELECT
    COUNT(*) FILTER (WHERE lifecycle_stage = 'active') as active,
    COUNT(*) FILTER (WHERE lifecycle_stage = 'orphan') as orphan
FROM pain_events;

-- 检查最新的events被处理
SELECT COUNT(*) FROM pain_events
WHERE extracted_at > datetime('now', '-1 day')
AND lifecycle_stage = 'active';
```

---

## Phase 6: 性能优化

### 目标

通过并行化和增量处理，将pipeline总运行时间控制在2小时以内。

### 性能基准

#### 当前性能 (Phase 4测试)

| Stage | 当前耗时 | 目标耗时 |
|-------|----------|----------|
| Fetch | 10 min | 10 min |
| Filter | 10 min | 10 min |
| Extract | 40 min | **8 min** ⚡ |
| Embed | 5 min | 5 min |
| Cluster | 20 min | **10 min** ⚡ |
| Map | 15 min | 15 min |
| Score | 15 min | 15 min |
| Decision | 5 min | 5 min |
| Cleanup | 1 min | 1 min |
| **总计** | **121 min** | **79 min** ✅ |

**优化潜力**: Extract和Cluster阶段有最大优化空间

---

### 任务清单

#### 6.1 并行化LLM调用 (Extract阶段)

**文件**: `pipeline/extract_pain.py`

**当前性能瓶颈**:
- 串行处理posts: 每个~2秒
- 100 posts = 200秒 ≈ 3.3分钟

**优化方案**: 使用`ThreadPoolExecutor`并行调用

**当前代码** (约100-150行):
```python
def extract_pain_from_posts_batch(
    self,
    posts: List[Dict[str, Any]],
    batch_size: int = 20
) -> int:
    """批量从帖子中提取痛点"""
    logger.info(f"Extracting pain from {len(posts)} posts")

    extracted_count = 0

    for i, post in enumerate(posts):
        if i % 10 == 0:
            logger.info(f"Processing {i}/{len(posts)} posts")

        # 提取单个帖子
        pain_events = self.extract_pain_from_post(post)

        if pain_events:
            extracted_count += len(pain_events)

        # 添加延迟避免API限制
        if i % batch_size == 0 and i > 0:
            time.sleep(1)

    return extracted_count
```

**优化后代码**:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

def extract_pain_from_posts_batch(
    self,
    posts: List[Dict[str, Any]],
    batch_size: int = 20,
    max_workers: int = 5  # ← 并发数
) -> int:
    """批量从帖子中提取痛点 (并行化版本)"""
    logger.info(f"Extracting pain from {len(posts)} posts (parallel, max_workers={max_workers})")

    extracted_count = 0
    failed_count = 0
    start_time = time.time()

    # 使用线程池并行处理
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_post = {
            executor.submit(self.extract_pain_from_post, post): post
            for post in posts
        }

        # 收集结果
        for i, future in enumerate(as_completed(future_to_post), 1):
            post = future_to_post[future]

            try:
                # 获取结果
                pain_events = future.result()

                if pain_events:
                    extracted_count += len(pain_events)

                # 进度日志
                if i % 10 == 0:
                    logger.info(f"Processed {i}/{len(posts)} posts, extracted: {extracted_count}")

            except Exception as e:
                logger.error(f"Failed to extract pain from post {post.get('id')}: {e}")
                failed_count += 1

    elapsed = time.time() - start_time
    logger.info(f"Extraction complete: {extracted_count} events from {len(posts)} posts")
    logger.info(f"Failed: {failed_count}, Time: {elapsed:.1f}s ({elapsed/len(posts):.1f}s per post)")

    return extracted_count
```

**注意事项**:
1. **max_workers设置**: 建议从5开始测试，逐步增加
2. **API限流**: 观察LLM API的rate limit错误
3. **内存使用**: 并发会增加内存占用
4. **错误处理**: 确保单个失败不影响整体

**测试方法**:
```bash
# 测试不同并发数
for workers in 3 5 8 10; do
    echo "Testing with max_workers=$workers"
    time python run_pipeline.py --stage extract --limit-posts 100
done
```

**预期效果**:
- 串行: 200秒 (100 posts × 2s)
- 并发(5 workers): 40秒 (200/5)
- **提升**: 5x

---

#### 6.2 增量处理 (所有Stage)

**目标**: 只处理自上次运行以来的新数据，而不是每次都处理全部。

**实现策略**: 使用时间戳过滤

##### 6.2.1 添加最后运行时间追踪

**文件**: `utils/db.py` 或新建 `utils/pipeline_state.py`

**新增代码**:
```python
class PipelineState:
    """Pipeline状态追踪"""

    def __init__(self, db_path: str = "data/wise_collection.db"):
        self.db_path = db_path
        self._init_state_table()

    def _init_state_table(self):
        """初始化state表"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_state (
                stage TEXT PRIMARY KEY,
                last_run_at TIMESTAMP,
                last_processed_count INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def get_last_run_time(self, stage: str) -> Optional[str]:
        """获取某stage最后运行时间"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT last_run_at FROM pipeline_state
            WHERE stage = ?
        """, (stage,))

        row = cursor.fetchone()
        conn.close()

        return row[0] if row else None

    def update_stage_run(
        self,
        stage: str,
        processed_count: int = 0
    ):
        """更新stage运行时间"""
        import sqlite3
        from datetime import datetime
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT OR REPLACE INTO pipeline_state (stage, last_run_at, last_processed_count, updated_at)
            VALUES (?, ?, ?, ?)
        """, (stage, now, processed_count, now))

        conn.commit()
        conn.close()


# 单例实例
_pipeline_state = None

def get_pipeline_state() -> PipelineState:
    global _pipeline_state
    if _pipeline_state is None:
        _pipeline_state = PipelineState()
    return _pipeline_state
```

##### 6.2.2 更新Filter阶段

**文件**: `run_pipeline.py`

**修改**:
```python
def run_stage_filter(self, limit_posts: Optional[int] = None, process_all: bool = False):
    """阶段2: 信号过滤 (Posts) - 增量处理版本"""
    logger.info("=" * 50)
    logger.info("STAGE 2: Filtering pain signals (Incremental)")
    logger.info("=" * 50)

    if self.enable_monitoring:
        performance_monitor.start_stage("filter")

    try:
        from utils.pipeline_state import get_pipeline_state

        # 获取上次运行时间
        last_run = get_pipeline_state().get_last_run_time("filter")
        if last_run:
            logger.info(f"Last run: {last_run}")
            logger.info("Processing posts collected since then...")

        filter = PainSignalFilter()

        # 获取未过滤的帖子 (增量)
        if process_all and limit_posts is None:
            limit_posts = 1000000
        elif limit_posts is None:
            limit_posts = 1000

        unfiltered_posts = db.get_unprocessed_posts(
            limit=limit_posts,
            since=last_run  # ← 新增参数：只获取新数据
        )

        # ... 处理逻辑 (保持不变)

        # 更新state
        saved_count = post_result['filtered']
        get_pipeline_state().update_stage_run("filter", saved_count)

        # ... 其余代码保持不变
```

**修改** `utils/db.py`:
```python
def get_unprocessed_posts(
    self,
    limit: int = 1000,
    since: Optional[str] = None  # ← 新增参数
) -> List[Dict]:
    """获取未处理的帖子

    Args:
        limit: 限制数量
        since: ISO格式时间戳，只获取此时间之后的posts
    """
    try:
        with self.get_connection("raw") as conn:
            if since:
                # 增量模式
                cursor = conn.execute("""
                    SELECT * FROM posts
                    WHERE collected_at > ?
                    AND id NOT IN (SELECT id FROM filtered_posts)
                    ORDER BY collected_at DESC
                    LIMIT ?
                """, (since, limit))
            else:
                # 全量模式
                cursor = conn.execute("""
                    SELECT * FROM posts
                    WHERE id NOT IN (SELECT id FROM filtered_posts)
                    ORDER BY collected_at DESC
                    LIMIT ?
                """, (limit,))

            return [dict(row) for row in cursor.fetchall()]

    except Exception as e:
        logger.error(f"Failed to get unprocessed posts: {e}")
        return []
```

##### 6.2.3 更新其他Stage

**Apply相同模式到**:
- `run_stage_extract`: 只处理自last_run以来的filtered_posts
- `run_stage_embed`: 只处理自last_run以来的pain_events
- `run_stage_cluster`: 只处理自last_run以来的unclustered_events

**示例 (Extract阶段)**:
```python
def run_stage_extract(self, limit_posts: Optional[int] = None, process_all: bool = False):
    """阶段3: 痛点抽取 - 增量处理版本"""
    # ...

    last_run = get_pipeline_state().get_last_run_time("extract")

    # 获取未提取的posts
    unextracted_posts = db.get_unextracted_posts(
        limit=limit_posts,
        since=last_run  # ← 新增
    )

    # ... 处理逻辑

    # 更新state
    get_pipeline_state().update_stage_run("extract", post_result['pain_events_saved'])
```

---

### 验收标准 Phase 6

#### 性能验收

运行完整pipeline并计时:

```bash
# 记录开始时间
start_time=$(date +%s)

# 运行pipeline (全量处理第一天，增量处理后续)
python run_pipeline.py --stage all --process-all

# 计算耗时
end_time=$(date +%s)
duration=$((end_time - start_time))
minutes=$((duration / 60))

echo "Pipeline completed in ${minutes} minutes"
```

**通过标准**:
- ✅ **首次运行** (process-all): < 150分钟
- ✅ **后续运行** (增量): < 90分钟
- ✅ **Extract阶段**: < 10分钟
- ✅ **Cluster阶段**: < 15分钟

#### 并发测试

```bash
# 测试不同并发配置
for workers in 3 5 8; do
    echo "=== Testing max_workers=$workers ==="
    time python run_pipeline.py --stage extract --limit-posts 100
    echo ""
done
```

选择性能最好且稳定的并发数。

#### 内存监控

```bash
# 监控内存使用
/usr/bin/time -v python run_pipeline.py --stage all --process-all

# 查看Maximum resident set size
# 应该 < 4GB
```

---

## 测试指南

### 单元测试

#### Test 1: Stage功能测试

```bash
# 测试单个stage
python run_pipeline.py --stage fetch --limit-sources 5
python run_pipeline.py --stage filter --limit-posts 10
python run_pipeline.py --stage extract --limit-posts 10
python run_pipeline.py --stage embed --limit-events 10
python run_pipeline.py --stage cluster
python run_pipeline.py --stage map --limit-clusters 5
python run_pipeline.py --stage score --limit-opportunities 10
python run_pipeline.py --stage shortlist
python run_pipeline.py --stage lifecycle_cleanup
```

#### Test 2: 增量处理测试

```bash
# 第一次运行 (全量)
python run_pipeline.py --stage all --process-all

# 第二次运行 (增量，应该很快)
python run_pipeline.py --stage all

# 检查是否跳过已处理数据
# 日志应该显示 "Processing posts collected since [last_run]"
```

#### Test 3: 并发性能测试

```bash
# 测试不同并发数
for workers in 3 5 8 10; do
    echo "=== max_workers=$workers ==="
    time python run_pipeline.py --stage extract --limit-posts 50
done
```

### 集成测试

#### Test 4: 完整Pipeline测试

```bash
# 完整运行 (记录时间)
time python run_pipeline.py --stage all --process-all

# 检查结果
sqlite3 data/wise_collection.db <<EOF
SELECT
    (SELECT COUNT(*) FROM posts) as raw_posts,
    (SELECT COUNT(*) FROM filtered_posts) as filtered,
    (SELECT COUNT(*) FROM pain_events) as pain_events,
    (SELECT COUNT(*) FROM clusters) as clusters,
    (SELECT COUNT(*) FROM opportunities) as opportunities;
EOF
```

#### Test 5: 数据一致性验证

```bash
# 运行测试套件
python tests/test_01_chroma_client.py
python tests/test_02_chroma_similarity.py
python tests/test_05_data_consistency.py

# 应该全部通过
```

### 性能测试

#### Test 6: 2小时目标验证

```bash
# 监控资源使用
/usr/bin/time -v python run_pipeline.py --stage all --process-all

# 检查输出:
# - Elapsed (wall clock) time: 应该 < 7200 seconds (2小时)
# - Maximum resident set size: 应该 < 4GB
# - Percent of CPU this job got: 应该 > 400% (多核利用)
```

---

## 注意事项

### 1. LLM API限流

**问题**: 并发调用可能触发rate limit

**解决方案**:
```python
# 在extract_pain.py中添加重试逻辑
import time
from functools import wraps

def retry_on_rate_limit(max_retries=3, delay=5):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except RateLimitError as e:
                    if attempt < max_retries - 1:
                        wait_time = delay * (2 ** attempt)  # 指数退避
                        logger.warning(f"Rate limit hit, waiting {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        raise
            return wrapper
        return decorator

# 使用
@retry_on_rate_limit(max_retries=3, delay=5)
def extract_pain_from_post(self, post):
    # ... original code
```

### 2. 内存管理

**问题**: 并发处理可能导致内存溢出

**解决方案**:
```python
# 批量处理，避免一次性加载太多数据
def process_in_batches(items, batch_size=50):
    """分批处理"""
    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        yield batch

# 使用
for batch in process_in_batches(all_posts, batch_size=50):
    results = extract_pain_from_posts_batch(batch, max_workers=5)
    # 释放内存
    del batch
    import gc
    gc.collect()
```

### 3. 数据库连接管理

**问题**: 并发环境下可能导致连接泄漏

**解决方案**:
```python
# 确保使用context manager
with db.get_connection("pain") as conn:
    # 操作
    cursor = conn.execute(...)
    results = cursor.fetchall()
# 连接自动关闭
```

### 4. Chroma并发写入

**问题**: 多线程同时写入Chroma可能冲突

**解决方案**:
```python
# 在embed.py中添加线程锁
from threading import Lock

class PainEventEmbedder:
    def __init__(self):
        self.chroma_lock = Lock()  # ← 保护Chroma写入

    def save_embedding(self, pain_event_id, embedding, pain_event_data=None):
        with self.chroma_lock:  # ← 加锁
            chroma.add_embeddings(...)
```

### 5. 错误恢复

**问题**: Pipeline中断后如何恢复？

**解决方案**:
- ✅ 增量处理自动支持恢复
- ✅ 使用`--stage`参数单独运行失败的stage
- ✅ 检查`pipeline_state`表确定最后成功点

```bash
# 查看各stage最后运行时间
sqlite3 data/wise_collection.db "SELECT * FROM pipeline_state"

# 从失败点继续
python run_pipeline.py --stage <failed_stage>
```

---

## 回滚计划

### 如果Phase 5失败

**症状**: 新pipeline无法正常运行

**回滚步骤**:
```bash
# 1. 切换回旧代码
git checkout main
git pull origin main

# 2. 恢复数据库 (如果schema被修改)
cp data/wise_collection.db.backup data/wise_collection.db

# 3. 删除Chroma数据 (可选)
rm -rf data/chroma_db/

# 4. 运行旧pipeline验证
python run_pipeline.py --stage all
```

### 如果Phase 6性能不达标

**症状**: Pipeline运行时间超过2小时

**回退步骤**:
```bash
# 1. 减少并发数
# 修改 extract_pain.py: max_workers = 3

# 2. 禁用增量处理 (使用全量)
python run_pipeline.py --stage all --process-all

# 3. 分阶段运行
python run_pipeline.py --stage fetch
python run_pipeline.py --stage filter
python run_pipeline.py --stage extract
python run_pipeline.py --stage embed
python run_pipeline.py --stage cluster
# ... etc
```

### 数据回滚

**如果需要回滚数据修改**:

```bash
# 1. 停止pipeline
pkill -f run_pipeline.py

# 2. 备份当前数据库
cp data/wise_collection.db data/wise_collection.db.before_rollback

# 3. 恢复到之前版本
cp data/wise_collection.db.backup_YYYYMMDD data/wise_collection.db

# 4. 恢复Chroma (如有备份)
tar -xzf chroma_backup_YYYYMMDD.tar.gz -C data/
```

---

## 附录

### A. 环境要求

```
Python: >= 3.10
Dependencies:
  - chromadb >= 0.4.0
  - openai (或兼容的LLM API)
  - sqlite3 (built-in)
```

### B. 配置文件

检查以下配置文件存在且正确:

- `config/llm.yaml`: LLM API配置
- `config/thresholds.yaml`: 聚类阈值配置

### C. 故障排查

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| ImportError: No module named 'chromadb' | chromadb未安装 | `pip install chromadb` |
| "Collection expecting dimension...got 9234" | **Pickle BLOB未反序列化** | 在查询后添加 `pickle.loads()` 反序列化embedding_vector |
| "Collection expecting dimension..." | Embedding维度不匹配 | 检查embedding_model配置 |
| Database is locked | 并发写入冲突 | 使用WAL模式: `PRAGMA journal_mode=WAL` |
| Rate limit exceeded | LLM API调用过快 | 减少max_workers |
| Out of memory | 并发数太高 | 减少batch_size或max_workers |

**Pickle反序列化问题详解** (Phase 5已修复):

在Phase 5集成中发现，`pain_embeddings` 表中的 `embedding_vector` 存储为pickle序列化的BLOB。如果直接查询并传给Chroma，会报错：

```
Collection expecting embedding with dimension of 1024, got 9234
```

**修复方法** (已在run_pipeline.py:389-399实现):
```python
import pickle

# 查询后需要反序列化
for row in rows:
    event = dict(row)
    if event.get('embedding_vector'):
        event['embedding_vector'] = pickle.loads(event['embedding_vector'])
```

### D. 监控命令

```bash
# 实时查看日志
tail -f logs/pipeline.log

# 监控数据库大小
watch -n 60 'du -sh data/wise_collection.db data/chroma_db/'

# 监控进程
ps aux | grep run_pipeline

# 系统资源
htop
```

---

## 总结

### Phase 5 核心任务 ✅ 已完成
1. ✅ 更新`run_pipeline.py`的`run_stage_cluster`方法
2. ✅ 添加`run_stage_lifecycle_cleanup`方法
3. ✅ 更新`run_full_pipeline`和`run_single_stage`
4. ✅ 更新argument parser
5. ✅ 修复pickle反序列化问题

**交付物**:
- [x] 更新的`run_pipeline.py` (139行新增，16行删除)
- [x] 测试报告（20 events cluster测试通过）
- [x] Lifecycle cleanup测试通过

### Phase 6 核心任务 ⏳ 待实施
1. [ ] 并行化LLM调用 (extract_pain.py)
2. [ ] 添加PipelineState追踪
3. [ ] 实现增量处理 (所有stage)
4. [ ] 性能测试和调优

**交付物**:
- [ ] 更新的`extract_pain.py`
- [ ] 新增的`utils/pipeline_state.py`
- [ ] 更新的`utils/db.py` (新增since参数)
- [ ] 性能对比报告

---

**文档作者**: Claude Sonnet 4.5
**最后更新**: 2026-01-15
**版本**: v1.1
