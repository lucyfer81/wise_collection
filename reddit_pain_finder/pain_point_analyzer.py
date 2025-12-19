#!/usr/bin/env python3
"""
痛点应用分析器

针对每个痛点聚类生成综合分析报告，包含：
1. 痛点分析
2. 应用设计方案
3. 可执行机会清单

每个聚类生成一个独立的markdown文件
"""

import os
import sqlite3
import json
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional
import re
from pathlib import Path
import logging
import sys

# 导入统一数据库管理器
try:
    from utils.db import WiseCollectionDB
except ImportError as e:
    print(f"❌ 无法导入数据库管理器: {e}")
    sys.exit(1)

# 加载.env文件
def load_env():
    """加载.env文件"""
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # 输出到控制台
        logging.FileHandler('pain_point_analyzer.log', encoding='utf-8')  # 同时输出到文件
    ]
)

logger = logging.getLogger(__name__)

# 加载环境变量
logger.info("开始加载环境变量...")
load_env()
logger.info("环境变量加载完成")


class PainPointAnalyzer:
    def __init__(self, unified_db: bool = True):
        """初始化分析器"""
        logger.info("初始化 PainPointAnalyzer...")

        # 初始化统一数据库管理器
        logger.info("初始化数据库管理器...")
        self.db = WiseCollectionDB(unified=unified_db)
        self.unified_db = unified_db

        if unified_db:
            logger.info(f"使用统一数据库模式: {self.db.get_database_path()}")
        else:
            logger.info("使用多数据库模式")

        self.base_url = os.getenv('Siliconflow_Base_URL', 'https://api.siliconflow.cn/v1')
        self.api_key = os.getenv('Siliconflow_KEY')
        self.model = os.getenv('Siliconflow_AI_Model_Default', 'deepseek-ai/DeepSeek-V3.2')

        logger.info(f"配置信息: base_url={self.base_url}, model={self.model}")
        logger.info(f"API key {'已设置' if self.api_key else '未设置'}")

        if not self.api_key:
            logger.error("SiliconFlow API key not found in environment variables")
            raise ValueError("SiliconFlow API key not found in environment variables")

        # 创建输出目录
        self.output_dir = "pain_analysis_reports"
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info(f"输出目录已创建: {self.output_dir}")

        print(f"🔧 初始化分析器")
        print(f"   • 数据库模式: {'统一数据库' if unified_db else '多数据库文件'}")
        if unified_db:
            print(f"   • 数据库路径: {self.db.get_database_path()}")
        print(f"   • API模型: {self.model}")
        print(f"   • 输出目录: {self.output_dir}")

    def get_db_connection(self, db_type: str = "clusters"):
        """获取数据库连接 - 使用统一数据库管理器"""
        logger.debug(f"获取数据库连接，类型: {db_type}")
        return self.db.get_connection(db_type)

    def call_llm(self, prompt: str, temperature: float = 0.3, max_retries: int = 3) -> str:
        """调用LLM"""
        logger.info(f"开始调用LLM: model={self.model}, temperature={temperature}, max_retries={max_retries}")
        logger.debug(f"prompt长度: {len(prompt)} 字符")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一位资深的产品分析师和技术顾问，专门分析用户痛点并设计创新的解决方案。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": 4000
        }

        for attempt in range(max_retries):
            try:
                print(f"  🤖 调用LLM (尝试 {attempt + 1}/{max_retries})...")
                logger.info(f"尝试第 {attempt + 1}/{max_retries} 次LLM调用")

                url = f"{self.base_url}/chat/completions"
                logger.debug(f"请求URL: {url}")

                response = requests.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=180  # 增加到3分钟
                )

                logger.debug(f"响应状态码: {response.status_code}")

                response.raise_for_status()
                result = response.json()

                if 'choices' not in result or len(result['choices']) == 0:
                    logger.error("LLM响应中没有choices字段")
                    return "LLM响应格式错误: 没有choices"

                content = result['choices'][0]['message']['content'].strip()
                logger.debug(f"LLM响应长度: {len(content)} 字符")
                print(f"  ✅ LLM响应成功")
                logger.info("LLM调用成功")
                return content

            except requests.exceptions.Timeout:
                error_msg = f"LLM调用超时 (尝试 {attempt + 1}/{max_retries})"
                logger.warning(error_msg)
                print(f"  ⚠️ {error_msg}")
                if attempt < max_retries - 1:
                    continue
                logger.error(f"LLM调用超时，已重试{max_retries}次")
                return f"LLM调用超时: 已重试{max_retries}次"

            except requests.exceptions.HTTPError as e:
                error_msg = f"HTTP错误: {e}"
                logger.error(error_msg)
                logger.error(f"响应内容: {response.text if 'response' in locals() else 'N/A'}")
                print(f"  ❌ {error_msg}")
                if attempt < max_retries - 1:
                    print(f"  🔄 正在重试...")
                    continue
                return f"LLM HTTP错误: {str(e)}"

            except Exception as e:
                error_msg = f"LLM调用失败: {e}"
                logger.error(error_msg)
                import traceback
                logger.error(traceback.format_exc())
                print(f"  ❌ {error_msg}")
                if attempt < max_retries - 1:
                    print(f"  🔄 正在重试...")
                    continue
                return f"LLM调用失败: {str(e)}"

    def get_top_clusters(self, min_score: float = 0.8, limit: int = 10) -> List[Dict]:
        """获取高分聚类 - 使用统一数据库"""
        logger.info(f"获取高分聚类: min_score={min_score}, limit={limit}")
        clusters = []

        try:
            with self.get_db_connection("clusters") as conn:
                cursor = conn.cursor()

                logger.debug("执行聚类查询SQL...")

                cursor.execute("""
                    SELECT c.id, c.cluster_name, c.cluster_description, c.avg_pain_score,
                           c.cluster_size, c.pain_event_ids,
                           COUNT(o.id) as opportunity_count,
                           MAX(o.total_score) as max_opportunity_score,
                           GROUP_CONCAT(o.opportunity_name, ' | ') as opportunity_names
                    FROM clusters c
                    LEFT JOIN opportunities o ON c.id = o.cluster_id
                    GROUP BY c.id
                    HAVING opportunity_count > 0 AND max_opportunity_score >= ?
                    ORDER BY max_opportunity_score DESC, c.avg_pain_score DESC
                    LIMIT ?
                """, (min_score, limit))

                logger.debug(f"查询执行完成，开始处理结果...")
                rows = cursor.fetchall()
                logger.info(f"查询到 {len(rows)} 个聚类")

                for i, row in enumerate(rows, 1):
                    logger.debug(f"处理第 {i}/{len(rows)} 个聚类: {row['cluster_name'][:50]}...")
                    # 获取该聚类的所有机会
                    logger.debug(f"获取聚类 {row['id']} 的机会数据...")
                    cursor.execute("""
                        SELECT opportunity_name, description, total_score, recommendation,
                               current_tools, missing_capability, why_existing_fail,
                               target_users, killer_risks
                        FROM opportunities
                        WHERE cluster_id = ?
                        ORDER BY total_score DESC
                    """, (row['id'],))

                    opportunities = []
                    opp_rows = cursor.fetchall()
                    logger.debug(f"聚类 {row['id']} 有 {len(opp_rows)} 个机会")

                    for opp_row in opp_rows:
                        opportunities.append({
                            'name': opp_row['opportunity_name'],
                            'description': opp_row['description'],
                            'score': opp_row['total_score'],
                            'recommendation': opp_row['recommendation'],
                            'current_tools': opp_row['current_tools'],
                            'missing_capability': opp_row['missing_capability'],
                            'why_existing_fail': opp_row['why_existing_fail'],
                            'target_users': opp_row['target_users'],
                            'killer_risks': json.loads(opp_row['killer_risks']) if opp_row['killer_risks'] else []
                        })

                    # 获取痛点事件样本
                    try:
                        pain_event_ids = json.loads(row['pain_event_ids'])
                        logger.debug(f"聚类 {row['id']} 痛点事件IDs: {len(pain_event_ids)} 个")
                        sample_pains = self.get_sample_pain_events(pain_event_ids[:5])
                    except json.JSONDecodeError as e:
                        logger.warning(f"聚类 {row['id']} pain_event_ids JSON解析失败: {e}")
                        sample_pains = []

                    clusters.append({
                        'id': row['id'],
                        'name': row['cluster_name'],
                        'description': row['cluster_description'],
                        'avg_pain_score': row['avg_pain_score'],
                        'cluster_size': row['cluster_size'],
                        'opportunity_count': row['opportunity_count'],
                        'max_opportunity_score': row['max_opportunity_score'],
                        'opportunities': opportunities,
                        'sample_pains': sample_pains
                    })

            logger.info(f"成功获取 {len(clusters)} 个聚类数据")
            return clusters

        except Exception as e:
            logger.error(f"获取聚类数据失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def get_sample_pain_events(self, pain_event_ids: List[int]) -> List[Dict]:
        """获取痛点事件样本 - 使用统一数据库"""
        logger.debug(f"获取 {len(pain_event_ids)} 个痛点事件样本: {pain_event_ids}")
        pains = []

        if not pain_event_ids:
            logger.warning("pain_event_ids 为空，返回空列表")
            return []

        try:
            with self.get_db_connection("pain") as conn:
                cursor = conn.cursor()

                placeholders = ','.join(['?' for _ in pain_event_ids])
                logger.debug(f"执行痛点事件查询，IDs: {pain_event_ids}")

                cursor.execute(f"""
                    SELECT problem, current_workaround, frequency, emotional_signal, mentioned_tools
                    FROM pain_events
                    WHERE id IN ({placeholders})
                """, pain_event_ids)

                rows = cursor.fetchall()
                logger.debug(f"查询到 {len(rows)} 个痛点事件")

                for row in rows:
                    pains.append({
                        'problem': row['problem'],
                        'workaround': row['current_workaround'],
                        'frequency': row['frequency'],
                        'emotion': row['emotional_signal'],
                        'tools': row['mentioned_tools']
                    })

            logger.debug(f"成功获取 {len(pains)} 个痛点事件")
            return pains

        except Exception as e:
            logger.error(f"获取痛点事件失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def generate_basic_analysis(self, cluster: Dict) -> str:
        """生成基础分析（当LLM调用失败时）"""
        pain_context = "\n".join([
            f"• {pain['problem']}" + chr(10) + f"  当前解决方案: {pain['workaround']}" + chr(10) + f"  发生频率: {pain['frequency']}" + chr(10) + f"  情绪信号: {pain['emotion']}"
            for pain in cluster['sample_pains']
        ])

        opp_analysis = ""
        for opp in cluster['opportunities'][:3]:
            opp_analysis += f"""
### {opp['name']} (评分: {opp['score']:.2f})

**问题描述**: {opp['description']}

**关键机会分析**:
- 市场需求: 通过{cluster['cluster_size']}个相关帖子验证了强烈需求
- 目标用户: {opp['target_users'] or '中小企业、个人开发者、自由职业者'}
- 竞争优势: {opp['missing_capability'] or '填补现有工具的功能空白'}

**MVP功能建议**:
1. 核心功能实现{opp['current_tools'] and f"，整合{opp['current_tools']}的工作流"}
2. 简化用户界面，降低学习成本
3. 快速部署和集成能力

**商业化建议**:
- 免费基础版吸引初始用户
- Pro版本月费$10-20
- 企业定制版支持
"""

        return f"""## 痛点深度分析

### 核心问题
{cluster['description']}

### 影响范围
- 受影响用户群体: {cluster['cluster_size']}个真实用户反馈
- 痛点强度: {cluster['avg_pain_score']:.2f}/1.0

### 典型痛点事件
{pain_context}

## 市场机会评估

### 市场规模
基于Reddit讨论热度，该问题影响了大量用户，具有明确的付费意愿。

### 机会数量
已识别{cluster['opportunity_count']}个具体机会，最高评分{cluster['max_opportunity_score']:.2f}

## 产品设计方案

{opp_analysis}

## 可执行行动计划

### 立即行动（1个月内）
1. 验证目标用户需求，进行深度用户访谈
2. 开发最小可行产品(MVP)原型
3. 建立用户反馈渠道

### 短期目标（3个月内）
1. 发布MVP版本并获取首批100个用户
2. 基于反馈迭代产品功能
3. 探索盈利模式

### 成功指标
- 用户留存率 > 60%
- 月活跃用户增长 > 20%
- NPS得分 > 40
"""

    def analyze_cluster(self, cluster: Dict) -> str:
        """分析单个聚类并生成完整报告"""

        # 构建分析prompt
        pain_context = "\n".join([
            f"• {pain['problem']} (当前解决方案: {pain['workaround']}, 频率: {pain['frequency']}, 情绪: {pain['emotion']})"
            for pain in cluster['sample_pains']
        ])

        opportunities_context = "\n".join([
            f"• {opp['name']} (评分: {opp['score']:.2f})"
            f"  描述: {opp['description'][:100]}..."
            for opp in cluster['opportunities'][:3]
        ])

        prompt = f"""
请分析以下痛点聚类并生成综合报告：

## 聚类信息
- **聚类名称**: {cluster['name']}
- **聚类描述**: {cluster['description']}
- **痛点数量**: {cluster['cluster_size']}
- **平均痛点强度**: {cluster['avg_pain_score']:.2f}
- **机会数量**: {cluster['opportunity_count']}

## 典型痛点样本
{pain_context}

## 已识别的机会
{opportunities_context}

## 分析要求
请按照以下结构生成详细分析报告：

### 1. 痛点深度分析
- 核心问题本质
- 影响范围和严重程度
- 用户特征和使用场景
- 现有解决方案的不足

### 2. 市场机会评估
- 市场规模估算
- 用户付费意愿
- 竞争格局分析
- 进入壁垒评估

### 3. 产品设计方案
- MVP功能定义
- 技术架构建议
- 用户体验设计要点
- 差异化竞争策略

### 4. 商业化路径
- 盈利模式设计
- 获客策略
- 定价策略
- 发展路线图

### 5. 可执行行动计划
- 近期行动项（1-3个月）
- 中期目标（3-6个月）
- 关键成功指标
- 风险应对措施

请确保分析深入、具体且可操作。使用markdown格式输出。
"""

        print(f"🤖 正在分析聚类: {cluster['name'][:50]}...")

        # 尝试调用LLM
        analysis = self.call_llm(prompt, temperature=0.4)

        # 如果LLM调用失败，使用基础分析
        if "LLM调用" in analysis:
            print(f"  ⚠️ 使用基础分析替代")
            analysis = self.generate_basic_analysis(cluster)

        return analysis

    def generate_cluster_report(self, cluster: Dict, analysis: str) -> str:
        """生成聚类报告文件"""
        logger.info(f"生成聚类报告: {cluster['name'][:50]}...")

        # 清理文件名
        safe_name = re.sub(r'[^\w\s-]', '', cluster['name']).strip()
        safe_name = re.sub(r'[-\s]+', '_', safe_name)
        filename = f"{safe_name}_opportunity_analysis.md"
        filepath = os.path.join(self.output_dir, filename)

        logger.debug(f"报告文件路径: {filepath}")

        # 构建完整报告
        report_content = f"""# {cluster['name']} - 机会分析报告

> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> **聚类ID**: {cluster['id']}
> **痛点数量**: {cluster['cluster_size']}
> **平均痛点强度**: {cluster['avg_pain_score']:.2f}
> **机会数量**: {cluster['opportunity_count']}

---

## 📊 聚类概览

**聚类描述**: {cluster['description']}

### 🎯 顶级机会
{chr(10).join([f"- **{opp['name']}** (评分: {opp['score']:.2f})" for opp in cluster['opportunities'][:5]])}

---

## 🔍 深度分析

{analysis}

---

## 📋 原始数据

### 典型痛点事件
{chr(10).join([f"**问题**: {pain['problem']}" + chr(10) + f"- 当前方案: {pain['workaround']}" + chr(10) + f"- 发生频率: {pain['frequency']}" + chr(10) + f"- 情绪信号: {pain['emotion']}" + chr(10) for pain in cluster['sample_pains']])}

### 已识别机会详情
{chr(10).join([f"**{opp['name']}** (评分: {opp['score']:.2f})" + chr(10) + f"- 描述: {opp['description']}" + chr(10) + f"- 推荐建议: {opp['recommendation']}" + chr(10) + (f"- 目标用户: {opp['target_users']}" if opp['target_users'] else "") + chr(10) for opp in cluster['opportunities']])}

---

*本报告由 Reddit Pain Point Finder 自动生成*
"""

        # 写入文件
        try:
            logger.debug(f"开始写入报告文件: {filepath}")
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report_content)
            logger.info(f"报告生成成功: {filepath}")
            print(f"✅ 报告已生成: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"报告生成失败: {filepath}, 错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            print(f"❌ 报告生成失败: {e}")
            return None

    def generate_summary_index(self, report_files: List[str]) -> str:
        """生成总结索引文件"""
        logger.info(f"生成总结索引，包含 {len(report_files)} 个报告")

        index_content = f"""# 痛点机会分析报告索引

> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> **分析数量**: {len(report_files)}

---

## 📈 分析概览

本次共分析了 {len(report_files)} 个高价值痛点聚类，每个聚类都包含详细的痛点分析、应用设计方案和可执行行动计划。

---

## 📋 报告列表

{chr(10).join([f"- [{os.path.basename(f)}]({f})" for f in report_files])}

---

## 🎯 下一步行动建议

1. **优先级排序**: 根据机会评分和市场规模确定产品开发优先级
2. **用户验证**: 针对Top 3机会进行用户访谈和需求验证
3. **MVP开发**: 选择最高价值的机会启动MVP开发
4. **持续监控**: 定期更新Reddit数据，跟踪新的痛点趋势

---

*使用方法: 点击上方链接查看具体的机会分析报告*
"""

        index_path = os.path.join(self.output_dir, "README.md")
        try:
            logger.debug(f"开始写入索引文件: {index_path}")
            with open(index_path, 'w', encoding='utf-8') as f:
                f.write(index_content)
            logger.info(f"索引文件生成成功: {index_path}")
            print(f"📑 索引文件已生成: {index_path}")
            return index_path
        except Exception as e:
            logger.error(f"索引文件生成失败: {index_path}, 错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            print(f"❌ 索引文件生成失败: {e}")
            return None

    def run_analysis(self, min_score: float = 0.8, limit: int = 10):
        """运行完整分析"""
        logger.info(f"开始运行完整分析: min_score={min_score}, limit={limit}")
        print(f"\n🚀 开始痛点机会分析...")
        print(f"   • 最低机会评分: {min_score}")
        print(f"   • 最大分析数量: {limit}")
        print("="*60)

        # 获取聚类数据
        logger.info("开始获取聚类数据...")
        clusters = self.get_top_clusters(min_score, limit)
        if not clusters:
            logger.warning("未找到符合条件的聚类数据")
            print("❌ 未找到符合条件的聚类数据")
            return

        logger.info(f"成功获取 {len(clusters)} 个聚类")
        print(f"📊 找到 {len(clusters)} 个高价值聚类")

        # 分析每个聚类
        report_files = []
        for i, cluster in enumerate(clusters, 1):
            logger.info(f"开始分析第 {i}/{len(clusters)} 个聚类: {cluster['name'][:50]}...")
            print(f"\n[{i}/{len(clusters)}] 分析聚类: {cluster['name'][:50]}...")

            # 执行分析
            logger.debug("执行聚类分析...")
            analysis = self.analyze_cluster(cluster)

            # 生成报告
            logger.debug("生成聚类报告...")
            report_path = self.generate_cluster_report(cluster, analysis)
            if report_path:
                report_files.append(report_path)
                logger.info(f"报告已添加到列表: {report_path}")

            logger.info(f"聚类 {i} 分析完成")
            print(f"✅ 完成: {cluster['name'][:50]}")

        # 生成索引文件
        if report_files:
            logger.info("开始生成总结索引...")
            self.generate_summary_index(report_files)

        logger.info(f"分析完成，生成了 {len(report_files)} 个报告")
        print(f"\n🎉 分析完成！")
        print(f"   • 生成报告: {len(report_files)} 份")
        print(f"   • 输出目录: {self.output_dir}")
        print(f"   • 查看索引: {self.output_dir}/README.md")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Reddit痛点机会分析器")
    parser.add_argument("--min-score", type=float, default=0.8, help="最低机会评分")
    parser.add_argument("--limit", type=int, default=15, help="最大分析数量")
    parser.add_argument("--legacy-db", action="store_true", help="使用旧的多数据库模式")
    parser.add_argument("--dry-run", action="store_true", help="试运行模式（仅获取数据，不生成报告）")

    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("痛点分析器开始运行")
    logger.info(f"数据库模式: {'多数据库文件' if args.legacy_db else '统一数据库'}")
    logger.info(f"最低评分: {args.min_score}, 最大数量: {args.limit}")
    logger.info("=" * 50)

    try:
        logger.info("初始化 PainPointAnalyzer...")
        analyzer = PainPointAnalyzer(unified_db=not args.legacy_db)

        if args.dry_run:
            # 试运行：仅获取数据并显示
            logger.info("试运行模式：获取聚类数据...")
            clusters = analyzer.get_top_clusters(min_score=args.min_score, limit=args.limit)
            logger.info(f"找到 {len(clusters)} 个聚类")

            print(f"\n📊 试运行结果：")
            print(f"找到 {len(clusters)} 个符合条件的聚类：")
            for i, cluster in enumerate(clusters, 1):
                print(f"  {i}. {cluster['name']} (评分: {cluster['max_opportunity_score']:.2f}, 机会数: {cluster['opportunity_count']})")
            return

        logger.info("开始运行分析...")
        analyzer.run_analysis(min_score=args.min_score, limit=args.limit)
        logger.info("程序执行完成")
    except Exception as e:
        logger.error(f"程序执行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        print(f"❌ 程序执行失败: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()