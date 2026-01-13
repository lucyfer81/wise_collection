"""
Chroma vector database client for pain event embeddings

Replaces pickle-based storage in pain_embeddings table with:
- Fast vector similarity search using HNSW indexing
- Metadata filtering for lifecycle queries
- Persistent local storage (DuckDB + Parquet)
"""
import chromadb
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import pickle

logger = logging.getLogger(__name__)

class ChromaClient:
    """Chroma client for pain event embeddings"""

    def __init__(self, persist_directory: str = "data/chroma_db"):
        """Initialize Chroma client with persistent storage

        Args:
            persist_directory: Directory for Chroma data (can be backed up manually)
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        # Initialize Chroma client with new API (v0.6+)
        # This provides:
        # - Local file-based storage (easy to backup)
        # - Fast querying with HNSW indexing
        # - No external dependencies
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory)
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="pain_events",
            metadata={"hnsw:space": "cosine"}  # Use cosine similarity
        )

        logger.info(f"Chroma client initialized: {self.persist_directory}")
        logger.info(f"Collection 'pain_events' has {self.collection.count()} embeddings")

    def add_embeddings(
        self,
        pain_event_ids: List[int],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]]
    ) -> bool:
        """Add new embeddings to Chroma

        Args:
            pain_event_ids: List of pain event IDs
            embeddings: List of embedding vectors
            metadatas: List of metadata dicts (problem, context, extracted_at, etc.)

        Returns:
            bool: True if successful
        """
        try:
            # Prepare documents for text search (optional)
            documents = [f"{m.get('problem', '')}. {m.get('context', '')}"
                        for m in metadatas]

            # Convert to string IDs (Chroma requirement)
            ids = [str(eid) for eid in pain_event_ids]

            # Add to collection
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )

            logger.debug(f"Added {len(pain_event_ids)} embeddings to Chroma")
            return True

        except Exception as e:
            logger.error(f"Failed to add embeddings to Chroma: {e}")
            return False

    def query_similar(
        self,
        query_embedding: List[float],
        top_k: int = 20,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Query for similar pain events

        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            where: Metadata filter (e.g., {"lifecycle_stage": "active"})
            where_document: Document text filter

        Returns:
            List of similar pain events with similarity scores
        """
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where,
                where_document=where_document,
                include=["distances", "metadatas", "documents"]
            )

            # Convert to standard format
            similar_events = []
            for i, event_id_str in enumerate(results["ids"][0]):
                similarity = 1 - results["distances"][0][i]  # Convert distance to similarity
                similar_events.append({
                    "pain_event_id": int(event_id_str),
                    "similarity": similarity,
                    "distance": results["distances"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "document": results["documents"][0][i]
                })

            return similar_events

        except Exception as e:
            logger.error(f"Failed to query Chroma: {e}")
            return []

    def get_by_ids(self, pain_event_ids: List[int]) -> List[Dict[str, Any]]:
        """Get embeddings by IDs

        Args:
            pain_event_ids: List of pain event IDs

        Returns:
            List of pain event data
        """
        try:
            ids = [str(eid) for eid in pain_event_ids]
            results = self.collection.get(
                ids=ids,
                include=["embeddings", "metadatas", "documents"]
            )

            events = []
            for i, event_id_str in enumerate(results["ids"]):
                events.append({
                    "pain_event_id": int(event_id_str),
                    "embedding": results["embeddings"][i],
                    "metadata": results["metadatas"][i],
                    "document": results["documents"][i]
                })

            return events

        except Exception as e:
            logger.error(f"Failed to get embeddings by IDs: {e}")
            return []

    def update_metadata(
        self,
        pain_event_id: int,
        metadata: Dict[str, Any]
    ) -> bool:
        """Update metadata for a pain event (e.g., lifecycle_stage, cluster_id)

        Args:
            pain_event_id: Pain event ID
            metadata: New metadata (will be merged with existing)

        Returns:
            bool: True if successful
        """
        try:
            # Get existing metadata
            existing = self.collection.get(
                ids=[str(pain_event_id)],
                include=["metadatas"]
            )

            if not existing["ids"]:
                logger.warning(f"Pain event {pain_event_id} not found in Chroma")
                return False

            # Merge metadata
            updated_metadata = existing["metadatas"][0].copy()
            updated_metadata.update(metadata)

            # Update
            self.collection.update(
                ids=[str(pain_event_id)],
                metadatas=[updated_metadata]
            )

            logger.debug(f"Updated metadata for pain_event {pain_event_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update metadata: {e}")
            return False

    def delete_by_ids(self, pain_event_ids: List[int]) -> bool:
        """Delete embeddings by IDs

        Args:
            pain_event_ids: List of pain event IDs to delete

        Returns:
            bool: True if successful
        """
        try:
            ids = [str(eid) for eid in pain_event_ids]
            self.collection.delete(ids=ids)

            logger.debug(f"Deleted {len(pain_event_ids)} embeddings from Chroma")
            return True

        except Exception as e:
            logger.error(f"Failed to delete embeddings: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get Chroma collection statistics

        Returns:
            Dict with count and storage info
        """
        return {
            "total_embeddings": self.collection.count(),
            "persist_directory": str(self.persist_directory),
            "collection_name": "pain_events",
            "metadata": self.collection.metadata
        }

    def persist(self):
        """Force persist to disk"""
        try:
            # Chroma with DuckDB+Parquet auto-persists, but we can explicitly persist
            logger.info(f"Chroma data persisted to {self.persist_directory}")
        except Exception as e:
            logger.error(f"Failed to persist Chroma: {e}")


# Singleton instance
_chroma_client: Optional[ChromaClient] = None

def get_chroma_client() -> ChromaClient:
    """Get or create singleton Chroma client instance

    Returns:
        ChromaClient instance
    """
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = ChromaClient()
    return _chroma_client
