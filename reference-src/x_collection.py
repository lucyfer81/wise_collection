# x_collection.py - v1.0 (X Platform Collector)
import os
import json
import sys
import config  # Import the centralized config
from datetime import datetime

# --- Configuration ---
# X platform specific configuration would go here
# For example, API keys, endpoints, etc.

def load_processed_ids():
    """Load previously processed post IDs from file"""
    # We'll use the same processed IDs file for now
    # In a more advanced implementation, you might want separate tracking
    if not config.PROCESSED_IDS_FILE.exists(): 
        return set()
    try:
        with open(config.PROCESSED_IDS_FILE, 'r', encoding='utf-8') as f: 
            return set(json.load(f))
    except (json.JSONDecodeError, IOError): 
        return set()

def save_processed_ids(ids):
    """Save processed post IDs to file"""
    with open(config.PROCESSED_IDS_FILE, 'w', encoding='utf-8') as f: 
        json.dump(list(ids), f, indent=4)

def process_and_save_post(post_data, output_dir):
    """
    Process and save a post from X platform.
    Adds a 'source' field to distinguish from Reddit posts.
    """
    print(f"  🐦 X Post Found: '{post_data['title'][:60]}...' (ID: {post_data['id']})")

    # Add source identifier
    post_data["source"] = "x_platform"
    
    # Use pathlib for path construction
    file_path = output_dir / f"{post_data['id']}.json"
    with open(file_path, 'w', encoding='utf-8') as f: 
        json.dump(post_data, f, indent=4, ensure_ascii=False)
    
    return True

def main():
    print("--- X Platform Collector v1.0 ---")
    
    # Create output directory if it doesn't exist
    config.REDDIT_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load processed IDs
    processed_ids = load_processed_ids()
    print(f"Loaded {len(processed_ids)} previously processed post IDs.")
    
    # Example placeholder for X platform collection
    # In a real implementation, you would:
    # 1. Connect to X platform API
    # 2. Fetch posts based on search criteria
    # 3. Filter and process posts
    # 4. Save new posts to the same directory as Reddit posts
    
    # For demonstration purposes, we'll simulate collecting some posts
    sample_posts = [
        {
            "id": "x1234567890",
            "title": "Example X Post about AI",
            "url": "https://x.com/user/status/1234567890",
            "score": 50,
            "num_comments": 15,
            "content": "This is an example post about AI from X platform.",
            "created_utc": datetime.utcnow().timestamp(),
            "author": "example_user"
        },
        {
            "id": "x0987654321",
            "title": "Another X Post on Machine Learning",
            "url": "https://x.com/user/status/0987654321",
            "score": 75,
            "num_comments": 30,
            "content": "This is another example post about machine learning from X platform.",
            "created_utc": datetime.utcnow().timestamp(),
            "author": "another_user"
        }
    ]
    
    total_found = 0
    for post in sample_posts:
        if post["id"] in processed_ids:
            continue
            
        if process_and_save_post(post, config.REDDIT_INBOX_DIR):
            processed_ids.add(post["id"])
            total_found += 1
    
    print(f"
--- Collection Complete ---")
    print(f"Found and saved {total_found} new posts from X platform.")
    save_processed_ids(processed_ids)
