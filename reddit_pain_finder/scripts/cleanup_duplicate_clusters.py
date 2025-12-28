#!/usr/bin/env python3
"""
Cleanup script for historical duplicate clusters

This script identifies and removes duplicate clusters from the database.
It keeps the most recently created cluster among duplicates.
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database path
DB_PATH = "data/wise_collection.db"


def identify_duplicate_clusters():
    """Identify all duplicate clusters (same pain_event_ids)"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT
                    pain_event_ids,
                    COUNT(*) as dup_count,
                    GROUP_CONCAT(id) as cluster_ids,
                    GROUP_CONCAT(cluster_name, ' | ') as cluster_names,
                    GROUP_CONCAT(created_at) as created_dates,
                    MAX(id) as keep_cluster_id,
                    MAX(created_at) as keep_cluster_created
                FROM clusters
                WHERE pain_event_ids IS NOT NULL AND pain_event_ids != '[]'
                GROUP BY pain_event_ids
                HAVING dup_count > 1
                ORDER BY dup_count DESC, keep_cluster_created DESC
            """)

            duplicates = []
            for row in cursor.fetchall():
                dup = {
                    'pain_event_ids': row['pain_event_ids'],
                    'dup_count': row['dup_count'],
                    'cluster_ids': [int(x) for x in row['cluster_ids'].split(',')],
                    'cluster_names': row['cluster_names'].split(' | '),
                    'created_dates': row['created_dates'].split(','),
                    'keep_cluster_id': row['keep_cluster_id'],
                    'keep_cluster_created': row['keep_cluster_created']
                }
                duplicates.append(dup)

            return duplicates

    except Exception as e:
        logger.error(f"Failed to identify duplicate clusters: {e}")
        return []


def delete_duplicate_clusters(dry_run=True):
    """Delete duplicate clusters, keeping the most recent one for each group

    Args:
        dry_run: If True, only show what would be deleted without actually deleting
    """
    duplicates = identify_duplicate_clusters()

    if not duplicates:
        logger.info("✅ No duplicate clusters found!")
        return

    logger.info(f"Found {len(duplicates)} groups of duplicate clusters\n")

    total_to_delete = 0
    for i, dup in enumerate(duplicates, 1):
        cluster_ids_to_delete = [cid for cid in dup['cluster_ids'] if cid != dup['keep_cluster_id']]

        logger.info(f"Duplicate Group {i}/{len(duplicates)}:")
        logger.info(f"  Pain Events: {dup['pain_event_ids']}")
        logger.info(f"  Duplicate Count: {dup['dup_count']}")
        logger.info(f"  Keep: Cluster {dup['keep_cluster_id']} (created: {dup['keep_cluster_created']})")
        logger.info(f"  Delete: {cluster_ids_to_delete}")

        total_to_delete += len(cluster_ids_to_delete)

    logger.info(f"\nTotal clusters to delete: {total_to_delete}")

    if dry_run:
        logger.info("\n🔍 DRY RUN MODE - No changes made to database")
        logger.info("Run with dry_run=False to actually delete duplicates")
    else:
        # Actually delete the duplicates
        with sqlite3.connect(DB_PATH) as conn:
            for dup in duplicates:
                cluster_ids_to_delete = [cid for cid in dup['cluster_ids'] if cid != dup['keep_cluster_id']]

                if cluster_ids_to_delete:
                    placeholders = ','.join('?' for _ in cluster_ids_to_delete)
                    conn.execute(f"""
                        DELETE FROM opportunities
                        WHERE cluster_id IN ({placeholders})
                    """, cluster_ids_to_delete)

                    conn.execute(f"""
                        DELETE FROM clusters
                        WHERE id IN ({placeholders})
                    """, cluster_ids_to_delete)

                    conn.commit()

        logger.info("✅ Deleted duplicate clusters successfully")


def backup_database():
    """Create a backup of the database before cleanup"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"data/wise_collection.db.backup_{timestamp}"

    import shutil
    shutil.copy2(DB_PATH, backup_path)

    logger.info(f"✅ Database backed up to: {backup_path}")
    return backup_path


def show_cluster_stats():
    """Show statistics about clusters"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        # Check if cluster_id column exists in pain_events table
        cursor = conn.execute("PRAGMA table_info(pain_events)")
        columns = {row['name'] for row in cursor.fetchall()}
        has_cluster_id = 'cluster_id' in columns

        # Total clusters
        cursor = conn.execute("SELECT COUNT(*) as count FROM clusters")
        total = cursor.fetchone()['count']

        # Clusters with duplicate pain_event_ids
        cursor = conn.execute("""
            SELECT COUNT(*) as count FROM (
                SELECT pain_event_ids, COUNT(*) as dup_count
                FROM clusters
                WHERE pain_event_ids IS NOT NULL
                GROUP BY pain_event_ids
                HAVING dup_count > 1
            )
        """)
        duplicate_groups = cursor.fetchone()['count']

        # Pain events without cluster_id (if column exists)
        if has_cluster_id:
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM pain_events
                WHERE cluster_id IS NULL
            """)
            unclustered_events = cursor.fetchone()['count']
        else:
            unclustered_events = "N/A (cluster_id column not yet added)"

        logger.info(f"""
📊 Database Statistics:
  Total clusters: {total}
  Duplicate cluster groups: {duplicate_groups}
  Pain events without cluster_id: {unclustered_events}
  cluster_id column exists: {has_cluster_id}
        """)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Clean up duplicate clusters")
    parser.add_argument("--dry-run", action="store_true", default=True,
                       help="Show what would be deleted without actually deleting (default: True)")
    parser.add_argument("--no-dry-run", action="store_false", dest="dry_run",
                       help="Actually delete duplicates (WARNING: cannot be undone)")
    parser.add_argument("--backup", action="store_true", default=True,
                       help="Create backup before cleanup (default: True)")
    parser.add_argument("--no-backup", action="store_false", dest="backup",
                       help="Skip backup (not recommended)")

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("DUPLICATE CLUSTER CLEANUP")
    logger.info("=" * 80)

    # Show stats
    show_cluster_stats()

    # Backup
    if args.backup and not args.dry_run:
        backup_database()
        logger.info("")
    elif args.dry_run:
        logger.info("🔍 Dry run mode - no backup needed\n")

    # Delete duplicates
    delete_duplicate_clusters(dry_run=args.dry_run)

    logger.info("")
    logger.info("=" * 80)
