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

def ensure_json_formatting(file_path):
    """Ensure JSON file is properly formatted with consistent escaping."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Rewrite with consistent JSON formatting
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"Warning: Could not reformat {file_path.name}: {e}")
        return False

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
            dest_path = unclassified_dir / post['file_path'].name
            shutil.copy(post['file_path'], dest_path)
            ensure_json_formatting(dest_path)
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
                dest_path = failed_dir / post['file_path'].name
                shutil.copy(post['file_path'], dest_path)
                ensure_json_formatting(dest_path)
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
            dest_path = topic_dir / post['file_path'].name
            shutil.copy(post['file_path'], dest_path)
            ensure_json_formatting(dest_path)
        
        print(f"  ✅ Saved topic summary and {len(cluster_posts)} posts to '{topic_dir.name}'")

    # 6. Handle unclassified (noise) posts
    if -1 in clusters:
        unclassified_dir = output_path / "_unclassified"
        unclassified_dir.mkdir()
        for post in clusters[-1]:
            dest_path = unclassified_dir / post['file_path'].name
            shutil.copy(post['file_path'], dest_path)
            ensure_json_formatting(dest_path)
        print(f"\n✅ Copied {len(clusters[-1])} unclassified posts to '{unclassified_dir.name}'")

    print("\n🎉 Topic analysis complete!")

if __name__ == "__main__":
    main()
