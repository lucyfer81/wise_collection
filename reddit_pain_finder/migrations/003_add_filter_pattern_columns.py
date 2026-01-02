"""
Migration 003: Add pain_patterns and emotional_intensity columns to filtered tables

This migration ensures that filtered_posts and filtered_comments tables have
the necessary columns for storing filter results from the fetch stage.
"""
import sqlite3
import logging

logger = logging.getLogger(__name__)

def upgrade(database_path: str = "data/wise_collection.db"):
    """Add missing columns to filtered tables"""
    
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()
    
    try:
        logger.info("Running migration 003: Add filter pattern columns")
        
        # Check filtered_posts columns
        cursor.execute("PRAGMA table_info(filtered_posts)")
        filtered_posts_columns = {row[1] for row in cursor.fetchall()}
        
        # Add missing columns to filtered_posts
        if 'pain_patterns' not in filtered_posts_columns:
            cursor.execute("ALTER TABLE filtered_posts ADD COLUMN pain_patterns TEXT")
            logger.info("✓ Added pain_patterns column to filtered_posts")
        
        if 'emotional_intensity' not in filtered_posts_columns:
            cursor.execute("ALTER TABLE filtered_posts ADD COLUMN emotional_intensity REAL DEFAULT 0.0")
            logger.info("✓ Added emotional_intensity column to filtered_posts")
        
        if 'author' not in filtered_posts_columns:
            cursor.execute("ALTER TABLE filtered_posts ADD COLUMN author TEXT")
            logger.info("✓ Added author column to filtered_posts")
        
        # Check filtered_comments columns
        cursor.execute("PRAGMA table_info(filtered_comments)")
        filtered_comments_columns = {row[1] for row in cursor.fetchall()}
        
        # Add missing columns to filtered_comments
        if 'pain_patterns' not in filtered_comments_columns:
            cursor.execute("ALTER TABLE filtered_comments ADD COLUMN pain_patterns TEXT")
            logger.info("✓ Added pain_patterns column to filtered_comments")
        
        if 'emotional_intensity' not in filtered_comments_columns:
            cursor.execute("ALTER TABLE filtered_comments ADD COLUMN emotional_intensity REAL DEFAULT 0.0")
            logger.info("✓ Added emotional_intensity column to filtered_comments")
        
        conn.commit()
        logger.info("✅ Migration 003 completed successfully")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Migration 003 failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    upgrade()
