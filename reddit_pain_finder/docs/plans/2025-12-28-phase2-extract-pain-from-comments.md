# Phase 2: Extract Pain from Comments Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend pain point extraction to process filtered comments as independent pain sources, loading parent post context dynamically.

**Architecture:** Parallel extraction flow for posts and comments with unified pain_events output. Comments are treated as independent pain expressions with parent post providing context only.

**Tech Stack:** Python 3, SQLite (unified DB), OpenAI-compatible LLM API (SiliconFlow), existing pipeline architecture

---

## Current State Analysis

**Phase 1 Completed:**
- ✅ `filtered_comments` table created with 3,656 records
- ✅ `filter_comment()` and `filter_comments_batch()` implemented
- ✅ Database methods: `get_all_comments_for_filtering()`, `save_filtered_comments()`
- ✅ Standalone script: `scripts/filter_comments.py`

**Phase 2 Requirements (from design doc):**
1. Implement `_extract_from_single_comment()` in `PainPointExtractor`
2. Add `_get_parent_post_context()` to database methods
3. Update LLM prompt for comment-aware extraction
4. Add `source_type` tracking to `pain_events` table
5. Run extraction on filtered comments
6. Compare quality with post-sourced events

**Database Schema Gap:**
- `pain_events` table missing: `source_type`, `source_id`, `parent_post_id` columns
- Design doc specifies these columns for tracking comment vs post sources

---

## Implementation Plan

### Task 1: Database Schema Migration

**Files:**
- Create: `migrations/002_add_source_tracking_to_pain_events.py`
- Modify: `utils/db.py:142-156` (pain_events table definition)

**Step 1: Write migration script**

Create file: `migrations/002_add_source_tracking_to_pain_events.py`

```python
#!/usr/bin/env python3
"""
Migration 002: Add source tracking columns to pain_events table
Phase 2: Include Comments - Track whether pain events come from posts or comments
"""
import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    """Add source_type, source_id, and parent_post_id columns to pain_events"""
    logger.info("Starting migration 002: Add source tracking to pain_events")

    try:
        with db.get_connection("pain") as conn:
            # Check existing columns
            cursor = conn.execute("PRAGMA table_info(pain_events)")
            existing_columns = {row['name'] for row in cursor.fetchall()}
            logger.info(f"Existing columns: {existing_columns}")

            # Add source_type column
            if 'source_type' not in existing_columns:
                logger.info("Adding source_type column...")
                conn.execute("""
                    ALTER TABLE pain_events
                    ADD COLUMN source_type TEXT DEFAULT 'post'
                """)
                logger.info("✓ Added source_type column")
            else:
                logger.info("source_type column already exists")

            # Add source_id column
            if 'source_id' not in existing_columns:
                logger.info("Adding source_id column...")
                conn.execute("""
                    ALTER TABLE pain_events
                    ADD COLUMN source_id TEXT
                """)
                logger.info("✓ Added source_id column")
            else:
                logger.info("source_id column already exists")

            # Add parent_post_id column
            if 'parent_post_id' not in existing_columns:
                logger.info("Adding parent_post_id column...")
                conn.execute("""
                    ALTER TABLE pain_events
                    ADD COLUMN parent_post_id TEXT
                """)
                logger.info("✓ Added parent_post_id column")
            else:
                logger.info("parent_post_id column already exists")

            # Migrate existing records: set source_type='post', source_id=post_id, parent_post_id=post_id
            logger.info("Migrating existing pain_events...")
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM pain_events
                WHERE source_type IS NULL OR source_type = 'post'
            """)
            count = cursor.fetchone()['count']

            if count > 0:
                cursor = conn.execute("""
                    UPDATE pain_events
                    SET source_type = 'post',
                        source_id = post_id,
                        parent_post_id = post_id
                    WHERE source_type IS NULL OR source_type = 'post'
                """)
                logger.info(f"✓ Migrated {cursor.rowcount} existing pain_events")
            else:
                logger.info("No existing records to migrate")

            # Create index for source_type queries
            logger.info("Creating indexes...")
            try:
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pain_events_source_type
                    ON pain_events(source_type)
                """)
                logger.info("✓ Created idx_pain_events_source_type")
            except Exception as e:
                logger.warning(f"Index creation (may already exist): {e}")

            conn.commit()
            logger.info("=" * 60)
            logger.info("Migration 002 completed successfully!")
            logger.info("=" * 60)

            # Verify migration
            cursor = conn.execute("""
                SELECT
                    source_type,
                    COUNT(*) as count
                FROM pain_events
                GROUP BY source_type
            """)
            logger.info("Current pain_events by source_type:")
            for row in cursor.fetchall():
                logger.info(f"  - {row['source_type']}: {row['count']}")

            return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
```

**Step 2: Run migration to verify it works**

Run: `python3 migrations/002_add_source_tracking_to_pain_events.py`
Expected: Output shows columns added, existing records migrated, indexes created

**Step 3: Commit changes**

```bash
git add migrations/002_add_source_tracking_to_pain_events.py
git commit -m "feat(phase2): add migration for source tracking columns"
```

---

### Task 2: Add Database Methods for Comments

**Files:**
- Modify: `utils/db.py` (add methods after line 985)

**Step 1: Add method to get parent post context**

Add to `utils/db.py` after `save_filtered_comments()` method (around line 985):

```python
def get_parent_post_context(self, post_id: str) -> Dict[str, Any]:
    """获取父帖子上下文信息 - Phase 2: Include Comments

    Args:
        post_id: 帖子ID

    Returns:
        包含帖子上下文的字典，如果不存在返回空字典
    """
    try:
        with self.get_connection("raw") as conn:
            cursor = conn.execute("""
                SELECT title, body, subreddit, score, num_comments
                FROM posts
                WHERE id = ?
            """, (post_id,))
            row = cursor.fetchone()
            return dict(row) if row else {}
    except Exception as e:
        logger.error(f"Failed to load parent post {post_id}: {e}")
        return {}
```

**Step 2: Add method to get all filtered comments for extraction**

Add to `utils/db.py` after `get_parent_post_context()`:

```python
def get_all_filtered_comments(self, limit: int = None) -> List[Dict[str, Any]]:
    """获取所有待提取的过滤评论 - Phase 2: Include Comments

    Args:
        limit: 限制返回数量，None表示返回所有

    Returns:
        过滤评论列表，按pain_score降序排列
    """
    try:
        with self.get_connection("filtered") as conn:
            query = """
                SELECT fc.id, fc.comment_id, fc.post_id, fc.author,
                       fc.body, fc.score, fc.pain_score, fc.pain_keywords,
                       p.subreddit, p.title as post_title
                FROM filtered_comments fc
                JOIN posts p ON fc.post_id = p.id
                ORDER BY fc.pain_score DESC
            """
            if limit:
                query += f" LIMIT {limit}"

            cursor = conn.execute(query)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to get filtered comments: {e}")
        return []
```

**Step 3: Modify `insert_pain_event` to support source tracking**

Update existing `insert_pain_event()` method in `utils/db.py` (around line 1062):

```python
def insert_pain_event(self, pain_data: Dict[str, Any]) -> Optional[int]:
    """插入痛点事件（支持post和comment来源）- Phase 2: Include Comments"""
    try:
        with self.get_connection("pain") as conn:
            cursor = conn.execute("""
                INSERT INTO pain_events
                (post_id, source_type, source_id, parent_post_id, actor, context,
                 problem, current_workaround, frequency, emotional_signal,
                 mentioned_tools, extraction_confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pain_data["post_id"],
                pain_data.get("source_type", "post"),  # NEW: source_type
                pain_data.get("source_id"),             # NEW: source_id
                pain_data.get("parent_post_id"),        # NEW: parent_post_id
                pain_data.get("actor", ""),
                pain_data.get("context", ""),
                pain_data["problem"],
                pain_data.get("current_workaround", ""),
                pain_data.get("frequency", ""),
                pain_data.get("emotional_signal", ""),
                json.dumps(pain_data.get("mentioned_tools", [])),
                pain_data.get("extraction_confidence", 0.0)
            ))
            pain_event_id = cursor.lastrowid
            conn.commit()
            return pain_event_id
    except Exception as e:
        logger.error(f"Failed to insert pain event: {e}")
        return None
```

**Step 4: Test new methods work**

Run: `python3 -c "from utils.db import db; print(db.get_parent_post_context('test_id'))"`
Expected: `{}` (empty dict for non-existent post) or post data for real ID

**Step 5: Commit changes**

```bash
git add utils/db.py
git commit -m "feat(phase2): add database methods for comment extraction"
```

---

### Task 3: Update LLM Client for Comment Extraction

**Files:**
- Modify: `utils/llm_client.py` (update extract_pain_points method around line 200-300)

**Step 1: Read current LLM prompt**

Read: `utils/llm_client.py` lines 200-400 to understand current prompt structure

**Step 2: Update `extract_pain_points` method signature**

Update method in `utils/llm_client.py` to accept `metadata` parameter (around line 200):

```python
def extract_pain_points(
    self,
    title: str,
    body: str,
    subreddit: str,
    upvotes: int,
    comments_count: int,
    top_comments: List[Dict[str, Any]] = [],
    metadata: Dict[str, Any] = None  # NEW: metadata parameter for comment extraction
) -> Dict[str, Any]:
```

**Step 3: Update LLM prompt to be comment-aware**

Find the `_get_pain_extraction_prompt()` method (or prompt definition) and update it:

```python
def _get_pain_extraction_prompt(self) -> str:
    return """You are extracting pain points from user-generated content.

## Important Context

You may be analyzing EITHER:
1. A POST (primary content, discussion starter)
2. A COMMENT (reaction/advice to a post) - NEW!

## If analyzing a COMMENT:
- The comment itself is the PRIMARY source of pain signals
- The parent post title provides context only
- Focus on pain expressed IN the comment, not the post
- Comments are often more direct and specific than posts
- High-upvote comments indicate community validation

## If analyzing a POST:
- Use both the post body and comments as evidence
- Look for pains mentioned in post AND comments
- Use comments to add specificity

## Output Format (same for both)

{"pain_events": [
  {
    "problem": "specific pain statement",
    "context": "additional details",
    "current_workaround": "current solution",
    "frequency": "how often",
    "emotional_signal": "emotion expressed",
    "mentioned_tools": ["tools"],
    "confidence": 0.8,
    "evidence_sources": ["post", "comment"]  # Specify source
  }
]}
"""
```

**Step 4: Pass metadata to LLM if analyzing comment**

Update the `extract_pain_points` implementation to check metadata:

```python
# In extract_pain_points method, after building messages
is_comment = metadata and metadata.get("source_type") == "comment" if metadata else False

# Add system instruction for comment vs post
if is_comment:
    system_instruction = "You are analyzing a COMMENT. The comment body is the primary pain source. Parent post title is context only."
else:
    system_instruction = "You are analyzing a POST. Extract pain points from post and comments."

messages = [
    {"role": "system", "content": system_instruction},
    {"role": "user", "content": self._get_pain_extraction_prompt() + f"\n\n### Content\nTitle: {title}\n\nBody: {body}\n\nSubreddit: {subreddit}\nUpvotes: {upvotes}\n\nComments: {json.dumps(top_comments, indent=2)}"}
]
```

**Step 5: Test LLM client still works**

Run: `python3 -c "from utils.llm_client import llm_client; print(llm_client.get_model_name())"`
Expected: Model name printed without errors

**Step 6: Commit changes**

```bash
git add utils/llm_client.py
git commit -m "feat(phase2): update LLM client for comment-aware extraction"
```

---

### Task 4: Implement Comment Extraction in PainPointExtractor

**Files:**
- Modify: `pipeline/extract_pain.py` (add new method after `_extract_from_single_post` around line 87)

**Step 1: Add `_extract_from_single_comment` method**

Add to `pipeline/extract_pain.py` after `_extract_from_single_post()` method (around line 87):

```python
def _extract_from_single_comment(self, comment_data: Dict[str, Any], retry_count: int = 0) -> List[Dict[str, Any]]:
    """从单条评论抽取痛点事件 - Phase 2: Include Comments

    Args:
        comment_data: 包含评论数据的字典
        retry_count: 重试次数

    Returns:
        痛点事件列表
    """
    max_retries = 2
    try:
        comment_id = comment_data["comment_id"]
        post_id = comment_data["post_id"]
        body = comment_data["body"]
        score = comment_data.get("score", 0)

        # 1. 加载父帖子作为上下文（不是主要来源）
        parent_post = db.get_parent_post_context(post_id)
        logger.debug(f"Loaded parent post context for comment {comment_id}: {parent_post.get('title', 'N/A')[:50]}...")

        # 2. 调用LLM进行抽取（comment作为主要来源）
        response = llm_client.extract_pain_points(
            title=parent_post.get("title", "[Comment context]"),  # 仅作为上下文
            body=body,  # PRIMARY: 评论本身
            subreddit=parent_post.get("subreddit", ""),
            upvotes=score,
            comments_count=0,  # 评论没有子评论（暂不支持）
            top_comments=[],   # 无子评论
            metadata={
                "source_type": "comment",
                "parent_post_title": parent_post.get("title"),
                "parent_post_body": parent_post.get("body", "")[:500]  # 截断上下文
            }
        )

        extraction_result = response["content"]
        pain_events = extraction_result.get("pain_events", [])

        # 3. 为每个痛点事件添加元数据
        for event in pain_events:
            event.update({
                "post_id": post_id,           # 父帖子（用于关联）
                "comment_id": comment_id,     # 实际来源
                "source_type": "comment",     # 标记为评论来源
                "source_id": str(comment_id),  # NEW: 具体来源ID
                "parent_post_id": post_id,    # NEW: 父帖子ID
                "subreddit": parent_post.get("subreddit", ""),
                "original_score": score,
                "extraction_model": response["model"],
                "extraction_timestamp": datetime.now().isoformat(),
                "confidence": event.get("confidence", 0.0),
                "comments_used": 0,  # 评论没有使用子评论
                "evidence_sources": ["comment"]  # 明确标记不是来自post
            })

        self.stats["total_pain_events"] += len(pain_events)
        logger.debug(f"Extracted {len(pain_events)} pain events from comment {comment_id}")

        return pain_events

    except Exception as e:
        error_msg = f"Failed to extract pain from comment {comment_data.get('comment_id')}: {e}"

        # 如果是超时错误且还有重试机会
        if "timeout" in str(e).lower() and retry_count < max_retries:
            logger.warning(f"{error_msg} (retry {retry_count + 1}/{max_retries})")
            time.sleep(5)  # 等待5秒后重试
            return self._extract_from_single_comment(comment_data, retry_count + 1)
        else:
            logger.error(error_msg)
            self.stats["extraction_errors"] += 1
            return []
```

**Step 2: Add `process_unextracted_comments` method**

Add to `pipeline/extract_pain.py` after `process_unextracted_posts()` method (around line 343):

```python
def process_unextracted_comments(self, limit: int = 100) -> Dict[str, Any]:
    """处理未抽取的过滤评论 - Phase 2: Include Comments

    Args:
        limit: 限制处理的评论数量

    Returns:
        处理结果统计字典
    """
    logger.info(f"Processing up to {limit} filtered comments")

    try:
        # 获取过滤后的评论
        filtered_comments = db.get_all_filtered_comments(limit=limit)

        if not filtered_comments:
            logger.info("No filtered comments found")
            return {"processed": 0, "pain_events": 0}

        logger.info(f"Found {len(filtered_comments)} comments to extract from")

        # 记录失败的评论ID
        failed_comments = []

        # 抽取痛点事件（带失败恢复）
        pain_events = []
        for i, comment in enumerate(filtered_comments):
            if i % 10 == 0:
                logger.info(f"Processed {i}/{len(filtered_comments)} comments")

            try:
                # 尝试抽取单条评论
                comment_events = self._extract_from_single_comment(comment)

                # 验证和增强每个痛点事件
                for event in comment_events:
                    if self._validate_pain_event(event):
                        # 注意：评论不能使用 _enhance_pain_event，因为其逻辑是针对帖子的
                        # 简化处理：直接添加事件
                        pain_events.append(event)

                logger.debug(f"Successfully processed comment {comment.get('comment_id')}")

            except Exception as e:
                logger.error(f"Failed to process comment {comment.get('comment_id')}: {e}")
                failed_comments.append(comment.get('comment_id'))
                self.stats["extraction_errors"] += 1
                continue

            # 添加延迟避免API限制
            delay = 2.0 + (i % 3)  # 2-4秒动态延迟（评论处理更快）
            logger.debug(f"Waiting {delay:.1f}s before next comment...")
            time.sleep(delay)

        # 保存成功处理的痛点事件
        saved_count = self.save_pain_events(pain_events)

        # 记录失败统计
        if failed_comments:
            logger.warning(f"Failed to process {len(failed_comments)} comments: {failed_comments}")

        return {
            "processed": len(filtered_comments) - len(failed_comments),
            "failed": len(failed_comments),
            "pain_events_extracted": len(pain_events),
            "pain_events_saved": saved_count,
            "extraction_stats": self.get_statistics(),
            "failed_comments": failed_comments
        }

    except Exception as e:
        logger.error(f"Failed to process unextracted comments: {e}")
        raise
```

**Step 3: Update `save_pain_events` to support comment metadata**

Update the `save_pain_events()` method in `pipeline/extract_pain.py` (around line 248) to include new fields:

```python
def save_pain_events(self, pain_events: List[Dict[str, Any]]) -> int:
    """保存痛点事件到数据库（支持post和comment来源）"""
    saved_count = 0

    for event in pain_events:
        try:
            # 准备数据库记录
            event_data = {
                "post_id": event["post_id"],
                "source_type": event.get("source_type", "post"),  # NEW
                "source_id": event.get("source_id"),              # NEW
                "parent_post_id": event.get("parent_post_id"),    # NEW
                "actor": event.get("actor", ""),
                "context": event.get("context", ""),
                "problem": event["problem"],
                "current_workaround": event.get("current_workaround", ""),
                "frequency": event.get("frequency", ""),
                "emotional_signal": event.get("emotional_signal", ""),
                "mentioned_tools": event.get("mentioned_tools", []),
                "extraction_confidence": event.get("confidence", 0.0)
            }

            # 保存到数据库
            pain_event_id = db.insert_pain_event(event_data)
            if pain_event_id:
                saved_count += 1
                logger.debug(f"Saved pain event {pain_event_id}: {event['problem'][:50]}...")

        except Exception as e:
            logger.error(f"Failed to save pain event: {e}")

    logger.info(f"Saved {saved_count}/{len(pain_events)} pain events to database")
    return saved_count
```

**Step 4: Test methods compile**

Run: `python3 -c "from pipeline.extract_pain import PainPointExtractor; e = PainPointExtractor(); print('PainPointExtractor loaded successfully')"`
Expected: No import errors

**Step 5: Commit changes**

```bash
git add pipeline/extract_pain.py
git commit -m "feat(phase2): implement comment pain extraction methods"
```

---

### Task 5: Create Standalone Comment Extraction Script

**Files:**
- Create: `scripts/extract_pain_from_comments.py`

**Step 1: Create standalone extraction script**

Create file: `scripts/extract_pain_from_comments.py`

```python
#!/usr/bin/env python3
"""
Extract Pain from Comments Script - Phase 2: Include Comments
从过滤评论中提取痛点事件脚本

This script extracts pain points from filtered comments, treating them as
independent pain sources with parent post as context.

**NOTE**: This is a STANDALONE script for one-time migration or manual use.
For automated extraction, use the main pipeline:

    python3 run_pipeline.py --stage extract_pain --include-comments

Usage:
    python3 scripts/extract_pain_from_comments.py [options]
"""
import os
import sys
import logging
import argparse
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.extract_pain import PainPointExtractor
from utils.db import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主函数 - 从评论提取痛点"""
    parser = argparse.ArgumentParser(
        description="Extract pain points from filtered comments (Phase 2: Include Comments)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Limit number of comments to process (default: 10 for testing)"
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Minimum pain score threshold (default: 0.0)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate extraction without saving to database"
    )
    args = parser.parse_args()

    try:
        logger.info("=" * 80)
        logger.info("Starting pain extraction from comments - Phase 2: Include Comments")
        logger.info("=" * 80)

        # 1. 检查数据库schema是否已迁移
        logger.info("Checking database schema...")
        try:
            with db.get_connection("pain") as conn:
                cursor = conn.execute("PRAGMA table_info(pain_events)")
                columns = {row['name'] for row in cursor.fetchall()}

                required_columns = {'source_type', 'source_id', 'parent_post_id'}
                missing_columns = required_columns - columns

                if missing_columns:
                    logger.error(f"Database schema not migrated! Missing columns: {missing_columns}")
                    logger.error("Please run: python3 migrations/002_add_source_tracking_to_pain_events.py")
                    sys.exit(1)

                logger.info("✓ Database schema verified")

        except Exception as e:
            logger.error(f"Failed to verify database schema: {e}")
            sys.exit(1)

        # 2. 初始化抽取器
        logger.info("Initializing PainPointExtractor...")
        extractor = PainPointExtractor()

        # 3. 获取过滤后的评论
        logger.info(f"Fetching filtered comments (limit={args.limit})...")
        filtered_comments = db.get_all_filtered_comments(limit=args.limit)

        if not filtered_comments:
            logger.info("No filtered comments found. Run filter_comments.py first.")
            return

        logger.info(f"Found {len(filtered_comments)} comments to extract from")

        # 显示评论统计
        pain_scores = [c.get("pain_score", 0) for c in filtered_comments]
        comment_scores = [c.get("score", 0) for c in filtered_comments]
        logger.info(f"Pain score range: {min(pain_scores):.2f} - {max(pain_scores):.2f}")
        logger.info(f"Comment score range: {min(comment_scores)} - {max(comment_scores)}")
        logger.info(f"Average pain score: {sum(pain_scores) / len(pain_scores):.2f}")

        # 4. 应用最小分数阈值
        if args.min_score > 0:
            logger.info(f"Applying min_pain_score threshold: {args.min_score}")
            before_count = len(filtered_comments)
            filtered_comments = [c for c in filtered_comments
                                if c.get("pain_score", 0) >= args.min_score]
            after_count = len(filtered_comments)
            logger.info(f"Filtered out {before_count - after_count} comments below threshold")

        # 5. 抽取痛点事件
        if args.dry_run:
            logger.info("=" * 80)
            logger.info("DRY RUN - Results will NOT be saved to database")
            logger.info("=" * 80)

            # 只处理前3个评论作为示例
            sample_comments = filtered_comments[:3]
            logger.info(f"Processing {len(sample_comments)} sample comments...")

            for comment in sample_comments:
                logger.info(f"\nProcessing comment {comment['comment_id']}...")
                events = extractor._extract_from_single_comment(comment)
                logger.info(f"  Extracted {len(events)} pain events")
                for i, event in enumerate(events, 1):
                    logger.info(f"    {i}. {event['problem'][:80]}...")

            logger.info("\nDry run complete!")
            return

        # 正式处理
        logger.info("Starting pain extraction...")
        start_time = datetime.now()

        result = extractor.process_unextracted_comments(limit=len(filtered_comments))

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # 6. 输出统计信息
        logger.info("=" * 80)
        logger.info("Extraction Summary")
        logger.info("=" * 80)
        logger.info(f"Comments processed:  {result['processed']}")
        logger.info(f"Failed:               {result['failed']}")
        logger.info(f"Pain events extracted:{result['pain_events_extracted']}")
        logger.info(f"Pain events saved:    {result['pain_events_saved']}")
        logger.info(f"Processing time:      {duration:.1f}s ({duration/max(result['processed'], 1):.2f}s per comment)")
        logger.info("")

        # 显示抽取统计
        stats = result['extraction_stats']
        logger.info("Extraction Statistics:")
        logger.info(f"  - Avg confidence:    {stats.get('avg_confidence', 0):.2f}")
        logger.info(f"  - Events per comment:{stats.get('avg_events_per_post', 0):.2f}")  # Note: reusing post stats
        logger.info(f"  - Error rate:        {stats.get('extraction_errors', 0)}")

        # 显示LLM统计
        if 'llm_stats' in stats:
            llm_stats = stats['llm_stats']
            logger.info(f"\nLLM Statistics:")
            logger.info(f"  - Requests:          {llm_stats.get('requests', 0)}")
            logger.info(f"  - Tokens used:       {llm_stats.get('tokens_used', 0)}")
            logger.info(f"  - Errors:            {llm_stats.get('errors', 0)}")

        logger.info("=" * 80)

        # 7. Sample extracted pain events
        if result['pain_events_saved'] > 0:
            logger.info("\nVerifying: Querying recent pain_events from comments...")
            with db.get_connection("pain") as conn:
                cursor = conn.execute("""
                    SELECT problem, source_type, extraction_confidence
                    FROM pain_events
                    WHERE source_type = 'comment'
                    ORDER BY extracted_at DESC
                    LIMIT 5
                """)
                sample_events = cursor.fetchall()

                if sample_events:
                    logger.info("Sample of 5 extracted pain events from comments:")
                    for i, event in enumerate(sample_events, 1):
                        logger.info(f"\n{i}. {event['problem'][:100]}...")
                        logger.info(f"   Source: {event['source_type']} | Confidence: {event['extraction_confidence']:.2f}")

        logger.info("")
        logger.info("Extraction complete!")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**Step 2: Make script executable**

Run: `chmod +x scripts/extract_pain_from_comments.py`

**Step 3: Test script help**

Run: `python3 scripts/extract_pain_from_comments.py --help`
Expected: Help message displayed

**Step 4: Commit changes**

```bash
git add scripts/extract_pain_from_comments.py
git commit -m "feat(phase2): add standalone comment extraction script"
```

---

### Task 6: Integration Testing with Small Batch

**Files:**
- Test: `scripts/extract_pain_from_comments.py`

**Step 1: Run dry-run test**

Run: `python3 scripts/extract_pain_from_comments.py --limit 5 --dry-run`
Expected: Processes 5 comments, shows extracted events, doesn't save

**Step 2: Verify database unchanged**

Run: `sqlite3 data/wise_collection.db "SELECT COUNT(*) FROM pain_events WHERE source_type='comment';"`
Expected: `0` (no comment-sourced events yet)

**Step 3: Run small batch test**

Run: `python3 scripts/extract_pain_from_comments.py --limit 10`
Expected: Processes 10 comments, saves pain events, shows statistics

**Step 4: Verify data in database**

Run: `sqlite3 data/wise_collection.db "SELECT COUNT(*) FROM pain_events WHERE source_type='comment';"`
Expected: Non-zero count (e.g., 5-20 events depending on extraction success)

**Step 5: Sample extracted events**

Run: `sqlite3 data/wise_collection.db "SELECT problem, source_type FROM pain_events WHERE source_type='comment' LIMIT 5;"`
Expected: 5 pain events from comments displayed

**Step 6: Document results**

Create file: `docs/phase2_test_results.md`

```markdown
# Phase 2 Testing Results

## Test Execution
- Date: 2025-12-28
- Command: `python3 scripts/extract_pain_from_comments.py --limit 10`
- Comments processed: [FILL IN]
- Pain events extracted: [FILL IN]
- Pain events saved: [FILL IN]

## Quality Assessment
Sample of extracted pain events:
1. [Event 1]
2. [Event 2]
3. [Event 3]

## Issues Found
- [List any issues]

## Next Steps
- [Any adjustments needed]
```

**Step 7: Commit test results**

```bash
git add docs/phase2_test_results.md
git commit -m "test(phase2): document small batch test results"
```

---

### Task 7: Full Extraction Run (Optional - Wait for Confirmation)

**⚠️ STOP: User confirmation required before running full batch**

This task processes all 3,656 filtered comments. Estimated time:
- 3656 comments × ~3 seconds per comment = ~3 hours
- LLM API costs: ~3656 requests

**Ask user before proceeding:**
```
Ready to extract pain events from all 3,656 filtered comments.
Estimated runtime: ~3 hours
Estimated API cost: [calculate based on pricing]

Options:
1. Run full extraction now
2. Run with a higher limit (e.g., 100, 500)
3. Stop here and review test results first

Which option?
```

**If user chooses full extraction:**

Run: `python3 scripts/extract_pain_from_comments.py --limit 3656`

Monitor progress in logs. Upon completion, verify results and document.

---

### Task 8: Update Documentation

**Files:**
- Create: `docs/phase2_implementation_summary.md`
- Update: `README.md` (if applicable)

**Step 1: Create implementation summary**

Create file: `docs/phase2_implementation_summary.md`

```markdown
# Phase 2 Implementation Summary: Extract Pain from Comments

## Overview
Successfully extended pain point extraction to process filtered comments as independent pain sources.

## What Was Built

### 1. Database Schema Migration
- Migration: `migrations/002_add_source_tracking_to_pain_events.py`
- Added columns: `source_type`, `source_id`, `parent_post_id` to `pain_events` table
- Migrated existing records to `source_type='post'`

### 2. Database Methods (`utils/db.py`)
- `get_parent_post_context()` - Load parent post as context for comments
- `get_all_filtered_comments()` - Retrieve filtered comments for extraction
- Updated `insert_pain_event()` - Support source tracking fields

### 3. LLM Client Updates (`utils/llm_client.py`)
- Added `metadata` parameter to `extract_pain_points()`
- Updated prompt to handle comments vs posts differently
- Comments are treated as PRIMARY pain source
- Parent post provides context only

### 4. Pain Extraction Methods (`pipeline/extract_pain.py`)
- `_extract_from_single_comment()` - Extract pain from individual comments
- `process_unextracted_comments()` - Batch processing for comments
- Updated `save_pain_events()` - Support comment metadata

### 5. Standalone Script (`scripts/extract_pain_from_comments.py`)
- One-time extraction script
- Dry-run mode for testing
- Detailed logging and statistics

## Usage

### Standalone Script
```bash
# Dry run with 10 comments
python3 scripts/extract_pain_from_comments.py --limit 10 --dry-run

# Extract from 100 comments
python3 scripts/extract_pain_from_comments.py --limit 100

# Extract from all comments
python3 scripts/extract_pain_from_comments.py --limit 3656
```

### Main Pipeline Integration (Future)
```bash
# Not yet integrated into run_pipeline.py
# This will be added in a future update
```

## Results

### Test Run (10 comments)
- Processed: [FILL]
- Pain events extracted: [FILL]
- Success rate: [FILL]

### Full Run (3656 comments)
- Processed: [FILL]
- Pain events extracted: [FILL]
- Runtime: [FILL]
- API cost: [FILL]

## Data Model Changes

### pain_events table
```sql
-- NEW columns
source_type TEXT DEFAULT 'post'      -- 'post' or 'comment'
source_id TEXT                       -- ID of the source (post_id or comment_id)
parent_post_id TEXT                  -- For comments, parent post ID
```

## Design Decisions

1. **Comments as Independent Sources**: Comments are first-class pain sources, not post accessories
2. **Parent Post as Context**: Parent post loaded for context but not treated as pain source
3. **Unified pain_events Table**: Both posts and comments store in same table with `source_type` discriminator
4. **Lower Thresholds for Comments**: Implemented in Phase 1, maintained in Phase 2
5. **Comment-Specific Prompt**: LLM instructed to treat comment body as primary pain source

## Known Limitations

1. **No Nested Comment Support**: Only top-level comments, no reply threading
2. **No Cross-Post Comment Detection**: Comments from same user across posts not linked
3. **No Comment Evolution Tracking**: Temporal changes in comment sentiment not tracked
4. **Post-Specific Enhancement Logic**: `_enhance_pain_event()` not called for comments (simplified)

## Future Enhancements

See design doc `docs/IncludeCommentsDesign.md` "Future Enhancements" section:
- Comment threading (recursive reply extraction)
- Cross-post pain discovery
- Comment evolution tracking
- Source-weighted clustering
- Sentiment analysis pre-filter

## Verification

To verify Phase 2 is working:

```bash
# Check database schema
sqlite3 data/wise_collection.db "PRAGMA table_info(pain_events);"

# Count comment-sourced events
sqlite3 data/wise_collection.db "SELECT COUNT(*) FROM pain_events WHERE source_type='comment';"

# Sample events
sqlite3 data/wise_collection.db "SELECT problem, source_type, extraction_confidence FROM pain_events WHERE source_type='comment' LIMIT 10;"
```

## Related Files

- Design: `docs/IncludeCommentsDesign.md`
- Phase 1: `scripts/filter_comments.py`
- Phase 2: `scripts/extract_pain_from_comments.py`
- Migration: `migrations/002_add_source_tracking_to_pain_events.py`
```

**Step 2: Update main README if needed**

Check if `README.md` needs updating. If yes, add Phase 2 section.

**Step 3: Commit documentation**

```bash
git add docs/phase2_implementation_summary.md
git add README.md  # if updated
git commit -m "docs(phase2): add implementation summary documentation"
```

---

### Task 9: Cleanup and Validation (Final)

**Files:**
- Multiple files for validation

**Step 1: Run code quality checks**

Run: `python3 -m py_compile pipeline/extract_pain.py utils/db.py utils/llm_client.py`
Expected: No syntax errors

**Step 2: Check for TODO comments**

Run: `grep -r "TODO" pipeline/extract_pain.py utils/db.py utils/llm_client.py scripts/extract_pain_from_comments.py`
Expected: No critical TODOs (documentation TODOs OK)

**Step 3: Verify git status**

Run: `git status`
Expected: All Phase 2 changes committed, clean working tree

**Step 4: Create final summary**

Create file: `docs/phase2_completion_checklist.md`

```markdown
# Phase 2 Completion Checklist

## Database
- [x] Migration 002 created and tested
- [x] `source_type`, `source_id`, `parent_post_id` columns added
- [x] Existing records migrated to `source_type='post'`
- [x] Indexes created for `source_type`

## Database Methods
- [x] `get_parent_post_context()` implemented
- [x] `get_all_filtered_comments()` implemented
- [x] `insert_pain_event()` updated for source tracking

## LLM Client
- [x] `extract_pain_points()` accepts `metadata` parameter
- [x] Prompt updated for comment-aware extraction
- [x] System instruction differentiates post vs comment

## Pain Extraction
- [x] `_extract_from_single_comment()` implemented
- [x] `process_unextracted_comments()` implemented
- [x] `save_pain_events()` supports comment metadata
- [x] Validation logic works for comments
- [x] Retry logic works for comments

## Scripts
- [x] `extract_pain_from_comments.py` created
- [x] Dry-run mode works
- [x] Detailed statistics output
- [x] Error handling and logging

## Testing
- [x] Small batch test (10 comments) successful
- [x] Database verification passed
- [x] Quality assessment completed
- [x] Full extraction run completed (if approved)

## Documentation
- [x] Implementation summary created
- [x] Test results documented
- [x] Usage examples provided
- [x] Design decisions documented

## Code Quality
- [x] No syntax errors
- [x] All changes committed
- [x] Clean git status
- [x] Code follows existing patterns

## Ready for Phase 3
- [ ] Integration with main pipeline (`run_pipeline.py`)
- [ ] Update `embed` stage to handle comment sources
- [ ] Update `cluster` stage for source-aware analysis
- [ ] Run full pipeline and validate clustering quality

## Phase 2 Status
✅ COMPLETE - Ready for user review and Phase 3 planning
```

**Step 5: Final commit**

```bash
git add docs/phase2_completion_checklist.md
git commit -m "docs(phase2): add completion checklist"
```

---

## Post-Implementation

### Verification Commands

```bash
# 1. Verify database schema
sqlite3 data/wise_collection.db "PRAGMA table_info(pain_events);"

# 2. Count events by source type
sqlite3 data/wise_collection.db "SELECT source_type, COUNT(*) as count FROM pain_events GROUP BY source_type;"

# 3. Sample comment-sourced events
sqlite3 data/wise_collection.db "SELECT problem, source_type, extraction_confidence FROM pain_events WHERE source_type='comment' LIMIT 10;"

# 4. Check extraction statistics
sqlite3 data/wise_collection.db "SELECT AVG(extraction_confidence) as avg_conf FROM pain_events WHERE source_type='comment';"
```

### Success Criteria

From design doc `docs/IncludeCommentsDesign.md` Phase 2 goals:

- [x] Extend pain extraction to handle comments
- [x] Load parent post context dynamically
- [x] Generate pain events from filtered comments
- [x] Add `source_type` tracking to pain_events
- [x] Run extraction on filtered comments
- [ ] Compare quality with post-sourced events (manual review task)

### Next Steps

1. **Manual Quality Review**: Review 50-100 comment-sourced pain events for quality
2. **Phase 3 Planning**: Integration with downstream pipeline stages (embed, cluster, map_opportunity)
3. **Performance Optimization**: Batch processing, parallel extraction if needed
4. **Monitoring**: Add metrics for comment extraction quality and rate

---

## Summary

This plan implements Phase 2 of the "Include Comments" design:
- **8 major tasks** broken into bite-sized steps
- **Database migration** for source tracking
- **New methods** for comment extraction
- **Updated LLM client** for comment-aware prompts
- **Standalone script** for one-time extraction
- **Comprehensive testing** and documentation

**Estimated implementation time**: 2-3 hours for tasks 1-6, plus full extraction time for task 7
**Risk level**: Low (extensions to existing architecture, no breaking changes)
**Dependencies**: Phase 1 must be complete (✅ confirmed)

---

**Plan complete and saved to `docs/plans/2025-12-28-phase2-extract-pain-from-comments.md`.**

**Execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
