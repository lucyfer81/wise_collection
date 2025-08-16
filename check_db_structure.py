#!/usr/bin/env python3
import os
import libsql
from dotenv import load_dotenv

load_dotenv()

def check_database_structure():
    """Check the database structure of the Turso database"""
    try:
        # Connect to database
        db_url = os.getenv("TURSO_DB_URL") or os.getenv("DB_URL")
        auth_token = os.getenv("TURSO_DB_AUTH_TOKEN") or os.getenv("DB_AUTH_TOKEN")
        
        print(f"Connecting to database: {db_url}")
        
        conn = libsql.connect(database="", sync_url=db_url, auth_token=auth_token)
        cursor = conn.cursor()
        
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
            
        conn.close()
        
    except Exception as e:
        print(f"Error connecting to database: {e}")

if __name__ == "__main__":
    check_database_structure()