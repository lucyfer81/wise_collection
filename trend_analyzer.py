# trend_analyzer.py - v2.0 (Centralized Config & DB Handling)
import sqlite3
import pandas as pd
import re
from collections import Counter
from difflib import get_close_matches
import config

# --- Relevance Scoring Constants ---
SCORE_EXACT_KEYWORD = 30
SCORE_PARTIAL_KEYWORD = 15
SCORE_TOPIC_NAME = 20
SCORE_SUMMARY = 10
SCORE_FUZZY_MATCH = 5

def calculate_relevance_score(keywords, search_terms, topic_name, summary_chinese):
    """Calculate relevance score based on multiple factors."""
    score = 0
    keywords_lower = [kw.lower() for kw in keywords]
    search_terms_lower = [term.lower() for term in search_terms]
    topic_name_lower = topic_name.lower()
    summary_lower = summary_chinese.lower() if summary_chinese else ""
    
    for term in search_terms_lower:
        if term in keywords_lower:
            score += SCORE_EXACT_KEYWORD
        if any(term in kw or kw in term for kw in keywords_lower):
            score += SCORE_PARTIAL_KEYWORD
        if term in topic_name_lower:
            score += SCORE_TOPIC_NAME
        if term in summary_lower:
            score += SCORE_SUMMARY
        if get_close_matches(term, keywords_lower, n=1, cutoff=0.7):
            score += SCORE_FUZZY_MATCH
            
    return min(score, 100)

def query_topics_by_keywords(conn, search_terms, min_score=20):
    """Finds topics matching multiple keywords with relevance scoring."""
    query = "SELECT id, created_at, topic_name, topic_keywords, summary_english, summary_chinese FROM topics ORDER BY created_at DESC"
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        return df
    
    results = []
    for _, row in df.iterrows():
        keywords = [kw.strip() for kw in row['topic_keywords'].split(',')] if row['topic_keywords'] else []
        score = calculate_relevance_score(keywords, search_terms, row['topic_name'], row['summary_chinese'])
        
        if score >= min_score:
            row_dict = row.to_dict()
            row_dict['relevance_score'] = score
            results.append(row_dict)
    
    if not results:
        return pd.DataFrame()

    results_df = pd.DataFrame(results).sort_values('relevance_score', ascending=False)
    cols = ['created_at', 'topic_name', 'relevance_score', 'summary_chinese']
    return results_df[[col for col in cols if col in results_df.columns]]

def get_related_keywords(conn, keyword, limit=5):
    """Find related keywords based on co-occurrence in topics."""
    query = "SELECT topic_keywords FROM topics WHERE topic_keywords LIKE ?"
    df = pd.read_sql_query(query, conn, params=(f"%{keyword}%",))
    
    if df.empty:
        return []
    
    all_keywords = [kw.strip().lower() for kw_string in df['topic_keywords'].dropna() for kw in kw_string.split(',')]
    keyword_counter = Counter(all_keywords)
    keyword_counter.pop(keyword.lower(), None)
    return [kw for kw, count in keyword_counter.most_common(limit)]

def list_all_keywords(conn):
    """Lists all unique keywords found in the database."""
    query = "SELECT topic_keywords FROM topics"
    df = pd.read_sql_query(query, conn)
    all_keywords = set(kw.strip() for kw_string in df['topic_keywords'].dropna() for kw in kw_string.split(','))
    return sorted(list(all_keywords))

def get_keyword_suggestions(conn, partial_keyword, limit=10):
    """Get keyword suggestions based on partial input."""
    all_keywords = list_all_keywords(conn)
    suggestions = []
    partial_lower = partial_keyword.lower()
    
    for kw in all_keywords:
        kw_lower = kw.lower()
        if partial_lower in kw_lower:
            priority = 2 if kw_lower.startswith(partial_lower) else 1
            suggestions.append((kw, priority))
    
    suggestions.sort(key=lambda x: x[1], reverse=True)
    return [kw for kw, _ in suggestions[:limit]]

def get_recent_topics(conn, days=7):
    """Gets all topics from the last N days."""
    query = f"SELECT created_at, topic_name, summary_chinese FROM topics WHERE created_at >= date('now', '-{days} days') ORDER BY created_at DESC"
    return pd.read_sql_query(query, conn)

def interactive_search():
    """Interactive search interface with suggestions and related keywords."""
    print("\n" + "="*60)
    print("🔍 智能趋势分析工具 | Intelligent Trend Analysis Tool")
    print("="*60)
    
    try:
        conn = sqlite3.connect(config.DATABASE_FILE)
    except sqlite3.Error as e:
        print(f"FATAL: Could not connect to database at {config.DATABASE_FILE}. Error: {e}")
        return

    while True:
        print("\n" + "-"*40 + "\n\nOptions:\n1. Keyword Search\n2. Browse All Keywords\n3. Recent 7 Days Topics\n4. Exit")
        choice = input("\nPlease choose (1-4): ").strip()
        
        if choice == "1":
            keyword_search(conn)
        elif choice == "2":
            browse_keywords(conn)
        elif choice == "3":
            show_recent_topics(conn)
        elif choice == "4":
            print("\n👋 Thank you for using!")
            break
        else:
            print("\n❌ Invalid choice, please try again")
    
    conn.close()

def keyword_search(conn):
    """Enhanced keyword search with suggestions."""
    print("\n" + "-"*40 + "\n🔎 Keyword Search\nTip: Support multiple keywords, separate with spaces")
    
    while True:
        search_input = input("\nEnter keywords (or 'back' to return): ").strip()
        if search_input.lower() == 'back': break
        if not search_input: continue
        
        search_terms = [term.strip() for term in search_input.split() if term.strip()]
        
        if len(search_terms) == 1:
            suggestions = get_keyword_suggestions(conn, search_terms[0], limit=5)
            if suggestions: print(f"\n💡 Related suggestions: {', '.join(suggestions[:3])}")
        
        print(f"\n🔍 Searching for: {', '.join(search_terms)}")
        results = query_topics_by_keywords(conn, search_terms, min_score=15)
        
        if not results.empty:
            print(f"\n✅ Found {len(results)} relevant topics\n" + "="*80)
            print(results.to_markdown(index=False))
            print("="*80)
            
            if len(search_terms) == 1:
                related = get_related_keywords(conn, search_terms[0], limit=3)
                if related: print(f"\n🔗 Related keywords: {', '.join(related)}")
        else:
            print(f"\n❌ No relevant topics found for: {', '.join(search_terms)}")
            if len(search_terms) == 1:
                similar = get_keyword_suggestions(conn, search_terms[0], limit=3)
                if similar: print(f"💡 Try these keywords: {', '.join(similar)}")

def browse_keywords(conn):
    """Browse all keywords with pagination."""
    print("\n" + "-"*40 + "\n📚 Browse Keywords")
    keywords = list_all_keywords(conn)
    if not keywords:
        print("❌ No keywords in database"); return
    
    total, per_page, current_page = len(keywords), 20, 0
    total_pages = (total + per_page - 1) // per_page
    
    while True:
        start, end = current_page * per_page, min((current_page + 1) * per_page, total)
        print(f"\n📄 Page {current_page + 1}/{total_pages}\nKeywords:")
        for i in range(start, end): print(f"  {i+1:3d}. {keywords[i]}")
        
        action = input("\n(n)ext, (p)revious, (s)earch, (back): ").strip().lower()
        
        if action == 'n' and current_page < total_pages - 1: current_page += 1
        elif action == 'p' and current_page > 0: current_page -= 1
        elif action == 's':
            term = input("Enter search term: ").strip()
            if term:
                matches = [kw for kw in keywords if term.lower() in kw.lower()]
                print(f"\n🔍 Matching: {', '.join(matches[:10])}" if matches else "\n❌ No matches found")
        elif action == 'back': break

def show_recent_topics(conn):
    """Show recent topics with time filtering."""
    print("\n" + "-"*40 + "\n📈 Recent Topics")
    recent_topics = get_recent_topics(conn, 7)
    if not recent_topics.empty:
        print(f"\n📅 Topics from last 7 days ({len(recent_topics)} total)\n" + "="*80)
        print(recent_topics.to_markdown(index=False))
        print("="*80)
    else:
        print("❌ No topics in the last 7 days")

if __name__ == "__main__":
    interactive_search()
