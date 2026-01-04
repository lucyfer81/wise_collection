"""
Change Detection Module for Reddit Pain Point Finder
变化检测模块 - 检测clusters的显著变化
"""
import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from utils.db import db
from utils.llm_client import llm_client

logger = logging.getLogger(__name__)


class ChangeDetector:
    """变化检测器 - 检测clusters的显著变化"""

    def __init__(self):
        """初始化变化检测器"""
        self.stats = {
            "total_clusters_checked": 0,
            "significant_changes_detected": 0,
            "new_clusters_detected": 0,
            "processing_time": 0.0
        }

        # 加载配置
        self.config = self._load_config()
        logger.info(f"ChangeDetector initialized with config: {self.config}")

    def _load_config(self) -> Dict[str, Any]:
        """加载配置"""
        try:
            import yaml
            config_path = "config/thresholds.yaml"
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config.get('significant_change_thresholds', {})
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """返回默认配置"""
        return {
            'min_new_events': 5,
            'min_new_events_ratio': 0.1,
            'min_new_authors': 3,
            'min_cross_subreddit_delta': 2,
            'min_days_since_last_score': 7,
            'periodic_full_rescore_days': 30
        }

    def detect_significant_changes(
        self,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """检测最近N小时内发生显著变化的clusters

        Args:
            hours: 检查最近N小时的变化

        Returns:
            显著变化的clusters列表
        """
        logger.info(f"Detecting significant changes in last {hours} hours...")
        start_time = time.time()

        try:
            # 1. 获取所有clusters
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT id, cluster_name, cluster_size, pain_event_ids, created_at
                    FROM clusters
                    ORDER BY cluster_size DESC
                """)
                all_clusters = [dict(row) for row in cursor.fetchall()]

            self.stats["total_clusters_checked"] = len(all_clusters)
            logger.info(f"Checking {len(all_clusters)} clusters for changes...")

            # 2. 对每个cluster检查变化
            significant_changes = []

            for cluster in all_clusters:
                cluster_id = cluster['id']

                # 2.1 获取上一个快照
                latest_snapshot = self._get_latest_snapshot(cluster_id)

                if not latest_snapshot:
                    # 新cluster，需要首次评分
                    significant_changes.append({
                        "cluster_id": cluster_id,
                        "cluster_name": cluster['cluster_name'],
                        "change_type": "new_cluster",
                        "reason": "First time scoring",
                        "priority": "high"
                    })
                    self.stats["new_clusters_detected"] += 1
                    logger.info(f"  → New cluster detected: {cluster_id} - {cluster['cluster_name']}")
                    continue

                # 2.2 计算当前指标
                current_metrics = self._calculate_cluster_metrics(cluster_id)
                previous_metrics = {
                    'cluster_size': latest_snapshot['cluster_size'],
                    'unique_authors': latest_snapshot['unique_authors'],
                    'cross_subreddit_count': latest_snapshot['cross_subreddit_count']
                }

                # 2.3 检查是否满足显著变化条件
                change_detected, change_details = self._check_significant_change(
                    current_metrics,
                    previous_metrics,
                    latest_snapshot
                )

                if change_detected:
                    significant_changes.append({
                        "cluster_id": cluster_id,
                        "cluster_name": cluster['cluster_name'],
                        "change_type": "significant_update",
                        "reasons": change_details['reasons'],
                        "priority": change_details['priority'],
                        "previous_snapshot": previous_metrics,
                        "current_snapshot": current_metrics
                    })
                    self.stats["significant_changes_detected"] += 1
                    logger.info(f"  → Significant change: {cluster_id} - {change_details['reasons']}")

            # 3. 更新统计信息
            processing_time = time.time() - start_time
            self.stats["processing_time"] = processing_time

            logger.info(f"""
=== Change Detection Summary ===
Clusters checked: {len(all_clusters)}
Significant changes: {len([c for c in significant_changes if c['change_type'] == 'significant_update'])}
New clusters: {len([c for c in significant_changes if c['change_type'] == 'new_cluster'])}
Processing time: {processing_time:.2f}s
""")

            return significant_changes

        except Exception as e:
            logger.error(f"Failed to detect significant changes: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _get_latest_snapshot(self, cluster_id: int) -> Optional[Dict[str, Any]]:
        """获取cluster的最新快照"""
        try:
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT *
                    FROM cluster_snapshots
                    WHERE cluster_id = ?
                    ORDER BY snapshot_time DESC
                    LIMIT 1
                """, (cluster_id,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Failed to get latest snapshot for cluster {cluster_id}: {e}")
            return None

    def _calculate_cluster_metrics(self, cluster_id: int) -> Dict[str, Any]:
        """计算cluster的当前指标"""
        try:
            # 获取cluster的pain_event_ids
            with db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT pain_event_ids
                    FROM clusters
                    WHERE id = ?
                """, (cluster_id,))
                result = cursor.fetchone()
                if not result:
                    return {}
                pain_event_ids = json.loads(result['pain_event_ids'])

            if not pain_event_ids:
                return {}

            # 计算指标
            with db.get_connection("pain") as conn:
                placeholders = ','.join('?' for _ in pain_event_ids)

                # 1. Cluster size
                cluster_size = len(pain_event_ids)

                # 2. Unique authors
                cursor = conn.execute(f"""
                    SELECT COUNT(DISTINCT fp.author) as unique_count
                    FROM pain_events pe
                    JOIN filtered_posts fp ON pe.post_id = fp.id
                    WHERE pe.id IN ({placeholders})
                """, pain_event_ids)
                unique_authors = cursor.fetchone()['unique_count']

                # 3. Cross-subreddit count
                cursor = conn.execute(f"""
                    SELECT COUNT(DISTINCT fp.subreddit) as subreddit_count
                    FROM pain_events pe
                    JOIN filtered_posts fp ON pe.post_id = fp.id
                    WHERE pe.id IN ({placeholders})
                """, pain_event_ids)
                cross_subreddit_count = cursor.fetchone()['subreddit_count']

                # 4. Avg frequency score
                cursor = conn.execute(f"""
                    SELECT pe.frequency
                    FROM pain_events pe
                    WHERE pe.id IN ({placeholders})
                """, pain_event_ids)
                frequencies = [row['frequency'] or '' for row in cursor.fetchall()]
                avg_frequency_score = self._frequency_to_score(frequencies)

                # 5. Latest event extracted_at
                cursor = conn.execute(f"""
                    SELECT MAX(pe.extracted_at) as latest_at
                    FROM pain_events pe
                    WHERE pe.id IN ({placeholders})
                """, pain_event_ids)
                latest_event_extracted_at = cursor.fetchone()['latest_at']

            return {
                'cluster_size': cluster_size,
                'unique_authors': unique_authors,
                'cross_subreddit_count': cross_subreddit_count,
                'avg_frequency_score': avg_frequency_score,
                'latest_event_extracted_at': latest_event_extracted_at
            }

        except Exception as e:
            logger.error(f"Failed to calculate metrics for cluster {cluster_id}: {e}")
            return {}

    def _frequency_to_score(self, frequencies: List[str]) -> float:
        """将频率文本转换为评分"""
        if not frequencies:
            return 0.0

        score_map = {
            'daily': 10, '每天': 10, 'day': 9,
            'weekly': 8, '每周': 8, 'week': 7,
            'monthly': 6, '每月': 6, 'month': 5,
            'often': 7, '经常': 7, 'frequently': 8,
            'sometimes': 5, '有时': 5, 'occasionally': 4,
            'rarely': 3, '很少': 3, 'seldom': 2,
            'always': 9, '总是': 9, 'constantly': 8,
            'never': 1, '从不': 1, 'default': 4
        }

        scores = []
        for freq in frequencies:
            if not freq:
                scores.append(score_map.get('default', 4))
                continue

            freq_lower = freq.lower()
            matched = False
            for key, score in score_map.items():
                if key == 'default':
                    continue
                if key in freq_lower:
                    scores.append(score)
                    matched = True
                    break

            if not matched:
                scores.append(score_map.get('default', 4))

        return sum(scores) / len(scores) if scores else 0.0

    def _check_significant_change(
        self,
        current_metrics: Dict[str, Any],
        previous_metrics: Dict[str, Any],
        latest_snapshot: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """检查cluster是否发生显著变化"""
        change_reasons = []
        priority = "medium"

        # 检查1: 新增events数量
        new_events = current_metrics['cluster_size'] - previous_metrics['cluster_size']
        if new_events >= self.config.get('min_new_events', 5):
            change_reasons.append(f"Added {new_events} new events")
            if new_events >= 20:
                priority = "high"

        # 检查2: 新增events比例
        if previous_metrics['cluster_size'] > 0:
            new_events_ratio = new_events / previous_metrics['cluster_size']
            if new_events_ratio >= self.config.get('min_new_events_ratio', 0.1):
                change_reasons.append(
                    f"Added {new_events_ratio*100:.1f}% new events"
                )

        # 检查3: 新增作者
        new_authors = current_metrics['unique_authors'] - previous_metrics['unique_authors']
        if new_authors >= self.config.get('min_new_authors', 3):
            change_reasons.append(f"Added {new_authors} new authors")

        # 检查4: 跨源验证增加
        cross_subreddit_delta = (
            current_metrics['cross_subreddit_count'] -
            previous_metrics['cross_subreddit_count']
        )
        if cross_subreddit_delta >= self.config.get('min_cross_subreddit_delta', 2):
            change_reasons.append(
                f"Cross-subreddit count increased by {cross_subreddit_delta}"
            )

        # 检查5: 距离上次评分的时间
        if latest_snapshot.get('snapshot_time'):
            last_snapshot_time = datetime.fromisoformat(latest_snapshot['snapshot_time'])
            days_since_last = (datetime.now() - last_snapshot_time).days
            min_days = self.config.get('min_days_since_last_score', 7)
            if days_since_last >= min_days:
                change_reasons.append(f"{days_since_last} days since last snapshot")

        return (len(change_reasons) > 0, {
            'reasons': '; '.join(change_reasons),
            'priority': priority
        })

    def save_cluster_snapshots(
        self,
        cluster_ids: List[int],
        snapshot_reason: str = "after_cluster_update"
    ) -> bool:
        """为指定的clusters创建快照

        Args:
            cluster_ids: 需要快照的cluster IDs
            snapshot_reason: 快照原因

        Returns:
            是否成功
        """
        try:
            logger.info(f"Saving snapshots for {len(cluster_ids)} clusters (reason: {snapshot_reason})")

            with db.get_connection("clusters") as conn:
                for cluster_id in cluster_ids:
                    # 计算当前指标
                    metrics = self._calculate_cluster_metrics(cluster_id)
                    if not metrics:
                        continue

                    # 插入快照
                    conn.execute("""
                        INSERT INTO cluster_snapshots (
                            cluster_id, snapshot_time,
                            cluster_size, unique_authors, cross_subreddit_count,
                            avg_frequency_score, latest_event_extracted_at,
                            snapshot_reason
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        cluster_id,
                        datetime.now().isoformat(),
                        metrics['cluster_size'],
                        metrics['unique_authors'],
                        metrics['cross_subreddit_count'],
                        metrics.get('avg_frequency_score', 0.0),
                        metrics.get('latest_event_extracted_at'),
                        snapshot_reason
                    ))

                conn.commit()
                logger.info(f"✓ Saved {len(cluster_ids)} cluster snapshots")
                return True

        except Exception as e:
            logger.error(f"Failed to save cluster snapshots: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Detect significant changes in clusters")
    parser.add_argument("--hours", type=int, default=24, help="Check last N hours")
    parser.add_argument("--save-snapshots", action="store_true", help="Save cluster snapshots")
    args = parser.parse_args()

    try:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        detector = ChangeDetector()

        # 检测显著变化
        changes = detector.detect_significant_changes(hours=args.hours)

        # 输出结果
        print("\n" + "=" * 80)
        print("SIGNIFICANT CHANGES DETECTED")
        print("=" * 80)

        for change in changes:
            print(f"\nCluster {change['cluster_id']}: {change['cluster_name']}")
            print(f"  Type: {change['change_type']}")
            print(f"  Priority: {change.get('priority', 'N/A')}")
            print(f"  Reason: {change.get('reasons', change.get('reason', 'N/A'))}")

        # 保存快照（如果指定）
        if args.save_snapshots and changes:
            cluster_ids = [c['cluster_id'] for c in changes]
            detector.save_cluster_snapshots(cluster_ids, "manual_snapshot")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
