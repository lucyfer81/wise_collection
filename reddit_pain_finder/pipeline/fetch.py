"""
Fetch module for Reddit Pain Point Finder
基于原有reddit_collection.py优化的Reddit数据抓取模块
"""
import os
import json
import sys
import time
import logging
import praw
import yaml
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 导入工具模块
try:
    from utils.db import db
except ImportError:
    logger.warning("Could not import db utility, will use local file storage")

class RedditSourceFetcher:
    """Reddit痛点数据抓取器"""

    def __init__(self, config_path: str = "config/subreddits.yaml"):
        """初始化抓取器"""
        self.config = self._load_config(config_path)
        self.reddit_client = self._init_reddit_client()
        self.processed_posts = set()

        # 初始化filter器（用于在保存前进行完整过滤）
        try:
            from pipeline.filter_signal import PainSignalFilter
            self.signal_filter = PainSignalFilter()
            self.filter_enabled = True
            logger.info("✅ PainSignalFilter initialized - will filter posts before saving")
        except ImportError as e:
            logger.warning(f"Could not import PainSignalFilter: {e}")
            self.signal_filter = None
            self.filter_enabled = False

        self.stats = {
            "total_fetched": 0,
            "total_saved": 0,
            "filtered_out": 0,
            "errors": 0,
            "start_time": None
        }

    def _get_trust_level_for_category(self, category: str) -> float:
        """Get trust level for a category from config"""
        try:
            # Get the category config
            category_config = self.config.get(category, {})
            if isinstance(category_config, dict):
                trust_level = category_config.get("trust_level")
                if trust_level is not None:
                    return float(trust_level)

            # Default fallback levels
            default_levels = {
                'core': 0.9,
                'secondary': 0.7,
                'verticals': 0.6,
                'experimental': 0.4
            }
            return default_levels.get(category, 0.5)

        except Exception as e:
            logger.warning(f"Failed to get trust_level for {category}: {e}, using default 0.5")
            return 0.5

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise

    def _init_reddit_client(self) -> praw.Reddit:
        """初始化Reddit客户端"""
        try:
            # 从环境变量获取API凭证
            client_id = os.getenv('REDDIT_CLIENT_ID')
            client_secret = os.getenv('REDDIT_CLIENT_SECRET')

            if not client_id or not client_secret:
                raise ValueError("Reddit API credentials not found in environment variables")

            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent="python:PainPointFinder:v1.0",
                read_only=True
            )

            # 测试认证
            test_subreddit = reddit.subreddit('test')
            test_subreddit.display_name
            logger.info("Reddit authentication successful")

            return reddit

        except Exception as e:
            logger.error(f"Failed to initialize Reddit client: {e}")
            raise

    def _load_processed_posts(self):
        """加载已处理的帖子ID（支持新旧ID格式）"""
        try:
            # 尝试从数据库加载
            if 'db' in globals():
                # 从数据库获取已处理的帖子ID
                with db.get_connection("raw") as conn:
                    cursor = conn.execute("SELECT id, source FROM posts")
                    self.processed_posts = {row[0] for row in cursor.fetchall()}

                    # 统计各种数据源
                    source_counts = {}
                    cursor = conn.execute("SELECT source, COUNT(*) as count FROM posts GROUP BY source")
                    for row in cursor.fetchall():
                        source_counts[row[0]] = row[1]
                    logger.info(f"Loaded posts by source: {source_counts}")
            else:
                # 从文件加载（备用方案）
                processed_file = "data/processed_posts.json"
                if os.path.exists(processed_file):
                    with open(processed_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.processed_posts = set(data.get("processed_ids", []))

            logger.info(f"Loaded {len(self.processed_posts)} previously processed post IDs")

        except Exception as e:
            logger.error(f"Failed to load processed posts: {e}")
            self.processed_posts = set()

    def _save_processed_posts(self):
        """保存已处理的帖子ID"""
        try:
            if 'db' in globals():
                # 数据库模式不需要额外保存，因为每条记录都单独存储
                pass
            else:
                # 保存到文件（备用方案）
                processed_file = "data/processed_posts.json"
                os.makedirs(os.path.dirname(processed_file), exist_ok=True)
                with open(processed_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "processed_ids": list(self.processed_posts),
                        "last_updated": datetime.now().isoformat()
                    }, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save processed posts: {e}")

    def _build_search_query(self, subreddit_config: Dict[str, Any]) -> str:
        """构建搜索查询"""
        search_focus = subreddit_config.get("search_focus", [])
        pain_keywords = self.config.get("pain_keywords", {})

        query_parts = []
        for category in search_focus:
            if category in pain_keywords:
                # 使用引号确保精确匹配
                category_keywords = pain_keywords[category][:5]  # 限制关键词数量
                quoted_keywords = [f'"{kw}"' for kw in category_keywords]
                query_parts.append(f"({' OR '.join(quoted_keywords)})")

        return " OR ".join(query_parts) if query_parts else ""

    def _calculate_pain_score(self, submission, subreddit_config: Dict[str, Any]) -> float:
        """计算帖子痛点分数"""
        score = 0.0

        # 1. 质量基础分
        thresholds = subreddit_config.get("thresholds", {})
        min_upvotes = thresholds.get("min_upvotes", 5)
        min_comments = thresholds.get("min_comments", 3)

        if submission.score >= min_upvotes:
            score += 0.3
        if submission.num_comments >= min_comments:
            score += 0.2

        # 2. 痛点关键词匹配
        title = (submission.title or "").lower()
        body = (submission.selftext or "").lower()
        full_text = f"{title} {body}"

        pain_keywords = self.config.get("pain_keywords", {})
        keyword_matches = 0

        for category_keywords in pain_keywords.values():
            for keyword in category_keywords:
                if keyword.lower() in full_text:
                    keyword_matches += 1
                    score += 0.1

        # 3. 长度分析（更长的帖子可能包含更多痛点细节）
        if len(full_text) > 200:
            score += 0.1
        if len(full_text) > 500:
            score += 0.1

        # 4. 情绪信号检测（简单规则）
        emotion_indicators = ["frustrated", "annoying", "struggling", "can't", "doesn't work", "broken"]
        emotion_count = sum(1 for indicator in emotion_indicators if indicator in full_text)
        score += emotion_count * 0.05

        return min(score, 1.0)  # 限制在0-1范围内

    def _is_pain_post(self, submission, subreddit_config: Dict[str, Any]) -> bool:
        """判断是否为痛点帖子"""
        # 1. 基础质量检查
        if submission.score < subreddit_config.get("min_upvotes", 5):
            return False
        if submission.num_comments < subreddit_config.get("min_comments", 3):
            return False

        # 2. 痛点关键词检查
        title = (submission.title or "").lower()
        body = (submission.selftext or "").lower()
        full_text = f"{title} {body}"

        pain_keywords = self.config.get("pain_keywords", {})
        keyword_matches = 0

        for category_keywords in pain_keywords.values():
            for keyword in category_keywords:
                if keyword.lower() in full_text:
                    keyword_matches += 1
                    if keyword_matches >= 1:  # 至少匹配一个关键词
                        return True

        # 3. 排除模式检查
        exclude_patterns = self.config.get("exclude_patterns", {})
        for pattern_category, patterns in exclude_patterns.items():
            for pattern in patterns:
                if pattern.lower() in full_text:
                    logger.debug(f"Excluded post due to {pattern_category}: {pattern}")
                    return False

        return False

    def _extract_post_data(self, submission, subreddit_config: Dict[str, Any]) -> Dict[str, Any]:
        """提取帖子数据（支持多数据源schema）"""
        try:
            # 获取评论
            comments = []
            try:
                submission.comment_sort = "top"
                submission.comments.replace_more(limit=0)
                for comment in submission.comments.list()[:20]:  # 获取前20条评论
                    if hasattr(comment, 'author') and comment.author:
                        comments.append({
                            "id": comment.id,  # 添加评论ID
                            "author": comment.author.name,
                            "body": comment.body,
                            "score": comment.score,
                            "created_utc": getattr(comment, 'created_utc', None),  # 添加时间戳
                            "created_at": datetime.fromtimestamp(getattr(comment, 'created_utc', 0)).isoformat() + "Z" if hasattr(comment, 'created_utc') else None
                        })
            except Exception as e:
                logger.warning(f"Failed to fetch comments for {submission.id}: {e}")

            # 计算痛点分数
            pain_score = self._calculate_pain_score(submission, subreddit_config)

            # Reddit特有数据存储在platform_data中
            platform_data = {
                "subreddit": subreddit_config["name"],
                "upvote_ratio": getattr(submission, 'upvote_ratio', 0.0),
                "is_self": getattr(submission, 'is_self', False),
                "reddit_url": f"https://reddit.com{submission.permalink}",
                "flair": getattr(submission, 'link_flair_text', None)
            }

            # 生成统一ID和标准化时间
            reddit_source_id = submission.id
            unified_id = f"reddit_{reddit_source_id}"
            created_at = datetime.fromtimestamp(submission.created_utc).isoformat() + "Z"

            return {
                "id": unified_id,                           # 新的统一ID
                "source": "reddit",                         # 数据源标识
                "source_id": reddit_source_id,              # Reddit原始ID
                "title": submission.title,
                "body": submission.selftext,
                "subreddit": subreddit_config["name"],     # 保持向后兼容
                "category": subreddit_config["category"],
                "url": submission.url,
                "platform_data": platform_data,             # Reddit特有数据
                "score": submission.score,
                "num_comments": submission.num_comments,
                "upvote_ratio": getattr(submission, 'upvote_ratio', 0.0),  # 向后兼容
                "is_self": getattr(submission, 'is_self', False),          # 向后兼容
                "created_utc": submission.created_utc,        # 向后兼容
                "created_at": created_at,                    # 新的标准化时间
                "author": submission.author.name if submission.author else "[deleted]",
                "comments": comments,
                "pain_score": pain_score,
                "trust_level": self._get_trust_level_for_category(subreddit_config["category"]),
                "collected_at": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to extract data for submission {submission.id}: {e}")
            return None

    def _process_submission(self, submission, subreddit_config: Dict[str, Any]) -> bool:
        """处理单个帖子"""
        try:
            # 检查是否已处理（使用统一ID）
            unified_id = f"reddit_{submission.id}"
            if unified_id in self.processed_posts:
                return False

            # 提取帖子数据
            post_data = self._extract_post_data(submission, subreddit_config)
            if not post_data:
                self.stats["errors"] += 1
                return False

            # 使用PainSignalFilter进行完整过滤（在保存前）
            if self.filter_enabled and self.signal_filter:
                passed, filter_result = self.signal_filter.filter_post(post_data)

                if not passed:
                    self.stats["filtered_out"] += 1
                    logger.debug(f"Post filtered out: {submission.title[:60]}... - Reason: {filter_result.get('filter_summary', {}).get('reason', 'unknown')}")
                    return False

                # 将filter结果添加到post_data
                post_data.update({
                    "pain_score": filter_result.get("pain_score", post_data.get("pain_score", 0.0)),
                    "pain_keywords": filter_result.get("matched_keywords", []),
                    "pain_patterns": filter_result.get("matched_patterns", []),
                    "emotional_intensity": filter_result.get("emotional_intensity", 0.0),
                    "filter_reason": "pain_signal_passed",
                    "aspiration_keywords": filter_result.get("matched_aspirations", []),
                    "aspiration_score": filter_result.get("aspiration_score", 0.0),
                    "pass_type": filter_result.get("pass_type", "pain"),
                    "engagement_score": filter_result.get("engagement_score", 0.0)
                })
            else:
                # 备用：使用简单过滤
                if not self._is_pain_post(submission, subreddit_config):
                    self.stats["filtered_out"] += 1
                    return False

            # 保存到数据库
            if 'db' in globals():
                success = db.insert_raw_post(post_data)
            else:
                # 备用文件存储方案
                success = self._save_post_to_file(post_data)

            if success:
                self.processed_posts.add(unified_id)  # 使用统一ID
                self.stats["total_saved"] += 1
                logger.info(f"Saved post: {submission.title[:60]}... (Score: {submission.score}, Pain: {post_data['pain_score']:.2f})")

                # 保存评论到独立的 comments 表（在fetch阶段就过滤）
                comments = post_data.get("comments", [])
                if comments and 'db' in globals():
                    try:
                        # 对comments进行过滤
                        filtered_comments = self._filter_comments(comments, post_data)
                        if filtered_comments:
                            comment_count = db.insert_comments(unified_id, filtered_comments, "reddit")
                            if comment_count > 0:
                                logger.info(f"Saved {comment_count}/{len(comments)} comments for post {unified_id}")
                        else:
                            logger.debug(f"No comments passed filter for post {unified_id}")
                    except Exception as e:
                        logger.error(f"Failed to save comments for {unified_id}: {e}")

                return True
            else:
                self.stats["errors"] += 1
                return False

        except Exception as e:
            logger.error(f"Failed to process submission: {e}")
            self.stats["errors"] += 1
            return False

    def _filter_comments(self, comments: List[Dict[str, Any]], post_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """过滤评论，只保留符合质量标准的评论

        Args:
            comments: 原始评论列表
            post_data: 父帖子数据

        Returns:
            过滤后的评论列表
        """
        if not self.filter_enabled or not self.signal_filter:
            # 如果没有启用filter，返回所有评论
            return comments

        filtered_comments = []
        for comment in comments:
            try:
                # 使用PainSignalFilter的filter_comment方法
                passed, filter_result = self.signal_filter.filter_comment(comment)

                if passed:
                    # 添加filter结果到comment数据
                    comment["pain_score"] = filter_result.get("pain_score", 0.0)
                    comment["pain_keywords"] = filter_result.get("matched_keywords", [])
                    comment["pain_patterns"] = filter_result.get("matched_patterns", [])
                    comment["emotional_intensity"] = filter_result.get("emotional_intensity", 0.0)
                    comment["filter_reason"] = "pain_signal_passed"
                    comment["engagement_score"] = filter_result.get("engagement_score", 0.0)
                    filtered_comments.append(comment)
                # else: comment被过滤掉，不保存

            except Exception as e:
                logger.debug(f"Error filtering comment {comment.get('id')}: {e}")
                # 出错时保守起见，不保存该comment
                continue

        return filtered_comments

    def _save_post_to_file(self, post_data: Dict[str, Any]) -> bool:
        """保存帖子到文件（备用方案）"""
        try:
            output_dir = "data/raw_posts"
            os.makedirs(output_dir, exist_ok=True)
            file_path = os.path.join(output_dir, f"{post_data['id']}.json")

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(post_data, f, indent=2, ensure_ascii=False)

            return True
        except Exception as e:
            logger.error(f"Failed to save post to file: {e}")
            return False

    def fetch_subreddit(self, subreddit_config: Dict[str, Any]) -> int:
        """抓取单个子版块"""
        subreddit_name = subreddit_config["name"]
        category = subreddit_config["category"]
        methods = subreddit_config.get("methods", ["hot"])

        logger.info(f"Fetching from r/{subreddit_name} (Category: {category})")

        try:
            subreddit = self.reddit_client.subreddit(subreddit_name)
            total_found = 0

            # 构建搜索查询
            search_query = self._build_search_query(subreddit_config)
            if search_query:
                logger.debug(f"Search query for r/{subreddit_name}: {search_query}")

            # 获取帖子限制
            max_results = self.config.get("search_strategy", {}).get("max_results_per_method", 100)

            for method in methods:
                logger.debug(f"Using method: {method}")

                try:
                    submissions = []

                    if method == "hot":
                        submissions = subreddit.hot(limit=max_results)
                    elif method == "new":
                        submissions = subreddit.new(limit=max_results)
                    elif method == "rising":
                        submissions = subreddit.rising(limit=max_results)
                    elif method == "controversial":
                        submissions = subreddit.controversial('week', limit=max_results)
                    elif method.startswith("top_"):
                        time_filter = method.split("_", 1)[1] if "_" in method else "week"
                        submissions = subreddit.top(time_filter=time_filter, limit=max_results)
                    elif method == "search" and search_query:
                        submissions = subreddit.search(search_query, sort='new', limit=max_results)
                    else:
                        logger.warning(f"Unknown method: {method}")
                        continue

                    # 处理帖子
                    method_count = 0
                    for submission in submissions:
                        if self._process_submission(submission, subreddit_config):
                            method_count += 1

                    total_found += method_count
                    logger.info(f"Method {method}: found {method_count} posts in r/{subreddit_name}")

                    # 添加延迟避免API限制
                    time.sleep(1)

                except Exception as e:
                    logger.error(f"Error with method {method} in r/{subreddit_name}: {e}")
                    continue

            return total_found

        except Exception as e:
            logger.error(f"Failed to fetch subreddit r/{subreddit_name}: {e}")
            return 0

    def fetch_all(self, limit_sources: Optional[int] = None) -> Dict[str, Any]:
        """抓取所有配置的子版块"""
        self.stats["start_time"] = datetime.now()

        logger.info("Starting Wise Collection posts fetching...")

        # 加载已处理的帖子
        self._load_processed_posts()

        # 从配置中构建 subreddit 列表
        subreddits = []

        # 处理所有分组中的 subreddits
        for group_name, group_data in self.config.items():
            if group_name in ["ignore", "search_strategy"]:
                continue  # 跳过忽略列表和搜索策略配置

            if isinstance(group_data, dict):
                for subreddit_name, subreddit_config in group_data.items():
                    if isinstance(subreddit_config, dict):
                        # 构建期望的配置格式
                        subreddit_data = {
                            "name": subreddit_name,
                            "category": group_name,
                            "min_upvotes": subreddit_config.get("min_upvotes", 0),
                            "min_comments": subreddit_config.get("min_comments", 0),
                            "methods": ["hot", "new", "top_week"]  # 默认使用这些方法
                        }
                        subreddits.append(subreddit_data)

        # 如果指定了限制，则截取列表
        if limit_sources:
            subreddits = subreddits[:limit_sources]

        logger.info(f"Will fetch from {len(subreddits)} subreddits")

        total_found = 0
        for i, subreddit_config in enumerate(subreddits, 1):
            logger.info(f"Processing subreddit {i}/{len(subreddits)}")
            found = self.fetch_subreddit(subreddit_config)
            total_found += found

        # 保存已处理的帖子
        self._save_processed_posts()

        # 计算运行时间
        runtime = datetime.now() - self.stats["start_time"]

        # 更新统计
        self.stats["total_fetched"] = total_found
        self.stats["runtime_seconds"] = runtime.total_seconds()

        # 输出总结
        logger.info(f"""
=== Fetch Summary ===
Total subreddits processed: {len(subreddits)}
Total posts found: {total_found}
Total posts saved: {self.stats["total_saved"]}
Posts filtered out: {self.stats["filtered_out"]}
Errors encountered: {self.stats["errors"]}
Runtime: {runtime}
Posts per minute: {self.stats["total_saved"] / max(runtime.total_seconds() / 60, 1):.1f}
""")

        return self.stats.copy()

class MultiSourceFetcher:
    """多数据源抓取器（当前仅支持Reddit）"""

    def __init__(self, sources: List[str] = None, config_path: str = "config/subreddits.yaml"):
        """初始化抓取器

        Args:
            sources: 要抓取的数据源列表（当前仅支持 'reddit'）
            config_path: Reddit配置文件路径
        """
        self.sources = sources or ['reddit']
        self.fetchers = {}

        # 初始化各个抓取器
        if 'reddit' in self.sources:
            self.fetchers['reddit'] = RedditSourceFetcher(config_path)

    def fetch_all(self, limit_sources: Optional[int] = None) -> Dict[str, Any]:
        """抓取所有配置的数据源"""
        overall_stats = {
            "sources_processed": [],
            "total_saved": 0,
            "total_filtered": 0,
            "total_errors": 0,
            "source_stats": {},
            "runtime_seconds": 0
        }

        start_time = datetime.now()

        for source_name in self.sources:
            if source_name in self.fetchers:
                logger.info(f"Fetching from {source_name}...")
                try:
                    stats = self.fetchers[source_name].fetch_all()
                    overall_stats["sources_processed"].append(source_name)
                    overall_stats["total_saved"] += stats.get("total_saved", 0)
                    overall_stats["total_filtered"] += stats.get("filtered_out", 0)
                    overall_stats["total_errors"] += stats.get("errors", 0)
                    overall_stats["source_stats"][source_name] = stats

                except Exception as e:
                    logger.error(f"Failed to fetch from {source_name}: {e}")
                    overall_stats["total_errors"] += 1
                    overall_stats["source_stats"][source_name] = {"error": str(e)}

        # 计算总运行时间
        runtime = datetime.now() - start_time
        overall_stats["runtime_seconds"] = runtime.total_seconds()

        # 输出总结
        logger.info(f"""
=== Multi-Source Fetch Summary ===
Sources processed: {overall_stats["sources_processed"]}
Total posts saved: {overall_stats["total_saved"]}
Total posts filtered: {overall_stats["total_filtered"]}
Total errors: {overall_stats["total_errors"]}
Runtime: {runtime}
Posts per minute: {overall_stats["total_saved"] / max(runtime.total_seconds() / 60, 1):.1f}
""")

        # 输出各数据源统计
        for source, stats in overall_stats.get("source_stats", {}).items():
            if "error" not in stats:
                logger.info(f"   - {source}: {stats.get('total_saved', 0)} saved, {stats.get('filtered_out', 0)} filtered")
            else:
                logger.error(f"   - {source}: ERROR - {stats['error']}")

        return overall_stats


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Fetch posts for pain point discovery")
    parser.add_argument("--limit", type=int, help="Limit number of sources to process")
    parser.add_argument("--config", default="config/subreddits.yaml", help="Reddit config file path")
    args = parser.parse_args()

    try:
        # 使用Reddit抓取器
        fetcher = RedditSourceFetcher(config_path=args.config)
        stats = fetcher.fetch_all(limit_sources=args.limit)

        # 输出JSON格式的统计信息（用于脚本集成）
        print(json.dumps(stats, indent=2))

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()