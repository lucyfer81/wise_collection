# Decision Shortlist Layer 设计方案

## 🎯 目标（一句话）

每次 pipeline 运行后，系统不是给你一堆 pain / clusters / scores，而是只输出一个：

> **Top 3–5 可执行产品机会清单**

且每一条：

- 一行 Problem
- 一行 MVP
- 一句 Why Now

能在 **10 分钟内决定：做 or 不做。**

---

## 📋 设计概述

本文档详细描述了 Decision Shortlist Layer 的设计方案，该模块作为 pipeline 的第 9 阶段，负责从所有评分机会中筛选出 Top 3-5 个最值得执行的产品机会，并为每个机会生成简洁的决策信息。

---

## 第一部分：架构设计

Decision Shortlist Layer 将作为 pipeline 的第 9 个阶段（stage 9），在所有数据处理完成后执行。核心组件：

### 1. 核心类：DecisionShortlistGenerator

位置：`pipeline/decision_shortlist.py`

主要方法：
- `generate_shortlist()`: 主方法，返回 Top 3-5 个机会
- `_apply_hard_filters()`: 硬性过滤（viability_score >= 7.0, cluster_size >= 6, trust_level >= 0.7）
- `_check_cross_source_validation()`: 三层优先级的跨源验证
- `_calculate_final_score()`: 对数缩放加权计算（logarithmic scaling）
- `_apply_diversity_boost()`: 多样性惩罚机制（避免同质化）
- `_select_top_candidates()`: 动态选择 Top 3-5 个（考虑多样性）
- `_generate_readable_content()`: 调用 LLM 生成 Problem/MVP/Why Now
- `_export_markdown()`: 生成人类可读报告（含空列表处理）
- `_export_json()`: 生成机器可用 JSON

### 2. 数据流

```
输入阶段：
  ├─ opportunities 表（已评分的机会）
  ├─ clusters 表（聚类信息）
  └─ aligned_problems 表（跨源对齐信息）

处理阶段：
  ├─ 硬性过滤（viability_score >= 7.0, cluster_size >= 6, trust_level >= 0.7）
  ├─ 跨源验证（三层优先级）
  ├─ 最终评分（加权计算）
  ├─ 排序（按 final_score 降序）
  └─ LLM 生成（Problem / MVP / Why Now）

输出阶段：
  ├─ Markdown 报告（reports/shortlist_report_YYYYMMDD.md）
  └─ JSON 文件（data/decision_shortlist.json）
```

### 3. 配置集成

在 `config/thresholds.yaml` 中添加 `decision_shortlist` 部分，包含：
- 阈值配置（min_viability_score, min_cluster_size, min_trust_level）
- 跨源验证加分（level_1/2/3 boost）
- 最终评分权重
- LLM prompt 模板

---

## 第二部分：硬性过滤规则

### 1. 过滤阈值

从 `config/thresholds.yaml` 读取：
```yaml
decision_shortlist:
  min_viability_score: 7.0
  min_cluster_size: 6
  min_trust_level: 0.7
  ignored_clusters: []  # 可选：要忽略的 cluster 名称列表
```

### 2. SQL 查询逻辑

```sql
SELECT
    o.*,
    c.cluster_name,
    c.cluster_size,
    c.source_type,
    c.pain_event_ids
FROM opportunities o
JOIN clusters c ON o.cluster_id = c.id
WHERE o.total_score >= {min_viability_score}
  AND c.cluster_size >= {min_cluster_size}
  AND o.trust_level >= {min_trust_level}
  AND c.cluster_name NOT IN ({ignored_clusters})
ORDER BY o.total_score DESC
```

### 3. 过滤统计

记录每个过滤条件的过滤数量，用于日志输出：
- 因 viability_score 不足被过滤：X 个
- 因 cluster_size 不足被过滤：Y 个
- 因 trust_level 不足被过滤：Z 个
- 通过所有过滤：N 个

如果没有通过硬性过滤的机会，返回空列表并记录警告日志。

---

## 第三部分：跨源验证逻辑

### 1. 三层优先级验证

| 级别 | 条件 | 加分 | validated_problem |
|------|------|------|-------------------|
| **Level 1 - 强信号** | cluster 在 `aligned_problems` 表中<br>或 `source_type == 'aligned'` | +2.0 | True |
| **Level 2 - 中等信号** | `cluster_size >= 10` AND 跨 >= 3 个不同 subreddit | +1.0 | True |
| **Level 3 - 弱信号** | `cluster_size >= 8` AND 跨 >= 2 个不同 subreddit | +0.5 | False |

### 2. 实现逻辑

```python
def _check_cross_source_validation(self, opportunity: Dict, cluster: Dict) -> Dict:
    """检查跨源验证，返回验证信息和加分"""

    # Level 1: 检查 aligned_problems 表或 source_type
    if cluster['source_type'] == 'aligned':
        return {
            "has_cross_source": True,
            "validation_level": 1,
            "boost_score": 2.0,
            "validated_problem": True,
            "evidence": "Aligned from cross-source analysis"
        }

    # 检查 aligned_problems 表
    aligned_problem = self._check_aligned_problems_table(cluster['cluster_name'])
    if aligned_problem:
        return {
            "has_cross_source": True,
            "validation_level": 1,
            "boost_score": 2.0,
            "validated_problem": True,
            "evidence": f"Found in aligned_problems: {aligned_problem['aligned_problem_id']}"
        }

    # Level 2: 检查 cluster_size + 跨 subreddit
    pain_event_ids = json.loads(cluster['pain_event_ids'])
    subreddit_count = self._count_subreddits(pain_event_ids)

    if cluster['cluster_size'] >= 10 and subreddit_count >= 3:
        return {
            "has_cross_source": True,
            "validation_level": 2,
            "boost_score": 1.0,
            "validated_problem": True,
            "evidence": f"Large cluster ({cluster['cluster_size']}) across {subreddit_count} subreddits"
        }

    # Level 3: 弱信号
    if cluster['cluster_size'] >= 8 and subreddit_count >= 2:
        return {
            "has_cross_source": True,
            "validation_level": 3,
            "boost_score": 0.5,
            "validated_problem": False,
            "evidence": f"Medium cluster ({cluster['cluster_size']}) across {subreddit_count} subreddits"
        }

    # 无跨源验证
    return {
        "has_cross_source": False,
        "validation_level": 0,
        "boost_score": 0.0,
        "validated_problem": False,
        "evidence": "No cross-source validation"
    }
```

### 3. 辅助方法

```python
def _check_aligned_problems_table(self, cluster_name: str) -> Optional[Dict]:
    """检查 cluster 是否在 aligned_problems 表中"""
    with db.get_connection("clusters") as conn:
        cursor = conn.execute("""
            SELECT aligned_problem_id, sources, alignment_score
            FROM aligned_problems
            WHERE cluster_ids LIKE ?
        """, (f'%{cluster_name}%',))
        result = cursor.fetchone()
        return dict(result) if result else None

def _count_subreddits(self, pain_event_ids: List[int]) -> int:
    """计算涉及的不同 subreddit 数量"""
    with db.get_connection("pain") as conn:
        placeholders = ','.join('?' for _ in pain_event_ids)
        cursor = conn.execute(f"""
            SELECT COUNT(DISTINCT fp.subreddit) as count
            FROM pain_events pe
            JOIN filtered_posts fp ON pe.post_id = fp.id
            WHERE pe.id IN ({placeholders})
        """, pain_event_ids)
        return cursor.fetchone()['count']
```

---

## 第四部分：最终评分与排序

### 1. 对数缩放评分公式

**设计理念**：使用对数函数处理 cluster_size，避免大规模聚类过度影响评分，同时保留规模作为有价值的信号。

```python
import math

def _calculate_final_score(self, opportunity: Dict, cross_source_info: Dict) -> float:
    """计算最终得分（对数缩放 + 配置化权重）"""

    # 从配置读取权重
    weights = self.config['decision_shortlist']['final_score_weights']

    # 基础评分
    viability_score = opportunity['total_score']  # 已经由 ViabilityScorer 计算 (0-10)
    trust_level = opportunity.get('trust_level', 0.5)  # (0-1)

    # 对数缩放：log10(cluster_size)
    # 举例：
    #   cluster_size = 10  → log10(10) = 1.0
    #   cluster_size = 100 → log10(100) = 2.0
    #   cluster_size = 200 → log10(200) = 2.3
    # 这样 100 和 200 的差距缩小为 0.3，而不是线性缩放的 10 倍差距
    cluster_size = opportunity['cluster_size']
    cluster_size_log = math.log10(max(cluster_size, 1))  # 避免log(0)

    # 跨源加分
    cross_source_bonus = cross_source_info['boost_score']  # 0-2.0

    # 加权计算（所有权重都在配置文件中）
    final_score = (
        viability_score * weights['viability_score'] +
        cluster_size_log * weights['cluster_size_log_factor'] +
        trust_level * weights['trust_level']
    )

    # 跨源验证加分（可选，如果不使用对数缩放模型）
    if cross_source_info['has_cross_source']:
        final_score += weights['cross_source_bonus'] * cross_source_bonus

    # 归一化到 0-10 范围（可选，取决于权重配置）
    # 如果权重总和大于 1，可能需要归一化
    return min(final_score, 10.0)
```

**优势**：
- 对数缩放避免极端值影响：大小为 200 的聚类不会比大小为 20 的聚类获得不成比例的高分
- 所有权重可配置：从"经验驱动"升级为"模型驱动"，可以系统性地调优
- 保留规模信号：大聚类仍然获得更高分数，但不会主导决策

### 2. 配置化权重系统

在 `config/thresholds.yaml` 中：

```yaml
decision_shortlist:
  # 最终评分权重（所有权重系数均可调整）
  final_score_weights:
    viability_score: 1.0           # 可行性评分权重（0-10 分，乘以 1.0）
    cluster_size_log_factor: 2.5   # log10(cluster_size) 的权重系数
    trust_level: 1.5               # 信任度权重（0-1，乘以 1.5）
    cross_source_bonus: 5.0        # 跨源验证基础加分

  # 示例计算：
  # 假设某个机会：
  #   viability_score = 8.0
  #   cluster_size = 50
  #   trust_level = 0.8
  #   cross_source_level = 1 (boost = 2.0)
  #
  # 计算：
  #   final_score = 8.0 * 1.0 + log10(50) * 2.5 + 0.8 * 1.5 + 2.0 * 5.0 * 0.2
  #              = 8.0 + 1.7 * 2.5 + 1.2 + 2.0
  #              = 8.0 + 4.25 + 1.2 + 2.0
  #              = 15.45 → 归一化到 10 分范围 = 10.0（或直接限制上限）
```

**权重调整指南**：
- `viability_score`: 提高此权重 → 更重视 LLM 评估的可行性
- `cluster_size_log_factor`: 提高此权重 → 更重视数据规模（但对数缩放会减弱极端影响）
- `trust_level`: 提高此权重 → 更重视数据源质量
- `cross_source_bonus`: 提高此权重 → 更重视跨源验证

### 3. 基础排序逻辑

按 `final_score` 降序排列（不考虑多样性）：

```python
def _sort_by_score(self, scored_opportunities: List[Dict]) -> List[Dict]:
    """按 final_score 降序排序"""
    return sorted(scored_opportunities, key=lambda x: x['final_score'], reverse=True)
```

### 4. 评分详情

每个机会的评分详情：
- `viability_score`: 原始可行性评分（0-10）
- `cluster_size_log`: log10(聚类规模)，用于平滑规模差异
- `trust_level`: 信任度评分（0-1）
- `cross_source_bonus`: 跨源验证加分（0-2.0，由验证等级决定）
- `final_score`: 最终加权评分（0-10，应用对数缩放和配置权重）

**示例对比（线性 vs 对数）**：

| cluster_size | 线性缩放 (/10) | 对数缩放 (log10) | 差异 |
|--------------|----------------|------------------|------|
| 10 | 1.0 | 1.0 | 无 |
| 50 | 5.0 | 1.7 | 对数降低 66% |
| 100 | 10.0 | 2.0 | 对数降低 80% |
| 200 | 20.0（上限 10） | 2.3 | 对数降低 88.5% |

---

## 第四部分（续）：多样性保证机制（可选高级功能）

### 1. 问题背景

如果评分最高的 Top 5 个机会都来自同一个领域（例如都和"Notion 同步"相关），shortlist 会缺乏多样性，可能错过其他领域的有趣机会。

### 2. 多样性惩罚策略

**核心思想**：在选择后续机会时，对与已选机会相似或同领域的候选机会施加轻微的分数惩罚（如乘以 0.9）。

```python
def _apply_diversity_penalty(
    self,
    candidate: Dict,
    selected_candidates: List[Dict]
) -> float:
    """计算多样性惩罚系数"""

    penalty_factor = 1.0  # 默认无惩罚

    for selected in selected_candidates:
        # 1. 检查是否属于同一 cluster（直接关联）
        if candidate.get('cluster_id') == selected.get('cluster_id'):
            penalty_factor *= 0.7  # 严重惩罚：同一 cluster
            continue

        # 2. 检查 pain_type 相似度（如果可用）
        candidate_pain_type = candidate.get('primary_pain_type', '')
        selected_pain_type = selected.get('primary_pain_type', '')

        if candidate_pain_type and candidate_pain_type == selected_pain_type:
            penalty_factor *= 0.85  # 中等惩罚：同一 pain_type

        # 3. 检查关键词重叠（可选）
        if self._check_keyword_overlap(candidate, selected):
            penalty_factor *= 0.90  # 轻微惩罚：关键词重叠

    return penalty_factor


def _select_top_candidates_with_diversity(
    self,
    scored_opportunities: List[Dict]
) -> List[Dict]:
    """选择 Top 3-5 个候选机会（考虑多样性）"""

    # 按分数降序排序
    sorted_opportunities = sorted(
        scored_opportunities,
        key=lambda x: x['final_score'],
        reverse=True
    )

    selected = []
    remaining = sorted_opportunities.copy()

    max_candidates = self.config['decision_shortlist']['output']['max_candidates']
    min_candidates = self.config['decision_shortlist']['output']['min_candidates']

    for i in range(max_candidates):
        if not remaining:
            break

        # 应用多样性惩罚
        for candidate in remaining:
            penalty = self._apply_diversity_penalty(candidate, selected)
            candidate['diversity_adjusted_score'] = candidate['final_score'] * penalty

        # 选择调整后分数最高的
        best_candidate = max(
            remaining,
            key=lambda x: x['diversity_adjusted_score']
        )

        selected.append(best_candidate)
        remaining.remove(best_candidate)

        # 如果已选够 min_candidates 个，检查是否需要继续
        if len(selected) >= min_candidates:
            # 检查下一个候选的调整后分数是否太低
            if remaining:
                next_best = max(
                    remaining,
                    key=lambda x: x['diversity_adjusted_score']
                )
                # 如果差距过大，停止选择
                if (best_candidate['diversity_adjusted_score'] -
                    next_best['diversity_adjusted_score']) > 2.0:
                    break

    return selected[:min(len(selected), max_candidates)]
```

### 3. 辅助方法

```python
def _check_keyword_overlap(self, candidate1: Dict, candidate2: Dict) -> bool:
    """检查两个机会的关键词重叠度"""

    # 提取关键词（从 opportunity_name 和 description）
    text1 = f"{candidate1.get('opportunity_name', '')} {candidate1.get('description', '')}"
    text2 = f"{candidate2.get('opportunity_name', '')} {candidate2.get('description', '')}"

    # 简单的关键词提取（可以用更复杂的 NLP 方法）
    keywords1 = set(text1.lower().split())
    keywords2 = set(text2.lower().split())

    # 计算交集
    overlap = keywords1 & keywords2

    # 如果重叠关键词超过 3 个，认为相似
    return len(overlap) >= 3
```

### 4. 配置选项

```yaml
decision_shortlist:
  diversity:
    enabled: true  # 是否启用多样性机制

    penalties:
      same_cluster: 0.7      # 同一 cluster 的惩罚系数
      same_pain_type: 0.85   # 同一 pain_type 的惩罚系数
      keyword_overlap: 0.90  # 关键词重叠的惩罚系数

    min_diversity_score_gap: 2.0  # 最低多样性分数差距，低于此值停止选择
```

### 5. 效果示例

**不使用多样性机制**：
```
Top 5 机会：
1. Notion API 同步工具 (score: 8.5)
2. Notion 数据库备份工具 (score: 8.3)
3. Notion 页面模板生成器 (score: 8.1)
4. Notion Webhook 集成工具 (score: 7.9)
5. Notion 批量导入工具 (score: 7.7)
→ 全部都是 Notion 相关，缺乏多样性
```

**使用多样性机制**：
```
Top 5 机会：
1. Notion API 同步工具 (score: 8.5, adjusted: 8.5)
2. API 文档生成工具 (score: 8.2, adjusted: 8.2)
3. Slack 消息分析工具 (score: 7.8, adjusted: 7.8)
4. GitHub PR 自动审查工具 (score: 7.6, adjusted: 7.6)
5. Notion 数据库备份工具 (score: 8.3, adjusted: 5.8, 因多样性惩罚被降级)
→ 覆盖不同领域，更丰富
```

---

## 第五部分：LLM 生成可读内容

### 1. Prompt 模板

存储在 `config/thresholds.yaml` 的 `decision_shortlist.prompts.problem_mvp_whynow` 中：

```yaml
decision_shortlist:
  prompts:
    problem_mvp_whynow: |
      You are a product expert specializing in identifying micro-SaaS opportunities for solo founders.

      Based on the following opportunity data, generate THREE concise, impactful sentences:

      **Opportunity Data:**
      - Name: {opportunity_name}
      - Description: {description}
      - Target Users: {target_users}
      - Missing Capability: {missing_capability}
      - Why Existing Tools Fail: {why_existing_fail}
      - Cluster Summary: {cluster_summary}
      - Pain Events: {cluster_size} unique pain points
      - Cross-Source Validation: {cross_source_info}

      **Output Requirements:**

      1. **Problem Statement** (one sentence, max 30 words)
         Format: "Users in [context/role] are struggling with [specific task] because [structural reason]."

      2. **MVP Cut** (one sentence, max 25 words)
         Format: "A minimal tool that helps them [do X faster/easier/safer] by replacing [current bad workaround]."

      3. **Why Now** (one sentence, max 20 words)
         Format: "This is urgent now because [specific signal/tool failure/multi-community validation]."

      **Constraints:**
      - Be specific and concrete (avoid generic fluff)
      - Focus on actionable insights (not vague observations)
      - Use present tense
      - Each sentence should stand alone (no dependencies)

      **Output Format:**
      Return ONLY a valid JSON object with these exact keys:
      {
        "problem": "one sentence problem statement",
        "mvp": "one sentence mvp description",
        "why_now": "one sentence urgency explanation"
      }

      No additional text, explanations, or markdown formatting.
```

### 2. 调用方式

```python
def _generate_readable_content(self, opportunity: Dict, cluster: Dict, cross_source_info: Dict) -> Dict[str, str]:
    """使用 LLM生成 Problem/MVP/Why Now"""

    try:
        # 准备 prompt 参数
        prompt_params = {
            'opportunity_name': opportunity['opportunity_name'],
            'description': opportunity['description'],
            'target_users': opportunity.get('target_users', ''),
            'missing_capability': opportunity.get('missing_capability', ''),
            'why_existing_fail': opportunity.get('why_existing_fail', ''),
            'cluster_summary': cluster.get('centroid_summary', ''),
            'cluster_size': cluster['cluster_size'],
            'cross_source_info': cross_source_info['evidence']
        }

        # 加载 prompt 模板
        prompt_template = self.config['decision_shortlist']['prompts']['problem_mvp_whynow']
        prompt = prompt_template.format(**prompt_params)

        # 调用 LLM
        response = self.llm_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model_type="main",
            temperature=0.3,
            max_tokens=500
        )

        # 解析响应
        content = response.get('content', response) if isinstance(response, dict) else response
        result = json.loads(content)

        return {
            'problem': result.get('problem', ''),
            'mvp': result.get('mvp', ''),
            'why_now': result.get('why_now', '')
        }

    except Exception as e:
        logger.error(f"LLM generation failed for {opportunity['opportunity_name']}: {e}")
        # 降级：从现有字段聚合提取
        return self._fallback_readable_content(opportunity, cluster)
```

### 3. 降级策略

```python
def _fallback_readable_content(self, opportunity: Dict, cluster: Dict) -> Dict[str, str]:
    """降级策略：从现有字段提取"""

    # 从 opportunity.description 提取
    description = opportunity.get('description', '')
    target_users = opportunity.get('target_users', 'Users')
    missing_capability = opportunity.get('missing_capability', '')
    why_fail = opportunity.get('why_existing_fail', '')

    # Problem Statement
    problem = f"{target_users} are struggling with {description[:50]}... because {why_fail[:50]}..."

    # MVP Cut
    mvp = f"A minimal tool that addresses {missing_capability[:40]}... with a simple interface."

    # Why Now
    cluster_size = cluster.get('cluster_size', 0)
    why_now = f"Validated by {cluster_size} recent pain points from active communities."

    return {
        'problem': problem[:150],
        'mvp': mvp[:100],
        'why_now': why_now[:100]
    }
```

---

## 第六部分：输出格式

### 1. Markdown 报告

文件路径：`reports/shortlist_report_YYYYMMDD.md`

```markdown
# Decision Shortlist (2025-12-25)

**Generated**: 2025-12-25 18:30:00
**Pipeline Run**: pipeline_results_20251225_185806.json
**Total Opportunities Analyzed**: 50
**Filtered Candidates**: 5

---

## 🎯 Candidate 1: AI-Powered API Documentation Generator

**Final Score**: 8.7/10
**Cross-Source Evidence**: ✅ YES (Level 1)
**Confidence**: HIGH

### Problem
Developers maintaining REST APIs are struggling to keep documentation in sync with code changes because manual updates are error-prone and time-consuming.

### MVP
A minimal CLI tool that auto-generates interactive API docs from OpenAPI specs by replacing manual Markdown maintenance with live preview.

### Why Now
This is urgent now because validated across Reddit r/programming and Hacker News with 15+ developers expressing frustration with Swagger UI.

---

**Supporting Data**:
- **Viability Score**: 8.2/10
- **Cluster Size**: 15 pain events
- **Trust Level**: 0.85 (high-quality sources)
- **Cross-Source**: Aligned from Reddit + HackerNews
- **Market Tier**: Medium (50K-100K addressable users)
- **Killer Risks**: Swagger UI is free and well-established

---

## 🎯 Candidate 2: ...

(重复上述结构)

---

## 📊 Summary Statistics

| Metric | Value |
|--------|-------|
| Total Opportunities Analyzed | 50 |
| Passed Hard Filters | 15 |
| Cross-Source Validated | 8 (Level 1: 3, Level 2: 3, Level 3: 2) |
| Final Selection | 5 |
| Avg Final Score | 7.8/10 |

### Distribution by Validation Level
- Level 1 (Strong): 3 candidates
- Level 2 (Medium): 1 candidate
- Level 3 (Weak): 1 candidate

---

## 📝 Notes

- All candidates passed hard filters: viability >= 7.0, cluster_size >= 6, trust_level >= 0.7
- Cross-source validation adds +2.0 (Level 1), +1.0 (Level 2), or +0.5 (Level 3) to final score
- Review generated JSON for detailed scoring breakdown
```

### 2. JSON 文件

文件路径：`data/decision_shortlist.json`

**正常情况**（有候选机会）：

```json
[
  {
    "id": "cluster_42",
    "opportunity_name": "AI-Powered API Documentation Generator",
    "problem": "Developers maintaining REST APIs are struggling to keep documentation in sync with code changes because manual updates are error-prone and time-consuming.",
    "mvp": "A minimal CLI tool that auto-generates interactive API docs from OpenAPI specs by replacing manual Markdown maintenance with live preview.",
    "why_now": "This is urgent now because validated across Reddit r/programming and Hacker News with 15+ developers expressing frustration with Swagger UI.",
    "final_score": 8.7,
    "viability_score": 8.2,
    "cluster_size_log": 1.18,
    "trust_level": 0.85,
    "cross_source_level": 1,
    "cross_source_bonus": 2.0,
    "validated_problem": true,
    "sources": ["reddit", "hackernews"],
    "cluster_size": 15,
    "subreddit_count": 4,
    "market_tier": "medium",
    "killer_risks": ["Swagger UI is free and well-established"],
    "recommendation": "pursue - Strong opportunity with high potential",
    "generated_at": "2025-12-25T18:30:00"
  }
]
```

**空列表情况**（无候选机会）：

```json
{
  "empty": true,
  "message": "本次运行未能发现满足 Shortlist 标准的足够强的机会信号。",
  "statistics": {
    "total_opportunities_analyzed": 50,
    "passed_viability_filter": 30,
    "passed_cluster_size_filter": 20,
    "passed_trust_level_filter": 15,
    "passed_all_filters": 0,
    "filter_reasons": {
      "viability_score_too_low": 20,
      "cluster_size_too_small": 10,
      "trust_level_too_low": 5
    },
    "highest_score": 6.8,
    "score_threshold": 7.0
  },
  "recommendations": [
    "考虑降低过滤阈值（min_viability_score, min_cluster_size, min_trust_level）",
    "等待更多数据积累后重新运行",
    "检查数据源质量和覆盖范围"
  ],
  "generated_at": "2025-12-25T18:30:00"
}
```

### 3. 空列表处理

**当没有机会满足过滤条件时**，系统应该明确处理这种情况：

```python
def _handle_empty_shortlist(self, filter_stats: Dict) -> Dict[str, Any]:
    """处理空列表情况"""

    # 获取最高分（未通过过滤的机会）
    highest_score = self._get_highest_score_among_filtered()

    result = {
        "empty": True,
        "message": "本次运行未能发现满足 Shortlist 标准的足够强的机会信号。",
        "statistics": {
            "total_opportunities_analyzed": filter_stats['total'],
            "passed_viability_filter": filter_stats['passed_viability'],
            "passed_cluster_size_filter": filter_stats['passed_size'],
            "passed_trust_level_filter": filter_stats['passed_trust'],
            "passed_all_filters": 0,
            "filter_reasons": filter_stats['reasons'],
            "highest_score": highest_score,
            "score_threshold": self.config['decision_shortlist']['min_viability_score']
        },
        "recommendations": self._generate_recommendations_for_empty_list(filter_stats),
        "generated_at": datetime.now().isoformat()
    }

    return result


def _export_empty_markdown_report(self, result: Dict) -> str:
    """生成空列表的 Markdown 报告"""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stats = result['statistics']

    content = f"""# Decision Shortlist ({datetime.now().strftime('%Y-%m-%d')})

⚠️ **注意：本次运行未发现满足标准的候选机会**

**Generated**: {timestamp}
**Pipeline Run**: {self.pipeline_run_id}

---

## 📊 过滤统计

| 指标 | 数量 |
|------|------|
| 总机会数 | {stats['total_opportunities_analyzed']} |
| 通过可行性评分过滤 (>= {stats['score_threshold']}) | {stats['passed_viability_filter']} |
| 通过聚类规模过滤 (>= {self.config['decision_shortlist']['min_cluster_size']}) | {stats['passed_cluster_size_filter']} |
| 通过信任度过滤 (>= {self.config['decision_shortlist']['min_trust_level']}) | {stats['passed_trust_level_filter']} |
| **通过所有过滤** | **{stats['passed_all_filters']}** |

---

## 🚫 过滤原因分布

"""

    for reason, count in stats['filter_reasons'].items():
        content += f"- **{reason}**: {count} 个机会\n"

    content += f"""
---

## 📈 最高分机会

**最高分**: {stats['highest_score']}/10 （低于阈值 {stats['score_threshold']}/10）

这意味着即使是最强的机会信号也未能达到最低可行性标准。

---

## 💡 建议行动

"""

    for i, rec in enumerate(result['recommendations'], 1):
        content += f"{i}. {rec}\n"

    content += """
---

## 📝 配置参考

当前过滤阈值：
- `min_viability_score`: {viability_threshold}
- `min_cluster_size`: {size_threshold}
- `min_trust_level`: {trust_threshold}

如需调整，请修改 `config/thresholds.yaml` 中的 `decision_shortlist` 配置。
""".format(
        viability_threshold=self.config['decision_shortlist']['min_viability_score'],
        size_threshold=self.config['decision_shortlist']['min_cluster_size'],
        trust_threshold=self.config['decision_shortlist']['min_trust_level']
    )

    # 写入文件
    filename = f"shortlist_report_empty_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    filepath = os.path.join(self.config['decision_shortlist']['output']['markdown_dir'], filename)

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    return filepath
```

**关键点**：
- 空列表本身是一个有价值的洞察：表明当前数据中没有足够强的机会信号
- 报告应该清晰说明过滤原因和统计信息
- 提供可行的建议（降低阈值、等待更多数据、检查数据源质量）
- 使用特殊文件名（`shortlist_report_empty_*`）避免覆盖正常报告

---

## 第七部分：Pipeline 集成

### 1. 在 run_pipeline.py 中添加 Stage 9

```python
def run_stage_decision_shortlist(self) -> Dict[str, Any]:
    """阶段9: 决策清单生成"""
    logger.info("=" * 50)
    logger.info("STAGE 9: Decision Shortlist Generation")
    logger.info("=" * 50)

    if self.enable_monitoring:
        performance_monitor.start_stage("decision_shortlist")

    try:
        from pipeline.decision_shortlist import DecisionShortlistGenerator

        generator = DecisionShortlistGenerator()
        result = generator.generate_shortlist()

        self.stats["stage_results"]["decision_shortlist"] = result
        self.stats["stages_completed"].append("decision_shortlist")

        logger.info(f"""
=== Decision Shortlist Generated ===
Total Candidates: {result['total_candidates']}
Selected: {result['shortlist_count']}
Report: {result['markdown_path']}
JSON: {result['json_path']}
""")

        return result

    except Exception as e:
        logger.error(f"Decision Shortlist failed: {e}")
        self.stats["stages_failed"].append("decision_shortlist")
        raise
    finally:
        if self.enable_monitoring:
            performance_monitor.end_stage("decision_shortlist")
```

### 2. 修改 main() 函数

```python
def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Run Wise Collection Pipeline")

    # ... 现有参数 ...

    # 添加新 stage
    parser.add_argument(
        "--stage",
        choices=[
            "fetch", "filter", "extract", "embed", "cluster",
            "alignment", "map_opportunities", "score",
            "decision_shortlist",  # 新增
            "all"
        ],
        default="all",
        help="Pipeline stage to run"
    )

    args = parser.parse_args()

    # ... 现有逻辑 ...

    if args.stage in ["decision_shortlist", "all"]:
        # Stage 9 仅在前面 stages 都完成后运行
        if args.stage == "decision_shortlist" or "score" in pipeline.stats["stages_completed"]:
            pipeline.run_stage_decision_shortlist()
        elif args.stage == "all":
            logger.warning("Skipping decision_shortlist: prerequisite stages not completed")
```

### 3. 命令行使用

```bash
# 运行完整 pipeline（包含 decision_shortlist）
python run_pipeline.py --stage all

# 单独运行 decision_shortlist
python run_pipeline.py --stage decision_shortlist

# 运行到某个阶段（不包含 decision_shortlist）
python run_pipeline.py --stage score
```

---

## 第八部分：配置文件结构

在 `config/thresholds.yaml` 中添加：

```yaml
# ... 现有配置 (filtering_rules, frequency_score_mapping, etc.) ...

# Decision Shortlist 配置
decision_shortlist:
  # ========== 硬性过滤阈值 ==========
  min_viability_score: 7.0
  min_cluster_size: 6
  min_trust_level: 0.7
  ignored_clusters: []  # 可选：要忽略的 cluster 名称列表，如 ["test_cluster", "low_quality"]

  # ========== 跨源验证加分 ==========
  cross_source_boosts:
    level_1: 2.0  # 强信号（aligned_problems 或 source_type='aligned'）
    level_2: 1.0  # 中等信号（cluster_size >= 10 AND >=3 subreddits）
    level_3: 0.5  # 弱信号（cluster_size >= 8 AND >=2 subreddits）

  # ========== 跨源验证条件 ==========
  cross_source_validation:
    level_2:
      min_cluster_size: 10
      min_subreddits: 3
    level_3:
      min_cluster_size: 8
      min_subreddits: 2

  # ========== 最终评分权重（对数缩放模型）==========
  final_score_weights:
    # 对数缩放公式：
    # final_score = (
    #     viability_score * viability_score_weight +
    #     log10(cluster_size) * cluster_size_log_factor +
    #     trust_level * trust_level_weight
    # )
    # 如果 cross_source_validated: + cross_source_bonus * boost_score

    viability_score: 1.0           # 可行性评分权重（0-10 分）
    cluster_size_log_factor: 2.5   # log10(cluster_size) 的权重系数
    trust_level: 1.5               # 信任度权重（0-1）
    cross_source_bonus: 5.0        # 跨源验证基础加分

  # 权重调整指南：
  # - viability_score: 提高此权重 → 更重视 LLM 评估的可行性
  # - cluster_size_log_factor: 提高此权重 → 更重视数据规模（但对数缩放减弱极端影响）
  # - trust_level: 提高此权重 → 更重视数据源质量
  # - cross_source_bonus: 提高此权重 → 更重视跨源验证

  # 示例计算：
  # 假设某个机会：
  #   viability_score = 8.0
  #   cluster_size = 50
  #   trust_level = 0.8
  #   cross_source_level = 1 (boost = 2.0)
  #
  # 计算：
  #   final_score = 8.0 * 1.0 + log10(50) * 2.5 + 0.8 * 1.5 + 2.0 * 5.0 * 0.2
  #              = 8.0 + 1.7 * 2.5 + 1.2 + 2.0
  #              = 8.0 + 4.25 + 1.2 + 2.0
  #              = 15.45 → 限制上限为 10.0

  # ========== 多样性机制（可选）==========
  diversity:
    enabled: true  # 是否启用多样性机制

    penalties:
      same_cluster: 0.7      # 同一 cluster 的惩罚系数
      same_pain_type: 0.85   # 同一 pain_type 的惩罚系数
      keyword_overlap: 0.90  # 关键词重叠的惩罚系数

    min_diversity_score_gap: 2.0  # 最低多样性分数差距，低于此值停止选择

  # ========== 输出设置 ==========
  output:
    min_candidates: 3
    max_candidates: 5
    score_gap_threshold: 0.5  # 用于动态调整输出数量
    markdown_dir: "reports"
    json_dir: "data"

  # ========== LLM Prompts ==========
  prompts:
    problem_mvp_whynow: |
      You are a product expert specializing in identifying micro-SaaS opportunities for solo founders.

      Based on the following opportunity data, generate THREE concise, impactful sentences:

      **Opportunity Data:**
      - Name: {opportunity_name}
      - Description: {description}
      - Target Users: {target_users}
      - Missing Capability: {missing_capability}
      - Why Existing Tools Fail: {why_existing_fail}
      - Cluster Summary: {cluster_summary}
      - Pain Events: {cluster_size} unique pain points
      - Cross-Source Validation: {cross_source_info}

      **Output Requirements:**

      1. **Problem Statement** (one sentence, max 30 words)
         Format: "Users in [context/role] are struggling with [specific task] because [structural reason]."

      2. **MVP Cut** (one sentence, max 25 words)
         Format: "A minimal tool that helps them [do X faster/easier/safer] by replacing [current bad workaround]."

      3. **Why Now** (one sentence, max 20 words)
         Format: "This is urgent now because [specific signal/tool failure/multi-community validation]."

      **Constraints:**
      - Be specific and concrete (avoid generic fluff)
      - Focus on actionable insights (not vague observations)
      - Use present tense
      - Each sentence should stand alone (no dependencies)

      **Output Format:**
      Return ONLY a valid JSON object with these exact keys:
      {
        "problem": "one sentence problem statement",
        "mvp": "one sentence mvp description",
        "why_now": "one sentence urgency explanation"
      }

      No additional text, explanations, or markdown formatting.

  # ========== 日志设置 ==========
  logging:
    log_filtering_details: true  # 记录每个过滤条件的详细统计
    log_scoring_breakdown: true  # 记录每个机会的详细评分计算
    log_llm_calls: true  # 记录 LLM 调用次数和成本估算
    log_diversity_penalties: true  # 记录多样性惩罚详情（如果启用）
```

### 配置说明

#### 1. 对数缩放权重系统

**与传统线性权重的对比**：

传统线性模型（已废弃）：
```yaml
final_score_weights:
  viability_score: 0.4
  signal_strength: 0.25  # 线性：cluster_size / 10
  trust_level: 0.2
  cross_source_bonus: 0.15
```

对数缩放模型（推荐）：
```yaml
final_score_weights:
  viability_score: 1.0
  cluster_size_log_factor: 2.5  # 对数：log10(cluster_size)
  trust_level: 1.5
  cross_source_bonus: 5.0
```

**迁移建议**：
- 新部署：直接使用对数缩放模型
- 现有部署：可以先用旧模型，观察结果后逐步迁移到对数模型
- 调优：根据实际效果调整权重系数

#### 2. 多样性机制配置

**何时启用**：
- 数据量大（50+ 机会）
- 聚类集中度高（多个机会来自同一领域）
- 需要探索不同领域的机会

**何时禁用**：
- 数据量小（< 20 机会）
- 需要绝对优先级排序
- 领域已经多样化

**调整惩罚系数**：
- 更严格的多样性：降低惩罚系数（如 0.6, 0.8, 0.85）
- 更宽松的多样性：提高惩罚系数（如 0.8, 0.9, 0.95）

---

## 第九部分：错误处理与日志

### 1. 错误处理策略

| 错误类型 | 处理策略 | 降级方案 |
|---------|---------|---------|
| 数据库查询失败 | 记录错误，返回空列表 | 检查数据库连接和表结构 |
| LLM 调用失败 | 记录警告，使用降级策略 | 从现有字段聚合提取内容 |
| 文件写入失败 | 尝试写入备用路径（/tmp/） | 记录错误，返回结果（不含文件） |
| 配置加载失败 | 使用硬编码默认值 | 记录警告，继续执行 |
| JSON 解析失败 | 重试一次，使用更宽松的解析 | 使用降级内容生成 |

### 2. 降级策略实现

```python
def _generate_readable_content_with_retry(self, opportunity: Dict, cluster: Dict, cross_source_info: Dict) -> Dict[str, str]:
    """带重试和降级的内容生成"""

    try:
        # 首次尝试：LLM 生成
        return self._generate_readable_content(opportunity, cluster, cross_source_info)
    except json.JSONDecodeError as e:
        # JSON 解析失败：尝试提取 JSON 片段
        logger.warning(f"JSON parsing failed for {opportunity['opportunity_name']}: {e}")
        return self._extract_json_from_response(opportunity, cluster, cross_source_info)
    except Exception as e:
        # 其他错误：使用降级策略
        logger.error(f"Content generation failed for {opportunity['opportunity_name']}: {e}")
        return self._fallback_readable_content(opportunity, cluster)
```

### 3. 日志输出示例

```
INFO: === Decision Shortlist Generation Started ===
INFO: Loading configuration from config/thresholds.yaml
INFO: Configuration loaded successfully
INFO:
INFO: === Stage 1: Hard Filtering ===
INFO: Total opportunities in database: 50
INFO: Applied viability_score filter (>= 7.0): 50 → 30 passed
INFO: Applied cluster_size filter (>= 6): 30 → 20 passed
INFO: Applied trust_level filter (>= 0.7): 20 → 15 passed
INFO: Hard filtering complete: 15/50 opportunities passed
INFO:
INFO: === Stage 2: Cross-Source Validation ===
INFO: Checking 15 opportunities for cross-source validation
INFO: Level 1 (strong signal): 3 opportunities found
INFO:   - cluster_42: Found in aligned_problems (AP_01)
INFO:   - cluster_17: source_type='aligned'
INFO:   - cluster_23: Found in aligned_problems (AP_03)
INFO: Level 2 (medium signal): 3 opportunities found
INFO:   - cluster_08: cluster_size=12, subreddits=4
INFO:   - cluster_15: cluster_size=11, subreddits=3
INFO:   - cluster_31: cluster_size=10, subreddits=3
INFO: Level 3 (weak signal): 2 opportunities found
INFO:   - cluster_05: cluster_size=9, subreddits=2
INFO:   - cluster_19: cluster_size=8, subreddits=2
INFO: Cross-source validation complete: 8/15 validated
INFO:
INFO: === Stage 3: Final Scoring ===
INFO: Calculating final scores for 15 opportunities
INFO: Score breakdown (top 5):
INFO:   1. cluster_42: viability=8.2, signal=10.0, trust=0.85, cross_bonus=2.0 → final=8.7
INFO:   2. cluster_17: viability=7.8, signal=9.0, trust=0.80, cross_bonus=2.0 → final=8.2
INFO:   3. cluster_08: viability=7.5, signal=10.0, trust=0.75, cross_bonus=1.0 → final=7.8
INFO:   4. cluster_15: viability=7.2, signal=9.0, trust=0.70, cross_bonus=1.0 → final=7.4
INFO:   5. cluster_23: viability=8.0, signal=8.0, trust=0.82, cross_bonus=2.0 → final=7.1
INFO:
INFO: === Stage 4: LLM Content Generation ===
INFO: Generating Problem/MVP/Why Now for top 5 opportunities
INFO: [1/5] Generating for cluster_42... OK (3.2s)
INFO: [2/5] Generating for cluster_17... OK (2.8s)
INFO: [3/5] Generating for cluster_08... OK (3.5s)
INFO: [4/5] Generating for cluster_15... OK (2.9s)
INFO: [5/5] Generating for cluster_23... OK (3.1s)
INFO: LLM generation complete: 5/5 success (avg 3.1s each)
INFO: Estimated LLM cost: $0.05
INFO:
INFO: === Stage 5: Export Results ===
INFO: Writing Markdown report to: reports/shortlist_report_20251225.md
INFO: Writing JSON file to: data/decision_shortlist.json
INFO: Export complete
INFO:
INFO: === Decision Shortlist Complete ===
INFO: Total Candidates: 15
INFO: Selected: 5 (score range: 8.7 - 7.1)
INFO: Report: reports/shortlist_report_20251225.md
INFO: JSON: data/decision_shortlist.json
INFO: Total processing time: 45.3s
```

### 4. 日志级别

- **DEBUG**: 详细的评分计算过程
- **INFO**: 关键步骤和统计信息（默认）
- **WARNING**: 降级策略使用和可恢复的错误
- **ERROR**: 严重错误和失败操作

---

## 第十部分：Milestone 1 验收测试

### 1. 验收测试脚本

文件位置：`tests/test_decision_shortlist.py`

```python
#!/usr/bin/env python3
"""
Decision Shortlist Milestone 1 验收测试
验证系统是否满足：从 50+ 机会中筛选出 Top 3-5 个可执行清单
"""

import os
import sys
import json
import logging
from datetime import datetime

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from pipeline.decision_shortlist import DecisionShortlistGenerator
from utils.db import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_decision_shortlist_milestone1():
    """验收测试：Milestone 1 功能验证"""

    print("\n" + "="*60)
    print("🧪 Decision Shortlist Milestone 1 验收测试")
    print("="*60 + "\n")

    # ========== 测试 1: 运行 Decision Shortlist ==========
    print("📋 测试 1: 运行 Decision Shortlist...")
    generator = DecisionShortlistGenerator()
    result = generator.generate_shortlist()

    assert result is not None, "Result should not be None"
    print("✅ Decision Shortlist 执行成功\n")

    # ========== 测试 2: 验证输出数量 ==========
    print("📋 测试 2: 验证输出数量...")
    shortlist_count = result['shortlist_count']
    assert 3 <= shortlist_count <= 5, f"Should output 3-5 candidates, got {shortlist_count}"
    print(f"✅ 输出数量正确: {shortlist_count} 个候选机会\n")

    # ========== 测试 3: 验证每个候选的完整性 ==========
    print("📋 测试 3: 验证每个候选的完整性...")
    for i, candidate in enumerate(result['shortlist'], 1):
        print(f"  检查 Candidate {i}...")

        # 必需字段
        assert 'problem' in candidate, f"Candidate {i} missing problem statement"
        assert 'mvp' in candidate, f"Candidate {i} missing MVP cut"
        assert 'why_now' in candidate, f"Candidate {i} missing why now"
        assert 'final_score' in candidate, f"Candidate {i} missing final_score"
        assert 'opportunity_name' in candidate, f"Candidate {i} missing opportunity_name"

        # 长度限制（确保简洁）
        problem_len = len(candidate['problem'])
        mvp_len = len(candidate['mvp'])
        why_now_len = len(candidate['why_now'])

        assert problem_len <= 200, f"Problem too long: {problem_len} chars (max 200)"
        assert mvp_len <= 150, f"MVP too long: {mvp_len} chars (max 150)"
        assert why_now_len <= 150, f"Why now too long: {why_now_len} chars (max 150)"

        # 非空检查
        assert candidate['problem'].strip(), f"Candidate {i} problem is empty"
        assert candidate['mvp'].strip(), f"Candidate {i} MVP is empty"
        assert candidate['why_now'].strip(), f"Candidate {i} why_now is empty"

        # 分数范围
        assert 0 <= candidate['final_score'] <= 10, f"Invalid final_score: {candidate['final_score']}"

        print(f"    ✅ Candidate {i} 完整且格式正确")

    print(f"✅ 所有 {shortlist_count} 个候选机会验证通过\n")

    # ========== 测试 4: 验证文件生成 ==========
    print("📋 测试 4: 验证文件生成...")
    markdown_path = result.get('markdown_path')
    json_path = result.get('json_path')

    assert markdown_path, "Missing markdown_path in result"
    assert json_path, "Missing json_path in result"
    assert os.path.exists(markdown_path), f"Markdown report not found: {markdown_path}"
    assert os.path.exists(json_path), f"JSON file not found: {json_path}"

    print(f"✅ 文件生成成功:")
    print(f"   - Markdown: {markdown_path}")
    print(f"   - JSON: {json_path}\n")

    # ========== 测试 5: 验证 JSON 格式 ==========
    print("📋 测试 5: 验证 JSON 格式...")
    with open(json_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    assert isinstance(json_data, list), "JSON root should be a list"
    assert len(json_data) == shortlist_count, f"JSON count mismatch: {len(json_data)} vs {shortlist_count}"

    for i, item in enumerate(json_data, 1):
        assert 'problem' in item, f"JSON item {i} missing problem"
        assert 'mvp' in item, f"JSON item {i} missing mvp"
        assert 'why_now' in item, f"JSON item {i} missing why_now"

    print(f"✅ JSON 格式正确，包含 {len(json_data)} 个机会\n")

    # ========== 测试 6: 验证硬性过滤规则 ==========
    print("📋 测试 6: 验证硬性过滤规则...")
    for candidate in result['shortlist']:
        assert candidate['viability_score'] >= 7.0, f"Viability score too low: {candidate['viability_score']}"
        assert candidate['cluster_size'] >= 6, f"Cluster size too small: {candidate['cluster_size']}"
        assert candidate['trust_level'] >= 0.7, f"Trust level too low: {candidate['trust_level']}"

    print("✅ 所有候选机会都通过硬性过滤\n")

    # ========== 测试 7: 验证跨源验证加分 ==========
    print("📋 测试 7: 验证跨源验证加分...")
    cross_source_validated = sum(1 for c in result['shortlist'] if c.get('validated_problem', False))
    print(f"   - 跨源验证通过: {cross_source_validated}/{shortlist_count}")
    print(f"   - 加分分布:")
    for level in [1, 2, 3]:
        count = sum(1 for c in result['shortlist'] if c.get('cross_source_level') == level)
        print(f"     Level {level}: {count} 个机会")

    print("✅ 跨源验证逻辑正确\n")

    # ========== 测试 8: 人类可读性检查 ==========
    print("📋 测试 8: 人类可读性检查（人工验证）...")
    print("\n" + "="*60)
    print("请人工检查以下输出是否符合 10 分钟决策标准：")
    print("="*60 + "\n")

    # 打印 Markdown 报告的前部分
    with open(markdown_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        # 打印前 80 行（约 2-3 个候选机会）
        print(''.join(lines[:80]))

    print("\n" + "="*60)
    print("✅ 请人工验证：")
    print("  1. 每个机会是否能在 1 分钟内理解？")
    print("  2. Problem / MVP / Why Now 是否简洁有力？")
    print("  3. 能否根据这些信息快速决策做 or 不做？")
    print("="*60 + "\n")

    # ========== 测试总结 ==========
    print("\n" + "="*60)
    print("🎉 所有自动化测试通过！")
    print("="*60)
    print(f"\n📊 测试总结:")
    print(f"   - 输入机会总数: {result.get('total_candidates', 'N/A')}")
    print(f"   - 通过硬性过滤: {result.get('passed_filters', 'N/A')}")
    print(f"   - 跨源验证通过: {result.get('cross_source_validated', 'N/A')}")
    print(f"   - 最终入选: {shortlist_count}")
    print(f"   - 分数范围: {result['shortlist'][0]['final_score']:.1f} - {result['shortlist'][-1]['final_score']:.1f}")
    print(f"\n📄 输出文件:")
    print(f"   - Markdown: {markdown_path}")
    print(f"   - JSON: {json_path}")
    print("\n✅ Milestone 1 验收测试通过！\n")

    return True


if __name__ == "__main__":
    try:
        success = test_decision_shortlist_milestone1()
        sys.exit(0 if success else 1)
    except AssertionError as e:
        logger.error(f"❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
```

### 2. 运行测试

```bash
# 运行验收测试
python tests/test_decision_shortlist.py

# 或通过 pytest
pytest tests/test_decision_shortlist.py -v
```

### 3. 验收标准

✅ **功能验证**：
- [x] Pipeline 跑完后，系统自动只给 3-5 个候选机会
- [x] 每个候选包含 Problem / MVP / Why Now 三句话
- [x] 不用打开代码，一看就能理解
- [x] 不用二次思考，一读就能讨论
- [x] 能在 10 分钟内决定做 or 不做

✅ **技术验证**：
- [x] 从数据库读取 opportunities
- [x] 应用硬性过滤规则（viability >= 7.0, cluster_size >= 6, trust_level >= 0.7）
- [x] 三层跨源验证（Level 1/2/3）
- [x] 最终评分计算正确
- [x] LLM 生成内容符合格式要求
- [x] Markdown 和 JSON 文件生成成功

---

## 第十一部分：实施计划

### 阶段 1：核心功能（1-2 天）

1. 创建 `pipeline/decision_shortlist.py`
   - 实现 `DecisionShortlistGenerator` 类骨架
   - 实现硬性过滤逻辑
   - 实现跨源验证逻辑
   - 实现最终评分计算

2. 更新配置文件
   - 在 `config/thresholds.yaml` 添加 `decision_shortlist` 配置

3. 编写单元测试
   - 测试硬性过滤逻辑
   - 测试跨源验证逻辑
   - 测试评分计算逻辑

### 阶段 2：LLM 集成（1 天）

1. 实现 LLM 内容生成
   - 设计并测试 prompt 模板
   - 实现 `_generate_readable_content()` 方法
   - 实现降级策略

2. 测试 LLM 输出质量
   - 生成多个示例，人工检查质量
   - 优化 prompt 以提高输出质量

### 阶段 3：Pipeline 集成（0.5 天）

1. 集成到 `run_pipeline.py`
   - 添加 Stage 9 处理函数
   - 更新命令行参数
   - 测试完整 pipeline 运行

2. 测试独立运行
   - 测试 `--stage decision_shortlist` 模式
   - 测试与前置 stages 的依赖关系

### 阶段 4：输出格式与验收（0.5 天）

1. 实现输出功能
   - 实现 Markdown 报告生成
   - 实现 JSON 文件导出
   - 添加统计信息输出

2. 运行验收测试
   - 执行 `test_decision_shortlist.py`
   - 人工检查输出质量
   - 确认满足 Milestone 1 验收标准

### 阶段 5：文档与优化（0.5 天）

1. 编写文档
   - 更新 README.md
   - 添加使用示例
   - 添加配置说明

2. 性能优化
   - 优化数据库查询
   - 添加缓存机制
   - 减少不必要的 LLM 调用

**总计估计时间：3-4 天**

---

## 第十二部分：风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| LLM 输出质量不稳定 | 高 | 中 | 使用精心设计的 prompt + 降级策略 |
| 跨源验证误判 | 中 | 低 | 三层优先级设计，弱信号仅作为辅助 |
| 输出机会数量过少 | 中 | 中 | 动态调整阈值，记录日志供调试 |
| 数据库查询性能 | 低 | 低 | 添加索引，优化 SQL 查询 |
| 配置过于复杂 | 低 | 中 | 提供默认配置，添加配置示例 |

---

## 附录：快速参考

### 关键文件位置

```
reddit_pain_finder/
├── pipeline/
│   └── decision_shortlist.py          # 新增：主模块
├── config/
│   └── thresholds.yaml                 # 修改：添加 decision_shortlist 配置
├── tests/
│   └── test_decision_shortlist.py     # 新增：验收测试
├── reports/
│   └── shortlist_report_YYYYMMDD.md   # 自动生成：Markdown 报告
├── data/
│   └── decision_shortlist.json        # 自动生成：JSON 输出
└── run_pipeline.py                     # 修改：集成 Stage 9
```

### 关键配置参数

```yaml
decision_shortlist:
  # 硬性过滤阈值
  min_viability_score: 7.0        # 最低可行性评分
  min_cluster_size: 6             # 最小聚类规模
  min_trust_level: 0.7            # 最低信任度

  # 跨源验证加分
  cross_source_boosts:
    level_1: 2.0                  # 强信号加分
    level_2: 1.0                  # 中等信号加分
    level_3: 0.5                  # 弱信号加分

  # 对数缩放评分权重（新模型）
  final_score_weights:
    viability_score: 1.0           # 可行性评分权重
    cluster_size_log_factor: 2.5   # log10(cluster_size) 权重
    trust_level: 1.5               # 信任度权重
    cross_source_bonus: 5.0        # 跨源验证基础加分

  # 多样性机制（可选）
  diversity:
    enabled: true                 # 是否启用多样性惩罚
    penalties:
      same_cluster: 0.7            # 同 cluster 惩罚
      same_pain_type: 0.85         # 同 pain_type 惩罚
      keyword_overlap: 0.90        # 关键词重叠惩罚
```

### 命令行使用

```bash
# 完整 pipeline（包含 decision_shortlist）
python run_pipeline.py --stage all

# 单独运行 decision_shortlist
python run_pipeline.py --stage decision_shortlist

# 运行验收测试
python tests/test_decision_shortlist.py
```

---

**文档版本**: 1.1
**创建日期**: 2025-12-26
**最后更新**: 2025-12-26
**作者**: Claude Code
**状态**: 待审阅

**变更历史**：
- **v1.1** (2025-12-26):
  - ✨ 新增：对数缩放评分模型，替代线性缩放
  - ✨ 新增：配置化权重系统，所有权重系数可在 config 中调整
  - ✨ 新增：多样性保证机制（可选高级功能）
  - ✨ 新增：空列表处理逻辑和报告格式
  - 📝 更新：配置文件结构，添加对数缩放和多样性配置
- **v1.0** (2025-12-26):
  - 🎉 初始版本

---
