#!/usr/bin/env python3
"""
Decision Shortlist - Milestone 1 Acceptance Test

This test validates the basic functionality of the Decision Shortlist feature:
1. Output count (3-5 candidates)
2. Candidate completeness (problem, mvp, why_now fields)
3. File generation (markdown + JSON)
4. JSON format validation

Run with: python3 tests/test_decision_shortlist_milestone1.py
"""

import json
import os
import sys
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from pipeline.decision_shortlist import DecisionShortlistGenerator
from utils.db import db


def setup_test_data():
    """Create test data for the acceptance test"""
    print("Setting up test data...")

    try:
        with db.get_connection("clusters") as conn:
            # Create test clusters
            conn.execute("""
                INSERT INTO clusters (cluster_name, cluster_description, source_type,
                                    centroid_summary, pain_event_ids, cluster_size)
                VALUES
                    ('high_pain_cluster_1', 'Users struggling with X', 'reddit',
                     'Users need automated solution for repetitive task X', '[1,2,3,4,5,6,7,8]', 10),
                    ('high_pain_cluster_2', 'Users frustrated by Y', 'reddit',
                     'Manual process Y is taking too much time', '[9,10,11,12,13,14]', 8),
                    ('high_pain_cluster_3', 'Users confused about Z', 'reddit',
                     'Lack of clarity in process Z causing errors', '[15,16,17,18,19]', 7),
                    ('medium_pain_cluster_4', 'Users want feature A', 'reddit',
                     'Feature A would greatly improve workflow', '[20,21,22,23]', 6)
            """)
            conn.commit()

            # Get cluster IDs
            clusters = conn.execute("SELECT id, cluster_name FROM clusters ORDER BY id DESC LIMIT 4").fetchall()
            cluster_map = {name: id for id, name in clusters}

            # Create test opportunities with high scores
            conn.execute("""
                INSERT INTO opportunities (cluster_id, opportunity_name, description,
                                         total_score, trust_level, target_users,
                                         missing_capability, why_existing_fail)
                VALUES
                    (?, 'Auto Task Tool', 'Automate repetitive task X',
                     8.5, 0.85, 'Data analysts', 'Automation', 'Too manual'),
                    (?, 'Process Optimizer', 'Streamline manual process Y',
                     8.0, 0.80, 'Business users', 'Streamlining', 'Too slow'),
                    (?, 'Clarity Assistant', 'Provide guidance for process Z',
                     7.5, 0.75, 'New users', 'Guidance', 'Too confusing'),
                    (?, 'Feature A Tool', 'Add feature A to workflow',
                     7.0, 0.70, 'Power users', 'Feature A', 'Missing capability')
            """, (
                cluster_map['high_pain_cluster_1'],
                cluster_map['high_pain_cluster_2'],
                cluster_map['high_pain_cluster_3'],
                cluster_map['medium_pain_cluster_4']
            ))
            conn.commit()

            print("✅ Test data created successfully")
            return True

    except Exception as e:
        print(f"❌ Failed to create test data: {e}")
        return False


def cleanup_test_data():
    """Clean up test data"""
    print("\nCleaning up test data...")

    try:
        with db.get_connection("clusters") as conn:
            # Delete test opportunities
            conn.execute("""
                DELETE FROM opportunities
                WHERE opportunity_name IN (
                    'Auto Task Tool', 'Process Optimizer',
                    'Clarity Assistant', 'Feature A Tool'
                )
            """)

            # Delete test clusters
            conn.execute("""
                DELETE FROM clusters
                WHERE cluster_name IN (
                    'high_pain_cluster_1', 'high_pain_cluster_2',
                    'high_pain_cluster_3', 'medium_pain_cluster_4'
                )
            """)

            conn.commit()
            print("✅ Test data cleaned up successfully")
            return True

    except Exception as e:
        print(f"⚠️  Warning: Failed to clean up test data: {e}")
        return False


def check_output_count(shortlist_result):
    """Test 1: Validate output count (3-5 candidates)"""
    print("\n" + "="*60)
    print("TEST 1: Output Count Validation")
    print("="*60)

    count = shortlist_result['shortlist_count']
    print(f"Candidates found: {count}")

    if 3 <= count <= 5:
        print(f"✅ PASS: Found {count} candidates (within 3-5 range)")
        return True
    else:
        print(f"❌ FAIL: Expected 3-5 candidates, got {count}")
        return False


def check_candidate_completeness(shortlist_result):
    """Test 2: Validate candidate completeness (problem, mvp, why_now)"""
    print("\n" + "="*60)
    print("TEST 2: Candidate Completeness Validation")
    print("="*60)

    shortlist = shortlist_result['shortlist']
    all_complete = True

    for idx, candidate in enumerate(shortlist, 1):
        print(f"\nCandidate {idx}: {candidate['opportunity_name']}")

        readable_content = candidate.get('readable_content', {})

        # Check required fields
        has_problem = 'problem' in readable_content
        has_mvp = 'mvp' in readable_content
        has_why_now = 'why_now' in readable_content

        print(f"  - Problem: {'✅' if has_problem else '❌'}")
        print(f"  - MVP: {'✅' if has_mvp else '❌'}")
        print(f"  - Why Now: {'✅' if has_why_now else '❌'}")

        if has_problem and has_mvp and has_why_now:
            print(f"  ✅ COMPLETE")
        else:
            print(f"  ❌ INCOMPLETE")
            all_complete = False

    if all_complete:
        print("\n✅ PASS: All candidates have required fields")
        return True
    else:
        print("\n❌ FAIL: Some candidates are missing required fields")
        return False


def check_file_generation(shortlist_result):
    """Test 3: Validate file generation (markdown + JSON)"""
    print("\n" + "="*60)
    print("TEST 3: File Generation Validation")
    print("="*60)

    markdown_path = shortlist_result.get('markdown_report')
    json_path = shortlist_result.get('json_report')

    # Check markdown file
    if markdown_path and os.path.exists(markdown_path):
        print(f"✅ Markdown file exists: {markdown_path}")
        markdown_ok = True
    else:
        print(f"❌ Markdown file missing or not specified")
        markdown_ok = False

    # Check JSON file
    if json_path and os.path.exists(json_path):
        print(f"✅ JSON file exists: {json_path}")
        json_ok = True
    else:
        print(f"❌ JSON file missing or not specified")
        json_ok = False

    if markdown_ok and json_ok:
        print("\n✅ PASS: Both files generated successfully")
        return True
    else:
        print("\n❌ FAIL: One or more files missing")
        return False


def check_json_format(shortlist_result):
    """Test 4: Validate JSON format"""
    print("\n" + "="*60)
    print("TEST 4: JSON Format Validation")
    print("="*60)

    json_path = shortlist_result.get('json_report')

    if not json_path:
        print("❌ FAIL: No JSON file specified")
        return False

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print("✅ JSON is valid and parseable")

        # Check required top-level fields
        required_fields = ['generated_at', 'total_candidates', 'candidates']
        missing_fields = [f for f in required_fields if f not in data]

        if missing_fields:
            print(f"❌ Missing top-level fields: {missing_fields}")
            return False

        print("✅ All required top-level fields present")

        # Check candidate structure
        candidates = data['candidates']
        if not candidates:
            print("⚠️  Warning: No candidates in JSON")
            return True  # Not a failure, just empty

        print(f"Validating {len(candidates)} candidates...")

        for idx, candidate in enumerate(candidates, 1):
            print(f"\nCandidate {idx}:")

            # Check candidate fields
            required_candidate_fields = [
                'opportunity_name', 'final_score', 'viability_score',
                'cluster_size', 'trust_level', 'readable_content',
                'cross_source_validation'
            ]

            missing = [f for f in required_candidate_fields if f not in candidate]

            if missing:
                print(f"  ❌ Missing fields: {missing}")
                return False
            else:
                print(f"  ✅ All required fields present")

            # Check readable_content structure
            readable_content = candidate.get('readable_content', {})
            if not all(k in readable_content for k in ['problem', 'mvp', 'why_now']):
                print(f"  ❌ Missing readable_content fields")
                return False
            else:
                print(f"  ✅ readable_content complete")

        print("\n✅ PASS: JSON format is valid")
        return True

    except json.JSONDecodeError as e:
        print(f"❌ FAIL: Invalid JSON format: {e}")
        return False
    except Exception as e:
        print(f"❌ FAIL: Error reading JSON: {e}")
        return False


def main():
    """Run all Milestone 1 acceptance tests"""
    print("="*60)
    print("Decision Shortlist - Milestone 1 Acceptance Tests")
    print("="*60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Setup test data
    if not setup_test_data():
        print("\n❌ FAILED: Could not setup test data")
        return 1

    try:
        # Run the decision shortlist generator
        print("\n" + "="*60)
        print("Running Decision Shortlist Generator...")
        print("="*60)

        generator = DecisionShortlistGenerator()
        result = generator.generate_shortlist()

        # Run all tests
        test_results = []

        test_results.append(("Output Count (3-5)", check_output_count(result)))
        test_results.append(("Candidate Completeness", check_candidate_completeness(result)))
        test_results.append(("File Generation", check_file_generation(result)))
        test_results.append(("JSON Format", check_json_format(result)))

        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)

        passed = sum(1 for _, result in test_results if result)
        total = len(test_results)

        for test_name, result in test_results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status}: {test_name}")

        print(f"\nTotal: {passed}/{total} tests passed")

        if passed == total:
            print("\n🎉 ALL TESTS PASSED - Milestone 1 Complete!")
            return 0
        else:
            print(f"\n❌ {total - passed} test(s) failed")
            return 1

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Cleanup
        cleanup_test_data()
        print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    sys.exit(main())
