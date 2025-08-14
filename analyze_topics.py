# analyze_topics.py - v3.0 ("The Strategic Analyst" with Central Config)
import json
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from openai import OpenAI
from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
import config

# --- Configuration ---
if not config.SILICONFLOW_API_KEY:
    raise ValueError("Siliconflow API key not found in .env file.")

client = OpenAI(api_key=config.SILICONFLOW_API_KEY, base_url=config.SILICONFLOW_BASE_URL)

# --- Prompts ---
STRATEGIC_SUMMARY_PROMPT = """
You are a world-class intelligence analyst specializing in AI. You have been given a cluster of Reddit posts and curation summaries about a single topic.
Synthesize all of it into a structured strategic briefing in English. The briefing MUST contain these exact sections:

### 1. The Core Event or Idea
(A one-paragraph summary of the central news, technology, or idea that sparked this conversation.)

### 2. The Bull Case (Arguments For)
(Summarize the key arguments from proponents. What are the exciting possibilities? What problems does this solve? Quote or paraphrase key points.)

### 3. The Bear Case (Arguments Against)
(Summarize the primary critiques, concerns, and risks raised by skeptics. What are the potential downsides or flaws? Quote or paraphrase key points.)

### 4. Key Entities & Players
(List the main companies, products, or people at the center of this discussion. e.g., OpenAI, Nvidia, Llama 3, Jensen Huang.)

### 5. The Unanswered Question
(Conclude with a single, powerful, open-ended question that captures the core tension or what the community is waiting to see next.)

--- START OF CONTENT CLUSTER ---
{english_text_block}
--- END OF CONTENT CLUSTER ---
"""

TRANSLATION_PROMPT = """You are a professional translator. Translate the following English text into Simplified Chinese. Preserve all Markdown formatting and structure:

{english_text_block}

Provide only the Chinese translation, no additional text."""

# --- Database Functions ---
def init_db(conn):
    """Initializes the SQLite database and table."""
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic_name TEXT NOT NULL,
        topic_keywords TEXT,
        summary_english TEXT,
        summary_chinese TEXT,
        source_post_ids TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()

def log_topic_to_db(conn, topic_name, keywords, summary_en, summary_zh, post_ids):
    """Logs a completed topic analysis to the database."""
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO topics (topic_name, topic_keywords, summary_english, summary_chinese, source_post_ids)
    VALUES (?, ?, ?, ?, ?)
    """, (topic_name, ", ".join(keywords), summary_en, summary_zh, json.dumps(post_ids)))
    conn.commit()

# --- LLM Function ---
def call_llm(model, prompt_template, content):
    messages = [{"role": "user", "content": prompt_template.format(english_text_block=content)}]
    try:
        chat_completion = client.chat.completions.create(model=model, messages=messages, temperature=0.3, max_tokens=3000)
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"  -> LLM call failed: {e}", file=sys.stderr)
        return None

# --- Main Analysis Logic ---
def main():
    print("--- Strategic Analyst v3.0 ---")
    
    # Use paths from config
    input_path, output_path = config.CURATED_DIR, config.TOPICS_OUTPUT_DIR
    if not input_path.exists() or not any(input_path.iterdir()):
        print(f"✅ Curated directory '{input_path}' is empty. Nothing to analyze."); return

    if output_path.exists(): shutil.rmtree(output_path)
    output_path.mkdir(parents=True)
    
    posts = []
    for json_file in input_path.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data['file_path'] = json_file
                posts.append(data)
        except Exception as e: print(f"Warning: Could not load {json_file.name}: {e}", file=sys.stderr)

    if len(posts) < config.DBSCAN_MIN_SAMPLES:
        print(f"❌ Not enough posts ({len(posts)}) to form topics. Required: {config.DBSCAN_MIN_SAMPLES}."); return
    
    documents = [p.get('curation_metadata', {}).get('summary_blurb', p.get('title')) for p in posts]
    vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(documents)
    feature_names = vectorizer.get_feature_names_out()

    dbscan = DBSCAN(eps=config.DBSCAN_EPS, min_samples=config.DBSCAN_MIN_SAMPLES, metric='cosine')
    labels = dbscan.fit_predict(tfidf_matrix)
    
    num_topics = len(set(labels)) - (1 if -1 in labels else 0)
    print(f"📊 Found {num_topics} topics.")

    clusters = defaultdict(list)
    for i, label in enumerate(labels):
        clusters[label].append(posts[i])

    # --- Database Connection ---
    conn = None
    try:
        if config.TURSO_DB_URL and config.TURSO_DB_AUTH_TOKEN:
            print("🚀 Connecting to Turso cloud database...")
            import libsql
            conn = libsql.connect(sync_url=config.TURSO_DB_URL, auth_token=config.TURSO_DB_AUTH_TOKEN)
        else:
            print("📦 Using local SQLite database...")
            conn = sqlite3.connect(config.DATABASE_FILE)
        
        init_db(conn)
        print("✅ Database connection successful.")
    except Exception as e:
        print(f"❌ FATAL: Could not connect to or initialize the database. Error: {e}", file=sys.stderr)
        sys.exit(1)
    # --- End of Database Connection ---

    for label, cluster_posts in clusters.items():
        if label == -1: continue
        print(f"\n--- Analyzing Topic {label+1} ---")
        
        cluster_indices = [i for i, l in enumerate(labels) if l == label]
        top_keywords = feature_names[tfidf_matrix[cluster_indices].mean(axis=0).A1.argsort()[-5:][::-1]]
        topic_name = re.sub(r'[^\w-]', '_', "_".join(top_keywords))
        print(f"  -> Topic Name: {topic_name}")
        
        english_text_block = "\n\n---\n\n".join([f"Title: {p['title']}\nBlurb: {p.get('curation_metadata', {}).get('summary_blurb', '')}" for p in cluster_posts])
        english_summary = call_llm(config.ANALYSIS_MODEL, STRATEGIC_SUMMARY_PROMPT, english_text_block)
        
        if not english_summary:
            print("  ❌ Failed to generate strategic summary. Skipping."); continue
        
        chinese_summary = call_llm(config.TRANSLATION_MODEL, TRANSLATION_PROMPT, english_summary)
        if not chinese_summary:
            chinese_summary = f"**TRANSLATION FAILED**\n\n---\n\n{english_summary}"
        
        topic_dir = output_path / f"topic_{label+1}_{topic_name}"
        topic_dir.mkdir()
        with open(topic_dir / "_STRATEGIC_BRIEFING_zh.md", 'w', encoding='utf-8') as f: f.write(chinese_summary)
        
        post_ids = [p['id'] for p in cluster_posts]
        for post in cluster_posts: shutil.copy(post['file_path'], topic_dir / post['file_path'].name)
        
        log_topic_to_db(conn, topic_name, top_keywords, english_summary, chinese_summary, post_ids)
        print(f"  ✅ Saved briefing and logged topic to database.")

    conn.close() # Close the connection at the end
    print("\n🎉 Topic analysis complete!")

if __name__ == "__main__":
    main()
