#!/usr/bin/env python3
"""
验证修复效果：确保 get_clusters_for_opportunity_mapping 不会返回已有opportunities的clusters
"""
import sys
import logging
from pathlib import Path

# 添加项目根目录到path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.db import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("=== 验证修复效果 ===")

    # 1. 获取所有clusters
    with db.get_connection("clusters") as conn:
        cursor = conn.execute("""
            SELECT id, cluster_name, cluster_size
            FROM clusters
            ORDER BY cluster_size DESC
            LIMIT 20
        """)
        all_clusters = [dict(row) for row in cursor.fetchall()]

    logger.info(f"数据库中共有 {len(all_clusters)} 个clusters (显示前20个)")

    # 2. 获取有opportunities的clusters
    with db.get_connection("clusters") as conn:
        cursor = conn.execute("""
            SELECT DISTINCT c.id, c.cluster_name, c.cluster_size, COUNT(o.id) as opp_count
            FROM clusters c
            JOIN opportunities o ON o.cluster_id = c.id
            GROUP BY c.id
            ORDER BY c.cluster_size DESC
        """)
        clusters_with_opps = [dict(row) for row in cursor.fetchall()]

    logger.info(f"其中 {len(clusters_with_opps)} 个clusters已有opportunities")

    # 3. 获取将被映射的clusters（使用修改后的方法）
    clusters_for_mapping = db.get_clusters_for_opportunity_mapping()

    logger.info(f"get_clusters_for_opportunity_mapping() 返回 {len(clusters_for_mapping)} 个clusters")

    # 4. 验证：返回的clusters不应该在 clusters_with_opps 中
    returned_cluster_ids = set()
    for cluster in clusters_for_mapping:
        # 对齐聚群的cluster_name可能不同，使用cluster_name来判断
        cluster_id = cluster.get('id')
        if cluster_id:
            returned_cluster_ids.add(cluster_id)

    clusters_with_opps_ids = set(c['id'] for c in clusters_with_opps)

    # 找出交集
    overlap = returned_cluster_ids & clusters_with_opps_ids

    if overlap:
        logger.error(f"❌ 验证失败！发现 {len(overlap)} 个已有opportunities的clusters被返回：")
        for cluster_id in overlap:
            cluster = next(c for c in clusters_with_opps if c['id'] == cluster_id)
            logger.error(f"  - Cluster {cluster_id}: {cluster['cluster_name']} ({cluster['opp_count']} opportunities)")
        return False
    else:
        logger.info("✅ 验证通过！返回的clusters都没有已存在的opportunities")

        # 显示详情
        logger.info(f"\n详情：")
        logger.info(f"  - 所有clusters总数: {len(all_clusters)} (显示前20)")
        logger.info(f"  - 已有opportunities的clusters: {len(clusters_with_opps)}")
        logger.info(f"  - 待映射的clusters: {len(clusters_for_mapping)}")
        logger.info(f"  - 预期待映射的clusters数量: {len(all_clusters) - len(clusters_with_opps)} (基于前20个估算)")

        # 显示待映射的clusters示例
        if clusters_for_mapping:
            logger.info(f"\n待映射的clusters示例（前5个）：")
            for cluster in clusters_for_mapping[:5]:
                logger.info(f"  - Cluster {cluster.get('id')}: {cluster.get('cluster_name')} (size: {cluster.get('cluster_size')})")

        return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
