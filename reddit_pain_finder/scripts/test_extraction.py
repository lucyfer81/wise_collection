#!/usr/bin/env python3
"""
Simple Test Script for Comment-Aware Pain Extraction
测试脚本 - 验证新的评论感知痛点提取是否正常工作
"""
import logging
from utils.llm_client import llm_client
from utils.db import db

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    """测试新的评论感知提取方法"""
    logger.info("Testing comment-aware pain extraction...")

    # 获取一个有评论的帖子
    posts = db.get_filtered_posts(limit=10, min_pain_score=0.6)
    if not posts:
        logger.error("No posts found for testing")
        return

    post = posts[0]
    logger.info(f"Testing post: {post['title'][:60]}...")
    logger.info(f"URL: {post['url']}\n")

    # 加载评论
    comments = db.get_top_comments_for_post(post['id'], top_n=5)
    logger.info(f"Loaded {len(comments)} comments")

    # 提取痛点（使用新方法）
    response = llm_client.extract_pain_points(
        title=post['title'],
        body=post['body'],
        subreddit=post['subreddit'],
        upvotes=post['score'],
        comments_count=post['num_comments'],
        top_comments=comments
    )

    result = response.get("content", {})
    pain_events = result.get("pain_events", [])

    logger.info(f"\n✅ Extracted {len(pain_events)} pain events:\n")

    for i, event in enumerate(pain_events, 1):
        logger.info(f"{i}. {event.get('problem', 'N/A')}")
        logger.info(f"   Confidence: {event.get('confidence', 0):.2f}")
        logger.info(f"   Evidence: {event.get('evidence_sources', [])}")
        if event.get('current_workaround'):
            logger.info(f"   Workaround: {event.get('current_workaround')[:60]}...")
        logger.info("")

    if len(pain_events) > 0:
        logger.info("✅ Test passed! Comment-aware extraction is working.")
    else:
        logger.warning("⚠️  No pain events extracted. This might be okay for some posts.")

if __name__ == "__main__":
    main()
