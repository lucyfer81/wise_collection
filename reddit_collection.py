import praw
import sys
import os
import json
from dotenv import load_dotenv

# --- NEW: Define path for storing processed IDs ---
PROCESSED_IDS_FILE = 'processed_ids.json'

# Load environment variables from .env file
load_dotenv()

# --- NEW: Function to load processed IDs from file ---
def load_processed_ids():
    """Loads the set of processed submission IDs from a file."""
    if not os.path.exists(PROCESSED_IDS_FILE):
        return set()
    try:
        with open(PROCESSED_IDS_FILE, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    except (json.JSONDecodeError, IOError):
        print(f"Warning: Could not read or parse {PROCESSED_IDS_FILE}. Starting with an empty set.", file=sys.stderr)
        return set()

# --- NEW: Function to save processed IDs to file ---
def save_processed_ids(processed_ids):
    """Saves the set of processed submission IDs to a file."""
    try:
        with open(PROCESSED_IDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(processed_ids), f, indent=4)
    except IOError as e:
        print(f"Error: Could not save processed IDs to {PROCESSED_IDS_FILE}: {e}", file=sys.stderr)

# Initialize the Reddit API client
print("Initializing Reddit API client...")
try:
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent="python:Wise_Collection:v1.0 (by /u/SpareAffectionate385)",
        read_only=True,
    )
    print(f"Authenticated as: {reddit.user.me()}")
except Exception as e:
    print(f"Error: Failed to initialize or authenticate with Reddit API.", file=sys.stderr)
    print(f"Details: {e}", file=sys.stderr)
    sys.exit(1)

print("Initialization successful.")

# Load configuration from reddit_config.json
print("Loading configuration from reddit_config.json...")
try:
    with open('reddit_config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    subreddits = config['subreddits']
    pain_signals = config['pain_signals']
    domains = config['domains']
    solution_intentions = config['solution_intentions']
    print("Configuration loaded successfully.")
except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
    print(f"Error loading or parsing reddit_config.json: {e}", file=sys.stderr)
    sys.exit(1)

# --- MODIFIED: The core processing logic ---
def process_and_save_submission(submission, subreddit_name, output_dir, processed_ids):
    """
    Checks, processes, and saves a submission if it's new or significantly updated.
    Returns True if a file was written (new or updated), False otherwise.
    """
    file_path = os.path.join(output_dir, f"{submission.id}.json")
    is_new = submission.id not in processed_ids
    should_update = False

    # If not new, check if it's worth updating
    if not is_new:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
            # Define update thresholds
            if (submission.score > old_data.get('score', 0) + 50 or
                submission.num_comments > old_data.get('num_comments', 0) + 20):
                should_update = True
                print(f"  -> Updating post: {submission.title[:70]}... (New Score: {submission.score}, New Comments: {submission.num_comments})")
        except (FileNotFoundError, json.JSONDecodeError):
            # If file is missing or corrupt, treat it as new
            is_new = True

    if not is_new and not should_update:
        return False # Skip if already processed and not worth updating

    # Filter out low-quality posts that might appear in searches
    if submission.score < 5 or submission.num_comments < 5:
        return False

    if is_new:
        print(f"  -> New post found: {submission.title[:70]}... (Score: {submission.score}, Comments: {submission.num_comments})")

    # Fetch top 5 comments
    submission.comments.replace_more(limit=0)
    top_comments = []
    for i, comment in enumerate(submission.comments.list()):
        if i >= 5: break
        if not hasattr(comment, 'author') or not hasattr(comment, 'body') or not comment.author or not comment.body: continue
        top_comments.append({"author": comment.author.name, "body": comment.body, "score": comment.score})

    # Structure the data
    post_data = {
        "id": submission.id,
        "title": submission.title,
        "subreddit": subreddit_name,
        "url": submission.url,
        "score": submission.score,
        "num_comments": submission.num_comments,
        "selftext": submission.selftext,
        "comments": top_comments
    }

    # Save data to a JSON file
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(post_data, f, indent=4, ensure_ascii=False)
    
    processed_ids.add(submission.id)
    return True

# --- MAIN EXECUTION ---
total_found = 0
output_dir = "content/reddit"
os.makedirs(output_dir, exist_ok=True) # Ensure directory exists

# --- MODIFIED: Load IDs at the start ---
processed_ids = load_processed_ids()
initial_id_count = len(processed_ids)
print(f"Loaded {initial_id_count} previously processed post IDs.")

print(f"Results will be saved in '{output_dir}' directory.")
print("Applying quality filter: Score >= 5 and Comments >= 5")
print("Update thresholds: Score +50 or Comments +20")
print("-" * 20)

try:
    for subreddit_name in subreddits:
        print(f"Scanning r/{subreddit_name}...")
        subreddit = reddit.subreddit(subreddit_name)
        found_in_subreddit = 0

        # Method 1: Get Hot posts (top discussions)
        try:
            for submission in subreddit.hot(limit=25):
                if process_and_save_submission(submission, subreddit_name, output_dir, processed_ids):
                    found_in_subreddit += 1
            print(f"    ✓ Processed 25 hot posts")
        except Exception as e:
            print(f"    Error getting hot posts in r/{subreddit_name}: {e}", file=sys.stderr)

        # Method 2: Get Rising posts (trending discussions)
        try:
            for submission in subreddit.rising(limit=15):
                if process_and_save_submission(submission, subreddit_name, output_dir, processed_ids):
                    found_in_subreddit += 1
            print(f"    ✓ Processed 15 rising posts")
        except Exception as e:
            print(f"    Error getting rising posts in r/{subreddit_name}: {e}", file=sys.stderr)

        # Method 3: Scan New posts for AI keywords
        ai_keywords = ["AI", "LLM", "artificial intelligence", "machine learning", "AGI", "ChatGPT", 
                      "OpenAI", "neural network", "deep learning", "startup", "venture capital", 
                      "singularity", "future", "breakthrough", "innovation", "business"]
        
        try:
            ai_hits = 0
            for submission in subreddit.new(limit=50):
                title_lower = submission.title.lower()
                if any(keyword.lower() in title_lower for keyword in ai_keywords) and submission.score >= 3:
                    if process_and_save_submission(submission, subreddit_name, output_dir, processed_ids):
                        found_in_subreddit += 1
                        ai_hits += 1
            print(f"    ✓ Found {ai_hits} AI-relevant new posts")
        except Exception as e:
            print(f"    Error scanning new posts in r/{subreddit_name}: {e}", file=sys.stderr)
        
        if found_in_subreddit == 0:
            print(f"No new or updated posts found in r/{subreddit_name}.")
        else:
            print(f"Saved or updated {found_in_subreddit} posts from r/{subreddit_name}.")
        
        total_found += found_in_subreddit
        print("-" * 20)

except Exception as e:
    print(f"An error occurred while fetching posts: {e}", file=sys.stderr)
    # --- MODIFIED: Save progress even if an error occurs ---
    print("Attempting to save progress before exiting...")
    save_processed_ids(processed_ids)
    sys.exit(1)

# --- MODIFIED: Save IDs at the end ---
print("\nSearch complete.")
save_processed_ids(processed_ids)
newly_added_count = len(processed_ids) - initial_id_count
print(f"Total posts saved or updated in this run: {total_found}.")
print(f"Total unique posts tracked: {len(processed_ids)} ({newly_added_count} new).")