# Trust Level & Soft Judgment System

## Overview

The Trust Level & Soft Judgment system transforms the pain point discovery pipeline from discrete boolean judgments to continuous float scores (0.0-1.0). This provides:

1. **Stability**: LLM outputs vary continuously rather than flipping between true/false
2. **Traceability**: All decisions are based on explicit, stored scores
3. **Flexibility**: Thresholds can be tuned without re-running the pipeline

## Key Components

### 1. Trust Level (Source Quality)

Posts from different sources have different `trust_level` values:

| Category | Trust Level | Description |
|----------|-------------|-------------|
| `core` | 0.9 | High-quality SaaS/founder communities |
| `secondary` | 0.7 | Complementary startup discussions |
| `verticals` | 0.6 | Industry-specific communities |
| `experimental` | 0.4 | Lower signal-to-noise sources |
| Hacker News | 0.8 | High-quality technical discussions |

### 2. Workflow Similarity (Cluster Validation)

Instead of asking "Are these the same workflow? (yes/no)", the LLM rates similarity from 0.0-1.0:

- **0.0-0.3**: Different workflows
- **0.3-0.5**: Some vague similarity
- **0.5-0.7**: Partially similar
- **0.7-0.9**: Strong similarity
- **0.9-1.0**: Nearly identical

**Threshold**: `WORKFLOW_SIMILARITY_THRESHOLD = 0.7` in `pipeline/cluster.py`

### 3. Alignment Score (Cross-Source Matching)

Cross-source alignments are scored 0.0-1.0:

- **< 0.6**: Not aligned (not stored)
- **0.6-0.7**: Weak alignment
- **0.7-0.85**: Good alignment
- **0.85-1.0**: Strong alignment

**Threshold**: `ALIGNMENT_SCORE_THRESHOLD = 0.7` in `pipeline/align_cross_sources.py`

## Database Schema Changes

### posts table
- **New column**: `trust_level REAL DEFAULT 0.5`
- Stores source quality rating for each post

### clusters table
- **New column**: `workflow_similarity REAL DEFAULT 0.0`
- Stores continuous similarity score from LLM validation

### aligned_problems table
- **New column**: `alignment_score REAL DEFAULT 0.0`
- Stores continuous alignment confidence score

## Configuration

### config/subreddits.yaml

Each category now has a `trust_level`:

```yaml
core:
  trust_level: 0.9
  SideProject:
    min_upvotes: 5
    min_comments: 3
    # ...
```

### Hardcoded Thresholds

Thresholds are defined as constants in pipeline modules:

```python
# pipeline/cluster.py
WORKFLOW_SIMILARITY_THRESHOLD = 0.7

# pipeline/align_cross_sources.py
ALIGNMENT_SCORE_THRESHOLD = 0.7
```

## Usage

### Running the Pipeline

The pipeline automatically uses the soft judgment system:

```bash
# Fetch posts (trust_level automatically assigned)
python -m pipeline.fetch

# Cluster (uses workflow_similarity scoring)
python -m pipeline.cluster

# Cross-source align (uses alignment_score)
python -m pipeline.align_cross_sources
```

### Migrating Existing Data

For existing installations, run the migration script:

```bash
python scripts/migrate_to_soft_judgment.py
```

### Verification

Run tests to verify the implementation:

```bash
python tests/test_trust_level_soft_judgment.py
```

### Viewing Score Statistics

```python
from utils.db import db
import json

stats = db.get_score_statistics()
print(json.dumps(stats, indent=2))
```

## Expected Behavior

### Stability Improvement

**Before** (Boolean):
- Run 1: `same_workflow: true` -> Cluster created
- Run 2: `same_workflow: false` -> Cluster rejected
- Result: Unstable!

**After** (Float):
- Run 1: `workflow_similarity: 0.75` -> Cluster created
- Run 2: `workflow_similarity: 0.78` -> Cluster created
- Run 3: `workflow_similarity: 0.72` -> Cluster created
- Result: Stable within threshold!

### Score Distribution

After running the pipeline on real data, you should see:
- Most `workflow_similarity` scores: 0.3-0.9 range
- Most `alignment_score` scores: 0.6-0.95 range (below threshold filtered)
- `trust_level` distribution matches your source categories

## Troubleshooting

### Scores are all 0.0

Check:
1. LLM prompt is requesting `workflow_similarity` not `same_workflow`
2. Response parsing is extracting the float correctly
3. Database schema has the new columns

### Thresholds not working

Check:
1. Constants are defined in the pipeline modules
2. Code is using `>= threshold` for comparison
3. Scores are being saved before threshold check

### Migration issues

```bash
# Check database schema
sqlite3 data/wise_collection.db "PRAGMA table_info(posts);"
sqlite3 data/wise_collection.db "PRAGMA table_info(clusters);"
```

## Tuning Thresholds

If you want to adjust sensitivity:

1. Edit the threshold constants in pipeline files
2. Higher threshold = more conservative (fewer clusters/alignments)
3. Lower threshold = more permissive (more clusters/alignments)

No need to re-fetch or re-cluster - just re-run the decision logic with new thresholds.
