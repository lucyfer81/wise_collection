# Reddit Pain Point Finder

一个自动化的 Reddit 痛点发现系统，从 Reddit 帖子中提取用户痛点，聚类分析工作流问题，并发现适合一人公司的微工具机会。

## 🎯 系统概述

这个系统实现了 instruction.md 中描述的设计理念，通过以下步骤发现商业机会：

1. **数据抓取** - 从多个子版块收集 Reddit 帖子
2. **信号过滤** - 识别包含痛点的帖子
3. **痛点抽取** - 使用 LLM 提取结构化痛点事件
4. **向量化** - 为痛点事件创建嵌入向量
5. **聚类分析** - 发现相似的工作流问题
6. **机会映射** - 将痛点聚类映射为工具机会
7. **可行性评分** - 评估机会对一人公司的可行性

## 📁 项目结构

```
reddit_pain_finder/
│
├── config/                    # 配置文件
│   ├── subreddits.yaml       # 子版块和关键词配置
│   ├── llm.yaml             # LLM 模型配置
│   └── thresholds.yaml      # 过滤阈值配置
│
├── data/                     # 数据库文件
│   ├── raw_posts.db         # 原始抓取数据
│   ├── filtered_posts.db    # 过滤后数据
│   ├── pain_events.db       # 痛点事件
│   └── clusters.db          # 聚类结果
│
├── pipeline/                 # 核心处理模块
│   ├── fetch.py             # Reddit 数据抓取
│   ├── filter_signal.py     # 痛点信号过滤
│   ├── extract_pain.py      # 痛点事件抽取
│   ├── embed.py             # 向量化
│   ├── cluster.py           # 聚类分析
│   ├── map_opportunity.py   # 机会映射
│   └── score_viability.py   # 可行性评分
│
├── utils/                    # 工具模块
│   ├── db.py                # 数据库操作
│   ├── llm_client.py        # LLM 客户端
│   └── embedding.py         # 嵌入工具
│
├── logs/                     # 日志文件
├── run_pipeline.py          # 主执行脚本
├── test_pipeline.py         # 测试脚本
└── README.md               # 本文档
```

## 🚀 快速开始

### 1. 环境准备

创建虚拟环境并安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

### 2. 环境变量配置

创建 `.env` 文件（在项目根目录）：

```env
# Reddit API
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret

# SiliconFlow API
Siliconflow_KEY=your_siliconflow_api_key
Siliconflow_Base_URL=https://api.siliconflow.cn/v1
Siliconflow_AI_Model_Default=deepseek-ai/DeepSeek-V3.2
```

### 3. 测试系统

运行测试脚本验证安装：

```bash
python test_pipeline.py
```

### 4. 运行 Pipeline

#### 运行完整流程：
```bash
python run_pipeline.py --stage all
```

#### 运行单个阶段：
```bash
# 只抓取数据
python run_pipeline.py --stage fetch --limit-subreddits 5

# 只过滤信号
python run_pipeline.py --stage filter --limit-posts 100

# 只抽取痛点
python run_pipeline.py --stage extract --limit-posts 50
```

## ⚙️ 配置说明

### 子版块配置 (`config/subreddits.yaml`)

定义要监控的子版块和痛点关键词：

```yaml
subreddits:
  - name: "programming"
    category: "technical_pain"
    methods: ["hot", "new", "search"]
    thresholds:
      min_upvotes: 20
      min_comments: 10
      min_upvote_ratio: 0.2

pain_keywords:
  frustration:
    - "frustrated with"
    - "tired of"
    - "struggling with"
```

### LLM 配置 (`config/llm.yaml`)

配置不同任务使用的模型：

```yaml
models:
  main:
    name: "deepseek-ai/DeepSeek-V3.2"
    temperature: 0.1
    max_tokens: 2000

task_mapping:
  pain_extraction:
    model: "medium"
    temperature: 0.1
```

### 阈值配置 (`config/thresholds.yaml`)

调整过滤和评分阈值：

```yaml
reddit_quality:
  base:
    min_upvotes: 5
    min_comments: 3
    min_upvote_ratio: 0.1

pain_signal:
  emotional_intensity:
    min_score: 0.3
```

## 📊 输出结果

系统运行完成后，会生成：

1. **数据库中的结构化数据**
   - 原始帖子数据
   - 过滤后的高质量帖子
   - 提取的痛点事件
   - 聚类结果
   - 映射的机会和评分

2. **日志文件** (`logs/pipeline.log`)
   - 详细的处理日志
   - 错误信息和统计

3. **最终报告**（可选保存）
   - Pipeline 运行统计
   - 发现的机会列表
   - 效率指标

## 🔧 高级用法

### 自定义子版块

编辑 `config/subreddits.yaml` 添加新的子版块：

```yaml
subreddits:
  - name: "your_subreddit"
    category: "your_category"
    methods: ["hot", "new"]
    thresholds:
      min_upvotes: 10
      min_comments: 5
```

### 调整模型使用

编辑 `config/llm.yaml` 优化成本和性能：

```yaml
models:
  # 使用更小的模型节省成本
  small:
    name: "Qwen/Qwen2.5-7B-Instruct"
    temperature: 0.0
```

### 查看结果

```bash
# 查看数据库统计
python -c "
from utils.db import db
print(db.get_statistics())
"

# 查看最高分机会
python run_pipeline.py --stage score --limit-opportunities 10
```

## 📈 监控和调试

### 查看详细日志

```bash
tail -f logs/pipeline.log
```

### 检查特定阶段

```bash
# 验证嵌入质量
python pipeline/embed.py --verify --limit 20

# 查看聚类结果
python pipeline/cluster.py --list

# 查看机会映射
python pipeline/map_opportunity.py --list --min-score 6.0
```

### 性能优化

1. **API 成本控制**
   - 使用较小的模型进行初步筛选
   - 启用缓存减少重复调用
   - 限制批处理大小

2. **处理速度优化**
   - 调整并发参数
   - 增加延迟避免 API 限制
   - 使用向量数据库优化相似度搜索

## 🚨 故障排除

### 常见问题

1. **Reddit API 认证失败**
   - 检查 `.env` 中的 API 密钥
   - 确认 Reddit 应用配置正确

2. **LLM API 调用失败**
   - 验证 SiliconFlow API 密钥
   - 检查模型名称和网络连接

3. **数据库错误**
   - 确保 `data/` 目录存在且可写
   - 检查 SQLite 文件权限

4. **内存不足**
   - 减少批处理大小
   - 限制处理的数据量

### 调试模式

启用详细日志：

```bash
export PYTHONPATH=/path/to/reddit_pain_finder
python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from run_pipeline import RedditPainPipeline
pipeline = RedditPainPipeline()
# 你的调试代码
"
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 开发流程

1. Fork 项目
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

### 代码规范

- 使用 type hints
- 添加详细的文档字符串
- 遵循 PEP 8 代码风格
- 编写相应的测试

## 📄 许可证

本项目采用 MIT 许可证。

## 🙏 致谢

- Reddit PRAW 库
- SiliconFlow API
- OpenAI Embeddings API
- Scikit-learn

---

**注意**: 本系统仅用于学习和研究目的。使用时请遵守 Reddit 和相关 API 的服务条款。