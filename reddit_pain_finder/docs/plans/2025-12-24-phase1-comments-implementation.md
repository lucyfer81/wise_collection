# Phase 1: Comments Data Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Reddit 和 Hacker News 的评论数据从 `posts.raw_data` JSON 字段中提取到独立的 `comments` 表中，建立可靠的数据源。

**Architecture:**
1. 在 `utils/db.py` 中添加 `comments` 表创建逻辑和 `insert_comments()` 方法
2. 更新 `pipeline/fetch.py` 和 `pipeline/hn_fetch.py` 在抓取后调用 `insert_comments()`
3. 创建回填脚本从现有数据中提取评论

**Tech Stack:** Python 3.x, SQLite, PRAW (Reddit), requests (HN API)

---

## Task 1: 添加 comments 表到数据库初始化

**Files:**
- Modify: `utils/db.py` (在 `_init_unified_database()` 方法中)

**Step 1: 在 `_init_unified_database()` 方法中添加 comments 表创建**

找到 `_init_unified_database()` 方法，在创建 `aligned_problems` 表之后、创建索引之前，添加以下代码：

```python
# 创建评论表
conn.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id TEXT NOT NULL,
        source TEXT NOT NULL,
        source_comment_id TEXT NOT NULL,
        author TEXT,
        body TEXT NOT NULL,
        score INTEGER DEFAULT 0,
        created_utc REAL,
        created_at TIMESTAMP,
        collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
        UNIQUE(source, source_comment_id)
    )
""")
```

**Step 2: 在索引创建区域添加 comments 表索引**

在 `_init_unified_database()` 方法的索引创建区域（约第 226 行附近），添加：

```python
# comments表索引
conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_id_score ON comments(post_id, score DESC)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_source ON comments(source)")
```

**Step 3: 测试数据库初始化**

运行测试脚本验证表创建成功：

```bash
python3 -c "
from utils.db import db
with db.get_connection('raw') as conn:
    cursor = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='comments'\")
    result = cursor.fetchone()
    if result:
        print('SUCCESS: comments table exists')
    else:
        print('ERROR: comments table not found')
        exit(1)
"
```

预期输出: `SUCCESS: comments table exists`

**Step 4: 提交**

```bash
git add utils/db.py
git commit -m "feat: add comments table schema and indexes"
```

---

## Task 2: 实现 insert_comments() 方法

**Files:**
- Modify: `utils/db.py` (添加新方法)

**Step 1: 在 WiseCollectionDB 类中添加 insert_comments() 方法**

在 `utils/db.py` 中，找到 `WiseCollectionDB` 类，在 `insert_raw_post()` 方法之后添加以下方法：

```python
def insert_comments(self, post_id: str, comments: List[Dict[str, Any]], source: str) -> int:
    """批量插入评论数据

    Args:
        post_id: 帖子ID
        comments: 评论列表，每个评论是包含 id, author, body, score, created_utc, created_at 的字典
        source: 数据源 ('reddit' 或 'hackernews')

    Returns:
        成功插入的评论数量
    """
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

**Step 2: 测试 insert_comments() 方法**

创建测试脚本：

```bash
cat > /tmp/test_insert_comments.py << 'EOF'
from utils.db import db

# 测试数据
test_post_id = "test_post_123"
test_comments = [
    {
        "id": "comment_1",
        "author": "test_user",
        "body": "This is a test comment",
        "score": 10,
        "created_utc": 1735000000.0,
        "created_at": "2025-01-23T12:00:00Z"
    },
    {
        "id": "comment_2",
        "author": "another_user",
        "body": "Another test comment",
        "score": 5,
        "created_utc": 1735000100.0,
        "created_at": "2025-01-23T12:01:40Z"
    }
]

# 插入评论
count = db.insert_comments(test_post_id, test_comments, "reddit")
print(f"Inserted {count} comments")

# 验证插入
with db.get_connection("raw") as conn:
    cursor = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", (test_post_id,))
    result = cursor.fetchone()
    print(f"Comments in database: {result[0]}")

    if result[0] == 2:
        print("SUCCESS: All comments inserted correctly")
    else:
        print("ERROR: Comment count mismatch")
        exit(1)

# 清理测试数据
with db.get_connection("raw") as conn:
    conn.execute("DELETE FROM comments WHERE post_id = ?", (test_post_id,))
    conn.commit()
    print("Cleaned up test data")
EOF

python3 /tmp/test_insert_comments.py
```

预期输出:
```
Inserted 2 comments
Comments in database: 2
SUCCESS: All comments inserted correctly
Cleaned up test data
```

**Step 3: 提交**

```bash
git add utils/db.py
git commit -m "feat: add insert_comments() method for batch comment insertion"
```

---

## Task 3: 更新 Reddit 抓取器以插入评论

**Files:**
- Modify: `pipeline/fetch.py` (修改 `_extract_post_data()` 和 `_process_submission()` 方法)

**Step 1: 修改 _extract_post_data() 确保评论包含 id 和时间戳**

找到 `_extract_post_data()` 方法中的评论提取代码（约第 242-255 行），修改为：

```python
# 获取评论
comments = []
try:
    submission.comment_sort = "top"
    submission.comments.replace_more(limit=0)
    for comment in submission.comments.list()[:20]:  # 获取前20条评论
        if hasattr(comment, 'author') and comment.author:
            comments.append({
                "id": comment.id,  # 添加评论ID
                "author": comment.author.name,
                "body": comment.body,
                "score": comment.score,
                "created_utc": getattr(comment, 'created_utc', None),  # 添加时间戳
                "created_at": datetime.fromtimestamp(getattr(comment, 'created_utc', 0)).isoformat() + "Z" if hasattr(comment, 'created_utc') else None
            })
except Exception as e:
    logger.warning(f"Failed to fetch comments for {submission.id}: {e}")
```

**Step 2: 修改 _process_submission() 调用 insert_comments()**

找到 `_process_submission()` 方法（约第 301-339 行），在保存帖子后添加评论插入逻辑。

在 `if success:` 块内，`self.stats["total_saved"] += 1` 之后添加：

```python
# 保存评论到独立的 comments 表
if comments and 'db' in globals():
    try:
        comment_count = db.insert_comments(unified_id, post_data.get("comments", []), "reddit")
        if comment_count > 0:
            logger.info(f"Saved {comment_count} comments for post {unified_id}")
    except Exception as e:
        logger.error(f"Failed to save comments for {unified_id}: {e}")
```

**Step 3: 测试 Reddit 抓取器评论插入**

```bash
# 先确保数据库已初始化
python3 -c "from utils.db import db; print('DB initialized')"

# 抓取少量帖子测试
python3 -c "
from pipeline.fetch import RedditSourceFetcher
import logging
logging.basicConfig(level=logging.INFO)

fetcher = RedditSourceFetcher('config/subreddits.yaml')
# 手动触发一个简单的测试
print('Reddit fetcher initialized successfully')
"
```

预期输出: `Reddit fetcher initialized successfully`

**Step 4: 提交**

```bash
git add pipeline/fetch.py
git commit -m "feat: update Reddit fetcher to insert comments into database"
```

---

## Task 4: 更新 Hacker News 抓取器以插入评论

**Files:**
- Modify: `pipeline/hn_fetch.py` (修改 `_extract_story_data()` 和 `fetch_from_endpoint()` 方法)

**Step 1: 修改 _extract_story_data() 确保评论包含完整字段**

找到 `_extract_story_data()` 方法中的评论提取代码（约第 52-69 行），修改为：

```python
# 获取评论（简化版，只获取前10条）
comments = []
kids = item.get("kids", [])

for kid_id in kids[:10]:  # 只获取前10条评论
    try:
        comment_url = f"{self.base_url}/item/{kid_id}.json"
        comment_resp = requests.get(comment_url, timeout=10)
        if comment_resp.status_code == 200:
            comment_data = comment_resp.json()
            if comment_data and comment_data.get("type") == "comment":
                comments.append({
                    "id": str(comment_data.get("id", "")),  # 确保id为字符串
                    "author": comment_data.get("by", ""),
                    "body": comment_data.get("text", ""),
                    "score": 0,  # HN评论没有score
                    "created_utc": comment_data.get("time"),  # 添加时间戳
                    "created_at": datetime.fromtimestamp(comment_data.get("time", 0)).isoformat() + "Z" if comment_data.get("time") else None
                })
    except Exception as e:
        logger.warning(f"Failed to fetch comment {kid_id}: {e}")
```

**Step 2: 修改 fetch_from_endpoint() 调用 insert_comments()**

找到 `fetch_from_endpoint()` 方法中保存帖子的代码（约第 152-163 行），在 `db.insert_raw_post(story_data)` 成功后添加评论插入：

```python
# 调用现有的db.insert_raw_post
try:
    from utils.db import db
    if db.insert_raw_post(story_data):
        self.processed_ids.add(unified_id)
        self.stats["total_saved"] += 1
        saved_count += 1
        logger.info(f"Saved HN story: {item.get('title', '')[:60]}... (ID: {story_id})")

        # 保存评论到独立的 comments 表
        if story_data.get("comments"):
            try:
                comment_count = db.insert_comments(unified_id, story_data["comments"], "hackernews")
                if comment_count > 0:
                    logger.info(f"Saved {comment_count} comments for HN story {story_id}")
            except Exception as e:
                logger.error(f"Failed to save comments for {unified_id}: {e}")
    else:
        self.stats["errors"] += 1
except Exception as db_e:
    logger.error(f"Failed to save HN story {story_id}: {db_e}")
    self.stats["errors"] += 1
```

**Step 3: 测试 HN 抓取器评论插入**

```bash
python3 -c "
from pipeline.hn_fetch import HackerNewsFetcher
import logging
logging.basicConfig(level=logging.INFO)

fetcher = HackerNewsFetcher()
print('HN fetcher initialized successfully')
"
```

预期输出: `HN fetcher initialized successfully`

**Step 4: 提交**

```bash
git add pipeline/hn_fetch.py
git commit -m "feat: update HN fetcher to insert comments into database"
```

---

## Task 5: 创建回填脚本

**Files:**
- Create: `scripts/backfill_comments.py`

**Step 1: 创建回填脚本文件**

```bash
mkdir -p scripts
cat > scripts/backfill_comments.py << 'EOF'
"""
回填评论数据
从 posts.raw_data 中提取评论并存入独立的 comments 表
"""
import logging
import json
from utils.db import db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _normalize_comments(comments: list, source: str) -> list:
    """规范化评论数据格式"""
    normalized = []

    for comment in comments:
        # Reddit 和 HN 的评论格式已经在 fetch 阶段统一
        # 这里主要做防御性检查
        if isinstance(comment, dict):
            normalized.append({
                "id": comment.get("id"),
                "author": comment.get("author", ""),
                "body": comment.get("body", ""),
                "score": comment.get("score", 0),
                "created_utc": comment.get("created_utc"),
                "created_at": comment.get("created_at")
            })

    return normalized

def backfill_comments(batch_size: int = 100, dry_run: bool = False) -> dict:
    """
    回填评论数据

    Args:
        batch_size: 每批处理的帖子数量
        dry_run: 如果为 True，只分析不实际插入

    Returns:
        统计信息字典
    """
    stats = {
        "total_posts": 0,
        "posts_with_comments": 0,
        "total_comments_extracted": 0,
        "comments_inserted": 0,
        "errors": 0
    }

    try:
        with db.get_connection("raw") as conn:
            # 获取所有包含 raw_data 的帖子
            cursor = conn.execute("""
                SELECT id, source, raw_data
                FROM posts
                WHERE raw_data IS NOT NULL
                AND raw_data != ''
                ORDER BY collected_at DESC
            """)

            posts = cursor.fetchall()
            stats["total_posts"] = len(posts)

            logger.info(f"Found {len(posts)} posts with raw_data to process")

            if len(posts) == 0:
                logger.warning("No posts with raw_data found")
                return stats

            # 分批处理
            for i in range(0, len(posts), batch_size):
                batch = posts[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(posts) + batch_size - 1) // batch_size
                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} posts)")

                for row in batch:
                    post_id = row['id']
                    source = row['source']
                    raw_data = row['raw_data']

                    try:
                        post_json = json.loads(raw_data)
                        comments = post_json.get("comments", [])

                        if not comments:
                            continue

                        stats["posts_with_comments"] += 1
                        stats["total_comments_extracted"] += len(comments)

                        if not dry_run:
                            # 提取并规范化评论数据
                            normalized_comments = _normalize_comments(comments, source)

                            # 插入评论
                            inserted = db.insert_comments(post_id, normalized_comments, source)
                            stats["comments_inserted"] += inserted
                        else:
                            # Dry-run 模式只统计
                            stats["comments_inserted"] += len(comments)

                        if (stats["posts_with_comments"] % 10) == 0:
                            logger.debug(f"Processed {stats['posts_with_comments']} posts with comments so far")

                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error for post {post_id}: {e}")
                        stats["errors"] += 1
                    except Exception as e:
                        logger.error(f"Error processing post {post_id}: {e}")
                        stats["errors"] += 1

        logger.info(f"""
=== Backfill Summary ===
Total posts processed: {stats['total_posts']}
Posts with comments: {stats['posts_with_comments']}
Total comments found: {stats['total_comments_extracted']}
Comments {'would be' if dry_run else 'actually'} inserted: {stats['comments_inserted']}
Errors: {stats['errors']}
""")

        return stats

    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        raise

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill comments from posts.raw_data")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, don't insert")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for processing")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("Running in DRY-RUN mode - no data will be inserted")

    backfill_comments(batch_size=args.batch_size, dry_run=args.dry_run)
EOF
```

**Step 2: 测试回填脚本 (dry-run 模式)**

```bash
python3 scripts/backfill_comments.py --dry-run --batch-size 10
```

预期输出示例:
```
Found XX posts with raw_data to process
Processing batch 1/X (10 posts)
...
=== Backfill Summary ===
Total posts processed: XX
Posts with comments: XX
Total comments found: XXX
Comments would be inserted: XXX
Errors: 0
```

**Step 3: 提交**

```bash
git add scripts/backfill_comments.py
git commit -m "feat: add backfill script for comments migration"
```

---

## Task 6: 执行回填并验证

**Step 1: 执行实际的回填操作**

```bash
python3 scripts/backfill_comments.py --batch-size 100
```

预期输出:
```
Found XX posts with raw_data to process
Processing batch 1/X (100 posts)
...
=== Backfill Summary ===
Total posts processed: XX
Posts with comments: XX
Total comments found: XXX
Comments actually inserted: XXX
Errors: 0
```

**Step 2: 验证数据已正确插入**

运行验证查询：

```bash
sqlite3 data/wise_collection.db << 'EOF'
-- 验证 1: 确认评论表有数据
SELECT '=== Test 1: Total comments ===' as test_name;
SELECT COUNT(*) as comment_count FROM comments;

-- 验证 2: 确认评论关联到多个帖子
SELECT '=== Test 2: Posts with comments ===' as test_name;
SELECT COUNT(DISTINCT post_id) as post_count FROM comments;

-- 验证 3: 确认两个数据源都有评论
SELECT '=== Test 3: Comments by source ===' as test_name;
SELECT source, COUNT(*) as count FROM comments GROUP BY source;

-- 验证 4: 验证关联查询正常
SELECT '=== Test 4: Sample join query ===' as test_name;
SELECT p.title, substr(c.body, 1, 50) as comment_preview, c.author
FROM posts p
JOIN comments c ON p.id = c.post_id
WHERE p.source = 'reddit'
LIMIT 5;
EOF
```

预期结果:
- Test 1: comment_count > 0
- Test 2: post_count > 0
- Test 3: 应该看到 'reddit' 和 'hackernews' 两行
- Test 4: 返回 5 条记录

**Step 3: 验证复合索引使用**

```bash
sqlite3 data/wise_collection.db << 'EOF'
EXPLAIN QUERY PLAN
SELECT * FROM comments
WHERE post_id IN (SELECT id FROM posts LIMIT 1)
ORDER BY score DESC
LIMIT 20;
EOF
```

预期输出应包含: `SEARCH comments USING INDEX idx_comments_post_id_score`

**Step 4: 提交回填完成**

如果所有验证通过，创建标记提交：

```bash
echo "Comments backfill completed successfully" > scripts/.backfill_completed
git add scripts/.backfill_completed
git commit -m "chore: mark comments backfill as completed"
```

---

## Task 7: 创建验证脚本

**Files:**
- Create: `scripts/verify_comments.sql`

**Step 1: 创建 SQL 验证脚本**

```bash
cat > scripts/verify_comments.sql << 'EOF'
-- Comments Table Verification Script
-- Run this to verify the comments table is working correctly

.mode column
.headers on

-- Test 1: Check if comments table exists
SELECT '=== Test 1: Comments Table Exists ===' as "";
SELECT name FROM sqlite_master WHERE type='table' AND name='comments';

-- Test 2: Count total comments
SELECT '=== Test 2: Total Comment Count ===' as "";
SELECT COUNT(*) as total_comments FROM comments;

-- Test 3: Count posts with comments
SELECT '=== Test 3: Posts With Comments ===' as "";
SELECT COUNT(DISTINCT post_id) as posts_with_comments FROM comments;

-- Test 4: Comments by source
SELECT '=== Test 4: Comments By Source ===' as "";
SELECT source, COUNT(*) as count, AVG(score) as avg_score FROM comments GROUP BY source;

-- Test 5: Sample comments with post titles
SELECT '=== Test 5: Sample Comments ===' as "";
SELECT
    p.source,
    substr(p.title, 1, 30) as title_preview,
    substr(c.body, 1, 50) as comment_preview,
    c.score
FROM posts p
JOIN comments c ON p.id = c.post_id
ORDER BY c.score DESC
LIMIT 10;

-- Test 6: Check indexes
SELECT '=== Test 6: Indexes on Comments Table ===' as "";
SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='comments';

SELECT '=== All Tests Complete ===' as "";
EOF
```

**Step 2: 运行验证脚本**

```bash
sqlite3 data/wise_collection.db < scripts/verify_comments.sql
```

预期输出: 所有测试应显示数据

**Step 3: 提交**

```bash
git add scripts/verify_comments.sql
git commit -m "test: add SQL verification script for comments table"
```

---

## Task 8: 更新 README 文档

**Files:**
- Modify: `README.md` (如果项目根目录有) 或 `docs/plans/2025-12-24-phase1-comments-integration-design.md`

**Step 1: 在设计文档的 Implementation Checklist 中标记完成的任务**

编辑 `docs/plans/2025-12-24-phase1-comments-integration-design.md`，将以下项标记为完成：

```markdown
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
```

**Step 2: 提交文档更新**

```bash
git add docs/plans/2025-12-24-phase1-comments-integration-design.md
git commit -m "docs: mark Phase 1 implementation tasks as completed"
```

---

## 验收标准

完成所有任务后，运行以下验证：

```bash
# 1. 验证表结构
sqlite3 data/wise_collection.db "SELECT COUNT(*) FROM comments;"

# 2. 验证数据完整性
sqlite3 data/wise_collection.db < scripts/verify_comments.sql

# 3. 验证新抓取的帖子会自动保存评论
# (手动测试：运行一次完整的 fetch，检查新帖子的评论是否被保存)
```

**成功标准:**
- ✅ `comments` 表存在且有数据
- ✅ 至少有 1 个帖子有关联的评论
- ✅ Reddit 和 HackerNews 都有评论记录
- ✅ 复合索引 `idx_comments_post_id_score` 存在
- ✅ 验证查询成功返回数据

---

## 故障排查

**问题：回填后 comments 表为空**
- 检查: `SELECT COUNT(*) FROM posts WHERE raw_data IS NOT NULL;`
- 如果为 0，说明现有帖子没有 raw_data，需要重新抓取

**问题：警告日志显示 "Comment ... is missing a source ID"**
- 检查日志确定是哪个数据源的问题
- 验证 fetch 阶段是否正确提取了评论 ID

**问题：评论插入失败**
- 检查数据库文件权限
- 查看详细错误日志: `grep "Failed to insert comments" logs/pipeline.log`
