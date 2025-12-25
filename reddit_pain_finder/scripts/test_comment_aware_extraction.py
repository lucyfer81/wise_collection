#!/usr/bin/env python3
"""
A/B Testing Script for Comment-Aware Pain Extraction
对比测试脚本 - 验证评论数据是否提升痛点抽取质量
"""
import json
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from utils.llm_client import llm_client
from utils.db import db

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def load_old_prompt():
    """加载旧的prompt（不含评论）"""
    return """You are an information extraction engine.

Your task:
From the following Reddit post, extract concrete PAIN EVENTS.
A pain event is a specific recurring problem experienced by the author,
not opinions, not general complaints.

Rules:
- Do NOT summarize the post
- Do NOT give advice
- If no concrete pain exists, return an empty list
- Be literal and conservative
- Focus on actionable problems people face repeatedly

Output JSON only with this format:
{
  "pain_events": [
    {
      "actor": "who experiences the problem",
      "context": "what they are trying to do",
      "problem": "the concrete difficulty",
      "current_workaround": "how they currently cope (if any)",
      "frequency": "how often it happens (explicit or inferred)",
      "emotional_signal": "frustration, anxiety, exhaustion, etc.",
      "mentioned_tools": ["tool1", "tool2"],
      "confidence": 0.8
    }
  ],
  "extraction_summary": "brief summary of findings"
}"""

def extract_with_old_method(post_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """使用旧方法提取痛点（不含评论）"""
    prompt = load_old_prompt()

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"""
Title: {post_data.get('title', '')}
Body: {post_data.get('body', '')}
Subreddit: {post_data.get('subreddit', '')}
Upvotes: {post_data.get('score', 0)}
Comments: {post_data.get('num_comments', 0)}
"""}
    ]

    try:
        response = llm_client.chat_completion(
            messages=messages,
            model_type="pain_extraction",
            json_mode=True
        )
        content = response.get("content", {})
        return content.get("pain_events", [])
    except Exception as e:
        logger.error(f"Old method failed: {e}")
        return []

def extract_with_new_method(post_data: Dict[str, Any], comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """使用新方法提取痛点（含评论）"""
    # 复用现有的 extract_pain_points 方法
    try:
        response = llm_client.extract_pain_points(
            title=post_data.get('title', ''),
            body=post_data.get('body', ''),
            subreddit=post_data.get('subreddit', ''),
            upvotes=post_data.get('score', 0),
            comments_count=post_data.get('num_comments', 0),
            top_comments=comments
        )
        content = response.get("content", {})
        return content.get("pain_events", [])
    except Exception as e:
        logger.error(f"New method failed: {e}")
        return []

def select_test_posts(limit: int = 10) -> List[Dict[str, Any]]:
    """选择测试用帖子（高质量且有评论）"""
    # 选择高pain_score且有足够评论的帖子
    posts = db.get_filtered_posts(limit=50, min_pain_score=0.5)

    # 筛选出有评论数据的帖子
    posts_with_comments = []
    for post in posts:
        comments = db.get_top_comments_for_post(post['id'], top_n=5)
        if len(comments) >= 3:  # 至少3条评论
            post['comments'] = comments
            posts_with_comments.append(post)
        if len(posts_with_comments) >= limit:
            break

    logger.info(f"Selected {len(posts_with_comments)} posts for A/B testing")
    return posts_with_comments

def calculate_quality_metrics(pain_events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """计算质量指标"""
    if not pain_events:
        return {
            "event_count": 0,
            "avg_confidence": 0,
            "avg_problem_length": 0,
            "has_workaround_count": 0,
            "has_evidence_sources": 0
        }

    return {
        "event_count": len(pain_events),
        "avg_confidence": sum(e.get("confidence", 0) for e in pain_events) / len(pain_events),
        "avg_problem_length": sum(len(e.get("problem", "")) for e in pain_events) / len(pain_events),
        "has_workaround_count": sum(1 for e in pain_events if e.get("current_workaround")),
        "has_evidence_sources": sum(1 for e in pain_events if e.get("evidence_sources"))
    }

def generate_comparison_report(results: List[Dict[str, Any]]) -> str:
    """生成对比报告"""
    report = ["# A/B Test Report: Comment-Aware Pain Extraction\n"]
    report.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.append(f"**Test Size:** {len(results)} posts\n")
    report.append("---\n\n")

    # 汇总统计
    old_total_events = sum(r['old_metrics']['event_count'] for r in results)
    new_total_events = sum(r['new_metrics']['event_count'] for r in results)
    old_avg_confidence = sum(r['old_metrics']['avg_confidence'] for r in results) / len(results)
    new_avg_confidence = sum(r['new_metrics']['avg_confidence'] for r in results) / len(results)
    old_avg_length = sum(r['old_metrics']['avg_problem_length'] for r in results) / len(results)
    new_avg_length = sum(r['new_metrics']['avg_problem_length'] for r in results) / len(results)

    report.append("## Overall Metrics\n\n")
    report.append(f"| Metric | Old Method | New Method | Change |\n")
    report.append(f"|--------|-----------|-----------|--------|\n")
    report.append(f"| Total Pain Events | {old_total_events} | {new_total_events} | {new_total_events - old_total_events:+d} |\n")
    report.append(f"| Avg Confidence | {old_avg_confidence:.3f} | {new_avg_confidence:.3f} | {(new_avg_confidence - old_avg_confidence):+.3f} |\n")
    report.append(f"| Avg Problem Length | {old_avg_length:.1f} | {new_avg_length:.1f} | {(new_avg_length - old_avg_length):+.1f} |\n")
    report.append("\n")

    # 详细对比
    report.append("## Per-Post Comparison\n\n")
    for i, result in enumerate(results, 1):
        post = result['post']
        old = result['old_metrics']
        new = result['new_metrics']

        report.append(f"### {i}. {post['title'][:60]}...\n\n")
        report.append(f"**Subreddit:** {post['subreddit']} | **Comments:** {len(post.get('comments', []))}\n\n")
        report.append(f"| Metric | Old | New |\n")
        report.append(f"|--------|-----|-----|\n")
        report.append(f"| Events | {old['event_count']} | {new['event_count']} |\n")
        report.append(f"| Confidence | {old['avg_confidence']:.2f} | {new['avg_confidence']:.2f} |\n")
        report.append(f"| Problem Length | {old['avg_problem_length']:.0f} | {new['avg_problem_length']:.0f} |\n")

        # 样本对比
        if old['event_count'] > 0:
            old_events = result['old_events']
            report.append("**Old Method Sample:**\n```\n")
            for e in old_events[:2]:
                report.append(f"- {e.get('problem', 'N/A')[:80]}...\n")
            report.append("```\n")

        if new['event_count'] > 0:
            new_events = result['new_events']
            report.append("**New Method Sample:**\n```\n")
            for e in new_events[:2]:
                evidence = e.get('evidence_sources', [])
                report.append(f"- [{', '.join(evidence)}] {e.get('problem', 'N/A')[:80]}...\n")
            report.append("```\n")

        report.append("\n")

    # 结论
    report.append("## Qualitative Assessment\n\n")
    improvement_count = sum(1 for r in results if r['new_metrics']['avg_problem_length'] > r['old_metrics']['avg_problem_length'])
    report.append(f"- **Specificity Improvement:** {improvement_count}/{len(results)} posts show more detailed problem descriptions\n")
    report.append(f"- **Evidence Tracking:** {sum(r['new_metrics']['has_evidence_sources'] for r in results)} pain events now track evidence sources\n")
    report.append(f"- **Avg Description Length:** {new_avg_length:.0f} vs {old_avg_length:.0f} chars ({((new_avg_length/old_avg_length - 1) * 100):+.0f}% change)\n")

    return "".join(report)

def main():
    """主函数"""
    logger.info("Starting A/B test for comment-aware pain extraction...")

    # 选择测试帖子
    test_posts = select_test_posts(limit=10)
    if not test_posts:
        logger.error("No test posts found!")
        return

    results = []

    # 对每个帖子运行A/B测试
    for i, post in enumerate(test_posts, 1):
        logger.info(f"Testing post {i}/{len(test_posts)}: {post['title'][:50]}...")

        comments = post.get('comments', [])

        # 旧方法（不含评论）
        old_events = extract_with_old_method(post)
        old_metrics = calculate_quality_metrics(old_events)

        # 新方法（含评论）
        new_events = extract_with_new_method(post, comments)
        new_metrics = calculate_quality_metrics(new_events)

        results.append({
            'post': post,
            'old_events': old_events,
            'new_events': new_events,
            'old_metrics': old_metrics,
            'new_metrics': new_metrics
        })

        # 添加延迟避免API限流
        import time
        time.sleep(2)

    # 生成报告
    report = generate_comparison_report(results)

    # 保存报告
    report_path = Path("docs/plans/ab_test_results.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)

    logger.info(f"\n{'='*60}")
    logger.info(f"A/B Test Complete!")
    logger.info(f"Report saved to: {report_path}")
    logger.info(f"{'='*60}\n")

    # 打印摘要
    old_total = sum(r['old_metrics']['event_count'] for r in results)
    new_total = sum(r['new_metrics']['event_count'] for r in results)
    logger.info(f"Total Events: Old={old_total}, New={new_total}")
    logger.info(f"Check the report for detailed analysis")

if __name__ == "__main__":
    main()
