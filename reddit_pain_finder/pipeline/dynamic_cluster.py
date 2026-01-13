"""
Dynamic Cluster Updater for Real-Time Pain Event Clustering

This replaces the static batch clustering with dynamic, streaming cluster updates:
- New pain_events immediately find or create clusters
- Clusters update incrementally as new data arrives
- Orphan pain_events are automatically cleaned up after 14 days
- Cluster scores and summaries update in real-time
"""
import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np

from utils.chroma_client import get_chroma_client
from utils.llm_client import llm_client
from utils.db import db

logger = logging.getLogger(__name__)


class DynamicClusterUpdater:
    """Dynamic cluster updater for streaming pain event clustering"""

    def __init__(self):
        """Initialize the dynamic cluster updater"""
        self.chroma = get_chroma_client()
        self.stats = {
            "total_events_processed": 0,
            "events_added_to_clusters": 0,
            "new_clusters_created": 0,
            "existing_clusters_updated": 0,
            "orphans_marked": 0,
            "processing_time": 0.0
        }

    def process_new_pain_events(
        self,
        new_pain_events: List[Dict[str, Any]],
        cluster_similarity_threshold: float = 0.75
    ) -> Dict[str, Any]:
        """Process new pain events and update clusters dynamically

        Args:
            new_pain_events: List of pain events with embeddings
            cluster_similarity_threshold: Minimum similarity to merge into existing cluster

        Returns:
            Processing results
        """
        logger.info(f"Processing {len(new_pain_events)} new pain events")
        start_time = time.time()

        for event in new_pain_events:
            pain_event_id = event['id']
            embedding_vector = event.get('embedding_vector')

            if embedding_vector is None:
                logger.warning(f"No embedding for pain_event {pain_event_id}, skipping")
                self.stats["orphans_marked"] += 1
                self._mark_as_orphan(pain_event_id, "No embedding available")
                continue

            # Convert to list if needed
            if hasattr(embedding_vector, 'tolist'):
                embedding_vector = embedding_vector.tolist()
            elif not isinstance(embedding_vector, list):
                embedding_vector = list(embedding_vector)

            # Step 1: Try to find similar existing cluster
            similar_cluster = self._find_similar_cluster(
                embedding_vector,
                threshold=cluster_similarity_threshold
            )

            if similar_cluster:
                # Step 2a: Merge into existing cluster
                self._merge_into_cluster(pain_event_id, similar_cluster)
                self.stats["existing_clusters_updated"] += 1
                logger.debug(f"Merged pain_event {pain_event_id} into cluster {similar_cluster['id']}")

            else:
                # Step 2b: Check if we can form a new cluster
                # (Need at least 4 similar events within 24 hours)
                can_form, similar_events = self._can_form_new_cluster(
                    embedding_vector,
                    event
                )

                if can_form:
                    # Step 3: Create new cluster
                    new_cluster_id = self._create_new_cluster(
                        similar_events + [pain_event_id]
                    )
                    self.stats["new_clusters_created"] += 1
                    logger.info(f"Created new cluster {new_cluster_id} with {len(similar_events) + 1} events")
                else:
                    # Step 4: Mark as orphan
                    self._mark_as_orphan(pain_event_id, "No similar cluster found")
                    self.stats["orphans_marked"] += 1
                    logger.debug(f"Marked pain_event {pain_event_id} as orphan")

            self.stats["total_events_processed"] += 1

        # Step 5: Recalculate affected clusters
        self._recalculate_affected_clusters()

        processing_time = time.time() - start_time
        self.stats["processing_time"] = processing_time

        logger.info(f"✅ Processed {len(new_pain_events)} pain events in {processing_time:.1f}s")
        logger.info(f"   Events added to clusters: {self.stats['events_added_to_clusters']}")
        logger.info(f"   New clusters created: {self.stats['new_clusters_created']}")
        logger.info(f"   Existing clusters updated: {self.stats['existing_clusters_updated']}")
        logger.info(f"   Orphans marked: {self.stats['orphans_marked']}")

        return self.stats.copy()

    def _find_similar_cluster(
        self,
        embedding_vector: List[float],
        threshold: float = 0.75
    ) -> Optional[Dict[str, Any]]:
        """Find similar existing cluster using centroid similarity

        Args:
            embedding_vector: Query embedding vector
            threshold: Minimum similarity threshold

        Returns:
            Most similar cluster dict or None
        """
        try:
            # Query Chroma for similar pain_events
            similar_events = self.chroma.query_similar(
                query_embedding=embedding_vector,
                top_k=50,  # Get more results for better cluster matching
                where={"lifecycle_stage": "active"}  # Only consider active events
            )

            if not similar_events:
                return None

            # Group by cluster_id and calculate cluster similarity
            cluster_similarities = {}
            cluster_event_counts = {}

            for event in similar_events[:20]:  # Check top 20 results
                cluster_id = event['metadata'].get('cluster_id')
                if not cluster_id or cluster_id == 0:
                    continue

                similarity = event['similarity']

                # Accumulate similarities for each cluster
                if cluster_id not in cluster_similarities:
                    cluster_similarities[cluster_id] = []
                    cluster_event_counts[cluster_id] = 0

                cluster_similarities[cluster_id].append(similarity)
                cluster_event_counts[cluster_id] += 1

            # Calculate average similarity for each cluster
            cluster_avg_similarities = {}
            for cluster_id, similarities in cluster_similarities.items():
                # Weight by cluster size (prefer larger, established clusters)
                avg_similarity = np.mean(similarities)
                cluster_size = cluster_event_counts[cluster_id]

                # Boost score for larger clusters (logarithmic scaling)
                size_boost = np.log(cluster_size + 1) / 10
                final_score = avg_similarity + size_boost

                cluster_avg_similarities[cluster_id] = final_score

            if not cluster_avg_similarities:
                return None

            # Return highest scoring cluster
            best_cluster_id = max(cluster_avg_similarities, key=cluster_avg_similarities.get)
            best_score = cluster_avg_similarities[best_cluster_id]

            if best_score >= threshold:
                # Fetch cluster details
                cluster = self._get_cluster_by_id(best_cluster_id)
                if cluster:
                    cluster['similarity_score'] = best_score
                    return cluster

            return None

        except Exception as e:
            logger.error(f"Failed to find similar cluster: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _can_form_new_cluster(
        self,
        embedding_vector: List[float],
        event_data: Dict[str, Any]
    ) -> Tuple[bool, List[int]]:
        """Check if we can form a new cluster with this event

        Requirements:
        - At least 4 similar pain_events
        - All within 24 hours
        - Not already in a cluster

        Args:
            embedding_vector: Query embedding vector
            event_data: Event metadata (for time filtering)

        Returns:
            (can_form, list_of_similar_event_ids)
        """
        try:
            # Get event time
            event_time = datetime.fromisoformat(event_data.get('extracted_at', '').replace('Z', '+00:00'))
            time_window = event_time - timedelta(hours=24)

            # Query Chroma for similar events
            similar_events = self.chroma.query_similar(
                query_embedding=embedding_vector,
                top_k=50,
                where={"lifecycle_stage": "orphan"}  # Only consider orphans
            )

            if not similar_events:
                return False, []

            # Filter by time window and similarity
            similar_event_ids = []
            for event in similar_events:
                similarity = event['similarity']
                if similarity < 0.7:  # Need high similarity for new cluster
                    continue

                event_id = event['pain_event_id']
                metadata = event['metadata']

                # Parse extracted_at
                try:
                    extracted_at_str = metadata.get('extracted_at', '')
                    extracted_at = datetime.fromisoformat(extracted_at_str.replace('Z', '+00:00'))

                    if extracted_at >= time_window:
                        similar_event_ids.append(event_id)
                except:
                    continue

                if len(similar_event_ids) >= 3:  # Need 3 others + this one = 4 total
                    logger.debug(f"Found {len(similar_event_ids)} similar events for new cluster")
                    return True, similar_event_ids

            return False, []

        except Exception as e:
            logger.error(f"Failed to check if can form new cluster: {e}")
            return False, []

    def _merge_into_cluster(
        self,
        pain_event_id: int,
        cluster: Dict[str, Any]
    ) -> bool:
        """Merge pain event into existing cluster

        Args:
            pain_event_id: Pain event ID to add
            cluster: Cluster dict with keys: id, pain_event_ids, cluster_size

        Returns:
            True if successful
        """
        try:
            cluster_id = cluster['id']
            existing_event_ids = json.loads(cluster.get('pain_event_ids', '[]'))

            # Add new event
            if pain_event_id not in existing_event_ids:
                existing_event_ids.append(pain_event_id)

            # Update pain_event
            with db.get_connection("pain") as conn:
                conn.execute("""
                    UPDATE pain_events
                    SET cluster_id = ?,
                        lifecycle_stage = 'active',
                        last_clustered_at = datetime('now'),
                        orphan_since = NULL
                    WHERE id = ?
                """, (cluster_id, pain_event_id))
                conn.commit()

            # Update cluster
            with db.get_connection("clusters") as conn:
                conn.execute("""
                    UPDATE clusters
                    SET pain_event_ids = ?,
                        cluster_size = ?,
                        created_at = datetime('now')  -- Update to show recent activity
                    WHERE id = ?
                """, (
                    json.dumps(sorted(existing_event_ids)),
                    len(existing_event_ids),
                    cluster_id
                ))
                conn.commit()

            # Update Chroma metadata
            self.chroma.update_metadata(
                pain_event_id,
                {
                    "cluster_id": cluster_id,
                    "lifecycle_stage": "active"
                }
            )

            self.stats["events_added_to_clusters"] += 1
            return True

        except Exception as e:
            logger.error(f"Failed to merge pain_event {pain_event_id} into cluster {cluster['id']}: {e}")
            return False

    def _create_new_cluster(self, pain_event_ids: List[int]) -> Optional[int]:
        """Create a new cluster from pain events

        Args:
            pain_event_ids: List of pain event IDs (at least 4)

        Returns:
            New cluster ID or None
        """
        try:
            # Get pain event details
            with db.get_connection("pain") as conn:
                placeholders = ','.join('?' for _ in pain_event_ids)
                cursor = conn.execute(f"""
                    SELECT * FROM pain_events
                    WHERE id IN ({placeholders})
                """, pain_event_ids)
                pain_events = [dict(row) for row in cursor.fetchall()]

            if len(pain_events) < 4:
                logger.warning(f"Not enough events to form cluster: {len(pain_events)} < 4")
                return None

            # Use LLM to validate and name the cluster
            validation_result = self._validate_new_cluster(pain_events)

            if not validation_result.get('is_valid_cluster', False):
                logger.debug("Cluster validation failed")
                return None

            # Create cluster record
            cluster_name = validation_result.get('cluster_name', 'Unnamed Cluster')
            cluster_description = validation_result.get('cluster_description', '')
            workflow_similarity = validation_result.get('workflow_similarity', 0.0)

            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    INSERT INTO clusters (
                        cluster_name, cluster_description, source_type,
                        pain_event_ids, cluster_size,
                        workflow_similarity, workflow_confidence,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """, (
                    cluster_name,
                    cluster_description,
                    'reddit',  # Default source type
                    json.dumps(sorted(pain_event_ids)),
                    len(pain_event_ids),
                    workflow_similarity,
                    validation_result.get('confidence', 0.0)
                ))

                cluster_id = cursor.lastrowid
                conn.commit()

            # Update pain_events
            for event_id in pain_event_ids:
                with db.get_connection("pain") as pain_conn:
                    pain_conn.execute("""
                        UPDATE pain_events
                        SET cluster_id = ?,
                            lifecycle_stage = 'active',
                            last_clustered_at = datetime('now'),
                            orphan_since = NULL
                        WHERE id = ?
                    """, (cluster_id, event_id))
                    pain_conn.commit()

                # Update Chroma metadata
                self.chroma.update_metadata(
                    event_id,
                    {
                        "cluster_id": cluster_id,
                        "lifecycle_stage": "active"
                    }
                )

            logger.info(f"Created cluster {cluster_id}: {cluster_name}")
            return cluster_id

        except Exception as e:
            logger.error(f"Failed to create new cluster: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _validate_new_cluster(self, pain_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate new cluster with LLM

        Args:
            pain_events: List of pain events

        Returns:
            Validation result dict
        """
        try:
            # Use existing cluster validation logic
            response = llm_client.cluster_pain_events(pain_events[:20])  # Limit to 20 for validation
            return response.get("content", {})

        except Exception as e:
            logger.error(f"Failed to validate cluster: {e}")
            # Fallback: Auto-approve if enough events
            return {
                "is_valid_cluster": len(pain_events) >= 4,
                "cluster_name": f"Auto Cluster ({len(pain_events)} events)",
                "workflow_similarity": 0.7
            }

    def _mark_as_orphan(self, pain_event_id: int, reason: str):
        """Mark pain event as orphan

        Args:
            pain_event_id: Pain event ID
            reason: Reason for marking as orphan
        """
        try:
            with db.get_connection("pain") as conn:
                conn.execute("""
                    UPDATE pain_events
                    SET cluster_id = NULL,
                        lifecycle_stage = 'orphan',
                        orphan_since = datetime('now'),
                        last_clustered_at = NULL
                    WHERE id = ?
                """, (pain_event_id,))
                conn.commit()

            # Update Chroma metadata
            self.chroma.update_metadata(
                pain_event_id,
                {"cluster_id": 0, "lifecycle_stage": "orphan"}
            )

        except Exception as e:
            logger.error(f"Failed to mark pain_event {pain_event_id} as orphan: {e}")

    def _recalculate_affected_clusters(self):
        """Recalculate summaries and scores for clusters that were updated

        This is called after processing all new events
        """
        try:
            # Find clusters updated in last hour
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT id, cluster_name, pain_event_ids
                    FROM clusters
                    WHERE datetime(created_at) > datetime('now', '-1 hour')
                """)

                affected_clusters = cursor.fetchall()

            logger.info(f"Recalculating {len(affected_clusters)} affected clusters...")

            for cluster_row in affected_clusters:
                cluster_id = cluster_row['id']
                pain_event_ids = json.loads(cluster_row['pain_event_ids'])

                # Get all pain events in cluster
                with db.get_connection("pain") as pain_conn:
                    placeholders = ','.join('?' for _ in pain_event_ids)
                    pain_cursor = pain_conn.execute(f"""
                        SELECT * FROM pain_events
                        WHERE id IN ({placeholders})
                    """, pain_event_ids)
                    pain_events = [dict(row) for row in pain_cursor.fetchall()]

                # Re-summarize using LLM
                summary_result = self._summarize_cluster(pain_events, cluster_row['cluster_name'])

                # Update cluster with new summary
                with db.get_connection("clusters") as conn:
                    conn.execute("""
                        UPDATE clusters
                        SET centroid_summary = ?,
                            common_pain = ?,
                            common_context = ?,
                            example_events = ?
                        WHERE id = ?
                    """, (
                        summary_result.get('centroid_summary', ''),
                        summary_result.get('common_pain', ''),
                        summary_result.get('common_context', ''),
                        json.dumps(summary_result.get('example_events', [])),
                        cluster_id
                    ))
                    conn.commit()

            logger.info("✅ Cluster recalculation complete")

        except Exception as e:
            logger.error(f"Failed to recalculate clusters: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _summarize_cluster(self, pain_events: List[Dict[str, Any]], cluster_name: str) -> Dict[str, Any]:
        """Summarize cluster using LLM

        Args:
            pain_events: List of pain events in cluster
            cluster_name: Current cluster name

        Returns:
            Summary dict
        """
        try:
            response = llm_client.summarize_source_cluster(pain_events[:20], 'reddit')
            return response.get("content", {})

        except Exception as e:
            logger.error(f"Failed to summarize cluster: {e}")
            # Fallback: Simple summary
            problems = [e.get('problem', '') for e in pain_events if e.get('problem')]
            return {
                "centroid_summary": f"Cluster with {len(pain_events)} pain events",
                "common_pain": " | ".join(problems[:5]),
                "common_context": "",
                "example_events": []
            }

    def _get_cluster_by_id(self, cluster_id: int) -> Optional[Dict[str, Any]]:
        """Get cluster details by ID

        Args:
            cluster_id: Cluster ID

        Returns:
            Cluster dict or None
        """
        try:
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT * FROM clusters WHERE id = ?
                """, (cluster_id,))
                row = cursor.fetchone()

                if row:
                    return dict(row)
                return None

        except Exception as e:
            logger.error(f"Failed to get cluster {cluster_id}: {e}")
            return None


def main():
    """Test dynamic cluster updater"""
    import sys
    logging.basicConfig(level=logging.INFO)

    # Get recent pain events
    with db.get_connection("pain") as conn:
        cursor = conn.execute("""
            SELECT pe.*,
                   em.embedding_vector
            FROM pain_events pe
            JOIN pain_embeddings em ON pe.id = em.pain_event_id
            WHERE pe.extracted_at > datetime('now', '-7 days')
            ORDER BY pe.extracted_at DESC
            LIMIT 100
        """)
        pain_events = [dict(row) for row in cursor.fetchall()]

    logger.info(f"Found {len(pain_events)} recent pain events for testing")

    # Process
    updater = DynamicClusterUpdater()
    results = updater.process_new_pain_events(pain_events)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
