# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Directories ---
BASE_DIR = Path(__file__).resolve().parent
CONTENT_DIR = BASE_DIR / "content"
OUTPUT_DIR = BASE_DIR / "output"

# Reddit Collection Directories
REDDIT_INBOX_DIR = CONTENT_DIR / "reddit"
PROCESSED_IDS_FILE = CONTENT_DIR / "processed_ids.json"
POTENTIAL_SOURCES_LOG = BASE_DIR / "potential_new_subreddits.log"

# Curation Directories
CURATED_DIR = CONTENT_DIR / "reddit_english_curated"
REJECTED_DIR = CONTENT_DIR / "processed_json"

# Topic Analysis Directories
TOPICS_OUTPUT_DIR = OUTPUT_DIR / "topics"

# --- Database ---
DATABASE_FILE = BASE_DIR / "topics_database.db"

# --- API & Models ---
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")

# Model Names
ANALYSIS_MODEL = "Qwen/Qwen3-32B"
TRANSLATION_MODEL = "Qwen/Qwen2.5-7B-Instruct"
JUDGE_MODEL = "Qwen/Qwen2.5-7B-Instruct"

# --- Algorithm Parameters ---
DBSCAN_EPS = 0.8
DBSCAN_MIN_SAMPLES = 2
COMMENTS_TO_FETCH = 20
