#!/usr/bin/env python3
"""
Migration 003: Add extraction_attempted tracking to filtered_comments table

This migration prevents reprocessing comments that have already been attempted
for pain extraction, regardless of whether extraction was successful.

Fields added:
- extraction_attempted: BOOLEAN - whether extraction was attempted
- extraction_attempted_at: TIMESTAMP - when extraction was attempted
"""
import sys
import os
import sqlite3
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import db

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def migrate():
    """Apply migration"""
    logger.info("=" * 80)
    logger.info("Migration 003: Add extraction_attempted tracking")
    logger.info("=" * 80)

    try:
        with db.get_connection("filtered") as conn:
            # Check if migration already applied
            cursor = conn.execute("PRAGMA table_info(filtered_comments)")
            columns = {row['name'] for row in cursor.fetchall()}

            if 'extraction_attempted' in columns:
                logger.info("✅ Migration already applied (extraction_attempted column exists)")
                return

            # Add columns
            logger.info("Adding extraction_attempted column...")
            conn.execute("ALTER TABLE filtered_comments ADD COLUMN extraction_attempted BOOLEAN DEFAULT 0")

            logger.info("Adding extraction_attempted_at column...")
            conn.execute("ALTER TABLE filtered_comments ADD COLUMN extraction_attempted_at TIMESTAMP")

            conn.commit()

            logger.info("✅ Migration completed successfully")

            # Verify
            cursor = conn.execute("PRAGMA table_info(filtered_comments)")
            columns = {row['name'] for row in cursor.fetchall()}
            assert 'extraction_attempted' in columns
            assert 'extraction_attempted_at' in columns

            logger.info("✅ Verification passed")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise


def rollback():
    """Rollback migration (if needed)"""
    logger.info("=" * 80)
    logger.info("Rollback 003: Remove extraction_attempted tracking")
    logger.info("=" * 80)

    try:
        with db.get_connection("filtered") as conn:
            logger.warning("⚠️  SQLite doesn't support DROP COLUMN")
            logger.warning("⚠️  To rollback, you need to:")
            logger.warning("   1. Export data")
            logger.warning("   2. Recreate table without these columns")
            logger.warning("   3. Import data back")
            logger.warning("Or just ignore the new columns")

    except Exception as e:
        logger.error(f"❌ Rollback failed: {e}")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migration 003: Add extraction_attempted tracking")
    parser.add_argument("--rollback", action="store_true", help="Rollback migration")
    args = parser.parse_args()

    try:
        if args.rollback:
            rollback()
        else:
            migrate()

        logger.info("\n" + "=" * 80)
        logger.info("Migration completed successfully!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"\n❌ Migration failed: {e}")
        sys.exit(1)
