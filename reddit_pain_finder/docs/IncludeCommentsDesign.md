# 🧠 Design: Treating Comments as Independent Pain Sources

## Executive Summary

This document outlines the design for extracting pain events from Reddit/HN **comments** as independent sources, rather than treating them as mere appendages to posts.

**Key Insight**: Comments are user expressions in their own right. A 9000-upvote comment saying "Stop giving him money" is itself a strong pain signal, regardless of whether its parent post passed our filters.

**Goal**: Increase pain event coverage by 2-3x by mining the 42,013 comments that currently sit unused in our database.

---

## Problem Statement

### Current Situation

```
Posts: 2,997 → Filtered: 417 (13.9%) → Pain events: ~600
Comments: 42,013 → Used: 6,296 (15%) → Mostly ignored
```

### The Waste

- **85% of comments (35,717)** are from posts that didn't pass `filter_signal`
- These comments are **never analyzed** for pain signals
- **High-value pain signals are being missed**:
  - 9,223-upvote comment: "Stop giving him money. You need it to keep a roof over your heads."
  - 5,634-upvote comment: "You're his tax evasion partner"
  - 4,490-upvote comment: "Why are you tolerating this from anyone"

### Root Cause

Current architecture assumes:
```
❌ Post = container (primary)
❌ Comment = accessory (secondary, dependent)
```

This is wrong. Comments are **independent user expressions** that happen to reference a post.

---

## Design Philosophy

### Core Principles

1. **Comments as First-Class Citizens**
   - Comments ≠ post metadata
   - Comments = independent user expressions
   - Each comment deserves its own pain signal evaluation

2. **No New Stages**
   - Extend existing `filter_signal` and `extract_pain` stages
   - Downstream stages (`embed`, `cluster`, `map_opportunity`) unchanged
   - Comments flow through the same pipeline as posts

3. **Context as Metadata, Not Dependency**
   - Parent post provides background context
   - But comment stands on its own for pain extraction
   - If comment has pain signals, extract them regardless of parent post status

4. **Lower Thresholds for Comments**
   - Comments are shorter and more direct
   - Require lower quality/pain thresholds than posts
   - High upvotes = community validation

---

## Architecture

### Pipeline Overview

```
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: fetch (unchanged)                                  │
│ - Fetch posts + comments, save all to database              │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: filter_signal (extended)                           │
│ ├─ Posts flow: posts → filter → filtered_posts              │
│ └─ Comments flow: comments → filter → filtered_comments (NEW)│
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: extract_pain (unified processing)                  │
│ ├─ filtered_posts → pain_events (source_type='post')        │
│ └─ filtered_comments → pain_events (source_type='comment')  │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Stage 4+: embed, cluster, map_opportunity (no changes)      │
│ - pain_events are pain_events, regardless of source         │
└─────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| **New table?** | Yes: `filtered_comments` | Parallel to `filtered_posts` |
| **New stage?** | No | Extend existing stages |
| **Context loading?** | Yes, dynamic | Load parent post as metadata |
| **Thresholds?** | Lower for comments | Comments shorter, more direct |
| **Downstream changes?** | None | Pain events are source-agnostic |

---

## Data Model

### 1. New Table: `filtered_comments`

```sql
CREATE TABLE filtered_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_id INTEGER NOT NULL,           -- FK to comments.id
    source TEXT NOT NULL,                  -- 'reddit' or 'hackernews'
    post_id TEXT NOT NULL,                 -- Parent post ID (for context)
    author TEXT,
    body TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    pain_score REAL DEFAULT 0.0,
    pain_keywords TEXT,                    -- JSON array
    filter_reason TEXT,
    engagement_score REAL DEFAULT 0.0,
    filtered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (comment_id) REFERENCES comments(id),
    FOREIGN KEY (post_id) REFERENCES posts(id),
    UNIQUE(comment_id)                     -- Each comment filtered once
);

-- Indexes for performance
CREATE INDEX idx_filtered_comments_post_id ON filtered_comments(post_id);
CREATE INDEX idx_filtered_comments_score ON filtered_comments(score DESC);
CREATE INDEX idx_filtered_comments_pain_score ON filtered_comments(pain_score DESC);
```

### 2. Extend `pain_events` Table

```sql
-- Add source tracking columns
ALTER TABLE pain_events ADD COLUMN source_type TEXT DEFAULT 'post';
ALTER TABLE pain_events ADD COLUMN source_id TEXT;
ALTER TABLE pain_events ADD COLUMN parent_post_id TEXT;

-- Update existing records (migration)
UPDATE pain_events SET source_type = 'post', source_id = post_id WHERE source_type IS NULL;

-- Index for source queries
CREATE INDEX idx_pain_events_source_type ON pain_events(source_type);
```

**Alternative**: Reuse existing fields
- `post_id` → When `source_type='comment'`, store parent post id
- `evidence_sources` → Explicitly mark `["comment"]` or `["post", "comment"]`

---

## Implementation Details

### Stage 2: filter_signal Extension

#### 2.1 Add Comment Filtering Logic

```python
# pipeline/filter_signal.py

class PainSignalFilter:
    def __init__(self, config_path: str = "config/thresholds.yaml"):
        # Existing initialization
        self.thresholds = self._load_thresholds(config_path)
        self.comment_thresholds = self._load_comment_thresholds()

    def _load_comment_thresholds(self) -> Dict[str, Any]:
        """Load comment-specific thresholds (lower than posts)"""
        return {
            "min_score": 5,              # Post: 5-20
            "min_length": 20,            # Post: 50
            "min_pain_score": 0.2,       # Post: 0.3-0.5
            "min_keywords": 1,           # Post: 1 category
            "engagement_threshold": 0.1  # Post: 0.2
        }

    def filter_comment(self, comment_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Filter a single comment (parallel to filter_post)"""

        # 1. Quality thresholds
        if comment_data.get("score", 0) < self.comment_thresholds["min_score"]:
            return False, {"reason": "low_score", "score": comment_data.get("score")}

        body = comment_data.get("body", "")
        if len(body) < self.comment_thresholds["min_length"]:
            return False, {"reason": "too_short", "length": len(body)}

        # 2. Pain signal detection (reuse existing logic)
        pain_signals = self._detect_pain_signals(
            text=body,
            context_type="comment"
        )

        if not pain_signals.get("has_pain", False):
            return False, {"reason": "no_pain_signals"}

        # 3. Calculate pain score
        pain_score = self._calculate_pain_score(
            text=body,
            signals=pain_signals
        )

        # 4. Check threshold
        if pain_score < self.comment_thresholds["min_pain_score"]:
            return False, {"reason": "low_pain_score", "score": pain_score}

        # 5. Passed!
        return True, {
            "pain_score": pain_score,
            "pain_keywords": pain_signals.get("keywords", []),
            "filter_reason": pain_signals.get("primary_reason", "pain_detected"),
            "engagement_score": self._calculate_engagement_score(comment_data)
        }

    def filter_comments_batch(self, comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter comments in batch"""
        filtered = []
        for comment in comments:
            passed, result = self.filter_comment(comment)
            if passed:
                filtered.append({
                    "comment_id": comment["id"],
                    "post_id": comment["post_id"],
                    "source": comment.get("source", "reddit"),
                    "author": comment.get("author"),
                    "body": body,
                    "score": comment.get("score", 0),
                    **result
                })
        return filtered
```

#### 2.2 Threshold Comparison

| Metric | Posts | Comments | Why Lower for Comments? |
|--------|-------|----------|-------------------------|
| Min score | 5-20 | 5 | Comments shorter, but high score = validation |
| Min length | 50 chars | 20 chars | Comments more concise |
| Pain keywords | ≥1 category | ≥1 keyword | Comments more focused |
| Min pain_score | 0.3-0.5 | 0.2-0.3 | Comments express pain more directly |
| Engagement | 0.2 | 0.1 | Comments are reactions to engagement |

**Rationale**:
- Comments are more direct: "This tool is broken" vs "I'm having trouble with tool X..."
- Comments are validated: High upvotes = community agrees
- Comments are specific: Often mention exact pain points

### Stage 3: extract_pain Extension

#### 3.1 Extract from Comments

```python
# pipeline/extract_pain.py

class PainPointExtractor:
    def _extract_from_single_comment(self, comment_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract pain events from a single comment"""

        comment_id = comment_data["comment_id"]
        post_id = comment_data["post_id"]
        body = comment_data["body"]
        score = comment_data.get("score", 0)

        # 1. Load parent post as context (not primary source)
        parent_post = self._get_parent_post_context(post_id)

        # 2. Call LLM with comment as PRIMARY source
        response = llm_client.extract_pain_points(
            title=parent_post.get("title", "[Comment context]"),  # Context only
            body=body,  # PRIMARY: the comment itself
            subreddit=parent_post.get("subreddit", ""),
            upvotes=score,
            comments_count=0,  # Comments don't have sub-comments (yet)
            top_comments=[],   # No sub-comments
            metadata={
                "source_type": "comment",
                "parent_post_title": parent_post.get("title"),
                "parent_post_body": parent_post.get("body", "")[:500],  # Truncated context
            }
        )

        # 3. Annotate pain events
        pain_events = response["content"]["pain_events"]
        for event in pain_events:
            event.update({
                "post_id": post_id,           # Parent post (for linking)
                "comment_id": comment_id,     # Actual source
                "source_type": "comment",     # Mark as comment-sourced
                "evidence_sources": ["comment"],  # Explicitly not from post
                "original_score": score,
                "extraction_timestamp": datetime.now().isoformat()
            })

        return pain_events

    def _get_parent_post_context(self, post_id: str) -> Dict[str, Any]:
        """Load parent post as lightweight context"""
        try:
            with db.get_connection("raw") as conn:
                cursor = conn.execute("""
                    SELECT title, body, subreddit, score, num_comments
                    FROM posts
                    WHERE id = ?
                """, (post_id,))
                row = cursor.fetchone()
                return dict(row) if row else {}
        except Exception as e:
            logger.warning(f"Failed to load parent post {post_id}: {e}")
            return {}
```

#### 3.2 Unified Processing

```python
def process_all_filtered_content(self):
    """Process both posts and comments"""

    # 1. Process posts (existing logic)
    logger.info("Processing filtered posts...")
    posts = db.get_all_filtered_posts()
    for post in posts:
        events = self._extract_from_single_post(post)
        db.save_pain_events(events, source_type='post')

    # 2. Process comments (new logic)
    logger.info("Processing filtered comments...")
    comments = db.get_all_filtered_comments()
    for comment in comments:
        events = self._extract_from_single_comment(comment)
        db.save_pain_events(events, source_type='comment')

    logger.info(f"Extracted pain events from {len(posts)} posts and {len(comments)} comments")
```

#### 3.3 LLM Prompt Update

```python
# utils/llm_client.py

def _get_pain_extraction_prompt(self) -> str:
    return """You are extracting pain points from user-generated content.

## Important Context

You may be analyzing EITHER:
1. A POST (primary content, discussion starter)
2. A COMMENT (reaction/advice to a post)

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

### Database Access Methods

```python
# utils/db.py

class WiseCollectionDB:
    def get_all_comments_for_filtering(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get all comments that need filtering"""
        try:
            with self.get_connection("raw") as conn:
                query = """
                    SELECT c.id, c.post_id, c.source, c.author, c.body, c.score,
                           p.subreddit, p.title as post_title
                    FROM comments c
                    JOIN posts p ON c.post_id = p.id
                    WHERE c.id NOT IN (
                        SELECT comment_id FROM filtered_comments
                    )
                    ORDER BY c.score DESC
                """
                if limit:
                    query += f" LIMIT {limit}"

                cursor = conn.execute(query)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get comments: {e}")
            return []

    def save_filtered_comments(self, comments: List[Dict[str, Any]]) -> int:
        """Save comments that passed filter"""
        try:
            with self.get_connection("filtered") as conn:
                count = 0
                for comment in comments:
                    conn.execute("""
                        INSERT OR IGNORE INTO filtered_comments
                        (comment_id, source, post_id, author, body, score,
                         pain_score, pain_keywords, filter_reason, engagement_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        comment["comment_id"],
                        comment["source"],
                        comment["post_id"],
                        comment.get("author"),
                        comment["body"],
                        comment["score"],
                        comment["pain_score"],
                        json.dumps(comment.get("pain_keywords", [])),
                        comment["filter_reason"],
                        comment.get("engagement_score", 0.0)
                    ))
                    count += 1
                conn.commit()
                return count
        except Exception as e:
            logger.error(f"Failed to save filtered comments: {e}")
            return 0

    def get_all_filtered_comments(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get all filtered comments for pain extraction"""
        try:
            with self.get_connection("filtered") as conn:
                query = """
                    SELECT fc.id, fc.comment_id, fc.post_id, fc.author,
                           fc.body, fc.score, fc.pain_score, fc.pain_keywords,
                           p.subreddit, p.title as post_title
                    FROM filtered_comments fc
                    JOIN posts p ON fc.post_id = p.id
                    WHERE fc.comment_id NOT IN (
                        SELECT source_id FROM pain_events WHERE source_type = 'comment'
                    )
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

---

## Downstream Stages (No Changes Required)

### Stage 4: embed

**No changes needed**. The embedding model processes text, regardless of source.

```python
# Existing code works
pain_events = db.get_all_pain_events()  # Includes comment-sourced events
for event in pain_events:
    embedding = model.encode(event["problem"])
    db.save_embedding(event["id"], embedding)
```

### Stage 5: cluster

**Minimal changes**. Add optional source-aware analysis:

```python
# pipeline/cluster.py

def _summarize_cluster_sources(self, pain_events: List[Dict]) -> Dict[str, Any]:
    """Analyze source composition of a cluster"""
    source_counts = {"post": 0, "comment": 0}
    for event in pain_events:
        source_type = event.get("source_type", "post")
        source_counts[source_type] += 1

    total = len(pain_events)
    return {
        "post_events": source_counts["post"],
        "comment_events": source_counts["comment"],
        "comment_ratio": source_counts["comment"] / total if total > 0 else 0
    }

# Use in cluster summary
cluster_info["source_breakdown"] = self._summarize_cluster_sources(cluster_events)
```

### Stage 6: map_opportunity

**No changes needed**. Pain events are pain events.

---

## Expected Outcomes

### Quantitative Impact

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Filtered content | 417 posts | 417 posts + ~2,000 comments | 5.8x more inputs |
| Pain events | ~1,200 | ~3,600 | 3x increase |
| Comment-sourced events | ~15% | ~67% | New majority |
| High-quality events | ~600 | ~1,800 | 3x increase |

**Assumptions**:
- 5% of comments pass filter (42,013 × 0.05 = ~2,100)
- Each comment yields 1.2 pain events (vs 1.5 for posts, due to shorter length)
- 50% of comment-sourced events pass quality thresholds

### Qualitative Improvements

1. **Community-Validated Pains**
   - High-upvote comments = many people agree
   - More reliable than single-user posts

2. **More Specific Pains**
   - Comments get into details
   - Post: "Tool X has issues"
   - Comment: "Tool X crashes when I save files larger than 10MB"

3. **Workaround Discovery**
   - Comments often share workarounds
   - "I use script Y to fix problem Z"
   - Rich context for opportunity mapping

4. **Pain Confirmation**
   - Same pain in post + comments = strong signal
   - "I struggle with X" (post) + "Me too, X is terrible" (comment)

---

## Implementation Phases

### Phase 1: Filter Comments (1-2 days)

**Goals**:
- Add `filtered_comments` table
- Implement `filter_comment()` logic
- Run filtering on existing 42,013 comments

**Tasks**:
1. ✅ Create `filtered_comments` table migration
2. ✅ Implement `PainSignalFilter.filter_comment()`
3. ✅ Add `WiseCollectionDB.get_all_comments_for_filtering()`
4. ✅ Add `WiseCollectionDB.save_filtered_comments()`
5. ✅ Run filtering script on all comments
6. ✅ Validate results (manual review of 100 random samples)

**Deliverables**:
- Database schema updated
- ~2,000 comments in `filtered_comments`
- Validation report (false positive rate)

### Phase 2: Extract Pain from Comments (2-3 days)

**Goals**:
- Extend pain extraction to handle comments
- Load parent post context dynamically
- Generate pain events from filtered comments

**Tasks**:
1. ✅ Implement `PainPointExtractor._extract_from_single_comment()`
2. ✅ Add `WiseCollectionDB._get_parent_post_context()`
3. ✅ Update LLM prompt for comment-aware extraction
4. ✅ Add `source_type` tracking to pain_events
5. ✅ Run extraction on filtered comments
6. ✅ Compare quality with post-sourced events

**Deliverables**:
- ~2,400 new pain events in database
- Quality comparison report
- Sample pain events (manual review)

### Phase 3: Integration & Validation (2-3 days)

**Goals**:
- Run full pipeline with comments
- Validate clustering quality
- Generate opportunities from comment-sourced events

**Tasks**:
1. ✅ Run `embed` on all pain events (posts + comments)
2. ✅ Run `cluster` and analyze source distribution
3. ✅ Run `map_opportunity` on new clusters
4. ✅ Manual review of 50 comment-sourced opportunities
5. ✅ Compare opportunity quality with/without comments

**Deliverables**:
- Updated clusters with comment data
- New opportunities from comments
- Validation report with metrics

### Phase 4: Optimization (Optional, 1-2 days)

**Goals**:
- Fine-tune comment thresholds
- Add source-aware features
- Performance optimization

**Tasks**:
1. 🔧 Adjust comment thresholds based on results
2. 🔧 Add comment-threading support (replies)
3. 🔧 Implement source-weighted clustering
4. 🔧 Optimize database queries for scale
5. 🔧 Add monitoring/metrics for comment pipeline

**Deliverables**:
- Optimized thresholds
- Enhanced clustering algorithm
- Performance benchmarks

---

## Risk Mitigation

### Risk 1: False Positives from Joke/Meme Comments

**Problem**: Reddit/HN have many low-quality comments

**Mitigation**:
- ✅ **Score threshold**: Only filter comments with ≥5 upvotes
- ✅ **Length threshold**: Minimum 20 characters
- ✅ **Joke detection**: Add patterns for common memes/copypasta
- ✅ **Manual review**: Sample 100 filtered comments for quality

**Acceptable Rate**: <15% false positives

### Risk 2: Context Loss Without Parent Post

**Problem**: Comment extracted in isolation may be misunderstood

**Mitigation**:
- ✅ **Dynamic context loading**: Always load parent post
- ✅ **LLM instructions**: Explicitly tell LLM it's a comment
- ✅ **Traceability**: Store `parent_post_id` for audit trail
- ✅ **Quality check**: Manual review of ambiguous cases

**Validation**: Compare extracted pain with/without context

### Risk 3: Duplicate Pain Events

**Problem**: Same pain mentioned in post and comments

**Mitigation**:
- ✅ **Deduplication**: Existing clustering handles this
- ✅ **Feature, not bug**: Duplication = pain validation
- ✅ **Confidence scoring**: Higher confidence when appears in both
- ✅ **Optional**: Merge similar events in extraction phase

**Strategy**: Keep duplicates, let clustering handle them

### Risk 4: Storage Increase

**Problem**: Filtering 42K comments increases database size

**Mitigation**:
- ✅ **Only filtered**: `filtered_comments` only contains ~2K (5%)
- ✅ **No raw data**: Don't store duplicate `raw_data` JSON
- ✅ **Archive policy**: Periodically move old filtered comments to archive
- ✅ **Cleanup**: Delete `filtered_comments` after pain extraction (optional)

**Estimate**: ~2K × 1KB = 2MB (negligible)

### Risk 5: Performance Degradation

**Problem**: Processing 3x more pain events slows down pipeline

**Mitigation**:
- ✅ **Batching**: Process comments in batches
- ✅ **Parallel processing**: Extract from posts and comments concurrently
- ✅ **Caching**: Cache parent post context
- ✅ **Incremental**: Only process new comments since last run

**Target**: No significant slowdown (<10% increase in runtime)

---

## Success Metrics

### Quantitative

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Pain event increase | ≥2x | Count pain_events before/after |
| Comment contribution | ≥50% | Ratio of comment-sourced events |
| Cluster quality | No decrease | workflow_similarity scores |
| False positive rate | <15% | Manual review of 100 samples |
| Pipeline runtime | <110% of baseline | Time pipeline execution |

### Qualitative

| Metric | Target | How to Measure |
|--------|--------|----------------|
| New pain discovery | ≥10 new pain patterns | Manual review of opportunities |
| Better validation | Comments confirm post pains | Compare post vs comment events |
| Deeper context | More specific pain details | Character count, specificity |
| Opportunity richness | More diverse opportunities | Category distribution |

---

## Future Enhancements

### 1. Comment Threading

**Current**: Top-level comments only
**Future**: Recursive extraction through reply chains

**Benefit**: Capture elaborated pain descriptions

```python
# Future implementation
def extract_from_comment_thread(self, root_comment):
    """Extract pain from comment and all replies"""
    events = self._extract_from_single_comment(root_comment)

    for reply in root_comment["replies"]:
        events += self._extract_from_single_comment(reply)

    return events
```

### 2. Cross-Post Pain Discovery

**Idea**: Same pain mentioned across multiple posts' comments

**Signal**: Strong pain pattern

```python
# Future implementation
def detect_cross_post_pains(self):
    """Find pains mentioned in comments across different posts"""
    pain_keywords = extract_keywords_from_comments()

    # Group by similar pains
    pain_groups = group_similar_pains(pain_keywords)

    # High frequency = strong pain
    strong_pains = [g for g in pain_groups if g.frequency > 5]

    return strong_pains
```

### 3. Comment Evolution Tracking

**Idea**: Track how pain signals change over time in comments

**Example**:
- Week 1: "Tool X is slow"
- Week 4: "Tool X is slow and crashes"
- Week 8: "Tool X is slow, crashes, and lost my data"

**Benefit**: Escalating pain = urgent opportunity

### 4. Source-Weighted Clustering

**Idea**: Give comment-sourced events higher weight

**Rationale**: Comments are community-validated

```python
# Future implementation
def calculate_event_weight(self, pain_event):
    """Calculate confidence weight based on source"""
    base_weight = 1.0

    if pain_event["source_type"] == "comment":
        # Boost for community validation
        comment_score = pain_event.get("original_score", 0)
        validation_factor = min(comment_score / 1000, 2.0)  # Max 2x
        return base_weight * validation_factor

    return base_weight
```

### 5. Sentiment Analysis Pre-Filter

**Idea**: Use sentiment analysis to filter obviously non-pain comments

**Benefit**: Reduce false positives

```python
# Future implementation
def is_likely_pain_comment(self, comment_body):
    """Use sentiment to pre-filter comments"""
    sentiment = analyze_sentiment(comment_body)

    # Only positive/unlikely comments get filtered out early
    if sentiment["polarity"] > 0.5:  # Very positive
        return False

    # Negative/neutral might still contain pain
    return True
```

---

## Configuration

### thresholds.yaml Extension

```yaml
# Comment-specific thresholds (lower than posts)
comment_thresholds:
  min_score: 5              # Minimum upvotes
  min_length: 20            # Minimum characters
  max_length: 2000          # Maximum characters (longer = likely not a comment)
  min_pain_score: 0.2       # Minimum pain signal score
  min_keywords: 1           # Minimum pain keywords
  engagement_threshold: 0.1 # Engagement score threshold

  # Comment-specific exclusions
  exclude_patterns:
    - "thanks!"
    - "great post"
    - "this!"
    - "source?"             # HN "source?" comments
    - "duplicate"           # HN duplicate flags

  # Score boosters
  boost_factors:
    high_score_multiplier: 1.5  # If score > 100
    gold_award_multiplier: 2.0  # If reddit gold awarded
    op_reply_multiplier: 1.2    # If reply to OP
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_filter_comments.py

def test_filter_comment_basic():
    """Test basic comment filtering"""
    comment = {
        "id": 1,
        "body": "This tool is frustrating, it keeps crashing",
        "score": 10,
        "author": "user1"
    }

    filter = PainSignalFilter()
    passed, result = filter.filter_comment(comment)

    assert passed is True
    assert result["pain_score"] > 0.2

def test_filter_comment_low_score():
    """Test that low-score comments are rejected"""
    comment = {
        "id": 2,
        "body": "This is terrible",
        "score": 2,  # Below threshold
        "author": "user2"
    }

    filter = PainSignalFilter()
    passed, result = filter.filter_comment(comment)

    assert passed is False
    assert result["reason"] == "low_score"

def test_filter_comment_too_short():
    """Test that very short comments are rejected"""
    comment = {
        "id": 3,
        "body": "bad",
        "score": 100,
        "author": "user3"
    }

    filter = PainSignalFilter()
    passed, result = filter.filter_comment(comment)

    assert passed is False
    assert result["reason"] == "too_short"
```

### Integration Tests

```python
# tests/test_comment_extraction_integration.py

def test_full_comment_pipeline():
    """Test end-to-end comment processing"""
    # 1. Setup: Insert test comments
    test_comments = create_test_comments(count=100)

    # 2. Filter
    filter = PainSignalFilter()
    filtered = filter.filter_comments_batch(test_comments)

    assert len(filtered) > 0
    assert len(filtered) < len(test_comments)  # Some should be filtered out

    # 3. Extract
    extractor = PainPointExtractor()
    pain_events = []
    for comment in filtered:
        events = extractor._extract_from_single_comment(comment)
        pain_events.extend(events)

    assert len(pain_events) > 0

    # 4. Validate
    for event in pain_events:
        assert event["source_type"] == "comment"
        assert event["comment_id"] is not None
        assert len(event["problem"]) > 10
```

### Quality Validation

```python
# scripts/validate_comment_quality.py

def manual_quality_review(sample_size=100):
    """Manual review of comment-sourced pain events"""
    events = get_random_comment_sourced_events(sample_size)

    results = {
        "valid": 0,
        "invalid": 0,
        "uncertain": 0
    }

    for event in events:
        print(f"\nEvent: {event['problem']}")
        print(f"Source: {event['source_type']}")
        print(f"Comment: {event['context'][:200]}")

        verdict = input("Valid? (y/n/u): ").lower()
        if verdict == 'y':
            results["valid"] += 1
        elif verdict == 'n':
            results["invalid"] += 1
        else:
            results["uncertain"] += 1

    print(f"\nResults:")
    print(f"Valid: {results['valid']}%")
    print(f"Invalid: {results['invalid']}%")
    print(f"Uncertain: {results['uncertain']}%")

    return results
```

---

## Migration Strategy

### Database Migration

```sql
-- migration_001_add_filtered_comments.sql

-- 1. Create filtered_comments table
CREATE TABLE IF NOT EXISTS filtered_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    post_id TEXT NOT NULL,
    author TEXT,
    body TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    pain_score REAL DEFAULT 0.0,
    pain_keywords TEXT,
    filter_reason TEXT,
    engagement_score REAL DEFAULT 0.0,
    filtered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (comment_id) REFERENCES comments(id),
    FOREIGN KEY (post_id) REFERENCES posts(id),
    UNIQUE(comment_id)
);

-- 2. Add source tracking to pain_events
ALTER TABLE pain_events ADD COLUMN source_type TEXT DEFAULT 'post';
ALTER TABLE pain_events ADD COLUMN source_id TEXT;
ALTER TABLE pain_events ADD COLUMN parent_post_id TEXT;

-- 3. Migrate existing pain events
UPDATE pain_events
SET source_type = 'post',
    source_id = post_id,
    parent_post_id = post_id
WHERE source_type IS NULL;

-- 4. Create indexes
CREATE INDEX idx_filtered_comments_post_id ON filtered_comments(post_id);
CREATE INDEX idx_filtered_comments_score ON filtered_comments(score DESC);
CREATE INDEX idx_filtered_comments_pain_score ON filtered_comments(pain_score DESC);
CREATE INDEX idx_pain_events_source_type ON pain_events(source_type);
```

### Rollback Plan

```sql
-- Rollback migration if needed

DROP TABLE IF EXISTS filtered_comments;

-- Note: We keep the pain_events columns for backward compatibility
-- They'll be NULL for old records, which is fine
```

---

## Monitoring & Metrics

### Key Metrics to Track

```python
# monitoring.py

class CommentPipelineMetrics:
    def __init__(self):
        self.metrics = {
            "comments_filtered": 0,
            "comments_extracted": 0,
            "pain_events_from_comments": 0,
            "avg_comment_pain_score": 0.0,
            "filter_pass_rate": 0.0,
            "extraction_success_rate": 0.0
        }

    def record_filter_result(self, total_comments, passed_comments):
        self.metrics["comments_filtered"] += passed_comments
        self.metrics["filter_pass_rate"] = passed_comments / total_comments

    def record_extraction_result(self, total_comments, events_extracted):
        self.metrics["comments_extracted"] += total_comments
        self.metrics["pain_events_from_comments"] += events_extracted
        self.metrics["extraction_success_rate"] = events_extracted / total_comments

    def generate_report(self):
        return {
            "filter_efficiency": f"{self.metrics['filter_pass_rate']:.1%} of comments passed",
            "extraction_yield": f"{self.metrics['extraction_success_rate']:.2f} events per comment",
            "total_contribution": f"{self.metrics['pain_events_from_comments']} pain events from comments"
        }
```

---

## Documentation Updates

### Update run_pipeline.py Help

```python
# run_pipeline.py

parser.add_argument(
    "--include-comments",
    action="store_true",
    help="Extract pain events from comments (experimental)"
)

parser.add_argument(
    "--comment-min-score",
    type=int,
    default=5,
    help="Minimum upvotes for comment filtering (default: 5)"
)
```

### Update README.md

```markdown
## Pain Point Extraction

The system extracts pain points from two sources:

1. **Posts**: Primary discussion content
2. **Comments** (experimental): User reactions and advice

By default, only posts are analyzed. To include comments:

```bash
python3 run_pipeline.py --stage extract_pain --include-comments
```

### Comment Filtering

Comments are filtered using the same pain signal detection as posts, but with adjusted thresholds:

- Minimum score: 5 upvotes
- Minimum length: 20 characters
- Lower pain score threshold: 0.2

This ensures we capture high-quality, community-validated pain signals from comments.
```

---

## Conclusion

This design treats **comments as independent pain signal sources**, not post dependencies. By extending the existing `filter_signal` and `extract_pain` stages (without adding new stages), we can:

1. **Unlock 3x more pain events** from existing data
2. **Capture community-validated pains** through high-upvote comments
3. **Discover more specific pain details** from comment discussions
4. **Maintain pipeline simplicity** without major architectural changes

The key insight: **Every user expression deserves pain signal evaluation**, whether it's a post or a comment.

---

## Appendix: Example Workflows

### Example 1: High-Scoring Comment with Pain

**Post**: "What's your cooking workflow?" (no clear pain)

**Comment** (9,000 upvotes):
> "I hate that my knife always dulls mid-prep. I have to stop and sharpen it 3-4 times per meal, and it ruins my flow. Anyone found a knife that stays sharp longer?"

**Analysis**:
- ✅ High score (9,000) = community validation
- ✅ Clear pain: "hate that my knife always dulls"
- ✅ Specific details: "3-4 times per meal", "ruins my flow"
- ✅ Emotional signal: "hate"
- ✅ Question indicates seeking solution

**Result**: Strong pain event about knife durability

### Example 2: Moderate Comment Confirming Post Pain

**Post**: "Tool X has been really slow lately (200ms load times)"

**Comment** (500 upvotes):
> "Same here. Switched to tool Y and it's 50ms. Much better."

**Analysis**:
- ✅ Confirms post pain (validation)
- ✅ Provides workaround (tool Y)
- ✅ Quantifies improvement (200ms → 50ms)

**Result**: Reinforces pain event, adds competitive intelligence

### Example 3: Comment Reveals Hidden Pain

**Post**: "How do you manage your finances?"

**Comment** (2,000 upvotes):
> "I'm struggling with debt from my failed startup. The monthly payments are killing me and I can't afford to save. Feeling pretty hopeless about ever getting ahead."

**Analysis**:
- ✅ Post is neutral (how-to question)
- ✅ Comment reveals strong emotional pain
- ✅ Specific context: startup debt, monthly payments
- ✅ Emotional signal: "struggling", "killing me", "hopeless"

**Result**: Captures pain that post filtering would miss
