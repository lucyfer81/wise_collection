# Code Export - 2025-08-11

This document contains the source code for the Python scripts and the Reddit configuration file as of 2025-08-11.

## `analyze_topics.py`

```python
# analyze_topics.py - v1.0 ("Topic Analysis and Summarization Engine")
import os
import json
import re
import shutil
from pathlib import Path
from collections import defaultdict

import numpy as np
import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import DBSCAN
from openai import OpenAI
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
API_KEY = os.getenv("SILICONFLOW_API_KEY")
if not API_KEY:
    raise ValueError("Siliconflow API key not found in .env file.")

client = OpenAI(api_key=API_KEY, base_url="https://api.siliconflow.cn/v1")

# --- Model Configuration ---
# For summarization, a powerful reasoning model is recommended for higher quality analysis.
SUMMARIZATION_MODEL = "Qwen/Qwen3-32B" 
# For translation, a smaller, efficient model is sufficient and cost-effective.
TRANSLATION_MODEL = "Qwen/Qwen2.5-7B-Instruct"

INPUT_DIR = "content/reddit_english_curated"
OUTPUT_DIR = "output/topics"
STOPWORDS_FILE = "chinese_stopwords.txt"

# DBSCAN Parameters (might need tuning)
DBSCAN_EPS = 0.75  # Neighborhood distance
DBSCAN_MIN_SAMPLES = 2  # Minimum number of posts to form a cluster

SUMMARIZATION_PROMPT = """
You are an expert AI news analyst. Below is a collection of Reddit post titles and contents, all discussing a similar topic.
Your task is to synthesize all the provided information into a single, concise, and insightful summary in English.
The summary should capture the main points, key discussions, and overall sentiment of the topic.
Do not just list the posts. Create a coherent narrative.

--- START OF CONTENT ---
{english_text_block}
--- END OF CONTENT ---

Your concise summary in English:
"""

TRANSLATION_PROMPT = """
Translate the following English summary into Simplified Chinese.
Preserve the original meaning, tone, and any technical terms accurately.
Do not add any commentary or extra text outside of the translation.

--- ENGLISH SUMMARY ---
{english_summary}
--- CHINESE TRANSLATION ---
"""

# --- Helper Functions ---

def load_stopwords(filepath):
    """Loads stopwords from a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f)
    except FileNotFoundError:
        print(f"Warning: Stopwords file not found at '{filepath}'. Proceeding without stopwords.")
        return set()

def get_text_from_post(post_data):
    """Extracts combined title and selftext from post data."""
    title = post_data.get("title", "")
    selftext = post_data.get("selftext", "")
    return f"{title}\n\n{selftext}".strip()

def call_llm(model, prompt_template, content_dict, max_retries=2):
    """Generic function to call the LLM with retries."""
    prompt = prompt_template.format(**content_dict)
    messages = [{"role": "user", "content": prompt}]
    
    for attempt in range(max_retries):
        try:
            chat_completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                max_tokens=2048
            )
            response = chat_completion.choices[0].message.content.strip()
            if response:
                return response
            print("  -> LLM returned empty response. Retrying...")
        except Exception as e:
            print(f"  -> LLM call failed (Attempt {attempt + 1}/{max_retries}): {e}")
    return None

# --- Main Analysis Logic ---

def main():
    """
    Main function to analyze curated English posts, cluster them into topics,
    summarize and translate each topic, and organize the output.
    """
    print("--- Topic Analysis and Summarization Engine v1.0 ---")

    # 1. Setup Paths and Load Resources
    input_path = Path(INPUT_DIR)
    output_path = Path(OUTPUT_DIR)
    
    if not input_path.exists() or not any(input_path.iterdir()):
        print(f"✅ Input directory '{INPUT_DIR}' is empty. Nothing to analyze.")
        return

    # Clean and recreate output directory
    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True)
    
    # stopwords = load_stopwords(STOPWORDS_FILE) # Not needed for English TF-IDF

    # 2. Load all curated posts
    posts = []
    for json_file in input_path.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['file_path'] = json_file # Keep track of original path
                posts.append(data)
        except Exception as e:
            print(f"Warning: Could not load or parse {json_file.name}: {e}")

    if len(posts) < DBSCAN_MIN_SAMPLES:
        print(f"❌ Not enough posts ({len(posts)}) to form topics. Need at least {DBSCAN_MIN_SAMPLES}.")
        # Copy all to unclassified
        unclassified_dir = output_path / "_unclassified"
        unclassified_dir.mkdir()
        for post in posts:
            shutil.copy(post['file_path'], unclassified_dir)
        return

    print(f"🔎 Loaded {len(posts)} curated posts for analysis.")

    # 3. Vectorize English Text
    print("🧠 Vectorizing English content using TF-IDF...")
    documents = [get_text_from_post(p) for p in posts]
    vectorizer = TfidfVectorizer(max_features=2000, stop_words='english', ngram_range=(1, 2))
    tfidf_matrix = vectorizer.fit_transform(documents)
    feature_names = np.array(vectorizer.get_feature_names_out())

    # 4. Cluster with DBSCAN
    print("🤖 Clustering posts into topics using DBSCAN...")
    dbscan = DBSCAN(eps=DBSCAN_EPS, min_samples=DBSCAN_MIN_SAMPLES, metric='cosine')
    dbscan.fit(tfidf_matrix)
    labels = dbscan.labels_
    
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = list(labels).count(-1)
    print(f"📊 Found {n_clusters} topics and {n_noise} unclassified posts.")

    # 5. Process each cluster
    clusters = defaultdict(list)
    for i, label in enumerate(labels):
        clusters[label].append(posts[i])

    for label, cluster_posts in clusters.items():
        if label == -1:
            continue # Skip noise for now

        print(f"\n--- Processing Topic {label+1}/{n_clusters} ---")
        
        # a. Get top keywords for topic name
        cluster_indices = [i for i, l in enumerate(labels) if l == label]
        cluster_vector = tfidf_matrix[cluster_indices].mean(axis=0)
        top_indices = np.asarray(cluster_vector).flatten().argsort()[-5:][::-1]
        top_keywords = [feature_names[i] for i in top_indices]
        
        # Sanitize keywords for folder name
        topic_name = re.sub(r'[^\w-]', '_', "_".join(top_keywords))
        topic_dir = output_path / f"topic_{label+1}_{topic_name}"
        topic_dir.mkdir()
        print(f"  -> Topic Name: {topic_name}")

        # b. Generate English Summary
        print("  -> Generating English summary...")
        english_text_block = "\n\n---\n\n".join([get_text_from_post(p) for p in cluster_posts])
        english_summary = call_llm(
            SUMMARIZATION_MODEL, 
            SUMMARIZATION_PROMPT, 
            {'english_text_block': english_text_block}
        )
        
        if not english_summary:
            print("  ❌ Failed to generate English summary. Skipping this topic.")
            # Move original files to a failed directory
            failed_dir = output_path / f"_failed_summary_topic_{label+1}"
            failed_dir.mkdir()
            for post in cluster_posts:
                shutil.copy(post['file_path'], failed_dir)
            continue

        # c. Translate Summary to Chinese
        print("  -> Translating summary to Chinese...")
        chinese_summary = call_llm(
            TRANSLATION_MODEL,
            TRANSLATION_PROMPT, 
            {'english_summary': english_summary}
        )

        if not chinese_summary:
            print("  ❌ Failed to translate summary. Saving English summary instead.")
            chinese_summary = f"**TRANSLATION FAILED**\n\n---\n\n{english_summary}"

        # d. Save summary and copy original files
        summary_path = topic_dir / "_SUMMARY_zh.md"
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(f"# 主题摘要: {topic_name}\n\n")
            f.write(chinese_summary)
        
        for post in cluster_posts:
            shutil.copy(post['file_path'], topic_dir)
        
        print(f"  ✅ Saved topic summary and {len(cluster_posts)} posts to '{topic_dir.name}'")

    # 6. Handle unclassified (noise) posts
    if -1 in clusters:
        unclassified_dir = output_path / "_unclassified"
        unclassified_dir.mkdir()
        for post in clusters[-1]:
            shutil.copy(post['file_path'], unclassified_dir)
        print(f"\n✅ Copied {len(clusters[-1])} unclassified posts to '{unclassified_dir.name}'")

    print("\n🎉 Topic analysis complete!")

if __name__ == "__main__":
    main()
```

## `curate.py`

```python
# curate_new.py - v5.0 ("English Curation Engine")
import os
import json
import re
import hashlib
import numpy as np
from pathlib import Path
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# --- Configuration ---
INPUT_DIR = "content/reddit"
# NEW: Output directory for high-quality, curated ENGLISH posts
CURATED_ENGLISH_DIR = "content/reddit_english_curated"
# Archive for rejected or already processed posts
REJECTED_ARCHIVE_DIR = "content/processed_json"
CONTENT_CACHE_FILE = "content_cache.json"

# --- Enhanced Data Quality Classes (Unchanged) ---

class ContentValidator:
    """内容验证器"""
    
    @staticmethod
    def validate_content_quality(post_data):
        """综合内容质量验证"""
        title = post_data.get("title", "")
        selftext = post_data.get("selftext", "")
        
        quality_score = 0
        violations = []
        
        # 1. 标题质量检查
        if len(title) < 10:
            violations.append("标题过短")
        elif len(title) > 300:
            violations.append("标题过长")
        else:
            quality_score += 20
        
        # 2. 内容长度检查
        if selftext:
            if 50 <= len(selftext) <= 5000:
                quality_score += 30
            elif len(selftext) < 50:
                violations.append("正文过短")
            else:
                violations.append("正文过长")
        else:
            violations.append("无正文内容")
        
        # 3. 语言质量检查
        if ContentValidator.is_english_content(title + " " + selftext):
            quality_score += 20
        else:
            violations.append("非英文内容")
        
        # 4. 垃圾内容检测
        spam_score = ContentValidator.detect_spam_content(title, selftext)
        if spam_score < 0.3:
            quality_score += 20
        else:
            violations.append(f"疑似垃圾内容 (分数: {spam_score:.2f})")
        
        # 5. AI相关性检查
        ai_relevance = ContentValidator.check_ai_relevance(title, selftext)
        if ai_relevance > 0.6:
            quality_score += 30
        else:
            violations.append(f"AI相关性低 (分数: {ai_relevance:.2f})")
        
        return {
            "quality_score": quality_score,
            "violations": violations,
            "is_valid": quality_score >= 60
        }
    
    @staticmethod
    def is_english_content(text):
        if not text: return True
        english_chars = sum(1 for char in text if char.isalpha() and ord(char) < 128)
        total_chars = sum(1 for char in text if char.isalpha())
        if total_chars == 0: return True
        return english_chars / total_chars > 0.8
    
    @staticmethod
    def detect_spam_content(title, text):
        combined_text = (title + " " + text).lower()
        spam_indicators = 0
        spam_keywords = ["click here", "buy now", "free trial", "limited time", "make money", "get rich", "lose weight", "dating site", "subscribe", "newsletter", "discount", "promotion"]
        for keyword in spam_keywords:
            if keyword in combined_text: spam_indicators += 1
        
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        urls = re.findall(url_pattern, combined_text)
        url_density = len(urls) / max(len(combined_text.split()), 1)
        if url_density > 0.1: spam_indicators += 2
        
        repeat_pattern = r'(.)\1{3,}'
        repeats = len(re.findall(repeat_pattern, combined_text))
        if repeats > 5: spam_indicators += 1
        
        return min(spam_indicators / 10, 1.0)
    
    @staticmethod
    def check_ai_relevance(title, text):
        combined_text = (title + " " + text).lower()
        ai_keywords = ["ai", "artificial intelligence", "machine learning", "deep learning", "neural network", "gpt", "chatgpt", "llm", "large language model", "openai", "anthropic", "claude", "gemini", "llama", "mistral", "stable diffusion", "midjourney", "sora", "generative ai", "automation", "nlp", "computer vision", "robotics"]
        found_keywords = sum(1 for keyword in ai_keywords if keyword in combined_text)
        return min(found_keywords / 5, 1.0)

class ContentDeduplicator:
    """内容去重器"""
    
    def __init__(self, similarity_threshold=0.8):
        self.similarity_threshold = similarity_threshold
        self.content_cache = {}
        self.content_texts = {}
        self.vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
        self.fitted = False
        self.load_cache()
    
    def load_cache(self):
        if os.path.exists(CONTENT_CACHE_FILE):
            try:
                with open(CONTENT_CACHE_FILE, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    self.content_cache = cache_data.get('hashes', {})
                    self.content_texts = cache_data.get('texts', {})
            except Exception as e:
                print(f"  Warning: Failed to load content cache: {e}")
    
    def save_cache(self):
        try:
            cache_data = {'hashes': self.content_cache, 'texts': self.content_texts}
            with open(CONTENT_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"  Warning: Failed to save content cache: {e}")
    
    def generate_content_fingerprint(self, title, text):
        cleaned_text = self.clean_text(title + " " + text)
        content_hash = hashlib.md5(cleaned_text.encode()).hexdigest()
        return content_hash, cleaned_text
    
    def clean_text(self, text):
        text = re.sub(r'http[s]?://\S+', '', text)
        text = re.sub(r'[^\w\s]', '', text)
        text = text.lower()
        text = ' '.join(text.split())
        return text
    
    def is_duplicate(self, title, text, post_id=None):
        content_hash, cleaned_text = self.generate_content_fingerprint(title, text)
        if content_hash in self.content_cache:
            return True, self.content_cache[content_hash]
        
        if not self.fitted and not self.content_texts:
            self.content_cache[content_hash] = post_id
            self.content_texts[content_hash] = cleaned_text
            self.fitted = True
            self.save_cache()
            return False, None
        
        similarity = self.calculate_semantic_similarity(cleaned_text)
        if similarity >= self.similarity_threshold:
            similar_id = self.find_most_similar_content(cleaned_text)
            return True, similar_id
        
        self.content_cache[content_hash] = post_id
        self.content_texts[content_hash] = cleaned_text
        self.save_cache()
        return False, None
    
    def calculate_semantic_similarity(self, new_text):
        if not self.content_texts: return 0.0
        try:
            existing_texts = list(self.content_texts.values())[-50:]
            if not existing_texts: return 0.0
            all_texts = existing_texts + [new_text]
            tfidf_matrix = self.vectorizer.fit_transform(all_texts)
            similarities = cosine_similarity(tfidf_matrix[-1:], tfidf_matrix[:-1])
            return similarities.max()
        except Exception:
            return 0.0
    
    def find_most_similar_content(self, new_text):
        try:
            existing_texts = list(self.content_texts.values())[-50:]
            existing_hashes = list(self.content_texts.keys())[-50:]
            if not existing_texts: return None
            all_texts = existing_texts + [new_text]
            tfidf_matrix = self.vectorizer.fit_transform(all_texts)
            similarities = cosine_similarity(tfidf_matrix[-1:], tfidf_matrix[:-1])
            max_index = similarities.argmax()
            return self.content_cache.get(existing_hashes[max_index])
        except Exception:
            return None

class AnomalyDetector:
    """异常检测器"""
    
    def detect_engagement_anomalies(self, post_data):
        score, num_comments, upvote_ratio = post_data.get("score", 0), post_data.get("num_comments", 0), post_data.get("upvote_ratio", 0.5)
        anomalies = []
        if score > 0 and (num_comments / score) > 10: anomalies.append("异常评论比率")
        if upvote_ratio > 0.95 or upvote_ratio < 0.05: anomalies.append("异常投票比例")
        return anomalies

    def detect_content_anomalies(self, title, text):
        anomalies = []
        if text and self.calculate_title_content_relevance(title, text) < 0.3:
            anomalies.append("标题与正文相关性低")
        return anomalies
    
    def calculate_title_content_relevance(self, title, text):
        try:
            vectorizer = TfidfVectorizer()
            tfidf_matrix = vectorizer.fit_transform([title, text])
            return cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        except Exception:
            return 0.5

# --- Main Curation Logic ---

def enhanced_quality_check(post_data, deduplicator, anomaly_detector):
    """
    Performs a series of quality checks on a post.
    Returns a tuple (is_valid: bool, reasons: list[str]).
    """
    # 1. Basic content validation
    validation_result = ContentValidator.validate_content_quality(post_data)
    if not validation_result["is_valid"]:
        return False, validation_result["violations"]
    
    # 2. Deduplication check
    is_duplicate, duplicate_id = deduplicator.is_duplicate(
        post_data.get("title", ""), post_data.get("selftext", ""), post_data.get("id")
    )
    if is_duplicate:
        return False, [f"重复内容 (与 {duplicate_id} 相似)"]
    
    # 3. Anomaly detection
    engagement_anomalies = anomaly_detector.detect_engagement_anomalies(post_data)
    content_anomalies = anomaly_detector.detect_content_anomalies(
        post_data.get("title", ""), post_data.get("selftext", "")
    )
    all_anomalies = engagement_anomalies + content_anomalies
    if len(all_anomalies) > 1: # Stricter anomaly check
        return False, [f"检测到异常: {', '.join(all_anomalies)}"]
    
    return True, []

def main():
    """
    Main function to process raw Reddit posts, apply quality filters,
    and move high-quality English posts to a curated directory.
    """
    print("--- English Reddit Curation Engine v5.0 ---")
    
    # Initialize paths
    input_path = Path(INPUT_DIR)
    curated_path = Path(CURATED_ENGLISH_DIR)
    rejected_path = Path(REJECTED_ARCHIVE_DIR)
    
    # Create directories
    input_path.mkdir(exist_ok=True)
    curated_path.mkdir(exist_ok=True)
    rejected_path.mkdir(exist_ok=True)
    
    # Initialize tools
    deduplicator = ContentDeduplicator()
    anomaly_detector = AnomalyDetector()
    
    # Get JSON files from inbox
    json_files = list(input_path.glob("*.json"))
    if not json_files:
        print(f"✅ Inbox is empty. No new posts in '{INPUT_DIR}'.")
        return
    
    print(f"🔎 Found {len(json_files)} new posts. Starting quality analysis...")
    
    accepted_count = 0
    rejected_count = 0
    
    for i, json_file in enumerate(json_files):
        print(f"[{i+1}/{len(json_files)}] Processing {json_file.name}...", end="")
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not data.get("title"):
                print(" ❌ REJECTED (No title)")
                destination = rejected_path / json_file.name
                rejected_count += 1
            else:
                is_valid, reasons = enhanced_quality_check(data, deduplicator, anomaly_detector)
                if is_valid:
                    print(" ✅ ACCEPTED")
                    destination = curated_path / json_file.name
                    accepted_count += 1
                else:
                    print(f" ❌ REJECTED ({', '.join(reasons[:2])})")
                    destination = rejected_path / json_file.name
                    rejected_count += 1
            
            # Move the file to its final destination
            json_file.rename(destination)

        except json.JSONDecodeError:
            print(" ❌ REJECTED (Invalid JSON)")
            json_file.rename(rejected_path / json_file.name)
            rejected_count += 1
        except Exception as e:
            print(f" ❌ ERROR: {e}")
            # Optionally move to rejected on other errors too
            # json_file.rename(rejected_path / json_file.name)
    
    # Save the updated deduplication cache
    deduplicator.save_cache()
    
    print("\n--- Curation Complete ---")
    print(f"Processed: {len(json_files)} files")
    print(f"✅ Accepted: {accepted_count} files moved to '{CURATED_ENGLISH_DIR}'")
    print(f"❌ Rejected: {rejected_count} files moved to '{REJECTED_ARCHIVE_DIR}'")

if __name__ == "__main__":
    main()
```

## `reddit_collection.py`

```python
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
```

## `reddit_config.json`

```json
{
    "ai_keywords": {
        "core_technical": [
            "AI", "LLM", "GPT-4", "GPT-5", "ChatGPT", "OpenAI", 
            "Anthropic", "Claude 3", "Llama 3", "Mistral", "Gemini",
            "neural network", "deep learning", "machine learning",
            "NLP", "computer vision", "transformer", "diffusion model",
            "generative AI", "AGI", "AI model", "AI algorithm",
            "AI training", "AI inference", "AI deployment"
        ],
        "business_finance": [
            "AI startup", "AI funding", "AI investment", "AI valuation",
            "AI business model", "AI revenue", "AI market cap",
            "AI IPO", "AI acquisition", "AI unicorn", "AI profitability",
            "AI monetization", "AI commercialization", "AI enterprise",
            "AI ROI", "AI economics", "AI market share"
        ],
        "ethics_policy": [
            "AI ethics", "AI safety", "AI regulation", "AI bias",
            "AI alignment", "AI governance", "AI policy",
            "AI risk", "AI security", "AI privacy", "AI transparency",
            "AI accountability", "AI fairness", "AI discrimination",
            "AI oversight", "AI compliance", "AI standards"
        ],
        "emerging_trends": [
            "AGI", "consciousness", "sentient AI", "AI singularity",
            "AI consciousness", "AI emotion", "AI creativity",
            "AI reasoning", "AI planning", "AI autonomy", "AI generalization",
            "AI breakthrough", "AI innovation", "AI disruption",
            "AI revolution", "AI evolution", "AI advancement"
        ],
        "industry_applications": [
            "AI in healthcare", "AI in finance", "AI in education", "AI automation",
            "AI in manufacturing", "AI in retail", "AI in transportation",
            "AI in legal", "AI in agriculture", "AI in energy",
            "AI workplace", "AI jobs", "AI employment", "AI productivity"
        ]
    },
    "search_strategies": {
        "comprehensive_search": true,
        "time_ranges": ["day", "week", "month"],
        "sort_methods": ["hot", "new", "top", "rising"],
        "max_results_per_method": 100,
        "enable_adaptive_search": true,
        "pre_filter_enabled": true
    },
    "subreddits": [
        {
            "category": "Core AI Tech",
            "name": "MachineLearning",
            "methods": ["hot", "new", "top_week", "search"],
            "thresholds": { "min_score": 30, "min_comments": 15, "min_ratio": 0.2 },
            "keyword_categories": ["core_technical", "emerging_trends"]
        },
        {
            "category": "Core AI Tech",
            "name": "LocalLLaMA",
            "methods": ["hot", "new", "rising", "search"],
            "thresholds": { "min_score": 25, "min_comments": 20, "min_ratio": 0.3 },
            "keyword_categories": ["core_technical", "industry_applications"]
        },
        {
            "category": "Core AI Tech",
            "name": "ChatGPT",
            "methods": ["hot", "new", "controversial", "search"],
            "thresholds": { "min_score": 80, "min_comments": 40, "min_ratio": 0.25 },
            "keyword_categories": ["core_technical", "business_finance"]
        },
        {
            "category": "Core AI Tech",
            "name": "OpenAI",
            "methods": ["hot", "new", "search"],
            "thresholds": { "min_score": 40, "min_comments": 25, "min_ratio": 0.2 },
            "keyword_categories": ["core_technical", "business_finance"]
        },
        {
            "category": "Business & Finance",
            "name": "investing",
            "methods": ["search", "new", "top_day"],
            "thresholds": { "min_score": 20, "min_comments": 30, "min_ratio": 0.3 },
            "keyword_categories": ["business_finance", "emerging_trends"]
        },
        {
            "category": "Business & Finance",
            "name": "Entrepreneur",
            "methods": ["search", "hot", "new"],
            "thresholds": { "min_score": 25, "min_comments": 20, "min_ratio": 0.4 },
            "keyword_categories": ["business_finance", "industry_applications"]
        },
        {
            "category": "Business & Finance",
            "name": "Business",
            "methods": ["search", "hot", "top_week"],
            "thresholds": { "min_score": 50, "min_comments": 30, "min_ratio": 0.2 },
            "keyword_categories": ["business_finance", "emerging_trends"]
        },
        {
            "category": "AI Ethics & Policy",
            "name": "Futurology",
            "methods": ["hot", "search", "controversial", "top_week"],
            "thresholds": { "min_score": 80, "min_comments": 80, "min_ratio": 0.4 },
            "keyword_categories": ["ethics_policy", "emerging_trends"]
        },
        {
            "category": "AI Ethics & Policy",
            "name": "singularity",
            "methods": ["hot", "new", "controversial", "search"],
            "thresholds": { "min_score": 35, "min_comments": 25, "min_ratio": 0.3 },
            "keyword_categories": ["ethics_policy", "emerging_trends"]
        },
        {
            "category": "AI Ethics & Policy",
            "name": "philosophy",
            "methods": ["search", "hot", "controversial"],
            "thresholds": { "min_score": 20, "min_comments": 20, "min_ratio": 0.4 },
            "keyword_categories": ["ethics_policy", "emerging_trends"]
        },
        {
            "category": "AI Ethics & Policy",
            "name": "ethics",
            "methods": ["search", "hot", "new"],
            "thresholds": { "min_score": 15, "min_comments": 15, "min_ratio": 0.3 },
            "keyword_categories": ["ethics_policy"]
        },
        {
            "category": "Technology Industry",
            "name": "technology",
            "methods": ["search", "hot", "new", "top_day"],
            "thresholds": { "min_score": 60, "min_comments": 30, "min_ratio": 0.2 },
            "keyword_categories": ["core_technical", "business_finance", "emerging_trends"]
        },
        {
            "category": "Technology Industry",
            "name": "tech",
            "methods": ["search", "hot", "new"],
            "thresholds": { "min_score": 40, "min_comments": 25, "min_ratio": 0.2 },
            "keyword_categories": ["core_technical", "business_finance"]
        },
        {
            "category": "Deep Tech & Academic",
            "name": "computervision",
            "methods": ["hot", "new", "search"],
            "thresholds": { "min_score": 20, "min_comments": 15, "min_ratio": 0.15 },
            "keyword_categories": ["core_technical"]
        },
        {
            "category": "Deep Tech & Academic",
            "name": "NLP",
            "methods": ["hot", "new", "search"],
            "thresholds": { "min_score": 15, "min_comments": 10, "min_ratio": 0.15 },
            "keyword_categories": ["core_technical"]
        },
        {
            "category": "Creative & Applications",
            "name": "StableDiffusion",
            "methods": ["hot", "new", "controversial", "search"],
            "thresholds": { "min_score": 80, "min_comments": 35, "min_ratio": 0.15 },
            "keyword_categories": ["core_technical", "industry_applications"]
        },
        {
            "category": "Creative & Applications",
            "name": "Midjourney",
            "methods": ["hot", "new", "search"],
            "thresholds": { "min_score": 50, "min_comments": 25, "min_ratio": 0.2 },
            "keyword_categories": ["core_technical", "industry_applications"]
        },
        {
            "category": "Creative & Applications",
            "name": "weirddalle",
            "methods": ["hot", "new"],
            "thresholds": { "min_score": 40, "min_comments": 20, "min_ratio": 0.2 },
            "keyword_categories": ["core_technical"]
        },
        {
            "category": "Developer Community",
            "name": "programming",
            "methods": ["search", "hot", "new"],
            "thresholds": { "min_score": 40, "min_comments": 25, "min_ratio": 0.2 },
            "keyword_categories": ["core_technical", "industry_applications"]
        },
        {
            "category": "Developer Community",
            "name": "Python",
            "methods": ["search", "hot", "new"],
            "thresholds": { "min_score": 30, "min_comments": 20, "min_ratio": 0.2 },
            "keyword_categories": ["core_technical", "industry_applications"]
        },
        {
            "category": "Developer Community",
            "name": "DataScience",
            "methods": ["search", "hot", "new"],
            "thresholds": { "min_score": 25, "min_comments": 15, "min_ratio": 0.2 },
            "keyword_categories": ["core_technical", "business_finance"]
        },
        {
            "category": "AI Ethics & Policy",
            "name": "darkfuturology",
            "methods": ["hot", "controversial", "search"],
            "thresholds": { "min_score": 30, "min_comments": 35, "min_ratio": 0.6 },
            "keyword_categories": ["ethics_policy", "emerging_trends"]
        }
    ]
}
```