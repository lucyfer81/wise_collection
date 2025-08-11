# reddit_collection_new.py - v6.0 ("Enhanced Search & AI-Focused Collection")
import os
import json
import sys
import praw
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# --- Configuration ---
CONFIG_FILE = 'reddit_config.json'
OUTPUT_DIR = "content/reddit"
PROCESSED_IDS_FILE = 'processed_ids.json'
COMMENTS_TO_FETCH = 20

load_dotenv()

class EnhancedRedditCollector:
    """增强版Reddit收集器"""
    
    def __init__(self):
        self.config = self.load_config()
        self.reddit = self.init_reddit()
        self.ai_keywords = self.config.get('ai_keywords', {})
        self.search_strategies = self.config.get('search_strategies', {})
        self.performance_stats = {}
        
    def load_config(self):
        """加载配置文件"""
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"FATAL: Could not load or parse '{CONFIG_FILE}'. Error: {e}", file=sys.stderr)
            sys.exit(1)
    
    def init_reddit(self):
        """初始化Reddit连接"""
        try:
            reddit = praw.Reddit(
                client_id=os.getenv("REDDIT_CLIENT_ID"),
                client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
                user_agent="python:EnhancedAICollector:v6.0",
                read_only=True
            )
            print(f"Authenticated as: {reddit.user.me()}")
            return reddit
        except Exception as e:
            print(f"FATAL: Could not connect to Reddit. Error: {e}", file=sys.stderr)
            sys.exit(1)
    
    def load_processed_ids(self):
        """加载已处理的帖子ID"""
        if not os.path.exists(PROCESSED_IDS_FILE):
            return set()
        try:
            with open(PROCESSED_IDS_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except (json.JSONDecodeError, IOError):
            return set()
    
    def save_processed_ids(self, ids):
        """保存已处理的帖子ID"""
        with open(PROCESSED_IDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(ids), f, indent=4)
    
    def build_dynamic_search_query(self, keyword_categories):
        """构建动态搜索查询"""
        if not keyword_categories:
            return ""
        
        all_keywords = []
        for category in keyword_categories:
            if category in self.ai_keywords:
                all_keywords.extend(self.ai_keywords[category])
        
        # 限制关键词数量以避免查询过长
        if len(all_keywords) > 20:
            # 优先选择核心关键词
            all_keywords = all_keywords[:20]
        
        # 构建OR查询
        query_parts = [f'"{keyword}"' for keyword in all_keywords]
        return " OR ".join(query_parts)
    
    def pre_filter_content(self, submission):
        """预筛选内容质量"""
        if not self.search_strategies.get('pre_filter_enabled', True):
            return True
        
        title = submission.title.lower()
        
        # 消极信号（直接过滤）
        negative_signals = [
            any(keyword in title for keyword in ["meme", "joke", "shitpost", "circlejerk"]),
            submission.score < 1,
            submission.num_comments == 0,
            len(submission.title) < 10
        ]
        
        if any(negative_signals):
            return False
        
        # 积极信号（至少需要2个）
        positive_signals = [
            submission.score > 10,
            submission.num_comments > 5,
            len(submission.title) > 20,
            submission.is_self,  # 文本帖子通常质量更高
            self.has_ai_relevance(submission.title)
        ]
        
        return sum(positive_signals) >= 2
    
    def has_ai_relevance(self, text):
        """检查文本是否有AI相关性"""
        text_lower = text.lower()
        
        # 核心AI关键词
        core_ai_terms = [
            "ai", "artificial intelligence", "machine learning", "deep learning",
            "gpt", "chatgpt", "llm", "openai", "anthropic", "claude",
            "gemini", "llama", "mistral", "neural network"
        ]
        
        return any(term in text_lower for term in core_ai_terms)
    
    def get_submissions_by_method(self, subreddit, method, search_query=None):
        """根据方法获取帖子"""
        try:
            if method == 'hot':
                return subreddit.hot(limit=100)
            elif method == 'new':
                return subreddit.new(limit=100)
            elif method == 'rising':
                return subreddit.rising(limit=50)
            elif method == 'controversial':
                return subreddit.controversial('week', limit=100)
            elif method.startswith('top_'):
                time_range = method.split('_')[1]
                return subreddit.top(time_range, limit=100)
            elif method == 'search' and search_query:
                return subreddit.search(search_query, sort='new', limit=100)
            else:
                return []
        except Exception as e:
            print(f"    Warning: Could not fetch {method} submissions: {e}", file=sys.stderr)
            return []
    
    def process_and_save_submission(self, submission, sub_config, output_dir):
        """处理并保存帖子"""
        thresholds = sub_config['thresholds']
        min_score = thresholds.get('min_score', 20)
        min_comments = thresholds.get('min_comments', 20)
        min_ratio = thresholds.get('min_ratio', 0.0)
        
        score = submission.score if submission.score > 0 else 1
        if (submission.score < min_score or 
            submission.num_comments < min_comments or 
            (submission.num_comments / score) < min_ratio):
            return False
        
        print(f"  🔥 High-Quality Post Found: '{submission.title[:60]}...' "
              f"(Score: {submission.score}, Comments: {submission.num_comments})")
        
        # 获取评论
        try:
            submission.comment_sort = "top"
            submission.comments.replace_more(limit=0)
            comments_list = [
                {"author": c.author.name, "body": c.body, "score": c.score}
                for i, c in enumerate(submission.comments.list())
                if i < COMMENTS_TO_FETCH and hasattr(c, 'author') and c.author
            ]
        except Exception as e:
            print(f"    Warning: Could not fetch comments for {submission.id}: {e}", file=sys.stderr)
            comments_list = []
        
        # 保存数据
        post_data = {
            "id": submission.id,
            "title": submission.title,
            "subreddit": sub_config['name'],
            "url": submission.url,
            "score": submission.score,
            "num_comments": submission.num_comments,
            "selftext": submission.selftext,
            "comments": comments_list,
            "upvote_ratio": submission.upvote_ratio,
            "is_self": submission.is_self,
            "created_utc": submission.created_utc,
            "category": sub_config.get('category', 'Unknown'),
            "collected_at": datetime.now().isoformat()
        }
        
        file_path = os.path.join(output_dir, f"{submission.id}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(post_data, f, indent=4, ensure_ascii=False)
        
        return True
    
    def collect_from_subreddit(self, sub_config, processed_ids):
        """从单个subreddit收集帖子"""
        subreddit_name = sub_config['name']
        category = sub_config.get('category', 'N/A')
        methods = sub_config.get('methods', ['hot'])
        keyword_categories = sub_config.get('keyword_categories', [])
        
        print(f"\n📡 Scanning r/{subreddit_name} (Category: {category})...")
        
        subreddit = self.reddit.subreddit(subreddit_name)
        found_count = 0
        
        # 构建搜索查询
        search_query = None
        if 'search' in methods and keyword_categories:
            search_query = self.build_dynamic_search_query(keyword_categories)
            if search_query:
                print(f"  🔍 Search query: {search_query[:100]}...")
        
        # 执行各种搜索方法
        for method in methods:
            print(f"  -> Method: '{method}'")
            
            submissions = self.get_submissions_by_method(subreddit, method, search_query)
            processed_count = 0
            
            for submission in submissions:
                # 检查是否已处理
                if submission.id in processed_ids:
                    continue
                
                # 预筛选
                if not self.pre_filter_content(submission):
                    continue
                
                # 处理并保存
                if self.process_and_save_submission(submission, sub_config, OUTPUT_DIR):
                    processed_ids.add(submission.id)
                    found_count += 1
                    processed_count += 1
                
                # 限制每次方法的处理数量
                if processed_count >= 20:
                    break
            
            print(f"     Processed {processed_count} posts from '{method}'")
        
        return found_count
    
    def run_collection(self):
        """运行收集过程"""
        print("--- Enhanced Reddit AI Collector v6.0 ---")
        print(f"📅 Collection started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 创建输出目录
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # 加载已处理的ID
        processed_ids = self.load_processed_ids()
        print(f"📋 Loaded {len(processed_ids)} previously processed post IDs")
        
        # 统计变量
        total_found = 0
        subreddits_processed = 0
        
        # 处理每个subreddit
        for sub_config in self.config['subreddits']:
            try:
                found_count = self.collect_from_subreddit(sub_config, processed_ids)
                total_found += found_count
                subreddits_processed += 1
                
                # 添加小延迟避免API限制
                if subreddits_processed < len(self.config['subreddits']):
                    time.sleep(1)
                    
            except Exception as e:
                print(f"    ERROR processing {sub_config['name']}: {e}", file=sys.stderr)
                continue
        
        # 保存处理状态
        self.save_processed_ids(processed_ids)
        
        # 输出统计信息
        print(f"\n--- Collection Complete ---")
        print(f"📊 Statistics:")
        print(f"  🎯 Subreddits processed: {subreddits_processed}/{len(self.config['subreddits'])}")
        print(f"  ✨ New posts found: {total_found}")
        print(f"  📈 Total unique posts tracked: {len(processed_ids)}")
        print(f"⏰ Collection completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 如果没有找到新帖子，提供建议
        if total_found == 0:
            print("\n💡 No new posts found. Consider:")
            print("  - Adjusting threshold values in config")
            print("  - Adding more AI keywords")
            print("  - Expanding subreddit list")
            print("  - Running at different times")

def main():
    """主函数"""
    collector = EnhancedRedditCollector()
    collector.run_collection()

if __name__ == "__main__":
    main()
