"""
Database utilities for Wise Collection
SQLite数据库操作工具
"""
import sqlite3
import json
import logging
import hashlib
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
                    trust_level REAL DEFAULT 0.5,
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
                    filter_reason TEXT,
                    aspiration_keywords TEXT,
                    aspiration_score REAL DEFAULT 0.0,
                    pass_type TEXT DEFAULT 'pain',
                    engagement_score REAL DEFAULT 0.0,
                    trust_level REAL DEFAULT 0.5
                )
            """)

            # 创建痛点事件表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pain_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT NOT NULL,
                    cluster_id INTEGER,
                    actor TEXT,
                    context TEXT,
                    problem TEXT NOT NULL,
                    current_workaround TEXT,
                    frequency TEXT,
                    emotional_signal TEXT,
                    mentioned_tools TEXT,
                    extraction_confidence REAL,
                    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES filtered_posts(id),
                    FOREIGN KEY (cluster_id) REFERENCES clusters(id)
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
                    workflow_similarity REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    -- JTBD产品语义字段
                    job_statement TEXT,
                    job_steps TEXT,
                    desired_outcomes TEXT,
                    job_context TEXT,
                    customer_profile TEXT,
                    semantic_category TEXT,
                    product_impact REAL DEFAULT 0.0
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
                    alignment_score REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建评论表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_comment_id TEXT NOT NULL,
                    author TEXT,
                    body TEXT NOT NULL,
                    score INTEGER DEFAULT 0,
                    created_utc REAL,
                    created_at TIMESTAMP,
                    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                    UNIQUE(source, source_comment_id)
                )
            """)

            # 创建过滤评论表（Phase 1: Include Comments）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS filtered_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    comment_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    post_id TEXT NOT NULL,
                    author TEXT,
                    body TEXT NOT NULL,
                    score INTEGER DEFAULT 0,
                    pain_score REAL DEFAULT 0.0,
                    pain_keywords TEXT,
                    filter_reason TEXT,
                    engagement_score REAL DEFAULT 0.0,
                    filtered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (comment_id) REFERENCES comments(id),
                    FOREIGN KEY (post_id) REFERENCES posts(id),
                    UNIQUE(comment_id)
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

            # comments表索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_id_score ON comments(post_id, score DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_source ON comments(source)")

            # filtered_comments表索引（Phase 1: Include Comments）
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filtered_comments_post_id ON filtered_comments(post_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filtered_comments_score ON filtered_comments(score DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_filtered_comments_pain_score ON filtered_comments(pain_score DESC)")

            # 添加对齐跟踪列到clusters表（如果不存在）
            self._add_alignment_columns_to_clusters(conn)

            # 添加trust_level列到posts表（如果不存在）
            self._add_trust_level_column(conn)

            # 添加cluster_id列到pain_events表（如果不存在）
            self._add_cluster_id_column(conn)

            # 添加workflow_similarity列到clusters表（如果不存在）
            self._add_workflow_similarity_column(conn)

            # 添加alignment_score列到aligned_problems表（如果不存在）
            self._add_alignment_score_column(conn)

            # 添加Phase 2字段到filtered_posts表（如果不存在）
            self._add_phase2_filtered_posts_columns(conn)

            # 添加Phase 3字段到opportunities表（如果不存在）
            self._add_phase3_opportunities_columns(conn)

            # 添加JTBD字段到clusters表（如果不存在）
            self._add_jtbd_columns(conn)

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
                    trust_level REAL DEFAULT 0.5,
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

            # 添加trust_level列到posts表（如果不存在）
            self._add_trust_level_column(conn)

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
                    workflow_similarity REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    -- JTBD产品语义字段
                    job_statement TEXT,
                    job_steps TEXT,
                    desired_outcomes TEXT,
                    job_context TEXT,
                    customer_profile TEXT,
                    semantic_category TEXT,
                    product_impact REAL DEFAULT 0.0
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
                    alignment_score REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_size ON clusters(cluster_size)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities(total_score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_cluster_id ON opportunities(cluster_id)")

            # 添加对齐跟踪列到clusters表（如果不存在）
            self._add_alignment_columns_to_clusters(conn)

            # 添加workflow_similarity列到clusters表（如果不存在）
            self._add_workflow_similarity_column(conn)

            # 添加alignment_score列到aligned_problems表（如果不存在）
            self._add_alignment_score_column(conn)

            # 添加Phase 3字段到opportunities表（如果不存在）
            self._add_phase3_opportunities_columns(conn)

            # 添加JTBD字段到clusters表（如果不存在）
            self._add_jtbd_columns(conn)

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

    def _add_trust_level_column(self, conn):
        """Add trust_level column to posts table if not exists"""
        try:
            cursor = conn.execute("PRAGMA table_info(posts)")
            existing_columns = {row['name'] for row in cursor.fetchall()}

            if 'trust_level' not in existing_columns:
                conn.execute("""
                    ALTER TABLE posts
                    ADD COLUMN trust_level REAL DEFAULT 0.5
                """)
                logger.info("Added trust_level column to posts table")

                # Migrate existing data: set trust_level based on category
                category_trust_levels = {
                    'core': 0.9,
                    'secondary': 0.7,
                    'verticals': 0.6,
                    'experimental': 0.4
                }

                for category, level in category_trust_levels.items():
                    conn.execute("""
                        UPDATE posts
                        SET trust_level = ?
                        WHERE category = ?
                    """, (level, category))

                logger.info("Migrated trust_level for existing posts")

        except Exception as e:
            logger.error(f"Failed to add trust_level column: {e}")

    def _add_workflow_similarity_column(self, conn):
        """Add workflow_similarity column to clusters table if not exists"""
        try:
            cursor = conn.execute("PRAGMA table_info(clusters)")
            existing_columns = {row['name'] for row in cursor.fetchall()}

            if 'workflow_similarity' not in existing_columns:
                conn.execute("""
                    ALTER TABLE clusters
                    ADD COLUMN workflow_similarity REAL DEFAULT 0.0
                """)
                logger.info("Added workflow_similarity column to clusters table")

                # For existing clusters, migrate workflow_confidence to workflow_similarity
                conn.execute("""
                    UPDATE clusters
                    SET workflow_similarity = COALESCE(workflow_confidence, 0.0)
                """)
                logger.info("Migrated workflow_confidence to workflow_similarity")

        except Exception as e:
            logger.error(f"Failed to add workflow_similarity column: {e}")

    def _add_cluster_id_column(self, conn):
        """Add cluster_id column to pain_events table if not exists"""
        try:
            cursor = conn.execute("PRAGMA table_info(pain_events)")
            existing_columns = {row['name'] for row in cursor.fetchall()}

            if 'cluster_id' not in existing_columns:
                conn.execute("""
                    ALTER TABLE pain_events
                    ADD COLUMN cluster_id INTEGER
                """)
                logger.info("Added cluster_id column to pain_events table")

                # Create index for faster queries
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pain_events_cluster_id
                    ON pain_events(cluster_id)
                """)
                logger.info("Created index on pain_events.cluster_id")

                # Note: Existing pain_events will have NULL cluster_id
                # They will be processed in next clustering run
                logger.info("Existing pain_events marked for re-clustering (cluster_id=NULL)")

        except Exception as e:
            logger.error(f"Failed to add cluster_id column: {e}")

    def _add_alignment_score_column(self, conn):
        """Add alignment_score column to aligned_problems table if not exists"""
        try:
            cursor = conn.execute("PRAGMA table_info(aligned_problems)")
            existing_columns = {row['name'] for row in cursor.fetchall()}

            if 'alignment_score' not in existing_columns:
                conn.execute("""
                    ALTER TABLE aligned_problems
                    ADD COLUMN alignment_score REAL DEFAULT 0.0
                """)
                logger.info("Added alignment_score column to aligned_problems table")

                # Existing alignments get default high score
                conn.execute("""
                    UPDATE aligned_problems
                    SET alignment_score = 0.85
                    WHERE alignment_score = 0.0
                """)
                logger.info("Set default alignment_score for existing aligned problems")

        except Exception as e:
            logger.error(f"Failed to add alignment_score column: {e}")

    def _add_phase2_filtered_posts_columns(self, conn):
        """Add Phase 2 aspiration and trust columns to filtered_posts table if not exist"""
        try:
            cursor = conn.execute("PRAGMA table_info(filtered_posts)")
            existing_columns = {row['name'] for row in cursor.fetchall()}

            new_columns = {
                'aspiration_keywords': 'TEXT',
                'aspiration_score': 'REAL DEFAULT 0.0',
                'pass_type': 'TEXT DEFAULT \'pain\'',
                'engagement_score': 'REAL DEFAULT 0.0',
                'trust_level': 'REAL DEFAULT 0.5'
            }

            for column_name, column_def in new_columns.items():
                if column_name not in existing_columns:
                    conn.execute(f"""
                        ALTER TABLE filtered_posts
                        ADD COLUMN {column_name} {column_def}
                    """)
                    logger.info(f"Added {column_name} column to filtered_posts table")

        except Exception as e:
            logger.error(f"Failed to add Phase 2 columns to filtered_posts table: {e}")

    def _add_phase3_opportunities_columns(self, conn):
        """Add Phase 3 scoring columns to opportunities table if not exist"""
        try:
            cursor = conn.execute("PRAGMA table_info(opportunities)")
            existing_columns = {row['name'] for row in cursor.fetchall()}

            new_columns = {
                'raw_total_score': 'REAL DEFAULT 0.0',
                'trust_level': 'REAL DEFAULT 0.5',
                'scoring_breakdown': 'TEXT'  # JSON格式存储详细计算过程
            }

            for column_name, column_def in new_columns.items():
                if column_name not in existing_columns:
                    conn.execute(f"""
                        ALTER TABLE opportunities
                        ADD COLUMN {column_name} {column_def}
                    """)
                    logger.info(f"Added {column_name} column to opportunities table")

        except Exception as e:
            logger.error(f"Failed to add Phase 3 columns to opportunities table: {e}")

    def _add_jtbd_columns(self, conn):
        """为clusters表添加JTBD产品语义字段（如果不存在）"""
        try:
            cursor = conn.execute("PRAGMA table_info(clusters)")
            existing_columns = {row['name'] for row in cursor.fetchall()}

            jtbd_columns = {
                'job_statement': 'TEXT',
                'job_steps': 'TEXT',  # JSON数组
                'desired_outcomes': 'TEXT',  # JSON数组
                'job_context': 'TEXT',
                'customer_profile': 'TEXT',
                'semantic_category': 'TEXT',
                'product_impact': 'REAL DEFAULT 0.0'
            }

            for column_name, column_def in jtbd_columns.items():
                if column_name not in existing_columns:
                    conn.execute(f"""
                        ALTER TABLE clusters
                        ADD COLUMN {column_name} {column_def}
                    """)
                    logger.info(f"Added {column_name} column to clusters table")

            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_semantic_category ON clusters(semantic_category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_product_impact ON clusters(product_impact)")

        except Exception as e:
            logger.error(f"Failed to add JTBD columns to clusters table: {e}")

    # Raw posts operations
    def insert_raw_post(self, post_data: Dict[str, Any]) -> bool:
        """插入原始帖子数据（支持多数据源）"""
        try:
            with self.get_connection("raw") as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO posts
                    (id, title, body, subreddit, url, source, source_id, platform_data,
                     score, num_comments, upvote_ratio, is_self, created_utc, created_at,
                     author, category, trust_level, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    post_data.get("trust_level", 0.5),      # 新字段，默认0.5
                    json.dumps(post_data)
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to insert raw post {post_data.get('id')}: {e}")
            return False

    def insert_comments(self, post_id: str, comments: List[Dict[str, Any]], source: str) -> int:
        """批量插入评论数据

        Args:
            post_id: 帖子ID
            comments: 评论列表，每个评论是包含 id, author, body, score, created_utc, created_at 的字典
            source: 数据源 ('reddit' 或 'hackernews')

        Returns:
            成功处理的评论数量（注意：由于使用 INSERT OR IGNORE，重复的评论会被跳过）
        """
        try:
            with self.get_connection("raw") as conn:
                inserted_count = 0
                for comment in comments:
                    comment_id = comment.get("id")

                    # 异常检测：记录缺失ID的评论
                    if comment_id is None:
                        logger.warning(
                            f"Comment for post {post_id} from {source} is missing a source ID. "
                            f"Author: {comment.get('author', 'unknown')}. "
                            f"Generating fallback ID."
                        )
                        # Fallback ID - use deterministic MD5 hash instead of Python's hash()
                        body_hash = hashlib.md5(comment.get('body', '').encode('utf-8')).hexdigest()[:12]
                        comment_id = f"{source}_{comment.get('author', 'unknown')}_{body_hash}"

                    conn.execute("""
                        INSERT OR IGNORE INTO comments
                        (post_id, source, source_comment_id, author, body, score, created_utc, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        post_id,
                        source,
                        comment_id,
                        comment.get("author", ""),
                        comment.get("body", ""),
                        comment.get("score", 0),
                        comment.get("created_utc"),
                        comment.get("created_at")
                    ))
                    # Count the comment as processed (INSERT OR IGNORE silently skips duplicates)
                    inserted_count += 1
                conn.commit()
                return inserted_count
        except Exception as e:
            logger.error(f"Failed to insert comments for post {post_id}: {e}")
            return 0

    def get_unprocessed_posts(self, limit: int = 100) -> List[Dict]:
        """获取未处理的帖子"""
        try:
            # 使用 NOT EXISTS 而不是 NOT IN，以正确处理 NULL 值
            with self.get_connection("raw") as conn:
                cursor = conn.execute("""
                    SELECT * FROM posts
                    WHERE NOT EXISTS (
                        SELECT 1 FROM filtered_posts
                        WHERE filtered_posts.id = posts.id
                    )
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
            # 使用 NOT EXISTS 而不是 NOT IN，以正确处理 NULL 值
            with self.get_connection("raw") as conn:
                cursor = conn.execute("""
                    SELECT * FROM posts
                    WHERE source = ?
                    AND NOT EXISTS (
                        SELECT 1 FROM filtered_posts
                        WHERE filtered_posts.id = posts.id
                    )
                    ORDER BY collected_at DESC
                    LIMIT ?
                """, (source, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get unprocessed posts for source {source}: {e}")
            return []

    def get_top_comments_for_post(self, post_id: str, top_n: int = 10) -> List[Dict[str, Any]]:
        """获取指定帖子的Top N高赞评论

        Args:
            post_id: 帖子ID
            top_n: 返回评论数量，默认10条

        Returns:
            评论列表，按score降序排列
        """
        try:
            with self.get_connection("raw") as conn:
                cursor = conn.execute("""
                    SELECT source_comment_id, author, body, score
                    FROM comments
                    WHERE post_id = ?
                    ORDER BY score DESC
                    LIMIT ?
                """, (post_id, top_n))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get comments for post {post_id}: {e}")
            return []

    def get_all_comments_for_filtering(self, limit: int = None) -> List[Dict[str, Any]]:
        """获取所有需要过滤的评论（Phase 1: Include Comments）

        Args:
            limit: 限制返回数量，None表示返回所有

        Returns:
            评论列表，包含comment相关信息和parent post信息
        """
        try:
            with self.get_connection("raw") as conn:
                query = """
                    SELECT c.id, c.post_id, c.source, c.author, c.body, c.score,
                           p.subreddit, p.title as post_title
                    FROM comments c
                    JOIN posts p ON c.post_id = p.id
                    WHERE c.id NOT IN (
                        SELECT comment_id FROM filtered_comments
                    )
                    ORDER BY c.score DESC
                """
                if limit:
                    query += f" LIMIT {limit}"

                cursor = conn.execute(query)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get comments for filtering: {e}")
            return []

    def save_filtered_comments(self, comments: List[Dict[str, Any]]) -> int:
        """保存通过过滤的评论（Phase 1: Include Comments）

        Args:
            comments: 通过过滤的评论列表

        Returns:
            成功保存的评论数量
        """
        try:
            with self.get_connection("filtered") as conn:
                count = 0
                for comment in comments:
                    conn.execute("""
                        INSERT OR IGNORE INTO filtered_comments
                        (comment_id, source, post_id, author, body, score,
                         pain_score, pain_keywords, filter_reason, engagement_score)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        comment["comment_id"],
                        comment["source"],
                        comment["post_id"],
                        comment.get("author"),
                        comment["body"],
                        comment["score"],
                        comment["pain_score"],
                        json.dumps(comment.get("pain_keywords", [])),
                        comment["filter_reason"],
                        comment.get("engagement_score", 0.0)
                    ))
                    count += 1
                conn.commit()
                return count
        except Exception as e:
            logger.error(f"Failed to save filtered comments: {e}")
            return 0

    # Filtered posts operations
    def insert_filtered_post(self, post_data: Dict[str, Any]) -> bool:
        """插入过滤后的帖子"""
        try:
            # 验证 ID 不为空或 NULL
            post_id = post_data.get("id")
            if not post_id or post_id.strip() == "":
                logger.error(f"Invalid post ID: '{post_id}'. Skipping insertion.")
                return False

            with self.get_connection("filtered") as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO filtered_posts
                    (id, title, body, subreddit, url, score, num_comments,
                     upvote_ratio, pain_score, pain_keywords, filter_reason,
                     aspiration_keywords, aspiration_score, pass_type, engagement_score, trust_level, author)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    post_id,
                    post_data["title"],
                    post_data.get("body", ""),
                    post_data["subreddit"],
                    post_data["url"],
                    post_data["score"],
                    post_data["num_comments"],
                    post_data.get("upvote_ratio", 0.0),
                    post_data.get("pain_score", 0.0),
                    json.dumps(post_data.get("pain_keywords", [])),
                    post_data.get("filter_reason", ""),
                    json.dumps(post_data.get("aspiration_keywords", [])),
                    post_data.get("aspiration_score", 0.0),
                    post_data.get("pass_type", "pain"),
                    post_data.get("engagement_score", 0.0),
                    post_data.get("trust_level", 0.5),
                    post_data.get("author", "")
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
        """插入聚类（包含JTBD字段）"""
        try:
            with self.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    INSERT INTO clusters
                    (cluster_name, cluster_description, source_type, centroid_summary,
                     common_pain, common_context, example_events, pain_event_ids, cluster_size,
                     avg_pain_score, workflow_confidence, workflow_similarity,
                     job_statement, job_steps, desired_outcomes, job_context,
                     customer_profile, semantic_category, product_impact)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    cluster_data.get("workflow_confidence", 0.0),
                    cluster_data.get("workflow_similarity", 0.0),
                    cluster_data.get("job_statement"),  # JTBD fields
                    json.dumps(cluster_data.get("job_steps", [])),
                    json.dumps(cluster_data.get("desired_outcomes", [])),
                    cluster_data.get("job_context"),
                    cluster_data.get("customer_profile"),
                    cluster_data.get("semantic_category"),
                    cluster_data.get("product_impact", 0.0)
                ))
                cluster_id = cursor.lastrowid
                conn.commit()
                return cluster_id
        except Exception as e:
            logger.error(f"Failed to insert cluster: {e}")
            return None

    def update_pain_event_cluster_ids(self, event_ids: List[int], cluster_id: int) -> bool:
        """批量更新 pain events 的 cluster_id

        Args:
            event_ids: pain event ID列表
            cluster_id: 要设置的cluster ID

        Returns:
            bool: 是否成功更新
        """
        try:
            if not event_ids:
                logger.warning("No event IDs provided for cluster assignment")
                return False

            with self.get_connection("pain") as conn:
                placeholders = ','.join('?' for _ in event_ids)
                conn.execute(f"""
                    UPDATE pain_events
                    SET cluster_id = ?
                    WHERE id IN ({placeholders})
                """, [cluster_id] + event_ids)
                conn.commit()

                logger.info(f"Assigned {len(event_ids)} pain events to cluster {cluster_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to update cluster IDs for pain events: {e}")
            return False

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

                # 对齐统计
                cursor = conn.execute("SELECT COUNT(*) as count FROM aligned_problems")
                stats["aligned_problems_count"] = cursor.fetchone()["count"]

                cursor = conn.execute("""
                    SELECT alignment_status, COUNT(*) as count
                    FROM clusters
                    WHERE alignment_status IS NOT NULL
                    GROUP BY alignment_status
                """)
                stats["clusters_by_alignment_status"] = {
                    row['alignment_status']: row['count']
                    for row in cursor.fetchall()
                }

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

    # 跨源对齐相关方法
    def get_aligned_problems(self) -> List[Dict]:
        """获取所有对齐问题"""
        try:
            with self.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT id, aligned_problem_id, sources, core_problem,
                           why_they_look_different, evidence, cluster_ids, created_at
                    FROM aligned_problems
                    ORDER BY created_at DESC
                """)

                results = []
                for row in cursor.fetchall():
                    result = dict(row)
                    result['sources'] = json.loads(result['sources'])
                    result['evidence'] = json.loads(result['evidence'])
                    result['cluster_ids'] = json.loads(result['cluster_ids'])
                    results.append(result)

                return results

        except Exception as e:
            logger.error(f"Failed to get aligned problems: {e}")
            return []

    def update_cluster_alignment_status(self, cluster_name: str, status: str, aligned_problem_id: str = None):
        """更新聚类对齐状态"""
        try:
            with self.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    UPDATE clusters
                    SET alignment_status = ?, aligned_problem_id = ?
                    WHERE cluster_name = ?
                """, (status, aligned_problem_id, cluster_name))

                # Verify that the update actually affected a row
                if cursor.rowcount == 0:
                    logger.error(
                        f"Failed to update cluster '{cluster_name}' - cluster not found! "
                        f"This means the cluster_name returned by LLM doesn't match any cluster in the database."
                    )
                    raise ValueError(f"Cluster '{cluster_name}' not found for alignment update")

                conn.commit()
                logger.info(f"Successfully updated cluster '{cluster_name}' to status='{status}'" + (
                    f", aligned_problem_id='{aligned_problem_id}'" if aligned_problem_id else ""
                ))
        except Exception as e:
            logger.error(f"Failed to update cluster alignment status: {e}")
            raise

    def insert_aligned_problem(self, aligned_problem_data: Dict):
        """插入新的对齐问题"""
        try:
            with self.get_connection("clusters") as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO aligned_problems
                    (id, aligned_problem_id, sources, core_problem,
                     why_they_look_different, evidence, cluster_ids, alignment_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    aligned_problem_data['id'],
                    aligned_problem_data['aligned_problem_id'],
                    json.dumps(aligned_problem_data['sources']),
                    aligned_problem_data['core_problem'],
                    aligned_problem_data['why_they_look_different'],
                    json.dumps(aligned_problem_data['evidence']),
                    json.dumps(aligned_problem_data['cluster_ids']),
                    aligned_problem_data.get('alignment_score', 0.0)
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to insert aligned problem: {e}")
            raise

    def get_clusters_for_opportunity_mapping(self) -> List[Dict]:
        """获取用于机会映射的聚类（包括对齐问题）

        防止重复映射：只返回尚未映射opportunities的clusters
        """
        try:
            with self.get_connection("clusters") as conn:
                # 获取未对齐的原始聚类，且该cluster尚未有opportunities
                cursor = conn.execute("""
                    SELECT id, cluster_name, source_type, centroid_summary,
                           common_pain, pain_event_ids, cluster_size,
                           cluster_description, workflow_confidence, created_at
                    FROM clusters
                    WHERE (alignment_status IN ('unprocessed', 'processed')
                           OR alignment_status IS NULL)
                      AND NOT EXISTS (
                          SELECT 1 FROM opportunities
                          WHERE opportunities.cluster_id = clusters.id
                      )
                """)

                clusters = [dict(row) for row in cursor.fetchall()]

                # 获取对齐问题作为"虚拟聚类"，在Python中计算cluster_size
                cursor = conn.execute("""
                    SELECT aligned_problem_id as cluster_name,
                           'aligned' as source_type,
                           core_problem as centroid_summary,
                           '' as common_pain,
                           '[]' as pain_event_ids,
                           cluster_ids
                    FROM aligned_problems
                """)

                aligned_clusters = []
                for row in cursor.fetchall():
                    cluster_dict = dict(row)
                    # 在Python中计算JSON数组的长度
                    cluster_ids = json.loads(cluster_dict['cluster_ids'])
                    cluster_dict['cluster_size'] = len(cluster_ids)
                    aligned_clusters.append(cluster_dict)

                # 合并结果
                return clusters + aligned_clusters

        except Exception as e:
            logger.error(f"Failed to get clusters for opportunity mapping: {e}")
            return []

    def get_cross_source_validated_opportunities(
        self,
        min_validation_level: int = 1,
        include_validated_only: bool = True
    ) -> List[Dict[str, Any]]:
        """查询所有跨源验证的机会

        Args:
            min_validation_level: 最低验证等级（1-3），默认为 1
            include_validated_only: 是否仅包含 validated_problem=True 的，默认为 True

        Returns:
            跨源验证的机会列表
        """
        try:
            with self.get_connection("opportunities") as conn:
                query = """
                    SELECT
                        o.opportunity_name,
                        o.total_score,
                        o.trust_level,
                        o.target_users,
                        o.missing_capability,
                        o.why_existing_fail,
                        c.cluster_name,
                        c.cluster_size,
                        c.source_type,
                        c.alignment_status,
                        c.aligned_problem_id
                    FROM opportunities o
                    LEFT JOIN clusters c ON o.cluster_id = c.id
                    WHERE 1=1
                """

                params = []

                query += " ORDER BY o.total_score DESC"

                cursor = conn.execute(query, params)
                results = [dict(row) for row in cursor.fetchall()]

                # 在 Python 中进行跨源验证过滤
                filtered_results = []
                for result in results:
                    validation_info = self._check_cross_source_validation_sync(
                        result['cluster_name'],
                        result.get('source_type'),
                        result.get('aligned_problem_id'),
                        result.get('cluster_size', 0)
                    )

                    validation_level = validation_info.get('validation_level', 0)

                    # 过滤条件
                    if validation_level >= min_validation_level:
                        if include_validated_only:
                            if validation_info.get('validated_problem'):
                                result['cross_source_validation'] = validation_info
                                filtered_results.append(result)
                        else:
                            result['cross_source_validation'] = validation_info
                            filtered_results.append(result)

                return filtered_results

        except Exception as e:
            logger.error(f"Failed to get cross-source validated opportunities: {e}")
            return []

    def _check_cross_source_validation_sync(
        self,
        cluster_name: str,
        source_type: Optional[str],
        aligned_problem_id: Optional[str],
        cluster_size: int
    ) -> Dict[str, Any]:
        """同步版本的跨源验证检查（用于数据库查询）

        注意：由于 pain_events 表没有 subreddit 和 cluster_name 列，
        目前只能检测 Level 1（跨平台对齐）的验证。

        Args:
            cluster_name: 聚类名称
            source_type: 来源类型
            aligned_problem_id: 对齐问题ID
            cluster_size: 聚类规模

        Returns:
            验证信息字典
        """
        # Level 1: 检查 aligned source_type 或 aligned_problem_id
        if source_type == 'aligned' or aligned_problem_id:
            return {
                "has_cross_source": True,
                "validation_level": 1,
                "boost_score": 2.0,
                "validated_problem": True,
                "evidence": "Independent validation across Reddit + Hacker News"
            }

        # Level 1: 检查 aligned_problems 表（cluster_ids JSON 字段中可能包含此 cluster）
        try:
            with self.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT aligned_problem_id
                    FROM aligned_problems
                    WHERE cluster_ids LIKE ?
                    LIMIT 1
                """, (f'%{cluster_name}%',))
                result = cursor.fetchone()
                if result:
                    return {
                        "has_cross_source": True,
                        "validation_level": 1,
                        "boost_score": 2.0,
                        "validated_problem": True,
                        "evidence": f"Found in aligned_problems: {result[0]}"
                    }
        except Exception as e:
            logger.warning(f"Failed to check aligned_problems for {cluster_name}: {e}")

        # 注意：Level 2 和 Level 3 需要 subreddit 跨度统计，
        # 但 pain_events 表没有 cluster_name 和 subreddit 列，无法查询
        # 因此暂时只支持 Level 1 验证

        # 无跨源验证
        return {
            "has_cross_source": False,
            "validation_level": 0,
            "boost_score": 0.0,
            "validated_problem": False,
            "evidence": "No cross-source validation (only Level 1 detection supported)"
        }

    def get_clusters_for_aligned_problem(self, aligned_problem_id: str) -> List[Dict]:
        """获取对齐问题的支持聚类"""
        try:
            with self.get_connection("clusters") as conn:
                # 首先获取对齐问题的cluster_ids
                cursor = conn.execute("""
                    SELECT cluster_ids
                    FROM aligned_problems
                    WHERE aligned_problem_id = ?
                """, (aligned_problem_id,))

                result = cursor.fetchone()
                if not result:
                    return []

                cluster_ids = json.loads(result['cluster_ids'])

                # 获取这些聚类的详细信息
                if not cluster_ids:
                    return []

                placeholders = ','.join(['?' for _ in cluster_ids])
                cursor = conn.execute(f"""
                    SELECT cluster_name, source_type, centroid_summary,
                           common_pain, cluster_size
                    FROM clusters
                    WHERE cluster_name IN ({placeholders})
                """, cluster_ids)

                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to get clusters for aligned problem {aligned_problem_id}: {e}")
            return []

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

    def get_score_statistics(self) -> Dict[str, Any]:
        """Get statistics on continuous scores"""
        stats = {}

        try:
            with self.get_connection("clusters") as conn:
                # Workflow similarity distribution
                cursor = conn.execute("""
                    SELECT
                        COUNT(*) as total_clusters,
                        AVG(workflow_similarity) as avg_similarity,
                        MIN(workflow_similarity) as min_similarity,
                        MAX(workflow_similarity) as max_similarity
                    FROM clusters
                    WHERE workflow_similarity IS NOT NULL
                """)
                row = cursor.fetchone()
                stats['workflow_similarity'] = dict(row) if row else {}

                # Distribution buckets
                cursor = conn.execute("""
                    SELECT
                        CASE
                            WHEN workflow_similarity >= 0.8 THEN 'high'
                            WHEN workflow_similarity >= 0.6 THEN 'medium'
                            ELSE 'low'
                        END as bucket,
                        COUNT(*) as count
                    FROM clusters
                    WHERE workflow_similarity IS NOT NULL
                    GROUP BY bucket
                """)
                stats['workflow_similarity_distribution'] = {row['bucket']: row['count'] for row in cursor.fetchall()}

            with self.get_connection("clusters") as conn:
                # Alignment score distribution
                cursor = conn.execute("""
                    SELECT
                        COUNT(*) as total_alignments,
                        AVG(alignment_score) as avg_alignment,
                        MIN(alignment_score) as min_alignment,
                        MAX(alignment_score) as max_alignment
                    FROM aligned_problems
                    WHERE alignment_score IS NOT NULL
                """)
                row = cursor.fetchone()
                stats['alignment_score'] = dict(row) if row else {}

            with self.get_connection("raw") as conn:
                # Trust level distribution by source
                cursor = conn.execute("""
                    SELECT
                        source,
                        COUNT(*) as count,
                        AVG(trust_level) as avg_trust_level
                    FROM posts
                    WHERE trust_level IS NOT NULL
                    GROUP BY source
                """)
                stats['trust_level_by_source'] = {row['source']: {'count': row['count'], 'avg_trust': row['avg_trust_level']} for row in cursor.fetchall()}

        except Exception as e:
            logger.error(f"Failed to get score statistics: {e}")

        return stats


# 全局数据库实例（使用统一数据库）
db = WiseCollectionDB(unified=True)

# 保持向后兼容的多数据库实例
db_multi = WiseCollectionDB(unified=False)