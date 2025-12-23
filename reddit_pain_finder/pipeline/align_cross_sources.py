"""
跨源对齐模块
Cross-Source Alignment Module
"""
import json
import time
from typing import List, Dict, Any, Optional
from utils.db import WiseCollectionDB
from utils.llm_client import LLMClient
import logging

logger = logging.getLogger(__name__)

class CrossSourceAligner:
    """跨源对齐器 - 识别不同社区讨论的同一问题"""

    def __init__(self, db: WiseCollectionDB, llm_client: LLMClient):
        self.db = db
        self.llm_client = llm_client

    def get_unprocessed_clusters(self) -> List[Dict]:
        """获取未处理的聚类数据"""
        try:
            with self.db.get_connection("clusters") as conn:
                cursor = conn.execute("""
                    SELECT cluster_name, source_type, centroid_summary,
                           common_pain, pain_event_ids, cluster_size
                    FROM clusters
                    WHERE alignment_status = 'unprocessed'
                    AND cluster_size >= 3
                    ORDER BY cluster_size DESC
                """)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get unprocessed clusters: {e}")
            return []

    def prepare_cluster_for_alignment(self, cluster: Dict) -> Dict:
        """为LLM对齐准备聚类数据"""
        try:
            # 提取workaround信息
            typical_workaround = self._extract_workarounds(cluster["common_pain"])

            return {
                "source_type": cluster["source_type"],
                "cluster_summary": cluster["centroid_summary"],
                "typical_workaround": typical_workaround,
                "context": f"Cluster size: {cluster['cluster_size']}, "
                          f"Pain events: {len(json.loads(cluster['pain_event_ids']))}"
            }
        except Exception as e:
            logger.error(f"Failed to prepare cluster {cluster.get('cluster_name')}: {e}")
            return {}

    def align_clusters_across_sources(self, clusters: List[Dict]) -> List[Dict]:
        """使用LLM跨源对齐聚类"""
        if len(clusters) < 2:
            logger.info("Not enough clusters for cross-source alignment")
            return []

        try:
            # 按源类型分组
            source_groups = {}
            for cluster in clusters:
                source_type = cluster["source_type"]
                if source_type not in source_groups:
                    source_groups[source_type] = []

                prepared_cluster = self.prepare_cluster_for_alignment(cluster)
                if prepared_cluster:  # Only add if preparation succeeded
                    source_groups[source_type].append(prepared_cluster)

            # 跳过如果只有一种源类型
            if len(source_groups) < 2:
                logger.info("Only one source type found, skipping cross-source alignment")
                return []

            # 构建对齐prompt
            alignment_prompt = self._build_alignment_prompt(source_groups)

            # 调用LLM
            logger.info(f"Running cross-source alignment for {len(source_groups)} source types")
            messages = [{"role": "user", "content": alignment_prompt}]
            response = self.llm_client.chat_completion(
                messages=messages,
                model_type="main",
                max_tokens=2000,
                temperature=0.1
            )

            # 解析响应 - chat_completion返回字典格式
            if isinstance(response, dict):
                response_content = response.get('content', '')
            else:
                response_content = str(response)

            alignments = self._parse_alignment_response(response_content, clusters)
            logger.info(f"Found {len(alignments)} cross-source alignments")

            return alignments

        except Exception as e:
            logger.error(f"Failed to align clusters across sources: {e}")
            return []

    def _extract_workarounds(self, common_pain: str) -> str:
        """从common_pain中提取workaround信息"""
        # 简单实现：如果提到workaround或solution，提取相关部分
        if not common_pain:
            return "No specific workaround mentioned"

        # 查找包含workaround、solution等关键词的句子
        pain_lower = common_pain.lower()
        workaround_keywords = ['workaround', 'solution', 'fix', 'solve', 'currently using', 'temporary']

        for keyword in workaround_keywords:
            if keyword in pain_lower:
                # 返回包含关键词的部分文本
                sentences = common_pain.split('.')
                for sentence in sentences:
                    if keyword in sentence.lower():
                        return sentence.strip()

        return "No explicit workaround mentioned"

    def _build_alignment_prompt(self, source_groups: Dict) -> str:
        """构建跨源对齐的LLM prompt"""
        prompt = """You are analyzing problem summaries from different online communities to identify when they're discussing the same underlying issue.

You will receive multiple problem clusters grouped by community type:
"""

        # 添加每个源组
        for source_type, clusters in source_groups.items():
            prompt += f"\n## {source_type.upper()} Communities:\n\n"
            for i, cluster in enumerate(clusters, 1):
                prompt += f"Cluster {i}:\n"
                prompt += f"- Summary: {cluster['cluster_summary']}\n"
                prompt += f"- Typical workaround: {cluster['typical_workaround']}\n"
                prompt += f"- Context: {cluster['context']}\n\n"

        prompt += """
## Task

Identify which clusters from different communities describe the SAME underlying problem.

Rules:
1. Ignore differences in tone, maturity level, or solution sophistication
2. Focus on the core problem being described
3. Consider workarounds and context as evidence
4. Only align clusters from DIFFERENT source types
5. Be conservative - only align when you're confident it's the same problem

## Output Format

For each alignment discovered, output a JSON object with this structure:
{
  "aligned_problem_id": "AP_XX",
  "sources": ["source_type_1", "source_type_2"],
  "core_problem": "Clear description of the shared underlying problem",
  "why_they_look_different": "Explanation of how the same problem appears different across communities",
  "evidence": [
    {
      "source": "hn_ask",
      "cluster_summary": "...",
      "evidence_quote": "Specific evidence from the cluster summary"
    },
    {
      "source": "reddit",
      "cluster_summary": "...",
      "evidence_quote": "Specific evidence from the cluster summary"
    }
  ],
  "original_cluster_ids": ["cluster_id_1", "cluster_id_2"]
}

Return only valid JSON arrays of alignment objects. If no alignments exist, return an empty array.
"""

        return prompt

    def _parse_alignment_response(self, response: str, original_clusters: List[Dict]) -> List[Dict]:
        """解析LLM响应为对齐问题"""
        try:
            # 提取JSON部分
            json_start = response.find('[')
            json_end = response.rfind(']') + 1

            if json_start == -1 or json_end == 0:
                logger.warning("No JSON array found in alignment response")
                return []

            json_str = response[json_start:json_end]
            alignments = json.loads(json_str)

            # 验证和丰富对齐结果
            validated_alignments = []

            for alignment in alignments:
                # 验证必需字段
                required_fields = [
                    'aligned_problem_id', 'sources', 'core_problem',
                    'why_they_look_different', 'evidence'
                ]

                if not all(field in alignment for field in required_fields):
                    logger.warning(f"Alignment missing required fields: {alignment}")
                    continue

                # 处理cluster_ids字段
                if 'original_cluster_ids' not in alignment:
                    alignment['cluster_ids'] = []
                else:
                    alignment['cluster_ids'] = alignment['original_cluster_ids']

                # 验证sources格式
                if not isinstance(alignment['sources'], list) or len(alignment['sources']) < 2:
                    logger.warning(f"Invalid sources in alignment: {alignment['sources']}")
                    continue

                validated_alignments.append(alignment)

            return validated_alignments

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error parsing alignment response: {e}")
            return []

    def process_alignments(self):
        """处理所有跨源对齐的主要方法"""
        logger.info("Starting cross-source alignment...")

        # 获取未处理的聚类
        clusters = self.get_unprocessed_clusters()
        logger.info(f"Found {len(clusters)} clusters to analyze")

        if not clusters:
            logger.info("No unprocessed clusters found")
            return

        # 执行对齐
        alignments = self.align_clusters_across_sources(clusters)
        logger.info(f"Found {len(alignments)} cross-source alignments")

        # 保存对齐结果到数据库
        for alignment in alignments:
            try:
                # 生成唯一ID
                alignment['id'] = f"aligned_{alignment['aligned_problem_id']}_{int(time.time())}"

                # 插入对齐问题
                self._insert_aligned_problem(alignment)

                # 更新聚类状态
                for cluster_id in alignment['cluster_ids']:
                    self._update_cluster_alignment_status(
                        cluster_id,
                        'aligned',
                        alignment['aligned_problem_id']
                    )

            except Exception as e:
                logger.error(f"Failed to save alignment {alignment.get('aligned_problem_id')}: {e}")

        # 标记剩余聚类为已处理但未对齐
        aligned_cluster_ids = []
        for alignment in alignments:
            aligned_cluster_ids.extend(alignment['cluster_ids'])

        for cluster in clusters:
            if cluster['cluster_name'] not in aligned_cluster_ids:
                try:
                    self._update_cluster_alignment_status(
                        cluster['cluster_name'],
                        'processed',
                        None
                    )
                except Exception as e:
                    logger.error(f"Failed to update cluster {cluster['cluster_name']}: {e}")

        logger.info("Cross-source alignment completed!")

    def _insert_aligned_problem(self, alignment_data: Dict):
        """插入对齐问题到数据库"""
        try:
            self.db.insert_aligned_problem(alignment_data)
        except Exception as e:
            logger.error(f"Failed to insert aligned problem: {e}")
            raise

    def _update_cluster_alignment_status(self, cluster_name: str, status: str, aligned_problem_id: str = None):
        """更新聚类对齐状态"""
        try:
            self.db.update_cluster_alignment_status(cluster_name, status, aligned_problem_id)
        except Exception as e:
            logger.error(f"Failed to update cluster alignment status: {e}")
            raise