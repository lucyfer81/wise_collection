# reddit_collection.py - v7.0 (Centralized Config)
import os
import json
import sys
import praw
import config  # Import the centralized config

# --- Configuration ---
CONFIG_FILE = 'reddit_config.json' # This is specific to this script, so it can stay

# (Helper functions using config paths)
def load_processed_ids():
    if not config.PROCESSED_IDS_FILE.exists(): return set()
    try:
        with open(config.PROCESSED_IDS_FILE, 'r', encoding='utf-8') as f: return set(json.load(f))
    except (json.JSONDecodeError, IOError): return set()

def save_processed_ids(ids):
    with open(config.PROCESSED_IDS_FILE, 'w', encoding='utf-8') as f: json.dump(list(ids), f, indent=4)

def log_potential_source(subreddit_name):
    with open(config.POTENTIAL_SOURCES_LOG, 'a', encoding='utf-8') as f: f.write(f"{subreddit_name}\n")


def process_and_save_submission(submission, sub_config, output_dir):
    """Processes and saves a submission, now with safe crosspost checking."""
    thresholds = sub_config['thresholds']
    min_score, min_comments, min_ratio = thresholds.get('min_score', 20), thresholds.get('min_comments', 20), thresholds.get('min_ratio', 0.0)
    
    score = submission.score if submission.score > 0 else 1
    if submission.score < min_score or submission.num_comments < min_comments or (submission.num_comments / score) < min_ratio:
        return False
    
    if hasattr(submission, 'crosspost_parent_list') and submission.crosspost_parent_list:
        parent_subreddit = submission.crosspost_parent_list[0]['subreddit']
        print(f"  [!] Crosspost found. Potential new source: r/{parent_subreddit}")
        log_potential_source(parent_subreddit)
    
    print(f"  🔥 High-Quality Post Found: '{submission.title[:60]}...' (Score: {submission.score})")

    try:
        submission.comment_sort = "top"
        submission.comments.replace_more(limit=0)
        comments_list = [{"author": c.author.name if c.author else "[deleted]", "body": c.body, "score": c.score} for i, c in enumerate(submission.comments.list()) if i < config.COMMENTS_TO_FETCH]
    except Exception as e:
        print(f"    Warning: Could not fetch comments for {submission.id}: {e}", file=sys.stderr)
        comments_list = []

    post_data = {
        "id": submission.id, "title": submission.title, "subreddit": sub_config['name'], "url": submission.url,
        "score": submission.score, "num_comments": submission.num_comments, "selftext": submission.selftext,
        "comments": comments_list, "upvote_ratio": submission.upvote_ratio, "is_self": submission.is_self,
        "created_utc": submission.created_utc, "category": sub_config.get('category', 'Unknown'),
        "source": "reddit"  # Add source identifier for database
    }
    
    # Use pathlib for path construction
    file_path = output_dir / f"{submission.id}.json"
    with open(file_path, 'w', encoding='utf-8') as f: json.dump(post_data, f, indent=4, ensure_ascii=False)
    
    return True

def main():
    print("--- Reddit Adaptive Scout v7.0 ---")
    try:
        # Use credentials from config
        if not all([config.REDDIT_CLIENT_ID, config.REDDIT_CLIENT_SECRET]):
            print("FATAL: Reddit API credentials not found in .env file.", file=sys.stderr)
            sys.exit(1)
            
        reddit = praw.Reddit(client_id=config.REDDIT_CLIENT_ID, 
                             client_secret=config.REDDIT_CLIENT_SECRET, 
                             user_agent="python:AdaptiveScout:v7.0", 
                             read_only=True)
        
        # Authentication check
        try:
            test_subreddit = reddit.subreddit('test')
            test_subreddit.display_name
            print("Reddit authentication successful.")
        except Exception as e:
            print(f"\nFATAL: Reddit authentication failed. Error: {e}", file=sys.stderr)
            print("Please check your .env file for correct REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET.", file=sys.stderr)
            sys.exit(1)
        
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: sub_data = json.load(f)
        sub_configs, ai_keywords = sub_data['subreddits'], sub_data.get('ai_keywords', {})
        search_strategies = sub_data.get('search_strategies', {})
        fetch_limit = search_strategies.get('max_results_per_method', 100)
    except Exception as e: print(f"FATAL: Initialization failed. Error: {e}", file=sys.stderr); sys.exit(1)

    config.REDDIT_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    processed_ids = load_processed_ids()
    print(f"Loaded {len(processed_ids)} previously processed post IDs.")
    
    total_found = 0
    for sub_config in sub_configs:
        print(f"\nScanning r/{sub_config['name']}...")
        subreddit = reddit.subreddit(sub_config['name'])
        methods = sub_config.get('methods', ['hot'])
        query = " OR ".join([f'\"{k}\"' for cat in sub_config.get('keyword_categories', []) for k in ai_keywords.get(cat, [])])

        for method in methods:
            try:
                submissions = []
                if method == 'hot': submissions = subreddit.hot(limit=fetch_limit)
                elif method == 'new': submissions = subreddit.new(limit=fetch_limit)
                elif method == 'rising': submissions = subreddit.rising(limit=fetch_limit)
                elif method == 'controversial': submissions = subreddit.controversial('week', limit=fetch_limit)
                elif method.startswith('top_'): submissions = subreddit.top(time_filter=method.split('_')[1], limit=fetch_limit)
                elif method == 'search' and query: submissions = subreddit.search(query, sort='new', limit=fetch_limit)
                
                for submission in submissions:
                    if submission.id in processed_ids: continue
                    if process_and_save_submission(submission, sub_config, config.REDDIT_INBOX_DIR):
                        processed_ids.add(submission.id)
                        total_found += 1
            except Exception as e: print(f"    ERROR scanning with method '{method}': {e}", file=sys.stderr)

    print(f"\n--- Scan Complete ---")
    print(f"Found and saved {total_found} new posts.")
    save_processed_ids(processed_ids)
    print(f"Check '{config.POTENTIAL_SOURCES_LOG.name}' for new source recommendations.")
