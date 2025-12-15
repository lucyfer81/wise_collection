"""
Embedding utilities for Reddit Pain Point Finder
向量化工具，用于痛点事件聚类
"""
import os
import logging
import pickle
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import DBSCAN
import yaml
from openai import OpenAI
import backoff

logger = logging.getLogger(__name__)

class EmbeddingClient:
    """嵌入向量客户端"""

    def __init__(self, config_path: str = "config/llm.yaml"):
        """初始化嵌入客户端"""
        self.config = self._load_config(config_path)
        self.client = self._init_client()
        self.model_name = self._get_model_name()
        self.embedding_cache = {}
        self.stats = {
            "embeddings_created": 0,
            "cache_hits": 0,
            "total_tokens": 0
        }

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            raise

    def _init_client(self) -> OpenAI:
        """初始化OpenAI客户端"""
        api_key = os.getenv(self.config['api']['api_key_env'])
        if not api_key:
            raise ValueError(f"API key not found: {self.config['api']['api_key_env']}")

        return OpenAI(
            api_key=api_key,
            base_url=self.config['api']['base_url']
        )

    def _get_model_name(self) -> str:
        """获取嵌入模型名称"""
        embedding_config = self.config.get("embedding", {})
        env_name = embedding_config.get("env_name")
        if env_name and os.getenv(env_name):
            return os.getenv(env_name)
        return embedding_config.get("model", "text-embedding-ada-002")

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        base=1,
        max_value=60
    )
    def create_embedding(self, text: str) -> List[float]:
        """创建文本嵌入向量"""
        try:
            # 检查缓存
            if text in self.embedding_cache:
                self.stats["cache_hits"] += 1
                return self.embedding_cache[text]

            # 调用API
            response = self.client.embeddings.create(
                model=self.model_name,
                input=text
            )

            embedding = response.data[0].embedding

            # 更新统计
            self.stats["embeddings_created"] += 1
            self.stats["total_tokens"] += response.usage.total_tokens

            # 缓存结果
            self.embedding_cache[text] = embedding

            logger.info(f"Created embedding for text length {len(text)}: {len(embedding)} dimensions")
            return embedding

        except Exception as e:
            logger.error(f"Failed to create embedding: {e}")
            raise

    def create_batch_embeddings(self, texts: List[str], batch_size: int = None) -> List[List[float]]:
        """批量创建嵌入向量"""
        if batch_size is None:
            batch_size = self.config.get("embedding", {}).get("batch_size", 32)

        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}/{(len(texts) + batch_size - 1)//batch_size}")

            for text in batch:
                embedding = self.create_embedding(text)
                embeddings.append(embedding)

        return embeddings

    def create_pain_event_embedding(self, pain_event: Dict[str, Any]) -> List[float]:
        """为痛点事件创建嵌入向量"""
        # 构建嵌入文本，重点关注问题的本质
        text_parts = []

        if pain_event.get("actor"):
            text_parts.append(pain_event["actor"])

        if pain_event.get("context"):
            text_parts.append(pain_event["context"])

        if pain_event.get("problem"):
            text_parts.append(pain_event["problem"])

        if pain_event.get("current_workaround"):
            text_parts.append(pain_event["current_workaround"])

        # 用 " | " 连接各个部分，保持语义结构
        embedding_text = " | ".join(text_parts)

        return self.create_embedding(embedding_text)

    def calculate_similarity_matrix(self, embeddings: List[List[float]]) -> np.ndarray:
        """计算相似度矩阵"""
        return cosine_similarity(embeddings)

    def find_similar_events(
        self,
        target_embedding: List[float],
        candidate_embeddings: List[List[float]],
        threshold: float = 0.7,
        top_k: int = 10
    ) -> List[Tuple[int, float]]:
        """找到相似的痛点事件"""
        similarities = cosine_similarity([target_embedding], candidate_embeddings)[0]

        # 筛选超过阈值的结果
        results = []
        for idx, similarity in enumerate(similarities):
            if similarity >= threshold:
                results.append((idx, similarity))

        # 按相似度排序，返回top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def cluster_embeddings(
        self,
        embeddings: List[List[float]],
        eps: float = 0.5,
        min_samples: int = 3
    ) -> Dict[int, List[int]]:
        """使用DBSCAN聚类嵌入向量"""
        if len(embeddings) < min_samples:
            return {0: list(range(len(embeddings)))}  # 如果样本太少，归为一类

        dbscan = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
        cluster_labels = dbscan.fit_predict(embeddings)

        # 构建聚类字典
        clusters = {}
        for idx, label in enumerate(cluster_labels):
            if label == -1:  # 噪声点
                continue
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(idx)

        return clusters

    def analyze_cluster(
        self,
        cluster_indices: List[int],
        embeddings: List[List[float]],
        pain_events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """分析一个聚类"""
        if not cluster_indices:
            return {}

        # 计算聚类中心
        cluster_embeddings = [embeddings[i] for i in cluster_indices]
        centroid = np.mean(cluster_embeddings, axis=0)

        # 计算每个点到中心的距离
        distances_to_center = [
            1 - cosine_similarity([embeddings[i]], [centroid])[0][0]
            for i in cluster_indices
        ]

        # 计算聚类的内聚性（平均距离）
        cohesion = 1 - np.mean(distances_to_center)

        # 获取该聚类的痛点事件
        cluster_events = [pain_events[i] for i in cluster_indices]

        return {
            "size": len(cluster_indices),
            "centroid": centroid.tolist(),
            "cohesion": cohesion,
            "events": cluster_events,
            "avg_distance_to_center": np.mean(distances_to_center),
            "max_distance_to_center": np.max(distances_to_center)
        }

    def get_embedding_statistics(self) -> Dict[str, Any]:
        """获取嵌入统计信息"""
        return self.stats.copy()

    def save_embedding_cache(self, cache_path: str):
        """保存嵌入缓存"""
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(self.embedding_cache, f)
            logger.info(f"Saved embedding cache to {cache_path}")
        except Exception as e:
            logger.error(f"Failed to save embedding cache: {e}")

    def load_embedding_cache(self, cache_path: str):
        """加载嵌入缓存"""
        try:
            if os.path.exists(cache_path):
                with open(cache_path, 'rb') as f:
                    self.embedding_cache = pickle.load(f)
                logger.info(f"Loaded embedding cache from {cache_path}: {len(self.embedding_cache)} entries")
        except Exception as e:
            logger.error(f"Failed to load embedding cache: {e}")

class PainEventClustering:
    """痛点事件聚类工具"""

    def __init__(self, embedding_client: EmbeddingClient):
        """初始化聚类工具"""
        self.embedding_client = embedding_client
        self.clustering_config = self._load_clustering_config()

    def _load_clustering_config(self) -> Dict[str, Any]:
        """加载聚类配置"""
        try:
            config_path = "config/clustering.yaml"
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            logger.error(f"Failed to load clustering config: {e}")
            # 返回默认配置
            return {
                "vector_similarity": {"similarity_threshold": 0.8, "top_k": 10},
                "dbscan": {"eps": 0.3, "min_samples": 2},
                "llm_validation": {"max_events_per_validation": 10, "confidence_threshold": 0.7},
                "post_processing": {"min_cluster_size": 2, "max_cluster_size": 15}
            }

    def cluster_pain_events(self, pain_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """聚类痛点事件"""
        if len(pain_events) < 2:
            return []

        logger.info(f"Clustering {len(pain_events)} pain events")

        # 1. 创建嵌入向量
        logger.info("Creating embeddings for pain events...")
        embeddings = []
        for event in pain_events:
            embedding = self.embedding_client.create_pain_event_embedding(event)
            embeddings.append(embedding)

        # 2. 使用向量相似度进行初步聚类
        logger.info("Performing vector similarity clustering...")
        similarity_threshold = self.clustering_config.get(
            "vector_similarity", {}
        ).get("similarity_threshold", 0.7)

        dbscan_eps = self.clustering_config.get(
            "dbscan", {}
        ).get("eps", 0.5)
        min_samples = self.clustering_config.get(
            "dbscan", {}
        ).get("min_samples", 3)

        # DBSCAN聚类
        clusters = self.embedding_client.cluster_embeddings(
            embeddings, eps=dbscan_eps, min_samples=min_samples
        )

        # 3. 分析每个聚类
        logger.info(f"Found {len(clusters)} clusters")
        cluster_results = []

        for cluster_id, indices in clusters.items():
            if len(indices) < 2:  # 跳过单个事件的聚类
                continue

            cluster_analysis = self.embedding_client.analyze_cluster(
                indices, embeddings, pain_events
            )

            cluster_result = {
                "cluster_id": cluster_id,
                "pain_event_ids": indices,
                "cluster_size": len(indices),
                "cohesion": cluster_analysis["cohesion"],
                "events": cluster_analysis["events"]
            }

            cluster_results.append(cluster_result)

        # 按聚类大小排序
        cluster_results.sort(key=lambda x: x["cluster_size"], reverse=True)

        logger.info(f"Successfully created {len(cluster_results)} clusters")
        return cluster_results

    def find_similar_events(
        self,
        target_event: Dict[str, Any],
        candidate_events: List[Dict[str, Any]],
        threshold: float = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """找到与目标事件相似的候选事件"""
        if threshold is None:
            threshold = self.clustering_config.get(
                "vector_similarity", {}
            ).get("similarity_threshold", 0.7)

        # 创建目标事件的嵌入
        target_embedding = self.embedding_client.create_pain_event_embedding(target_event)

        # 创建候选事件的嵌入
        candidate_embeddings = []
        for event in candidate_events:
            embedding = self.embedding_client.create_pain_event_embedding(event)
            candidate_embeddings.append(embedding)

        # 找到相似事件
        similar_indices = self.embedding_client.find_similar_events(
            target_embedding, candidate_embeddings, threshold, top_k
        )

        # 返回相似事件及其相似度
        results = []
        for idx, similarity in similar_indices:
            result = candidate_events[idx].copy()
            result["similarity_score"] = similarity
            results.append(result)

        return results

# 全局嵌入客户端实例
embedding_client = EmbeddingClient()
pain_clustering = PainEventClustering(embedding_client)