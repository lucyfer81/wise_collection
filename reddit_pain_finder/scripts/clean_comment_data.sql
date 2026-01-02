-- Clean Comment Data Script
-- 清理comment相关数据以重新应用新阈值过滤
-- 执行前请先备份数据库！

-- ============================================
-- 预检查：查看将要删除的数据
-- ============================================

-- 查看filtered_comments统计
SELECT 'Filtered comments to be deleted:' as info, COUNT(*) as count
FROM filtered_comments;

-- 查看从comments提取的pain_events统计
SELECT 'Pain events from comments to be deleted:' as info, COUNT(*) as count
FROM pain_events
WHERE source_type = 'comment';

-- 查看pain_score分布（了解数据质量）
SELECT
  CASE
    WHEN pain_score < 0.3 THEN '0.2-0.3 (Low Quality)'
    WHEN pain_score < 0.4 THEN '0.3-0.4 (Medium)'
    WHEN pain_score < 0.5 THEN '0.4-0.5 (Good)'
    ELSE '0.5+ (High Quality)'
  END as quality_range,
  COUNT(*) as count,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM filtered_comments), 1) as percentage
FROM filtered_comments
GROUP BY quality_range
ORDER BY
  CASE quality_range
    WHEN '0.2-0.3 (Low Quality)' THEN 1
    WHEN '0.3-0.4 (Medium)' THEN 2
    WHEN '0.4-0.5 (Good)' THEN 3
    ELSE 4
  END;

-- ============================================
-- 执行清理（请确认后再执行）
-- ============================================

-- BEGIN TRANSACTION;  -- 开始事务（可以回滚）

-- 步骤1: 删除从comments提取的pain_events
-- DELETE FROM pain_events
-- WHERE source_type = 'comment';

-- 步骤2: 删除所有filtered_comments
-- DELETE FROM filtered_comments;

-- 步骤3: （可选）重置自增ID
-- DELETE FROM sqlite_sequence WHERE name = 'filtered_comments';

-- COMMIT;  -- 提交事务
-- ROLLBACK;  -- 如果发现问题，执行回滚

-- ============================================
-- 验证清理结果
-- ============================================

-- 验证filtered_comments已清空
SELECT 'Remaining filtered_comments (should be 0):' as info, COUNT(*) as count
FROM filtered_comments;

-- 验证comment的pain_events已清空
SELECT 'Remaining pain_events from comments (should be 0):' as info, COUNT(*) as count
FROM pain_events
WHERE source_type = 'comment';

-- 验证posts的数据未受影响
SELECT 'Pain events from posts (should be unchanged):' as info, COUNT(*) as count
FROM pain_events
WHERE source_type = 'post' OR source_type IS NULL;
