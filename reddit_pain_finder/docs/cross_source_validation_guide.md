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
- `aligned_problems`: Unified problems after LLM detects cross-source alignment

Each `aligned_problem` links to 2+ original `clusters` via `cluster_ids` field.

---

## Technical Implementation

### Database Schema

#### `aligned_problems` table

```sql
CREATE TABLE aligned_problems (
    id TEXT PRIMARY KEY,              -- aligned_ap_XX_timestamp
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
- **Database Queries**: `utils/db.py` (lines 1312-1494)
- **CLI Tool**: `scripts/show_cross_source_pain_points.py`

---

## The Strategic Question

**"现阶段世界上'被不同社群独立提及'的痛点有哪些？"**

Now you can answer this in seconds:

```bash
python scripts/show_cross_source_pain_points.py --min-level 1
```

This gives you a prioritized list of pain points validated across Reddit and Hacker News - your **opportunity radar** for product discovery.
