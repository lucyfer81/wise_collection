# test_dashboard_connection.py - Fixed version
import os
import libsql_experimental as libsql
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database credentials from environment
TURSO_DB_URL = os.getenv("TURSO_DB_URL")
TURSO_DB_AUTH_TOKEN = os.getenv("TURSO_DB_AUTH_TOKEN")

print(f"Testing connection to: {TURSO_DB_URL}")
print(f"Auth token length: {len(TURSO_DB_AUTH_TOKEN) if TURSO_DB_AUTH_TOKEN else 0}")

try:
    # Connect to the database
    conn = libsql.connect("test.db", sync_url=TURSO_DB_URL, auth_token=TURSO_DB_AUTH_TOKEN)
    print("✅ Database connection successful.")
    
    # List tables
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"Tables found: {tables}")
    
    # Check if topics table exists
    topics_table_exists = any('topics' in table for table in tables)
    if topics_table_exists:
        print("✅ topics table exists")
        # Count records
        cursor.execute("SELECT COUNT(*) FROM topics;")
        count = cursor.fetchone()[0]
        print(f"Record count: {count}")
    else:
        print("❌ topics table does not exist")
        
    conn.close()
    
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    exit(1)