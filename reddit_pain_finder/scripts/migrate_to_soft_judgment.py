#!/usr/bin/env python3
"""
Migration script to add trust_level and soft judgment columns to existing databases.

This script should be run ONCE after deploying the new code to existing installations.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_posts_trust_level():
    """Migrate posts table to add trust_level"""
    logger.info("Migrating posts table for trust_level...")

    with db.get_connection("raw") as conn:
        # Check if column exists
        cursor = conn.execute("PRAGMA table_info(posts)")
        columns = {row['name'] for row in cursor.fetchall()}

        if 'trust_level' not in columns:
            conn.execute("ALTER TABLE posts ADD COLUMN trust_level REAL DEFAULT 0.5")
            logger.info("Added trust_level column to posts table")

            # Set trust_level based on category
            category_trust = {
                'core': 0.9,
                'secondary': 0.7,
                'verticals': 0.6,
                'experimental': 0.4
            }

            for category, level in category_trust.items():
                conn.execute("UPDATE posts SET trust_level = ? WHERE category = ?", (level, category))
                affected = conn.total_changes
                logger.info(f"Set trust_level={level} for {affected} posts in category '{category}'")

            conn.commit()
            logger.info("✓ Posts table migration complete")
        else:
            logger.info("trust_level column already exists in posts table")

def migrate_clusters_workflow_similarity():
    """Migrate clusters table to add workflow_similarity"""
    logger.info("Migrating clusters table for workflow_similarity...")

    with db.get_connection("clusters") as conn:
        cursor = conn.execute("PRAGMA table_info(clusters)")
        columns = {row['name'] for row in cursor.fetchall()}

        if 'workflow_similarity' not in columns:
            conn.execute("ALTER TABLE clusters ADD COLUMN workflow_similarity REAL DEFAULT 0.0")
            logger.info("Added workflow_similarity column to clusters table")

            # Migrate from workflow_confidence for existing clusters
            conn.execute("""
                UPDATE clusters
                SET workflow_similarity = COALESCE(workflow_confidence, 0.0)
                WHERE workflow_similarity = 0.0
            """)
            affected = conn.total_changes
            logger.info(f"Migrated {affected} clusters from workflow_confidence to workflow_similarity")

            conn.commit()
            logger.info("✓ Clusters table migration complete")
        else:
            logger.info("workflow_similarity column already exists in clusters table")

def migrate_aligned_problems_alignment_score():
    """Migrate aligned_problems table to add alignment_score"""
    logger.info("Migrating aligned_problems table for alignment_score...")

    with db.get_connection("clusters") as conn:
        cursor = conn.execute("PRAGMA table_info(aligned_problems)")
        columns = {row['name'] for row in cursor.fetchall()}

        if 'alignment_score' not in columns:
            conn.execute("ALTER TABLE aligned_problems ADD COLUMN alignment_score REAL DEFAULT 0.0")
            logger.info("Added alignment_score column to aligned_problems table")

            # Set default high score for existing manually validated alignments
            conn.execute("""
                UPDATE aligned_problems
                SET alignment_score = 0.85
                WHERE alignment_score = 0.0
            """)
            affected = conn.total_changes
            logger.info(f"Set default alignment_score=0.85 for {affected} existing aligned problems")

            conn.commit()
            logger.info("✓ Aligned problems table migration complete")
        else:
            logger.info("alignment_score column already exists in aligned_problems table")

def main():
    """Run all migrations"""
    logger.info("=" * 60)
    logger.info("Starting Trust Level & Soft Judgment Migration")
    logger.info("=" * 60)

    try:
        migrate_posts_trust_level()
        migrate_clusters_workflow_similarity()
        migrate_aligned_problems_alignment_score()

        logger.info("=" * 60)
        logger.info("✓ All migrations completed successfully!")
        logger.info("=" * 60)

        # Show post-migration stats
        stats = db.get_score_statistics()
        logger.info("\nPost-migration statistics:")
        if 'trust_level_by_source' in stats:
            for source, data in stats['trust_level_by_source'].items():
                logger.info(f"  {source}: {data['count']} posts, avg trust={data['avg_trust']:.2f}")

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
