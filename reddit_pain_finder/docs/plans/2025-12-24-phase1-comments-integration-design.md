# Phase 1: Comments Data Integration - Design Document

**Date:** 2025-12-24
**Status:** Approved
**Author:** Claude (assisted by user review)

## Overview

将 Reddit 和 Hacker News 的评论数据从 `posts.raw_data` JSON 字段中提取到独立的 `comments` 表中，为后续的痛点分析建立数据基础。此阶段不改变任何分析逻辑，只专注于构建可靠的数据源。

## Database Schema Design

### New Table: `comments`

```sql
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,              -- FK to posts.id
    source TEXT NOT NULL,               -- 'reddit' or 'hackernews'
    source_comment_id TEXT NOT NULL,    -- Original platform comment ID
    author TEXT,                        -- Comment author
    body TEXT NOT NULL,                 -- Comment content
    score INTEGER DEFAULT 0,            -- Comment score/upvotes
    created_utc REAL,                   -- Unix timestamp
    created_at TIMESTAMP,               -- ISO 8601 format
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    UNIQUE(source, source_comment_id)
);
```

### Indexes

```sql
-- Primary lookup index
CREATE INDEX idx_comments_post_id ON comments(post_id);

-- Compound index for sorted queries (optimized for "get top comments for a post")
CREATE INDEX idx_comments_post_id_score ON comments(post_id, score DESC);

-- Source-based filtering
CREATE INDEX idx_comments_source ON comments(source);
```

### Key Design Decisions

1. **No Nested Comments** - Only store top-level comments, not replies. This aligns with Phase 1 goal of establishing data foundation.
2. **Backfill Support** - Design supports extracting comments from existing `posts.raw_data` JSON field.
3. **Cascade Delete** - When a post is deleted, associated comments are automatically cleaned up.
4. **Composite Unique Index** - Prevents duplicate comments from the same platform.

## Implementation Changes

### 1. Database Layer (`utils/db.py`)

**New method: `insert_comments()`**

```python
def insert_comments(self, post_id: str, comments: List[Dict[str, Any]], source: str) -> int:
    """批量插入评论数据"""
    try:
        with self.get_connection("raw") as conn:
            inserted_count = 0
            for comment in comments:
                comment_id = comment.get("id")

                # 异常检测：记录缺失ID的评论
                if comment_id is None:
                    logger.warning(
                        f"Comment for post {post_id} from {source} is missing a source ID. "
                        f"Author: {comment.get('author', 'unknown')}. "
                        f"Generating fallback ID."
                    )
                    # Fallback ID
                    comment_id = f"{source}_{comment.get('author', 'unknown')}_{hash(comment.get('body', ''))}"

                conn.execute("""
                    INSERT OR IGNORE INTO comments
                    (post_id, source, source_comment_id, author, body, score, created_utc, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    post_id,
                    source,
                    comment_id,
                    comment.get("author", ""),
                    comment.get("body", ""),
                    comment.get("score", 0),
                    comment.get("created_utc"),
                    comment.get("created_at")
                ))
                inserted_count += conn.rowcount
            conn.commit()
            return inserted_count
    except Exception as e:
        logger.error(f"Failed to insert comments for post {post_id}: {e}")
        return 0
```

**Modify `_init_unified_database()`**
- Add `comments` table creation
- Add index creation

### 2. Reddit Fetcher (`pipeline/fetch.py`)

**Modify `_extract_post_data()`**
- Ensure comments include `id` field
- Include `created_utc` and `created_at` for each comment

**Modify `_process_submission()`**
- After `db.insert_raw_post()`, call `db.insert_comments()`

### 3. HackerNews Fetcher (`pipeline/hn_fetch.py`)

**Modify `_extract_story_data()`**
- Ensure comment objects include `id` field from HN API
- Include `created_utc` from `item.get("time")`

**Modify `fetch_from_endpoint()`**
- After `db.insert_raw_post()`, call `db.insert_comments()`

## Backfill Migration

### Script: `scripts/backfill_comments.py`

**Purpose:** Extract comments from existing `posts.raw_data` and insert into `comments` table.

**Key Features:**
- Batch processing (configurable batch size)
- Dry-run mode for validation
- Error handling per-post
- Progress logging
- Statistics reporting

**Usage:**
```bash
# Dry-run to analyze
python scripts/backfill_comments.py --dry-run

# Execute migration
python scripts/backfill_comments.py --batch-size 100
```

## Error Handling Strategy

### Fetch Phase
- Single comment failure doesn't abort other comments
- Log error, continue processing
- Return count of successfully inserted comments

### Backfill Phase
- Single post parse failure skips that post only
- Statistics track error count
- Dry-run mode validates data before actual migration

### Database Layer
- `INSERT OR IGNORE` prevents duplicate-key aborts
- Transactions ensure atomicity per-batch
- Foreign key `ON DELETE CASCADE` for cleanup

## Acceptance Criteria

### SQL Verification Queries

```sql
-- 1. Confirm comments table has data
SELECT COUNT(*) FROM comments;
-- Expected: > 0

-- 2. Confirm comments linked to multiple posts
SELECT COUNT(DISTINCT post_id) FROM comments;
-- Expected: > 1

-- 3. Confirm both sources have comments
SELECT source, COUNT(*) FROM comments GROUP BY source;
-- Expected: Both 'reddit' and 'hackernews' present

-- 4. Verify join query works
SELECT p.title, c.body, c.author
FROM posts p
JOIN comments c ON p.id = c.post_id
WHERE p.source = 'reddit'
LIMIT 5;
-- Expected: Returns 5 Reddit posts with their comments

-- 5. Verify compound index usage
EXPLAIN QUERY PLAN
SELECT * FROM comments
WHERE post_id = 'reddit_abc123'
ORDER BY score DESC
LIMIT 20;
-- Expected: Shows `SEARCH comments USING INDEX idx_comments_post_id_score`
```

### Performance Benchmarks
- Backfill 1000 posts (~5000-10000 comments): < 5 minutes
- New fetch comment insertion: < 100ms per post

## Testing Strategy

1. **Unit Tests**
   - Test `insert_comments()` with edge cases
   - Test missing ID fallback logic
   - Test duplicate prevention

2. **Integration Tests**
   - Fetch small batch of new posts
   - Verify comments stored correctly
   - Verify foreign key constraints

3. **Regression Tests**
   - Run existing pipeline to ensure no breaking changes
   - Verify all existing functionality intact

## Implementation Checklist

- [x] Add `comments` table to `utils/db.py::_init_unified_database()`
- [x] Create indexes for `comments` table
- [x] Implement `insert_comments()` method in `utils/db.py`
- [x] Update `pipeline/fetch.py::_process_submission()` to call `insert_comments()`
- [x] Update `pipeline/hn_fetch.py::fetch_from_endpoint()` to call `insert_comments()`
- [x] Create `scripts/backfill_comments.py`
- [x] Run backfill in dry-run mode
- [x] Execute backfill migration
- [x] Run verification SQL queries
- [x] Update documentation

## Phase Boundaries

**Phase 1 (Current):**
- Establish data foundation
- Create `comments` table
- Backfill existing data
- No changes to analysis logic

**Phase 2 (Future):**
- Analyze comments for pain signals
- Extract pain points from discussions
- Update pain detection algorithms

**Phase 3 (Future):**
- Use comment sentiment analysis
- Identify user desires/aspirations
- Enhance opportunity scoring
