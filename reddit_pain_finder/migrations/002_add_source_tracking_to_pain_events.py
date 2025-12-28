#!/usr/bin/env python3
"""
Migration 002: Add source tracking columns to pain_events table
Phase 2: Include Comments - Track whether pain events come from posts or comments
"""
import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    """Add source_type, source_id, and parent_post_id columns to pain_events"""
    logger.info("Starting migration 002: Add source tracking to pain_events")

    try:
        with db.get_connection("pain") as conn:
            # Check existing columns
            cursor = conn.execute("PRAGMA table_info(pain_events)")
            existing_columns = {row['name'] for row in cursor.fetchall()}
            logger.info(f"Existing columns: {existing_columns}")

            # Add source_type column
            if 'source_type' not in existing_columns:
                logger.info("Adding source_type column...")
                conn.execute("""
                    ALTER TABLE pain_events
                    ADD COLUMN source_type TEXT DEFAULT 'post'
                """)
                logger.info("✓ Added source_type column")
            else:
                logger.info("source_type column already exists")

            # Add source_id column
            if 'source_id' not in existing_columns:
                logger.info("Adding source_id column...")
                conn.execute("""
                    ALTER TABLE pain_events
                    ADD COLUMN source_id TEXT
                """)
                logger.info("✓ Added source_id column")
            else:
                logger.info("source_id column already exists")

            # Add parent_post_id column
            if 'parent_post_id' not in existing_columns:
                logger.info("Adding parent_post_id column...")
                conn.execute("""
                    ALTER TABLE pain_events
                    ADD COLUMN parent_post_id TEXT
                """)
                logger.info("✓ Added parent_post_id column")
            else:
                logger.info("parent_post_id column already exists")

            # Migrate existing records: set source_type='post', source_id=post_id, parent_post_id=post_id
            logger.info("Migrating existing pain_events...")
            cursor = conn.execute("""
                SELECT COUNT(*) as count
                FROM pain_events
                WHERE source_type IS NULL OR source_type = 'post'
            """)
            count = cursor.fetchone()['count']

            if count > 0:
                cursor = conn.execute("""
                    UPDATE pain_events
                    SET source_type = 'post',
                        source_id = post_id,
                        parent_post_id = post_id
                    WHERE source_type IS NULL OR source_type = 'post'
                """)
                logger.info(f"✓ Migrated {cursor.rowcount} existing pain_events")
            else:
                logger.info("No existing records to migrate")

            # Create index for source_type queries
            logger.info("Creating indexes...")
            try:
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_pain_events_source_type
                    ON pain_events(source_type)
                """)
                logger.info("✓ Created idx_pain_events_source_type")
            except Exception as e:
                logger.warning(f"Index creation (may already exist): {e}")

            conn.commit()
            logger.info("=" * 60)
            logger.info("Migration 002 completed successfully!")
            logger.info("=" * 60)

            # Verify migration
            cursor = conn.execute("""
                SELECT
                    source_type,
                    COUNT(*) as count
                FROM pain_events
                GROUP BY source_type
            """)
            logger.info("Current pain_events by source_type:")
            for row in cursor.fetchall():
                logger.info(f"  - {row['source_type']}: {row['count']}")

            return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
