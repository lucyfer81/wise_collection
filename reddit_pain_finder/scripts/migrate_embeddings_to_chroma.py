#!/usr/bin/env python3
"""
Migrate existing pain_embeddings from SQLite to Chroma

This script:
1. Reads all pain_events with embeddings from SQLite
2. Migrates them to Chroma
3. Verifies migration success
4. (Optional) Drops the old pain_embeddings table

Usage:
    python scripts/migrate_embeddings_to_chroma.py [--drop-old]
"""
import sys
import os
import logging
import sqlite3
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.chroma_client import ChromaClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_embeddings_to_chroma(
    db_path: str = "data/wise_collection.db",
    drop_old: bool = False
):
    """Migrate pain_embeddings from SQLite to Chroma

    Args:
        db_path: Path to SQLite database
        drop_old: If True, drop pain_embeddings table after migration
    """
    logger.info("=" * 60)
    logger.info("Migrating pain_embeddings from SQLite to Chroma")
    logger.info("=" * 60)

    # 1. Initialize Chroma client
    logger.info("Step 1: Initializing Chroma client...")
    chroma = ChromaClient(persist_directory="data/chroma_db")

    # 2. Connect to SQLite
    logger.info("Step 2: Connecting to SQLite database...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 3. Count existing embeddings
    cursor.execute("""
        SELECT COUNT(*)
        FROM pain_embeddings
    """)
    total_count = cursor.fetchone()[0]
    logger.info(f"Found {total_count} embeddings to migrate")

    if total_count == 0:
        logger.info("No embeddings to migrate, exiting")
        return

    # 4. Check Chroma current count
    current_chroma_count = chroma.collection.count()
    if current_chroma_count > 0:
        logger.warning(f"Chroma already has {current_chroma_count} embeddings")
        response = input("Continue and add duplicates? (y/N): ")
        if response.lower() != 'y':
            logger.info("Migration cancelled")
            return

    # 5. Fetch all pain_events with embeddings
    logger.info("Step 3: Fetching pain_events with embeddings...")
    cursor.execute("""
        SELECT
            pe.id,
            pe.problem,
            pe.context,
            pe.extracted_at,
            pe.cluster_id,
            pe.lifecycle_stage,
            em.embedding_vector,
            em.embedding_model
        FROM pain_events pe
        JOIN pain_embeddings em ON pe.id = em.pain_event_id
        ORDER BY pe.extracted_at DESC
    """)

    # 6. Batch migrate to Chroma
    logger.info("Step 4: Migrating embeddings to Chroma...")
    batch_size = 100
    batch_data = {
        "ids": [],
        "embeddings": [],
        "metadatas": [],
        "documents": []
    }
    migrated_count = 0

    for row in cursor.fetchall():
        import pickle

        pain_event_id, problem, context, extracted_at, cluster_id, lifecycle_stage, vector_blob, model = row

        # Deserialize embedding vector
        try:
            embedding = pickle.loads(vector_blob)
            # Convert to list if it's a numpy array
            if hasattr(embedding, 'tolist'):
                embedding = embedding.tolist()
            elif not isinstance(embedding, list):
                embedding = list(embedding)
        except Exception as e:
            logger.error(f"Failed to deserialize embedding for pain_event {pain_event_id}: {e}")
            continue

        # Prepare metadata (ensure no None values, Chroma doesn't support them)
        metadata = {
            "pain_event_id": pain_event_id,
            "problem": (problem or "")[:500],  # Truncate long text
            "context": (context or "")[:500],
            "extracted_at": extracted_at or "",
            "cluster_id": cluster_id or 0,
            "lifecycle_stage": (lifecycle_stage or "unknown"),
            "embedding_model": model or "unknown"
        }

        # Prepare document text
        document = f"{problem or ''}. {context or ''}"

        # Add to batch
        batch_data["ids"].append(str(pain_event_id))
        batch_data["embeddings"].append(embedding)  # Already converted to list
        batch_data["metadatas"].append(metadata)
        batch_data["documents"].append(document)

        # Insert batch when full
        if len(batch_data["ids"]) >= batch_size:
            chroma.collection.add(**batch_data)
            migrated_count += len(batch_data["ids"])
            logger.info(f"  Migrated {migrated_count}/{total_count} embeddings...")

            # Reset batch
            batch_data = {"ids": [], "embeddings": [], "metadatas": [], "documents": []}

    # Insert remaining batch
    if batch_data["ids"]:
        chroma.collection.add(**batch_data)
        migrated_count += len(batch_data["ids"])

    logger.info(f"✅ Migration complete: {migrated_count} embeddings migrated to Chroma")

    # 7. Verify migration
    logger.info("Step 5: Verifying migration...")
    chroma_count = chroma.collection.count()
    logger.info(f"  SQLite count: {total_count}")
    logger.info(f"  Chroma count: {chroma_count}")

    if abs(chroma_count - total_count) > 0.1 * total_count:  # Allow 10% variance (duplicates)
        logger.warning("⚠️  Counts don't match, please verify!")
    else:
        logger.info("✅ Migration verified successfully")

    # 8. Optional: Drop old table
    if drop_old:
        logger.warning("You requested to DROP the pain_embeddings table")
        logger.warning("This cannot be undone!")
        response = input("Are you sure? (type 'yes' to confirm): ")
        if response == 'yes':
            logger.info("Dropping pain_embeddings table...")
            cursor.execute("DROP TABLE IF EXISTS pain_embeddings")
            conn.commit()
            logger.info("✅ pain_embeddings table dropped")
        else:
            logger.info("Skipping table drop")

    # 9. Test query
    logger.info("Step 6: Testing Chroma query...")
    if chroma_count > 0:
        # Get first embedding for test
        cursor.execute("""
            SELECT pe.id, em.embedding_vector
            FROM pain_events pe
            JOIN pain_embeddings em ON pe.id = em.pain_event_id
            LIMIT 1
        """)
        test_row = cursor.fetchone()

        if test_row:
            test_id, test_vector_blob = test_row
            test_vector = pickle.loads(test_vector_blob)

            # Convert to list if needed
            if hasattr(test_vector, 'tolist'):
                test_vector = test_vector.tolist()
            elif not isinstance(test_vector, list):
                test_vector = list(test_vector)

            # Query Chroma
            results = chroma.query_similar(
                query_embedding=test_vector,
                top_k=5
            )

            logger.info(f"✅ Test query returned {len(results)} results")
            if results:
                logger.info(f"  Top result: pain_event_id={results[0]['pain_event_id']}, "
                           f"similarity={results[0]['similarity']:.3f}")

    conn.close()
    logger.info("=" * 60)
    logger.info("Migration completed successfully!")
    logger.info(f"Chroma data location: {Path('data/chroma_db').absolute()}")
    logger.info("You can now backup this directory as part of your regular backups")
    logger.info("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate pain_embeddings to Chroma")
    parser.add_argument("--db-path", default="data/wise_collection.db",
                       help="Path to SQLite database")
    parser.add_argument("--drop-old", action="store_true",
                       help="Drop pain_embeddings table after migration")

    args = parser.parse_args()

    try:
        migrate_embeddings_to_chroma(
            db_path=args.db_path,
            drop_old=args.drop_old
        )
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
