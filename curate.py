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
        
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
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
