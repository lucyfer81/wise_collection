# Phase 3: Pipeline Integration Plan for Comment Extraction

> **IMPORTANT**: This plan must be approved by the user before implementation.

**Goal:** Integrate comment pain extraction into the main pipeline (`run_pipeline.py`), making it a first-class citizen alongside post extraction.

**Architecture:** Follow the established pattern from Phase 1 (comment filtering), where comments are processed in parallel with posts within the same pipeline stage.

**Current State Analysis:**

### What's Already Built (Phase 2 ✅)
- ✅ `process_unextracted_comments()` method exists in `pipeline/extract_pain.py` (line 422)
- ✅ `_extract_from_single_comment()` method exists (line 88)
- ✅ Database migration complete (source_type, source_id, parent_post_id)
- ✅ Database methods: `get_all_filtered_comments()`, `get_parent_post_context()`
- ✅ LLM client supports comment-aware extraction via `metadata` parameter
- ✅ Standalone script works: `scripts/extract_pain_from_comments.py`

### What's Missing (This Plan)
- ❌ `run_stage_extract()` doesn't call `process_unextracted_comments()`
- ❌ No `--include-comments-extract` CLI flag
- ❌ Statistics don't distinguish between post/comment extraction
- ❌ No unified reporting for both sources

### Current Pipeline Architecture

**Stage 2 (Filter) - Already Supports Comments:**
```python
def run_stage_filter(self, limit_posts=None, process_all=False, include_comments=False):
    # Process posts (existing)
    unfiltered_posts = db.get_unprocessed_posts(limit=limit_posts)
    filtered_posts = filter.filter_posts_batch(unfiltered_posts)

    # Process comments (Phase 1: Include Comments) ✅
    if include_comments:
        unfiltered_comments = db.get_all_comments_for_filtering()
        filtered_comments = filter.filter_comments_batch(unfiltered_comments)
        db.save_filtered_comments(filtered_comments)
```

**Stage 3 (Extract) - Currently Posts Only:**
```python
def run_stage_extract(self, limit_posts=None, process_all=False):
    # Process posts (existing)
    extractor = PainPointExtractor()
    result = extractor.process_unextracted_posts(limit=limit_posts)

    # ❌ MISSING: Comment extraction
```

---

## Integration Plan

### Option A: Minimal Integration (Recommended) ⭐

**Approach:** Add comment extraction to `run_stage_extract()`, following the exact same pattern as Stage 2 (Filter).

**Changes Required:**

#### 1. Update `run_stage_extract()` method in `run_pipeline.py`

**Location:** Lines 298-332

**Current code:**
```python
def run_stage_extract(self, limit_posts: Optional[int] = None, process_all: bool = False) -> Dict[str, Any]:
    """阶段3: 痛点抽取"""
    extractor = PainPointExtractor()
    result = extractor.process_unextracted_posts(limit=limit_posts)
    # ... rest of method
```

**Updated code:**
```python
def run_stage_extract(
    self,
    limit_posts: Optional[int] = None,
    process_all: bool = False,
    include_comments: bool = False,  # NEW: Phase 3 parameter
    comment_limit: Optional[int] = None  # NEW: Separate limit for comments
) -> Dict[str, Any]:
    """阶段3: 痛点抽取 (Posts + Comments)

    Args:
        limit_posts: 限制处理帖子数量
        process_all: 处理所有未过滤数据
        include_comments: 是否抽取comments（Phase 3: Include Comments）
        comment_limit: 限制处理评论数量（独立于limit_posts）
    """
    logger.info("=" * 50)
    logger.info("STAGE 3: Extracting pain points")
    if include_comments:
        logger.info("Including comments in extraction (experimental)")
    logger.info("=" * 50)

    if self.enable_monitoring:
        performance_monitor.start_stage("extract")

    try:
        extractor = PainPointExtractor()

        # ============ 处理Posts ============
        # 如果 process_all=True 且未指定 limit，则处理所有数据
        if process_all and limit_posts is None:
            limit_posts = 1000000  # 处理所有数据
        elif limit_posts is None:
            limit_posts = 100

        post_result = extractor.process_unextracted_posts(limit=limit_posts)

        logger.info(f"✅ Posts: Extracted {post_result.get('pain_events_saved', 0)} pain events")

        # ============ 处理Comments（Phase 3: Include Comments）============
        comment_result = {"processed": 0, "pain_events_saved": 0}
        if include_comments:
            logger.info("")
            logger.info("Processing comments...")

            # 重置统计
            extractor.stats = {
                "total_processed": 0,
                "total_pain_events": 0,
                "extraction_errors": 0,
                "avg_confidence": 0.0,
                "processing_time": 0.0
            }

            # 使用独立的limit参数，或默认处理所有过滤的评论
            if process_all and comment_limit is None:
                comment_limit = 1000000
            elif comment_limit is None:
                comment_limit = 1000000  # 默认处理所有（因为已经过滤过）

            comment_result = extractor.process_unextracted_comments(limit=comment_limit)

            logger.info(f"✅ Comments: Extracted {comment_result.get('pain_events_saved', 0)} pain events")

        # ============ 合并结果 ============
        result = {
            "posts": post_result,
            "comments": comment_result if include_comments else None,
            "include_comments": include_comments,
            "total_events": (
                post_result.get('pain_events_saved', 0) +
                comment_result.get('pain_events_saved', 0)
            ) if include_comments else post_result.get('pain_events_saved', 0)
        }

        self.stats["stages_completed"].append("extract")
        self.stats["stage_results"]["extract"] = result

        if self.enable_monitoring:
            events_saved = result.get('total_events', 0)
            performance_monitor.end_stage("extract", events_saved)

        # 输出总结
        logger.info("")
        logger.info("=" * 50)
        logger.info("Extract Stage Summary")
        logger.info("=" * 50)
        logger.info(f"Posts:    {post_result.get('pain_events_saved', 0)} events")
        if include_comments:
            logger.info(f"Comments: {comment_result.get('pain_events_saved', 0)} events")
        logger.info(f"Total:    {result.get('total_events', 0)} events")
        logger.info("=" * 50)

        return result

    except Exception as e:
        logger.error(f"❌ Stage 3 failed: {e}")
        self.stats["stages_failed"].append("extract")
        if self.enable_monitoring:
            performance_monitor.end_stage("extract", 0)
        raise
```

#### 2. Update CLI argument parsing

**Location:** Lines 996-1037 (main function)

**Add new argument:**
```python
# Comment extraction options（Phase 3: Include Comments）
parser.add_argument("--include-comments-extract", action="store_true",
                   help="Include comments in extract stage (experimental)")
parser.add_argument("--limit-comments-extract", type=int,
                   help="Limit number of comments to extract (default: all filtered comments)")
```

#### 3. Update `run_full_pipeline()` to pass the new parameter

**Location:** Lines 663-738

**Update stage definition:**
```python
stages = [
    ("fetch", lambda: self.run_stage_fetch(limit_sources, fetch_sources)),
    ("filter", lambda: self.run_stage_filter(limit_posts, process_all, include_comments)),
    ("extract", lambda: self.run_stage_extract(
        limit_posts,
        process_all,
        include_comments_extract,  # NEW
        kwargs.get("limit_comments_extract")  # NEW
    )),
    # ... other stages
]
```

#### 4. Update `run_single_stage()` to pass the new parameter

**Location:** Lines 739-760

**Update stage mapping:**
```python
stage_map = {
    # ... other stages
    "extract": lambda: self.run_stage_extract(
        kwargs.get("limit_posts"),
        process_all,
        kwargs.get("include_comments_extract", False),  # NEW
        kwargs.get("limit_comments_extract")  # NEW
    ),
    # ... other stages
}
```

---

### Option B: Unified Source-Aware Extraction (Advanced)

**Approach:** Create a single method that processes both posts and comments, treating them uniformly as "pain sources".

**Pros:**
- Cleaner code (DRY principle)
- Easier to add new sources in future (HN comments, tweets, etc.)
- Unified statistics and error handling

**Cons:**
- More complex refactoring
- Higher risk of breaking existing functionality
- Requires changes to `PainPointExtractor` class structure

**Implementation Sketch:**
```python
def run_stage_extract(self, sources=None, **kwargs):
    """Extract pain from multiple sources (posts, comments, etc.)"""
    extractor = PainPointExtractor()

    results = {}
    for source in (sources or ['posts', 'comments']):
        if source == 'posts':
            results['posts'] = extractor.process_unextracted_posts(**kwargs)
        elif source == 'comments':
            results['comments'] = extractor.process_unextracted_comments(**kwargs)

    return results
```

**Recommendation:** Start with Option A (Minimal Integration), consider Option B for Phase 4.

---

## Usage Examples (After Integration)

### Example 1: Extract from posts only (existing behavior)
```bash
python3 run_pipeline.py --stage extract
# or
python3 run_pipeline.py --stage extract --limit-posts 100
```

### Example 2: Extract from both posts and comments
```bash
python3 run_pipeline.py --stage extract --include-comments-extract
```

### Example 3: Extract from comments only
```bash
python3 run_pipeline.py --stage extract --include-comments-extract --limit-posts 0
```

### Example 4: Full pipeline with comments
```bash
# Filter comments + Extract from both posts and comments
python3 run_pipeline.py \
  --stage filter \
  --include-comments \
  --stage extract \
  --include-comments-extract \
  --process-all
```

### Example 5: Complete pipeline with comments (one command)
```bash
python3 run_pipeline.py \
  --all \
  --include-comments \
  --include-comments-extract \
  --process-all
```

---

## Testing Plan

### Test 1: Extract stage only (posts)
```bash
python3 run_pipeline.py --stage extract --limit-posts 10
```
**Expected:** Works exactly as before (backward compatibility)

### Test 2: Extract stage with comments (small batch)
```bash
python3 run_pipeline.py --stage extract --include-comments-extract --limit-comments-extract 10
```
**Expected:**
- Processes 10 filtered comments
- Extracts ~30-40 pain events
- Displays unified statistics

### Test 3: Full pipeline with comments
```bash
python3 run_pipeline.py --all --include-comments --include-comments-extract --limit-posts 50 --limit-comments-extract 50
```
**Expected:**
- Stage 2 (Filter): Filters both posts and comments
- Stage 3 (Extract): Extracts from both posts and comments
- Stage 4+ (Embed/Cluster/etc.): Processes all pain events uniformly

### Test 4: Verify database
```bash
sqlite3 data/wise_collection.db <<EOF
-- Count by source type
SELECT source_type, COUNT(*) as count
FROM pain_events
GROUP BY source_type;

-- Sample recent comment events
SELECT problem, source_type, extraction_confidence
FROM pain_events
WHERE source_type = 'comment'
ORDER BY extracted_at DESC
LIMIT 5;
EOF
```

---

## Impact Analysis

### Files to Modify
- `run_pipeline.py` (main integration)
  - `run_stage_extract()` method
  - `run_full_pipeline()` method
  - `run_single_stage()` method
  - `main()` function (CLI args)

### Files to Test
- `pipeline/extract_pain.py` (already has the methods)
- `utils/db.py` (already has the methods)
- `utils/llm_client.py` (already supports comments)

### Backward Compatibility
✅ **100% Backward Compatible**
- Default behavior unchanged (`include_comments_extract=False`)
- Existing scripts and commands work as-is
- New parameter is opt-in

### Performance Impact
- **Filter Stage:** +20-30 seconds for 3,656 comments (already done in Phase 1)
- **Extract Stage:** +52 hours for 3,656 comments (can be batched)
- **Embed/Cluster Stages:** +10-20% processing time for ~12k additional events

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing pipeline | **HIGH** | ✅ Default parameter = False (opt-in) |
| Performance degradation | **MEDIUM** | ✅ Independent limits for posts/comments |
| Database lock contention | **LOW** | ✅ Sequential processing (not parallel) |
| LLM API rate limits | **LOW** | ✅ Existing retry logic handles this |
| Poor quality comment extractions | **LOW** | ✅ Already tested in Phase 2 (89% confidence) |

**Overall Risk Level:** **LOW** ✅

---

## Success Criteria

### Integration Success
- [ ] `run_stage_extract()` accepts `include_comments` parameter
- [ ] CLI flag `--include-comments-extract` works
- [ ] Comment extraction runs via pipeline
- [ ] Statistics distinguish between post/comment sources
- [ ] Backward compatibility maintained

### Functional Success
- [ ] Can extract from posts only (existing behavior)
- [ ] Can extract from comments only
- [ ] Can extract from both simultaneously
- [ ] Results saved with correct `source_type`
- [ ] Downstream stages (embed/cluster) work with comment events

---

## Next Steps (After Approval)

1. **Implement Option A (Minimal Integration)**
   - Modify `run_pipeline.py` with changes above
   - Test each change incrementally
   - Run Test 1-4 from testing plan

2. **Update Documentation**
   - Update README.md with new flag
   - Update Phase 2 completion checklist
   - Create Phase 3 summary

3. **Validation Run**
   - Run full pipeline with 100 posts + 100 comments
   - Verify all stages work correctly
   - Check quality of final opportunities

---

## Estimated Implementation Time

- **Coding:** 1-2 hours (4 methods to modify)
- **Testing:** 1 hour (4 test scenarios)
- **Documentation:** 30 minutes
- **Total:** 2.5-3.5 hours

---

## Alternative: Keep Standalone Script

If pipeline integration is deemed too complex, **Phase 2 is already complete and production-ready** with the standalone script:

```bash
# Filter stage (via pipeline)
python3 run_pipeline.py --stage filter --include-comments --process-all

# Extract stage (via standalone script)
python3 scripts/extract_pain_from_comments.py --limit 3656

# Continue with pipeline
python3 run_pipeline.py --stage embed --process-all
python3 run_pipeline.py --stage cluster --process-all
# ... etc
```

**Pros:**
- Zero risk to existing pipeline
- Clear separation of concerns
- Easier to debug and maintain

**Cons:**
- More manual steps
- Less integrated experience
- Harder to automate end-to-end

---

## Recommendation

**Recommended Approach:** **Option A (Minimal Integration)**

**Reasoning:**
1. Follows established pattern from Phase 1 (comment filtering)
2. Low risk (opt-in parameter)
3. Maintains backward compatibility
4. Clean, understandable code
5. Enables full automation of the pipeline

**When to Implement:**
- After user approval of this plan
- In a dedicated branch (can continue in `feat-includeComment-p2`)
- After creating backup of current working state

---

**Plan ready for user review and approval.**

**Question for user:**
1. Do you approve Option A (Minimal Integration)?
2. Or would you prefer Option B (Unified Source-Aware Extraction)?
3. Or would you rather keep using the standalone script?
4. Any specific concerns or requirements not addressed in this plan?
