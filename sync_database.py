#!/usr/bin/env python3
"""
数据库同步脚本 - 将本地SQLite数据库同步到Turso云端数据库
"""
import sqlite3
import libsql
import os
from dotenv import load_dotenv
import sys
from datetime import datetime

load_dotenv()

def sync_databases():
    """同步本地数据库到云端数据库"""
    try:
        # 连接到本地数据库
        local_conn = sqlite3.connect('topics_database.db')
        local_cursor = local_conn.cursor()
        
        # 连接到云端数据库
        db_url = os.getenv('TURSO_DB_URL', 'libsql://wisecollection-lucyfer81.aws-ap-northeast-1.turso.io')
        auth_token = os.getenv('TURSO_DB_AUTH_TOKEN', 'eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3NTUxNTc0NTIsImlkIjoiOGZmMWFmMjYtY2Y2Yi00YTRhLTg2NjMtOGFlNDliYzA4NTE4IiwicmlkIjoiNDY4NThiNTItYTEyOS00ZDIyLWE1MjgtMzVmMThhYjZlYTgzIn0.7NNB7cN1F_HexlPhTURCSvYvvEhkRxhlKBRNMh-TSoPb_wiwVxk44UEV1hsZOfEoyoW8N7tGoWCFCWNjZMaVDA')
        
        print(f"连接到云端数据库: {db_url}")
        if not db_url or not auth_token:
            print("❌ 错误: 缺少数据库连接信息")
            return False
        
        cloud_conn = libsql.connect(database='', sync_url=db_url, auth_token=auth_token)
        cloud_cursor = cloud_conn.cursor()
        
        print("🔄 开始同步数据库...")
        
        # 检查本地数据
        local_cursor.execute("SELECT COUNT(*) FROM topics;")
        local_count = local_cursor.fetchone()[0]
        print(f"本地数据库: {local_count} 条记录")
        
        # 检查云端表是否存在
        try:
            cloud_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [table[0] for table in cloud_cursor.fetchall()]
            print(f"云端表: {tables}")
            
            if 'topics' not in tables:
                print("📋 创建topics表...")
                cloud_cursor.execute("""
                    CREATE TABLE topics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic_name TEXT NOT NULL,
                        topic_keywords TEXT,
                        summary_english TEXT,
                        summary_chinese TEXT,
                        source_post_ids TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cloud_conn.commit()
                print("✅ topics表创建成功")
                cloud_count = 0
            else:
                cloud_cursor.execute("SELECT COUNT(*) FROM topics;")
                cloud_count = cloud_cursor.fetchone()[0]
                print(f"云端数据库: {cloud_count} 条记录")
                
        except Exception as e:
            print(f"❌ 检查云端表失败: {e}")
            return False
        
        # 获取本地所有数据
        local_cursor.execute("SELECT * FROM topics ORDER BY id;")
        local_data = local_cursor.fetchall()
        
        # 获取云端所有数据
        cloud_cursor.execute("SELECT id FROM topics;")
        cloud_ids = {row[0] for row in cloud_cursor.fetchall()}
        
        # 找出需要同步的记录
        new_records = []
        updated_records = []
        
        for record in local_data:
            record_id = record[0]
            if record_id not in cloud_ids:
                new_records.append(record)
            else:
                # 检查是否需要更新
                cloud_cursor.execute("SELECT * FROM topics WHERE id = ?", (record_id,))
                cloud_record = cloud_cursor.fetchone()
                if record != cloud_record:
                    updated_records.append(record)
        
        print(f"需要新增: {len(new_records)} 条记录")
        print(f"需要更新: {len(updated_records)} 条记录")
        
        # 同步新记录
        for record in new_records:
            try:
                cloud_cursor.execute("""
                    INSERT INTO topics (id, topic_name, topic_keywords, summary_english, summary_chinese, source_post_ids, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, record)
                cloud_conn.commit()
                print(f"✅ 新增记录 ID: {record[0]}")
            except Exception as e:
                print(f"❌ 新增记录失败 ID: {record[0]}, 错误: {e}")
        
        # 同步更新记录
        for record in updated_records:
            try:
                cloud_cursor.execute("""
                    UPDATE topics SET 
                        topic_name = ?, 
                        topic_keywords = ?, 
                        summary_english = ?, 
                        summary_chinese = ?, 
                        source_post_ids = ?, 
                        created_at = ?
                    WHERE id = ?
                """, (record[1], record[2], record[3], record[4], record[5], record[6], record[0]))
                cloud_conn.commit()
                print(f"✅ 更新记录 ID: {record[0]}")
            except Exception as e:
                print(f"❌ 更新记录失败 ID: {record[0]}, 错误: {e}")
        
        # 验证同步结果
        cloud_cursor.execute("SELECT COUNT(*) FROM topics;")
        final_count = cloud_cursor.fetchone()[0]
        print(f"✅ 同步完成！云端数据库现在有 {final_count} 条记录")
        
        # 关闭连接
        local_conn.close()
        cloud_conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ 同步失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = sync_databases()
    sys.exit(0 if success else 1)