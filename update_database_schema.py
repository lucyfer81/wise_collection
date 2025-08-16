#!/usr/bin/env python3
"""
Script to update the database schema to include a source column
"""
import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

def update_local_database():
    """Update local SQLite database to include source column"""
    try:
        # Connect to local database
        db_path = os.path.join(os.path.dirname(__file__), 'topics_database.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if source column already exists
        cursor.execute("PRAGMA table_info(topics);")
        columns = cursor.fetchall()
        source_column_exists = any(col[1] == 'source' for col in columns)
        
        if not source_column_exists:
            print("Adding 'source' column to local topics table...")
            # Add source column with default value 'reddit'
            cursor.execute("ALTER TABLE topics ADD COLUMN source TEXT DEFAULT 'reddit';")
            conn.commit()
            print("✅ Source column added successfully to local database")
        else:
            print("✅ Source column already exists in local database")
            
        # Update existing records to have 'reddit' as source
        cursor.execute("UPDATE topics SET source = 'reddit' WHERE source IS NULL;")
        conn.commit()
        print("✅ Updated existing records with 'reddit' as source in local database")
        
        # Verify the changes
        cursor.execute("PRAGMA table_info(topics);")
        columns = cursor.fetchall()
        print("\nUpdated local topics table structure:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
            
        # Check sources in the database
        cursor.execute("SELECT DISTINCT source FROM topics LIMIT 5;")
        sources = cursor.fetchall()
        print("\nSources in the local database:")
        for source in sources:
            print(f"  {source[0]}")
            
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error updating local database schema: {e}")
        return False

def update_turso_database():
    """Update Turso database to include source column"""
    try:
        # Connect to Turso database
        import libsql
        db_url = os.getenv("TURSO_DB_URL") or os.getenv("DB_URL")
        auth_token = os.getenv("TURSO_DB_AUTH_TOKEN") or os.getenv("DB_AUTH_TOKEN")
        
        print(f"Connecting to Turso database: {db_url}")
        
        conn = libsql.connect(database="", sync_url=db_url, auth_token=auth_token)
        cursor = conn.cursor()
        
        # Check if source column already exists
        cursor.execute("PRAGMA table_info(topics);")
        columns = cursor.fetchall()
        source_column_exists = any(col[1] == 'source' for col in columns)
        
        if not source_column_exists:
            print("Adding 'source' column to Turso topics table...")
            # Add source column with default value 'reddit'
            cursor.execute("ALTER TABLE topics ADD COLUMN source TEXT DEFAULT 'reddit';")
            conn.commit()
            print("✅ Source column added successfully to Turso database")
        else:
            print("✅ Source column already exists in Turso database")
            
        # Update existing records to have 'reddit' as source
        cursor.execute("UPDATE topics SET source = 'reddit' WHERE source IS NULL;")
        conn.commit()
        print("✅ Updated existing records with 'reddit' as source in Turso database")
        
        # Verify the changes
        cursor.execute("PRAGMA table_info(topics);")
        columns = cursor.fetchall()
        print("\nUpdated Turso topics table structure:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
            
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error updating Turso database schema: {e}")
        return False

def main():
    print("--- Updating Database Schema ---")
    
    # Update local database
    print("\n1. Updating local database...")
    local_success = update_local_database()
    
    # Update Turso database
    print("\n2. Updating Turso database...")
    turso_success = update_turso_database()
    
    if local_success and turso_success:
        print("\n✅ Both databases updated successfully!")
    elif local_success:
        print("\n✅ Local database updated successfully (Turso update failed)")
    elif turso_success:
        print("\n✅ Turso database updated successfully (Local update failed)")
    else:
        print("\n❌ Both database updates failed")

if __name__ == "__main__":
    main()