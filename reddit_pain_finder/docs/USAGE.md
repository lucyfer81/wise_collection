# Reddit Pain Point Finder - 使用指南

本文档说明如何运行Reddit痛点发现pipeline的不同模式。

---

## 📋 目录

1. [快速开始](#快速开始)
2. [运行模式](#运行模式)
3. [命令参数](#命令参数)
4. [常用场景](#常用场景)
5. [性能优化](#性能优化)
6. [故障排查](#故障排查)

---

## 快速开始

### 首次使用

```bash
# 首次运行 - 处理所有数据（全量模式）
python run_pipeline.py --stage all --process-all
```

这会运行完整的9个stage，可能需要30-60分钟。

---

## 运行模式

### 1. 全量模式 (Full Processing)

**用途**: 处理所有数据，忽略之前的运行状态

```bash
# 方式1: 使用 --process-all 标志
python run_pipeline.py --stage all --process-all

# 方式2: 重置pipeline状态后运行
python -m utils.pipeline_state --reset all
python run_pipeline.py --stage all
```

**何时使用**:
- 首次运行
- 需要重新处理所有数据
- 数据库已重置

---

### 2. 增量模式 (Incremental Processing)

**用途**: 只处理自上次运行以来的新数据（默认模式）

```bash
# 运行所有stages（自动增量）
python run_pipeline.py --stage all

# 或省略 --stage all（默认就是all）
python run_pipeline.py
```

**工作原理**:
- Pipeline会读取上次运行时间
- 只处理该时间之后的新数据
- 大幅减少运行时间

**性能对比**:
```
全量模式: 48分钟 (处理2604个posts)
增量模式: 5-10分钟 (处理100-200个新posts)
```

---

### 3. 单Stage模式

**用途**: 只运行特定的stage

```bash
# 只运行Filter stage
python run_pipeline.py --stage filter

# 只运行Extract stage
python run_pipeline.py --stage extract

# 只运行Cluster stage
python run_pipeline.py --stage cluster

# 只运行Lifecycle Cleanup
python run_pipeline.py --stage lifecycle_cleanup
```

**可用的stages**:
- `fetch` - 获取原始数据
- `filter` - 过滤信号
- `extract` - 提取痛点
- `embed` - 生成向量
- `cluster` - 聚类分析
- `map` - 映射机会
- `score` - 可行性评分
- `shortlist` - 决策清单
- `lifecycle_cleanup` - 生命周期清理
- `all` - 运行所有stages

---

### 4. 限制数据量模式

**用途**: 测试或快速验证，只处理少量数据

```bash
# 只处理前100个posts
python run_pipeline.py --stage all --limit-posts 100

# 只处理前20个events
python run_pipeline.py --stage extract --limit-posts 20

# 只处理前10个clusters
python run_pipeline.py --stage map --limit-clusters 10
```

**参数说明**:
- `--limit-posts N`: 限制处理的帖子数量
- `--limit-events N`: 限制处理的events数量
- `--limit-clusters N`: 限制处理的clusters数量
- `--limit-opportunities N`: 限制处理的机会数量
- `--limit-sources N`: 限制数据源数量

---

## 命令参数

### 基础参数

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `--stage` | 运行哪个stage | `all` | `--stage extract` |
| `--process-all` | 全量处理所有数据 | False | `--process-all` |
| `--enable-monitoring` | 启用性能监控 | False | `--enable-monitoring` |

### 数据限制参数

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `--limit-posts` | 限制帖子数量 | 100/200 | `--limit-posts 50` |
| `--limit-events` | 限制events数量 | 200 | `--limit-events 100` |
| `--limit-clusters` | 限制clusters数量 | 20 | `--limit-clusters 10` |
| `--limit-sources` | 限制数据源数量 | None | `--limit-sources 5` |

---

## 常用场景

### 场景1: 日常数据更新

**目标**: 处理今天的新数据

```bash
# 增量运行（默认）
python run_pipeline.py
```

**预期**: 5-15分钟完成

---

### 场景2: 首次设置

**目标**: 初始化系统，处理所有历史数据

```bash
# 全量运行
python run_pipeline.py --stage all --process-all
```

**预期**: 30-60分钟完成

---

### 场景3: 重新聚类

**目标**: 重新运行聚类分析（使用新的算法参数）

```bash
# 1. 重置cluster状态
python -m utils.pipeline_state --reset cluster

# 2. 只运行cluster及之后的stages
python run_pipeline.py --stage cluster
python run_pipeline.py --stage map
python run_pipeline.py --stage score
python run_pipeline.py --stage shortlist
```

---

### 场景4: 快速测试

**目标**: 快速验证系统是否正常工作

```bash
# 只处理少量数据
python run_pipeline.py --stage all --limit-posts 10
```

**预期**: 2-5分钟完成

---

### 场景5: 单独更新某个stage

**目标**: 只更新决策报告（不需要重新提取数据）

```bash
# 只运行决策shortlist生成
python run_pipeline.py --stage shortlist
```

---

## 性能优化

### 并行化配置

Extract阶段使用并行处理（`max_workers=8`），可在代码中调整：

```python
# pipeline/extract_pain.py
extractor.process_unextracted_posts(
    limit=100,
    max_workers=8  # 可调整为 3, 5, 8, 10
)
```

**建议值**:
- 保守: 3-5 (稳定，适合低配服务器)
- 推荐: 8 (平衡性能和稳定性)
- 激进: 10 (更快，可能触发API限制)

---

### 增量处理优化

增量处理会自动跳过已处理数据：

```bash
# 第一次: 48分钟 (处理2604 posts)
python run_pipeline.py --stage all --process-all

# 第二次: 5分钟 (处理100新posts)
python run_pipeline.py --stage all

# 第三次: 5分钟 (处理80新posts)
python run_pipeline.py --stage all
```

---

## Pipeline状态管理

### 查看状态

```bash
# 查看所有stages的最后运行时间
python -m utils.pipeline_state --status
```

输出示例：
```
=== Pipeline Stage Status ===

cluster:
  Last run: 2026-01-15T15:17:41
  Processed: 753 items

extract:
  Last run: 2026-01-15T15:02:59
  Processed: 219 items

filter:
  Last run: 2026-01-15T14:48:05
  Processed: 0 items
```

---

### 重置状态

```bash
# 重置单个stage（强制全量处理该stage）
python -m utils.pipeline_state --reset extract

# 重置所有stages
python -m utils.pipeline_state --reset all
```

**何时需要重置**:
- 修改了stage的处理逻辑
- 想重新验证结果
- 数据库修复后

---

## 输出文件

运行完成后会生成以下文件：

### 主要结果文件

```
pipeline_results_YYYYMMDD_HHMMSS.json
├── 完整的pipeline运行结果
├── 所有stages的统计数据
└── 处理的数据详情

reports/decision_shortlist_YYYYMMDD_HHMMSS.md
├── 人类可读的决策报告
└── Top机会的详细分析

data/decision_shortlist_YYYYMMDD_HHMMSS.json
├── 结构化的机会数据
└── 可用于后续分析
```

---

## 故障排查

### 问题1: "No module named 'xxx'"

**解决**:
```bash
# 安装依赖
pip install -r requirements.txt
```

---

### 问题2: Database is locked

**原因**: 并发写入冲突（已通过WAL模式和线程锁修复）

**解决**:
```bash
# 如果仍然出现，检查是否有其他进程在运行
ps aux | grep run_pipeline

# 终止其他进程
pkill -f run_pipeline
```

---

### 问题3: API rate limit exceeded

**原因**: LLM API调用过快

**解决**:
```bash
# 降低并发数
# 编辑 pipeline/extract_pain.py
# 将 max_workers 从 8 降至 5
```

---

### 问题4: 增量模式处理了0个数据

**可能原因**:
1. 没有新数据（正常）
2. Pipeline状态未更新

**验证**:
```bash
# 检查最后运行时间
python -m utils.pipeline_state --status

# 检查是否有新数据
python -c "
from utils.db import db
posts = db.get_unprocessed_posts(limit=10)
print(f'未处理posts: {len(posts)}')
"
```

---

### 问题5: 某个stage失败

**解决**:
```bash
# 1. 查看错误日志
tail -100 error.txt

# 2. 单独运行失败的stage
python run_pipeline.py --stage <failed_stage> --limit-posts 10

# 3. 如果需要，重置该stage状态
python -m utils.pipeline_state --reset <failed_stage>

# 4. 重新运行
python run_pipeline.py --stage <failed_stage>
```

---

## 高级用法

### 自定义数据源

```bash
# 只从特定subreddit获取数据
python -c "
from pipeline.fetch import RedditFetcher
fetcher = RedditFetcher()
fetcher.fetch_subreddit('python', limit_posts=100)
"
```

---

### 导出特定数据

```bash
# 导出所有clusters
python -c "
from utils.db import db
import json
clusters = db.get_all_clusters()
with open('clusters.json', 'w') as f:
    json.dump(clusters, f, indent=2)
"
```

---

## 监控和日志

### 查看实时日志

```bash
# 监控日志输出
tail -f error.txt
```

### 查看性能统计

```bash
# 运行时启用监控
python run_pipeline.py --stage all --enable-monitoring
```

---

## 最佳实践

### 1. 定期运行

```bash
# 每天运行一次（增量模式）
# 添加到crontab
0 2 * * * cd /path/to/reddit_pain_finder && python run_pipeline.py
```

### 2. 定期备份

```bash
# 备份数据库
cp data/wise_collection.db backups/wise_collection_$(date +%Y%m%d).db

# 备份Chroma数据
tar -czf backups/chroma_db_$(date +%Y%m%d).tar.gz data/chroma_db/
```

### 3. 定期清理

```bash
# 运行lifecycle cleanup
python run_pipeline.py --stage lifecycle_cleanup
```

---

## 附录

### 完整参数列表

```bash
python run_pipeline.py --help
```

### 版本信息

```bash
# 查看Git版本
git log -1 --oneline

# 查看Python版本
python --version
```

---

## 获取帮助

如有问题，请查看：
- [开发文档](docs/PHASE_5_6_DEV_GUIDE.md)
- [性能测试报告](docs/PHASE_6_PERFORMANCE_TEST_REPORT.md)
- GitHub Issues

---

**最后更新**: 2026-01-15
**版本**: v1.0
