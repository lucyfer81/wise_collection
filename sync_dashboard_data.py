#!/usr/bin/env python3
"""
Dashboard data sync script - sync data to Turso in a way that libsql can see
"""

import subprocess
import json
import sqlite3
import tempfile
import os

def sync_for_dashboard():
    """Sync data in a way that libsql client can see"""
    
    print("🔄 开始为dashboard同步数据...")
    
    # Get data from local database
    local_conn = sqlite3.connect('topics_database.db')
    local_cursor = local_conn.cursor()
    
    local_cursor.execute("SELECT COUNT(*) FROM topics;")
    local_count = local_cursor.fetchone()[0]
    print(f"本地数据库: {local_count} 条记录")
    
    if local_count == 0:
        print("❌ 本地数据库没有数据")
        return False
    
    # Get all data
    local_cursor.execute("""
        SELECT id, topic_name, topic_keywords, summary_english, summary_chinese, source_post_ids, created_at
        FROM topics ORDER BY id
    """)
    data = local_cursor.fetchall()
    local_conn.close()
    
    # Create a temporary SQL file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
        f.write("-- Dashboard data sync\n")
        f.write("DROP TABLE IF EXISTS topics;\n")
        f.write("""
CREATE TABLE topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_name TEXT NOT NULL,
    topic_keywords TEXT,
    summary_english TEXT,
    summary_chinese TEXT,
    source_post_ids TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);\n""")
        
        for row in data:
            # Escape single quotes in text fields
            escaped_row = []
            for item in row:
                if isinstance(item, str):
                    escaped_row.append(item.replace("'", "''"))
                else:
                    escaped_row.append(item)
            
            f.write(f"INSERT INTO topics VALUES ({escaped_row[0]}, '{escaped_row[1]}', '{escaped_row[2]}', '{escaped_row[3]}', '{escaped_row[4]}', '{escaped_row[5]}', '{escaped_row[6]}');\n")
        
        temp_file = f.name
    
    try:
        # Use turso CLI to import the data
        print("📤 使用Turso CLI导入数据...")
        result = subprocess.run([
            '/home/ubuntu/.turso/turso', 'db', 'shell', 'wisecollection', 
            f'.read {temp_file}'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ 数据同步成功")
            
            # Verify the data
            verify_result = subprocess.run([
                '/home/ubuntu/.turso/turso', 'db', 'shell', 'wisecollection', 
                'SELECT COUNT(*) FROM topics;'
            ], capture_output=True, text=True)
            
            if verify_result.returncode == 0:
                count_line = verify_result.stdout.strip()
                print(f"✅ 验证成功: {count_line}")
                
                # Clean up
                os.unlink(temp_file)
                return True
            else:
                print(f"❌ 验证失败: {verify_result.stderr}")
        else:
            print(f"❌ 同步失败: {result.stderr}")
    
    except Exception as e:
        print(f"❌ 同步过程出错: {e}")
    
    # Clean up
    if os.path.exists(temp_file):
        os.unlink(temp_file)
    
    return False

if __name__ == "__main__":
    success = sync_for_dashboard()
    if success:
        print("🎉 Dashboard数据同步完成！")
    else:
        print("❌ Dashboard数据同步失败！")