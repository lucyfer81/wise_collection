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

    def _extract_from_single_post(self, post_data: Dict[str, Any], retry_count: int = 0) -> List[Dict[str, Any]]:
        """从单个帖子抽取痛点事件"""
        max_retries = 2
        try:
            title = post_data.get("title", "")
            body = post_data.get("body", "")
            subreddit = post_data.get("subreddit", "")
            upvotes = post_data.get("score", 0)
            comments_count = post_data.get("num_comments", 0)

            # Load top comments for context
            top_n_comments = 10
            comments = db.get_top_comments_for_post(post_data["id"], top_n=top_n_comments)
            logger.debug(f"Loaded {len(comments)} comments for post {post_data['id']}")

            # 调用LLM进行抽取（包含评论上下文）
            response = llm_client.extract_pain_points(
                title=title,
                body=body,
                subreddit=subreddit,
                upvotes=upvotes,
                comments_count=comments_count,
                top_comments=comments
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
                    "confidence": event.get("confidence", 0.0),
                    "comments_used": len(comments),  # 新增：使用的评论数量
                    "evidence_sources": event.get("evidence_sources", ["post"])  # 新增：证据来源
                })

            self.stats["total_pain_events"] += len(pain_events)
            logger.debug(f"Extracted {len(pain_events)} pain events from post {post_data['id']}")

            return pain_events

        except Exception as e:
            error_msg = f"Failed to extract pain from post {post_data.get('id')}: {e}"

            # 如果是超时错误且还有重试机会
            if "timeout" in str(e).lower() and retry_count < max_retries:
                logger.warning(f"{error_msg} (retry {retry_count + 1}/{max_retries})")
                time.sleep(5)  # 等待5秒后重试
                return self._extract_from_single_post(post_data, retry_count + 1)
            else:
                logger.error(error_msg)
                self.stats["extraction_errors"] += 1
                return []

    def _extract_from_single_comment(self, comment_data: Dict[str, Any], retry_count: int = 0) -> List[Dict[str, Any]]:
        """从单条评论抽取痛点事件 - Phase 2: Include Comments

        Args:
            comment_data: 包含评论数据的字典
            retry_count: 重试次数

        Returns:
            痛点事件列表
        """
        max_retries = 2
        try:
            comment_id = comment_data["comment_id"]
            post_id = comment_data["post_id"]
            body = comment_data["body"]
            score = comment_data.get("score", 0)

            # 1. 加载父帖子作为上下文（不是主要来源）
            parent_post = db.get_parent_post_context(post_id)
            logger.debug(f"Loaded parent post context for comment {comment_id}: {parent_post.get('title', 'N/A')[:50]}...")

            # 2. 调用LLM进行抽取（comment作为主要来源）
            response = llm_client.extract_pain_points(
                title=parent_post.get("title", "[Comment context]"),  # 仅作为上下文
                body=body,  # PRIMARY: 评论本身
                subreddit=parent_post.get("subreddit", ""),
                upvotes=score,
                comments_count=0,  # 评论没有子评论（暂不支持）
                top_comments=[],   # 无子评论
                metadata={
                    "source_type": "comment",
                    "parent_post_title": parent_post.get("title"),
                    "parent_post_body": parent_post.get("body", "")[:500]  # 截断上下文
                }
            )

            extraction_result = response["content"]
            pain_events = extraction_result.get("pain_events", [])

            # 3. 为每个痛点事件添加元数据
            for event in pain_events:
                event.update({
                    "post_id": post_id,           # 父帖子（用于关联）
                    "comment_id": comment_id,     # 实际来源
                    "source_type": "comment",     # 标记为评论来源
                    "source_id": str(comment_id),  # NEW: 具体来源ID
                    "parent_post_id": post_id,    # NEW: 父帖子ID
                    "subreddit": parent_post.get("subreddit", ""),
                    "original_score": score,
                    "extraction_model": response["model"],
                    "extraction_timestamp": datetime.now().isoformat(),
                    "confidence": event.get("confidence", 0.0),
                    "comments_used": 0,  # 评论没有使用子评论
                    "evidence_sources": ["comment"]  # 明确标记不是来自post
                })

            self.stats["total_pain_events"] += len(pain_events)
            logger.debug(f"Extracted {len(pain_events)} pain events from comment {comment_id}")

            return pain_events

        except Exception as e:
            error_msg = f"Failed to extract pain from comment {comment_data.get('comment_id')}: {e}"

            # 如果是超时错误且还有重试机会
            if "timeout" in str(e).lower() and retry_count < max_retries:
                logger.warning(f"{error_msg} (retry {retry_count + 1}/{max_retries})")
                time.sleep(5)  # 等待5秒后重试
                return self._extract_from_single_comment(comment_data, retry_count + 1)
            else:
                logger.error(error_msg)
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
            time.sleep(2.0)  # 增加到2秒间隔

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
        """保存痛点事件到数据库（支持post和comment来源）"""
        saved_count = 0

        for event in pain_events:
            try:
                # 准备数据库记录
                event_data = {
                    "post_id": event["post_id"],
                    "source_type": event.get("source_type", "post"),  # NEW
                    "source_id": event.get("source_id"),              # NEW
                    "parent_post_id": event.get("parent_post_id"),    # NEW
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

            # 记录失败的帖子ID，用于后续跳过
            failed_posts = []

            # 抽取痛点事件（带失败恢复）
            pain_events = []
            for i, post in enumerate(unextracted_posts):
                if i % 10 == 0:
                    logger.info(f"Processed {i}/{len(unextracted_posts)} posts")

                try:
                    # 尝试抽取单个帖子
                    post_events = self._extract_from_single_post(post)

                    # 验证和增强每个痛点事件
                    for event in post_events:
                        if self._validate_pain_event(event):
                            enhanced_event = self._enhance_pain_event(event, post)
                            pain_events.append(enhanced_event)

                    logger.debug(f"Successfully processed post {post.get('id')}")

                except Exception as e:
                    logger.error(f"Failed to process post {post.get('id')}: {e}")
                    failed_posts.append(post.get('id'))
                    self.stats["extraction_errors"] += 1
                    continue

                # 添加延迟避免API限制，使用动态延迟
                delay = 3.0 + (i % 5)  # 3-7秒动态延迟
                logger.debug(f"Waiting {delay:.1f}s before next post...")
                time.sleep(delay)

            # 保存成功处理的痛点事件
            saved_count = self.save_pain_events(pain_events)

            # 记录失败统计
            if failed_posts:
                logger.warning(f"Failed to process {len(failed_posts)} posts: {failed_posts}")

            return {
                "processed": len(unextracted_posts) - len(failed_posts),
                "failed": len(failed_posts),
                "pain_events_extracted": len(pain_events),
                "pain_events_saved": saved_count,
                "extraction_stats": self.get_statistics(),
                "failed_posts": failed_posts
            }

        except Exception as e:
            logger.error(f"Failed to process unextracted posts: {e}")
            raise

    def process_unextracted_comments(self, limit: int = 100) -> Dict[str, Any]:
        """处理未抽取的过滤评论 - Phase 2: Include Comments

        Args:
            limit: 限制处理的评论数量

        Returns:
            处理结果统计字典
        """
        logger.info(f"Processing up to {limit} filtered comments")

        try:
            # 获取过滤后的评论
            filtered_comments = db.get_all_filtered_comments(limit=limit)

            if not filtered_comments:
                logger.info("No filtered comments found")
                return {"processed": 0, "pain_events": 0}

            logger.info(f"Found {len(filtered_comments)} comments to extract from")

            # 记录失败的评论ID
            failed_comments = []
            total_pain_events = []

            # 抽取痛点事件（带失败恢复）
            for i, comment in enumerate(filtered_comments):
                if i % 10 == 0:
                    logger.info(f"Processed {i}/{len(filtered_comments)} comments")

                try:
                    # 尝试抽取单条评论
                    comment_events = self._extract_from_single_comment(comment)

                    # 验证每个痛点事件
                    validated_events = []
                    for event in comment_events:
                        if self._validate_pain_event(event):
                            validated_events.append(event)

                    # 立即保存这条comment的events（支持中断恢复）
                    if validated_events:
                        saved = self.save_pain_events(validated_events)
                        logger.info(f"Saved {saved} pain events from comment {comment.get('comment_id')}")
                        total_pain_events.extend(validated_events)
                    else:
                        logger.warning(f"No valid pain events extracted from comment {comment.get('comment_id')}")

                    # 标记comment为已尝试（无论成功或失败）
                    db.mark_comment_extraction_attempted(comment.get('comment_id'))
                    logger.debug(f"Marked comment {comment.get('comment_id')} as attempted")

                except Exception as e:
                    logger.error(f"Failed to process comment {comment.get('comment_id')}: {e}")

                    # 即使失败也标记为已尝试，避免无限重试
                    db.mark_comment_extraction_attempted(comment.get('comment_id'))
                    logger.debug(f"Marked failed comment {comment.get('comment_id')} as attempted")

                    failed_comments.append(comment.get('comment_id'))
                    self.stats["extraction_errors"] += 1
                    continue

                # 添加延迟避免API限制
                delay = 2.0 + (i % 3)  # 2-4秒动态延迟（评论处理更快）
                logger.debug(f"Waiting {delay:.1f}s before next comment...")
                time.sleep(delay)

            saved_count = len(total_pain_events)

            # 记录失败统计
            if failed_comments:
                logger.warning(f"Failed to process {len(failed_comments)} comments: {failed_comments}")

            return {
                "processed": len(filtered_comments) - len(failed_comments),
                "failed": len(failed_comments),
                "pain_events_extracted": len(total_pain_events),
                "pain_events_saved": saved_count,
                "extraction_stats": self.get_statistics(),
                "failed_comments": failed_comments
            }

        except Exception as e:
            logger.error(f"Failed to process unextracted comments: {e}")
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