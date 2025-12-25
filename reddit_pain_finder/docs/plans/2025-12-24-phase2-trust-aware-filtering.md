# Phase 2: Trust-Aware Filtering & Aspiration Signals Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand signal sources by safely unblocking high-value/high-noise subreddits with trust-aware dynamic filtering and aspiration-based signal detection.

**Architecture:**
1. Modify `config/subreddits.yaml` to add `noisy_tech` category with low trust_level (0.4) and `aspiration_keywords`
2. Upgrade `pipeline/filter_signal.py` to implement trust-aware dynamic thresholds and aspiration keyword detection
3. Validate data changes through database queries after running pipeline

**Tech Stack:** Python 3.x, YAML configuration, SQLite database

---

## Task 1: Modify subreddits.yaml - Remove ignore list entries

**Files:**
- Modify: `config/subreddits.yaml:187-195`

**Step 1: Edit the ignore list**

Remove `programming`, `learnprogramming`, `ChatGPT`, `OpenAI` from the ignore list.

```yaml
# Before:
ignore:
  - technology
  - Futurism
  - artificial
  - ChatGPT
  - OpenAI
  - programming
  - learnprogramming

# After:
ignore:
  - technology
  - Futurism
  - artificial
```

**Step 2: Verify the change**

Run: `grep -A 10 "^ignore:" config/subreddits.yaml`
Expected: The ignore list should only contain `technology`, `Futurism`, `artificial`

**Step 3: Commit**

```bash
git add config/subreddits.yaml
git commit -m "chore: remove programming-related subreddits from ignore list"
```

---

## Task 2: Add noisy_tech category to subreddits.yaml

**Files:**
- Modify: `config/subreddits.yaml:80-96`

**Step 1: Add the noisy_tech category after experimental section**

```yaml
# Add after experimental section (after line 96):
# =========================
# Noisy Tech: 高噪音但有价值
# =========================
noisy_tech:
  trust_level: 0.4
  programming:
    min_upvotes: 20
    min_comments: 10
    notes: >
      High volume, low signal-to-noise. Requires strict filtering.
      Look for specific pain points, not general discussions.

  learnprogramming:
    min_upvotes: 15
    min_comments: 8
    notes: >
      Beginners often express pain differently. Focus on repeated
      obstacles in learning, not one-off questions.

  ChatGPT:
    min_upvotes: 25
    min_comments: 15
    notes: >
      AI tool users. Focus on workflow integration pain, not
      prompt engineering or capability showcase.

  OpenAI:
    min_upvotes: 25
    min_comments: 15
    notes: >
      Similar to ChatGPT. Focus on API integration, production
      deployment, and scaling challenges.
```

**Step 2: Verify the change**

Run: `grep -A 45 "noisy_tech:" config/subreddits.yaml | head -50`
Expected: Should see the new `noisy_tech` category with all 4 subreddits

**Step 3: Commit**

```bash
git add config/subreddits.yaml
git commit -m "feat: add noisy_tech category with programming subreddits at trust_level 0.4"
```

---

## Task 3: Remove exclude patterns in subreddits.yaml

**Files:**
- Modify: `config/subreddits.yaml:153-176`

**Step 1: Edit the question exclusion patterns**

```yaml
# Before:
  question:
    - "how do i"
    - "what is the best"
    - "any recommendations"
    - "looking for advice"

# After:
  question:
    - "any recommendations"
    - "looking for advice"
```

**Step 2: Edit the off_topic exclusion patterns**

```yaml
# Before:
  off_topic:
    - "meme"
    - "discussion"
    - "general"

# After:
  off_topic:
    - "meme"
    - "general"
```

**Step 3: Verify the changes**

Run: `grep -A 20 "exclude_patterns:" config/subreddits.yaml | grep -E "(question|off_topic)" -A 4`
Expected: "how do i", "what is the best", and "discussion" should NOT appear

**Step 4: Commit**

```bash
git add config/subreddits.yaml
git commit -m "feat: relax exclusion patterns to capture more signals"
```

---

## Task 4: Add aspiration_keywords to subreddits.yaml

**Files:**
- Modify: `config/subreddits.yaml:148-150` (insert after pain_keywords section)

**Step 1: Add the aspiration_keywords section**

```yaml
# Add after pain_keywords section (after line 148):
# =========================
# Aspiration Keywords Configuration
# =========================
aspiration_keywords:
  forward_looking:
    - "wish i had"
    - "if only there was"
    - "my dream tool would"
    - "would be amazing if"
    - "i wish someone would build"
    - "someone should make"
    - "looking for a tool that"
    - "need a way to"
  opportunity:
    - "there should be a"
    - "why isn't there a"
    - "can't believe no one has"
    - "surprised there's no"
    - "would pay for"
    - "would subscribe to"
  workflow_gap:
    - "manual process"
    - "currently i have to"
    - "still doing manually"
    - "tired of doing"
    - "hate that i have to"
```

**Step 2: Verify the addition**

Run: `grep -A 25 "aspiration_keywords:" config/subreddits.yaml`
Expected: Should see three categories (forward_looking, opportunity, workflow_gap) with keywords

**Step 3: Commit**

```bash
git add config/subreddits.yaml
git commit -m "feat: add aspiration_keywords for opportunity detection"
```

---

## Task 5: Add aspiration keyword detection method to PainSignalFilter

**Files:**
- Modify: `pipeline/filter_signal.py`

**Step 1: Add _check_aspiration_keywords method**

Add this new method after `_check_pain_keywords` method (after line 106):

```python
    def _check_aspiration_keywords(self, post_data: Dict[str, Any]) -> Tuple[bool, List[str], float]:
        """检查愿望关键词 - 寻找机会信号"""
        title = (post_data.get("title", "")).lower()
        body = (post_data.get("body", "")).lower()
        full_text = f"{title} {body}"

        aspiration_keywords = self.subreddits_config.get("aspiration_keywords", {})
        matched_keywords = []
        keyword_scores = {}

        # 统计各类别关键词匹配
        for category, keywords in aspiration_keywords.items():
            category_matches = 0
            category_weight = {
                "forward_looking": 1.0,
                "opportunity": 0.9,
                "workflow_gap": 0.8
            }.get(category, 0.5)

            for keyword in keywords:
                if keyword.lower() in full_text:
                    matched_keywords.append(f"{category}:{keyword}")
                    category_matches += 1
                    keyword_scores[keyword] = category_weight

            # 计算该类别的得分
            if category_matches > 0:
                keyword_scores[f"category_{category}"] = category_matches * category_weight

        # 计算总愿望分数
        total_score = sum(score for score in keyword_scores.values() if isinstance(score, (int, float)))

        # 标准化分数（0-1范围）
        normalized_score = min(total_score / 3.0, 1.0)  # 3分为满分

        return len(matched_keywords) > 0, matched_keywords, normalized_score
```

**Step 2: Verify syntax**

Run: `python -m py_compile pipeline/filter_signal.py`
Expected: No syntax errors

**Step 3: Commit**

```bash
git add pipeline/filter_signal.py
git commit -m "feat: add aspiration keyword detection method"
```

---

## Task 6: Add trust-aware threshold helper method

**Files:**
- Modify: `pipeline/filter_signal.py`

**Step 1: Add _get_trust_based_thresholds method**

Add this new method after `_check_post_type_specific` method (after line 214):

```python
    def _get_trust_based_thresholds(self, post_data: Dict[str, Any]) -> Dict[str, int]:
        """根据帖子所属subreddit的trust_level返回动态阈值"""
        subreddit = post_data.get("subreddit", "").lower()

        # 查找subreddit所属category及其trust_level
        trust_level = 0.5  # 默认值
        for category_name, category_config in self.subreddits_config.get("categories", {}).items():
            if isinstance(category_config, dict):
                # 检查category级别的trust_level
                if "trust_level" in category_config:
                    category_trust = category_config["trust_level"]
                    # 检查subreddit是否在这个category下
                    for sub_name in category_config.keys():
                        if sub_name.lower() == subreddit and sub_name != "trust_level":
                            trust_level = category_trust
                            break

        # 从posts表获取trust_level（如果有）
        post_trust_level = post_data.get("trust_level", trust_level)

        # 根据trust_level返回阈值
        if post_trust_level < 0.5:
            # 低信任度板块 - 更严格的标准
            return {
                "min_comments": 20,
                "min_upvotes": 50,
                "min_engagement_score": 0.6
            }
        elif post_trust_level < 0.7:
            # 中等信任度板块 - 中等标准
            return {
                "min_comments": 10,
                "min_upvotes": 25,
                "min_engagement_score": 0.4
            }
        else:
            # 高信任度板块 - 标准阈值
            return {
                "min_comments": 5,
                "min_upvotes": 10,
                "min_engagement_score": 0.2
            }
```

**Step 2: Verify syntax**

Run: `python -m py_compile pipeline/filter_signal.py`
Expected: No syntax errors

**Step 3: Commit**

```bash
git add pipeline/filter_signal.py
git commit -m "feat: add trust-based threshold helper method"
```

---

## Task 7: Update filter_post to integrate aspiration and trust-aware filtering

**Files:**
- Modify: `pipeline/filter_signal.py:216-335`

**Step 1: Modify filter_post method to call aspiration check**

After the pain keywords check (around line 250-252), add:

```python
        # 3.5 愿望关键词检查
        has_aspiration, matched_aspirations, aspiration_score = self._check_aspiration_keywords(post_data)
        filter_result["matched_aspirations"] = matched_aspirations
```

**Step 2: Add trust-based threshold check**

After the type specific check (around line 268), add:

```python
        # 6.5 基于信任度的动态阈值检查
        trust_thresholds = self._get_trust_based_thresholds(post_data)
        min_comments = trust_thresholds["min_comments"]
        min_upvotes = trust_thresholds["min_upvotes"]
        min_engagement_score = trust_thresholds["min_engagement_score"]

        # 计算参与度分数
        engagement_score = min(
            (post_data.get("score", 0) / min_upvotes + post_data.get("num_comments", 0) / min_comments) / 2.0,
            1.0
        )

        # 对于低信任度板块，必须满足参与度要求
        if post_data.get("trust_level", 0.5) < 0.5 and engagement_score < min_engagement_score:
            self.stats["filtered_out"] += 1
            failure_reason = f"Low trust post with insufficient engagement: {engagement_score:.2f} < {min_engagement_score}"
            self.stats["filter_reasons"][failure_reason] = self.stats["filter_reasons"].get(failure_reason, 0) + 1
            filter_result["reasons"].append(failure_reason)
            filter_result["filter_summary"] = {
                "reason": "trust_based_engagement",
                "details": {
                    "trust_level": post_data.get("trust_level", 0.5),
                    "engagement_score": engagement_score,
                    "min_required": min_engagement_score
                }
            }
            return False, filter_result

        filter_result["engagement_score"] = engagement_score
        filter_result["trust_level"] = post_data.get("trust_level", 0.5)
```

**Step 3: Modify final pass logic to include aspiration signals**

Update the final pass判断 (around line 300-305) to:

```python
        # 判断是否通过痛点信号检查
        pain_config = self.thresholds.get("pain_signal", {})
        min_keyword_matches = pain_config.get("keyword_match", {}).get("min_matches", 1)
        min_emotional_intensity = pain_config.get("emotional_intensity", {}).get("min_score", 0.3)

        # 最终判断 - 支持愿望信号通过
        passed = False

        # 路径1: 强痛点信号（原有逻辑）
        if (has_keywords and
            len(matched_keywords) >= min_keyword_matches and
            emotional_intensity >= min_emotional_intensity and
            pain_score >= 0.3):
            passed = True

        # 路径2: 愿望信号 + 高参与度（新增逻辑）
        elif (has_aspiration and
              engagement_score >= min_engagement_score and
              aspiration_score >= 0.4):
            passed = True
            filter_result["pass_type"] = "aspiration"
            filter_result["aspiration_score"] = aspiration_score
        else:
            filter_result["pass_type"] = "pain"
```

**Step 4: Update filter_result for pass type**

Move the `pass_type` assignment earlier, before the if/else block (around line 309):

```python
        # Set default pass_type if not already set
        if "pass_type" not in filter_result:
            filter_result["pass_type"] = "pain"
```

**Step 5: Verify syntax**

Run: `python -m py_compile pipeline/filter_signal.py`
Expected: No syntax errors

**Step 6: Commit**

```bash
git add pipeline/filter_signal.py
git commit -m "feat: integrate aspiration signals and trust-aware filtering"
```

---

## Task 8: Update filter_posts_batch to preserve aspiration data

**Files:**
- Modify: `pipeline/filter_signal.py:337-361`

**Step 1: Modify the post enrichment section**

Update the filtered_post construction (around line 350-357):

```python
                filtered_post = post.copy()
                filtered_post.update({
                    "pain_score": result["pain_score"],
                    "pain_keywords": result["matched_keywords"],
                    "pain_patterns": result["matched_patterns"],
                    "emotional_intensity": result["emotional_intensity"],
                    "filter_reason": "pain_signal_passed",
                    "aspiration_keywords": result.get("matched_aspirations", []),
                    "aspiration_score": result.get("aspiration_score", 0.0),
                    "pass_type": result.get("pass_type", "pain"),
                    "engagement_score": result.get("engagement_score", 0.0),
                    "trust_level": result.get("trust_level", 0.5)
                })
```

**Step 2: Verify syntax**

Run: `python -m py_compile pipeline/filter_signal.py`
Expected: No syntax errors

**Step 3: Commit**

```bash
git add pipeline/filter_signal.py
git commit -m "feat: preserve aspiration and trust metadata in filtered posts"
```

---

## Task 9: Write validation script for aspiration signal detection

**Files:**
- Create: `scripts/validate_phase2.py`

**Step 1: Create the validation script**

```python
#!/usr/bin/env python3
"""
Validation script for Phase 2: Trust-Aware Filtering & Aspiration Signals
验证脚本 - 检查Phase 2升级是否成功
"""
import sys
import yaml
import sqlite3
from pathlib import Path

def check_config_changes():
    """检查配置文件修改"""
    print("=== Checking Configuration Changes ===")

    config_path = Path("config/subreddits.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Check 1: Ignore list should NOT contain programming subreddits
    ignore_list = config.get("ignore", [])
    removed_subs = ["programming", "learnprogramming", "ChatGPT", "OpenAI"]
    still_ignored = [sub for sub in removed_subs if sub in ignore_list]

    if still_ignored:
        print(f"❌ FAIL: Subreddits still in ignore list: {still_ignored}")
        return False
    else:
        print(f"✅ PASS: Programming subreddits removed from ignore list")

    # Check 2: noisy_tech category should exist
    if "noisy_tech" not in config:
        print("❌ FAIL: noisy_tech category not found")
        return False
    print("✅ PASS: noisy_tech category exists")

    # Check 3: noisy_tech should have trust_level 0.4
    noisy_tech = config["noisy_tech"]
    if noisy_tech.get("trust_level") != 0.4:
        print(f"❌ FAIL: noisy_tech trust_level is {noisy_tech.get('trust_level')}, expected 0.4")
        return False
    print("✅ PASS: noisy_tech has trust_level 0.4")

    # Check 4: aspiration_keywords should exist
    if "aspiration_keywords" not in config:
        print("❌ FAIL: aspiration_keywords not found")
        return False
    print("✅ PASS: aspiration_keywords exists")

    # Check 5: Exclude patterns should be relaxed
    exclude_patterns = config.get("exclude_patterns", {})
    question_patterns = exclude_patterns.get("question", [])
    off_topic_patterns = exclude_patterns.get("off_topic", [])

    forbidden_question = ["how do i", "what is the best"]
    forbidden_off_topic = ["discussion"]

    found_forbidden = []
    for pattern in forbidden_question:
        if pattern in question_patterns:
            found_forbidden.append(f"question:{pattern}")

    for pattern in forbidden_off_topic:
        if pattern in off_topic_patterns:
            found_forbidden.append(f"off_topic:{pattern}")

    if found_forbidden:
        print(f"❌ FAIL: Forbidden patterns still in exclude list: {found_forbidden}")
        return False
    print("✅ PASS: Exclude patterns relaxed correctly")

    return True

def check_database_state(db_path="data/wise_collection.db"):
    """检查数据库状态（需要先运行pipeline）"""
    print("\n=== Checking Database State ===")

    if not Path(db_path).exists():
        print(f"⚠️  SKIP: Database not found at {db_path}")
        print("   Run the pipeline first: python -m pipeline.fetch && python -m pipeline.filter_signal")
        return True

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check 1: Posts table should have trust_level column
    cursor.execute("PRAGMA table_info(posts)")
    columns = {row["name"] for row in cursor.fetchall()}
    if "trust_level" not in columns:
        print("❌ FAIL: posts table missing trust_level column")
        return False
    print("✅ PASS: posts table has trust_level column")

    # Check 2: Check if posts from new subreddits exist
    new_subreddits = ["programming", "learnprogramming", "ChatGPT", "OpenAI"]
    placeholders = ",".join("?" * len(new_subreddits))
    cursor.execute(f"SELECT COUNT(*) as count FROM posts WHERE subreddit IN ({placeholders})", new_subreddits)
    count = cursor.fetchone()["count"]

    if count > 0:
        print(f"✅ PASS: Found {count} posts from newly added subreddits")
    else:
        print(f"⚠️  INFO: No posts from new subreddits yet (run fetch first)")

    # Check 3: Check for aspiration-based filtered posts
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM filtered_posts
        WHERE filter_reason LIKE '%aspiration%'
    """)
    aspiration_count = cursor.fetchone()["count"]

    # Note: This requires schema update to filter_reason or new column
    print(f"ℹ️  INFO: Aspiration-based filtering count: {aspiration_count}")

    # Check 4: Trust level distribution
    cursor.execute("""
        SELECT trust_level, COUNT(*) as count
        FROM posts
        WHERE trust_level IS NOT NULL
        GROUP BY trust_level
        ORDER BY trust_level
    """)
    print("\n   Trust level distribution:")
    for row in cursor.fetchall():
        print(f"     {row['trust_level']}: {row['count']} posts")

    conn.close()
    return True

def main():
    """主函数"""
    print("Phase 2 Validation Script")
    print("=" * 50)

    config_ok = check_config_changes()
    db_ok = check_database_state()

    print("\n" + "=" * 50)
    if config_ok and db_ok:
        print("✅ VALIDATION PASSED")
        return 0
    else:
        print("❌ VALIDATION FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Make script executable**

Run: `chmod +x scripts/validate_phase2.py`

**Step 3: Run validation**

Run: `python3 scripts/validate_phase2.py`
Expected: All checks should pass

**Step 4: Commit**

```bash
git add scripts/validate_phase2.py
git commit -m "test: add Phase 2 validation script"
```

---

## Task 10: Run validation and verify configuration

**Step 1: Run the validation script**

```bash
python3 scripts/validate_phase2.py
```

Expected output:
```
Phase 2 Validation Script
==================================================
=== Checking Configuration Changes ===
✅ PASS: Programming subreddits removed from ignore list
✅ PASS: noisy_tech category exists
✅ PASS: noisy_tech has trust_level 0.4
✅ PASS: aspiration_keywords exists
✅ PASS: Exclude patterns relaxed correctly

=== Checking Database State ===
⚠️  SKIP: Database not found at data/wise_collection.db
   Run the pipeline first: python -m pipeline.fetch && python -m pipeline.filter_signal

==================================================
✅ VALIDATION PASSED
```

**Step 2: If validation fails, fix issues and re-run**

---

## Task 11: Test pipeline with new configuration (Manual)

**Step 1: Run fetch to get posts from new subreddits**

```bash
python3 -m pipeline.fetch --limit 100
```

**Step 2: Run filter to test new filtering logic**

```bash
python3 -m pipeline.filter_signal --limit 100
```

**Step 3: Check database for results**

```bash
sqlite3 data/wise_collection.db "SELECT subreddit, COUNT(*) FROM posts GROUP BY subreddit;"
sqlite3 data/wise_collection.db "SELECT COUNT(*) FROM filtered_posts;"
```

**Step 4: Query for aspiration-based posts**

```bash
sqlite3 data/wise_collection.db "SELECT id, title, subreddit FROM filtered_posts WHERE pass_type='aspiration' LIMIT 10;"
```

Expected: Should see posts from programming, learnprogramming, ChatGPT, OpenAI

---

## Task 12: Verify acceptance criteria

**Step 1: Check ignore list is cleaned**

```bash
grep -A 10 "^ignore:" config/subreddits.yaml
```

Expected: Should only see `technology`, `Futurism`, `artificial`

**Step 2: Check aspiration_keywords added**

```bash
grep -A 25 "aspiration_keywords:" config/subreddits.yaml
```

Expected: Should see three categories with keywords

**Step 3: Verify database has posts from new subreddits**

```bash
sqlite3 data/wise_collection.db "SELECT DISTINCT subreddit FROM posts WHERE subreddit IN ('programming', 'learnprogramming', 'ChatGPT', 'OpenAI');"
```

Expected: Should return at least one subreddit name

**Step 4: Verify aspiration posts exist**

```bash
sqlite3 data/wise_collection.db "SELECT COUNT(*) FROM filtered_posts WHERE pass_type='aspiration';"
```

Expected: Should be 5-10+ posts (after running pipeline with sufficient data)

**Step 5: Commit final validation**

```bash
git add scripts/validate_phase2.py
git commit -m "test: validate Phase 2 acceptance criteria"
```

---

## Acceptance Criteria Summary

Upon completion, the following should be true:

- ✅ `ignore` list is cleaned (no programming-related subreddits)
- ✅ `exclude_patterns` relaxed ("how do i", "what is the best", "discussion" removed)
- ✅ `aspiration_keywords` added with three categories
- ✅ `noisy_tech` category with `trust_level: 0.4` added
- ✅ Database contains posts from `programming`, `OpenAI` etc.
- ✅ 5-10+ aspiration-based posts detected in filtered_posts
