#!/usr/bin/env python3
"""
清理重复的opportunities
策略：保留每个cluster中raw_total_score最高的，如果分数相同则保留ID最大的
"""
import sqlite3
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "data/wise_collection.db"

def analyze_duplicates(conn):
    """分析重复数据"""
    cursor = conn.execute("""
        SELECT
            cluster_id,
            COUNT(*) as total_opportunities,
            COUNT(*) - 1 as to_be_deleted,
            GROUP_CONCAT(opportunity_name, '; ') as all_names
        FROM opportunities
        GROUP BY cluster_id
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
    """)

    duplicates = cursor.fetchall()
    total_to_delete = sum(row[2] for row in duplicates)

    logger.info(f"=== 重复数据分析 ===")
    logger.info(f"有重复opportunities的cluster数量: {len(duplicates)}")
    logger.info(f"将要删除的opportunities总数: {total_to_delete}")

    return duplicates, total_to_delete

def get_keep_opportunity_ids(conn):
    """获取要保留的opportunity IDs"""
    # 对于每个cluster，保留raw_total_score最高的，如果分数相同则保留ID最大的
    cursor = conn.execute("""
        WITH ranked AS (
            SELECT
                id,
                cluster_id,
                raw_total_score,
                ROW_NUMBER() OVER (
                    PARTITION BY cluster_id
                    ORDER BY raw_total_score DESC, id DESC
                ) as rank
            FROM opportunities
        )
        SELECT id FROM ranked WHERE rank = 1
    """)

    keep_ids = [row[0] for row in cursor.fetchall()]
    logger.info(f"保留的opportunities数量: {len(keep_ids)}")

    return keep_ids

def show_deletion_preview(conn, keep_ids):
    """显示将被删除的opportunities预览"""
    cursor = conn.execute("""
        SELECT
            o.id,
            o.cluster_id,
            c.cluster_name,
            o.opportunity_name,
            o.raw_total_score
        FROM opportunities o
        JOIN clusters c ON o.cluster_id = c.id
        WHERE o.id NOT IN ({})
        ORDER BY c.cluster_name, o.raw_total_score DESC
        LIMIT 20
    """.format(','.join(map(str, keep_ids))))

    logger.info(f"\n=== 将被删除的opportunities预览（前20条）===")
    for row in cursor.fetchall():
        logger.info(f"  Cluster {row[1]} ({row[2]}): {row[3]} (score: {row[4]})")

def show_keep_preview(conn, keep_ids):
    """显示将被保留的opportunities预览"""
    cursor = conn.execute("""
        SELECT
            o.id,
            o.cluster_id,
            c.cluster_name,
            o.opportunity_name,
            o.raw_total_score
        FROM opportunities o
        JOIN clusters c ON o.cluster_id = c.id
        WHERE o.id IN ({})
        ORDER BY c.cluster_name, o.raw_total_score DESC
        LIMIT 20
    """.format(','.join(map(str, keep_ids))))

    logger.info(f"\n=== 将被保留的opportunities预览（前20条）===")
    for row in cursor.fetchall():
        logger.info(f"  ✓ Cluster {row[1]} ({row[2]}): {row[3]} (score: {row[4]})")

def delete_duplicates(conn, keep_ids):
    """删除重复的opportunities"""
    # 使用参数化查询避免IN子句过长问题
    placeholders = ','.join('?' * len(keep_ids))

    cursor = conn.execute(f"""
        DELETE FROM opportunities
        WHERE id NOT IN ({placeholders})
    """, keep_ids)

    deleted_count = cursor.rowcount
    conn.commit()

    logger.info(f"已删除 {deleted_count} 条重复opportunities")
    return deleted_count

def verify_cleanup(conn):
    """验证清理结果"""
    cursor = conn.execute("""
        SELECT
            cluster_id,
            COUNT(*) as remaining_count
        FROM opportunities
        GROUP BY cluster_id
        HAVING COUNT(*) > 1
    """)

    remaining_duplicates = cursor.fetchall()

    if remaining_duplicates:
        logger.warning(f"⚠️  仍有 {len(remaining_duplicates)} 个cluster有重复opportunities")
        return False
    else:
        logger.info("✅ 所有重复opportunities已清理完成")
        return True

def main():
    """主函数"""
    logger.info(f"=== 开始清理重复opportunities ===")
    logger.info(f"数据库: {DB_PATH}")
    logger.info(f"时间: {datetime.now()}")

    conn = sqlite3.connect(DB_PATH)

    try:
        # 步骤1: 分析重复数据
        duplicates, total_to_delete = analyze_duplicates(conn)

        if not duplicates:
            logger.info("没有发现重复数据")
            return

        # 步骤2: 获取要保留的opportunity IDs
        keep_ids = get_keep_opportunity_ids(conn)

        # 步骤3: 显示预览
        show_keep_preview(conn, keep_ids)
        show_deletion_preview(conn, keep_ids)

        # 步骤4: 确认删除
        logger.info(f"\n⚠️  即将删除 {total_to_delete} 条opportunities")
        logger.info("请确认以上信息正确后，按Enter继续...")
        input()

        # 步骤5: 执行删除
        deleted_count = delete_duplicates(conn, keep_ids)

        # 步骤6: 验证
        verify_cleanup(conn)

        logger.info("=== 清理完成 ===")

    except Exception as e:
        logger.error(f"清理失败: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
