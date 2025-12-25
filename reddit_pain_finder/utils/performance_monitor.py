"""
Performance monitoring utility for Phase 3
Tracks LLM calls, token usage, and execution time
"""
import time
import json
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from functools import wraps
import logging

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.metrics = {
            "start_time": None,
            "end_time": None,
            "stages": {},
            "llm_calls": {
                "total_calls": 0,
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_cost": 0.0,
                "calls_by_stage": {}
            }
        }

    def start_stage(self, stage_name: str):
        """开始一个阶段"""
        if stage_name not in self.metrics["stages"]:
            self.metrics["stages"][stage_name] = {
                "start_time": datetime.now().isoformat(),
                "end_time": None,
                "duration_seconds": 0,
                "items_processed": 0,
                "llm_calls": 0,
                "tokens_used": 0
            }
        else:
            self.metrics["stages"][stage_name]["start_time"] = datetime.now().isoformat()

    def end_stage(self, stage_name: str, items_processed: int = 0):
        """结束一个阶段"""
        if stage_name in self.metrics["stages"]:
            self.metrics["stages"][stage_name]["end_time"] = datetime.now().isoformat()
            start = datetime.fromisoformat(self.metrics["stages"][stage_name]["start_time"])
            end = datetime.fromisoformat(self.metrics["stages"][stage_name]["end_time"])
            self.metrics["stages"][stage_name]["duration_seconds"] = (end - start).total_seconds()
            self.metrics["stages"][stage_name]["items_processed"] = items_processed

    def record_llm_call(self, stage_name: str, usage: Dict[str, Any]):
        """记录LLM调用"""
        self.metrics["llm_calls"]["total_calls"] += 1

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        self.metrics["llm_calls"]["prompt_tokens"] += prompt_tokens
        self.metrics["llm_calls"]["completion_tokens"] += completion_tokens
        self.metrics["llm_calls"]["total_tokens"] += total_tokens

        if stage_name not in self.metrics["llm_calls"]["calls_by_stage"]:
            self.metrics["llm_calls"]["calls_by_stage"][stage_name] = {"calls": 0, "tokens": 0}

        self.metrics["llm_calls"]["calls_by_stage"][stage_name]["calls"] += 1
        self.metrics["llm_calls"]["calls_by_stage"][stage_name]["tokens"] += total_tokens

        if stage_name in self.metrics["stages"]:
            self.metrics["stages"][stage_name]["llm_calls"] += 1
            self.metrics["stages"][stage_name]["tokens_used"] += total_tokens

    def calculate_cost(self, prompt_price_per_1k: float = 0.001,
                      completion_price_per_1k: float = 0.002):
        """计算成本（根据实际定价调整）"""
        prompt_cost = (self.metrics["llm_calls"]["prompt_tokens"] / 1000) * prompt_price_per_1k
        completion_cost = (self.metrics["llm_calls"]["completion_tokens"] / 1000) * completion_price_per_1k
        self.metrics["llm_calls"]["total_cost"] = prompt_cost + completion_cost
        return self.metrics["llm_calls"]["total_cost"]

    def get_summary(self) -> Dict[str, Any]:
        """获取统计摘要"""
        if self.metrics["stages"]:
            total_duration = sum(stage["duration_seconds"] for stage in self.metrics["stages"].values())
        else:
            total_duration = 0

        return {
            "total_duration_seconds": total_duration,
            "total_duration_minutes": round(total_duration / 60, 2),
            "total_llm_calls": self.metrics["llm_calls"]["total_calls"],
            "total_tokens": self.metrics["llm_calls"]["total_tokens"],
            "estimated_cost_usd": self.calculate_cost(),
            "stages_summary": {
                name: {
                    "duration_seconds": stage["duration_seconds"],
                    "items_processed": stage["items_processed"],
                    "llm_calls": stage["llm_calls"],
                    "tokens_used": stage["tokens_used"]
                }
                for name, stage in self.metrics["stages"].items()
            }
        }

    def save_metrics(self, filepath: str):
        """保存指标到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.metrics, f, indent=2, default=str)

    @classmethod
    def load_metrics(cls, filepath: str) -> 'PerformanceMonitor':
        """从文件加载指标"""
        monitor = cls()
        with open(filepath, 'r', encoding='utf-8') as f:
            monitor.metrics = json.load(f)
        return monitor


# 全局监控器实例
performance_monitor = PerformanceMonitor()
