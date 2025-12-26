#!/usr/bin/env python3
"""为现有clusters生成JTBD字段"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db import db
from utils.llm_client import llm_client
import json
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_cluster(cluster_id: int) -> bool:
    """为单个cluster生成JTBD"""
    try:
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("""
                SELECT id, cluster_name, cluster_description, common_pain,
                       common_context, example_events, job_statement
                FROM clusters
                WHERE id = ?
            """, (cluster_id,))

            cluster = cursor.fetchone()

            if not cluster:
                logger.warning(f"Cluster {cluster_id} not found")
                return False

            cluster_dict = dict(cluster)

            # 检查是否需要更新：job_statement为空 OR desired_outcomes为空
            needs_update = (
                not cluster_dict.get("job_statement") or
                not cluster_dict.get("desired_outcomes") or
                cluster_dict.get("desired_outcomes") == "[]"
            )

            if not needs_update:
                logger.info(f"Cluster {cluster_id} already has complete JTBD, skipping")
                return False

            # 生成JTBD
            logger.info(f"Generating JTBD for cluster {cluster_id}: {cluster_dict['cluster_name']}")

            jtbd_result = llm_client.generate_jtbd_from_cluster({
                "cluster_name": cluster_dict["cluster_name"],
                "cluster_description": cluster_dict.get("cluster_description", ""),
                "common_pain": cluster_dict.get("common_pain", ""),
                "common_context": cluster_dict.get("common_context", ""),
                "example_events": json.loads(cluster_dict.get("example_events", "[]"))
            })

            jtbd_content = jtbd_result.get("content", {})

            # 更新数据库
            cursor.execute("""
                UPDATE clusters
                SET job_statement = ?,
                    job_steps = ?,
                    desired_outcomes = ?,
                    job_context = ?,
                    customer_profile = ?,
                    semantic_category = ?,
                    product_impact = ?
                WHERE id = ?
            """, (
                jtbd_content.get("job_statement", ""),
                json.dumps(jtbd_content.get("job_steps", [])),
                json.dumps(jtbd_content.get("desired_outcomes", [])),
                jtbd_content.get("job_context", ""),
                jtbd_content.get("customer_profile", ""),
                jtbd_content.get("semantic_category", ""),
                jtbd_content.get("product_impact", 0.0),
                cluster_id
            ))

            conn.commit()
            logger.info(f"✅ Migrated cluster {cluster_id}")
            return True

    except Exception as e:
        logger.error(f"Failed to migrate cluster {cluster_id}: {e}")
        return False

def main():
    """迁移所有现有clusters"""
    with db.get_connection("clusters") as conn:
        # 查找需要更新的clusters：job_statement为空 OR desired_outcomes为空
        cursor = conn.execute("""
            SELECT id FROM clusters
            WHERE job_statement IS NULL OR job_statement = ''
               OR desired_outcomes IS NULL OR desired_outcomes = '' OR desired_outcomes = '[]'
            ORDER BY id
        """)

        cluster_ids = [row["id"] for row in cursor.fetchall()]

    logger.info(f"Found {len(cluster_ids)} clusters to migrate")

    if not cluster_ids:
        logger.info("No clusters need migration")
        return

    success_count = 0
    for i, cluster_id in enumerate(cluster_ids, 1):
        logger.info(f"\n[{i}/{len(cluster_ids)}] Processing cluster {cluster_id}")
        if migrate_cluster(cluster_id):
            success_count += 1
            time.sleep(2)  # 避免API限流

    logger.info(f"\n=== Migration Complete ===")
    logger.info(f"Successfully migrated: {success_count}/{len(cluster_ids)}")

if __name__ == "__main__":
    main()
