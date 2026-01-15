"""Test smart data sampling for opportunity mapping"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
import pytest
from pipeline.map_opportunity import OpportunityMapper


def test_create_llm_friendly_summary_limits_pain_events():
    """Should limit pain_events to top 20 most representative"""
    mapper = OpportunityMapper()

    # Create cluster with 30 pain events
    large_cluster = {
        "cluster_id": 1,
        "cluster_name": "Test Cluster",
        "cluster_description": "Test Description",
        "cluster_size": 30,
        "workflow_confidence": 0.8,
        "pain_events": [
            {
                "id": i,
                "problem": f"Problem {i}",
                "context": f"Context {i}" * 50,  # Long context
                "current_workaround": f"Workaround {i}" * 30,
                "emotional_signal": "frustration" if i % 2 == 0 else "anxiety",
                "frequency_score": i % 10,
                "post_pain_score": i * 100,
            }
            for i in range(30)
        ],
        "subreddit_distribution": {"test": 30},
        "mentioned_tools": {},
        "emotional_signals": {},
        "avg_frequency_score": 5.0,
    }

    summary = mapper._create_llm_friendly_cluster_summary(large_cluster)

    # Should have max 20 pain events
    assert len(summary["pain_events"]) <= 20, f"Expected max 20 pain_events, got {len(summary['pain_events'])}"


def test_create_llm_friendly_summary_truncates_long_fields():
    """Should truncate long text fields to 200 chars"""
    mapper = OpportunityMapper()

    cluster = {
        "cluster_id": 1,
        "cluster_name": "Test Cluster",
        "cluster_description": "Test Description",
        "cluster_size": 1,
        "workflow_confidence": 0.8,
        "pain_events": [
            {
                "id": 1,
                "problem": "x" * 500,  # Very long problem
                "context": "y" * 500,  # Very long context
                "current_workaround": "z" * 500,  # Very long workaround
                "emotional_signal": "frustration",
                "frequency_score": 5,
                "post_pain_score": 100,
            }
        ],
        "subreddit_distribution": {"test": 1},
        "mentioned_tools": {},
        "emotional_signals": {},
        "avg_frequency_score": 5.0,
    }

    summary = mapper._create_llm_friendly_cluster_summary(cluster)

    event = summary["pain_events"][0]
    assert len(event["problem"]) <= 200, f"Problem should be <= 200 chars, got {len(event['problem'])}"
    assert len(event["context"]) <= 200, f"Context should be <= 200 chars, got {len(event['context'])}"
    assert len(event["current_workaround"]) <= 200, f"Workaround should be <= 200 chars, got {len(event['current_workaround'])}"


def test_create_llm_friendly_summary_preserves_key_info():
    """Should preserve aggregated statistics"""
    mapper = OpportunityMapper()

    cluster = {
        "cluster_id": 1,
        "cluster_name": "Test Cluster",
        "cluster_description": "Test Description",
        "cluster_size": 5,
        "workflow_confidence": 0.85,
        "pain_events": [
            {
                "id": 1,
                "problem": "Problem 1",
                "context": "Context 1",
                "current_workaround": "Workaround 1",
                "emotional_signal": "frustration",
                "frequency_score": 5,
                "post_pain_score": 100,
            }
        ],
        "subreddit_distribution": {"reddit": 3, "programming": 2},
        "mentioned_tools": {"git": 5, "docker": 3},
        "emotional_signals": {"frustration": 4, "anxiety": 1},
        "avg_frequency_score": 7.5,
        "representative_problems": ["Problem 1", "Problem 2"],
        "representative_workarounds": ["Workaround 1"],
        "total_pain_score": 500,
    }

    summary = mapper._create_llm_friendly_cluster_summary(cluster)

    # Should preserve cluster metadata
    assert summary["cluster_id"] == 1
    assert summary["cluster_name"] == "Test Cluster"
    assert summary["cluster_size"] == 5
    assert summary["workflow_confidence"] == 0.85

    # Should preserve aggregated statistics
    assert summary["subreddit_distribution"] == {"reddit": 3, "programming": 2}
    assert summary["mentioned_tools"] == {"git": 5, "docker": 3}
    assert summary["emotional_signals"] == {"frustration": 4, "anxiety": 1}
    assert summary["avg_frequency_score"] == 7.5
    assert summary["total_pain_score"] == 500


def test_create_llm_friendly_summary_sorts_by_pain_score():
    """Should keep pain events with highest post_pain_score"""
    mapper = OpportunityMapper()

    cluster = {
        "cluster_id": 1,
        "cluster_name": "Test Cluster",
        "cluster_description": "Test Description",
        "cluster_size": 25,
        "workflow_confidence": 0.8,
        "pain_events": [
            {
                "id": i,
                "problem": f"Problem {i}",
                "context": f"Context {i}",
                "current_workaround": f"Workaround {i}",
                "emotional_signal": "frustration",
                "frequency_score": 5,
                "post_pain_score": i * 100,  # Higher ID = higher score
            }
            for i in range(25)
        ],
        "subreddit_distribution": {"test": 25},
        "mentioned_tools": {},
        "emotional_signals": {},
        "avg_frequency_score": 5.0,
    }

    summary = mapper._create_llm_friendly_cluster_summary(cluster)

    # Should keep top 20 (highest post_pain_score)
    assert len(summary["pain_events"]) == 20

    # The kept events should be the ones with highest scores
    kept_scores = [e["post_pain_score"] for e in summary["pain_events"]]
    assert max(kept_scores) == 2400, "Should keep highest scoring event"
    assert min(kept_scores) == 500, "Should drop lowest scoring events"


def test_create_llm_friendly_summary_token_estimate():
    """Should produce JSON that fits within reasonable token limit"""
    mapper = OpportunityMapper()

    # Create a worst-case cluster
    cluster = {
        "cluster_id": 1,
        "cluster_name": "Test Cluster with a Very Long Name",
        "cluster_description": "This is a very long description" * 20,
        "cluster_size": 100,
        "workflow_confidence": 0.9,
        "pain_events": [
            {
                "id": i,
                "problem": "Problem " + "x" * 200,
                "context": "Context " + "y" * 200,
                "current_workaround": "Workaround " + "z" * 200,
                "emotional_signal": "frustration",
                "frequency_score": 8,
                "post_pain_score": 1000,
            }
            for i in range(100)
        ],
        "subreddit_distribution": {f"sub{i}": 10 for i in range(10)},
        "mentioned_tools": {f"tool{i}": 5 for i in range(20)},
        "emotional_signals": {f"emotion{i}": 3 for i in range(10)},
        "avg_frequency_score": 7.0,
    }

    summary = mapper._create_llm_friendly_cluster_summary(cluster)
    json_str = json.dumps(summary)

    # Rough estimate: 1 token ≈ 4 characters
    # We want to stay well under 163,840 limit
    # Let's aim for < 50,000 chars to be safe (~12,000 tokens for user message)
    assert len(json_str) < 50000, f"Summary too large: {len(json_str)} chars"
