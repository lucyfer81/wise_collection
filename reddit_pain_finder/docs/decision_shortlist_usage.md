# Decision Shortlist Usage Guide

## Overview

The Decision Shortlist feature analyzes all scored opportunities and selects the Top 3-5 most promising product ideas for solo developers. It combines multiple signals including viability score, cluster size, trust level, and cross-source validation to create a final ranking.

## Quick Start

### Run as part of full pipeline

```bash
python3 run_pipeline.py --stage all
```

### Run as standalone stage

```bash
python3 run_pipeline.py --stage decision_shortlist
```

### Run programmatically

```python
from pipeline.decision_shortlist import DecisionShortlistGenerator

generator = DecisionShortlistGenerator()
result = generator.generate_shortlist()

print(f"Generated {result['shortlist_count']} candidates")
print(f"Markdown report: {result['markdown_report']}")
print(f"JSON report: {result['json_report']}")
```

## Configuration

Configuration is stored in `config/thresholds.yaml` under the `decision_shortlist` section:

```yaml
decision_shortlist:
  # 硬性过滤阈值
  min_viability_score: 7.0      # Minimum viability score (0-10)
  min_cluster_size: 6           # Minimum cluster size
  min_trust_level: 0.7          # Minimum trust level (0-1)
  ignored_clusters: []          # Clusters to ignore (optional)

  # 最终评分权重
  final_score_weights:
    viability_score: 1.0            # Viability score weight
    cluster_size_log_factor: 2.5    # Logarithmic cluster size weight
    trust_level: 1.5                # Trust level weight
    cross_source_bonus: 5.0         # Cross-source validation bonus

  # 输出控制
  output:
    min_candidates: 3           # Minimum candidates to select
    max_candidates: 5           # Maximum candidates to select
    markdown_dir: 'reports'    # Markdown report directory
    json_dir: 'data'           # JSON report directory
```

## How It Works

### Step 1: Hard Filters

Only opportunities meeting ALL these criteria are considered:

- **Viability Score** ≥ 7.0 (out of 10)
- **Cluster Size** ≥ 6 pain events
- **Trust Level** ≥ 0.7 (out of 1.0)
- **Not in ignored_clusters** list

### Step 2: Cross-Source Validation

Three validation levels provide confidence signals:

| Level | Criteria | Boost Score | Validated Problem |
|-------|----------|-------------|-------------------|
| **Level 1** (Strong) | source_type='aligned' OR in aligned_problems table | 2.0 | Yes |
| **Level 2** (Medium) | cluster_size ≥ 10 AND ≥ 3 subreddits | 1.0 | Yes |
| **Level 3** (Weak) | cluster_size ≥ 8 AND ≥ 2 subreddits | 0.5 | No |
| **Level 0** (None) | Below Level 3 thresholds | 0.0 | No |

### Step 3: Final Score Calculation

Uses logarithmic scaling to prevent large clusters from dominating:

```
final_score = (
    viability_score × 1.0 +
    log10(cluster_size) × 2.5 +
    trust_level × 1.5
)

if has_cross_source:
    final_score += cross_source_bonus × boost_score × 0.1

final_score = clamp(final_score, 0, 10)  # Cap at 10.0
```

**Example:**
- viability_score = 8.0
- cluster_size = 50 (log10 ≈ 1.7)
- trust_level = 0.8
- cross-source boost = 2.0

```
final_score = 8.0×1.0 + 1.7×2.5 + 0.8×1.5 + 5.0×2.0×0.1
            = 8.0 + 4.25 + 1.2 + 1.0
            = 14.45 → capped at 10.0
```

### Step 4: Candidate Selection

Top candidates are selected based on final_score (descending). By default, returns 3-5 candidates.

### Step 5: Readable Content Generation

Uses LLM (GPT-4o-mini) to generate:
- **Problem**: Clear pain point description
- **MVP**: Minimum viable product solution
- **Why Now**: Market timing justification

If LLM fails, falls back to template-based generation.

### Step 6: Export Reports

Two report formats are generated:

1. **Markdown Report** (`reports/decision_shortlist_YYYYMMDD_HHMMSS.md`)
   - Human-readable format
   - Includes all details for each candidate
   - Perfect for stakeholder review

2. **JSON Report** (`data/decision_shortlist_YYYYMMDD_HHMMSS.json`)
   - Machine-readable format
   - Structured data for further processing
   - Includes all metadata

## Output Format

### Markdown Report Structure

```markdown
# Decision Shortlist Report

**Generated**: 2025-12-26 12:34:56
**Total Candidates**: 3

---

## 1. Auto Task Tool

**Final Score**: 10.00/10.0
**Viability Score**: 8.5
**Cluster Size**: 10
**Trust Level**: 0.85
**Cross-Source Validation**: ✅ Yes
**Validation Level**: 2 (Large cluster (10) across 3 subreddits)

### Problem
Users are spending too much time on repetitive data transformation tasks...

### MVP Solution
Build a web-based tool that automates common data transformations...

### Why Now
Remote work has increased manual data handling...
```

### JSON Report Structure

```json
{
  "generated_at": "2025-12-26T12:34:56",
  "total_candidates": 3,
  "candidates": [
    {
      "opportunity_name": "Auto Task Tool",
      "final_score": 10.0,
      "viability_score": 8.5,
      "cluster_size": 10,
      "trust_level": 0.85,
      "target_users": "Data analysts",
      "missing_capability": "Automation",
      "why_existing_fail": "Too manual",
      "readable_content": {
        "problem": "...",
        "mvp": "...",
        "why_now": "..."
      },
      "cross_source_validation": {
        "has_cross_source": true,
        "validation_level": 2,
        "boost_score": 1.0,
        "validated_problem": true,
        "evidence": "Large cluster (10) across 3 subreddits"
      }
    }
  ]
}
```

## Customization

### Adjust Filtering Thresholds

Edit `config/thresholds.yaml`:

```yaml
decision_shortlist:
  min_viability_score: 8.0  # Raise for stricter filtering
  min_cluster_size: 10      # Require larger clusters
```

### Adjust Scoring Weights

Change how factors contribute to final score:

```yaml
decision_shortlist:
  final_score_weights:
    viability_score: 1.5        # Increase importance
    cluster_size_log_factor: 1.0  # Decrease importance
```

### Adjust Output Count

```yaml
decision_shortlist:
  output:
    min_candidates: 5  # Get more options
    max_candidates: 10
```

### Ignore Specific Clusters

```yaml
decision_shortlist:
  ignored_clusters:
    - "spam_cluster"
    - "low_quality_cluster"
```

## FAQ

**Q: Why use logarithmic scaling for cluster size?**

A: Large clusters (100+ events) shouldn't dominate the score. log10 ensures diminishing returns: the difference between 10 and 100 events is the same as 100 and 1000.

**Q: Can I run decision shortlist without completing earlier pipeline stages?**

A: No, decision shortlist requires:
- Opportunities with viability scores (Stage 7)
- Clusters with pain events (Stage 5)
- Optional: Cross-source alignment (Stage 5.5)

**Q: How accurate is the LLM-generated content?**

A: GPT-4o-mini provides good quality for most cases. If you need higher accuracy, you can:
1. Switch to GPT-4o (edit the `model` parameter in `_generate_readable_content`)
2. Provide a custom prompt (override `_get_default_prompt`)
3. Manually review and edit the markdown report

**Q: What if no opportunities pass the filters?**

A: The generator returns an empty shortlist with a warning. You can:
1. Lower the filter thresholds in config
2. Run more data collection to increase opportunities
3. Check if earlier pipeline stages completed successfully

**Q: Can I integrate this into my own workflow?**

A: Yes! The JSON output is designed for programmatic consumption:

```python
import json

# Load the latest shortlist
with open('data/decision_shortlist_20251226_123456.json') as f:
    data = json.load(f)

# Process candidates
for candidate in data['candidates']:
    if candidate['final_score'] > 8.0:
        print(f"High-priority: {candidate['opportunity_name']}")
```

## Troubleshooting

### Issue: "No opportunities passed hard filters"

**Solution:** Check your database has opportunities with sufficient scores:

```bash
sqlite3 data/wise_collection.db "SELECT opportunity_name, total_score FROM opportunities ORDER BY total_score DESC LIMIT 10"
```

### Issue: LLM content generation fails

**Solution:** Check your API key and rate limits:

```bash
export OPENAI_API_KEY="your-key-here"
```

The system will fall back to template-based content if LLM fails.

### Issue: "Module not found: pipeline.decision_shortlist"

**Solution:** Ensure you're running from the project root directory:

```bash
cd /home/ubuntu/PyProjects/wise_collection/reddit_pain_finder
python3 run_pipeline.py --stage decision_shortlist
```

## Testing

Run the Milestone 1 acceptance test:

```bash
python3 tests/test_decision_shortlist_milestone1.py
```

This will validate:
- Output count (3-5 candidates)
- Candidate completeness (problem, mvp, why_now fields)
- File generation (markdown + JSON)
- JSON format validation

## Performance

Typical execution time (with 20-50 scored opportunities):
- Filtering & scoring: < 1 second
- Cross-source validation: 1-2 seconds
- LLM content generation: 5-10 seconds (3-5 candidates)
- **Total**: ~10-15 seconds

Cost (GPT-4o-mini):
- ~500 tokens per candidate
- ~2500 tokens total for 5 candidates
- **Est. cost**: $0.0025 per run

## Next Steps

After generating the shortlist:
1. Review the markdown report
2. Validate findings with user research
3. Prioritize based on your skills and market fit
4. Start building the MVP!

For questions or issues, please refer to the main project documentation.
