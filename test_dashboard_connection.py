#!/usr/bin/env python3
"""
Test script to verify Turso database connection for dashboard.py
"""

import libsql
import os
import sys

def test_dashboard_connection():
    """Test the exact connection method used in dashboard.py"""
    
    # Use the same connection logic as dashboard.py
    db_url = "libsql://wisecollection-lucyfer81.aws-ap-northeast-1.turso.io"
    auth_token = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3NTUxNTc0NTIsImlkIjoiOGZmMWFmMjYtY2Y2Yi00YTRhLTg2NjMtOGFlNDliYzA4NTE4IiwicmlkIjoiNDY4NThiNTItYTEyOS00ZDIyLWE1MjgtMzVmMThhYjZlYTgzIn0.7NNB7cN1F_HexlPhTURCSvYvvEhkRxhlKBRNMh-TSoPb_wiwVxk44UEV1hsZOfEoyoW8N7tGoWCFCWNjZMaVDA"
    
    print(f"Testing connection to: {db_url}")
    print(f"Auth token length: {len(auth_token)}")
    
    try:
        # Use the exact same connection method as dashboard.py
        conn = libsql.connect(database="", sync_url=db_url, auth_token=auth_token)
        cursor = conn.cursor()
        
        print("✅ Database connection successful.")
        
        # Test table existence
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Tables found: {tables}")
        
        # Check if topics table exists
        if not any('topics' in table for table in tables):
            print("❌ topics table does not exist")
            return False
        
        # Test the exact query from dashboard.py line 103
        cursor.execute("SELECT id, created_at, topic_name, topic_keywords, summary_english, summary_chinese FROM topics ORDER BY id DESC")
        results = cursor.fetchall()
        print(f"✅ Dashboard query successful! Found {len(results)} records")
        
        if results:
            print(f"Sample record ID: {results[0][0]}, Topic: {results[0][2][:50]}...")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_dashboard_connection()
    sys.exit(0 if success else 1)