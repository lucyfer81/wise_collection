# curate.py - v4.0 (Centralized Config & Bug Fix)
import json
import sys
from pathlib import Path
from openai import OpenAI
import config

# --- Configuration ---
if not config.SILICONFLOW_API_KEY:
    raise ValueError("Siliconflow API key not found in .env file.")

client = OpenAI(api_key=config.SILICONFLOW_API_KEY, base_url=config.SILICONFLOW_BASE_URL)

JUDGEMENT_PROMPT = """
You are a sharp, discerning AI news editor. Evaluate the following Reddit post.
Respond ONLY with a single, minified JSON object with no newlines, based on these criteria:
1. "quality_score": An integer from 0-10. How insightful, original, and well-presented is this? (10 is best)
2. "is_rejected": A boolean (true or false). Would you reject this for being spam, a meme, a low-effort question, off-topic, or just uninteresting?
3. "rejection_reason": A short string explaining why it was rejected (e.g., "Low-effort question", "Meme/Joke", "Not AI-related"). Provide this ONLY if is_rejected is true.
4. "content_type": A string classifying the content. Choose ONE of: "Technical Deep Dive", "News/Announcement", "Discussion/Debate", "Project Showcase", "Question".
5. "summary_blurb": A string containing a single, compelling sentence describing the post's core idea.

--- POST DATA ---
Title: {title}
Content Snippet: {selftext_snippet}
Stats: Score={score}, Comments={num_comments}
"""

def get_llm_judgement(post_data):
    """Uses an LLM to perform a nuanced quality check."""
    title = post_data.get("title", "")
    selftext_snippet = post_data.get("selftext", "")[:500] # Use a larger snippet for better context
    
    prompt = JUDGEMENT_PROMPT.format(
        title=title,
        selftext_snippet=selftext_snippet,
        score=post_data.get("score", 0),
        num_comments=post_data.get("num_comments", 0)
    )
    
    try:
        messages = [{"role": "system", "content": "You are a helpful assistant that responds in minified JSON."}, {"role": "user", "content": prompt}]
        chat_completion = client.chat.completions.create(model=config.JUDGE_MODEL, messages=messages, temperature=0.0, max_tokens=250)
        response_text = chat_completion.choices[0].message.content.strip()
        
        # Robustly parse the JSON from the response
        judgement = json.loads(response_text)
        return judgement
    except Exception as e:
        print(f"  -> LLM judgement failed or returned invalid JSON: {e}", file=sys.stderr)
        return {"is_rejected": True, "rejection_reason": "LLM judgement error"}


def main():
    print("--- AI-Powered Judge v4.0 ---")
    # Use paths from config
    input_path, curated_path, rejected_path = config.REDDIT_INBOX_DIR, config.CURATED_DIR, config.REJECTED_DIR
    input_path.mkdir(exist_ok=True); curated_path.mkdir(exist_ok=True); rejected_path.mkdir(exist_ok=True)

    json_files = list(input_path.glob("*.json"))
    if not json_files:
        print("✅ Inbox is empty. Nothing to curate."); return

    print(f"🔎 Found {len(json_files)} new posts. Starting AI-powered judgement...")
    accepted_count, rejected_count = 0, 0
    
    for i, json_file in enumerate(json_files):
        print(f"[{i+1}/{len(json_files)}] Judging {json_file.name}...", end="")
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not data.get("title"):
                print(" ❌ REJECTED (No title)")
                destination = rejected_path / json_file.name
                json_file.rename(destination)
                rejected_count += 1
            else:
                judgement = get_llm_judgement(data)
                if judgement.get("is_rejected"):
                    reason = judgement.get('rejection_reason', 'Unknown reason')
                    print(f" ❌ REJECTED ({reason})")
                    destination = rejected_path / json_file.name
                    json_file.rename(destination) # Just move the original file
                    rejected_count += 1
                else:
                    # Add the new rich metadata to the post data before saving
                    data['curation_metadata'] = judgement
                    print(f" ✅ ACCEPTED (Type: {judgement.get('content_type')})")
                    destination = curated_path / json_file.name
                    # Write the modified data to the new location
                    with open(destination, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    json_file.unlink() # Delete the original file from the inbox
                    accepted_count += 1

        except Exception as e:
            print(f" ❌ SYSTEM ERROR processing {json_file.name}: {e}", file=sys.stderr)
            try:
                json_file.rename(rejected_path / json_file.name)
            except OSError as move_err:
                print(f"   FATAL: Could not even move rejected file: {move_err}", file=sys.stderr)
            rejected_count += 1

    print("\n--- Curation Complete ---")
    print(f"✅ Accepted: {accepted_count} files moved to '{config.CURATED_DIR}'")
    print(f"❌ Rejected/Archived: {rejected_count} files moved to '{config.REJECTED_DIR}'")


if __name__ == "__main__":
    main()
