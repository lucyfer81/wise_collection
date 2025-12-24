# Trust Level & Soft Judgment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the pipeline from discrete boolean judgments to continuous float scores (0.0-1.0) with source trust levels to fundamentally solve system instability.

**Architecture:** Replace all boolean LLM outputs with float scores, add trust_level to posts based on their source category, use hardcoded thresholds for decision-making.

**Tech Stack:** Python, SQLite, YAML configuration, LLM prompts

---

## Overview

This plan implements a "soft judgment" mechanism that changes:
- Boolean outputs (`true`/`false`) → Float scores (`0.0`-`1.0`)
- Source-based trust levels for all posts
- Hardcoded, traceable thresholds for decision logic

---

## Task 1: Update Configuration File with Trust Levels

**Files:**
- Modify: `config/subreddits.yaml`

**Step 1: Add trust_level field to all categories**

Edit `config/subreddits.yaml` to add `trust_level` to each category:

```yaml
# =========================
# Core: 必抓（高痛点密度）
# =========================
core:
  trust_level: 0.9
  SideProject:
    min_upvotes: 5
    min_comments: 3
    # ... rest unchanged

  solopreneur:
    trust_level: 0.9  # Inherit from category if not set per-subreddit
    min_upvotes: 3
    min_comments: 2
    # ... rest unchanged

  SaaS:
    min_upvotes: 5
    min_comments: 5
    # ... rest unchanged

# =========================
# Secondary: 补充视角
# =========================
secondary:
  trust_level: 0.7
  IndieHackers:
    min_upvotes: 5
    min_comments: 3
    # ... rest unchanged

  startups:
    min_upvotes: 10
    min_comments: 5
    # ... rest unchanged

  Entrepreneur:
    min_upvotes: 15
    min_comments: 10
    # ... rest unchanged

# =========================
# Vertical:
# =========================
verticals:
  trust_level: 0.6
  freelance:
    min_upvotes: 5
    min_comments: 3
    # ... rest unchanged

  consulting:
    min_upvotes: 5
    min_comments: 3
    # ... rest unchanged

  contentcreators:
    min_upvotes: 10
    min_comments: 5
    # ... rest unchanged

# =========================
# Experimental: 低频探索
# =========================
experimental:
  trust_level: 0.4
  devops:
    min_upvotes: 10
    min_comments: 5
    # ... rest unchanged

  marketing:
    min_upvotes: 10
    min_comments: 5
    # ... rest unchanged
```

**Step 2: Verify YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('config/subreddits.yaml'))"`
Expected: No errors, YAML parses correctly

**Step 3: Commit**

```bash
git add config/subreddits.yaml
git commit -m "feat: add trust_level to all categories in subreddits.yaml"
```

---

## Task 2: Add trust_level Column to Database Schema

**Files:**
- Modify: `utils/db.py`

**Step 1: Add trust_level column to posts table in _init_unified_database**

Locate `def _init_unified_database(self)` in `utils/db.py` (around line 85). Find the `posts` table creation and add the `trust_level` column:

```python
# Create this in the CREATE TABLE posts statement (after line 108, before UNIQUE constraint):
trust_level REAL DEFAULT 0.5,
```

The full table definition should be:

```python
conn.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        body TEXT,
        subreddit TEXT,
        url TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'reddit',
        source_id TEXT NOT NULL,
        platform_data TEXT,
        score INTEGER NOT NULL,
        num_comments INTEGER NOT NULL,
        upvote_ratio REAL,
        is_self INTEGER,
        created_utc REAL NOT NULL,
        created_at TIMESTAMP NOT NULL,
        author TEXT,
        category TEXT,
        trust_level REAL DEFAULT 0.5,
        collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        raw_data TEXT,
        UNIQUE(source, source_id)
    )
""")
```

**Step 2: Add trust_level column to _init_raw_posts_db**

Similarly, update the posts table creation in `def _init_raw_posts_db(self)` (around line 259) with the same `trust_level REAL DEFAULT 0.5,` line.

**Step 3: Add database migration for existing databases**

Add a new method after `_add_alignment_columns_to_clusters`:

```python
def _add_trust_level_column(self, conn):
    """Add trust_level column to posts table if not exists"""
    try:
        cursor = conn.execute("PRAGMA table_info(posts)")
        existing_columns = {row['name'] for row in cursor.fetchall()}

        if 'trust_level' not in existing_columns:
            conn.execute("""
                ALTER TABLE posts
                ADD COLUMN trust_level REAL DEFAULT 0.5
            """)
            logger.info("Added trust_level column to posts table")

            # Migrate existing data: set trust_level based on category
            category_trust_levels = {
                'core': 0.9,
                'secondary': 0.7,
                'verticals': 0.6,
                'experimental': 0.4
            }

            for category, level in category_trust_levels.items():
                conn.execute("""
                    UPDATE posts
                    SET trust_level = ?
                    WHERE category = ?
                """, (level, category))

            logger.info("Migrated trust_level for existing posts")

    except Exception as e:
        logger.error(f"Failed to add trust_level column: {e}")
```

**Step 4: Call the migration in _init_databases**

Update `def _init_databases(self)` to call the migration:

```python
def _init_databases(self):
    """Initialize all database schemas"""
    if self.unified:
        self._init_unified_database()
        # Migrate trust_level
        with self.get_connection("raw") as conn:
            self._add_trust_level_column(conn)
    else:
        self._init_raw_posts_db()
        self._init_filtered_posts_db()
        self._init_pain_events_db()
        self._init_clusters_db()
        # Migrate trust_level for raw posts
        with self.get_connection("raw") as conn:
            self._add_trust_level_column(conn)
```

**Step 5: Update insert_raw_post to include trust_level**

Modify `def insert_raw_post(self, post_data: Dict[str, Any])` (around line 468):

```python
def insert_raw_post(self, post_data: Dict[str, Any]) -> bool:
    """Insert raw post data with trust_level support"""
    try:
        with self.get_connection("raw") as conn:
            conn.execute("""
                INSERT OR REPLACE INTO posts
                (id, title, body, subreddit, url, source, source_id, platform_data,
                 score, num_comments, upvote_ratio, is_self, created_utc, created_at,
                 author, category, trust_level, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                post_data.get("id"),
                post_data["title"],
                post_data.get("body", ""),
                post_data.get("subreddit", "unknown"),
                post_data["url"],
                post_data.get("source", "reddit"),
                post_data.get("source_id"),
                json.dumps(post_data.get("platform_data", {})),
                post_data["score"],
                post_data["num_comments"],
                post_data.get("upvote_ratio"),
                post_data.get("is_self"),
                post_data.get("created_utc", 0),
                post_data.get("created_at", datetime.now().isoformat()),
                post_data.get("author", ""),
                post_data.get("category", ""),
                post_data.get("trust_level", 0.5),  # New field
                json.dumps(post_data)
            ))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Failed to insert raw post {post_data.get('id')}: {e}")
        return False
```

**Step 6: Test database migration**

Run: `python -c "from utils.db import db; print('Database initialized'); print(db.get_statistics())"`
Expected: No errors, trust_level column exists

**Step 7: Commit**

```bash
git add utils/db.py
git commit -m "feat: add trust_level column to posts table with migration"
```

---

## Task 3: Update Fetch Pipeline to Store Trust Level

**Files:**
- Modify: `pipeline/fetch.py`
- Modify: `pipeline/hn_fetch.py` (if exists)

**Step 1: Add trust_level helper to RedditSourceFetcher**

Add this method to the `RedditSourceFetcher` class (around line 40, after `__init__`):

```python
def _get_trust_level_for_category(self, category: str) -> float:
    """Get trust level for a category from config"""
    try:
        # Get the category config
        category_config = self.config.get(category, {})
        if isinstance(category_config, dict):
            trust_level = category_config.get("trust_level")
            if trust_level is not None:
                return float(trust_level)

        # Default fallback levels
        default_levels = {
            'core': 0.9,
            'secondary': 0.7,
            'verticals': 0.6,
            'experimental': 0.4
        }
        return default_levels.get(category, 0.5)

    except Exception as e:
        logger.warning(f"Failed to get trust_level for {category}: {e}, using default 0.5")
        return 0.5
```

**Step 2: Update _extract_post_data to include trust_level**

Modify `def _extract_post_data(self, submission, subreddit_config)` (around line 216). Add trust_level to the return dict:

Find the return statement (around line 251) and add:
```python
"trust_level": self._get_trust_level_for_category(subreddit_config["category"]),
```

The return dict should include:
```python
return {
    "id": unified_id,
    "source": "reddit",
    "source_id": reddit_source_id,
    # ... existing fields ...
    "pain_score": pain_score,
    "trust_level": self._get_trust_level_for_category(subreddit_config["category"]),  # NEW
    "collected_at": datetime.now().isoformat()
}
```

**Step 3: Update HackerNewsSourceFetcher to use trust_level**

If `pipeline/hn_fetch.py` exists, similarly add a `trust_level` field. HN posts should have a default trust level of 0.8 (high quality technical discussions).

In the `_extract_post_data` or equivalent method in `hn_fetch.py`, add:
```python
"trust_level": 0.8,  # HN has high-quality technical discussions
```

**Step 4: Test trust_level is stored correctly**

Run a test fetch:
```bash
python -m pipeline.fetch --limit 1
```

Then verify in database:
```bash
python -c "from utils.db import db; import sqlite3; conn = sqlite3.connect('data/wise_collection.db'); cursor = conn.execute('SELECT id, title, trust_level FROM posts LIMIT 5'); print([dict(row) for row in cursor.fetchall()])"
```
Expected: Posts should have trust_level values between 0.4-0.9

**Step 5: Commit**

```bash
git add pipeline/fetch.py pipeline/hn_fetch.py
git commit -m "feat: store trust_level when fetching posts"
```

---

## Task 4: Add workflow_similarity Column to Clusters Table

**Files:**
- Modify: `utils/db.py`

**Step 1: Add workflow_similarity column to clusters table schema**

Update the `clusters` table creation in both `_init_unified_database` (around line 161) and `_init_clusters_db` (around line 371):

Replace the existing table definition with:

```python
conn.execute("""
    CREATE TABLE IF NOT EXISTS clusters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cluster_name TEXT NOT NULL,
        cluster_description TEXT,
        source_type TEXT,
        centroid_summary TEXT,
        common_pain TEXT,
        common_context TEXT,
        example_events TEXT,
        pain_event_ids TEXT NOT NULL,
        cluster_size INTEGER NOT NULL,
        avg_pain_score REAL,
        workflow_confidence REAL,
        workflow_similarity REAL DEFAULT 0.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
```

**Step 2: Add migration for existing clusters**

Add a new method:

```python
def _add_workflow_similarity_column(self, conn):
    """Add workflow_similarity column to clusters table if not exists"""
    try:
        cursor = conn.execute("PRAGMA table_info(clusters)")
        existing_columns = {row['name'] for row in cursor.fetchall()}

        if 'workflow_similarity' not in existing_columns:
            conn.execute("""
                ALTER TABLE clusters
                ADD COLUMN workflow_similarity REAL DEFAULT 0.0
            """)
            logger.info("Added workflow_similarity column to clusters table")

            # For existing clusters, migrate workflow_confidence to workflow_similarity
            conn.execute("""
                UPDATE clusters
                SET workflow_similarity = workflow_confidence
                WHERE workflow_confidence IS NOT NULL
            """)
            logger.info("Migrated workflow_confidence to workflow_similarity")

    except Exception as e:
        logger.error(f"Failed to add workflow_similarity column: {e}")
```

**Step 3: Call migration in _init_databases**

Update `def _init_databases(self)` to include the migration:

```python
def _init_databases(self):
    """Initialize all database schemas"""
    if self.unified:
        self._init_unified_database()
        with self.get_connection("raw") as conn:
            self._add_trust_level_column(conn)
        with self.get_connection("clusters") as conn:
            self._add_workflow_similarity_column(conn)
    else:
        self._init_raw_posts_db()
        self._init_filtered_posts_db()
        self._init_pain_events_db()
        self._init_clusters_db()
        with self.get_connection("raw") as conn:
            self._add_trust_level_column(conn)
        with self.get_connection("clusters") as conn:
            self._add_workflow_similarity_column(conn)
```

**Step 4: Update insert_cluster to include workflow_similarity**

Modify `def insert_cluster(self, cluster_data: Dict[str, Any])` (around line 715):

```python
def insert_cluster(self, cluster_data: Dict[str, Any]) -> Optional[int]:
    """Insert cluster with workflow_similarity support"""
    try:
        with self.get_connection("clusters") as conn:
            cursor = conn.execute("""
                INSERT INTO clusters
                (cluster_name, cluster_description, source_type, centroid_summary,
                 common_pain, common_context, example_events, pain_event_ids, cluster_size,
                 avg_pain_score, workflow_confidence, workflow_similarity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cluster_data["cluster_name"],
                cluster_data.get("cluster_description", ""),
                cluster_data.get("source_type", ""),
                cluster_data.get("centroid_summary", ""),
                cluster_data.get("common_pain", ""),
                cluster_data.get("common_context", ""),
                json.dumps(cluster_data.get("example_events", [])),
                json.dumps(cluster_data["pain_event_ids"]),
                cluster_data["cluster_size"],
                cluster_data.get("avg_pain_score", 0.0),
                cluster_data.get("workflow_confidence", 0.0),
                cluster_data.get("workflow_similarity", 0.0)  # NEW
            ))
            cluster_id = cursor.lastrowid
            conn.commit()
            return cluster_id
    except Exception as e:
        logger.error(f"Failed to insert cluster: {e}")
        return None
```

**Step 5: Test database migration**

Run: `python -c "from utils.db import db; print('Migration test passed')"`
Expected: No errors, columns exist

**Step 6: Commit**

```bash
git add utils/db.py
git commit -m "feat: add workflow_similarity column to clusters table"
```

---

## Task 5: Add alignment_score Column to Aligned Problems Table

**Files:**
- Modify: `utils/db.py`

**Step 1: Add alignment_score to aligned_problems table schema**

Update the `aligned_problems` table creation in both `_init_unified_database` (around line 203) and `_init_clusters_db` (around line 413):

```python
conn.execute("""
    CREATE TABLE IF NOT EXISTS aligned_problems (
        id TEXT PRIMARY KEY,
        aligned_problem_id TEXT UNIQUE,
        sources TEXT,
        core_problem TEXT,
        why_they_look_different TEXT,
        evidence TEXT,
        cluster_ids TEXT,
        alignment_score REAL DEFAULT 0.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
```

**Step 2: Add migration for existing aligned_problems**

```python
def _add_alignment_score_column(self, conn):
    """Add alignment_score column to aligned_problems table if not exists"""
    try:
        cursor = conn.execute("PRAGMA table_info(aligned_problems)")
        existing_columns = {row['name'] for row in cursor.fetchall()}

        if 'alignment_score' not in existing_columns:
            conn.execute("""
                ALTER TABLE aligned_problems
                ADD COLUMN alignment_score REAL DEFAULT 0.0
            """)
            logger.info("Added alignment_score column to aligned_problems table")

            # Existing alignments get a default high score since they were manually validated
            conn.execute("""
                UPDATE aligned_problems
                SET alignment_score = 0.85
                WHERE alignment_score = 0.0
            """)
            logger.info("Set default alignment_score for existing aligned problems")

    except Exception as e:
        logger.error(f"Failed to add alignment_score column: {e}")
```

**Step 3: Call migration in _init_databases**

Update the `_init_databases` method to include this migration:

```python
def _init_databases(self):
    """Initialize all database schemas"""
    if self.unified:
        self._init_unified_database()
        with self.get_connection("raw") as conn:
            self._add_trust_level_column(conn)
        with self.get_connection("clusters") as conn:
            self._add_workflow_similarity_column(conn)
            self._add_alignment_score_column(conn)
    else:
        self._init_raw_posts_db()
        self._init_filtered_posts_db()
        self._init_pain_events_db()
        self._init_clusters_db()
        with self.get_connection("raw") as conn:
            self._add_trust_level_column(conn)
        with self.get_connection("clusters") as conn:
            self._add_workflow_similarity_column(conn)
            self._add_alignment_score_column(conn)
```

**Step 4: Update insert_aligned_problem**

Modify `def insert_aligned_problem(self, aligned_problem_data: Dict)` (around line 911):

```python
def insert_aligned_problem(self, aligned_problem_data: Dict):
    """Insert aligned problem with alignment_score"""
    try:
        with self.get_connection("clusters") as conn:
            conn.execute("""
                INSERT OR REPLACE INTO aligned_problems
                (id, aligned_problem_id, sources, core_problem,
                 why_they_look_different, evidence, cluster_ids, alignment_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                aligned_problem_data['id'],
                aligned_problem_data['aligned_problem_id'],
                json.dumps(aligned_problem_data['sources']),
                aligned_problem_data['core_problem'],
                aligned_problem_data['why_they_look_different'],
                json.dumps(aligned_problem_data['evidence']),
                json.dumps(aligned_problem_data['cluster_ids']),
                aligned_problem_data.get('alignment_score', 0.0)  # NEW
            ))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to insert aligned problem: {e}")
        raise
```

**Step 5: Commit**

```bash
git add utils/db.py
git commit -m "feat: add alignment_score to aligned_problems table"
```

---

## Task 6: Update LLM Client Prompt for Clustering

**Files:**
- Modify: `utils/llm_client.py`

**Step 1: Update _get_workflow_clustering_prompt to output float scores**

Replace the entire `_get_workflow_clustering_prompt` method (around line 369):

```python
def _get_workflow_clustering_prompt(self) -> str:
    """Get workflow clustering prompt with continuous scoring"""
    return """You are analyzing user pain events.

Given the following pain events, rate how similar their UNDERLYING WORKFLOWS are on a continuous scale.

A workflow means:
- The same repeated activity
- Where different people fail in similar ways
- With similar root causes

Your task: Rate the workflow similarity from 0.0 to 1.0:
- 0.0 = Completely different workflows
- 0.3 = Some vague similarity but different core activities
- 0.5 = Partially similar with key differences
- 0.7 = Strong similarity with minor variations
- 1.0 = Identical workflows

If similarity >= 0.7:
- Give the workflow a short descriptive name
- Provide a brief description
- Explain your reasoning

If similarity < 0.7:
- Still provide a workflow name and description
- But note the key differences in reasoning

Return JSON only with this format:
{
  "workflow_similarity": 0.75,
  "workflow_name": "name of the workflow (even if low similarity)",
  "workflow_description": "description of what these events have in common",
  "confidence": 0.8,
  "reasoning": "brief explanation of your rating"
}

Be precise with your similarity score - use the full 0.0-1.0 range."""
```

**Step 2: Update cluster_pain_events method to handle the new response**

The method signature and call don't need to change since it already returns JSON. The response parsing in `pipeline/cluster.py` will need to be updated.

**Step 3: Commit**

```bash
git add utils/llm_client.py
git commit -m "feat: change clustering prompt from boolean to float score"
```

---

## Task 7: Update Clustering Pipeline to Use Float Scores

**Files:**
- Modify: `pipeline/cluster.py`

**Step 1: Add threshold constant**

At the top of the file, after imports (around line 16), add:

```python
# Hardcoded threshold for cluster validation
WORKFLOW_SIMILARITY_THRESHOLD = 0.7
```

**Step 2: Update _validate_cluster_with_llm to parse float scores**

Modify the `def _validate_cluster_with_llm` method (around line 53):

```python
def _validate_cluster_with_llm(
    self,
    pain_events: List[Dict[str, Any]],
    cluster_name: str = None
) -> Dict[str, Any]:
    """Use LLM to validate cluster with continuous scoring"""
    try:
        # Call LLM for cluster validation
        response = llm_client.cluster_pain_events(pain_events)
        validation_result = response["content"]

        # Extract workflow_similarity score
        workflow_similarity = validation_result.get("workflow_similarity", 0.0)

        # Use hardcoded threshold for decision
        is_valid_cluster = workflow_similarity >= WORKFLOW_SIMILARITY_THRESHOLD

        return {
            "is_valid_cluster": is_valid_cluster,
            "workflow_similarity": workflow_similarity,  # NEW: Store raw score
            "cluster_name": validation_result.get("workflow_name", "Unnamed Cluster"),
            "cluster_description": validation_result.get("workflow_description", ""),
            "confidence": validation_result.get("confidence", 0.0),
            "reasoning": validation_result.get("reasoning", "")
        }

    except Exception as e:
        logger.error(f"Failed to validate cluster with LLM: {e}")
        return {
            "is_valid_cluster": False,
            "workflow_similarity": 0.0,
            "reasoning": f"Validation error: {e}"
        }
```

**Step 3: Update _save_cluster_to_database to store workflow_similarity**

Modify `def _save_cluster_to_database` (around line 158):

```python
def _save_cluster_to_database(self, cluster_data: Dict[str, Any]) -> Optional[int]:
    """Save cluster to database with workflow_similarity"""
    try:
        # Prepare cluster data
        cluster_record = {
            "cluster_name": cluster_data["cluster_name"],
            "cluster_description": cluster_data["cluster_description"],
            "source_type": cluster_data.get("source_type", ""),
            "centroid_summary": cluster_data.get("centroid_summary", ""),
            "common_pain": cluster_data.get("common_pain", ""),
            "common_context": cluster_data.get("common_context", ""),
            "example_events": cluster_data.get("example_events", []),
            "pain_event_ids": cluster_data["pain_event_ids"],
            "cluster_size": cluster_data["cluster_size"],
            "avg_pain_score": cluster_data.get("avg_pain_score", 0.0),
            "workflow_confidence": cluster_data.get("workflow_confidence", 0.0),
            "workflow_similarity": cluster_data.get("workflow_similarity", 0.0)  # NEW
        }

        cluster_id = db.insert_cluster(cluster_record)
        return cluster_id

    except Exception as e:
        logger.error(f"Failed to save cluster to database: {e}")
        return None
```

**Step 4: Update _process_source_clusters to use workflow_similarity**

Modify the cluster validation part (around line 341):

```python
# Use LLM to validate cluster
validation_result = self._validate_cluster_with_llm(events_for_processing)
self.stats["llm_validations"] += 1

# Log the continuous score for debugging
logger.info(f"Cluster {i+1} workflow_similarity: {validation_result.get('workflow_similarity', 0.0):.2f}")

if validation_result["is_valid_cluster"]:
    # ... rest of the processing code ...
```

Also add workflow_similarity to the final_cluster dict (around line 350):

```python
final_cluster = {
    "cluster_name": f"{source_type}: {validation_result['cluster_name']}",
    "cluster_description": validation_result["cluster_description"],
    "source_type": source_type,
    "cluster_id": cluster_id,
    "centroid_summary": summary_result.get("centroid_summary", ""),
    "common_pain": summary_result.get("common_pain", ""),
    "common_context": summary_result.get("common_context", ""),
    "example_events": summary_result.get("example_events", []),
    "pain_event_ids": [event["id"] for event in cluster_events],
    "cluster_size": len(cluster_events),
    "workflow_confidence": validation_result["confidence"],
    "workflow_similarity": validation_result.get("workflow_similarity", 0.0),  # NEW
    "validation_reasoning": validation_result["reasoning"]
}
```

**Step 5: Test clustering with new scores**

Run: `python -m pipeline.cluster --limit 50`
Expected: Clusters should have workflow_similarity values stored

**Step 6: Commit**

```bash
git add pipeline/cluster.py
git commit -m "feat: use workflow_similarity float score in clustering"
```

---

## Task 8: Update Cross-Source Alignment to Use Float Scores

**Files:**
- Modify: `pipeline/align_cross_sources.py`

**Step 1: Add threshold constant**

At the top of the file (around line 11), add:

```python
# Hardcoded threshold for alignment confidence
ALIGNMENT_SCORE_THRESHOLD = 0.7
```

**Step 2: Update _build_alignment_prompt to request float scores**

Modify `def _build_alignment_prompt` (around line 126). Update the prompt to request continuous scoring:

```python
def _build_alignment_prompt(self, source_groups: Dict) -> str:
    """Build alignment prompt with continuous scoring"""
    prompt = """You are analyzing problem summaries from different online communities to identify when they're discussing the same underlying issue.

You will receive multiple problem clusters grouped by community type.
"""

    # Add each source group (existing code unchanged)
    for source_type, clusters in source_groups.items():
        prompt += f"\n## {source_type.upper()} Communities:\n\n"
        for i, cluster in enumerate(clusters, 1):
            prompt += f"Cluster {i}:\n"
            prompt += f"- Summary: {cluster['cluster_summary']}\n"
            prompt += f"- Typical workaround: {cluster['typical_workaround']}\n"
            prompt += f"- Context: {cluster['context']}\n\n"

    prompt += """
## Task

For each PAIR of clusters from DIFFERENT communities, rate how likely they describe the SAME underlying problem on a scale of 0.0 to 1.0:

- 0.0 = Completely different problems
- 0.3 = Some surface similarity but different core issues
- 0.5 = Partially overlapping with key differences
- 0.7 = Strong indication of same problem with different expressions
- 1.0 = Clearly the same underlying problem

Rules:
1. Only align clusters from DIFFERENT source types
2. Be conservative - only report alignments with score >= 0.6
3. Focus on the core problem, not tone or solution sophistication
4. Consider workarounds and context as evidence

## Output Format

For each alignment with score >= 0.6, output a JSON object:
{
  "alignment_score": 0.85,
  "aligned_problem_id": "AP_XX",
  "sources": ["source_type_1", "source_type_2"],
  "core_problem": "Clear description of the shared underlying problem",
  "why_they_look_different": "Explanation of how the same problem appears different",
  "evidence": [
    {
      "source": "hn_ask",
      "cluster_summary": "...",
      "evidence_quote": "Specific evidence from the cluster summary"
    },
    {
      "source": "reddit",
      "cluster_summary": "...",
      "evidence_quote": "Specific evidence from the cluster summary"
    }
  ],
  "original_cluster_ids": ["cluster_id_1", "cluster_id_2"]
}

Return only valid JSON arrays of alignment objects. If no alignments have score >= 0.6, return an empty array.
"""

    return prompt
```

**Step 3: Update _parse_alignment_response to handle alignment_score**

Modify `def _parse_alignment_response` (around line 182). Add validation for `alignment_score` field:

```python
def _parse_alignment_response(self, response: str, original_clusters: List[Dict]) -> List[Dict]:
    """Parse LLM response with alignment_score"""
    try:
        # Extract JSON part
        json_start = response.find('[')
        json_end = response.rfind(']') + 1

        if json_start == -1 or json_end == 0:
            logger.warning("No JSON array found in alignment response")
            return []

        json_str = response[json_start:json_end]
        alignments = json.loads(json_str)

        # Validate and enrich alignments
        validated_alignments = []

        for alignment in alignments:
            # Check for required fields including new alignment_score
            required_fields = [
                'alignment_score', 'aligned_problem_id', 'sources',
                'core_problem', 'why_they_look_different', 'evidence'
            ]

            if not all(field in alignment for field in required_fields):
                logger.warning(f"Alignment missing required fields: {alignment}")
                continue

            # Validate alignment_score is present and is a float
            try:
                alignment_score = float(alignment['alignment_score'])
            except (ValueError, TypeError):
                logger.warning(f"Invalid alignment_score in {alignment}")
                continue

            # Filter by threshold
            if alignment_score < ALIGNMENT_SCORE_THRESHOLD:
                logger.info(f"Skipping alignment with score {alignment_score:.2f} below threshold {ALIGNMENT_SCORE_THRESHOLD}")
                continue

            # Process cluster_ids
            if 'original_cluster_ids' not in alignment:
                alignment['cluster_ids'] = []
            else:
                alignment['cluster_ids'] = alignment['original_cluster_ids']

            # Validate sources
            if not isinstance(alignment['sources'], list) or len(alignment['sources']) < 2:
                logger.warning(f"Invalid sources in alignment: {alignment['sources']}")
                continue

            validated_alignments.append(alignment)

        return validated_alignments

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing alignment response: {e}")
        return []
```

**Step 4: Update process_alignments to store alignment_score**

Modify `def process_alignments` (around line 229). The `alignment` dict from LLM now contains `alignment_score`, and `_insert_aligned_problem` already accepts it via `**alignment_data`:

```python
# In the loop where alignments are saved (around line 246):
for alignment in alignments:
    try:
        alignment['id'] = f"aligned_{alignment['aligned_problem_id']}_{int(time.time())}"

        # alignment_score is already in the dict from LLM
        logger.info(f"Saving alignment {alignment['aligned_problem_id']} with score {alignment.get('alignment_score', 0.0):.2f}")

        self._insert_aligned_problem(alignment)
        # ... rest of code
```

**Step 5: Test cross-source alignment**

Run: `python -m pipeline.align_cross_sources`
Expected: Alignments should have alignment_score values

**Step 6: Commit**

```bash
git add pipeline/align_cross_sources.py
git commit -m "feat: use alignment_score float in cross-source alignment"
```

---

## Task 9: Update Statistics and Reporting to Show Scores

**Files:**
- Modify: `pipeline/cluster.py`
- Modify: `utils/db.py`

**Step 1: Update cluster listing to show workflow_similarity**

Modify `def get_all_clusters_summary` in `pipeline/cluster.py` (around line 436):

```python
def get_all_clusters_summary(self) -> List[Dict[str, Any]]:
    """Get summary of all clusters with workflow_similarity"""
    try:
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("""
                SELECT id, cluster_name, cluster_size, avg_pain_score,
                       workflow_confidence, workflow_similarity, created_at
                FROM clusters
                ORDER BY cluster_size DESC, workflow_similarity DESC
            """)
            clusters = [dict(row) for row in cursor.fetchall()]

        return clusters

    except Exception as e:
        logger.error(f"Failed to get clusters summary: {e}")
        return []
```

**Step 2: Add statistics method for score distribution**

Add a new method to `utils/db.py` (after `get_statistics`):

```python
def get_score_statistics(self) -> Dict[str, Any]:
    """Get statistics on continuous scores"""
    stats = {}

    try:
        with self.get_connection("clusters") as conn:
            # Workflow similarity distribution
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total_clusters,
                    AVG(workflow_similarity) as avg_similarity,
                    MIN(workflow_similarity) as min_similarity,
                    MAX(workflow_similarity) as max_similarity
                FROM clusters
                WHERE workflow_similarity IS NOT NULL
            """)
            row = cursor.fetchone()
            stats['workflow_similarity'] = dict(row) if row else {}

            # Distribution buckets
            cursor = conn.execute("""
                SELECT
                    CASE
                        WHEN workflow_similarity >= 0.8 THEN 'high'
                        WHEN workflow_similarity >= 0.6 THEN 'medium'
                        ELSE 'low'
                    END as bucket,
                    COUNT(*) as count
                FROM clusters
                WHERE workflow_similarity IS NOT NULL
                GROUP BY bucket
            """)
            stats['workflow_similarity_distribution'] = {row['bucket']: row['count'] for row in cursor.fetchall()}

        with self.get_connection("clusters") as conn:
            # Alignment score distribution
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total_alignments,
                    AVG(alignment_score) as avg_alignment,
                    MIN(alignment_score) as min_alignment,
                    MAX(alignment_score) as max_alignment
                FROM aligned_problems
                WHERE alignment_score IS NOT NULL
            """)
            row = cursor.fetchone()
            stats['alignment_score'] = dict(row) if row else {}

        with self.get_connection("raw") as conn:
            # Trust level distribution by source
            cursor = conn.execute("""
                SELECT
                    source,
                    COUNT(*) as count,
                    AVG(trust_level) as avg_trust_level
                FROM posts
                WHERE trust_level IS NOT NULL
                GROUP BY source
            """)
            stats['trust_level_by_source'] = {row['source']: {'count': row['count'], 'avg_trust': row['avg_trust_level']} for row in cursor.fetchall()}

    except Exception as e:
        logger.error(f"Failed to get score statistics: {e}")

    return stats
```

**Step 3: Test statistics**

Run: `python -c "from utils.db import db; import json; print(json.dumps(db.get_score_statistics(), indent=2))"`
Expected: Shows distribution of scores

**Step 4: Commit**

```bash
git add pipeline/cluster.py utils/db.py
git commit -m "feat: add score statistics reporting"
```

---

## Task 10: Create Test Script for Verification

**Files:**
- Create: `tests/test_trust_level_soft_judgment.py`

**Step 1: Create test file**

```python
#!/usr/bin/env python3
"""
Test script to verify trust_level and soft judgment implementation

Tests:
1. Trust level is correctly loaded from config
2. Posts are stored with trust_level
3. Clusters are validated with workflow_similarity scores
4. Alignment uses alignment_score
5. Hardcoded thresholds are applied correctly
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import db
from utils.llm_client import llm_client
import yaml

def test_trust_level_config():
    """Test that trust_level is in config"""
    print("Testing trust_level in config...")
    with open("config/subreddits.yaml") as f:
        config = yaml.safe_load(f)

    # Check each category has trust_level
    categories = ['core', 'secondary', 'verticals', 'experimental']
    for cat in categories:
        if cat in config and isinstance(config[cat], dict):
            if 'trust_level' in config[cat]:
                print(f"  ✓ {cat}: trust_level = {config[cat]['trust_level']}")
            else:
                print(f"  ✗ {cat}: missing trust_level")
                return False
    return True

def test_posts_have_trust_level():
    """Test that posts table has trust_level column"""
    print("\nTesting trust_level in posts table...")
    import sqlite3
    conn = sqlite3.connect(db.unified_db_path)
    cursor = conn.execute("PRAGMA table_info(posts)")
    columns = {row['name'] for row in cursor.fetchall()}
    conn.close()

    if 'trust_level' in columns:
        print("  ✓ trust_level column exists")
        # Check sample values
        with db.get_connection("raw") as conn:
            cursor = conn.execute("SELECT id, category, trust_level FROM posts LIMIT 5")
            posts = cursor.fetchall()
            if posts:
                print(f"  ✓ Sample posts have trust_level:")
                for post in posts:
                    print(f"    - {post['category']}: {post['trust_level']}")
            else:
                print("  ⚠ No posts found to verify")
        return True
    else:
        print("  ✗ trust_level column missing")
        return False

def test_clusters_have_workflow_similarity():
    """Test that clusters table has workflow_similarity column"""
    print("\nTesting workflow_similarity in clusters table...")
    import sqlite3
    conn = sqlite3.connect(db.unified_db_path)
    cursor = conn.execute("PRAGMA table_info(clusters)")
    columns = {row['name'] for row in cursor.fetchall()}
    conn.close()

    if 'workflow_similarity' in columns:
        print("  ✓ workflow_similarity column exists")
        # Check sample values
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("""
                SELECT cluster_name, workflow_similarity
                FROM clusters
                WHERE workflow_similarity IS NOT NULL
                LIMIT 5
            """)
            clusters = cursor.fetchall()
            if clusters:
                print(f"  ✓ Sample clusters have workflow_similarity:")
                for cluster in clusters:
                    print(f"    - {cluster['cluster_name']}: {cluster['workflow_similarity']:.2f}")
            else:
                print("  ⚠ No clusters found to verify")
        return True
    else:
        print("  ✗ workflow_similarity column missing")
        return False

def test_aligned_problems_have_alignment_score():
    """Test that aligned_problems table has alignment_score column"""
    print("\nTesting alignment_score in aligned_problems table...")
    import sqlite3
    conn = sqlite3.connect(db.unified_db_path)
    cursor = conn.execute("PRAGMA table_info(aligned_problems)")
    columns = {row['name'] for row in cursor.fetchall()}
    conn.close()

    if 'alignment_score' in columns:
        print("  ✓ alignment_score column exists")
        return True
    else:
        print("  ✗ alignment_score column missing")
        return False

def test_llm_prompt_outputs_float():
    """Test that clustering prompt requests float output"""
    print("\nTesting LLM clustering prompt...")
    prompt = llm_client._get_workflow_clustering_prompt()

    if "workflow_similarity" in prompt and "0.0" in prompt and "1.0" in prompt:
        print("  ✓ Prompt requests workflow_similarity (0.0-1.0)")
        return True
    else:
        print("  ✗ Prompt doesn't request float score")
        return False

def test_threshold_constants():
    """Test that threshold constants are defined"""
    print("\nTesting threshold constants...")
    try:
        from pipeline.cluster import WORKFLOW_SIMILARITY_THRESHOLD
        print(f"  ✓ WORKFLOW_SIMILARITY_THRESHOLD = {WORKFLOW_SIMILARITY_THRESHOLD}")
    except ImportError:
        print("  ✗ WORKFLOW_SIMILARITY_THRESHOLD not defined")
        return False

    try:
        from pipeline.align_cross_sources import ALIGNMENT_SCORE_THRESHOLD
        print(f"  ✓ ALIGNMENT_SCORE_THRESHOLD = {ALIGNMENT_SCORE_THRESHOLD}")
    except ImportError:
        print("  ✗ ALIGNMENT_SCORE_THRESHOLD not defined")
        return False

    return True

def test_score_statistics():
    """Test score statistics"""
    print("\nTesting score statistics...")
    stats = db.get_score_statistics()

    print("  Workflow similarity stats:")
    if 'workflow_similarity' in stats:
        ws = stats['workflow_similarity']
        print(f"    - Total clusters: {ws.get('total_clusters', 0)}")
        print(f"    - Avg similarity: {ws.get('avg_similarity', 0):.3f}")
        print(f"    - Min: {ws.get('min_similarity', 0):.3f}, Max: {ws.get('max_similarity', 0):.3f}")

    print("  Alignment score stats:")
    if 'alignment_score' in stats:
        als = stats['alignment_score']
        print(f"    - Total alignments: {als.get('total_alignments', 0)}")
        print(f"    - Avg score: {als.get('avg_alignment', 0):.3f}")

    print("  Trust level by source:")
    if 'trust_level_by_source' in stats:
        for source, data in stats['trust_level_by_source'].items():
            print(f"    - {source}: count={data['count']}, avg_trust={data['avg_trust']:.2f}")

    return True

def main():
    """Run all tests"""
    print("=" * 60)
    print("Trust Level & Soft Judgment Verification Tests")
    print("=" * 60)

    tests = [
        test_trust_level_config,
        test_posts_have_trust_level,
        test_clusters_have_workflow_similarity,
        test_aligned_problems_have_alignment_score,
        test_llm_prompt_outputs_float,
        test_threshold_constants,
        test_score_statistics,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)

    return all(results)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
```

**Step 2: Create tests directory**

```bash
mkdir -p /home/ubuntu/PyProjects/wise_collection/reddit_pain_finder/tests
```

**Step 3: Make test executable**

```bash
chmod +x tests/test_trust_level_soft_judgment.py
```

**Step 4: Run tests**

```bash
python tests/test_trust_level_soft_judgment.py
```
Expected: All tests pass

**Step 5: Commit**

```bash
git add tests/test_trust_level_soft_judgment.py
git commit -m "test: add verification tests for trust level and soft judgment"
```

---

## Task 11: Create Migration Script for Existing Data

**Files:**
- Create: `scripts/migrate_to_soft_judgment.py`

**Step 1: Create migration script**

```python
#!/usr/bin/env python3
"""
Migration script to add trust_level and soft judgment columns to existing databases.

This script should be run ONCE after deploying the new code to existing installations.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_posts_trust_level():
    """Migrate posts table to add trust_level"""
    logger.info("Migrating posts table for trust_level...")

    with db.get_connection("raw") as conn:
        # Check if column exists
        cursor = conn.execute("PRAGMA table_info(posts)")
        columns = {row['name'] for row in cursor.fetchall()}

        if 'trust_level' not in columns:
            conn.execute("ALTER TABLE posts ADD COLUMN trust_level REAL DEFAULT 0.5")
            logger.info("Added trust_level column to posts table")

            # Set trust_level based on category
            category_trust = {
                'core': 0.9,
                'secondary': 0.7,
                'verticals': 0.6,
                'experimental': 0.4
            }

            for category, level in category_trust.items():
                conn.execute("UPDATE posts SET trust_level = ? WHERE category = ?", (level, category))
                affected = conn.total_changes
                logger.info(f"Set trust_level={level} for {affected} posts in category '{category}'")

            conn.commit()
            logger.info("✓ Posts table migration complete")
        else:
            logger.info("trust_level column already exists in posts table")

def migrate_clusters_workflow_similarity():
    """Migrate clusters table to add workflow_similarity"""
    logger.info("Migrating clusters table for workflow_similarity...")

    with db.get_connection("clusters") as conn:
        cursor = conn.execute("PRAGMA table_info(clusters)")
        columns = {row['name'] for row in cursor.fetchall()}

        if 'workflow_similarity' not in columns:
            conn.execute("ALTER TABLE clusters ADD COLUMN workflow_similarity REAL DEFAULT 0.0")
            logger.info("Added workflow_similarity column to clusters table")

            # Migrate from workflow_confidence for existing clusters
            conn.execute("""
                UPDATE clusters
                SET workflow_similarity = COALESCE(workflow_confidence, 0.0)
                WHERE workflow_similarity = 0.0
            """)
            affected = conn.total_changes
            logger.info(f"Migrated {affected} clusters from workflow_confidence to workflow_similarity")

            conn.commit()
            logger.info("✓ Clusters table migration complete")
        else:
            logger.info("workflow_similarity column already exists in clusters table")

def migrate_aligned_problems_alignment_score():
    """Migrate aligned_problems table to add alignment_score"""
    logger.info("Migrating aligned_problems table for alignment_score...")

    with db.get_connection("clusters") as conn:
        cursor = conn.execute("PRAGMA table_info(aligned_problems)")
        columns = {row['name'] for row in cursor.fetchall()}

        if 'alignment_score' not in columns:
            conn.execute("ALTER TABLE aligned_problems ADD COLUMN alignment_score REAL DEFAULT 0.0")
            logger.info("Added alignment_score column to aligned_problems table")

            # Set default high score for existing manually validated alignments
            conn.execute("""
                UPDATE aligned_problems
                SET alignment_score = 0.85
                WHERE alignment_score = 0.0
            """)
            affected = conn.total_changes
            logger.info(f"Set default alignment_score=0.85 for {affected} existing aligned problems")

            conn.commit()
            logger.info("✓ Aligned problems table migration complete")
        else:
            logger.info("alignment_score column already exists in aligned_problems table")

def main():
    """Run all migrations"""
    logger.info("=" * 60)
    logger.info("Starting Trust Level & Soft Judgment Migration")
    logger.info("=" * 60)

    try:
        migrate_posts_trust_level()
        migrate_clusters_workflow_similarity()
        migrate_aligned_problems_alignment_score()

        logger.info("=" * 60)
        logger.info("✓ All migrations completed successfully!")
        logger.info("=" * 60)

        # Show post-migration stats
        stats = db.get_score_statistics()
        logger.info("\nPost-migration statistics:")
        if 'trust_level_by_source' in stats:
            for source, data in stats['trust_level_by_source'].items():
                logger.info(f"  {source}: {data['count']} posts, avg trust={data['avg_trust']:.2f}")

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
```

**Step 2: Create scripts directory**

```bash
mkdir -p /home/ubuntu/PyProjects/wise_collection/reddit_pain_finder/scripts
```

**Step 3: Make script executable**

```bash
chmod +x scripts/migrate_to_soft_judgment.py
```

**Step 4: Run migration**

```bash
python scripts/migrate_to_soft_judgment.py
```
Expected: All migrations complete successfully

**Step 5: Commit**

```bash
git add scripts/migrate_to_soft_judgment.py
git commit -m "feat: add migration script for trust level and soft judgment"
```

---

## Task 12: Documentation and Summary

**Files:**
- Create: `docs/trust_level_soft_judgment_guide.md`

**Step 1: Create documentation**

```markdown
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
- Run 1: `same_workflow: true` → Cluster created
- Run 2: `same_workflow: false` → Cluster rejected
- Result: Unstable!

**After** (Float):
- Run 1: `workflow_similarity: 0.75` → Cluster created
- Run 2: `workflow_similarity: 0.78` → Cluster created
- Run 3: `workflow_similarity: 0.72` → Cluster created
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
```

**Step 2: Commit documentation**

```bash
git add docs/trust_level_soft_judgment_guide.md
git commit -m "docs: add trust level and soft judgment guide"
```

---

## Final Verification Steps

After implementing all tasks:

1. **Run migration script**: `python scripts/migrate_to_soft_judgment.py`
2. **Run tests**: `python tests/test_trust_level_soft_judgment.py`
3. **Fetch new posts**: `python -m pipeline.fetch --limit 10`
4. **Verify trust_level**: Check database for trust_level values
5. **Run clustering**: `python -m pipeline.cluster --limit 50`
6. **Verify workflow_similarity**: Check clusters table
7. **Run alignment**: `python -m pipeline.align_cross_sources`
8. **Verify alignment_score**: Check aligned_problems table

**Expected outcome**: Multiple pipeline runs should produce consistent results within a reasonable score range, not flip-flopping between boolean states.

---

## Execution Options

**Plan complete and saved to `docs/plans/2025-12-23-trust-level-soft-judgment.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
