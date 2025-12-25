# Phase 2: Comment-Aware Pain Extraction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate comment data into pain extraction to improve quality, specificity, and evidence support for extracted pain events.

**Architecture:**
1. Add `get_top_comments_for_post()` method to `utils/db.py`
2. Modify `_extract_from_single_post()` in `pipeline/extract_pain.py` to load comments
3. Update `extract_pain_points()` in `utils/llm_client.py` with new context-aware prompt
4. Create A/B testing script to compare old vs new extraction quality
5. Generate qualitative comparison report

**Tech Stack:** Python 3.x, SQLite, OpenAI-compatible LLM API

---

## Task 1: Add get_top_comments_for_post() method to utils/db.py

**Files:**
- Modify: `utils/db.py` (add new method after line 743)

**Step 1: Add the new method to WiseCollectionDB class**

```python
    def get_top_comments_for_post(self, post_id: str, top_n: int = 10) -> List[Dict[str, Any]]:
        """获取指定帖子的Top N高赞评论

        Args:
            post_id: 帖子ID
            top_n: 返回评论数量，默认10条

        Returns:
            评论列表，按score降序排列
        """
        try:
            with self.get_connection("raw") as conn:
                cursor = conn.execute("""
                    SELECT source_comment_id, author, body, score
                    FROM comments
                    WHERE post_id = ?
                    ORDER BY score DESC
                    LIMIT ?
                """, (post_id, top_n))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get comments for post {post_id}: {e}")
            return []
```

**Step 2: Verify syntax**

Run: `python -m py_compile utils/db.py`
Expected: No syntax errors

**Step 3: Test the new method**

Run: `python3 -c "
from utils.db import db
comments = db.get_top_comments_for_post('reddit_1psbpp0', top_n=5)
print(f'Found {len(comments)} comments')
for c in comments[:2]:
    print(f'  Score: {c[\"score\"]}, Author: {c[\"author\"]}, Body: {c[\"body\"][:50]}...')
"`
Expected: Returns 5 comments sorted by score

**Step 4: Commit**

```bash
git add utils/db.py
git commit -m "feat: add get_top_comments_for_post() method for comment retrieval"
```

---

## Task 2: Update LLM client extract_pain_points() signature

**Files:**
- Modify: `utils/llm_client.py:195-222`

**Step 1: Modify extract_pain_points() method signature**

Change from:
```python
    def extract_pain_points(
        self,
        title: str,
        body: str,
        subreddit: str,
        upvotes: int,
        comments_count: int
    ) -> Dict[str, Any]:
```

To:
```python
    def extract_pain_points(
        self,
        title: str,
        body: str,
        subreddit: str,
        upvotes: int,
        comments_count: int,
        top_comments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
```

**Step 2: Update the user message construction**

Replace the user message construction (lines 208-214) with:

```python
        # Build user message with comment context
        user_message = f"""Title: {title}
Body: {body}
Subreddit: {subreddit}
Upvotes: {upvotes}
Comments: {comments_count}
"""

        # Add top comments if available
        if top_comments and len(top_comments) > 0:
            user_message += f"\nTop {len(top_comments)} Comments:\n"
            for i, comment in enumerate(top_comments, 1):
                comment_body = comment.get('body', '')
                comment_score = comment.get('score', 0)
                comment_author = comment.get('author', 'unknown')
                # Truncate very long comments to save tokens
                if len(comment_body) > 500:
                    comment_body = comment_body[:500] + "... [truncated]"
                user_message += f"\n{i}. [{comment_score} upvotes] {comment_author}: {comment_body}\n"

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message}
        ]
```

**Step 3: Verify syntax**

Run: `python -m py_compile utils/llm_client.py`
Expected: No syntax errors

**Step 4: Commit**

```bash
git add utils/llm_client.py
git commit -m "feat: update extract_pain_points to accept top_comments parameter"
```

---

## Task 3: Update pain extraction prompt to leverage comment context

**Files:**
- Modify: `utils/llm_client.py:326-368`

**Step 1: Modify _get_pain_extraction_prompt() method**

Replace the entire prompt (lines 326-367) with:

```python
    def _get_pain_extraction_prompt(self) -> str:
        """获取痛点抽取提示 - 支持评论上下文"""
        return """You are an information extraction engine specializing in user pain point analysis.

Your task:
From the provided Reddit post and its top comments, extract concrete PAIN EVENTS.

A pain event is a specific recurring problem experienced by users, supported by evidence from discussions.

Rules:
- Do NOT summarize the post
- Do NOT give advice
- If no concrete pain exists, return an empty list
- Be literal and conservative
- Focus on actionable problems people face repeatedly

**Using Comment Context:**
Top comments often reveal:
- Additional specific pain instances mentioned by others
- Confirmation/refinement of the main pain point
- Alternative perspectives on the same problem
- Workarounds people are actually using
- Frequency indicators (how often this occurs)

When extracting pain events:
1. Look for pains mentioned in BOTH the post AND comments
2. Use comments to add specificity to vague problems in the post
3. Include alternative formulations of the same pain
4. Note if multiple commenters confirm the same issue

Output JSON only with this format:
{
  "pain_events": [
    {
      "actor": "who experiences the problem",
      "context": "what they are trying to do",
      "problem": "the concrete difficulty",
      "current_workaround": "how they currently cope (if any)",
      "frequency": "how often it happens (explicit or inferred)",
      "emotional_signal": "frustration, anxiety, exhaustion, etc.",
      "mentioned_tools": ["tool1", "tool2"],
      "confidence": 0.8,
      "evidence_sources": ["post", "comments"]  # where this pain was mentioned
    }
  ],
  "extraction_summary": "brief summary of findings"
}

Fields explanation:
- actor: who has this problem (developer, manager, user, etc.)
- context: the situation or workflow where the problem occurs
- problem: specific, concrete issue (e.g., "compilation takes 30 minutes" not "things are slow")
- current_workaround: current solutions people use (if mentioned)
- frequency: how often this happens (daily, weekly, occasionally, etc.)
- emotional_signal: the emotion expressed (frustration, anger, disappointment, etc.)
- mentioned_tools: tools, software, or methods explicitly mentioned
- confidence: how confident you are this is a real pain point (0-1)
- evidence_sources: list of where pain was found ("post", "comments", or both)

Be more confident when the same pain appears in both post and comments."""
```

**Step 2: Verify syntax**

Run: `python -m py_compile utils/llm_client.py`
Expected: No syntax errors

**Step 3: Commit**

```bash
git add utils/llm_client.py
git commit -m "feat: enhance pain extraction prompt to leverage comment context"
```

---

## Task 4: Modify extract_pain.py to load comments for each post

**Files:**
- Modify: `pipeline/extract_pain.py:29-78`

**Step 1: Update _extract_from_single_post() to load comments**

Add comment loading after line 37:

```python
            # Load top comments for context
            top_n_comments = 10
            comments = db.get_top_comments_for_post(post_data["id"], top_n=top_n_comments)
            logger.debug(f"Loaded {len(comments)} comments for post {post_data['id']}")
```

**Step 2: Update LLM call to include comments**

Replace the `llm_client.extract_pain_points()` call (lines 40-46) with:

```python
            # 调用LLM进行抽取（包含评论上下文）
            response = llm_client.extract_pain_points(
                title=title,
                body=body,
                subreddit=subreddit,
                upvotes=upvotes,
                comments_count=comments_count,
                top_comments=comments
            )
```

**Step 3: Add comment metadata to pain events**

Update the event enrichment section (lines 52-60) to include comment metadata:

```python
            # 为每个痛点事件添加元数据
            for event in pain_events:
                event.update({
                    "post_id": post_data["id"],
                    "subreddit": subreddit,
                    "original_score": upvotes,
                    "extraction_model": response["model"],
                    "extraction_timestamp": datetime.now().isoformat(),
                    "confidence": event.get("confidence", 0.0),
                    "comments_used": len(comments),  # 新增：使用的评论数量
                    "evidence_sources": event.get("evidence_sources", ["post"])  # 新增：证据来源
                })
```

**Step 4: Verify syntax**

Run: `python -m py_compile pipeline/extract_pain.py`
Expected: No syntax errors

**Step 5: Commit**

```bash
git add pipeline/extract_pain.py
git commit -m "feat: load and use comments in pain extraction"
```

---

## Task 5: Create A/B testing script for quality comparison

**Files:**
- Create: `scripts/test_comment_aware_extraction.py`

**Step 1: Create the A/B test script**

```python
#!/usr/bin/env python3
"""
A/B Testing Script for Comment-Aware Pain Extraction
对比测试脚本 - 验证评论数据是否提升痛点抽取质量
"""
import json
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from utils.llm_client import llm_client
from utils.db import db

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def load_old_prompt():
    """加载旧的prompt（不含评论）"""
    return """You are an information extraction engine.

Your task:
From the following Reddit post, extract concrete PAIN EVENTS.
A pain event is a specific recurring problem experienced by the author,
not opinions, not general complaints.

Rules:
- Do NOT summarize the post
- Do NOT give advice
- If no concrete pain exists, return an empty list
- Be literal and conservative
- Focus on actionable problems people face repeatedly

Output JSON only with this format:
{
  "pain_events": [
    {
      "actor": "who experiences the problem",
      "context": "what they are trying to do",
      "problem": "the concrete difficulty",
      "current_workaround": "how they currently cope (if any)",
      "frequency": "how often it happens (explicit or inferred)",
      "emotional_signal": "frustration, anxiety, exhaustion, etc.",
      "mentioned_tools": ["tool1", "tool2"],
      "confidence": 0.8
    }
  ],
  "extraction_summary": "brief summary of findings"
}"""

def extract_with_old_method(post_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """使用旧方法提取痛点（不含评论）"""
    prompt = load_old_prompt()

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"""
Title: {post_data.get('title', '')}
Body: {post_data.get('body', '')}
Subreddit: {post_data.get('subreddit', '')}
Upvotes: {post_data.get('score', 0)}
Comments: {post_data.get('num_comments', 0)}
"""}
    ]

    try:
        response = llm_client.chat_completion(
            messages=messages,
            model_type="pain_extraction",
            json_mode=True
        )
        content = response.get("content", {})
        return content.get("pain_events", [])
    except Exception as e:
        logger.error(f"Old method failed: {e}")
        return []

def extract_with_new_method(post_data: Dict[str, Any], comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """使用新方法提取痛点（含评论）"""
    # 复用现有的 extract_pain_points 方法
    try:
        response = llm_client.extract_pain_points(
            title=post_data.get('title', ''),
            body=post_data.get('body', ''),
            subreddit=post_data.get('subreddit', ''),
            upvotes=post_data.get('score', 0),
            comments_count=post_data.get('num_comments', 0),
            top_comments=comments
        )
        content = response.get("content", {})
        return content.get("pain_events", [])
    except Exception as e:
        logger.error(f"New method failed: {e}")
        return []

def select_test_posts(limit: int = 10) -> List[Dict[str, Any]]:
    """选择测试用帖子（高质量且有评论）"""
    # 选择高pain_score且有足够评论的帖子
    posts = db.get_filtered_posts(limit=50, min_pain_score=0.5)

    # 筛选出有评论数据的帖子
    posts_with_comments = []
    for post in posts:
        comments = db.get_top_comments_for_post(post['id'], top_n=5)
        if len(comments) >= 3:  # 至少3条评论
            post['comments'] = comments
            posts_with_comments.append(post)
        if len(posts_with_comments) >= limit:
            break

    logger.info(f"Selected {len(posts_with_comments)} posts for A/B testing")
    return posts_with_comments

def calculate_quality_metrics(pain_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """计算质量指标"""
    if not pain_events:
        return {
            "event_count": 0,
            "avg_confidence": 0,
            "avg_problem_length": 0,
            "has_workaround_count": 0,
            "has_evidence_sources": 0
        }

    return {
        "event_count": len(pain_events),
        "avg_confidence": sum(e.get("confidence", 0) for e in pain_events) / len(pain_events),
        "avg_problem_length": sum(len(e.get("problem", "")) for e in pain_events) / len(pain_events),
        "has_workaround_count": sum(1 for e in pain_events if e.get("current_workaround")),
        "has_evidence_sources": sum(1 for e in pain_events if e.get("evidence_sources"))
    }

def generate_comparison_report(results: List[Dict[str, Any]]) -> str:
    """生成对比报告"""
    report = ["# A/B Test Report: Comment-Aware Pain Extraction\n"]
    report.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.append(f"**Test Size:** {len(results)} posts\n")
    report.append("---\n\n")

    # 汇总统计
    old_total_events = sum(r['old_metrics']['event_count'] for r in results)
    new_total_events = sum(r['new_metrics']['event_count'] for r in results)
    old_avg_confidence = sum(r['old_metrics']['avg_confidence'] for r in results) / len(results)
    new_avg_confidence = sum(r['new_metrics']['avg_confidence'] for r in results) / len(results)
    old_avg_length = sum(r['old_metrics']['avg_problem_length'] for r in results) / len(results)
    new_avg_length = sum(r['new_metrics']['avg_problem_length'] for r in results) / len(results)

    report.append("## Overall Metrics\n\n")
    report.append(f"| Metric | Old Method | New Method | Change |\n")
    report.append(f"|--------|-----------|-----------|--------|\n")
    report.append(f"| Total Pain Events | {old_total_events} | {new_total_events} | {new_total_events - old_total_events:+d} |\n")
    report.append(f"| Avg Confidence | {old_avg_confidence:.3f} | {new_avg_confidence:.3f} | {(new_avg_confidence - old_avg_confidence):+.3f} |\n")
    report.append(f"| Avg Problem Length | {old_avg_length:.1f} | {new_avg_length:.1f} | {(new_avg_length - old_avg_length):+.1f} |\n")
    report.append("\n")

    # 详细对比
    report.append("## Per-Post Comparison\n\n")
    for i, result in enumerate(results, 1):
        post = result['post']
        old = result['old_metrics']
        new = result['new_metrics']

        report.append(f"### {i}. {post['title'][:60]}...\n\n")
        report.append(f"**Subreddit:** {post['subreddit']} | **Comments:** {len(post.get('comments', []))}\n\n")
        report.append(f"| Metric | Old | New |\n")
        report.append(f"|--------|-----|-----|\n")
        report.append(f"| Events | {old['event_count']} | {new['event_count']} |\n")
        report.append(f"| Confidence | {old['avg_confidence']:.2f} | {new['avg_confidence']:.2f} |\n")
        report.append(f"| Problem Length | {old['avg_problem_length']:.0f} | {new['avg_problem_length']:.0f} |\n")

        # 样本对比
        if old['event_count'] > 0:
            old_events = result['old_events']
            report.append("**Old Method Sample:**\n```\n")
            for e in old_events[:2]:
                report.append(f"- {e.get('problem', 'N/A')[:80]}...\n")
            report.append("```\n")

        if new['event_count'] > 0:
            new_events = result['new_events']
            report.append("**New Method Sample:**\n```\n")
            for e in new_events[:2]:
                evidence = e.get('evidence_sources', [])
                report.append(f"- [{', '.join(evidence)}] {e.get('problem', 'N/A')[:80]}...\n")
            report.append("```\n")

        report.append("\n")

    # 结论
    report.append("## Qualitative Assessment\n\n")
    improvement_count = sum(1 for r in results if r['new_metrics']['avg_problem_length'] > r['old_metrics']['avg_problem_length'])
    report.append(f"- **Specificity Improvement:** {improvement_count}/{len(results)} posts show more detailed problem descriptions\n")
    report.append(f"- **Evidence Tracking:** {sum(r['new_metrics']['has_evidence_sources'] for r in results)} pain events now track evidence sources\n")
    report.append(f"- **Avg Description Length:** {new_avg_length:.0f} vs {old_avg_length:.0f} chars ({((new_avg_length/old_avg_length - 1) * 100):+.0f}% change)\n")

    return "".join(report)

def main():
    """主函数"""
    logger.info("Starting A/B test for comment-aware pain extraction...")

    # 选择测试帖子
    test_posts = select_test_posts(limit=10)
    if not test_posts:
        logger.error("No test posts found!")
        return

    results = []

    # 对每个帖子运行A/B测试
    for i, post in enumerate(test_posts, 1):
        logger.info(f"Testing post {i}/{len(test_posts)}: {post['title'][:50]}...")

        comments = post.get('comments', [])

        # 旧方法（不含评论）
        old_events = extract_with_old_method(post)
        old_metrics = calculate_quality_metrics(old_events)

        # 新方法（含评论）
        new_events = extract_with_new_method(post, comments)
        new_metrics = calculate_quality_metrics(new_events)

        results.append({
            'post': post,
            'old_events': old_events,
            'new_events': new_events,
            'old_metrics': old_metrics,
            'new_metrics': new_metrics
        })

        # 添加延迟避免API限流
        import time
        time.sleep(2)

    # 生成报告
    report = generate_comparison_report(results)

    # 保存报告
    report_path = Path("docs/plans/ab_test_results.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)

    logger.info(f"\n{'='*60}")
    logger.info(f"A/B Test Complete!")
    logger.info(f"Report saved to: {report_path}")
    logger.info(f"{'='*60}\n")

    # 打印摘要
    old_total = sum(r['old_metrics']['event_count'] for r in results)
    new_total = sum(r['new_metrics']['event_count'] for r in results)
    logger.info(f"Total Events: Old={old_total}, New={new_total}")
    logger.info(f"Check the report for detailed analysis")

if __name__ == "__main__":
    main()
```

**Step 2: Make script executable**

Run: `chmod +x scripts/test_comment_aware_extraction.py`

**Step 3: Verify syntax**

Run: `python -m py_compile scripts/test_comment_aware_extraction.py`
Expected: No syntax errors

**Step 4: Commit**

```bash
git add scripts/test_comment_aware_extraction.py
git commit -m "test: add A/B testing script for comment-aware extraction"
```

---

## Task 6: Run A/B test on small batch (10 posts)

**Step 1: Execute the A/B test script**

```bash
python3 scripts/test_comment_aware_extraction.py
```

Expected output:
```
INFO: Selected 10 posts for A/B testing
INFO: Testing post 1/10: I've built 30+ MVPs. The founders who succeed...
INFO: Testing post 2/10: Is it normal that half of consulting is...
...
INFO: A/B Test Complete!
INFO: Report saved to: docs/plans/ab_test_results.md
```

**Step 2: Review the generated report**

Run: `cat docs/plans/ab_test_results.md | head -100`
Expected: Should show comparison table with metrics

**Step 3: Check if improvements are visible**

Look for:
- Higher problem description length (specificity)
- More events extracted (comprehensive coverage)
- Evidence sources tracking
- Workaround mentions

**Step 4: Save the raw test data**

```bash
# Commit the report
git add docs/plans/ab_test_results.md
git commit -m "test: add A/B test results for comment-aware extraction"
```

---

## Task 7: Create quality comparison analysis document

**Files:**
- Create: `docs/plans/phase2-quality-analysis.md`

**Step 1: Create the analysis document template**

```markdown
# Phase 2 Quality Analysis: Comment-Aware Pain Extraction

**Date:** 2025-12-25
**Test Size:** 10 posts
**Test Posts:** Selected from high pain_score posts with 3+ comments each

## Executive Summary

[Fill in after running A/B test]

## Detailed Findings

### 1. Specificity Improvement

**Metric:** Average problem description length

- **Old Method:** X chars
- **New Method:** Y chars
- **Improvement:** Z%

**Qualitative Examples:**

| Post | Old (Generic) | New (Specific) |
|------|--------------|----------------|
| 1 | "Software is too complex" | "Users complain existing software requires complex plugin configuration to sync data" |
| 2 | ... | ... |

### 2. Evidence Quality

**Metric:** Pain events with comment evidence

- **Old Method:** N/A (no tracking)
- **New Method:** X% of events include comment evidence

### 3. Solution Clues

**Metric:** Pain events mentioning workarounds

- **Old Method:** X events
- **New Method:** Y events

**Analysis:** Comments often reveal actual workarounds users employ.

### 4. Confidence Scores

- **Old Method:** Avg X
- **New Method:** Avg Y

**Interpretation:** [Fill in analysis]

## Per-Post Analysis

### Post 1: [Title]

**Context:** Subreddit, X comments

**Old Method Results:**
- Extracted X pain events
- Sample: [...]
- Issues: [Vague, missing context]

**New Method Results:**
- Extracted Y pain events
- Sample: [...]
- Improvements: [More specific, includes comment insights]

### Post 2: [Title]
[Repeat for each post...]

## Limitations

1. Small sample size (10 posts)
2. Only posts with 3+ comments tested
3. Comments quality varies by subreddit

## Recommendations

1. [Based on findings, recommend whether to deploy]

## Conclusion

[Summary of whether comment-aware extraction provides value]
```

**Step 2: Fill in the template with actual data**

After running the A/B test, populate the template with real findings.

**Step 3: Commit**

```bash
git add docs/plans/phase2-quality-analysis.md
git commit -m "docs: add Phase 2 quality analysis document"
```

---

## Task 8: End-to-end small batch test

**Step 1: Backup existing pain_events table**

```bash
# Backup current pain_events
sqlite3 data/wise_collection.db ".dump pain_events" > data/pain_events_backup_$(date +%Y%m%d_%H%M%S).sql
```

**Step 2: Clear test data (optional)**

```bash
# Option A: Delete pain_events for test posts only
# Get list of test post IDs from A/B test first

# Option B: Use a separate test database
cp data/wise_collection.db data/wise_collection_test.db
# Then modify db.py to point to test DB for this run
```

**Step 3: Run extraction on 10-15 posts**

```bash
python3 -c "
from pipeline.extract_pain import PainPointExtractor
from utils.db import db

# Get test posts
posts = db.get_filtered_posts(limit=15, min_pain_score=0.5)
print(f'Extracting from {len(posts)} posts...')

extractor = PainPointExtractor()
result = extractor.extract_from_posts_batch(posts[:10])

print(f'Extracted {len(result)} pain events')
"
```

**Step 4: Verify results**

```bash
# Check extracted pain_events
sqlite3 data/wise_collection.db "
SELECT pe.post_id, pe.problem, pe.comments_used, pe.evidence_sources
FROM pain_events pe
JOIN filtered_posts fp ON pe.post_id = fp.id
ORDER BY pe.extracted_at DESC
LIMIT 20;
"
```

Expected: Should see `comments_used` and `evidence_sources` fields populated

**Step 5: Run clustering on extracted events**

```bash
python3 -m pipeline.cluster --limit 20
```

**Step 6: Verify cluster quality**

```bash
# Check clusters
sqlite3 data/wise_collection.db "
SELECT cluster_name, cluster_size, common_pain
FROM clusters
ORDER BY created_at DESC
LIMIT 5;
"
```

---

## Task 9: Verification and acceptance criteria

**Step 1: Verify functional requirements**

Run: `python3 -c "
from utils.db import db
import json

# Check 1: Verify comments_used field exists
result = db.get_cross_table_stats()
print(f'Pain events count: {result.get(\"pain_events_count\", 0)}')

# Check 2: Sample pain events with comment data
import sqlite3
conn = sqlite3.connect('data/wise_collection.db')
conn.row_factory = sqlite3.Row
cursor = conn.execute('''
    SELECT problem, comments_used, evidence_sources
    FROM pain_events
    WHERE comments_used IS NOT NULL
    LIMIT 5
''')
for row in cursor.fetchall():
    print(f'Problem: {row[\"problem\"][:50]}...')
    print(f'  Comments used: {row[\"comments_used\"]}')
    print(f'  Evidence: {row[\"evidence_sources\"]}')
    print()
conn.close()
"`
Expected: Should show pain events with `comments_used` > 0 and `evidence_sources` tracking

**Step 2: Verify quality improvements**

Compare A/B test report metrics:
- [ ] Problem descriptions are more specific (length increased by 20%+)
- [ ] Evidence sources are tracked
- [ ] Workaround mentions increased
- [ ] Confidence scores maintained or improved

**Step 3: Run pipeline validation**

```bash
# Test the complete pipeline doesn't break
python3 -m pipeline.filter_signal --limit 5
python3 -m pipeline.extract_pain --limit 5
```

Expected: No errors, completes successfully

**Step 4: Create final summary**

Create a brief summary document:

```markdown
# Phase 2 Implementation Summary

**Completed:** 2025-12-25

## Changes Made

1. **Database Layer**: Added `get_top_comments_for_post()` method
2. **LLM Client**: Updated `extract_pain_points()` to accept comments, enhanced prompt
3. **Extractor**: Modified to load comments and pass to LLM
4. **Testing**: Created A/B test script and quality comparison framework

## Results

- **Posts Tested:** X
- **Improvement in Specificity:** Y%
- **Evidence Tracking:** Z% of events now track sources
- **Confidence:** Maintained at X.X

## Next Steps

1. Deploy to production pipeline
2. Monitor quality metrics on larger dataset
3. Consider tuning `top_n` comments parameter
```

**Step 5: Commit final changes**

```bash
git add docs/plans/
git commit -m "docs: add Phase 2 implementation summary"
```

---

## Acceptance Criteria Summary

Upon completion, the following should be true:

### Functional
- ✅ `get_top_comments_for_post()` method works in `utils/db.py`
- ✅ `extract_pain_points()` accepts `top_comments` parameter
- ✅ Pain extraction prompt includes comment-aware instructions
- ✅ Extracted pain events include `comments_used` and `evidence_sources` fields
- ✅ Small batch (10-15 posts) end-to-end test completes without errors

### Quality
- ✅ Problem descriptions are more specific (20%+ longer on average)
- ✅ Evidence sources are tracked for pain events
- ✅ Workaround mentions are captured more frequently
- ✅ Confidence scores are maintained or improved

### Documentation
- ✅ A/B test report generated showing before/after comparison
- ✅ Quality analysis document created with findings
- ✅ Implementation summary with recommendations

### Optional Enhancements (if time permits)
- [ ] Add `top_n` as configurable parameter in config/llm.yaml
- [ ] Create visualization for quality improvement metrics
- [ ] Add comment quality filtering (ignore low-effort comments)
