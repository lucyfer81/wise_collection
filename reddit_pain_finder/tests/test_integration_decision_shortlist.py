#!/usr/bin/env python3
"""
Simple Integration Test for Decision Shortlist
Tests the complete workflow with mock data
"""

import json
import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from pipeline.decision_shortlist import DecisionShortlistGenerator
from utils.db import db


def test_full_workflow():
    """Test the complete decision shortlist workflow"""
    print("="*60)
    print("Decision Shortlist - Integration Test")
    print("="*60)

    # Create test data
    print("\n1. Creating test data...")
    try:
        with db.get_connection("clusters") as conn:
            # Create test clusters
            conn.execute("""
                INSERT INTO clusters (cluster_name, cluster_description, source_type,
                                    centroid_summary, pain_event_ids, cluster_size)
                VALUES
                    ('test_cluster_1', 'Test cluster 1', 'reddit',
                     'Users need automated solution', '[1,2,3,4,5,6,7,8,9,10]', 10),
                    ('test_cluster_2', 'Test cluster 2', 'reddit',
                     'Manual process is too slow', '[11,12,13,14,15,16]', 8)
            """)
            conn.commit()

            # Get cluster IDs
            clusters = conn.execute("SELECT id, cluster_name FROM clusters WHERE cluster_name LIKE 'test_cluster%'").fetchall()
            cluster_map = {name: id for id, name in clusters}

            # Create test opportunities
            conn.execute("""
                INSERT INTO opportunities (cluster_id, opportunity_name, description,
                                         total_score, trust_level, target_users,
                                         missing_capability, why_existing_fail)
                VALUES
                    (?, 'Test Opportunity 1', 'Great opportunity',
                     8.5, 0.85, 'Data analysts', 'Automation', 'Too manual'),
                    (?, 'Test Opportunity 2', 'Another good opportunity',
                     7.5, 0.75, 'Business users', 'Efficiency', 'Too slow')
            """, (cluster_map['test_cluster_1'], cluster_map['test_cluster_2']))
            conn.commit()

        print("✅ Test data created")

    except Exception as e:
        print(f"❌ Failed to create test data: {e}")
        return False

    # Run the generator
    print("\n2. Running Decision Shortlist Generator...")
    try:
        generator = DecisionShortlistGenerator()

        # Mock the LLM to avoid API calls
        original_generate = generator._generate_readable_content
        def mock_generate(opportunity, cluster, cross_source_info):
            return {
                'problem': f"Test problem for {opportunity['opportunity_name']}",
                'mvp': f"Test MVP for {opportunity['target_users']}",
                'why_now': "Test timing justification"
            }
        generator._generate_readable_content = mock_generate

        result = generator.generate_shortlist()

        print(f"✅ Generator completed successfully")
        print(f"   - Candidates: {result['shortlist_count']}")
        print(f"   - Markdown: {result.get('markdown_report', 'N/A')}")
        print(f"   - JSON: {result.get('json_report', 'N/A')}")

    except Exception as e:
        print(f"❌ Generator failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Validate results
    print("\n3. Validating results...")

    # Check candidate count
    count = result['shortlist_count']
    if not (1 <= count <= 5):  # Allow 1-5 for integration test
        print(f"❌ Invalid candidate count: {count}")
        return False
    print(f"✅ Candidate count valid: {count}")

    # Check readable content
    for candidate in result['shortlist']:
        content = candidate.get('readable_content', {})
        if not all(k in content for k in ['problem', 'mvp', 'why_now']):
            print(f"❌ Missing content in {candidate['opportunity_name']}")
            return False
    print(f"✅ All candidates have readable content")

    # Check files exist
    markdown_path = result.get('markdown_report')
    json_path = result.get('json_report')

    if markdown_path and os.path.exists(markdown_path):
        print(f"✅ Markdown file exists")
    else:
        print(f"❌ Markdown file missing")
        return False

    if json_path and os.path.exists(json_path):
        print(f"✅ JSON file exists")
    else:
        print(f"❌ JSON file missing")
        return False

    # Check JSON format
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        if 'candidates' not in data:
            print(f"❌ JSON missing 'candidates' field")
            return False
        print(f"✅ JSON format valid")
    except Exception as e:
        print(f"❌ JSON format invalid: {e}")
        return False

    # Cleanup
    print("\n4. Cleaning up test data...")
    try:
        with db.get_connection("clusters") as conn:
            conn.execute("DELETE FROM opportunities WHERE opportunity_name LIKE 'Test Opportunity%'")
            conn.execute("DELETE FROM clusters WHERE cluster_name LIKE 'test_cluster%'")
            conn.commit()
        print(f"✅ Test data cleaned up")

        # Clean up generated files
        if markdown_path and os.path.exists(markdown_path):
            os.remove(markdown_path)
            print(f"✅ Cleaned up {markdown_path}")
        if json_path and os.path.exists(json_path):
            os.remove(json_path)
            print(f"✅ Cleaned up {json_path}")

    except Exception as e:
        print(f"⚠️  Cleanup warning: {e}")

    print("\n" + "="*60)
    print("🎉 ALL TESTS PASSED")
    print("="*60)
    return True


if __name__ == "__main__":
    success = test_full_workflow()
    sys.exit(0 if success else 1)
