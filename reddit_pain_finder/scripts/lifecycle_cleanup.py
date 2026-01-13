#!/usr/bin/env python3
"""
Lifecycle Cleanup Script for Cluster-Centric Retention

This script maintains the cluster-centric data retention strategy:
- Deletes orphan pain_events older than 14 days
- Archives inactive clusters (optional)
- Updates statistics

This should be run after each cluster update or daily via cron.
"""
import sys
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.db import db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def mark_orphan_events(db_path: str = "data/wise_collection.db"):
    """Mark pain_events without clusters as orphans

    This should be called after cluster updates to ensure all
    unclustered events are marked as orphans.

    Args:
        db_path: Path to SQLite database

    Returns:
        Number of events marked as orphan
    """
    logger.info("Marking orphan pain_events...")

    try:
        with db.get_connection("pain") as conn:
            # Mark events without cluster_id as orphans
            cursor = conn.execute("""
                UPDATE pain_events
                SET lifecycle_stage = 'orphan',
                    orphan_since = COALESCE(orphan_since, datetime('now')),
                    cluster_id = NULL,
                    last_clustered_at = NULL
                WHERE cluster_id IS NULL
                AND lifecycle_stage != 'orphan'
            """)

            orphan_count = cursor.rowcount
            conn.commit()

            logger.info(f"✅ Marked {orphan_count} pain_events as orphans")
            return orphan_count

    except Exception as e:
        logger.error(f"Failed to mark orphan events: {e}")
        return 0


def cleanup_old_orphans(
    db_path: str = "data/wise_collection.db",
    orphan_age_days: int = 14
):
    """Delete orphan pain_events older than specified days

    This implements the core retention strategy:
    - Pain_events that are repeatedly mentioned stay in clusters forever
    - Pain_events that are mentioned once disappear after 14 days

    Args:
        db_path: Path to SQLite database
        orphan_age_days: Delete orphans older than this (default: 14)

    Returns:
        Number of orphans deleted
    """
    logger.info(f"Cleaning up orphans older than {orphan_age_days} days...")

    try:
        with db.get_connection("pain") as conn:
            # First, count what will be deleted
            cursor = conn.execute("""
                SELECT COUNT(*)
                FROM pain_events
                WHERE lifecycle_stage = 'orphan'
                AND orphan_since < datetime('now', '-' || ? || ' days')
            """, (orphan_age_days,))

            count = cursor.fetchone()[0]
            logger.info(f"Found {count} orphan pain_events to delete")

            if count == 0:
                logger.info("No old orphans to clean up")
                return 0

            # Delete from Chroma (will need Chroma client)
            # Note: Implementing Chroma cleanup separately

            # Delete from SQLite
            cursor = conn.execute("""
                DELETE FROM pain_events
                WHERE lifecycle_stage = 'orphan'
                AND orphan_since < datetime('now', '-' || ? || ' days')
            """, (orphan_age_days,))

            deleted_count = cursor.rowcount
            conn.commit()

            logger.info(f"✅ Deleted {deleted_count} old orphan pain_events")
            return deleted_count

    except Exception as e:
        logger.error(f"Failed to cleanup old orphans: {e}")
        return 0


def cleanup_orphans_from_chroma(
    orphan_ids: list[int],
    chroma_client
):
    """Remove orphaned pain_events from Chroma

    Args:
        orphan_ids: List of pain_event IDs to delete
        chroma_client: ChromaClient instance
    """
    if not orphan_ids:
        return

    try:
        logger.info(f"Removing {len(orphan_ids)} orphans from Chroma...")
        chroma_client.delete_by_ids(orphan_ids)
        logger.info("✅ Chroma cleanup complete")

    except Exception as e:
        logger.error(f"Failed to cleanup Chroma: {e}")


def archive_inactive_clusters(
    db_path: str = "data/wise_collection.db",
    inactivity_days: int = 90
):
    """Archive clusters that haven't been updated in X days

    This is optional - keeps the database clean by moving very old
    clusters to an archive table or marking them as archived.

    Args:
        db_path: Path to SQLite database
        inactivity_days: Days of inactivity before archiving

    Returns:
        Number of clusters archived
    """
    logger.info(f"Checking for clusters inactive for {inactivity_days} days...")

    try:
        with db.get_connection("clusters") as conn:
            # Count inactive clusters
            cursor = conn.execute("""
                SELECT COUNT(*)
                FROM clusters
                WHERE datetime(created_at) < datetime('now', '-' || ? || ' days')
                AND alignment_status != 'archived'
            """, (inactivity_days,))

            count = cursor.fetchone()[0]

            if count == 0:
                logger.info("No inactive clusters to archive")
                return 0

            logger.info(f"Found {count} inactive clusters (marking as archived)")

            # Mark as archived (soft delete)
            cursor = conn.execute("""
                UPDATE clusters
                SET alignment_status = 'archived'
                WHERE datetime(created_at) < datetime('now', '-' || ? || ' days')
                AND alignment_status != 'archived'
            """, (inactivity_days,))

            archived_count = cursor.rowcount
            conn.commit()

            logger.info(f"✅ Archived {archived_count} inactive clusters")
            return archived_count

    except Exception as e:
        logger.error(f"Failed to archive inactive clusters: {e}")
        return 0


def get_lifecycle_statistics(db_path: str = "data/wise_collection.db") -> dict:
    """Get current lifecycle statistics

    Args:
        db_path: Path to SQLite database

    Returns:
        Statistics dict
    """
    try:
        with db.get_connection("pain") as conn:
            # Total pain_events
            cursor = conn.execute("SELECT COUNT(*) FROM pain_events")
            total = cursor.fetchone()[0]

            # Active (in clusters)
            cursor = conn.execute("""
                SELECT COUNT(*) FROM pain_events
                WHERE lifecycle_stage = 'active'
            """)
            active = cursor.fetchone()[0]

            # Orphans
            cursor = conn.execute("""
                SELECT COUNT(*) FROM pain_events
                WHERE lifecycle_stage = 'orphan'
            """)
            orphans = cursor.fetchone()[0]

            # Old orphans (eligible for deletion)
            cursor = conn.execute("""
                SELECT COUNT(*) FROM pain_events
                WHERE lifecycle_stage = 'orphan'
                AND orphan_since < datetime('now', '-14 days')
            """)
            old_orphans = cursor.fetchone()[0]

            # Clusters
            with db.get_connection("clusters") as cluster_conn:
                cursor = cluster_conn.execute("SELECT COUNT(*) FROM clusters")
                clusters = cursor.fetchone()[0]

                cursor = cluster_conn.execute("""
                    SELECT COUNT(*) FROM clusters
                    WHERE alignment_status = 'archived'
                """)
                archived_clusters = cursor.fetchone()[0]

            return {
                "total_pain_events": total,
                "active_events": active,
                "orphan_events": orphans,
                "old_orphans": old_orphans,
                "total_clusters": clusters,
                "active_clusters": clusters - archived_clusters,
                "archived_clusters": archived_clusters,
                "retention_rate": (active / total * 100) if total > 0 else 0
            }

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        return {}


def run_full_cleanup(
    db_path: str = "data/wise_collection.db",
    orphan_age_days: int = 14,
    cluster_inactivity_days: int = 90
):
    """Run complete lifecycle cleanup

    This is the main entry point for scheduled cleanup jobs.

    Args:
        db_path: Path to SQLite database
        orphan_age_days: Days before deleting orphans
        cluster_inactivity_days: Days before archiving clusters
    """
    logger.info("=" * 60)
    logger.info("Starting Lifecycle Cleanup")
    logger.info("=" * 60)

    # 1. Get initial statistics
    logger.info("\n--- Initial Statistics ---")
    initial_stats = get_lifecycle_statistics(db_path)
    for key, value in initial_stats.items():
        logger.info(f"  {key}: {value}")

    # 2. Mark orphans
    logger.info("\n--- Step 1: Mark Orphans ---")
    mark_orphan_events(db_path)

    # 3. Cleanup old orphans from SQLite
    logger.info("\n--- Step 2: Cleanup Old Orphans ---")
    deleted_orphans = cleanup_old_orphans(db_path, orphan_age_days)

    # 4. Cleanup old orphans from Chroma
    if deleted_orphans > 0:
        # Get orphan IDs to cleanup from Chroma
        with db.get_connection("pain") as conn:
            cursor = conn.execute("""
                SELECT id FROM pain_events
                WHERE lifecycle_stage = 'orphan'
                AND orphan_since < datetime('now', '-' || ? || ' days')
            """, (orphan_age_days,))

            orphan_ids = [row[0] for row in cursor.fetchall()]

        if orphan_ids:
            from utils.chroma_client import get_chroma_client
            chroma = get_chroma_client()
            cleanup_orphans_from_chroma(orphan_ids, chroma)

    # 5. Archive inactive clusters
    logger.info("\n--- Step 3: Archive Inactive Clusters ---")
    archive_inactive_clusters(db_path, cluster_inactivity_days)

    # 6. Get final statistics
    logger.info("\n--- Final Statistics ---")
    final_stats = get_lifecycle_statistics(db_path)
    for key, value in final_stats.items():
        logger.info(f"  {key}: {value}")

    logger.info("\n" + "=" * 60)
    logger.info("Lifecycle Cleanup Complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Lifecycle cleanup for cluster-centric retention")
    parser.add_argument("--orphan-age", type=int, default=14,
                       help="Delete orphans older than X days (default: 14)")
    parser.add_argument("--cluster-inactivity", type=int, default=90,
                       help="Archive clusters inactive for X days (default: 90)")
    parser.add_argument("--stats-only", action="store_true",
                       help="Only show statistics, don't cleanup")

    args = parser.parse_args()

    if args.stats_only:
        stats = get_lifecycle_statistics()
        print("\n=== Current Lifecycle Statistics ===")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    else:
        run_full_cleanup(
            orphan_age_days=args.orphan_age,
            cluster_inactivity_days=args.cluster_inactivity
        )
