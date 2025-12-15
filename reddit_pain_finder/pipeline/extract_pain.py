"""
Extract Pain module for Reddit Pain Point Finder
痛点事件抽取模块 - 使用LLM进行结构化抽取
"""
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import time

from utils.llm_client import llm_client
from utils.db import db

logger = logging.getLogger(__name__)

class PainPointExtractor:
    """痛点事件抽取器"""

    def __init__(self):
        """初始化抽取器"""
        self.stats = {
            "total_processed": 0,
            "total_pain_events": 0,
            "extraction_errors": 0,
            "avg_confidence": 0.0,
            "processing_time": 0.0
        }

    def _extract_from_single_post(self, post_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从单个帖子抽取痛点事件"""
        try:
            title = post_data.get("title", "")
            body = post_data.get("body", "")
            subreddit = post_data.get("subreddit", "")
            upvotes = post_data.get("score", 0)
            comments_count = post_data.get("num_comments", 0)

            # 调用LLM进行抽取
            response = llm_client.extract_pain_points(
                title=title,
                body=body,
                subreddit=subreddit,
                upvotes=upvotes,
                comments_count=comments_count
            )

            extraction_result = response["content"]
            pain_events = extraction_result.get("pain_events", [])

            # 为每个痛点事件添加元数据
            for event in pain_events:
                event.update({
                    "post_id": post_data["id"],
                    "subreddit": subreddit,
                    "original_score": upvotes,
                    "extraction_model": response["model"],
                    "extraction_timestamp": datetime.now().isoformat(),
                    "confidence": event.get("confidence", 0.0)
                })

            self.stats["total_pain_events"] += len(pain_events)
            logger.debug(f"Extracted {len(pain_events)} pain events from post {post_data['id']}")

            return pain_events

        except Exception as e:
            logger.error(f"Failed to extract pain from post {post_data.get('id')}: {e}")
            self.stats["extraction_errors"] += 1
            return []

    def _validate_pain_event(self, pain_event: Dict[str, Any]) -> bool:
        """验证痛点事件的质量"""
        try:
            # 检查必需字段
            required_fields = ["problem", "post_id"]
            for field in required_fields:
                if not pain_event.get(field):
                    logger.warning(f"Missing required field '{field}' in pain event")
                    return False

            # 检查问题描述长度
            problem = pain_event.get("problem", "")
            if len(problem) < 10:
                logger.warning(f"Problem description too short: {problem}")
                return False

            if len(problem) > 1000:
                logger.warning(f"Problem description too long: {len(problem)} characters")
                return False

            # 检查置信度
            confidence = pain_event.get("confidence", 0.0)
            if confidence < 0.3:
                logger.warning(f"Low confidence pain event: {confidence}")
                return False

            # 检查是否过于泛泛
            generic_problems = [
                "it's slow", "it's bad", "it doesn't work", "it's broken",
                "i don't like it", "it's annoying", "it's frustrating"
            ]
            problem_lower = problem.lower()
            for generic in generic_problems:
                if problem_lower == generic:
                    logger.warning(f"Too generic problem: {problem}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating pain event: {e}")
            return False

    def _enhance_pain_event(self, pain_event: Dict[str, Any], post_data: Dict[str, Any]) -> Dict[str, Any]:
        """增强痛点事件信息"""
        try:
            enhanced = pain_event.copy()

            # 添加帖子上下文
            enhanced.update({
                "post_title": post_data.get("title", ""),
                "post_category": post_data.get("category", ""),
                "post_pain_score": post_data.get("pain_score", 0.0),
                "post_comments": post_data.get("num_comments", 0)
            })

            # 分析痛点类型
            problem_text = enhanced.get("problem", "").lower()
            context_text = enhanced.get("context", "").lower()
            full_text = f"{problem_text} {context_text}"

            # 痛点类型分类
            pain_types = {
                "workflow": ["workflow", "process", "flow", "pipeline", "automation"],
                "technical": ["code", "programming", "development", "technical", "bug"],
                "efficiency": ["slow", "time", "inefficient", "productivity", "performance"],
                "complexity": ["complex", "complicated", "difficult", "hard", "confusing"],
                "integration": ["integration", "connect", "api", "compatibility", "sync"],
                "cost": ["expensive", "cost", "price", "pricing", "budget"],
                "user_experience": ["ui", "ux", "interface", "usability", "experience"],
                "data": ["data", "database", "storage", "backup", "analysis"]
            }

            detected_types = []
            for pain_type, keywords in pain_types.items():
                if any(keyword in full_text for keyword in keywords):
                    detected_types.append(pain_type)

            enhanced["pain_types"] = detected_types
            enhanced["primary_pain_type"] = detected_types[0] if detected_types else "general"

            # 提取提到的工具
            mentioned_tools = enhanced.get("mentioned_tools", [])
            if not isinstance(mentioned_tools, list):
                mentioned_tools = []

            # 从文本中提取更多工具名（简单规则）
            common_tools = [
                "excel", "google sheets", "slack", "discord", "jira", "trello", "asana",
                "github", "gitlab", "vscode", "intellij", "docker", "kubernetes", "aws",
                "azure", "gcp", "mysql", "postgresql", "mongodb", "redis", "figma",
                "sketch", "photoshop", "wordpress", "shopify", "salesforce"
            ]

            for tool in common_tools:
                if tool in full_text and tool not in mentioned_tools:
                    mentioned_tools.append(tool)

            enhanced["mentioned_tools"] = mentioned_tools

            # 分析频率
            frequency = enhanced.get("frequency", "").lower()
            if "daily" in frequency or "every day" in frequency:
                enhanced["frequency_score"] = 10
            elif "weekly" in frequency or "every week" in frequency:
                enhanced["frequency_score"] = 8
            elif "monthly" in frequency or "every month" in frequency:
                enhanced["frequency_score"] = 6
            elif "often" in frequency or "frequent" in frequency:
                enhanced["frequency_score"] = 7
            elif "sometimes" in frequency or "occasional" in frequency:
                enhanced["frequency_score"] = 4
            elif "rarely" in frequency:
                enhanced["frequency_score"] = 2
            else:
                enhanced["frequency_score"] = 5  # 默认中等频率

            return enhanced

        except Exception as e:
            logger.error(f"Error enhancing pain event: {e}")
            return pain_event

    def extract_from_posts_batch(self, posts: List[Dict[str, Any]], batch_size: int = 10) -> List[Dict[str, Any]]:
        """批量从帖子中抽取痛点事件"""
        logger.info(f"Extracting pain points from {len(posts)} posts")

        all_pain_events = []
        start_time = time.time()

        for i, post in enumerate(posts):
            if i % 10 == 0:
                logger.info(f"Processed {i}/{len(posts)} posts")

            # 抽取痛点事件
            pain_events = self._extract_from_single_post(post)

            # 验证和增强每个痛点事件
            for event in pain_events:
                if self._validate_pain_event(event):
                    enhanced_event = self._enhance_pain_event(event, post)
                    all_pain_events.append(enhanced_event)

            # 添加延迟避免API限制
            time.sleep(0.5)

        # 更新统计信息
        processing_time = time.time() - start_time
        self.stats["total_processed"] = len(posts)
        self.stats["processing_time"] = processing_time

        if all_pain_events:
            avg_confidence = sum(event.get("confidence", 0) for event in all_pain_events) / len(all_pain_events)
            self.stats["avg_confidence"] = avg_confidence

        logger.info(f"Extraction complete: {len(all_pain_events)} pain events from {len(posts)} posts")
        logger.info(f"Processing time: {processing_time:.2f}s, Avg per post: {processing_time/len(posts):.2f}s")

        return all_pain_events

    def save_pain_events(self, pain_events: List[Dict[str, Any]]) -> int:
        """保存痛点事件到数据库"""
        saved_count = 0

        for event in pain_events:
            try:
                # 准备数据库记录
                event_data = {
                    "post_id": event["post_id"],
                    "actor": event.get("actor", ""),
                    "context": event.get("context", ""),
                    "problem": event["problem"],
                    "current_workaround": event.get("current_workaround", ""),
                    "frequency": event.get("frequency", ""),
                    "emotional_signal": event.get("emotional_signal", ""),
                    "mentioned_tools": event.get("mentioned_tools", []),
                    "extraction_confidence": event.get("confidence", 0.0)
                }

                # 保存到数据库
                pain_event_id = db.insert_pain_event(event_data)
                if pain_event_id:
                    saved_count += 1
                    logger.debug(f"Saved pain event {pain_event_id}: {event['problem'][:50]}...")

            except Exception as e:
                logger.error(f"Failed to save pain event: {e}")

        logger.info(f"Saved {saved_count}/{len(pain_events)} pain events to database")
        return saved_count

    def process_unextracted_posts(self, limit: int = 100) -> Dict[str, Any]:
        """处理未抽取的帖子"""
        logger.info(f"Processing up to {limit} unextracted posts")

        try:
            # 获取未处理的过滤帖子
            unextracted_posts = db.get_filtered_posts(limit=limit, min_pain_score=0.3)

            if not unextracted_posts:
                logger.info("No unextracted posts found")
                return {"processed": 0, "pain_events": 0}

            logger.info(f"Found {len(unextracted_posts)} posts to extract from")

            # 抽取痛点事件
            pain_events = self.extract_from_posts_batch(unextracted_posts)

            # 保存到数据库
            saved_count = self.save_pain_events(pain_events)

            return {
                "processed": len(unextracted_posts),
                "pain_events_extracted": len(pain_events),
                "pain_events_saved": saved_count,
                "extraction_stats": self.get_statistics()
            }

        except Exception as e:
            logger.error(f"Failed to process unextracted posts: {e}")
            raise

    def get_statistics(self) -> Dict[str, Any]:
        """获取抽取统计信息"""
        stats = self.stats.copy()
        if stats["total_processed"] > 0:
            stats["avg_events_per_post"] = stats["total_pain_events"] / stats["total_processed"]
            stats["processing_rate"] = stats["total_processed"] / max(stats["processing_time"], 1)
        else:
            stats["avg_events_per_post"] = 0
            stats["processing_rate"] = 0

        # 添加LLM客户端统计
        llm_stats = llm_client.get_statistics()
        stats["llm_stats"] = llm_stats

        return stats

    def reset_statistics(self):
        """重置统计信息"""
        self.stats = {
            "total_processed": 0,
            "total_pain_events": 0,
            "extraction_errors": 0,
            "avg_confidence": 0.0,
            "processing_time": 0.0
        }

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Extract pain points from filtered Reddit posts")
    parser.add_argument("--limit", type=int, default=100, help="Limit number of posts to process")
    parser.add_argument("--min-score", type=float, default=0.3, help="Minimum pain score threshold")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for processing")
    args = parser.parse_args()

    try:
        logger.info("Starting pain point extraction...")

        extractor = PainPointExtractor()

        # 处理未抽取的帖子
        result = extractor.process_unextracted_posts(limit=args.limit)

        logger.info(f"""
=== Extraction Summary ===
Posts processed: {result['processed']}
Pain events extracted: {result['pain_events_extracted']}
Pain events saved: {result['pain_events_saved']}
Extraction stats: {result['extraction_stats']}
""")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()