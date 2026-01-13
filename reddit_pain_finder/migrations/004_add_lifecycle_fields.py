"""
Migration 004: Add lifecycle management fields to pain_events

This migration adds fields for cluster-centric retention strategy:
- lifecycle_stage: Track if event is 'active', 'orphan', or 'archived'
- last_clustered_at: Track when event was last part of a cluster
- orphan_since: Track when event became orphan (for cleanup scheduling)
"""
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def migrate(db_path: str = "data/wise_collection.db"):
    """Apply migration 004"""
    logger.info(f"Applying migration 004 to {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if migration already applied
        cursor.execute("PRAGMA table_info(pain_events)")
        columns = [row[1] for row in cursor.fetchall()]

        if "lifecycle_stage" in columns:
            logger.info("Migration 004 already applied, skipping")
            return

        # Add new columns
        logger.info("Adding lifecycle_stage column...")
        cursor.execute("""
            ALTER TABLE pain_events
            ADD COLUMN lifecycle_stage TEXT DEFAULT 'orphan'
        """)

        logger.info("Adding last_clustered_at column...")
        cursor.execute("""
            ALTER TABLE pain_events
            ADD COLUMN last_clustered_at TIMESTAMP
        """)

        logger.info("Adding orphan_since column...")
        cursor.execute("""
            ALTER TABLE pain_events
            ADD COLUMN orphan_since TIMESTAMP
        """)

        # Initialize lifecycle_stage for existing records
        logger.info("Initializing lifecycle_stage for existing records...")
        cursor.execute("""
            UPDATE pain_events
            SET lifecycle_stage = CASE
                WHEN cluster_id IS NOT NULL THEN 'active'
                ELSE 'orphan'
            END,
            orphan_since = CASE
                WHEN cluster_id IS NULL THEN datetime('now')
                ELSE NULL
            END
        """)

        # Create index for lifecycle queries
        logger.info("Creating index on lifecycle_stage...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pain_events_lifecycle
            ON pain_events(lifecycle_stage, orphan_since)
        """)

        # Create index for orphan cleanup queries
        logger.info("Creating index for orphan cleanup...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pain_events_orphan_cleanup
            ON pain_events(orphan_since)
            WHERE lifecycle_stage = 'orphan'
        """)

        conn.commit()

        # Verification
        cursor.execute("SELECT COUNT(*) FROM pain_events")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM pain_events WHERE lifecycle_stage = 'active'")
        active = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM pain_events WHERE lifecycle_stage = 'orphan'")
        orphan = cursor.fetchone()[0]

        logger.info(f"✅ Migration 004 applied successfully")
        logger.info(f"   Total pain_events: {total}")
        logger.info(f"   Active (in cluster): {active}")
        logger.info(f"   Orphan (no cluster): {orphan}")

        return True

    except Exception as e:
        logger.error(f"Failed to apply migration 004: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()

def rollback(db_path: str = "data/wise_collection.db"):
    """Rollback migration 004 (for development/testing)"""
    logger.info(f"Rolling back migration 004 from {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Note: SQLite doesn't support DROP COLUMN directly
        # For production, we'd need to recreate the table
        logger.warning("SQLite DROP COLUMN not supported, manual rollback required")
        logger.info("To rollback, manually recreate pain_events table without:")
        logger.info("  - lifecycle_stage")
        logger.info("  - last_clustered_at")
        logger.info("  - orphan_since")

        return False

    except Exception as e:
        logger.error(f"Failed to rollback migration 004: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/wise_collection.db"

    if "--rollback" in sys.argv:
        rollback(db_path)
    else:
        migrate(db_path)
