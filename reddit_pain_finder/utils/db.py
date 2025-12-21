"""
Database utilities for Wise Collection
SQLite数据库操作工具
"""
import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
import os

logger = logging.getLogger(__name__)

class WiseCollectionDB:
    """Wise Collection系统数据库管理器"""

    def __init__(self, db_dir: str = "data", unified: bool = True):
        """初始化数据库连接"""
        self.db_dir = db_dir
        self.unified = unified  # 是否使用统一数据库
        os.makedirs(db_dir, exist_ok=True)

        if unified:
            # 使用统一数据库文件
            self.unified_db_path = os.path.join(db_dir, "wise_collection.db")
            # 兼容性：保持原有路径变量
            self.raw_db_path = self.unified_db_path
            self.filtered_db_path = self.unified_db_path
            self.pain_db_path = self.unified_db_path
            self.clusters_db_path = self.unified_db_path
        else:
            # 使用多个数据库文件（原有模式）
            self.raw_db_path = os.path.join(db_dir, "raw_posts.db")
            self.filtered_db_path = os.path.join(db_dir, "filtered_posts.db")
            self.pain_db_path = os.path.join(db_dir, "pain_events.db")
            self.clusters_db_path = os.path.join(db_dir, "clusters.db")

        # 初始化所有数据库
        self._init_databases()

    @contextmanager
    def get_connection(self, db_type: str = "raw"):
        """获取数据库连接的上下文管理器"""
        if self.unified:
            # 统一数据库模式：所有连接都指向同一个文件
            db_path = self.unified_db_path
        else:
            # 多数据库模式：根据db_type选择不同的文件
            db_paths = {
                "raw": self.raw_db_path,
                "filtered": self.filtered_db_path,
                "pain": self.pain_db_path,
                "clusters": self.clusters_db_path
            }

            if db_type not in db_paths:
                raise ValueError(f"Invalid db_type: {db_type}")
            db_path = db_paths[db_type]

        conn = None
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def _init_databases(self):
        """初始化所有数据库表结构"""
        if self.unified:
            self._init_unified_database()
        else:
            self._init_raw_posts_db()
            self._init_filtered_posts_db()
            self._init_pain_events_db()
            self._init_clusters_db()

    def _init_unified_database(self):
        """初始化统一数据库，包含所有表"""
        with self.get_connection("raw") as conn:
            # 创建原始帖子表（升级版 - 支持多数据源）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT,
                    subreddit TEXT,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'reddit',
                    source_id TEXT NOT NULL,
                    platform_data TEXT,
                    score INTEGER NOT NULL,
                    num_comments INTEGER NOT NULL,
                    upvote_ratio REAL,
                    is_self INTEGER,
                    created_utc REAL NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    author TEXT,
                    category TEXT,
                    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    raw_data TEXT,  -- 原始JSON数据
                    UNIQUE(source, source_id)
                )
            """)

            # 创建过滤帖子表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS filtered_posts (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT,
                    subreddit TEXT NOT NULL,
                    url TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    num_comments INTEGER NOT NULL,
                    upvote_ratio REAL NOT NULL,
                    pain_score REAL NOT NULL,
                    pain_keywords TEXT,
                    filtered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    filter_reason TEXT
                )
            """)

            # 创建痛点事件表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pain_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT NOT NULL,
                    actor TEXT,
                    context TEXT,
                    problem TEXT NOT NULL,
                    current_workaround TEXT,
                    frequency TEXT,
                    emotional_signal TEXT,
                    mentioned_tools TEXT,
                    extraction_confidence REAL,
                    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES filtered_posts(id)
                )
            """)

            # 创建嵌入向量表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pain_embeddings (
                    pain_event_id INTEGER PRIMARY KEY,
                    embedding_vector BLOB NOT NULL,
                    embedding_model TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (pain_event_id) REFERENCES pain_events(id)
                )
            """)

            # 创建聚类表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_name TEXT NOT NULL,
                    cluster_description TEXT,
                    source_type TEXT,  -- 新增：数据源类型 (hn_ask, hn_show, reddit, etc.)
                    centroid_summary TEXT,  -- 新增：聚类中心摘要
                    common_pain TEXT,  -- 新增：共同痛点
                    common_context TEXT,  -- 新增：共同上下文
                    example_events TEXT,  -- 新增：代表性事件 (JSON数组)
                    pain_event_ids TEXT NOT NULL,  -- JSON数组
                    cluster_size INTEGER NOT NULL,
                    avg_pain_score REAL,
                    workflow_confidence REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建机会表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_id INTEGER NOT NULL,
                    opportunity_name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    current_tools TEXT,
                    missing_capability TEXT,
                    why_existing_fail TEXT,
                    target_users TEXT,
                    pain_frequency_score REAL,
                    market_size_score REAL,
                    mvp_complexity_score REAL,
                    competition_risk_score REAL,
                    integration_complexity_score REAL,
                    total_score REAL,
                    killer_risks TEXT,  -- JSON数组
                    recommendation TEXT,  -- AI建议：pursue/modify/abandon with reason
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (cluster_id) REFERENCES clusters(id)
                )
            """)

            # 创建跨源对齐问题表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS aligned_problems (
                    id TEXT PRIMARY KEY,  -- aligned_AP_XX_timestamp format
                    aligned_problem_id TEXT UNIQUE,  -- AP_XX format
                    sources TEXT,  -- JSON array of source types
                    core_problem TEXT,
                    why_they_look_different TEXT,
                    evidence TEXT,  -- JSON array of evidence objects
                    cluster_ids TEXT,  -- JSON array of original cluster IDs
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建所有索引
            # posts表索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_score ON posts(score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_collected_at ON posts(collected_at)")

            # 检查新列是否存在，然后创建相应索引
            cursor = conn.execute("PRAGMA table_info(posts)")
            existing_columns = {row['name'] for row in cursor.fetchall()}

            if 'source' in existing_columns:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_source ON posts(source)")

            if 'created_at' in existing_columns:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_source_created ON posts(source, created_at)")

            if 'source' in existing_columns and 'source_id' in existing_columns:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_unique_source ON posts(source, source_id)")

            # filtered_posts表索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filtered_pain_score ON filtered_posts(pain_score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filtered_subreddit ON filtered_posts(subreddit)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filtered_at ON filtered_posts(filtered_at)")

            # pain_events表索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pain_post_id ON pain_events(post_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pain_problem ON pain_events(problem)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pain_extracted_at ON pain_events(extracted_at)")

            # clusters表索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_size ON clusters(cluster_size)")

            # opportunities表索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities(total_score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_cluster_id ON opportunities(cluster_id)")

            # 添加对齐跟踪列到clusters表（如果不存在）
            self._add_alignment_columns_to_clusters(conn)

            conn.commit()
            logger.info("Unified database initialized successfully")

    def _init_raw_posts_db(self):
        """初始化原始帖子数据库"""
        with self.get_connection("raw") as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT,
                    subreddit TEXT,
                    url TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'reddit',
                    source_id TEXT NOT NULL,
                    platform_data TEXT,
                    score INTEGER NOT NULL,
                    num_comments INTEGER NOT NULL,
                    upvote_ratio REAL,
                    is_self INTEGER,
                    created_utc REAL NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    author TEXT,
                    category TEXT,
                    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    raw_data TEXT,  -- 原始JSON数据
                    UNIQUE(source, source_id)
                )
            """)

            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_score ON posts(score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_collected_at ON posts(collected_at)")

            # 检查新列是否存在，然后创建相应索引
            cursor = conn.execute("PRAGMA table_info(posts)")
            existing_columns = {row['name'] for row in cursor.fetchall()}

            if 'source' in existing_columns:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_source ON posts(source)")

            if 'created_at' in existing_columns:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_source_created ON posts(source, created_at)")

            if 'source' in existing_columns and 'source_id' in existing_columns:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_unique_source ON posts(source, source_id)")
            conn.commit()

    def _init_filtered_posts_db(self):
        """初始化过滤后的帖子数据库"""
        with self.get_connection("filtered") as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS filtered_posts (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT,
                    subreddit TEXT NOT NULL,
                    url TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    num_comments INTEGER NOT NULL,
                    upvote_ratio REAL NOT NULL,
                    pain_score REAL NOT NULL,
                    pain_keywords TEXT,
                    filtered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    filter_reason TEXT
                )
            """)

            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filtered_pain_score ON filtered_posts(pain_score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filtered_subreddit ON filtered_posts(subreddit)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filtered_at ON filtered_posts(filtered_at)")
            conn.commit()

    def _init_pain_events_db(self):
        """初始化痛点事件数据库"""
        with self.get_connection("pain") as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pain_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT NOT NULL,
                    actor TEXT,
                    context TEXT,
                    problem TEXT NOT NULL,
                    current_workaround TEXT,
                    frequency TEXT,
                    emotional_signal TEXT,
                    mentioned_tools TEXT,
                    extraction_confidence REAL,
                    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES filtered_posts(id)
                )
            """)

            # 创建嵌入向量表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pain_embeddings (
                    pain_event_id INTEGER PRIMARY KEY,
                    embedding_vector BLOB NOT NULL,
                    embedding_model TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (pain_event_id) REFERENCES pain_events(id)
                )
            """)

            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pain_post_id ON pain_events(post_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pain_problem ON pain_events(problem)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pain_extracted_at ON pain_events(extracted_at)")
            conn.commit()

    def _init_clusters_db(self):
        """初始化聚类数据库"""
        with self.get_connection("clusters") as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_name TEXT NOT NULL,
                    cluster_description TEXT,
                    source_type TEXT,  -- 新增：数据源类型 (hn_ask, hn_show, reddit, etc.)
                    centroid_summary TEXT,  -- 新增：聚类中心摘要
                    common_pain TEXT,  -- 新增：共同痛点
                    common_context TEXT,  -- 新增：共同上下文
                    example_events TEXT,  -- 新增：代表性事件 (JSON数组)
                    pain_event_ids TEXT NOT NULL,  -- JSON数组
                    cluster_size INTEGER NOT NULL,
                    avg_pain_score REAL,
                    workflow_confidence REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建机会表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_id INTEGER NOT NULL,
                    opportunity_name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    current_tools TEXT,
                    missing_capability TEXT,
                    why_existing_fail TEXT,
                    target_users TEXT,
                    pain_frequency_score REAL,
                    market_size_score REAL,
                    mvp_complexity_score REAL,
                    competition_risk_score REAL,
                    integration_complexity_score REAL,
                    total_score REAL,
                    killer_risks TEXT,  -- JSON数组
                    recommendation TEXT,  -- AI建议：pursue/modify/abandon with reason
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (cluster_id) REFERENCES clusters(id)
                )
            """)

            # 创建跨源对齐问题表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS aligned_problems (
                    id TEXT PRIMARY KEY,  -- aligned_AP_XX_timestamp format
                    aligned_problem_id TEXT UNIQUE,  -- AP_XX format
                    sources TEXT,  -- JSON array of source types
                    core_problem TEXT,
                    why_they_look_different TEXT,
                    evidence TEXT,  -- JSON array of evidence objects
                    cluster_ids TEXT,  -- JSON array of original cluster IDs
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_size ON clusters(cluster_size)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities(total_score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_cluster_id ON opportunities(cluster_id)")

            # 添加对齐跟踪列到clusters表（如果不存在）
            self._add_alignment_columns_to_clusters(conn)

            conn.commit()

    def _add_alignment_columns_to_clusters(self, conn):
        """为clusters表添加对齐跟踪列（如果不存在）"""
        try:
            # 检查列是否存在
            cursor = conn.execute("PRAGMA table_info(clusters)")
            existing_columns = {row['name'] for row in cursor.fetchall()}

            # 添加alignment_status列（如果不存在）
            if 'alignment_status' not in existing_columns:
                conn.execute("""
                    ALTER TABLE clusters
                    ADD COLUMN alignment_status TEXT DEFAULT 'unprocessed'
                """)
                logger.info("Added alignment_status column to clusters table")

            # 添加aligned_problem_id列（如果不存在）
            if 'aligned_problem_id' not in existing_columns:
                conn.execute("""
                    ALTER TABLE clusters
                    ADD COLUMN aligned_problem_id TEXT
                """)
                logger.info("Added aligned_problem_id column to clusters table")

            # 创建相关索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_alignment_status ON clusters(alignment_status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_aligned_problem_id ON clusters(aligned_problem_id)")

        except Exception as e:
            logger.error(f"Failed to add alignment columns to clusters table: {e}")

    # Raw posts operations
    def insert_raw_post(self, post_data: Dict[str, Any]) -> bool:
        """插入原始帖子数据（支持多数据源）"""
        try:
            with self.get_connection("raw") as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO posts
                    (id, title, body, subreddit, url, source, source_id, platform_data,
                     score, num_comments, upvote_ratio, is_self, created_utc, created_at,
                     author, category, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    post_data.get("id"),                    # 统一ID (兼容旧数据)
                    post_data["title"],
                    post_data.get("body", ""),
                    post_data.get("subreddit", "unknown"),   # 兼容性：如果没有subreddit，使用unknown
                    post_data["url"],
                    post_data.get("source", "reddit"),      # 新字段，默认为reddit
                    post_data.get("source_id"),             # 新字段
                    json.dumps(post_data.get("platform_data", {})),  # 新字段
                    post_data["score"],
                    post_data["num_comments"],
                    post_data.get("upvote_ratio"),          # 可能为None (新字段)
                    post_data.get("is_self"),               # 可能为None (新字段)
                    post_data.get("created_utc", 0),
                    post_data.get("created_at", datetime.now().isoformat()),  # 新字段
                    post_data.get("author", ""),
                    post_data.get("category", ""),
                    json.dumps(post_data)
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to insert raw post {post_data.get('id')}: {e}")
            return False

    def get_unprocessed_posts(self, limit: int = 100) -> List[Dict]:
        """获取未处理的帖子"""
        try:
            # 首先获取所有已处理的帖子ID
            with self.get_connection("filtered") as conn:
                cursor = conn.execute("SELECT id FROM filtered_posts")
                processed_ids = {row['id'] for row in cursor.fetchall()}

            # 然后获取未处理的帖子
            with self.get_connection("raw") as conn:
                if processed_ids:
                    # 如果有已处理的帖子，排除它们
                    placeholders = ','.join('?' * len(processed_ids))
                    cursor = conn.execute(f"""
                        SELECT * FROM posts
                        WHERE id NOT IN ({placeholders})
                        ORDER BY collected_at DESC
                        LIMIT ?
                    """, list(processed_ids) + [limit])
                else:
                    # 如果没有已处理的帖子，直接获取
                    cursor = conn.execute("""
                        SELECT * FROM posts
                        ORDER BY collected_at DESC
                        LIMIT ?
                    """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get unprocessed posts: {e}")
            return []

    def get_unprocessed_posts_by_source(self, source: str, limit: int = 100) -> List[Dict]:
        """获取未处理的帖子，支持按数据源过滤"""
        try:
            # 首先获取所有已处理的帖子ID
            with self.get_connection("filtered") as conn:
                cursor = conn.execute("SELECT id FROM filtered_posts")
                processed_ids = {row['id'] for row in cursor.fetchall()}

            # 然后获取未处理的帖子，按数据源过滤
            with self.get_connection("raw") as conn:
                if processed_ids:
                    # 如果有已处理的帖子，排除它们
                    placeholders = ','.join('?' * len(processed_ids))
                    cursor = conn.execute(f"""
                        SELECT * FROM posts
                        WHERE source = ?
                        AND id NOT IN ({placeholders})
                        ORDER BY collected_at DESC
                        LIMIT ?
                    """, [source] + list(processed_ids) + [limit])
                else:
                    # 如果没有已处理的帖子，直接获取
                    cursor = conn.execute("""
                        SELECT * FROM posts
                        WHERE source = ?
                        ORDER BY collected_at DESC
                        LIMIT ?
                    """, (source, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get unprocessed posts for source {source}: {e}")
            return []

    # Filtered posts operations
    def insert_filtered_post(self, post_data: Dict[str, Any]) -> bool:
        """插入过滤后的帖子"""
        try:
            with self.get_connection("filtered") as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO filtered_posts
                    (id, title, body, subreddit, url, score, num_comments,
                     upvote_ratio, pain_score, pain_keywords, filter_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    post_data["id"],
                    post_data["title"],
                    post_data.get("body", ""),
                    post_data["subreddit"],
                    post_data["url"],
                    post_data["score"],
                    post_data["num_comments"],
                    post_data.get("upvote_ratio", 0.0),
                    post_data.get("pain_score", 0.0),
                    json.dumps(post_data.get("pain_keywords", [])),
                    post_data.get("filter_reason", "")
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to insert filtered post {post_data.get('id')}: {e}")
            return False

    def get_filtered_posts(self, limit: int = 100, min_pain_score: float = 0.0) -> List[Dict]:
        """获取过滤后的帖子"""
        try:
            # 首先获取所有已提取的帖子ID
            with self.get_connection("pain") as conn:
                cursor = conn.execute("SELECT DISTINCT post_id FROM pain_events")
                extracted_ids = {row['post_id'] for row in cursor.fetchall()}

            # 然后获取过滤后的帖子
            with self.get_connection("filtered") as conn:
                if extracted_ids:
                    # 如果有已提取的帖子，排除它们
                    placeholders = ','.join('?' * len(extracted_ids))
                    cursor = conn.execute(f"""
                        SELECT * FROM filtered_posts
                        WHERE pain_score >= ?
                        AND id NOT IN ({placeholders})
                        ORDER BY pain_score DESC
                        LIMIT ?
                    """, [min_pain_score] + list(extracted_ids) + [limit])
                else:
                    # 如果没有已提取的帖子，直接获取
                    cursor = conn.execute("""
                        SELECT * FROM filtered_posts
                        WHERE pain_score >= ?
                        ORDER BY pain_score DESC
                        LIMIT ?
                    """, (min_pain_score, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get filtered posts: {e}")
            return []

    # Pain events operations
    def insert_pain_event(self, pain_data: Dict[str, Any]) -> Optional[int]:
        """插入痛点事件"""
        try:
            with self.get_connection("pain") as conn:
                cursor = conn.execute("""
                    INSERT INTO pain_events
                    (post_id, actor, context, problem, current_workaround,
                     frequency, emotional_signal, mentioned_tools, extraction_confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pain_data["post_id"],
                    pain_data.get("actor", ""),
                    pain_data.get("context", ""),
                    pain_data["problem"],
                    pain_data.get("current_workaround", ""),
                    pain_data.get("frequency", ""),
                    pain_data.get("emotional_signal", ""),
                    json.dumps(pain_data.get("mentioned_tools", [])),
                    pain_data.get("extraction_confidence", 0.0)
                ))
                pain_event_id = cursor.lastrowid
                conn.commit()
                return pain_event_id
        except Exception as e:
            logger.error(f"Failed to insert pain event: {e}")
            return None

    def insert_pain_embedding(self, pain_event_id: int, embedding_vector: List[float], model_name: str) -> bool:
        """插入痛点嵌入向量"""
        try:
            import pickle
            embedding_blob = pickle.dumps(embedding_vector)

            with self.get_connection("pain") as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO pain_embeddings
                    (pain_event_id, embedding_vector, embedding_model)
                    VALUES (?, ?, ?)
                """, (pain_event_id, embedding_blob, model_name))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to insert pain embedding for event {pain_event_id}: {e}")
            return False

    def get_pain_events_without_embeddings(self, limit: int = 100) -> List[Dict]:
        """获取没有嵌入向量的痛点事件"""
        try:
            with self.get_connection("pain") as conn:
                cursor = conn.execute("""
                    SELECT p.* FROM pain_events p
                    LEFT JOIN pain_embeddings e ON p.id = e.pain_event_id
                    WHERE e.pain_event_id IS NULL
                    ORDER BY p.extracted_at DESC
                    LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get pain events without embeddings: {e}")
            return []

    def get_all_pain_events_with_embeddings(self) -> List[Dict]:
        """获取所有有嵌入向量的痛点事件"""
        try:
            import pickle
            with self.get_connection("pain") as conn:
                cursor = conn.execute("""
                    SELECT p.*, e.embedding_vector, e.embedding_model
                    FROM pain_events p
                    JOIN pain_embeddings e ON p.id = e.pain_event_id
                    ORDER BY p.extracted_at DESC
                """)
                results = []
                for row in cursor.fetchall():
                    event_data = dict(row)
                    # 反序列化嵌入向量
                    if event_data["embedding_vector"]:
                        event_data["embedding_vector"] = pickle.loads(event_data["embedding_vector"])
                    results.append(event_data)
                return results
        except Exception as e:
            logger.error(f"Failed to get pain events with embeddings: {e}")
            return []

    # Clusters operations
    def insert_cluster(self, cluster_data: Dict[str, Any]) -> Optional[int]:
        """插入聚类"""
        try:
            with self.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    INSERT INTO clusters
                    (cluster_name, cluster_description, source_type, centroid_summary,
                     common_pain, common_context, example_events, pain_event_ids, cluster_size,
                     avg_pain_score, workflow_confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cluster_data["cluster_name"],
                    cluster_data.get("cluster_description", ""),
                    cluster_data.get("source_type", ""),
                    cluster_data.get("centroid_summary", ""),
                    cluster_data.get("common_pain", ""),
                    cluster_data.get("common_context", ""),
                    json.dumps(cluster_data.get("example_events", [])),
                    json.dumps(cluster_data["pain_event_ids"]),
                    cluster_data["cluster_size"],
                    cluster_data.get("avg_pain_score", 0.0),
                    cluster_data.get("workflow_confidence", 0.0)
                ))
                cluster_id = cursor.lastrowid
                conn.commit()
                return cluster_id
        except Exception as e:
            logger.error(f"Failed to insert cluster: {e}")
            return None

    def insert_opportunity(self, opportunity_data: Dict[str, Any]) -> Optional[int]:
        """插入机会"""
        try:
            with self.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    INSERT INTO opportunities
                    (cluster_id, opportunity_name, description, current_tools,
                     missing_capability, why_existing_fail, target_users,
                     pain_frequency_score, market_size_score, mvp_complexity_score,
                     competition_risk_score, integration_complexity_score, total_score, killer_risks, recommendation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    opportunity_data["cluster_id"],
                    opportunity_data["opportunity_name"],
                    opportunity_data["description"],
                    opportunity_data.get("current_tools", ""),
                    opportunity_data.get("missing_capability", ""),
                    opportunity_data.get("why_existing_fail", ""),
                    opportunity_data.get("target_users", ""),
                    opportunity_data.get("pain_frequency_score", 0.0),
                    opportunity_data.get("market_size_score", 0.0),
                    opportunity_data.get("mvp_complexity_score", 0.0),
                    opportunity_data.get("competition_risk_score", 0.0),
                    opportunity_data.get("integration_complexity_score", 0.0),
                    opportunity_data.get("total_score", 0.0),
                    json.dumps(opportunity_data.get("killer_risks", [])),
                    opportunity_data.get("recommendation", "")
                ))
                opportunity_id = cursor.lastrowid
                conn.commit()
                return opportunity_id
        except Exception as e:
            logger.error(f"Failed to insert opportunity: {e}")
            return None

    def get_top_opportunities(self, limit: int = 20) -> List[Dict]:
        """获取最高分的机会"""
        try:
            with self.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT o.*, c.cluster_name, c.cluster_description
                    FROM opportunities o
                    JOIN clusters c ON o.cluster_id = c.id
                    ORDER BY o.total_score DESC
                    LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get top opportunities: {e}")
            return []

    # Statistics operations
    def get_statistics(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        stats = {}

        try:
            # Raw posts count
            with self.get_connection("raw") as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM posts")
                stats["raw_posts_count"] = cursor.fetchone()["count"]

            # Filtered posts count
            with self.get_connection("filtered") as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM filtered_posts")
                stats["filtered_posts_count"] = cursor.fetchone()["count"]

                cursor = conn.execute("SELECT AVG(pain_score) as avg_score FROM filtered_posts")
                stats["avg_pain_score"] = cursor.fetchone()["avg_score"] or 0

            # Pain events count
            with self.get_connection("pain") as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM pain_events")
                stats["pain_events_count"] = cursor.fetchone()["count"]

            # Clusters count
            with self.get_connection("clusters") as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM clusters")
                stats["clusters_count"] = cursor.fetchone()["count"]

                cursor = conn.execute("SELECT COUNT(*) as count FROM opportunities")
                stats["opportunities_count"] = cursor.fetchone()["count"]

            # 按数据源统计原始帖子
            with self.get_connection("raw") as conn:
                cursor = conn.execute("""
                    SELECT source, COUNT(*) as count
                    FROM posts
                    GROUP BY source
                """)
                stats["posts_by_source"] = {row['source']: row['count'] for row in cursor.fetchall()}

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")

        return stats

# 添加一些便利方法
    def is_unified(self) -> bool:
        """检查是否使用统一数据库"""
        return self.unified

    def get_database_path(self) -> str:
        """获取当前使用的数据库路径"""
        return self.unified_db_path if self.unified else "Multiple DB files"

    def switch_to_unified(self):
        """切换到统一数据库模式（需要重启应用）"""
        if not self.unified:
            logger.warning("Switch to unified database mode requires application restart")
            logger.info("Please create a new WiseCollectionDB(unified=True) instance")

    def get_cross_table_stats(self) -> Dict[str, Any]:
        """获取跨表统计信息（仅在统一模式下有效）"""
        if not self.unified:
            logger.warning("Cross-table stats only available in unified mode")
            return {}

        stats = {}
        try:
            with self.get_connection("raw") as conn:
                # 获取各表的记录数
                tables = ['posts', 'filtered_posts', 'pain_events', 'clusters', 'opportunities']
                for table in tables:
                    cursor = conn.execute(f"SELECT COUNT(*) as count FROM {table}")
                    stats[f"{table}_count"] = cursor.fetchone()["count"]

                # 获取一些跨表的关联统计
                # 有多少filtered_posts有对应的pain_events
                cursor = conn.execute("""
                    SELECT COUNT(DISTINCT p.id) as count
                    FROM filtered_posts p
                    JOIN pain_events pe ON p.id = pe.post_id
                """)
                stats["filtered_with_pain_events"] = cursor.fetchone()["count"]

                # 平均每个cluster有多少opportunities
                cursor = conn.execute("""
                    SELECT AVG(opp_count) as avg_opportunities
                    FROM (
                        SELECT COUNT(o.id) as opp_count
                        FROM clusters c
                        LEFT JOIN opportunities o ON c.id = o.cluster_id
                        GROUP BY c.id
                    )
                """)
                result = cursor.fetchone()
                stats["avg_opportunities_per_cluster"] = result["avg_opportunities"] or 0

        except Exception as e:
            logger.error(f"Failed to get cross-table stats: {e}")

        return stats


# 全局数据库实例（使用统一数据库）
db = WiseCollectionDB(unified=True)

# 保持向后兼容的多数据库实例
db_multi = WiseCollectionDB(unified=False)