# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Reddit content collection and analysis pipeline focused on AI-related content. The system collects posts from various subreddits, curates high-quality English content, and performs topic analysis with summarization.

## Architecture

### Core Components

1. **Collection Engine** (`reddit_collection.py`)
   - Fetches posts from multiple subreddits using PRAW Reddit API
   - Implements dynamic search queries with AI keyword categories
   - Pre-filters content based on quality signals
   - Supports multiple collection methods (hot, new, top, controversial, search)

2. **Curation Engine** (`curate.py`)
   - Quality validation with multi-factor scoring
   - Content deduplication using TF-IDF and cosine similarity
   - Spam detection and AI relevance filtering
   - English language validation
   - Anomaly detection for engagement metrics

3. **Analysis Engine** (`analyze_topics.py`)
   - TF-IDF vectorization of English content
   - DBSCAN clustering for topic discovery
   - LLM-based summarization using SiliconFlow API
   - Bilingual summaries (English to Chinese translation)
   - Topic organization and file management

### Data Flow

```
Reddit API → Collection → Raw JSON → Curation → Curated JSON → Analysis → Topics with Summaries
```

### Directory Structure

- `content/reddit/` - Raw collected posts
- `content/reddit_english_curated/` - High-quality curated posts
- `content/processed_json/` - Archived/rejected posts
- `output/topics/` - Final topic analysis with summaries
- `logs/` - Processing logs

## Development Workflow

### Running the Pipeline

1. **Collection Phase**:
   ```bash
   python reddit_collection.py
   ```
   - Requires Reddit API credentials in `.env`
   - Uses `reddit_config.json` for subreddits and keywords
   - Skips already processed posts using `processed_ids.json`

2. **Curation Phase**:
   ```bash
   python curate.py
   ```
   - Processes raw posts from `content/reddit/`
   - Moves high-quality posts to `content/reddit_english_curated/`
   - Maintains content cache in `content_cache.json`

3. **Analysis Phase**:
   ```bash
   python analyze_topics.py
   ```
   - Requires SiliconFlow API key in `.env`
   - Processes curated posts into topic clusters
   - Generates bilingual summaries using Qwen models

### Configuration

- **Reddit API**: Set `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` in `.env`
- **LLM API**: Set `SILICONFLOW_API_KEY` in `.env`
- **Collection Strategy**: Modify `reddit_config.json` for subreddits, thresholds, and keywords
- **Analysis Parameters**: Adjust DBSCAN parameters in `analyze_topics.py`

### Key Dependencies

- `praw` - Reddit API wrapper
- `sklearn` - Machine learning for clustering and similarity
- `numpy` - Numerical operations
- `jieba` - Chinese text processing
- `openai` - LLM API client

## Development Notes

### Code Quality
- All scripts include comprehensive error handling and logging
- Content validation uses multi-factor scoring (minimum 60/100 points)
- Deduplication uses both hash-based and semantic similarity
- Anomaly detection prevents processing of low-quality or spam content

### Performance Considerations
- Collection includes rate limiting (1 second between subreddits)
- Curation processes posts in batches with progress tracking
- Analysis limits TF-IDF features to 2000 for performance
- LLM calls include retry logic for API failures

### Testing
- No formal test suite exists
- Manual testing requires live API access
- Consider adding unit tests for validation logic
- Integration testing would require mock APIs

### Environment Setup
- Python 3.12+ recommended
- Virtual environment in `.venv/`
- Sensitive data in `.env` (not committed)
- Large content directories ignored via `.gitignore`