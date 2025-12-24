"""
Filter Signal module for Reddit Pain Point Finder
痛点信号过滤模块 - 冷血守门员
"""
import os
import json
import logging
import re
import yaml
from typing import List, Dict, Any, Set, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class PainSignalFilter:
    """痛点信号过滤器"""

    def __init__(self, config_path: str = "config/thresholds.yaml"):
        """初始化过滤器"""
        self.thresholds = self._load_thresholds(config_path)
        self.subreddits_config = self._load_subreddits_config("config/subreddits.yaml")
        self.stats = {
            "total_processed": 0,
            "passed_filter": 0,
            "filtered_out": 0,
            "filter_reasons": {}
        }

    def _load_thresholds(self, config_path: str) -> Dict[str, Any]:
        """加载阈值配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load thresholds from {config_path}: {e}")
            return {}

    def _load_subreddits_config(self, config_path: str) -> Dict[str, Any]:
        """加载子版块配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load subreddits config from {config_path}: {e}")
            return {}

    def _check_quality_thresholds(self, post_data: Dict[str, Any]) -> Tuple[bool, str]:
        """检查质量阈值"""
        quality_config = self.thresholds.get("reddit_quality", {})
        base_thresholds = quality_config.get("base", {})

        score = post_data.get("score", 0)
        comments = post_data.get("num_comments", 0)
        upvote_ratio = post_data.get("upvote_ratio", 0.0)
        text_length = len(post_data.get("title", "") + " " + post_data.get("body", ""))

        # 检查基础阈值
        if score < base_thresholds.get("min_upvotes", 5):
            return False, f"Too few upvotes: {score} < {base_thresholds.get('min_upvotes')}"

        if comments < base_thresholds.get("min_comments", 3):
            return False, f"Too few comments: {comments} < {base_thresholds.get('min_comments')}"

        if upvote_ratio < base_thresholds.get("min_upvote_ratio", 0.1):
            return False, f"Too low upvote ratio: {upvote_ratio:.2f} < {base_thresholds.get('min_upvote_ratio')}"

        if text_length < base_thresholds.get("min_post_length", 50):
            return False, f"Post too short: {text_length} < {base_thresholds.get('min_post_length')}"

        if text_length > base_thresholds.get("max_post_length", 5000):
            return False, f"Post too long: {text_length} > {base_thresholds.get('max_post_length')}"

        return True, "Passed quality thresholds"

    def _check_pain_keywords(self, post_data: Dict[str, Any]) -> Tuple[bool, List[str], float]:
        """检查痛点关键词"""
        title = (post_data.get("title", "")).lower()
        body = (post_data.get("body", "")).lower()
        full_text = f"{title} {body}"

        pain_keywords = self.subreddits_config.get("pain_keywords", {})
        matched_keywords = []
        keyword_scores = {}

        # 统计各类别关键词匹配
        for category, keywords in pain_keywords.items():
            category_matches = 0
            category_weight = {"frustration": 1.0, "inefficiency": 0.8, "complexity": 0.7, "workflow": 0.9, "cost": 0.6}.get(category, 0.5)

            for keyword in keywords:
                if keyword.lower() in full_text:
                    matched_keywords.append(f"{category}:{keyword}")
                    category_matches += 1
                    keyword_scores[keyword] = category_weight

            # 计算该类别的得分
            if category_matches > 0:
                keyword_scores[f"category_{category}"] = category_matches * category_weight

        # 计算总痛点分数
        total_score = sum(score for score in keyword_scores.values() if isinstance(score, (int, float)))

        # 标准化分数（0-1范围）
        normalized_score = min(total_score / 5.0, 1.0)  # 假设5分为满分

        return len(matched_keywords) > 0, matched_keywords, normalized_score

    def _check_aspiration_keywords(self, post_data: Dict[str, Any]) -> Tuple[bool, List[str], float]:
        """检查愿望关键词 - 寻找机会信号"""
        title = (post_data.get("title", "")).lower()
        body = (post_data.get("body", "")).lower()
        full_text = f"{title} {body}"

        aspiration_keywords = self.subreddits_config.get("aspiration_keywords", {})
        matched_keywords = []
        keyword_scores = {}

        # 统计各类别关键词匹配
        for category, keywords in aspiration_keywords.items():
            category_matches = 0
            category_weight = {
                "forward_looking": 1.0,
                "opportunity": 0.9,
                "workflow_gap": 0.8
            }.get(category, 0.5)

            for keyword in keywords:
                if keyword.lower() in full_text:
                    matched_keywords.append(f"{category}:{keyword}")
                    category_matches += 1
                    keyword_scores[keyword] = category_weight

            # 计算该类别的得分
            if category_matches > 0:
                keyword_scores[f"category_{category}"] = category_matches * category_weight

        # 计算总愿望分数
        total_score = sum(score for score in keyword_scores.values() if isinstance(score, (int, float)))

        # 标准化分数（0-1范围）
        normalized_score = min(total_score / 3.0, 1.0)  # 3分为满分

        return len(matched_keywords) > 0, matched_keywords, normalized_score

    def _check_pain_patterns(self, post_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """检查痛点句式模式"""
        title = (post_data.get("title", "")).lower()
        body = (post_data.get("body", "")).lower()
        full_text = f"{title} {body}"

        pain_config = self.thresholds.get("pain_signal", {})
        required_patterns = pain_config.get("pain_patterns", {}).get("required_patterns", [])
        strong_signals = pain_config.get("pain_patterns", {}).get("strong_signals", [])

        matched_patterns = []
        matched_strong = []

        # 检查必须匹配的句式
        for pattern in required_patterns:
            if pattern.lower() in full_text:
                matched_patterns.append(pattern)

        # 检查强化信号句式
        for pattern in strong_signals:
            if pattern.lower() in full_text:
                matched_strong.append(pattern)

        # 判断是否通过模式检查
        min_pattern_matches = pain_config.get("pain_patterns", {}).get("min_pattern_matches", 1)
        min_strong_signals = pain_config.get("pain_patterns", {}).get("min_strong_signals", 0)

        has_required = len(matched_patterns) >= min_pattern_matches
        has_strong = len(matched_strong) >= min_strong_signals

        all_matches = matched_patterns + matched_strong

        return (has_required or has_strong), all_matches

    def _check_exclusion_patterns(self, post_data: Dict[str, Any]) -> Tuple[bool, str]:
        """检查排除模式"""
        title = (post_data.get("title", "")).lower()
        body = (post_data.get("body", "")).lower()
        full_text = f"{title} {body}"

        exclude_patterns = self.subreddits_config.get("exclude_patterns", {})

        for category, patterns in exclude_patterns.items():
            for pattern in patterns:
                if pattern.lower() in full_text:
                    return False, f"Excluded due to {category}: {pattern}"

        return True, "No exclusion patterns matched"

    def _calculate_emotional_intensity(self, post_data: Dict[str, Any]) -> float:
        """计算情绪强度"""
        title = (post_data.get("title", "")).lower()
        body = (post_data.get("body", "")).lower()
        full_text = f"{title} {body}"

        # 高强度情绪词汇
        high_intensity_words = [
            "frustrated", "frustrating", "annoying", "annoyed", "hate", "terrible",
            "awful", "horrible", "disaster", "catastrophe", "nightmare", "hell",
            "impossible", "useless", "worthless", "broken", "crashed", "failed"
        ]

        # 中强度情绪词汇
        medium_intensity_words = [
            "difficult", "hard", "struggling", "trouble", "problem", "issue",
            "challenge", "confusing", "complicated", "complex", "slow", "tedious"
        ]

        # 低强度情绪词汇
        low_intensity_words = [
            "annoyance", "minor", "slight", "inconvenient", "suboptimal", "could be better"
        ]

        high_count = sum(1 for word in high_intensity_words if word in full_text)
        medium_count = sum(1 for word in medium_intensity_words if word in full_text)
        low_count = sum(1 for word in low_intensity_words if word in full_text)

        # 计算加权情绪强度
        intensity = (high_count * 1.0 + medium_count * 0.6 + low_count * 0.3) / max(len(full_text.split()) / 100, 1)
        return min(intensity, 1.0)

    def _check_post_type_specific(self, post_data: Dict[str, Any]) -> Tuple[bool, str]:
        """检查特定类型帖子的阈值"""
        subreddit = post_data.get("subreddit", "").lower()
        score = post_data.get("score", 0)
        comments = post_data.get("num_comments", 0)

        quality_config = self.thresholds.get("reddit_quality", {})
        type_specific = quality_config.get("type_specific", {})

        # 根据子版块类别判断类型
        post_type = "general"  # 默认类型
        if any(keyword in subreddit for keyword in ["programming", "sysadmin", "webdev", "technical"]):
            post_type = "technical"
        elif any(keyword in subreddit for keyword in ["entrepreneur", "startups", "business"]):
            post_type = "business"
        elif "discussion" in subreddit or comments > score * 2:
            post_type = "discussion"

        if post_type in type_specific:
            type_config = type_specific[post_type]
            if score < type_config.get("min_upvotes", 0):
                return False, f"Type {post_type}: too few upvotes: {score} < {type_config.get('min_upvotes')}"
            if comments < type_config.get("min_comments", 0):
                return False, f"Type {post_type}: too few comments: {comments} < {type_config.get('min_comments')}"

        return True, f"Type {post_type} check passed"

    def _get_trust_based_thresholds(self, post_data: Dict[str, Any]) -> Dict[str, float]:
        """根据帖子所属subreddit的trust_level返回动态阈值"""
        subreddit = post_data.get("subreddit", "").lower()

        # 查找subreddit所属category及其trust_level
        trust_level = 0.5  # 默认值
        for category_name, category_config in self.subreddits_config.items():
            if isinstance(category_config, dict):
                # 检查category级别的trust_level
                if "trust_level" in category_config:
                    category_trust = category_config["trust_level"]
                    # 检查subreddit是否在这个category下
                    for sub_name in category_config.keys():
                        if sub_name.lower() == subreddit and sub_name != "trust_level":
                            trust_level = category_trust
                            break

        # 从posts表获取trust_level（如果有）
        post_trust_level = post_data.get("trust_level", trust_level)

        # 根据trust_level返回阈值
        if post_trust_level < 0.5:
            # 低信任度板块 - 更严格的标准
            return {
                "min_comments": 20,
                "min_upvotes": 50,
                "min_engagement_score": 0.6
            }
        elif post_trust_level < 0.7:
            # 中等信任度板块 - 中等标准
            return {
                "min_comments": 10,
                "min_upvotes": 25,
                "min_engagement_score": 0.4
            }
        else:
            # 高信任度板块 - 标准阈值
            return {
                "min_comments": 5,
                "min_upvotes": 10,
                "min_engagement_score": 0.2
            }

    def filter_post(self, post_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """过滤单个帖子"""
        self.stats["total_processed"] += 1

        filter_result = {
            "post_id": post_data.get("id"),
            "passed": False,
            "pain_score": 0.0,
            "reasons": [],
            "matched_keywords": [],
            "matched_patterns": [],
            "emotional_intensity": 0.0,
            "filter_summary": {}
        }

        # 1. 质量阈值检查
        quality_passed, quality_reason = self._check_quality_thresholds(post_data)
        if not quality_passed:
            self.stats["filtered_out"] += 1
            self.stats["filter_reasons"][quality_reason] = self.stats["filter_reasons"].get(quality_reason, 0) + 1
            filter_result["reasons"].append(quality_reason)
            filter_result["filter_summary"] = {"reason": "quality_threshold", "details": quality_reason}
            return False, filter_result

        # 2. 排除模式检查
        exclusion_passed, exclusion_reason = self._check_exclusion_patterns(post_data)
        if not exclusion_passed:
            self.stats["filtered_out"] += 1
            self.stats["filter_reasons"][exclusion_reason] = self.stats["filter_reasons"].get(exclusion_reason, 0) + 1
            filter_result["reasons"].append(exclusion_reason)
            filter_result["filter_summary"] = {"reason": "exclusion_pattern", "details": exclusion_reason}
            return False, filter_result

        # 3. 痛点关键词检查
        has_keywords, matched_keywords, keyword_score = self._check_pain_keywords(post_data)
        filter_result["matched_keywords"] = matched_keywords

        # 3.5 愿望关键词检查
        has_aspiration, matched_aspirations, aspiration_score = self._check_aspiration_keywords(post_data)
        filter_result["matched_aspirations"] = matched_aspirations

        # 4. 痛点句式检查
        has_patterns, matched_patterns = self._check_pain_patterns(post_data)
        filter_result["matched_patterns"] = matched_patterns

        # 5. 情绪强度计算
        emotional_intensity = self._calculate_emotional_intensity(post_data)
        filter_result["emotional_intensity"] = emotional_intensity

        # 6. 类型特定检查
        type_passed, type_reason = self._check_post_type_specific(post_data)
        if not type_passed:
            self.stats["filtered_out"] += 1
            self.stats["filter_reasons"][type_reason] = self.stats["filter_reasons"].get(type_reason, 0) + 1
            filter_result["reasons"].append(type_reason)
            filter_result["filter_summary"] = {"reason": "type_specific", "details": type_reason}
            return False, filter_result

        # 6.5 基于信任度的动态阈值检查
        trust_thresholds = self._get_trust_based_thresholds(post_data)
        min_comments = trust_thresholds["min_comments"]
        min_upvotes = trust_thresholds["min_upvotes"]
        min_engagement_score = trust_thresholds["min_engagement_score"]

        # 计算参与度分数
        engagement_score = min(
            (post_data.get("score", 0) / min_upvotes + post_data.get("num_comments", 0) / min_comments) / 2.0,
            1.0
        )

        # 对于低信任度板块，必须满足参与度要求
        if post_data.get("trust_level", 0.5) < 0.5 and engagement_score < min_engagement_score:
            self.stats["filtered_out"] += 1
            failure_reason = f"Low trust post with insufficient engagement: {engagement_score:.2f} < {min_engagement_score}"
            self.stats["filter_reasons"][failure_reason] = self.stats["filter_reasons"].get(failure_reason, 0) + 1
            filter_result["reasons"].append(failure_reason)
            filter_result["filter_summary"] = {
                "reason": "trust_based_engagement",
                "details": {
                    "trust_level": post_data.get("trust_level", 0.5),
                    "engagement_score": engagement_score,
                    "min_required": min_engagement_score
                }
            }
            return False, filter_result

        filter_result["engagement_score"] = engagement_score
        filter_result["trust_level"] = post_data.get("trust_level", 0.5)

        # 计算综合痛点分数
        pain_score = 0.0

        # 关键词分数 (40%)
        pain_score += keyword_score * 0.4

        # 句式分数 (30%)
        pattern_score = min(len(matched_patterns) / 3.0, 1.0) * 0.3
        pain_score += pattern_score

        # 情绪强度分数 (20%)
        pain_score += emotional_intensity * 0.2

        # 基础质量分数 (10%)
        score_normalized = min(post_data.get("score", 0) / 100.0, 1.0)
        comments_normalized = min(post_data.get("num_comments", 0) / 50.0, 1.0)
        quality_score = (score_normalized + comments_normalized) / 2.0 * 0.1
        pain_score += quality_score

        # 确保分数在0-1范围内
        pain_score = min(max(pain_score, 0.0), 1.0)

        filter_result["pain_score"] = pain_score

        # 判断是否通过痛点信号检查
        pain_config = self.thresholds.get("pain_signal", {})
        min_keyword_matches = pain_config.get("keyword_match", {}).get("min_matches", 1)
        min_emotional_intensity = pain_config.get("emotional_intensity", {}).get("min_score", 0.3)

        # 最终判断 - 支持愿望信号通过
        passed = False

        # Set default pass_type if not already set
        if "pass_type" not in filter_result:
            filter_result["pass_type"] = "pain"

        # 路径1: 强痛点信号（原有逻辑）
        if (has_keywords and
            len(matched_keywords) >= min_keyword_matches and
            emotional_intensity >= min_emotional_intensity and
            pain_score >= 0.3):
            passed = True

        # 路径2: 愿望信号 + 高参与度（新增逻辑）
        elif (has_aspiration and
              engagement_score >= min_engagement_score and
              aspiration_score >= 0.4):
            passed = True
            filter_result["pass_type"] = "aspiration"
            filter_result["aspiration_score"] = aspiration_score

        if passed:
            self.stats["passed_filter"] += 1
            filter_result["passed"] = True
            filter_result["filter_summary"] = {
                "reason": "passed",
                "pain_score": pain_score,
                "components": {
                    "keywords": keyword_score,
                    "patterns": pattern_score,
                    "emotion": emotional_intensity,
                    "quality": quality_score
                }
            }
        else:
            self.stats["filtered_out"] += 1
            failure_reasons = []
            if not has_keywords or len(matched_keywords) < min_keyword_matches:
                failure_reasons.append("insufficient_keywords")
            if emotional_intensity < min_emotional_intensity:
                failure_reasons.append("low_emotional_intensity")
            if pain_score < 0.3:
                failure_reasons.append("low_overall_score")

            reason_str = "; ".join(failure_reasons)
            self.stats["filter_reasons"][reason_str] = self.stats["filter_reasons"].get(reason_str, 0) + 1
            filter_result["reasons"].append(f"Failed: {reason_str}")
            filter_result["filter_summary"] = {"reason": "failed", "details": failure_reasons}

        return passed, filter_result

    def filter_posts_batch(self, posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量过滤帖子"""
        logger.info(f"Filtering {len(posts)} posts through pain signal detector")

        filtered_posts = []
        for i, post in enumerate(posts):
            if i % 100 == 0:
                logger.info(f"Processed {i}/{len(posts)} posts")

            passed, result = self.filter_post(post)

            if passed:
                # 为帖子添加过滤结果
                filtered_post = post.copy()
                filtered_post.update({
                    "pain_score": result["pain_score"],
                    "pain_keywords": result["matched_keywords"],
                    "pain_patterns": result["matched_patterns"],
                    "emotional_intensity": result["emotional_intensity"],
                    "filter_reason": "pain_signal_passed",
                    "aspiration_keywords": result.get("matched_aspirations", []),
                    "aspiration_score": result.get("aspiration_score", 0.0),
                    "pass_type": result.get("pass_type", "pain"),
                    "engagement_score": result.get("engagement_score", 0.0),
                    "trust_level": result.get("trust_level", 0.5)
                })
                filtered_posts.append(filtered_post)

        logger.info(f"Filter complete: {len(filtered_posts)}/{len(posts)} posts passed")
        return filtered_posts

    def get_statistics(self) -> Dict[str, Any]:
        """获取过滤统计信息"""
        stats = self.stats.copy()
        if stats["total_processed"] > 0:
            stats["pass_rate"] = stats["passed_filter"] / stats["total_processed"]
        else:
            stats["pass_rate"] = 0.0
        return stats

    def reset_statistics(self):
        """重置统计信息"""
        self.stats = {
            "total_processed": 0,
            "passed_filter": 0,
            "filtered_out": 0,
            "filter_reasons": {}
        }

def main():
    """主函数 - 过滤原始帖子"""
    import argparse
    from utils.db import db

    parser = argparse.ArgumentParser(description="Filter Reddit posts for pain signals")
    parser.add_argument("--limit", type=int, default=1000, help="Limit number of posts to process")
    parser.add_argument("--min-score", type=float, default=0.0, help="Minimum pain score threshold")
    args = parser.parse_args()

    try:
        logger.info("Starting pain signal filtering...")

        # 初始化过滤器
        filter = PainSignalFilter()

        # 获取未过滤的帖子
        logger.info(f"Fetching up to {args.limit} unprocessed posts...")
        unfiltered_posts = db.get_unprocessed_posts(limit=args.limit)

        if not unfiltered_posts:
            logger.info("No unprocessed posts found")
            return

        logger.info(f"Found {len(unfiltered_posts)} posts to filter")

        # 批量过滤
        filtered_posts = filter.filter_posts_batch(unfiltered_posts)

        # 应用最小分数阈值
        if args.min_score > 0:
            filtered_posts = [p for p in filtered_posts if p.get("pain_score", 0) >= args.min_score]
            logger.info(f"After applying min_score threshold: {len(filtered_posts)} posts")

        # 保存过滤结果
        saved_count = 0
        for post in filtered_posts:
            if db.insert_filtered_post(post):
                saved_count += 1

        logger.info(f"Saved {saved_count}/{len(filtered_posts)} filtered posts to database")

        # 输出统计信息
        stats = filter.get_statistics()
        logger.info(f"""
=== Filter Summary ===
Total processed: {stats['total_processed']}
Passed filter: {stats['passed_filter']}
Filtered out: {stats['filtered_out']}
Pass rate: {stats['pass_rate']:.2%}
Filter reasons: {stats['filter_reasons']}
""")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()