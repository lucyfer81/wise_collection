-- 清理重复的opportunities
-- 策略：保留每个cluster中raw_total_score最高的，如果分数相同则保留ID最大的

-- 步骤1: 查看将要删除的记录
SELECT
    cluster_id,
    COUNT(*) as total_opportunities,
    COUNT(*) - 1 as to_be_deleted,
    GROUP_CONCAT(opportunity_name, '; ') as all_names
FROM opportunities
GROUP BY cluster_id
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC;

-- 步骤2: 创建临时表存储要保留的opportunity IDs
CREATE TEMP TABLE keep_opportunities AS
SELECT
    MAX(id) as opportunity_id
FROM opportunities
WHERE raw_total_score > 0  -- 只考虑有分数的
GROUP BY cluster_id
UNION
SELECT MAX(id)
FROM opportunities
GROUP BY cluster_id
HAVING MAX(raw_total_score) = 0;  -- 如果全都是0分，保留ID最大的

-- 步骤3: 查看将被保留的记录
SELECT
    o.id,
    o.cluster_id,
    c.cluster_name,
    o.opportunity_name,
    o.raw_total_score
FROM opportunities o
JOIN clusters c ON o.cluster_id = c.id
WHERE o.id IN (SELECT opportunity_id FROM keep_opportunities)
ORDER BY c.cluster_name;

-- 步骤4: 删除重复的opportunities（不在keep_opportunities表中的）
DELETE FROM opportunities
WHERE id NOT IN (SELECT opportunity_id FROM keep_opportunities);

-- 步骤5: 验证清理结果
SELECT
    cluster_id,
    COUNT(*) as remaining_count,
    GROUP_CONCAT(opportunity_name, '; ') as remaining_names
FROM opportunities
GROUP BY cluster_id
HAVING COUNT(*) > 1;

-- 步骤6: 清理临时表
DROP TABLE keep_opportunities;
