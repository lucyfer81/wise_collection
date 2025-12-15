#!/usr/bin/env python3
"""Fixed script to view the pipeline results from local database files"""

import sqlite3
import json

def get_connection(db_file):
    """Get connection to SQLite database"""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn

def view_summary():
    """View pipeline summary from error.txt"""
    print("\n" + "="*60)
    print("🎉 PIPELINE COMPLETED SUCCESSFULLY!")
    print("="*60)

    # Read from error.txt for the summary
    try:
        with open('error.txt', 'r') as f:
            content = f.read()
            # Find JSON summary
            start = content.find('"pipeline_completed": true')
            if start > -1:
                # Find the start of the JSON object
                json_start = content.rfind('{', 0, start)
                brace_count = 0
                for i in range(json_start, len(content)):
                    if content[i] == '{':
                        brace_count += 1
                    elif content[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i + 1
                            break

                json_str = content[json_start:json_end]
                try:
                    results = json.loads(json_str)
                    print(f"\n📊 Final Summary:")
                    print(f"   • Runtime: {results['total_runtime_minutes']:.2f} minutes")
                    print(f"   • Stages completed: {results['stages_completed']}/{results['stages_completed'] + results['stages_failed']}")
                    stats = results['database_statistics']
                    print(f"   • Raw posts collected: {stats['raw_posts_count']}")
                    print(f"   • Pain events extracted: {stats['pain_events_count']}")
                    print(f"   • Clusters created: {stats['clusters_count']}")
                    print(f"   • Opportunities identified: {stats['opportunities_count']}")

                    if results['top_opportunities']:
                        print(f"\n🏆 Top 5 Opportunities:")
                        for i, opp in enumerate(results['top_opportunities'][:5], 1):
                            print(f"   {i}. {opp['opportunity_name']} (Score: {opp['total_score']})")
                            print(f"      Cluster: {opp['cluster_name'][:50]}...")
                except json.JSONDecodeError:
                    print("Could not parse results JSON")
    except Exception as e:
        print(f"Could not read pipeline summary: {e}")

def view_opportunities():
    """View opportunities from database"""
    try:
        conn = get_connection('data/clusters.db')
        cursor = conn.cursor()

        cursor.execute("""
            SELECT o.opportunity_name, o.description, o.total_score,
                   o.recommendation, c.cluster_name, c.avg_pain_score
            FROM opportunities o
            JOIN clusters c ON o.cluster_id = c.id
            WHERE o.total_score >= 0.8
            ORDER BY o.total_score DESC, o.opportunity_name
            LIMIT 15
        """)

        rows = cursor.fetchall()
        if rows:
            print("\n" + "="*60)
            print("🏆 TOP OPPORTUNITIES (Score >= 0.8)")
            print("="*60)
            for row in rows:
                print(f"\n📌 {row['opportunity_name']} (Score: {row['total_score']:.2f})")
                print(f"   Cluster: {row['cluster_name'][:60]}...")
                print(f"   Description: {row['description'][:100]}...")
                if row['recommendation']:
                    print(f"   Recommendation: {row['recommendation'][:100]}...")

        conn.close()
    except Exception as e:
        print(f"Error viewing opportunities: {e}")

def view_clusters():
    """View top clusters by pain score"""
    try:
        conn = get_connection('data/clusters.db')
        cursor = conn.cursor()

        cursor.execute("""
            SELECT cluster_name, cluster_size, avg_pain_score,
                   (SELECT COUNT(*) FROM opportunities WHERE cluster_id = clusters.id) as opportunity_count
            FROM clusters
            ORDER BY avg_pain_score DESC, cluster_size DESC
            LIMIT 10
        """)

        rows = cursor.fetchall()
        if rows:
            print("\n" + "="*60)
            print("🔥 TOP PAIN CLUSTERS")
            print("="*60)
            for row in rows:
                print(f"\n📊 {row['cluster_name'][:70]}...")
                print(f"   Size: {row['cluster_size']} events, Avg Pain Score: {row['avg_pain_score']:.2f}")
                print(f"   Opportunities: {row['opportunity_count']}")

        conn.close()
    except Exception as e:
        print(f"Error viewing clusters: {e}")

def view_sample_posts():
    """View sample posts with high pain scores"""
    try:
        conn = get_connection('data/pain_events.db')
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.title, p.pain_score, p.url, p.subreddit
            FROM pain_events p
            WHERE p.pain_score > 0.8
            ORDER BY p.pain_score DESC
            LIMIT 8
        """)

        rows = cursor.fetchall()
        if rows:
            print("\n" + "="*60)
            print("💬 SAMPLE HIGH-PAIN POSTS")
            print("="*60)
            for row in rows:
                print(f"\nTitle: {row['title'][:70]}...")
                print(f"Pain Score: {row['pain_score']:.2f}")
                print(f"Subreddit: r/{row['subreddit']}")
                print(f"URL: {row['url']}")

        conn.close()
    except Exception as e:
        print(f"Error viewing posts: {e}")

def main():
    print("Reddit Pain Point Finder - Results Viewer")
    print("="*60)

    view_summary()
    view_opportunities()
    view_clusters()
    view_sample_posts()

    print("\n" + "="*60)
    print("💡 HOW TO VIEW INTERACTIVE DASHBOARD:")
    print("   1. cd ../reference-src")
    print("   2. streamlit run dashboard.py")
    print("\n💡 DATABASE FILES LOCATION:")
    print("   - ./data/raw_posts.db (442 posts collected)")
    print("   - ./data/pain_events.db (171 pain events extracted)")
    print("   - ./data/clusters.db (17 clusters, 22 opportunities)")
    print("   - ./data/filtered_posts.db (129 filtered posts)")
    print("="*60)

if __name__ == "__main__":
    main()