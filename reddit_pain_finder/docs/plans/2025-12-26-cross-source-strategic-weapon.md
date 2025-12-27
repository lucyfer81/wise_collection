# Cross-Source Strategic Weapon Enhancement

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform cross-source alignment into a strategic priority engine that highlights independently validated pain points across Reddit and Hacker News with prominent visual indicators and easy query capabilities.

**Architecture:**
1. **Visual Indicators**: Add prominent badges in reports for cross-source validated opportunities
2. **Priority Sorting**: Automatically sort cross-source validated opportunities to the top
3. **Query Interface**: Add dedicated query methods and CLI tool to retrieve all cross-source validated pain points
4. **Scoring Boost**: Leverage existing boost_score mechanism with enhanced visibility

**Tech Stack:**
- Python 3.10+
- SQLite database (no schema changes required)
- Markdown/JSON report generation
- CLI argument parsing

---

## Current Implementation Analysis

### ✅ Already Working
- `aligned_problems` table stores cross-source aligned problems
- Three-tier validation logic (Level 1-3)
- `validated_problem = True` for Level 1 and Level 2
- `boost_score` implemented (2.0, 1.0, 0.5)
- Cross-source bonus applied in final scoring

### ❌ Needs Enhancement
1. **Report visibility**: Current indicator is just "✅ Yes/❌ No" - not prominent enough
2. **Missing badges**: No "Independent validation across Reddit + Hacker News" badge
3. **No query tool**: No easy way to list all cross-source validated pain points
4. **No sorting**: Cross-source validated opportunities not prioritized in reports

---

## Task 1: Enhanced Report Visual Indicators

**Files:**
- Modify: `pipeline/decision_shortlist.py:485-549`

**Step 1: Read current report generation logic**

Read the file to understand the current Markdown report generation.

**Step 2: Add helper method for badge generation**

Add this method to the `DecisionShortlistGenerator` class after line 484:

```python
def _get_cross_source_badge(self, cross_source: Dict) -> str:
    """生成跨源验证的徽章标识

    Args:
        cross_source: 跨源验证信息字典

    Returns:
        徽章字符串（Markdown格式）
    """
    if not cross_source.get('has_cross_source'):
        return ""

    validation_level = cross_source.get('validation_level', 0)

    if validation_level == 1:
        # Level 1: 最强信号 - 多平台独立验证
        return """
<div align="center">

### 🎯 INDEPENDENT VALIDATION ACROSS REDDIT + HACKER NEWS

**This pain point has been independently validated across multiple communities**

</div>
"""
    elif validation_level == 2:
        # Level 2: 中等信号 - 多 subreddit 验证
        return """
### ✓ Multi-Subreddit Validation
*Validated across 3+ subreddits with strong cluster size*
"""
    elif validation_level == 3:
        # Level 3: 弱信号
        return """
### ◐ Weak Cross-Source Signal
*Initial cross-community detection signal*
"""
    else:
        return ""
```

**Step 3: Modify report generation to include badges**

In the `_export_markdown_report` method, replace lines 515-528 with:

```python
            # 添加跨源验证徽章（在最前面，最醒目）
            badge = self._get_cross_source_badge(cross_source)
            if badge:
                report_lines.extend([
                    f"\n{badge}",
                    f"**Validation Level**: {cross_source.get('validation_level', 0)}  ",
                    f"**Boost Applied**: +{cross_source.get('boost_score', 0.0):.1f} to final score",
                    ""
                ])

            report_lines.extend([
                f"**Final Score**: {candidate['final_score']:.2f}/10.0  ",
                f"**Viability Score**: {candidate['viability_score']:.1f}  ",
                f"**Cluster Size**: {candidate['cluster_size']}  ",
                f"**Trust Level**: {candidate['trust_level']:.2f}  ",
                f"**Validated Problem**: {'✅ Yes' if cross_source.get('validated_problem') else '❌ No'}"
            ])
```

**Step 4: Test the enhanced report generation**

Run: `python -m pytest tests/test_decision_shortlist.py -v -k report`

Expected: PASS with new badge formatting in Markdown output

**Step 5: Commit**

```bash
git add pipeline/decision_shortlist.py
git commit -m "feat: add prominent badges for cross-source validation in reports"
```

---

## Task 2: Prioritize Cross-Source Validated Opportunities

**Files:**
- Modify: `pipeline/decision_shortlist.py:372-459`

**Step 1: Read current sorting logic**

Review the `generate_shortlist` method to understand how candidates are currently sorted.

**Step 2: Add sorting key function**

Add this method to the `DecisionShortlistGenerator` class after line 371:

```python
def _sort_priority_key(self, candidate: Dict) -> tuple:
    """生成排序键，确保跨源验证的机会排在前面

    排序优先级：
    1. 跨源验证等级（Level 1 > Level 2 > Level 3 > No validation）
    2. 最终评分（降序）
    3. 聚类规模（降序）

    Args:
        candidate: 候选机会字典

    Returns:
        排序键元组
    """
    cross_source = candidate.get('cross_source_validation', {})
    validation_level = cross_source.get('validation_level', 0)

    # 验证等级越高越优先（用负数实现降序）
    # Level 1-3 优先于无验证（0）
    priority_score = -validation_level

    # 最终评分降序
    final_score = -candidate.get('final_score', 0)

    # 聚类规模降序
    cluster_size = -candidate.get('cluster_size', 0)

    return (priority_score, final_score, cluster_size)
```

**Step 3: Apply sorting in generate_shortlist**

In the `generate_shortlist` method, find the sorting logic (around line 430-435) and replace with:

```python
        # 按照优先级排序：跨源验证 > 最终评分 > 聚类规模
        filtered_candidates.sort(key=self._sort_priority_key)
```

**Step 4: Test the sorting logic**

Run: `python -m pytest tests/test_decision_shortlist.py -v -k sort`

Expected: PASS with cross-source validated candidates appearing first

**Step 5: Commit**

```bash
git add pipeline/decision_shortlist.py
git commit -m "feat: prioritize cross-source validated opportunities in shortlist"
```

---

## Task 3: Add Database Query Method for Cross-Source Opportunities

**Files:**
- Modify: `utils/db.py` (after line 1310)

**Step 1: Add new query method**

Add this method to the `DatabaseManager` class:

```python
    def get_cross_source_validated_opportunities(
        self,
        min_validation_level: int = 1,
        include_validated_only: bool = True
    ) -> List[Dict[str, Any]]:
        """查询所有跨源验证的机会

        Args:
            min_validation_level: 最低验证等级（1-3），默认为 1
            include_validated_only: 是否仅包含 validated_problem=True 的，默认为 True

        Returns:
            跨源验证的机会列表
        """
        try:
            with self.get_connection("opportunities") as conn:
                query = """
                    SELECT
                        o.opportunity_name,
                        o.final_score,
                        o.viability_score,
                        o.cluster_size,
                        o.trust_level,
                        o.target_users,
                        o.missing_capability,
                        o.why_existing_fail,
                        o.cluster_name,
                        c.source_type,
                        c.alignment_status,
                        c.aligned_problem_id
                    FROM opportunities o
                    LEFT JOIN clusters c ON o.cluster_name = c.cluster_name
                    WHERE 1=1
                """

                params = []

                # 添加跨源验证过滤
                if include_validated_only:
                    # Level 1: source_type='aligned' 或有 aligned_problem_id
                    # Level 2: cluster_size >= 10 AND 跨 >= 3 subreddits
                    # Level 3: cluster_size >= 8 AND 跨 >= 2 subreddits

                    # 这里我们简化处理：查询所有可能跨源验证的聚类
                    # 然后在 Python 中进行详细过滤
                    pass

                query += " ORDER BY o.final_score DESC"

                cursor = conn.execute(query, params)
                results = [dict(row) for row in cursor.fetchall()]

                # 在 Python 中进行跨源验证过滤
                filtered_results = []
                for result in results:
                    validation_info = self._check_cross_source_validation_sync(
                        result['cluster_name'],
                        result.get('source_type'),
                        result.get('aligned_problem_id'),
                        result['cluster_size']
                    )

                    validation_level = validation_info.get('validation_level', 0)

                    # 过滤条件
                    if validation_level >= min_validation_level:
                        if include_validated_only:
                            if validation_info.get('validated_problem'):
                                result['cross_source_validation'] = validation_info
                                filtered_results.append(result)
                        else:
                            result['cross_source_validation'] = validation_info
                            filtered_results.append(result)

                return filtered_results

        except Exception as e:
            logger.error(f"Failed to get cross-source validated opportunities: {e}")
            return []

    def _check_cross_source_validation_sync(
        self,
        cluster_name: str,
        source_type: Optional[str],
        aligned_problem_id: Optional[str],
        cluster_size: int
    ) -> Dict[str, Any]:
        """同步版本的跨源验证检查（用于数据库查询）

        Args:
            cluster_name: 聚类名称
            source_type: 来源类型
            aligned_problem_id: 对齐问题ID
            cluster_size: 聚类规模

        Returns:
            验证信息字典
        """
        # Level 1: 检查 aligned source_type 或 aligned_problem_id
        if source_type == 'aligned' or aligned_problem_id:
            return {
                "has_cross_source": True,
                "validation_level": 1,
                "boost_score": 2.0,
                "validated_problem": True,
                "evidence": "Independent validation across Reddit + Hacker News"
            }

        # Level 2 & 3: 需要 subreddit 计数（从 pain_events 中查询）
        try:
            with self.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT DISTINCT subreddit
                    FROM pain_events
                    WHERE cluster_name = ?
                """, (cluster_name,))

                subreddits = set(row[0] for row in cursor.fetchall())
                subreddit_count = len(subreddits)

                # Level 2
                if cluster_size >= 10 and subreddit_count >= 3:
                    return {
                        "has_cross_source": True,
                        "validation_level": 2,
                        "boost_score": 1.0,
                        "validated_problem": True,
                        "evidence": f"Validated across {subreddit_count}+ subreddits"
                    }

                # Level 3
                if cluster_size >= 8 and subreddit_count >= 2:
                    return {
                        "has_cross_source": True,
                        "validation_level": 3,
                        "boost_score": 0.5,
                        "validated_problem": False,
                        "evidence": f"Detected across {subreddit_count}+ subreddits"
                    }

        except Exception as e:
            logger.warning(f"Failed to check cross-source validation for {cluster_name}: {e}")

        # 无跨源验证
        return {
            "has_cross_source": False,
            "validation_level": 0,
            "boost_score": 0.0,
            "validated_problem": False,
            "evidence": "No cross-source validation"
        }
```

**Step 2: Test the new query method**

Run: `python -c "from utils.db import DatabaseManager; db = DatabaseManager(); results = db.get_cross_source_validated_opportunities(); print(f'Found {len(results)} cross-source validated opportunities')"`

Expected: Print count of cross-source validated opportunities (may be 0 if no data)

**Step 3: Commit**

```bash
git add utils/db.py
git commit -m "feat: add query method for cross-source validated opportunities"
```

---

## Task 4: Create CLI Tool to Display Cross-Source Pain Points

**Files:**
- Create: `scripts/show_cross_source_pain_points.py`

**Step 1: Write the CLI tool**

```python
#!/usr/bin/env python3
"""
Cross-Source Pain Points Viewer

显示所有跨源验证的痛点，回答："现阶段世界上'被不同社群独立提及'的痛点有哪些？"
"""

import argparse
import json
from typing import List, Dict
from utils.db import DatabaseManager
from utils.logger import logger


def format_opportunity(opportunity: Dict, detailed: bool = False) -> str:
    """格式化单个机会显示

    Args:
        opportunity: 机会数据
        detailed: 是否显示详细信息

    Returns:
        格式化的字符串
    """
    cross_source = opportunity.get('cross_source_validation', {})
    validation_level = cross_source.get('validation_level', 0)

    # 验证等级徽章
    level_badges = {
        1: "🎯 LEVEL 1 - Multi-Platform Validation",
        2: "✓ LEVEL 2 - Multi-Subreddit Validation",
        3: "◐ LEVEL 3 - Weak Cross-Source Signal"
    }

    badge = level_badges.get(validation_level, "")

    lines = [
        f"\n{'='*80}",
        f"📌 {opportunity['opportunity_name']}",
        f"{'='*80}",
        f"\n{badge}" if badge else "",
        f"\n📊 Scores:",
        f"  • Final Score: {opportunity['final_score']:.2f}/10.0",
        f"  • Viability Score: {opportunity['viability_score']:.1f}/10.0",
        f"  • Cluster Size: {opportunity['cluster_size']}",
        f"  • Trust Level: {opportunity['trust_level']:.2f}",
        f"\n✅ Validation: {cross_source.get('evidence', 'N/A')}",
        f"   Boost Applied: +{cross_source.get('boost_score', 0.0):.1f}",
        f"   Validated Problem: {'Yes' if cross_source.get('validated_problem') else 'No'}",
    ]

    if detailed:
        lines.extend([
            f"\n🎯 Target Users:",
            f"  {opportunity.get('target_users', 'N/A')}",
            f"\n❌ Missing Capability:",
            f"  {opportunity.get('missing_capability', 'N/A')}",
            f"\n💡 Why Existing Solutions Fail:",
            f"  {opportunity.get('why_existing_fail', 'N/A')}",
            f"\n📋 Cluster Info:",
            f"  • Cluster Name: {opportunity.get('cluster_name', 'N/A')}",
            f"  • Source Type: {opportunity.get('source_type', 'N/A')}",
            f"  • Alignment Status: {opportunity.get('alignment_status', 'N/A')}",
        ])

    return '\n'.join(lines)


def print_summary(opportunities: List[Dict]):
    """打印统计摘要

    Args:
        opportunities: 机会列表
    """
    total = len(opportunities)

    if total == 0:
        print("\n⚠️  No cross-source validated pain points found.")
        return

    # 按等级统计
    level_counts = {1: 0, 2: 0, 3: 0}
    validated_count = 0

    for opp in opportunities:
        cs = opp.get('cross_source_validation', {})
        level = cs.get('validation_level', 0)
        if level in level_counts:
            level_counts[level] += 1
        if cs.get('validated_problem'):
            validated_count += 1

    print("\n" + "="*80)
    print("📊 CROSS-SOURCE VALIDATED PAIN POINTS SUMMARY")
    print("="*80)
    print(f"\nTotal Opportunities: {total}")
    print(f"\n  🎯 Level 1 (Multi-Platform): {level_counts[1]}")
    print(f"  ✓ Level 2 (Multi-Subreddit): {level_counts[2]}")
    print(f"  ◐ Level 3 (Weak Signal): {level_counts[3]}")
    print(f"\n  ✅ Validated Problems: {validated_count}")
    print(f"  ❌ Not Validated: {total - validated_count}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Display cross-source validated pain points",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 显示所有跨源验证的痛点（摘要）
  python scripts/show_cross_source_pain_points.py

  # 显示详细信息
  python scripts/show_cross_source_pain_points.py --detailed

  # 仅显示 Level 1 的多平台验证
  python scripts/show_cross_source_pain_points.py --min-level 1

  # 仅显示 validated_problem=True 的
  python scripts/show_cross_source_pain_points.py --validated-only

  # 导出到 JSON
  python scripts/show_cross_source_pain_points.py --export cross_source.json
        """
    )

    parser.add_argument(
        '--min-level',
        type=int,
        choices=[1, 2, 3],
        default=1,
        help='Minimum validation level (default: 1)'
    )

    parser.add_argument(
        '--validated-only',
        action='store_true',
        help='Show only validated_problem=True opportunities'
    )

    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed information for each opportunity'
    )

    parser.add_argument(
        '--export',
        type=str,
        metavar='FILE',
        help='Export results to JSON file'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of results (default: show all)'
    )

    args = parser.parse_args()

    # 查询数据库
    logger.info("Querying cross-source validated pain points...")
    db = DatabaseManager()

    opportunities = db.get_cross_source_validated_opportunities(
        min_validation_level=args.min_level,
        include_validated_only=args.validated_only
    )

    # 应用限制
    if args.limit:
        opportunities = opportunities[:args.limit]

    # 打印摘要
    print_summary(opportunities)

    # 导出到 JSON
    if args.export:
        export_data = {
            'generated_at': datetime.now().isoformat(),
            'filter': {
                'min_validation_level': args.min_level,
                'validated_only': args.validated_only
            },
            'total_count': len(opportunities),
            'opportunities': opportunities
        }

        with open(args.export, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ Exported to {args.export}")

    # 打印每个机会
    for opp in opportunities:
        print(format_opportunity(opp, detailed=args.detailed))

    print(f"\n{'='*80}\n")
    logger.info(f"✅ Displayed {len(opportunities)} cross-source validated pain points")


if __name__ == '__main__':
    from datetime import datetime
    main()
```

**Step 2: Make the script executable**

Run: `chmod +x scripts/show_cross_source_pain_points.py`

**Step 3: Test the CLI tool**

Run: `python scripts/show_cross_source_pain_points.py --help`

Expected: Display help message with all options

**Step 4: Test with actual data**

Run: `python scripts/show_cross_source_pain_points.py`

Expected: Display all cross-source validated pain points (or message if none found)

**Step 5: Commit**

```bash
git add scripts/show_cross_source_pain_points.py
git commit -m "feat: add CLI tool to display cross-source validated pain points"
```

---

## Task 5: Update JSON Report Format

**Files:**
- Modify: `pipeline/decision_shortlist.py:551-596`

**Step 1: Add cross-source validation summary to JSON report**

Modify the `_export_json_report` method to include enhanced cross-source information. Replace lines 576-589 with:

```python
        for candidate in shortlist:
            cross_source = candidate.get('cross_source_validation', {})

            export_candidate = {
                'opportunity_name': candidate.get('opportunity_name'),
                'final_score': candidate.get('final_score'),
                'viability_score': candidate.get('viability_score'),
                'cluster_size': candidate.get('cluster_size'),
                'trust_level': candidate.get('trust_level'),
                'target_users': candidate.get('target_users'),
                'missing_capability': candidate.get('missing_capability'),
                'why_existing_fail': candidate.get('why_existing_fail'),
                'readable_content': candidate.get('readable_content', {}),
                'cross_source_validation': {
                    'has_cross_source': cross_source.get('has_cross_source', False),
                    'validation_level': cross_source.get('validation_level', 0),
                    'validated_problem': cross_source.get('validated_problem', False),
                    'boost_score': cross_source.get('boost_score', 0.0),
                    'evidence': cross_source.get('evidence', ''),
                    'badge_text': self._get_cross_source_badge_text(cross_source)
                }
            }
            export_data['candidates'].append(export_candidate)
```

**Step 2: Add helper method for badge text**

Add this method to the class:

```python
def _get_cross_source_badge_text(self, cross_source: Dict) -> str:
    """获取跨源验证徽章的纯文本版本

    Args:
        cross_source: 跨源验证信息字典

    Returns:
        徽章文本
    """
    if not cross_source.get('has_cross_source'):
        return ""

    validation_level = cross_source.get('validation_level', 0)

    badge_texts = {
        1: "🎯 INDEPENDENT VALIDATION ACROSS REDDIT + HACKER NEWS",
        2: "✓ Multi-Subreddit Validation",
        3: "◐ Weak Cross-Source Signal"
    }

    return badge_texts.get(validation_level, "")
```

**Step 3: Test JSON report generation**

Run: `python -m pytest tests/test_decision_shortlist.py::test_json_report -v`

Expected: PASS with enhanced cross-source information in JSON output

**Step 4: Commit**

```bash
git add pipeline/decision_shortlist.py
git commit -m "feat: enhance JSON report with cross-source validation details"
```

---

## Task 6: Add Documentation

**Files:**
- Create: `docs/cross_source_validation_guide.md`

**Step 1: Write comprehensive documentation**

```markdown
# Cross-Source Validation Guide

## Overview

Cross-source validation is a strategic engine that identifies pain points independently validated across multiple communities (Reddit, Hacker News, etc.). This system transforms social listening into a prioritized opportunity radar.

## What is Cross-Source Validation?

A pain point is "cross-source validated" when the **same underlying problem** is discussed across different communities, despite differences in:
- Language and terminology
- Community maturity
- Technical depth
- Cultural context

### Why This Matters

When developers on Reddit and entrepreneurs on Hacker News **independently** complain about the same problem, that's a **strong market signal**.

It means:
- ✅ The problem is **real and persistent**
- ✅ It affects **multiple user segments**
- ✅ It's **not platform-specific noise**
- ✅ There's **unmet demand** across different contexts

## Validation Levels

### Level 1: Multi-Platform Validation (🎯 Strongest)

**Condition**: Pain point appears across **different platforms** (Reddit + Hacker News)

**Indicators**:
- `source_type = 'aligned'` in clusters table
- OR exists in `aligned_problems` table with `alignment_score >= 0.7`

**Boost**: +2.0 to final score
**Validated Problem**: Yes

**Example**:
> Reddit: "I hate managing environment variables across different projects"
> HackerNews: "Configuration management is a nightmare in microservices"

→ Both are complaining about **configuration management**, just using different words.

---

### Level 2: Multi-Subreddit Validation (✓ Medium)

**Condition**:
- `cluster_size >= 10`
- Appears across **3+ different subreddits**

**Boost**: +1.0 to final score
**Validated Problem**: Yes

**Example**:
Same problem discussed in:
- r/programming
- r/devops
- r/webdev

---

### Level 3: Weak Cross-Source Signal (◐ Weak)

**Condition**:
- `cluster_size >= 8`
- Appears across **2+ different subreddits**

**Boost**: +0.5 to final score
**Validated Problem**: No (needs more validation)

---

## How to Use

### 1. View All Cross-Source Validated Pain Points

```bash
# Show all cross-source validated pain points
python scripts/show_cross_source_pain_points.py

# Show only Level 1 (strongest signals)
python scripts/show_cross_source_pain_points.py --min-level 1

# Show detailed information
python scripts/show_cross_source_pain_points.py --detailed

# Export to JSON
python scripts/show_cross_source_pain_points.py --export cross_source.json
```

### 2. In Decision Shortlist Reports

Decision shortlist reports automatically:
- ✅ Prioritize cross-source validated opportunities at the top
- ✅ Display prominent badges (🎯 / ✓ / ◐)
- ✅ Show validation level and boost applied
- ✅ Include "Independent validation across Reddit + Hacker News" for Level 1

### 3. Query Programmatically

```python
from utils.db import DatabaseManager

db = DatabaseManager()

# Get all cross-source validated opportunities
opportunities = db.get_cross_source_validated_opportunities()

# Get only Level 1 (strongest)
opportunities = db.get_cross_source_validated_opportunities(
    min_validation_level=1
)

# Get only validated_problem=True
opportunities = db.get_cross_source_validated_opportunities(
    include_validated_only=True
)
```

## FAQ

### Q: How is cross-source alignment detected?

**A**: We use LLM-based semantic analysis:
1. Extract cluster summaries from each source (Reddit, HN Ask, HN Show)
2. Ask LLM: "Are these describing the same underlying problem?"
3. LLM provides alignment score (0.0-1.0) and explanation
4. Threshold: `alignment_score >= 0.7`

### Q: Why doesn't Level 3 count as "validated_problem"?

**A**: Level 3 is a **weak signal** - it indicates potential cross-source validation, but needs more evidence. Only Level 1 and Level 2 are strong enough to be "validated problems".

### Q: Can I adjust the boost scores?

**A**: Yes! Edit `config/thresholds.yaml`:

```yaml
decision_shortlist:
  final_score_weights:
    cross_source_bonus: 5.0  # Adjust base bonus
```

The actual boost is: `cross_source_bonus * boost_score * 0.1`
- Level 1: 5.0 * 2.0 * 0.1 = 1.0
- Level 2: 5.0 * 1.0 * 0.1 = 0.5
- Level 3: 5.0 * 0.5 * 0.1 = 0.25

### Q: What's the difference between `aligned_problems` and `clusters`?

**A**:
- `clusters`: Raw groupings from a single source (Reddit, HN Ask, HN Show)
- `aligned_problems**: Unified problems after LLM detects cross-source alignment

Each `aligned_problem` links to 2+ original `clusters` via `cluster_ids` field.

---

## Technical Implementation

### Database Schema

#### `aligned_problems` table

```sql
CREATE TABLE aligned_problems (
    id TEXT PRIMARY KEY,              -- aligned_AP_XX_timestamp
    aligned_problem_id TEXT UNIQUE,   -- AP_XX
    sources TEXT,                     -- JSON: ["reddit", "hackernews"]
    core_problem TEXT,                -- Unified problem description
    why_they_look_different TEXT,     -- LLM explanation
    evidence TEXT,                    -- JSON: Evidence from each source
    cluster_ids TEXT,                 -- JSON: Original cluster IDs
    alignment_score REAL DEFAULT 0.0, -- 0.0-1.0, threshold: 0.7
    created_at TIMESTAMP
);
```

#### `clusters` table (alignment columns)

```sql
ALTER TABLE clusters ADD COLUMN:
    alignment_status TEXT,           -- 'unprocessed' | 'aligned' | 'processed'
    aligned_problem_id TEXT          -- Foreign key to aligned_problems
);
```

### Key Code Files

- **Alignment Logic**: `pipeline/align_cross_sources.py`
- **Scoring**: `pipeline/decision_shortlist.py` (lines 126-198, 231-263)
- **Database Queries**: `utils/db.py` (lines 1270-1310)
- **CLI Tool**: `scripts/show_cross_source_pain_points.py`

---

## The Strategic Question

**"现阶段世界上'被不同社群独立提及'的痛点有哪些？"**

Now you can answer this in seconds:

```bash
python scripts/show_cross_source_pain_points.py --min-level 1
```

This gives you a prioritized list of pain points validated across Reddit and Hacker News - your **opportunity radar** for product discovery.
```

**Step 2: Commit documentation**

```bash
git add docs/cross_source_validation_guide.md
git commit -m "docs: add comprehensive cross-source validation guide"
```

---

## Task 7: Integration Testing

**Files:**
- Create: `tests/test_cross_source_validation.py`

**Step 1: Write integration tests**

```python
import pytest
from utils.db import DatabaseManager
from pipeline.decision_shortlist import DecisionShortlistGenerator


class TestCrossSourceValidation:
    """跨源验证功能集成测试"""

    @pytest.fixture
    def db(self):
        """数据库实例"""
        return DatabaseManager()

    @pytest.fixture
    def shortlist_generator(self):
        """决策清单生成器"""
        return DecisionShortlistGenerator()

    def test_query_cross_source_validated_opportunities(self, db):
        """测试查询跨源验证机会"""
        # 测试查询所有
        opportunities = db.get_cross_source_validated_opportunities()
        assert isinstance(opportunities, list)

        # 如果有数据，验证字段
        if opportunities:
            opp = opportunities[0]
            assert 'cross_source_validation' in opp
            assert 'opportunity_name' in opp
            assert 'final_score' in opp

    def test_query_min_validation_level(self, db):
        """测试最低验证等级过滤"""
        # Level 1
        level1 = db.get_cross_source_validated_opportunities(
            min_validation_level=1
        )

        # Level 2
        level2 = db.get_cross_source_validated_opportunities(
            min_validation_level=2
        )

        # Level 1 应该包含 Level 2（或者更多）
        assert len(level1) >= len(level2)

    def test_sorting_priority(self, shortlist_generator):
        """测试排序优先级"""
        # 创建模拟数据
        mock_candidates = [
            {
                'opportunity_name': 'No Validation',
                'final_score': 9.0,
                'cluster_size': 100,
                'cross_source_validation': {
                    'has_cross_source': False,
                    'validation_level': 0
                }
            },
            {
                'opportunity_name': 'Level 2 Validation',
                'final_score': 7.0,
                'cluster_size': 50,
                'cross_source_validation': {
                    'has_cross_source': True,
                    'validation_level': 2
                }
            },
            {
                'opportunity_name': 'Level 1 Validation',
                'final_score': 8.0,
                'cluster_size': 30,
                'cross_source_validation': {
                    'has_cross_source': True,
                    'validation_level': 1
                }
            }
        ]

        # 应用排序
        sorted_candidates = sorted(
            mock_candidates,
            key=shortlist_generator._sort_priority_key
        )

        # 验证顺序：Level 1 > Level 2 > No Validation
        assert sorted_candidates[0]['opportunity_name'] == 'Level 1 Validation'
        assert sorted_candidates[1]['opportunity_name'] == 'Level 2 Validation'
        assert sorted_candidates[2]['opportunity_name'] == 'No Validation'

    def test_badge_generation(self, shortlist_generator):
        """测试徽章生成"""
        # Level 1
        badge1 = shortlist_generator._get_cross_source_badge({
            'has_cross_source': True,
            'validation_level': 1
        })
        assert 'INDEPENDENT VALIDATION ACROSS REDDIT + HACKER NEWS' in badge1

        # Level 2
        badge2 = shortlist_generator._get_cross_source_badge({
            'has_cross_source': True,
            'validation_level': 2
        })
        assert 'Multi-Subreddit Validation' in badge2

        # No validation
        badge0 = shortlist_generator._get_cross_source_badge({
            'has_cross_source': False
        })
        assert badge0 == ""

    def test_cross_source_boost_in_scoring(self, shortlist_generator):
        """测试跨源验证在评分中的加成"""
        # 模拟数据
        cluster = {
            'cluster_size': 20,
            'cluster_name': 'test_cluster',
            'source_type': 'reddit',
            'trust_level': 0.8,
            'alignment_status': 'unprocessed'
        }

        # 无跨源验证
        score1 = shortlist_generator._calculate_final_score(
            viability_score=7.0,
            cluster=cluster,
            cross_source_info={
                'has_cross_source': False,
                'boost_score': 0.0
            }
        )

        # 有跨源验证 (Level 1, boost=2.0)
        score2 = shortlist_generator._calculate_final_score(
            viability_score=7.0,
            cluster=cluster,
            cross_source_info={
                'has_cross_source': True,
                'boost_score': 2.0
            }
        )

        # 有跨源验证的评分应该更高
        assert score2 > score1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

**Step 2: Run tests**

Run: `python -m pytest tests/test_cross_source_validation.py -v`

Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/test_cross_source_validation.py
git commit -m "test: add cross-source validation integration tests"
```

---

## Verification Checklist

After implementation, verify:

- [ ] Reports show prominent badges for cross-source validation
- [ ] Level 1 displays "🎯 INDEPENDENT VALIDATION ACROSS REDDIT + HACKER NEWS"
- [ ] Cross-source validated opportunities appear at the top of shortlists
- [ ] CLI tool works: `python scripts/show_cross_source_pain_points.py`
- [ ] Can query cross-source opportunities programmatically
- [ ] JSON reports include enhanced cross-source information
- [ ] All tests pass
- [ ] Documentation is complete and clear

---

## Success Criteria

✅ **Can easily answer**: "What pain points are independently validated across different communities?"

Run this command:
```bash
python scripts/show_cross_source_pain_points.py --min-level 1
```

Expected output:
- List of all Level 1 cross-source validated pain points
- With prominent badges and evidence
- Prioritized by final score

This is your **strategic opportunity radar**.
