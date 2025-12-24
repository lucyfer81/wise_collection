"""
回填评论数据
从 posts.raw_data 中提取评论并存入独立的 comments 表
"""
import logging
import json
from utils.db import db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _normalize_comments(comments: list, source: str) -> list:
    """规范化评论数据格式"""
    normalized = []

    for comment in comments:
        # Reddit 和 HN 的评论格式已经在 fetch 阶段统一
        # 这里主要做防御性检查
        if isinstance(comment, dict):
            normalized.append({
                "id": comment.get("id"),
                "author": comment.get("author", ""),
                "body": comment.get("body", ""),
                "score": comment.get("score", 0),
                "created_utc": comment.get("created_utc"),
                "created_at": comment.get("created_at")
            })

    return normalized

def backfill_comments(batch_size: int = 100, dry_run: bool = False) -> dict:
    """
    回填评论数据

    Args:
        batch_size: 每批处理的帖子数量
        dry_run: 如果为 True，只分析不实际插入

    Returns:
        统计信息字典
    """
    stats = {
        "total_posts": 0,
        "posts_with_comments": 0,
        "total_comments_extracted": 0,
        "comments_inserted": 0,
        "errors": 0
    }

    try:
        with db.get_connection("raw") as conn:
            # 获取所有包含 raw_data 的帖子
            cursor = conn.execute("""
                SELECT id, source, raw_data
                FROM posts
                WHERE raw_data IS NOT NULL
                AND raw_data != ''
                ORDER BY collected_at DESC
            """)

            posts = cursor.fetchall()
            stats["total_posts"] = len(posts)

            logger.info(f"Found {len(posts)} posts with raw_data to process")

            if len(posts) == 0:
                logger.warning("No posts with raw_data found")
                return stats

            # 分批处理
            for i in range(0, len(posts), batch_size):
                batch = posts[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(posts) + batch_size - 1) // batch_size
                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} posts)")

                for row in batch:
                    post_id = row['id']
                    source = row['source']
                    raw_data = row['raw_data']

                    try:
                        post_json = json.loads(raw_data)
                        comments = post_json.get("comments", [])

                        if not comments:
                            continue

                        stats["posts_with_comments"] += 1
                        stats["total_comments_extracted"] += len(comments)

                        if not dry_run:
                            # 提取并规范化评论数据
                            normalized_comments = _normalize_comments(comments, source)

                            # 插入评论
                            inserted = db.insert_comments(post_id, normalized_comments, source)
                            stats["comments_inserted"] += inserted
                        else:
                            # Dry-run 模式只统计
                            stats["comments_inserted"] += len(comments)

                        if (stats["posts_with_comments"] % 10) == 0:
                            logger.debug(f"Processed {stats['posts_with_comments']} posts with comments so far")

                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error for post {post_id}: {e}")
                        stats["errors"] += 1
                    except Exception as e:
                        logger.error(f"Error processing post {post_id}: {e}")
                        stats["errors"] += 1

        logger.info(f"""
=== Backfill Summary ===
Total posts processed: {stats['total_posts']}
Posts with comments: {stats['posts_with_comments']}
Total comments found: {stats['total_comments_extracted']}
Comments {'would be' if dry_run else 'actually'} inserted: {stats['comments_inserted']}
Errors: {stats['errors']}
""")

        return stats

    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        raise

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill comments from posts.raw_data")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, don't insert")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for processing")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("Running in DRY-RUN mode - no data will be inserted")

    backfill_comments(batch_size=args.batch_size, dry_run=args.dry_run)
