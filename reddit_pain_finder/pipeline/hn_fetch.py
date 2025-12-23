"""
Hacker News 数据抓取器
基于 HN API v0，只抓取 Ask HN、Show HN 和高评论故事
"""
import requests
import json
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class HackerNewsFetcher:
    """Hacker News 数据抓取器"""

    def __init__(self):
        self.base_url = "https://hacker-news.firebaseio.com/v0"
        self.processed_ids = set()
        self.stats = {
            "total_fetched": 0,
            "total_saved": 0,
            "filtered_out": 0,
            "errors": 0,
            "start_time": None
        }

    def _is_pain_story(self, item: Dict[str, Any]) -> bool:
        """判断是否为痛点相关故事"""
        # 只抓三类内容:
        # 1. Ask HN
        # 2. Show HN
        # 3. 普通故事但评论数 > 10

        title = item.get("title", "").lower()

        # Ask HN / Show HN 直接收录
        if "ask hn" in title or "show hn" in title:
            return True

        # 普通故事需要评论数 > 10
        if item.get("descendants", 0) > 10:
            return True

        return False

    def _extract_story_data(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """提取故事数据为统一格式"""
        hn_id = item["id"]
        unified_id = f"hackernews_{hn_id}"

        # 获取评论（简化版，只获取前10条）
        comments = []
        kids = item.get("kids", [])

        for kid_id in kids[:10]:  # 只获取前10条评论
            try:
                comment_url = f"{self.base_url}/item/{kid_id}.json"
                comment_resp = requests.get(comment_url, timeout=10)
                if comment_resp.status_code == 200:
                    comment_data = comment_resp.json()
                    if comment_data and comment_data.get("type") == "comment":
                        comments.append({
                            "author": comment_data.get("by", ""),
                            "body": comment_data.get("text", ""),
                            "score": 0  # HN评论没有score
                        })
            except Exception as e:
                logger.warning(f"Failed to fetch comment {kid_id}: {e}")

        # 确定source_type
        title_lower = item.get("title", "").lower()
        if "ask hn" in title_lower:
            source_type = "HN_ASK"
        elif "show hn" in title_lower:
            source_type = "HN_SHOW"
        else:
            source_type = "HN_STORY"

        # HN特有的platform_data
        platform_data = {
            "hn_id": hn_id,
            "type": item.get("type", "story"),
            "descendants": item.get("descendants", 0),
            "hn_url": f"https://news.ycombinator.com/item?id={hn_id}"
        }

        created_at = datetime.fromtimestamp(item.get("time", 0)).isoformat() + "Z"

        return {
            "id": unified_id,
            "source": "hackernews",
            "source_id": str(hn_id),
            "title": item.get("title", ""),
            "body": item.get("text", ""),
            "subreddit": source_type,  # 复用subreddit字段存储source_type
            "category": "hackernews",
            "url": item.get("url", f"https://news.ycombinator.com/item?id={hn_id}"),
            "platform_data": platform_data,
            "score": item.get("score", 0),
            "num_comments": item.get("descendants", 0),
            "upvote_ratio": 1.0,  # HN没有upvote_ratio，设为1.0
            "is_self": 1 if item.get("text") else 0,
            "created_utc": item.get("time", 0),
            "created_at": created_at,
            "author": item.get("by", ""),
            "comments": comments,
            "pain_score": 0.5,  # 默认pain_score，后续pipeline会重新计算
            "trust_level": 0.8,  # HN has high quality technical discussions
            "collected_at": datetime.now().isoformat()
        }

    def fetch_from_endpoint(self, endpoint: str, limit: int = 50) -> int:
        """从特定端点抓取数据"""
        try:
            # 获取故事ID列表
            url = f"{self.base_url}/{endpoint}.json"
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                logger.error(f"Failed to fetch {endpoint}: {resp.status_code}")
                return 0

            story_ids = resp.json()[:limit] if limit else resp.json()
            saved_count = 0

            for story_id in story_ids:
                try:
                    # 获取故事详情
                    item_url = f"{self.base_url}/item/{story_id}.json"
                    item_resp = requests.get(item_url, timeout=10)
                    if item_resp.status_code != 200:
                        continue

                    item = item_resp.json()
                    if not item or item.get("type") != "story":
                        continue

                    # 检查是否已处理
                    unified_id = f"hackernews_{story_id}"
                    if unified_id in self.processed_ids:
                        continue

                    # 检查是否为痛点内容
                    if not self._is_pain_story(item):
                        self.stats["filtered_out"] += 1
                        continue

                    # 提取并保存数据
                    story_data = self._extract_story_data(item)

                    # 调用现有的db.insert_raw_post
                    try:
                        from utils.db import db
                        if db.insert_raw_post(story_data):
                            self.processed_ids.add(unified_id)
                            self.stats["total_saved"] += 1
                            saved_count += 1
                            logger.info(f"Saved HN story: {item.get('title', '')[:60]}... (ID: {story_id})")
                        else:
                            self.stats["errors"] += 1
                    except Exception as db_e:
                        logger.error(f"Failed to save HN story {story_id}: {db_e}")
                        self.stats["errors"] += 1

                    # 避免请求过快
                    time.sleep(0.1)

                except Exception as e:
                    logger.error(f"Error processing story {story_id}: {e}")
                    self.stats["errors"] += 1

            return saved_count

        except Exception as e:
            logger.error(f"Error fetching from {endpoint}: {e}")
            return 0

    def fetch_all(self) -> Dict[str, Any]:
        """抓取所有HN数据"""
        from datetime import datetime
        self.stats["start_time"] = datetime.now()

        logger.info("Starting Hacker News data fetching...")

        # 加载已处理的帖子ID
        try:
            from utils.db import db
            with db.get_connection("raw") as conn:
                cursor = conn.execute("SELECT id FROM posts WHERE source = 'hackernews'")
                self.processed_ids = {row['id'] for row in cursor.fetchall()}
            logger.info(f"Loaded {len(self.processed_ids)} previously processed HN posts")
        except Exception as e:
            logger.error(f"Failed to load processed posts: {e}")
            self.processed_ids = set()

        # 抓取三类内容
        endpoints = [
            ("askstories", 25),    # Ask HN - 抓取25条
            ("showstories", 25),   # Show HN - 抓取25条
            ("topstories", 50)     # Top Stories - 抓取50条，过滤评论数>10的
        ]

        total_saved = 0
        for endpoint, limit in endpoints:
            logger.info(f"Fetching from {endpoint}...")
            saved = self.fetch_from_endpoint(endpoint, limit)
            total_saved += saved
            logger.info(f"Saved {saved} stories from {endpoint}")

        self.stats["total_fetched"] = total_saved

        # 计算运行时间
        runtime = datetime.now() - self.stats["start_time"]
        self.stats["runtime_seconds"] = runtime.total_seconds()

        logger.info(f"""
=== HN Fetch Summary ===
Total stories saved: {total_saved}
Posts filtered out: {self.stats["filtered_out"]}
Errors encountered: {self.stats["errors"]}
Runtime: {runtime}
Posts per minute: {self.stats["total_saved"] / max(runtime.total_seconds() / 60, 1):.1f}
""")

        return self.stats.copy()