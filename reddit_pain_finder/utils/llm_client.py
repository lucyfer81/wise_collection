"""
LLM Client for Reddit Pain Point Finder
基于SiliconFlow API的LLM客户端
"""
import os
import json
import logging
import time
from typing import Dict, List, Any, Optional, Union
import yaml
from openai import OpenAI
import backoff
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

class LLMClient:
    """SiliconFlow LLM客户端"""

    def __init__(self, config_path: str = "config/llm.yaml"):
        """初始化LLM客户端"""
        self.config = self._load_config(config_path)
        self.client = self._init_client()
        self.stats = {
            "requests": 0,
            "tokens_used": 0,
            "cost": 0.0,
            "errors": 0
        }

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载LLM配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load LLM config from {config_path}: {e}")
            raise

    def _init_client(self) -> OpenAI:
        """初始化OpenAI客户端"""
        api_key = os.getenv(self.config['api']['api_key_env'])
        if not api_key:
            raise ValueError(f"API key not found in environment variable: {self.config['api']['api_key_env']}")

        return OpenAI(
            api_key=api_key,
            base_url=self.config['api']['base_url']
        )

    def get_model_name(self, model_type: str = "main") -> str:
        """获取指定类型的模型名称"""
        if model_type in self.config.get("models", {}):
            model_config = self.config["models"][model_type]
            # 如果有环境变量配置，优先使用
            env_name = model_config.get("env_name")
            if env_name and os.getenv(env_name):
                return os.getenv(env_name)
            return model_config["name"]

        # 从task_mapping中查找
        task_mapping = self.config.get("task_mapping", {})
        if model_type in task_mapping:
            mapped_model = task_mapping[model_type]["model"]
            return self.get_model_name(mapped_model)

        # 默认返回main模型
        return self.config["models"]["main"]["name"]

    def get_model_config(self, model_type: str = "main") -> Dict[str, Any]:
        """获取模型配置"""
        # 从task_mapping中查找
        task_mapping = self.config.get("task_mapping", {})
        if model_type in task_mapping:
            mapped_model = task_mapping[model_type]["model"]
            base_config = self.config["models"][mapped_model].copy()
            # 覆盖任务特定配置
            base_config.update(task_mapping[model_type])
            return base_config

        # 直接从models中查找
        if model_type in self.config.get("models", {}):
            return self.config["models"][model_type].copy()

        # 默认返回main模型配置
        return self.config["models"]["main"].copy()

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model_type: str = "main",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False
    ) -> Dict[str, Any]:
        """聊天补全请求"""

        max_retries = 5
        base_delay = 1
        max_delay = 120

        for attempt in range(max_retries):
            try:
                model_config = self.get_model_config(model_type)
                model_name = self.get_model_name(model_type)

                # 参数配置
                params = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature if temperature is not None else model_config.get("temperature", 0.1),
                    "max_tokens": max_tokens if max_tokens is not None else model_config.get("max_tokens", 2000),
                    "timeout": model_config.get("timeout", 180)
                }

                # JSON模式
                if json_mode:
                    params["response_format"] = {"type": "json_object"}

                # 记录请求开始时间
                start_time = time.time()

                logger.info(f"LLM Request {attempt + 1}/{max_retries}: model={model_name}, timeout={params['timeout']}s")

                # 发送请求
                response = self.client.chat.completions.create(**params)

                # 计算请求时间
                request_time = time.time() - start_time

                # 更新统计信息
                self.stats["requests"] += 1
                if hasattr(response.usage, 'total_tokens'):
                    self.stats["tokens_used"] += response.usage.total_tokens

                # 提取响应内容
                content = response.choices[0].message.content

                # 如果是JSON模式，尝试解析
                if json_mode:
                    try:
                        content = json.loads(content)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON response: {e}")
                        logger.error(f"Raw content: {content}")
                        # 尝试修复JSON
                        content = self._try_fix_json(content)

                result = {
                    "content": content,
                    "model": model_name,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                        "total_tokens": response.usage.total_tokens if response.usage else 0
                    },
                    "request_time": request_time
                }

                logger.info(f"✅ LLM request {attempt + 1}/{max_retries} completed: {result['usage']['total_tokens']} tokens in {request_time:.2f}s")
                return result

            except Exception as e:
                error_msg = f"❌ LLM request {attempt + 1}/{max_retries} failed: {e}"
                self.stats["errors"] += 1

                if attempt < max_retries - 1:
                    # 计算退避延迟
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(f"{error_msg} - Retrying in {delay:.2f}s...")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"{error_msg} - Max retries exceeded")
                    raise

    def _try_fix_json(self, content: str) -> Dict[str, Any]:
        """尝试修复损坏的JSON"""
        try:
            # 尝试提取JSON部分
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                return json.loads(json_str)
            else:
                raise ValueError("No JSON found in response")
        except Exception as e:
            logger.error(f"Failed to fix JSON: {e}")
            return {"error": "Failed to parse JSON", "raw_content": content}

    def extract_pain_points(
        self,
        title: str,
        body: str,
        subreddit: str,
        upvotes: int,
        comments_count: int,
        top_comments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """从Reddit帖子中提取痛点（支持评论上下文）"""
        prompt = self._get_pain_extraction_prompt()

        # Build user message with comment context
        user_message = f"""Title: {title}
Body: {body}
Subreddit: {subreddit}
Upvotes: {upvotes}
Comments: {comments_count}
"""

        # Add top comments if available
        if top_comments and len(top_comments) > 0:
            user_message += f"\nTop {len(top_comments)} Comments:\n"
            for i, comment in enumerate(top_comments, 1):
                comment_body = comment.get('body', '')
                comment_score = comment.get('score', 0)
                comment_author = comment.get('author', 'unknown')
                # Truncate very long comments to save tokens
                if len(comment_body) > 500:
                    comment_body = comment_body[:500] + "... [truncated]"
                user_message += f"\n{i}. [{comment_score} upvotes] {comment_author}: {comment_body}\n"

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message}
        ]

        return self.chat_completion(
            messages=messages,
            model_type="pain_extraction",
            json_mode=True
        )

    def cluster_pain_events(
        self,
        pain_events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """聚类痛点事件"""
        prompt = self._get_workflow_clustering_prompt()

        # 构建痛点事件文本
        events_text = "\n\n".join([
            f"Event {i+1}: {event.get('problem', '')} (Context: {event.get('context', '')}, Workaround: {event.get('current_workaround', '')})"
            for i, event in enumerate(pain_events)
        ])

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Pain events:\n{events_text}"}
        ]

        return self.chat_completion(
            messages=messages,
            model_type="clustering",
            json_mode=True
        )

    def summarize_source_cluster(
        self,
        pain_events: List[Dict[str, Any]],
        source_type: str
    ) -> Dict[str, Any]:
        """为同一source的聚类生成摘要"""
        prompt = self._get_cluster_summarizer_prompt()

        # 构建痛点事件文本，重点关注问题和上下文
        events_text = "\n\n".join([
            f"Event {i+1}:\nProblem: {event.get('problem', '')}\nContext: {event.get('context', '')}\nWorkaround: {event.get('current_workaround', '')}\n"
            for i, event in enumerate(pain_events[:10])  # 最多处理10个事件以控制token长度
        ])

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Source Type: {source_type}\n\nPain Events:\n{events_text}"}
        ]

        return self.chat_completion(
            messages=messages,
            model_type="cluster_summarizer",
            json_mode=True
        )

    def map_opportunity(
        self,
        cluster_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """从痛点聚类映射机会"""
        prompt = self._get_opportunity_mapping_prompt()

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Pain cluster:\n{json.dumps(cluster_summary, indent=2)}"}
        ]

        return self.chat_completion(
            messages=messages,
            model_type="opportunity_mapping",
            json_mode=True
        )

    def score_viability(
        self,
        opportunity_description: str
    ) -> Dict[str, Any]:
        """评估机会可行性"""
        prompt = self._get_viability_scoring_prompt()

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Idea:\n{opportunity_description}"}
        ]

        return self.chat_completion(
            messages=messages,
            model_type="viability_scoring",
            json_mode=True
        )

    def validate_pain_signal(
        self,
        text: str
    ) -> Dict[str, Any]:
        """验证痛点信号"""
        prompt = self._get_signal_validation_prompt()

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ]

        return self.chat_completion(
            messages=messages,
            model_type="signal_validation",
            json_mode=True
        )

    def _get_pain_extraction_prompt(self) -> str:
        """获取痛点抽取提示 - 支持评论上下文"""
        return """You are an information extraction engine specializing in user pain point analysis.

Your task:
From the provided Reddit post and its top comments, extract concrete PAIN EVENTS.

A pain event is a specific recurring problem experienced by users, supported by evidence from discussions.

Rules:
- Do NOT summarize the post
- Do NOT give advice
- If no concrete pain exists, return an empty list
- Be literal and conservative
- Focus on actionable problems people face repeatedly

**Using Comment Context:**
Top comments often reveal:
- Additional specific pain instances mentioned by others
- Confirmation/refinement of the main pain point
- Alternative perspectives on the same problem
- Workarounds people are actually using
- Frequency indicators (how often this occurs)

When extracting pain events:
1. Look for pains mentioned in BOTH the post AND comments
2. Use comments to add specificity to vague problems in the post
3. Include alternative formulations of the same pain
4. Note if multiple commenters confirm the same issue

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
      "confidence": 0.8,
      "evidence_sources": ["post", "comments"]  # where this pain was mentioned
    }
  ],
  "extraction_summary": "brief summary of findings"
}

Fields explanation:
- actor: who has this problem (developer, manager, user, etc.)
- context: the situation or workflow where the problem occurs
- problem: specific, concrete issue (e.g., "compilation takes 30 minutes" not "things are slow")
- current_workaround: current solutions people use (if mentioned)
- frequency: how often this happens (daily, weekly, occasionally, etc.)
- emotional_signal: the emotion expressed (frustration, anger, disappointment, etc.)
- mentioned_tools: tools, software, or methods explicitly mentioned
- confidence: how confident you are this is a real pain point (0-1)
- evidence_sources: list of where pain was found ("post", "comments", or both)

Be more confident when the same pain appears in both post and comments."""

    def _get_workflow_clustering_prompt(self) -> str:
        """Get workflow clustering prompt with continuous scoring"""
        return """You are analyzing user pain events.

Given the following pain events, rate how similar their UNDERLYING WORKFLOWS are on a continuous scale.

A workflow means:
- The same repeated activity
- Where different people fail in similar ways
- With similar root causes

Your task: Rate the workflow similarity from 0.0 to 1.0:
- 0.0 = Completely different workflows
- 0.3 = Some vague similarity but different core activities
- 0.5 = Partially similar with key differences
- 0.7 = Strong similarity with minor variations
- 1.0 = Identical workflows

If similarity >= 0.7:
- Give the workflow a short descriptive name
- Provide a brief description
- Explain your reasoning

If similarity < 0.7:
- Still provide a workflow name and description
- But note the key differences in reasoning

Return JSON only with this format:
{
  "workflow_similarity": 0.75,
  "workflow_name": "name of the workflow (even if low similarity)",
  "workflow_description": "description of what these events have in common",
  "confidence": 0.8,
  "reasoning": "brief explanation of your rating"
}

Be precise with your similarity score - use the full 0.0-1.0 range."""

    def _get_opportunity_mapping_prompt(self) -> str:
        """获取机会映射提示 - Phase 3 简化版（仅定性描述）"""
        return """You are a practical product thinker for solo founders.

Given a cluster of pain events from the same workflow:

1. Identify what tools people CURRENTLY use to cope with this problem
2. Identify what capability is MISSING that would solve it
3. Explain WHY existing tools fail (too complex, too expensive, wrong focus, etc.)
4. Propose ONE narrow micro-tool opportunity

Focus on:
- Specific, actionable problems with clear user context
- Narrow scope suitable for solo founder MVP (1-3 months)
- Concrete user needs, not abstract concepts

Rules:
- No platforms (unless you can justify the MVP scope)
- No marketplaces or two-sided markets
- If no viable tool opportunity exists, say so

Return JSON only with this format:
{
  "current_tools": ["tool1", "tool2", "manual methods"],
  "missing_capability": "what's missing that would solve this",
  "why_existing_fail": "why current solutions don't work well",
  "opportunity": {
    "name": "short descriptive name",
    "description": "what the micro-tool does in 1-2 sentences",
    "target_users": "who would use this (be specific about role/context)"
  }
}

NO quantitative scores - focus on clear, specific descriptions that capture the essence of the problem and solution."""

    def _get_viability_scoring_prompt(self) -> str:
        """获取可行性评分提示"""
        return """You are an experienced solo-founder investor.

Score the following idea for a ONE-PERSON COMPANY.

Criteria:
- Pain frequency: How often does this pain occur? (daily=10, rarely=1)
- Clear buyer: Can we easily identify who would pay? (clear=10, vague=1)
- MVP buildable: Can one person build MVP in 1-3 months? (easy=10, hard=1)
- Crowded market: How competitive is this space? (empty=10, saturated=1)
- Integration: How easy to integrate with existing tools? (easy=10, hard=1)

Score each criteria 0-10, then calculate total score.

Also list the TOP 3 killer risks that could kill this project.

Return JSON only with this format:
{
  "scores": {
    "pain_frequency": 8,
    "clear_buyer": 7,
    "mvp_buildable": 6,
    "crowded_market": 5,
    "integration": 7
  },
  "total_score": 6.6,
  "killer_risks": [
    "Risk 1: specific and concrete",
    "Risk 2: specific and concrete",
    "Risk 3: specific and concrete"
  ],
  "recommendation": "pursue/modify/abandon with brief reason"
}

Be realistic and conservative in scoring."""

    def _get_cluster_summarizer_prompt(self) -> str:
        """获取聚类摘要提示"""
        return """You are a cluster summarizer for pain events.

These pain events come from the same source and discourse style.
Your task is to summarize the SHARED UNDERLYING PROBLEM, ignoring emotional tone and individual details.

Focus on:
1. What is the common problem across all these events?
2. What shared context or workflow is involved?
3. What is the essential pain point, stripped of emotional language?
4. Provide 2-3 representative examples that capture the essence

BE CONSERVATIVE - only identify patterns that truly exist across multiple events.

Return JSON only with this format:
{
  "centroid_summary": "brief summary of the core shared problem",
  "common_pain": "the main difficulty or challenge (technical language)",
  "common_context": "the shared workflow or situation where this occurs",
  "example_events": [
    "Event 1: representative problem description",
    "Event 2: representative problem description"
  ],
  "coherence_score": 0.8,  # how well do these events belong together (0-1)
  "reasoning": "brief explanation of why these belong together"
}

Do not exaggerate similarities. Be literal and precise."""

    def _get_signal_validation_prompt(self) -> str:
        """获取信号验证提示"""
        return """You are a pain signal validator.

Given this text, determine if it contains a genuine pain point.

A genuine pain point:
- Describes a specific problem or difficulty
- Shows frustration or struggle
- Is not just venting or seeking help
- Represents a recurring issue

Return JSON only with this format:
{
  "is_pain_point": true/false,
  "confidence": 0.8,
  "pain_type": "frustration/inefficiency/complexity/workflow/cost/other",
  "specificity": 0.9,  # How specific is the problem (0-1)
  "emotional_intensity": 0.7,  # How strong is the emotion (0-1)
  "keywords": ["struggling", "frustrated", "can't figure out"]
}

Be conservative - only flag clear pain points."""

    def get_statistics(self) -> Dict[str, Any]:
        """获取使用统计"""
        return self.stats.copy()

    def reset_statistics(self):
        """重置统计"""
        self.stats = {
            "requests": 0,
            "tokens_used": 0,
            "cost": 0.0,
            "errors": 0
        }

# 全局LLM客户端实例
llm_client = LLMClient()