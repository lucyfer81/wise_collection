#!/usr/bin/env python3
"""
Script to create a new collection script for X platform posts,
similar to reddit_collection.py but with a new source identifier.

This script will:
1. Create a new collection script for X platform
2. Modify the database schema to include a source column
"""

import os
import sys

def create_x_collection_script():
    """Create a new collection script for X platform posts"""
    script_content = '''# x_collection.py - v1.0 (X Platform Collector)
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
    
    print(f"\n--- Collection Complete ---")
    print(f"Found and saved {total_found} new posts from X platform.")
    save_processed_ids(processed_ids)
'''

    # Write the script to file
    script_path = os.path.join(os.path.dirname(__file__), 'x_collection.py')
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    print(f"Created X platform collection script at: {script_path}")
    return script_path

def update_database_schema():
    """Update the database schema to include a source column"""
    update_script = '''#!/usr/bin/env python3
"""
Script to update the database schema to include a source column
"""
import os
import libsql
from dotenv import load_dotenv

load_dotenv()

def update_database_schema():
    """Update database to include source column"""
    try:
        # Connect to database
        db_url = os.getenv("TURSO_DB_URL") or os.getenv("DB_URL")
        auth_token = os.getenv("TURSO_DB_AUTH_TOKEN") or os.getenv("DB_AUTH_TOKEN")
        
        print(f"Connecting to database: {db_url}")
        
        conn = libsql.connect(database="", sync_url=db_url, auth_token=auth_token)
        cursor = conn.cursor()
        
        # Check if source column already exists
        cursor.execute("PRAGMA table_info(topics);")
        columns = cursor.fetchall()
        source_column_exists = any(col[1] == 'source' for col in columns)
        
        if not source_column_exists:
            print("Adding 'source' column to topics table...")
            # Add source column with default value 'reddit'
            cursor.execute("ALTER TABLE topics ADD COLUMN source TEXT DEFAULT 'reddit';")
            conn.commit()
            print("✅ Source column added successfully")
        else:
            print("✅ Source column already exists")
            
        # Update existing records to have 'reddit' as source
        cursor.execute("UPDATE topics SET source = 'reddit' WHERE source IS NULL;")
        conn.commit()
        print("✅ Updated existing records with 'reddit' as source")
        
        # Verify the changes
        cursor.execute("PRAGMA table_info(topics);")
        columns = cursor.fetchall()
        print("\nUpdated topics table structure:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
            
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error updating database schema: {e}")
        return False

if __name__ == "__main__":
    update_database_schema()
'''
    
    # Write the update script to file
    script_path = os.path.join(os.path.dirname(__file__), 'update_database_schema.py')
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(update_script)
    
    print(f"Created database update script at: {script_path}")
    return script_path

def main():
    print("Creating X platform collection script and database update script...")
    
    # Create the X collection script
    x_script_path = create_x_collection_script()
    
    # Create the database update script
    db_script_path = update_database_schema()
    
    print("\nNext steps:")
    print("1. Review and modify the X collection script as needed:")
    print(f"   {x_script_path}")
    print("\n2. Run the database update script to add the source column:")
    print(f"   python {db_script_path}")
    print("\n3. Run the X collection script:")
    print(f"   python {x_script_path}")

if __name__ == "__main__":
    main()