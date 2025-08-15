#!/usr/bin/env python3
import os
import libsql
from dotenv import load_dotenv

load_dotenv()

def check_and_create_tables():
    """检查数据库连接并创建必要的表"""
    try:
        # 连接到数据库
        db_url = os.getenv("TURSO_DB_URL") or os.getenv("DB_URL")
        auth_token = os.getenv("TURSO_DB_AUTH_TOKEN") or os.getenv("DB_AUTH_TOKEN")
        
        print(f"连接到数据库: {db_url}")
        
        conn = libsql.connect(database="", sync_url=db_url, auth_token=auth_token)
        
        # 检查是否已存在topics表
        cursor = conn.cursor()
        
        # 查看所有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"当前数据库中的表: {[table[0] for table in tables]}")
        
        # 如果topics表不存在，创建它
        if not any('topics' in table for table in tables):
            print("创建topics表...")
            
            create_table_sql = """
            CREATE TABLE topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                topic_name TEXT NOT NULL,
                topic_keywords TEXT,
                summary_english TEXT,
                summary_chinese TEXT,
                post_count INTEGER DEFAULT 0,
                avg_score REAL DEFAULT 0.0,
                cluster_id INTEGER,
                file_name TEXT
            );
            """
            
            cursor.execute(create_table_sql)
            conn.commit()
            print("✅ topics表创建成功")
        else:
            print("✅ topics表已存在")
            
        # 检查表结构
        cursor.execute("PRAGMA table_info(topics);")
        columns = cursor.fetchall()
        print("\ntopics表结构:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
            
        # 尝试查询一条数据
        try:
            cursor.execute("SELECT COUNT(*) FROM topics;")
            count = cursor.fetchone()[0]
            print(f"\n表中数据条数: {count}")
            
            if count > 0:
                cursor.execute("SELECT * FROM topics LIMIT 1;")
                sample = cursor.fetchone()
                print(f"示例数据: {sample}")
        except Exception as e:
            print(f"查询数据时出错: {e}")
            
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

if __name__ == "__main__":
    check_and_create_tables()