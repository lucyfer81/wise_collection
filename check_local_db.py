#!/usr/bin/env python3
import sqlite3
import os

# Connect to the local database file
db_path = os.path.join(os.path.dirname(__file__), 'topics_database.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check if topics table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='topics';")
table_exists = cursor.fetchone()

if table_exists:
    print("Topics table exists in local database.")
    
    # Check table structure
    cursor.execute("PRAGMA table_info(topics);")
    columns = cursor.fetchall()
    
    print("Current topics table structure:")
    for col in columns:
        print(f"  {col[1]} ({col[2]})")
        
    # Check if source column exists and has data
    try:
        cursor.execute("SELECT DISTINCT source FROM topics LIMIT 5;")
        sources = cursor.fetchall()
        print("\nSources in the database:")
        for source in sources:
            print(f"  {source[0]}")
    except Exception as e:
        print(f"\nCould not query source column: {e}")
else:
    print("Topics table does not exist in local database.")

conn.close()