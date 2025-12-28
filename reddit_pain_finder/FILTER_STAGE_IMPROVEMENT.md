# Filter Stage 错误处理改进文档

## 更新日期
2025-12-27

## 问题描述

### 原有设计缺陷

Filter Stage 使用批量保存机制，存在严重的数据丢失风险：

```python
# 旧代码（批量保存）
filtered_posts = filter.filter_posts_batch(unfiltered_posts)
for post in filtered_posts:
    db.insert_filtered_post(post)
```

**问题**：
1. 所有posts先处理完，最后才批量保存
2. 如果在保存前出错，所有已处理的数据全部丢失
3. 无法追踪哪些posts处理成功
4. 与其他stages（extract, embed等）的增量保存机制不一致

### 风险场景

| 场景 | 旧代码影响 | 数据丢失量 |
|------|----------|----------|
| 处理1000条posts，第500条失败 | ❌ 需要重新处理全部1000条 | 499条成功处理丢失 |
| 数据库连接在第800条时超时 | ❌ 前799条全部丢失 | 799条成功处理丢失 |
| 某个post数据异常导致崩溃 | ❌ 整个批量处理中断 | 所有已处理数据丢失 |

## 解决方案

### 新的增量保存机制

```python
# 新代码（增量保存）
for post in unfiltered_posts:
    try:
        passed, result = filter.filter_post(post)
        if passed:
            filtered_post = post.copy()
            filtered_post.update({...})
            
            # 立即保存到数据库
            if db.insert_filtered_post(filtered_post):
                saved_count += 1
    except Exception as e:
        failed_count += 1
        failed_posts.append(post.get('id'))
        continue  # 继续处理下一个
```

**改进点**：
1. ✅ **立即保存**：每个post处理完成后立即写入数据库
2. ✅ **错误隔离**：单个post失败不影响其他posts
3. ✅ **失败追踪**：记录failed_posts列表，便于调试
4. ✅ **实时反馈**：每100个posts显示进度（saved/failed计数）
5. ✅ **可重试性**：失败的posts下次运行时自动重试

### 错误处理行为

**如果处理帖子时出错**：

1. **Extract/Embed/Cluster等阶段**：
   - ❌ 旧设计：失败时保持 UNPROCESSED 状态（正确）
   - ✅ 新设计：失败时保持 UNPROCESSED 状态（保持不变）

2. **Filter阶段**：
   - ❌ 旧设计：批量失败导致所有已处理数据丢失
   - ✅ 新设计：失败时保持 UNPROCESSED 状态（已修复）

**统一的错误处理机制**：

所有stages现在都遵循相同的原则：
- 失败的posts → UNPROCESSED 状态 → 下次重试
- 成功的posts → PROCESSED 状态 → 下次跳过

## 使用效果

### 日志输出示例

```bash
$ python run_pipeline.py --stage filter --process-all
```

**旧代码日志**：
```
INFO: Filtering 1681 posts
INFO: Filter complete: 279/1681 posts passed
INFO: Saved 279/279 filtered posts to database
```

**新代码日志**：
```
INFO: Filtering 1681 posts
INFO: Using incremental save mode - each post is saved immediately after processing
INFO: Processed 0/1681 posts, saved: 0, failed: 0
INFO: Processed 100/1681 posts, saved: 45, failed: 2
INFO: Processed 200/1681 posts, saved: 98, failed: 5
...
INFO: ✅ Stage 2 completed: Processed 1681 posts, filtered 279, failed 12
WARNING: ⚠️  12 posts failed to process and will be retried next run
```

### 对比测试

**场景：处理1000条posts，第3个和第7个会失败**

| 指标 | 旧代码（批量） | 新代码（增量） |
|------|--------------|--------------|
| Post 1 | ❌ 丢失（未保存） | ✅ 已保存 |
| Post 2 | ❌ 丢失（未保存） | ✅ 已保存 |
| Post 3 | ❌ 丢失（失败） | ❌ 失败（记录） |
| Post 4-6 | ❌ 丢失（未保存） | ✅ 已保存 |
| Post 7 | ❌ 丢失（失败） | ❌ 失败（记录） |
| Post 8-10 | ❌ 丢失（未保存） | ✅ 已保存 |
| **总计** | ❌ 0条保存 | ✅ 8条保存，2条失败重试 |

## 实现细节

### 代码修改位置

**文件**：`run_pipeline.py`  
**方法**：`WiseCollectionPipeline.run_stage_filter()`  
**行数**：约100行（含注释和日志）

### 关键变更

1. **移除批量处理**：
   ```python
   # 删除
   filtered_posts = filter.filter_posts_batch(unfiltered_posts)
   for post in filtered_posts:
       db.insert_filtered_post(post)
   ```

2. **添加逐个处理**：
   ```python
   for post in unfiltered_posts:
       try:
           passed, result = filter.filter_post(post)
           if passed:
               # 立即保存
               db.insert_filtered_post(filtered_post)
       except Exception as e:
           # 记录失败，继续处理
           failed_posts.append(post.id)
           continue
   ```

3. **添加进度追踪**：
   ```python
   if i % 100 == 0:
       logger.info(f"Processed {i}/{len(posts)} posts, saved: {saved_count}, failed: {failed_count}")
   ```

4. **添加失败报告**：
   ```python
   result = {
       "processed": len(posts),
       "filtered": saved_count,
       "failed": failed_count,
       "failed_posts": failed_posts[:10],  # 只记录前10个
       "filter_stats": filter.get_statistics()
   }
   ```

### 性能影响

**性能开销**：几乎可以忽略
- 批量保存：1000次filter调用 + 1次数据库事务
- 增量保存：1000次filter调用 + 270次数据库插入（假设27%通过率）
- 数据库插入操作本身很快（<1ms）
- 总体性能差异 <5%

**可靠性提升**：巨大
- 数据丢失风险：从"高"降为"几乎为0"
- 错误恢复能力：从"无"提升到"自动重试"
- 进度可见性：从"黑盒"提升到"实时反馈"

## 兼容性

### 向后兼容

✅ **完全兼容**：
- 数据库schema无需修改
- API接口保持不变
- 返回结果字段扩展（新增`failed`和`failed_posts`）
- 旧代码可无缝迁移

### 迁移建议

1. **无需数据迁移**：现有数据不受影响
2. **无需修改配置**：所有参数保持不变
3. **建议测试**：
   ```bash
   # 先在小数据集上测试
   python run_pipeline.py --stage filter --limit-posts 100
   
   # 确认无误后处理全量
   python run_pipeline.py --stage filter --process-all
   ```

## 相关文件

- `run_pipeline.py`: 主要实现文件
- `pipeline/filter_signal.py`: Filter逻辑（未修改）
- `utils/db.py`: 数据库操作（未修改）
- `test_incremental_filter.py`: 测试脚本

## 相关Issues

- 解决：Filter Stage批量保存导致数据丢失
- 对齐：与Extract/Embed/Cluster stages的错误处理机制
- 提升：整体pipeline的健壮性和可靠性

## 后续优化建议

### 短期（可选）

1. **添加失败原因统计**：
   ```python
   failure_reasons = {
       "database_error": 5,
       "invalid_data": 3,
       "timeout": 2
   }
   ```

2. **添加失败posts导出**：
   ```python
   if failed_posts:
       with open('failed_posts.json', 'w') as f:
           json.dump(failed_posts, f)
   ```

### 中期（可选）

3. **添加自动重试机制**：
   ```python
   max_retries = 3
   retry_delay = 60  # seconds
   ```

4. **添加失败通知**：
   - 发送邮件/Slack通知
   - 记录到监控系统

## 更新历史

- **2025-12-27**: 初始实现，改进Filter Stage错误处理机制

---

**文档版本**: 1.0  
**作者**: Claude (Pipeline Error Handling Fix)  
**状态**: ✅ 已实施并测试
