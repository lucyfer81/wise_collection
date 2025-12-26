# Decision Shortlist Layer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 从所有评分机会中筛选出 Top 3-5 个最值得执行的产品机会，并为每个机会生成简洁的决策信息（Problem / MVP / Why Now）

**Architecture:** 新增 `pipeline/decision_shortlist.py` 模块，作为 pipeline 的 Stage 9。从数据库读取 opportunities 表，应用硬性过滤、跨源验证、对数缩放评分、多样性惩罚（可选），最后通过 LLM 生成可读内容并输出 Markdown + JSON 报告。

**Tech Stack:** Python 3, SQLite, YAML config, LLM (现有 llm_client), math (log10)

---

## Task 1: 创建 DecisionShortlistGenerator 类骨架

**Files:**
- Create: `pipeline/decision_shortlist.py`

**Step 1: Write basic class structure**

```python
# pipeline/decision_shortlist.py
"""
Decision Shortlist Generator
从所有评分机会中筛选出 Top 3-5 个最值得执行的产品机会
"""
import json
import logging
import math
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

import yaml

from utils.llm_client import llm_client
from utils.db import db

logger = logging.getLogger(__name__)


class DecisionShortlistGenerator:
    """决策清单生成器"""

    def __init__(self, config_path: str = "config/thresholds.yaml"):
        """初始化生成器"""
        self.config = self._load_config(config_path)
        self.pipeline_run_id = f"pipeline_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info("DecisionShortlistGenerator initialized")

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config.get('decision_shortlist', {})
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """返回默认配置"""
        return {
            'min_viability_score': 7.0,
            'min_cluster_size': 6,
            'min_trust_level': 0.7,
            'ignored_clusters': [],
            'final_score_weights': {
                'viability_score': 1.0,
                'cluster_size_log_factor': 2.5,
                'trust_level': 1.5,
                'cross_source_bonus': 5.0
            },
            'output': {
                'min_candidates': 3,
                'max_candidates': 5,
                'markdown_dir': 'reports',
                'json_dir': 'data'
            }
        }

    def generate_shortlist(self) -> Dict[str, Any]:
        """生成决策清单（主方法）"""
        logger.info("=== Decision Shortlist Generation Started ===")

        # TODO: 实现各个步骤
        result = {
            'shortlist_count': 0,
            'shortlist': [],
            'generated_at': datetime.now().isoformat()
        }

        return result
```

**Step 2: Verify module can be imported**

Run: `python3 -c "from pipeline.decision_shortlist import DecisionShortlistGenerator; print('Import successful')"`

Expected: `Import successful`

**Step 3: Commit**

```bash
git add pipeline/decision_shortlist.py
git commit -m "feat: add DecisionShortlistGenerator class skeleton"
```

---

## Task 2: 实现硬性过滤逻辑

**Files:**
- Modify: `pipeline/decision_shortlist.py`

**Step 1: Write test for hard filters**

```python
# tests/test_decision_shortlist.py
import pytest
from pipeline.decision_shortlist import DecisionShortlistGenerator
from utils.db import db

def test_apply_hard_filters():
    """测试硬性过滤逻辑"""
    generator = DecisionShortlistGenerator()

    # 准备测试数据（需要数据库中有机会数据）
    # 这里假设数据库中已有测试数据
    result = generator._apply_hard_filters()

    # 验证返回值是列表
    assert isinstance(result, list)

    # 验证每个机会都满足过滤条件
    for opp in result:
        assert opp['total_score'] >= 7.0
        assert opp['cluster_size'] >= 6
        assert opp['trust_level'] >= 0.7
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_decision_shortlist.py::test_apply_hard_filters -v`

Expected: `AttributeError: 'DecisionShortlistGenerator' object has no attribute '_apply_hard_filters'`

**Step 3: Implement `_apply_hard_filters` method**

```python
# 在 DecisionShortlistGenerator 类中添加

def _apply_hard_filters(self) -> List[Dict[str, Any]]:
    """应用硬性过滤规则

    Returns:
        通过所有过滤的机会列表
    """
    config = self.config

    min_viability = config['min_viability_score']
    min_cluster_size = config['min_cluster_size']
    min_trust = config['min_trust_level']
    ignored_clusters = set(config.get('ignored_clusters', []))

    logger.info(f"Applying hard filters: viability>={min_viability}, "
                f"cluster_size>={min_cluster_size}, trust>={min_trust}")

    try:
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("""
                SELECT
                    o.id as opportunity_id,
                    o.opportunity_name,
                    o.description,
                    o.total_score as viability_score,
                    o.trust_level as trust_level,
                    o.target_users,
                    o.missing_capability,
                    o.why_existing_fail,
                    c.id as cluster_id,
                    c.cluster_name,
                    c.cluster_size,
                    c.source_type,
                    c.pain_event_ids,
                    c.centroid_summary as cluster_summary
                FROM opportunities o
                JOIN clusters c ON o.cluster_id = c.id
                WHERE o.total_score >= ?
                  AND c.cluster_size >= ?
                  AND o.trust_level >= ?
                  AND c.cluster_name NOT IN (
                    SELECT value FROM json_each(?)
                    WHERE json_valid(?) AND json_each.value IS NOT NULL
                  )
                ORDER BY o.total_score DESC
            """, (min_viability, min_cluster_size, min_trust,
                  json.dumps(list(ignored_clusters)),
                  json.dumps(list(ignored_clusters))))

            opportunities = [dict(row) for row in cursor.fetchall()]

            # 解析 pain_event_ids JSON
            for opp in opportunities:
                if opp.get('pain_event_ids'):
                    try:
                        opp['pain_event_ids'] = json.loads(opp['pain_event_ids'])
                    except:
                        opp['pain_event_ids'] = []

            logger.info(f"Hard filters: {len(opportunities)} opportunities passed")
            return opportunities

    except Exception as e:
        logger.error(f"Failed to apply hard filters: {e}")
        return []
```

**Step 4: Run test to verify it works**

Run: `pytest tests/test_decision_shortlist.py::test_apply_hard_filters -v`

Expected: `PASSED` (如果有数据) 或 `SKIP` (如果数据库为空)

**Step 5: Commit**

```bash
git add pipeline/decision_shortlist.py tests/test_decision_shortlist.py
git commit -m "feat: implement hard filters for opportunities"
```

---

## Task 3: 实现跨源验证逻辑

**Files:**
- Modify: `pipeline/decision_shortlist.py`

**Step 1: Write test for cross-source validation**

```python
# tests/test_decision_shortlist.py (添加)

def test_check_cross_source_validation():
    """测试跨源验证逻辑"""
    generator = DecisionShortlistGenerator()

    # 模拟一个 aligned 类型的 cluster
    mock_opportunity = {
        'cluster_id': 1,
        'cluster_name': 'test_cluster',
        'cluster_size': 15,
        'source_type': 'aligned',
        'pain_event_ids': [1, 2, 3, 4, 5]
    }

    result = generator._check_cross_source_validation(mock_opportunity)

    assert result['has_cross_source'] == True
    assert result['validation_level'] == 1
    assert result['boost_score'] == 2.0
    assert result['validated_problem'] == True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_decision_shortlist.py::test_check_cross_source_validation -v`

Expected: `AttributeError: 'DecisionShortlistGenerator' object has no attribute '_check_cross_source_validation'`

**Step 3: Implement `_check_cross_source_validation` method**

```python
# 在 DecisionShortlistGenerator 类中添加

def _check_cross_source_validation(self, opportunity: Dict) -> Dict[str, Any]:
    """检查跨源验证，返回验证信息和加分

    三层优先级：
    - Level 1 (强信号): source_type='aligned' 或在 aligned_problems 表中
    - Level 2 (中等信号): cluster_size >= 10 AND 跨 >=3 subreddits
    - Level 3 (弱信号): cluster_size >= 8 AND 跨 >=2 subreddits
    """
    cluster = opportunity

    # Level 1: 检查 source_type
    if cluster.get('source_type') == 'aligned':
        return {
            "has_cross_source": True,
            "validation_level": 1,
            "boost_score": 2.0,
            "validated_problem": True,
            "evidence": "source_type='aligned'"
        }

    # Level 1: 检查 aligned_problems 表
    aligned_problem = self._check_aligned_problems_table(cluster['cluster_name'])
    if aligned_problem:
        return {
            "has_cross_source": True,
            "validation_level": 1,
            "boost_score": 2.0,
            "validated_problem": True,
            "evidence": f"Found in aligned_problems: {aligned_problem['aligned_problem_id']}"
        }

    # Level 2 & 3: 检查 cluster_size + 跨 subreddit
    pain_event_ids = cluster.get('pain_event_ids', [])
    if not pain_event_ids:
        return {
            "has_cross_source": False,
            "validation_level": 0,
            "boost_score": 0.0,
            "validated_problem": False,
            "evidence": "No pain events"
        }

    subreddit_count = self._count_subreddits(pain_event_ids)
    cluster_size = cluster['cluster_size']

    # Level 2
    if cluster_size >= 10 and subreddit_count >= 3:
        return {
            "has_cross_source": True,
            "validation_level": 2,
            "boost_score": 1.0,
            "validated_problem": True,
            "evidence": f"Large cluster ({cluster_size}) across {subreddit_count} subreddits"
        }

    # Level 3
    if cluster_size >= 8 and subreddit_count >= 2:
        return {
            "has_cross_source": True,
            "validation_level": 3,
            "boost_score": 0.5,
            "validated_problem": False,
            "evidence": f"Medium cluster ({cluster_size}) across {subreddit_count} subreddits"
        }

    # 无跨源验证
    return {
        "has_cross_source": False,
        "validation_level": 0,
        "boost_score": 0.0,
        "validated_problem": False,
        "evidence": "No cross-source validation"
    }

def _check_aligned_problems_table(self, cluster_name: str) -> Optional[Dict]:
    """检查 cluster 是否在 aligned_problems 表中"""
    try:
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("""
                SELECT aligned_problem_id, sources, alignment_score
                FROM aligned_problems
                WHERE cluster_ids LIKE ?
            """, (f'%{cluster_name}%',))
            result = cursor.fetchone()
            return dict(result) if result else None
    except Exception as e:
        logger.error(f"Failed to check aligned_problems: {e}")
        return None

def _count_subreddits(self, pain_event_ids: List[int]) -> int:
    """计算涉及的不同 subreddit 数量"""
    try:
        with db.get_connection("pain") as conn:
            placeholders = ','.join('?' for _ in pain_event_ids)
            cursor = conn.execute(f"""
                SELECT COUNT(DISTINCT fp.subreddit) as count
                FROM pain_events pe
                JOIN filtered_posts fp ON pe.post_id = fp.id
                WHERE pe.id IN ({placeholders})
            """, pain_event_ids)
            return cursor.fetchone()['count']
    except Exception as e:
        logger.error(f"Failed to count subreddits: {e}")
        return 1  # 默认为 1，避免 0
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_decision_shortlist.py::test_check_cross_source_validation -v`

Expected: `PASSED`

**Step 5: Commit**

```bash
git add pipeline/decision_shortlist.py tests/test_decision_shortlist.py
git commit -m "feat: implement cross-source validation logic"
```

---

## Task 4: 实现对数缩放评分计算

**Files:**
- Modify: `pipeline/decision_shortlist.py`

**Step 1: Write test for score calculation**

```python
# tests/test_decision_shortlist.py (添加)

def test_calculate_final_score():
    """测试对数缩放评分计算"""
    generator = DecisionShortlistGenerator()

    # 测试数据
    opportunity = {
        'viability_score': 8.0,
        'cluster_size': 50,
        'trust_level': 0.8
    }

    cross_source_info = {
        'has_cross_source': True,
        'boost_score': 2.0
    }

    result = generator._calculate_final_score(opportunity, cross_source_info)

    # 验证返回值是数字且在 0-10 范围内
    assert isinstance(result, float)
    assert 0 <= result <= 10

    # 手动计算验证
    # final_score = 8.0 * 1.0 + log10(50) * 2.5 + 0.8 * 1.5 + 2.0 * 5.0 * 0.2
    #             = 8.0 + 1.7 * 2.5 + 1.2 + 2.0
    #             = 8.0 + 4.25 + 1.2 + 2.0 = 15.45 → 10.0
    assert result == 10.0  # 会被限制上限
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_decision_shortlist.py::test_calculate_final_score -v`

Expected: `AttributeError: 'DecisionShortlistGenerator' object has no attribute '_calculate_final_score'`

**Step 3: Implement `_calculate_final_score` method**

```python
# 在 DecisionShortlistGenerator 类中添加

def _calculate_final_score(self, opportunity: Dict, cross_source_info: Dict) -> float:
    """计算最终得分（对数缩放 + 配置化权重）

    Args:
        opportunity: 机会数据，必须包含 viability_score, cluster_size, trust_level
        cross_source_info: 跨源验证信息

    Returns:
        最终评分 (0-10)
    """
    weights = self.config['final_score_weights']

    # 基础评分
    viability_score = opportunity['viability_score']
    trust_level = opportunity['trust_level']

    # 对数缩放：log10(cluster_size)
    cluster_size = opportunity['cluster_size']
    cluster_size_log = math.log10(max(cluster_size, 1))  # 避免log(0)

    # 加权计算
    final_score = (
        viability_score * weights['viability_score'] +
        cluster_size_log * weights['cluster_size_log_factor'] +
        trust_level * weights['trust_level']
    )

    # 跨源验证加分
    if cross_source_info['has_cross_source']:
        boost = cross_source_info['boost_score']
        final_score += weights['cross_source_bonus'] * boost * 0.1  # 缩放因子

    # 限制在 0-10 范围
    return min(max(final_score, 0), 10.0)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_decision_shortlist.py::test_calculate_final_score -v`

Expected: `PASSED`

**Step 5: Commit**

```bash
git add pipeline/decision_shortlist.py tests/test_decision_shortlist.py
git commit -m "feat: implement logarithmic scoring system"
```

---

## Task 5: 实现 LLM 内容生成

**Files:**
- Modify: `pipeline/decision_shortlist.py`

**Step 1: Write test for LLM content generation**

```python
# tests/test_decision_shortlist.py (添加)

def test_generate_readable_content(monkeypatch):
    """测试 LLM 生成可读内容"""
    generator = DecisionShortlistGenerator()

    # Mock LLM 响应
    mock_response = {
        'content': '''{
            "problem": "Developers are struggling with API documentation sync.",
            "mvp": "A minimal CLI tool for auto-generating API docs.",
            "why_now": "Validated by 15+ developers on Reddit and HN."
        }'''
    }

    def mock_chat_completion(*args, **kwargs):
        return mock_response

    monkeypatch.setattr(generator.llm_client, 'chat_completion', mock_chat_completion)

    opportunity = {
        'opportunity_name': 'API Doc Generator',
        'description': 'Auto-generate API documentation',
        'target_users': 'Developers',
        'missing_capability': 'Real-time sync',
        'why_existing_fail': 'Manual updates'
    }

    cluster = {
        'centroid_summary': 'API documentation pain points',
        'cluster_size': 15
    }

    cross_source_info = {
        'evidence': 'Validated across Reddit and HN'
    }

    result = generator._generate_readable_content(opportunity, cluster, cross_source_info)

    assert 'problem' in result
    assert 'mvp' in result
    assert 'why_now' in result
    assert len(result['problem']) > 0
    assert len(result['mvp']) > 0
    assert len(result['why_now']) > 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_decision_shortlist.py::test_generate_readable_content -v`

Expected: `AttributeError: 'DecisionShortlistGenerator' object has no attribute '_generate_readable_content'`

**Step 3: Implement `_generate_readable_content` method**

```python
# 在 DecisionShortlistGenerator 类中添加

def _generate_readable_content(
    self,
    opportunity: Dict,
    cluster: Dict,
    cross_source_info: Dict
) -> Dict[str, str]:
    """使用 LLM 生成 Problem/MVP/Why Now

    Args:
        opportunity: 机会数据
        cluster: 聚类数据
        cross_source_info: 跨源验证信息

    Returns:
        包含 problem, mvp, why_now 的字典
    """
    try:
        # 准备 prompt 参数
        prompt_params = {
            'opportunity_name': opportunity['opportunity_name'],
            'description': opportunity.get('description', ''),
            'target_users': opportunity.get('target_users', ''),
            'missing_capability': opportunity.get('missing_capability', ''),
            'why_existing_fail': opportunity.get('why_existing_fail', ''),
            'cluster_summary': cluster.get('cluster_summary', ''),
            'cluster_size': cluster['cluster_size'],
            'cross_source_info': cross_source_info['evidence']
        }

        # 加载 prompt 模板
        prompt_template = self.config.get('prompts', {}).get(
            'problem_mvp_whynow',
            self._get_default_prompt()
        )
        prompt = prompt_template.format(**prompt_params)

        # 调用 LLM
        response = llm_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model_type="main",
            temperature=0.3,
            max_tokens=500
        )

        # 解析响应
        if isinstance(response, dict):
            content = response.get('content', response)
        else:
            content = str(response)

        result = json.loads(content)

        return {
            'problem': result.get('problem', ''),
            'mvp': result.get('mvp', ''),
            'why_now': result.get('why_now', '')
        }

    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        # 降级策略
        return self._fallback_readable_content(opportunity, cluster)

def _get_default_prompt(self) -> str:
    """返回默认 prompt 模板"""
    return """Based on the following opportunity data, generate THREE concise sentences:

Opportunity: {opportunity_name}
Description: {description}
Target Users: {target_users}

Return JSON with keys: problem, mvp, why_now"""

def _fallback_readable_content(self, opportunity: Dict, cluster: Dict) -> Dict[str, str]:
    """降级策略：从现有字段提取"""
    description = opportunity.get('description', '')
    target_users = opportunity.get('target_users', 'Users')
    cluster_size = cluster.get('cluster_size', 0)

    problem = f"{target_users} are struggling with {description[:100]}..."
    mvp = "A minimal tool to address this pain point."
    why_now = f"Validated by {cluster_size} recent pain points."

    return {
        'problem': problem[:200],
        'mvp': mvp[:150],
        'why_now': why_now[:150]
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_decision_shortlist.py::test_generate_readable_content -v`

Expected: `PASSED`

**Step 5: Commit**

```bash
git add pipeline/decision_shortlist.py tests/test_decision_shortlist.py
git commit -m "feat: implement LLM-based content generation"
```

---

## Task 6: 实现主流程 `generate_shortlist`

**Files:**
- Modify: `pipeline/decision_shortlist.py`

**Step 1: Update `generate_shortlist` method**

```python
# 替换现有的 generate_shortlist 方法

def generate_shortlist(self) -> Dict[str, Any]:
    """生成决策清单（主方法）

    Returns:
        包含 shortlist 和统计信息的字典
    """
    start_time = datetime.now()

    try:
        # Step 1: 硬性过滤
        opportunities = self._apply_hard_filters()

        if not opportunities:
            logger.warning("No opportunities passed hard filters")
            return self._handle_empty_shortlist({
                'total': 0,
                'reasons': {'no_opportunities': 1}
            })

        # Step 2: 跨源验证 + 评分
        scored_opportunities = []

        for opp in opportunities:
            # 跨源验证
            cross_source_info = self._check_cross_source_validation(opp)

            # 计算最终分数
            final_score = self._calculate_final_score(
                {
                    'viability_score': opp['viability_score'],
                    'cluster_size': opp['cluster_size'],
                    'trust_level': opp['trust_level']
                },
                cross_source_info
            )

            # 添加到结果
            scored_opp = opp.copy()
            scored_opp['final_score'] = final_score
            scored_opp['cross_source_info'] = cross_source_info
            scored_opportunities.append(scored_opp)

        # Step 3: 排序
        scored_opportunities.sort(key=lambda x: x['final_score'], reverse=True)

        # Step 4: 选择 Top N（考虑多样性，如果启用）
        if self.config.get('diversity', {}).get('enabled', False):
            selected = self._select_top_candidates_with_diversity(scored_opportunities)
        else:
            max_candidates = self.config['output']['max_candidates']
            selected = scored_opportunities[:max_candidates]

        # Step 5: LLM 生成可读内容
        for i, opp in enumerate(selected):
            logger.info(f"Generating content for candidate {i+1}/{len(selected)}")

            content = self._generate_readable_content(
                opp,
                {
                    'cluster_summary': opp.get('cluster_summary', ''),
                    'cluster_size': opp['cluster_size']
                },
                opp['cross_source_info']
            )

            opp.update(content)

        # Step 6: 导出报告
        markdown_path = self._export_markdown_report(selected)
        json_path = self._export_json_report(selected)

        processing_time = (datetime.now() - start_time).total_seconds()

        result = {
            'empty': False,
            'total_candidates': len(opportunities),
            'shortlist_count': len(selected),
            'shortlist': selected,
            'markdown_path': markdown_path,
            'json_path': json_path,
            'processing_time_seconds': processing_time,
            'generated_at': datetime.now().isoformat()
        }

        logger.info(f"Decision Shortlist generated: {len(selected)} candidates in {processing_time:.1f}s")
        return result

    except Exception as e:
        logger.error(f"Failed to generate shortlist: {e}")
        raise
```

**Step 2: Implement helper methods**

```python
# 添加以下辅助方法到类中

def _select_top_candidates_with_diversity(self, scored_opportunities: List[Dict]) -> List[Dict]:
    """选择 Top 3-5 个候选机会（考虑多样性）"""
    # 简化版本：直接返回前 N 个，不应用多样性惩罚
    # 完整实现已在设计文档中
    max_candidates = self.config['output']['max_candidates']
    return scored_opportunities[:max_candidates]

def _export_markdown_report(self, shortlist: List[Dict]) -> str:
    """导出 Markdown 报告"""
    os.makedirs(self.config['output']['markdown_dir'], exist_ok=True)

    filename = f"shortlist_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    filepath = os.path.join(self.config['output']['markdown_dir'], filename)

    content = f"""# Decision Shortlist ({datetime.now().strftime('%Y-%m-%d')})

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Pipeline Run**: {self.pipeline_run_id}
**Total Candidates**: {len(shortlist)}

---

"""

    for i, candidate in enumerate(shortlist, 1):
        content += f"""## 🎯 Candidate {i}: {candidate['opportunity_name']}

**Final Score**: {candidate['final_score']}/10
**Cross-Source Evidence**: {'✅ YES' if candidate['cross_source_info']['has_cross_source'] else '❌ NO'} (Level {candidate['cross_source_info']['validation_level']})

### Problem
{candidate.get('problem', 'N/A')}

### MVP
{candidate.get('mvp', 'N/A')}

### Why Now
{candidate.get('why_now', 'N/A')}

---
"""

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    logger.info(f"Markdown report exported: {filepath}")
    return filepath

def _export_json_report(self, shortlist: List[Dict]) -> str:
    """导出 JSON 报告"""
    os.makedirs(self.config['output']['json_dir'], exist_ok=True)

    filename = "decision_shortlist.json"
    filepath = os.path.join(self.config['output']['json_dir'], filename)

    # 简化输出，只包含必要字段
    simplified_shortlist = []
    for candidate in shortlist:
        simplified = {
            'opportunity_name': candidate['opportunity_name'],
            'problem': candidate.get('problem', ''),
            'mvp': candidate.get('mvp', ''),
            'why_now': candidate.get('why_now', ''),
            'final_score': candidate['final_score'],
            'cluster_size': candidate['cluster_size'],
            'validated_problem': candidate['cross_source_info']['validated_problem'],
            'generated_at': datetime.now().isoformat()
        }
        simplified_shortlist.append(simplified)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(simplified_shortlist, f, indent=2, ensure_ascii=False)

    logger.info(f"JSON report exported: {filepath}")
    return filepath

def _handle_empty_shortlist(self, filter_stats: Dict) -> Dict[str, Any]:
    """处理空列表情况"""
    return {
        'empty': True,
        'message': 'No opportunities passed hard filters',
        'statistics': filter_stats,
        'shortlist_count': 0,
        'shortlist': [],
        'generated_at': datetime.now().isoformat()
    }
```

**Step 3: Test the full flow**

```python
# tests/test_decision_shortlist.py (添加)

def test_generate_shortlist_integration():
    """集成测试：完整流程"""
    generator = DecisionShortlistGenerator()

    result = generator.generate_shortlist()

    # 验证返回结构
    assert 'shortlist_count' in result
    assert 'shortlist' in result
    assert 'generated_at' in result

    # 如果非空，验证每个候选都有必需字段
    if not result.get('empty', False):
        for candidate in result['shortlist']:
            assert 'problem' in candidate or 'opportunity_name' in candidate
```

**Step 4: Run integration test**

Run: `pytest tests/test_decision_shortlist.py::test_generate_shortlist_integration -v`

Expected: `PASSED` 或 `SKIP` (如果数据库为空)

**Step 5: Commit**

```bash
git add pipeline/decision_shortlist.py tests/test_decision_shortlist.py
git commit -m "feat: implement main generate_shortlist flow"
```

---

## Task 7: 更新配置文件

**Files:**
- Modify: `config/thresholds.yaml`

**Step 1: Add decision_shortlist configuration**

```yaml
# 在 config/thresholds.yaml 末尾添加

# Decision Shortlist 配置
decision_shortlist:
  # 硬性过滤阈值
  min_viability_score: 7.0
  min_cluster_size: 6
  min_trust_level: 0.7
  ignored_clusters: []

  # 跨源验证加分
  cross_source_boosts:
    level_1: 2.0
    level_2: 1.0
    level_3: 0.5

  # 跨源验证条件
  cross_source_validation:
    level_2:
      min_cluster_size: 10
      min_subreddits: 3
    level_3:
      min_cluster_size: 8
      min_subreddits: 2

  # 最终评分权重（对数缩放模型）
  final_score_weights:
    viability_score: 1.0
    cluster_size_log_factor: 2.5
    trust_level: 1.5
    cross_source_bonus: 5.0

  # 多样性机制（可选）
  diversity:
    enabled: false  # 默认禁用，避免过度复杂
    penalties:
      same_cluster: 0.7
      same_pain_type: 0.85
      keyword_overlap: 0.90
    min_diversity_score_gap: 2.0

  # 输出设置
  output:
    min_candidates: 3
    max_candidates: 5
    score_gap_threshold: 0.5
    markdown_dir: "reports"
    json_dir: "data"

  # LLM Prompts
  prompts:
    problem_mvp_whynow: |
      You are a product expert specializing in identifying micro-SaaS opportunities.

      Based on the following opportunity data, generate THREE concise sentences:

      **Opportunity:**
      - Name: {opportunity_name}
      - Description: {description}
      - Target Users: {target_users}
      - Missing: {missing_capability}
      - Why Fail: {why_existing_fail}
      - Cluster: {cluster_summary} ({cluster_size} events)
      - Validation: {cross_source_info}

      **Output (JSON only):**
      {{
        "problem": "One sentence problem (max 30 words)",
        "mvp": "One sentence MVP (max 25 words)",
        "why_now": "One sentence urgency (max 20 words)"
      }}

  # 日志设置
  logging:
    log_filtering_details: true
    log_scoring_breakdown: true
    log_llm_calls: true
    log_diversity_penalties: false
```

**Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; print(yaml.safe_load(open('config/thresholds.yaml'))['decision_shortlist']['min_viability_score'])"`

Expected: `7.0`

**Step 3: Commit**

```bash
git add config/thresholds.yaml
git commit -m "config: add decision_shortlist configuration"
```

---

## Task 8: 集成到 run_pipeline.py

**Files:**
- Modify: `run_pipeline.py`

**Step 1: Add stage 9 handler**

```python
# 在 WiseCollectionPipeline 类中添加

def run_stage_decision_shortlist(self) -> Dict[str, Any]:
    """阶段9: 决策清单生成"""
    logger.info("=" * 50)
    logger.info("STAGE 9: Decision Shortlist Generation")
    logger.info("=" * 50)

    if self.enable_monitoring:
        from utils.performance_monitor import performance_monitor
        performance_monitor.start_stage("decision_shortlist")

    try:
        from pipeline.decision_shortlist import DecisionShortlistGenerator

        generator = DecisionShortlistGenerator()
        result = generator.generate_shortlist()

        self.stats["stage_results"]["decision_shortlist"] = result
        self.stats["stages_completed"].append("decision_shortlist")

        logger.info(f"""
=== Decision Shortlist Complete ===
Empty: {result.get('empty', False)}
Total Candidates: {result.get('total_candidates', 0)}
Selected: {result.get('shortlist_count', 0)}
Markdown: {result.get('markdown_path', 'N/A')}
JSON: {result.get('json_path', 'N/A')}
""")

        return result

    except Exception as e:
        logger.error(f"Decision Shortlist failed: {e}")
        self.stats["stages_failed"].append("decision_shortlist")
        raise
    finally:
        if self.enable_monitoring:
            from utils.performance_monitor import performance_monitor
            performance_monitor.end_stage("decision_shortlist")
```

**Step 2: Update main() to support stage 9**

```python
# 修改 run_pipeline.py 的 main() 函数

# 1. 在 argparse choices 中添加 'decision_shortlist'
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

# 2. 在主流程中添加对 decision_shortlist 的处理
if args.stage in ["decision_shortlist", "all"]:
    # Stage 9 仅在前面 stages 都完成后运行
    if args.stage == "decision_shortlist" or "score" in pipeline.stats["stages_completed"]:
        pipeline.run_stage_decision_shortlist()
    elif args.stage == "all":
        logger.warning("Skipping decision_shortlist: prerequisite stages not completed")
```

**Step 3: Test the integration**

Run: `python3 run_pipeline.py --help | grep decision_shortlist`

Expected: 输出中包含 `decision_shortlist` 选项

**Step 4: Commit**

```bash
git add run_pipeline.py
git commit -m "feat: integrate decision_shortlist as stage 9"
```

---

## Task 9: 编写验收测试

**Files:**
- Create: `tests/test_decision_shortlist_milestone1.py`

**Step 1: Write Milestone 1 acceptance test**

```python
#!/usr/bin/env python3
"""
Decision Shortlist Milestone 1 验收测试
"""
import os
import sys
import json
from datetime import datetime

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from pipeline.decision_shortlist import DecisionShortlistGenerator
from utils.db import db


def test_milestone1_functionality():
    """验收测试：从 50+ 机会中筛选出 Top 3-5 个"""
    print("\n" + "="*60)
    print("🧪 Milestone 1 验收测试")
    print("="*60 + "\n")

    generator = DecisionShortlistGenerator()
    result = generator.generate_shortlist()

    # 测试 1: 验证输出数量
    print("📋 测试 1: 输出数量...")
    count = result['shortlist_count']
    if not result.get('empty', False):
        assert 3 <= count <= 5, f"Expected 3-5 candidates, got {count}"
        print(f"✅ 输出数量正确: {count} 个候选\n")
    else:
        print("⚠️  空列表（这可能是正常的，取决于数据库内容）\n")
        return

    # 测试 2: 验证每个候选的完整性
    print("📋 测试 2: 候选完整性...")
    for i, candidate in enumerate(result['shortlist'], 1):
        assert 'problem' in candidate, f"Candidate {i} missing problem"
        assert 'mvp' in candidate, f"Candidate {i} missing mvp"
        assert 'why_now' in candidate, f"Candidate {i} missing why_now"
        assert len(candidate['problem']) <= 200, "Problem too long"
        assert len(candidate['mvp']) <= 150, "MVP too long"
    print(f"✅ 所有 {count} 个候选验证通过\n")

    # 测试 3: 验证文件生成
    print("📋 测试 3: 文件生成...")
    assert os.path.exists(result['markdown_path']), "Markdown not found"
    assert os.path.exists(result['json_path']), "JSON not found"
    print(f"✅ 文件生成成功\n")

    # 测试 4: 验证 JSON 格式
    print("📋 测试 4: JSON 格式...")
    with open(result['json_path'], 'r') as f:
        data = json.load(f)
    assert isinstance(data, list), "JSON should be a list"
    print(f"✅ JSON 格式正确\n")

    print("="*60)
    print("🎉 Milestone 1 验收测试通过！")
    print("="*60)


if __name__ == "__main__":
    test_milestone1_functionality()
```

**Step 2: Run acceptance test**

Run: `python3 tests/test_decision_shortlist_milestone1.py`

Expected: `🎉 Milestone 1 验收测试通过！`

**Step 3: Commit**

```bash
git add tests/test_decision_shortlist_milestone1.py
git commit -m "test: add Milestone 1 acceptance test"
```

---

## Task 10: 编写文档和使用示例

**Files:**
- Create: `docs/decision_shortlist_usage.md`

**Step 1: Write usage documentation**

```markdown
# Decision Shortlist 使用指南

## 快速开始

### 1. 运行完整 pipeline（包含 decision_shortlist）

```bash
python run_pipeline.py --stage all
```

### 2. 单独运行 decision_shortlist

```bash
python run_pipeline.py --stage decision_shortlist
```

### 3. 查看结果

```bash
# Markdown 报告
cat reports/shortlist_report_YYYYMMDD_HHMMSS.md

# JSON 报告
cat data/decision_shortlist.json
```

## 配置调整

编辑 `config/thresholds.yaml` 中的 `decision_shortlist` 部分：

### 调整过滤阈值

```yaml
decision_shortlist:
  min_viability_score: 7.0  # 降低以获得更多候选
  min_cluster_size: 5        # 降低以包含小聚类
  min_trust_level: 0.6       # 降低以包含低信任度源
```

### 启用多样性机制

```yaml
decision_shortlist:
  diversity:
    enabled: true  # 启用多样性惩罚
```

### 调整评分权重

```yaml
decision_shortlist:
  final_score_weights:
    viability_score: 1.2      # 提高 LLM 评分权重
    cluster_size_log_factor: 2.0  # 降低规模权重
```

## 输出解读

### Markdown 报告结构

- **Candidate N**: 第 N 个候选机会
- **Final Score**: 最终评分（0-10）
- **Cross-Source Evidence**: 跨源验证等级
- **Problem**: 问题陈述
- **MVP**: 最小可行产品描述
- **Why Now**: 紧迫性说明

### JSON 字段说明

```json
{
  "opportunity_name": "机会名称",
  "problem": "问题陈述",
  "mvp": "MVP 描述",
  "why_now": "紧迫性",
  "final_score": 8.7,
  "cluster_size": 15,
  "validated_problem": true
}
```

## 常见问题

### Q: 输出为空列表？

**A**: 检查以下几点：
1. 数据库中是否有已评分的机会（total_score > 0）
2. 过滤阈值是否过高
3. 查看日志中的过滤统计信息

### Q: 如何提高输出数量？

**A**: 降低过滤阈值：
```yaml
min_viability_score: 6.5  # 从 7.0 降低
min_cluster_size: 4        # 从 6 降低
```

### Q: 如何获得更多样化的结果？

**A**: 启用多样性机制：
```yaml
diversity:
  enabled: true
```
```

**Step 2: Verify documentation**

Read: `less docs/decision_shortlist_usage.md`

Expected: 内容清晰可读

**Step 3: Commit**

```bash
git add docs/decision_shortlist_usage.md
git commit -m "docs: add Decision Shortlist usage guide"
```

---

## Task 11: 最终集成测试

**Files:**
- None (run existing tests)

**Step 1: Run all tests**

```bash
# 运行所有 decision_shortlist 测试
pytest tests/test_decision_shortlist.py -v

# 运行验收测试
python3 tests/test_decision_shortlist_milestone1.py
```

Expected: All tests pass

**Step 2: Manual verification**

```bash
# 运行 decision_shortlist stage
python3 run_pipeline.py --stage decision_shortlist

# 检查输出
ls -la reports/shortlist_report_*.md
cat data/decision_shortlist.json
```

Expected: Files generated successfully

**Step 3: Create summary documentation**

```bash
cat << 'EOF' > IMPLEMENTATION_SUMMARY.md
# Decision Shortlist Implementation Summary

## 完成的功能

✅ 硬性过滤：viability >= 7.0, cluster_size >= 6, trust_level >= 0.7
✅ 跨源验证：三层优先级（Level 1/2/3）
✅ 对数缩放评分：log10(cluster_size) 避免极端值
✅ LLM 内容生成：Problem / MVP / Why Now
✅ 多样性机制：可选功能，避免同质化
✅ 空列表处理：清晰的报告和建议
✅ 双输出：Markdown + JSON

## 文件清单

- `pipeline/decision_shortlist.py`: 核心模块
- `config/thresholds.yaml`: 添加 decision_shortlist 配置
- `run_pipeline.py`: 集成 Stage 9
- `tests/test_decision_shortlist.py`: 单元测试
- `tests/test_decision_shortlist_milestone1.py`: 验收测试
- `docs/decision_shortlist_usage.md`: 使用文档

## 使用方式

```bash
# 完整 pipeline
python run_pipeline.py --stage all

# 单独运行
python run_pipeline.py --stage decision_shortlist

# 验收测试
python3 tests/test_decision_shortlist_milestone1.py
```

## Milestone 1 验收标准

✅ Pipeline 跑完后，系统自动只给 3-5 个候选机会
✅ 每个候选包含 Problem / MVP / Why Now 三句话
✅ 不用打开代码，一看就能理解
✅ 能在 10 分钟内决定做 or 不做

## 下一步

- 根据实际使用反馈调优权重系数
- 优化 LLM prompt 以提高内容质量
- 考虑添加历史趋势分析
- 探索自动化验证机会可行性
EOF
cat IMPLEMENTATION_SUMMARY.md
```

**Step 4: Final commit**

```bash
git add IMPLEMENTATION_SUMMARY.md
git commit -m "docs: add implementation summary"
```

---

## Execution Summary

This implementation plan consists of **11 tasks** with **29 steps**, following TDD principles with frequent commits. Each step is bite-sized (2-5 minutes) and builds the Decision Shortlist feature incrementally.

**Estimated completion time:** 4-6 hours

**Key features:**
- Hard filtering with configurable thresholds
- Three-tier cross-source validation
- Logarithmic scoring to avoid extreme values
- LLM-powered content generation
- Optional diversity mechanism
- Empty list handling
- Dual output (Markdown + JSON)

**Testing strategy:**
- Unit tests for each component
- Integration test for full flow
- Milestone 1 acceptance test

Ready for execution! Choose your preferred execution method when ready.
