"""
Embed module for Reddit Pain Point Finder
痛点事件向量化模块 - 为聚类做准备

Updated to use Chroma for vector storage instead of pain_embeddings table.
"""
import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from utils.embedding import embedding_client
from utils.db import db
from utils.chroma_client import get_chroma_client

logger = logging.getLogger(__name__)

class PainEventEmbedder:
    """痛点事件向量化器"""

    def __init__(self):
        """初始化向量化器"""
        self.stats = {
            "total_processed": 0,
            "embeddings_created": 0,
            "errors": 0,
            "processing_time": 0.0,
            "cache_hits": 0
        }

    def _create_embedding_text(self, pain_event: Dict[str, Any]) -> str:
        """创建用于嵌入的文本"""
        text_parts = []

        # 核心要素
        if pain_event.get("actor"):
            text_parts.append(pain_event["actor"])

        if pain_event.get("context"):
            text_parts.append(pain_event["context"])

        if pain_event.get("problem"):
            text_parts.append(pain_event["problem"])

        if pain_event.get("current_workaround"):
            text_parts.append(pain_event["current_workaround"])

        # 用连接符保持语义结构
        embedding_text = " | ".join(text_parts)

        # 检查文本长度
        if len(embedding_text) > 2000:
            logger.warning(f"Embedding text too long ({len(embedding_text)} chars), truncating")
            # 优先保留problem和context
            core_text = f"{pain_event.get('context', '')} | {pain_event.get('problem', '')}"
            if len(core_text) > 1000:
                # 进一步截断
                embedding_text = core_text[:1000]
            else:
                embedding_text = core_text

        return embedding_text

    def embed_single_event(self, pain_event: Dict[str, Any]) -> Optional[List[float]]:
        """为单个痛点事件创建嵌入向量"""
        try:
            # 创建嵌入文本
            embedding_text = self._create_embedding_text(pain_event)

            if not embedding_text:
                logger.warning(f"Empty embedding text for pain event {pain_event.get('id')}")
                return None

            # 创建嵌入向量
            embedding = embedding_client.create_embedding(embedding_text)

            self.stats["embeddings_created"] += 1
            return embedding

        except Exception as e:
            logger.error(f"Failed to create embedding for pain event {pain_event.get('id')}: {e}")
            self.stats["errors"] += 1
            return None

    def save_embedding(self, pain_event_id: int, embedding: List[float], pain_event_data: Dict[str, Any] = None) -> bool:
        """保存嵌入向量到Chroma（新架构）"""
        try:
            chroma = get_chroma_client()

            # Get pain event data if not provided
            if pain_event_data is None:
                with db.get_connection("pain") as conn:
                    cursor = conn.execute("""
                        SELECT * FROM pain_events WHERE id = ?
                    """, (pain_event_id,))
                    row = cursor.fetchone()
                    if row:
                        pain_event_data = dict(row)
                    else:
                        logger.error(f"Pain event {pain_event_id} not found")
                        return False

            # Convert embedding to list if needed
            if hasattr(embedding, 'tolist'):
                embedding = embedding.tolist()
            elif not isinstance(embedding, list):
                embedding = list(embedding)

            # Prepare metadata
            metadata = {
                "pain_event_id": pain_event_id,
                "problem": (pain_event_data.get('problem', '') or "")[:500],
                "context": (pain_event_data.get('context', '') or "")[:500],
                "extracted_at": pain_event_data.get('extracted_at', '') or "",
                "cluster_id": pain_event_data.get('cluster_id') or 0,
                "lifecycle_stage": pain_event_data.get('lifecycle_stage', 'orphan'),
                "embedding_model": embedding_client.model_name
            }

            # Save to Chroma
            success = chroma.add_embeddings(
                pain_event_ids=[pain_event_id],
                embeddings=[embedding],
                metadatas=[metadata]
            )

            if success:
                logger.debug(f"Saved embedding for pain_event {pain_event_id} to Chroma")

            return success

        except Exception as e:
            logger.error(f"Failed to save embedding for pain event {pain_event_id} to Chroma: {e}")
            return False

    def process_pain_events_batch(self, pain_events: List[Dict[str, Any]], batch_size: int = 20) -> int:
        """批量处理痛点事件的向量化"""
        logger.info(f"Creating embeddings for {len(pain_events)} pain events")

        start_time = time.time()
        saved_count = 0

        for i, event in enumerate(pain_events):
            if i % 10 == 0:
                logger.info(f"Processed {i}/{len(pain_events)} pain events")

            # 创建嵌入向量
            embedding = self.embed_single_event(event)
            if embedding is None:
                continue

            # 保存到Chroma（传递event data）
            if self.save_embedding(event["id"], embedding, event):
                saved_count += 1

            # 批量处理延迟
            if i % batch_size == 0 and i > 0:
                time.sleep(1)  # 避免API限制

        # 更新统计信息
        processing_time = time.time() - start_time
        self.stats["total_processed"] = len(pain_events)
        self.stats["processing_time"] = processing_time

        # 添加嵌入客户端统计
        embedding_stats = embedding_client.get_embedding_statistics()
        self.stats["cache_hits"] = embedding_stats.get("cache_hits", 0)

        logger.info(f"Embedding complete: {saved_count}/{len(pain_events)} embeddings saved to Chroma")
        logger.info(f"Processing time: {processing_time:.2f}s")

        return saved_count

    def process_missing_embeddings(self, limit: int = 100) -> Dict[str, Any]:
        """处理缺失嵌入向量的痛点事件（使用Chroma）"""
        logger.info(f"Processing up to {limit} pain events without embeddings")

        try:
            # Get recent pain events from SQLite
            with db.get_connection("pain") as conn:
                cursor = conn.execute("""
                    SELECT * FROM pain_events
                    ORDER BY extracted_at DESC
                    LIMIT ?
                """, (limit * 2,))  # Get more to account for already embedded
                all_pain_events = [dict(row) for row in cursor.fetchall()]

            if not all_pain_events:
                logger.info("No pain events found")
                return {"processed": 0, "embeddings_created": 0}

            # Check which ones are already in Chroma
            chroma = get_chroma_client()
            existing_ids = set()

            # Check in batches
            batch_size = 100
            for i in range(0, len(all_pain_events), batch_size):
                batch = all_pain_events[i:i+batch_size]
                batch_ids = [str(e['id']) for e in batch]

                try:
                    results = chroma.collection.get(
                        ids=batch_ids,
                        include=["metadatas"]
                    )
                    existing_ids.update(int(id) for id in results['ids'])
                except:
                    pass  # Chroma might not have these IDs yet

            # Filter to only those without embeddings
            pain_events_without = [e for e in all_pain_events if e['id'] not in existing_ids]
            pain_events_without = pain_events_without[:limit]  # Apply limit

            if not pain_events_without:
                logger.info(f"All recent pain events already have embeddings in Chroma")
                return {"processed": 0, "embeddings_created": 0}

            logger.info(f"Found {len(pain_events_without)} pain events to embed (out of {len(all_pain_events)} recent events)")

            # 批量创建嵌入向量
            saved_count = self.process_pain_events_batch(pain_events_without)

            return {
                "processed": len(pain_events_without),
                "embeddings_created": saved_count,
                "embedding_stats": self.get_statistics()
            }

        except Exception as e:
            logger.error(f"Failed to process missing embeddings: {e}")
            raise

    def get_embedding_statistics(self) -> Dict[str, Any]:
        """获取向量化统计信息"""
        stats = self.stats.copy()

        if stats["total_processed"] > 0:
            stats["success_rate"] = stats["embeddings_created"] / stats["total_processed"]
            stats["processing_rate"] = stats["total_processed"] / max(stats["processing_time"], 1)
        else:
            stats["success_rate"] = 0
            stats["processing_rate"] = 0

        # 添加嵌入客户端统计
        embedding_stats = embedding_client.get_embedding_statistics()
        stats["embedding_client_stats"] = embedding_stats

        return stats

    def reset_statistics(self):
        """重置统计信息"""
        self.stats = {
            "total_processed": 0,
            "embeddings_created": 0,
            "errors": 0,
            "processing_time": 0.0,
            "cache_hits": 0
        }

    def verify_embeddings(self, limit: int = 50) -> Dict[str, Any]:
        """验证嵌入向量的质量"""
        logger.info(f"Verifying {limit} embeddings")

        try:
            # 获取所有有嵌入向量的痛点事件
            pain_events = db.get_all_pain_events_with_embeddings()

            if len(pain_events) > limit:
                pain_events = pain_events[:limit]

            if not pain_events:
                return {"verified": 0, "issues": []}

            issues = []
            verified_count = 0

            for event in pain_events:
                try:
                    embedding = event.get("embedding_vector")
                    if not embedding:
                        issues.append(f"Event {event['id']}: Missing embedding vector")
                        continue

                    # 检查维度
                    if len(embedding) == 0:
                        issues.append(f"Event {event['id']}: Empty embedding vector")
                        continue

                    # 检查是否包含有效数值
                    if not all(isinstance(x, (int, float)) for x in embedding):
                        issues.append(f"Event {event['id']}: Invalid embedding data types")
                        continue

                    # 检查是否全为零（异常）
                    if all(abs(x) < 1e-6 for x in embedding):
                        issues.append(f"Event {event['id']}: All-zero embedding vector")
                        continue

                    verified_count += 1

                except Exception as e:
                    issues.append(f"Event {event.get('id', 'unknown')}: Verification error - {e}")

            logger.info(f"Embedding verification complete: {verified_count}/{len(pain_events)} passed")

            return {
                "verified": verified_count,
                "total": len(pain_events),
                "issues": issues
            }

        except Exception as e:
            logger.error(f"Failed to verify embeddings: {e}")
            return {"verified": 0, "issues": [f"Verification failed: {e}"]}

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.stats.copy()
        if stats["total_processed"] > 0:
            stats["success_rate"] = stats["embeddings_created"] / stats["total_processed"]
        else:
            stats["success_rate"] = 0.0
        return stats

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Create embeddings for pain events")
    parser.add_argument("--limit", type=int, default=100, help="Limit number of pain events to process")
    parser.add_argument("--verify", action="store_true", help="Verify existing embeddings")
    parser.add_argument("--batch-size", type=int, default=20, help="Batch size for processing")
    args = parser.parse_args()

    try:
        logger.info("Starting pain event embedding...")

        embedder = PainEventEmbedder()

        if args.verify:
            # 验证现有嵌入
            result = embedder.verify_embeddings(limit=args.limit)
            logger.info(f"Verification result: {result}")
        else:
            # 处理缺失的嵌入
            result = embedder.process_missing_embeddings(limit=args.limit)

            logger.info(f"""
=== Embedding Summary ===
Pain events processed: {result['processed']}
Embeddings created: {result['embeddings_created']}
Embedding stats: {result['embedding_stats']}
""")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()