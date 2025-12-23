#!/usr/bin/env python3
"""
测试新的source-aware聚类功能
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.db import db
import json
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_test_data():
    """创建测试数据"""
    logger.info("Creating test pain events with source information...")

    # 创建测试痛点事件
    test_events = [
        {
            "post_id": "test_hn_1",
            "actor": "developer",
            "context": "building web applications",
            "problem": "React development environment takes too long to setup",
            "current_workaround": "Using pre-configured templates",
            "frequency": "weekly",
            "emotional_signal": "frustration",
            "mentioned_tools": ["React", "npm", "webpack"],
            "extraction_confidence": 0.8
        },
        {
            "post_id": "test_hn_2",
            "actor": "developer",
            "context": "frontend development",
            "problem": "JavaScript bundling process is slow and complex",
            "current_workaround": "Using simpler build tools",
            "frequency": "daily",
            "emotional_signal": "exhaustion",
            "mentioned_tools": ["webpack", "rollup", "vite"],
            "extraction_confidence": 0.9
        },
        {
            "post_id": "test_hn_3",
            "actor": "team lead",
            "context": "managing development team",
            "problem": "Code reviews take too much time and slow down delivery",
            "current_workaround": "Doing minimal reviews",
            "frequency": "daily",
            "emotional_signal": "anxiety",
            "mentioned_tools": ["GitHub", "GitLab"],
            "extraction_confidence": 0.8
        },
        {
            "post_id": "test_hn_4",
            "actor": "developer",
            "context": "backend development",
            "problem": "Database migrations are risky and hard to rollback",
            "current_workaround": "Manual schema changes",
            "frequency": "monthly",
            "emotional_signal": "fear",
            "mentioned_tools": ["PostgreSQL", "Rails migrations"],
            "extraction_confidence": 0.9
        },
        {
            "post_id": "test_reddit_1",
            "actor": "student",
            "context": "learning programming",
            "problem": "Can't understand how to use Git branches properly",
            "current_workaround": "Using only main branch",
            "frequency": "weekly",
            "emotional_signal": "confusion",
            "mentioned_tools": ["Git", "GitHub"],
            "extraction_confidence": 0.7
        },
        {
            "post_id": "test_reddit_2",
            "actor": "hobbyist",
            "context": "personal projects",
            "problem": "Deployment process is confusing and error-prone",
            "current_workaround": "Manual file uploads",
            "frequency": "monthly",
            "emotional_signal": "frustration",
            "mentioned_tools": ["AWS", "Docker"],
            "extraction_confidence": 0.8
        },
        {
            "post_id": "test_reddit_3",
            "actor": "junior developer",
            "context": "first job",
            "problem": "Imposter syndrome and feeling overwhelmed by codebase",
            "current_workaround": "Asking for help frequently",
            "frequency": "daily",
            "emotional_signal": "anxiety",
            "mentioned_tools": ["IDE", "documentation"],
            "extraction_confidence": 0.9
        },
        {
            "post_id": "test_reddit_4",
            "actor": "freelancer",
            "context": "client projects",
            "problem": "Hard to estimate project timelines accurately",
            "current_workaround": "Adding large buffers",
            "frequency": "weekly",
            "emotional_signal": "stress",
            "mentioned_tools": ["project management tools"],
            "extraction_confidence": 0.8
        }
    ]

    # 创建对应的posts表数据
    test_posts = [
        {
            "id": "test_hn_1",
            "title": "React setup is too slow",
            "body": "Setting up React environment takes hours",
            "subreddit": "programming",
            "url": "https://news.ycombinator.com/item/1",
            "source": "hackernews",
            "source_id": "1",
            "platform_data": "{}",
            "score": 100,
            "num_comments": 50,
            "upvote_ratio": 0.9,
            "is_self": 1,
            "created_utc": 1640995200,
            "created_at": "2021-12-31T16:00:00Z",
            "author": "hnuser1",
            "category": "ask"
        },
        {
            "id": "test_hn_2",
            "title": "JavaScript bundling pain",
            "body": "Webpack is slow and complex",
            "subreddit": "programming",
            "url": "https://news.ycombinator.com/item/2",
            "source": "hackernews",
            "source_id": "2",
            "platform_data": "{}",
            "score": 150,
            "num_comments": 80,
            "upvote_ratio": 0.95,
            "is_self": 1,
            "created_utc": 1640995200,
            "created_at": "2021-12-31T16:00:00Z",
            "author": "hnuser2",
            "category": "show"
        },
        {
            "id": "test_hn_3",
            "title": "Code reviews bottleneck",
            "body": "Reviews slow down our team",
            "subreddit": "programming",
            "url": "https://news.ycombinator.com/item/3",
            "source": "hackernews",
            "source_id": "3",
            "platform_data": "{}",
            "score": 200,
            "num_comments": 120,
            "upvote_ratio": 0.9,
            "is_self": 1,
            "created_utc": 1640995200,
            "created_at": "2021-12-31T16:00:00Z",
            "author": "hnuser3",
            "category": "ask"
        },
        {
            "id": "test_hn_4",
            "title": "Database migration fears",
            "body": "Migrations are scary",
            "subreddit": "programming",
            "url": "https://news.ycombinator.com/item/4",
            "source": "hackernews",
            "source_id": "4",
            "platform_data": "{}",
            "score": 120,
            "num_comments": 60,
            "upvote_ratio": 0.85,
            "is_self": 1,
            "created_utc": 1640995200,
            "created_at": "2021-12-31T16:00:00Z",
            "author": "hnuser4",
            "category": "ask"
        },
        {
            "id": "test_reddit_1",
            "title": "Git branches confusion",
            "body": "Don't understand git branches",
            "subreddit": "learnprogramming",
            "url": "https://reddit.com/r/learnprogramming/1",
            "source": "reddit",
            "source_id": "1",
            "platform_data": "{}",
            "score": 50,
            "num_comments": 30,
            "upvote_ratio": 0.8,
            "is_self": 1,
            "created_utc": 1640995200,
            "created_at": "2021-12-31T16:00:00Z",
            "author": "reddituser1",
            "category": "question"
        },
        {
            "id": "test_reddit_2",
            "title": "Deployment is hard",
            "body": "How do I deploy my app?",
            "subreddit": "webdev",
            "url": "https://reddit.com/r/webdev/1",
            "source": "reddit",
            "source_id": "2",
            "platform_data": "{}",
            "score": 30,
            "num_comments": 20,
            "upvote_ratio": 0.7,
            "is_self": 1,
            "created_utc": 1640995200,
            "created_at": "2021-12-31T16:00:00Z",
            "author": "reddituser2",
            "category": "help"
        },
        {
            "id": "test_reddit_3",
            "title": "Imposter syndrome",
            "body": "Feeling overwhelmed at work",
            "subreddit": "programming",
            "url": "https://reddit.com/r/programming/1",
            "source": "reddit",
            "source_id": "3",
            "platform_data": "{}",
            "score": 100,
            "num_comments": 100,
            "upvote_ratio": 0.9,
            "is_self": 1,
            "created_utc": 1640995200,
            "created_at": "2021-12-31T16:00:00Z",
            "author": "reddituser3",
            "category": "discussion"
        },
        {
            "id": "test_reddit_4",
            "title": "Project estimation problems",
            "body": "Can't estimate timelines well",
            "subreddit": "freelance",
            "url": "https://reddit.com/r/freelance/1",
            "source": "reddit",
            "source_id": "4",
            "platform_data": "{}",
            "score": 80,
            "num_comments": 40,
            "upvote_ratio": 0.8,
            "is_self": 1,
            "created_utc": 1640995200,
            "created_at": "2021-12-31T16:00:00Z",
            "author": "reddituser4",
            "category": "advice"
        }
    ]

    # 插入posts数据
    for post in test_posts:
        post["raw_data"] = json.dumps(post)
        success = db.insert_raw_post(post)
        if success:
            logger.info(f"✅ Inserted post {post['id']} from source {post['source']}")
        else:
            logger.error(f"❌ Failed to insert post {post['id']}")

    # 插入pain events数据
    pain_event_ids = []
    for event in test_events:
        pain_event_id = db.insert_pain_event(event)
        if pain_event_id:
            pain_event_ids.append(pain_event_id)
            logger.info(f"✅ Inserted pain event for post {event['post_id']}")
        else:
            logger.error(f"❌ Failed to insert pain event for post {event['post_id']}")

    logger.info(f"Created {len(pain_event_ids)} pain events")
    return pain_event_ids

def create_test_embeddings(pain_event_ids):
    """创建测试嵌入向量（模拟）"""
    logger.info("Creating mock embeddings for pain events...")

    import random
    import pickle

    # 为每个pain event创建模拟的1536维嵌入向量
    for i, pain_event_id in enumerate(pain_event_ids):
        # 创建有区别但相似的向量
        base_vector = [random.gauss(0, 1) for _ in range(1536)]

        # 为相似的事件添加相似性（HN事件在前几个维度相似，Reddit事件在其他维度相似）
        if i < 4:  # HN events
            base_vector[0] += 0.5  # 开发相关
            base_vector[1] += 0.3  # 技术问题
        else:  # Reddit events
            base_vector[2] += 0.5  # 学习相关
            base_vector[3] += 0.3  # 困难表达

        # 归一化向量
        import numpy as np
        norm = np.linalg.norm(base_vector)
        base_vector = [x/norm for x in base_vector]

        # 保存嵌入向量
        embedding_blob = pickle.dumps(base_vector)
        model_name = "mock-embedding-model"

        success = db.insert_pain_embedding(pain_event_id, base_vector, model_name)
        if success:
            logger.info(f"✅ Created embedding for pain event {pain_event_id}")
        else:
            logger.error(f"❌ Failed to create embedding for pain event {pain_event_id}")

def test_clustering():
    """测试新的聚类功能"""
    logger.info("Testing source-aware clustering...")

    try:
        from pipeline.cluster import PainEventClusterer
        clusterer = PainEventClusterer()

        # 运行聚类
        result = clusterer.cluster_pain_events(limit=20)

        logger.info("=== Clustering Test Results ===")
        logger.info(f"Clusters created: {result['clusters_created']}")
        logger.info(f"Events processed: {result['events_processed']}")
        logger.info(f"Source groups: {result.get('source_groups', 0)}")

        for cluster in result.get('final_clusters', []):
            logger.info(f"\n📍 Cluster: {cluster['cluster_id']}")
            logger.info(f"   Name: {cluster['cluster_name']}")
            logger.info(f"   Source: {cluster['source_type']}")
            logger.info(f"   Size: {cluster['cluster_size']}")
            logger.info(f"   Common Pain: {cluster.get('common_pain', 'N/A')}")
            logger.info(f"   Common Context: {cluster.get('common_context', 'N/A')}")
            logger.info(f"   Examples: {len(cluster.get('example_events', []))}")

        return True

    except Exception as e:
        logger.error(f"Clustering test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    logger.info("=== Starting Source-Aware Clustering Test ===")

    # 1. 创建测试数据
    pain_event_ids = create_test_data()
    if not pain_event_ids:
        logger.error("Failed to create test data")
        return False

    # 2. 创建测试嵌入向量
    create_test_embeddings(pain_event_ids)

    # 3. 测试聚类功能
    success = test_clustering()

    if success:
        logger.info("🎉 Source-aware clustering test completed successfully!")
        return True
    else:
        logger.error("💥 Clustering test failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)