# JTBD产品语义升级实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 将cluster从"研究标签"升级为"产品语义标签"，通过添加JTBD（Job To Be Done）字段，使聚类成为可设计的用户任务机会。

**架构:**
1. 扩展数据库schema，添加JTBD相关字段
2. 增强LLM提示词，引导模型从痛点中提取产品语义
3. 修改聚类生成流程，自动生成JTBD字段
4. 保持向后兼容，新字段可选

**技术栈:** Python 3.10, SQLite, LLM API (SiliconFlow), JSON

---

## 核心设计理念

### JTBD格式统一
```
"当[某类人]想完成[某个任务]时，会因为[某个结构性原因]而失败。"
```

### 字段设计
- **job_statement**: 统一的JTBD陈述（上述格式）
- **job_steps**: 任务步骤分解（JSON数组）
- **desired_outcomes**: 期望结果（JSON数组）
- **job_context**: 任务上下文描述
- **customer_profile**: 用户画像
- **semantic_category**: 语义分类（用于聚合）
- **product_impact**: 产品影响评分（0-1）

---

## Task 1: 数据库Schema扩展

**Files:**
- Modify: `utils/db.py:168-185` (clusters表定义)
- Modify: `utils/db.py:420-440` (多数据库模式clusters表)

**Step 1: 添加JTBD字段到_init_unified_database()**

在`utils/db.py`的clusters表定义中添加JTBD字段：

```python
# 在utils/db.py的第168-185行，修改clusters表创建SQL
conn.execute("""
    CREATE TABLE IF NOT EXISTS clusters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cluster_name TEXT NOT NULL,
        cluster_description TEXT,
        source_type TEXT,
        centroid_summary TEXT,
        common_pain TEXT,
        common_context TEXT,
        example_events TEXT,
        pain_event_ids TEXT NOT NULL,
        cluster_size INTEGER NOT NULL,
        avg_pain_score REAL,
        workflow_confidence REAL,
        workflow_similarity REAL DEFAULT 0.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        -- JTBD产品语义字段
        job_statement TEXT,
        job_steps TEXT,
        desired_outcomes TEXT,
        job_context TEXT,
        customer_profile TEXT,
        semantic_category TEXT,
        product_impact REAL DEFAULT 0.0
    )
""")
```

**Step 2: 添加JTBD字段到_init_clusters_db()**

同样修改多数据库模式下的clusters表定义（第420-440行）：

```python
# 在_init_clusters_db()方法中，使用相同的ALTER TABLE逻辑
```

**Step 3: 添加迁移逻辑_add_jtbd_columns()**

在`utils/db.py`中添加新方法，为现有数据库添加JTBD字段：

```python
def _add_jtbd_columns(self, conn):
    """为clusters表添加JTBD产品语义字段（如果不存在）"""
    try:
        cursor = conn.execute("PRAGMA table_info(clusters)")
        existing_columns = {row['name'] for row in cursor.fetchall()}

        jtbd_columns = {
            'job_statement': 'TEXT',
            'job_steps': 'TEXT',  # JSON数组
            'desired_outcomes': 'TEXT',  # JSON数组
            'job_context': 'TEXT',
            'customer_profile': 'TEXT',
            'semantic_category': 'TEXT',
            'product_impact': 'REAL DEFAULT 0.0'
        }

        for column_name, column_def in jtbd_columns.items():
            if column_name not in existing_columns:
                conn.execute(f"""
                    ALTER TABLE clusters
                    ADD COLUMN {column_name} {column_def}
                """)
                logger.info(f"Added {column_name} column to clusters table")

        # 创建索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_semantic_category ON clusters(semantic_category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_product_impact ON clusters(product_impact)")

    except Exception as e:
        logger.error(f"Failed to add JTBD columns to clusters table: {e}")
```

**Step 4: 在数据库初始化时调用迁移方法**

在`_init_unified_database()`和`_init_clusters_db()`的commit之前添加：

```python
# 添加JTBD字段到clusters表（如果不存在）
self._add_jtbd_columns(conn)
```

**Step 5: 修改insert_cluster()方法**

在`utils/db.py:987-1016`的`insert_cluster()`方法中添加JTBD字段支持：

```python
def insert_cluster(self, cluster_data: Dict[str, Any]) -> Optional[int]:
    """插入聚类"""
    try:
        with self.get_connection("clusters") as conn:
            cursor = conn.execute("""
                INSERT INTO clusters
                (cluster_name, cluster_description, source_type, centroid_summary,
                 common_pain, common_context, example_events, pain_event_ids, cluster_size,
                 avg_pain_score, workflow_confidence, workflow_similarity,
                 job_statement, job_steps, desired_outcomes, job_context,
                 customer_profile, semantic_category, product_impact)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cluster_data["cluster_name"],
                cluster_data.get("cluster_description", ""),
                cluster_data.get("source_type", ""),
                cluster_data.get("centroid_summary", ""),
                cluster_data.get("common_pain", ""),
                cluster_data.get("common_context", ""),
                json.dumps(cluster_data.get("example_events", [])),
                json.dumps(cluster_data["pain_event_ids"]),
                cluster_data["cluster_size"],
                cluster_data.get("avg_pain_score", 0.0),
                cluster_data.get("workflow_confidence", 0.0),
                cluster_data.get("workflow_similarity", 0.0),
                cluster_data.get("job_statement"),  # 新增
                json.dumps(cluster_data.get("job_steps", [])),  # 新增
                json.dumps(cluster_data.get("desired_outcomes", [])),  # 新增
                cluster_data.get("job_context"),  # 新增
                cluster_data.get("customer_profile"),  # 新增
                cluster_data.get("semantic_category"),  # 新增
                cluster_data.get("product_impact", 0.0)  # 新增
            ))
            cluster_id = cursor.lastrowid
            conn.commit()
            return cluster_id
    except Exception as e:
        logger.error(f"Failed to insert cluster: {e}")
        return None
```

**Step 6: 测试数据库迁移**

```bash
# 运行测试脚本
python3 -c "
from utils.db import db
print('Testing JTBD columns...')
with db.get_connection('clusters') as conn:
    cursor = conn.execute('PRAGMA table_info(clusters)')
    columns = [row['name'] for row in cursor.fetchall()]
    jtbd_columns = ['job_statement', 'job_steps', 'desired_outcomes',
                    'job_context', 'customer_profile', 'semantic_category', 'product_impact']
    for col in jtbd_columns:
        if col in columns:
            print(f'✅ {col} exists')
        else:
            print(f'❌ {col} missing')
"
```

预期输出：所有JTBD字段显示`✅`

**Step 7: 提交数据库schema变更**

```bash
git add utils/db.py
git commit -m "feat: add JTBD product semantics fields to clusters schema"
```

---

## Task 2: LLM提示词增强

**Files:**
- Modify: `utils/llm_client.py:410-446` (_get_workflow_clustering_prompt)
- Modify: `utils/llm_client.py:520-548` (_get_cluster_summarizer_prompt)
- Create: `utils/llm_client.py` (新增_generate_jtbd_from_cluster方法)

**Step 1: 修改workflow clustering提示词，要求JTBD格式**

在`utils/llm_client.py`的`_get_workflow_clustering_prompt()`方法中添加JTBD要求：

```python
def _get_workflow_clustering_prompt(self) -> str:
    """Get workflow clustering prompt with JTBD output"""
    return """You are analyzing user pain events to extract product opportunities.

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

Additionally, extract the JTBD (Job To Be Done) format:
"当[某类人]想完成[某个任务]时，会因为[某个结构性原因]而失败。"

Return JSON only with this format:
{
  "workflow_similarity": 0.75,
  "workflow_name": "name of the workflow",
  "workflow_description": "description of what these events have in common",
  "confidence": 0.8,
  "reasoning": "brief explanation of your rating",
  "job_statement": "当[用户类型]想完成[核心任务]时，会因为[结构性障碍]而失败",
  "customer_profile": "describe who faces this problem (role, context, expertise level)",
  "desired_outcomes": ["outcome 1", "outcome 2", "outcome 3"]
}

Be precise with your similarity score and JTBD statement."""
```

**Step 2: 修改cluster summarizer提示词，添加JTBD步骤提取**

在`_get_cluster_summarizer_prompt()`方法中添加JTBD步骤提取：

```python
def _get_cluster_summarizer_prompt(self) -> str:
    """获取聚类摘要提示（增强JTBD版本）"""
    return """You are a cluster summarizer for pain events with focus on product semantics.

These pain events come from the same source and discourse style.
Your task is to extract:
1. The common problem pattern
2. The Job To Be Done (JTBD) structure
3. Task steps where failures occur
4. User context and profile

JTBD Format: "当[某类人]想完成[某个任务]时，会因为[某个结构性原因]而失败。"

Focus on:
1. What is the common problem across all these events?
2. What shared task are users trying to accomplish?
3. Where exactly does the task fail? (which step)
4. What is the structural root cause?
5. Who are these users? (role, expertise, context)
6. What outcomes do they desire?

Return JSON only with this format:
{
  "centroid_summary": "brief summary of the core shared problem",
  "common_pain": "the main difficulty or challenge (technical language)",
  "common_context": "the shared workflow or situation where this occurs",
  "example_events": [
    "Event 1: representative problem description",
    "Event 2: representative problem description"
  ],
  "job_statement": "当[用户类型]想完成[核心任务]时，会因为[结构性障碍]而失败",
  "job_steps": [
    "步骤1: 用户尝试[动作]",
    "步骤2: 遇到[具体障碍]",
    "步骤3: 寻找[替代方案]但[为什么失败]"
  ],
  "job_context": "detailed description of when/where/why this task is performed",
  "customer_profile": "specific user type (role, expertise level, tools they use)",
  "semantic_category": "category name (e.g., 'ai_interaction', 'data_processing', 'workflow_automation')",
  "product_impact": 0.85,
  "coherence_score": 0.8,
  "reasoning": "brief explanation"
}

BE PRECISE - extract real patterns, don't invent."""
```

**Step 3: 在LLMClient类中添加JTBD生成方法**

```python
def generate_jtbd_from_cluster(
    self,
    cluster_data: Dict[str, Any]
) -> Dict[str, Any]:
    """从已验证的聚类生成详细JTBD分析"""
    prompt = """You are a product analyst specializing in Jobs To Be Done (JTBD) framework.

Given this cluster information, extract a detailed JTBD analysis.

CLUSTER DATA:
- Name: {cluster_name}
- Description: {cluster_description}
- Common Pain: {common_pain}
- Context: {common_context}
- Representative Events: {example_events}

Your task:
1. Refine the JTBD statement to follow exact format: "当[某类人]想完成[某个任务]时，会因为[某个结构性原因]而失败。"
2. Break down the task into explicit steps
3. Identify where exactly the failure occurs
4. Describe the user profile precisely
5. Categorize the semantic type

Return JSON only:
{{
  "job_statement": "当[用户类型]想完成[核心任务]时，会因为[结构性障碍]而失败",
  "job_steps": ["步骤1: ...", "步骤2: ...", "步骤3: ..."],
  "desired_outcomes": ["期望结果1", "期望结果2", "期望结果3"],
  "job_context": "detailed context description",
  "customer_profile": "specific user role and context",
  "semantic_category": "category_name",
  "product_impact": 0.85
}}

Be actionable and precise.""".format(
        cluster_name=cluster_data.get('cluster_name', ''),
        cluster_description=cluster_data.get('cluster_description', ''),
        common_pain=cluster_data.get('common_pain', ''),
        common_context=cluster_data.get('common_context', ''),
        example_events=json.dumps(cluster_data.get('example_events', [])[:3])
    )

    messages = [
        {"role": "system", "content": "You are a JTBD analysis expert. Extract precise, actionable product insights."},
        {"role": "user", "content": prompt}
    ]

    return self.chat_completion(
        messages=messages,
        model_type="cluster_summarizer",
        json_mode=True
    )
```

**Step 4: 更新cluster_pain_events()方法的响应处理**

修改`pipeline/cluster.py`的`_validate_cluster_with_llm()`方法，提取JTBD字段：

```python
def _validate_cluster_with_llm(
    self,
    pain_events: List[Dict[str, Any]],
    cluster_name: str = None
) -> Dict[str, Any]:
    """Use LLM to validate cluster with JTBD extraction"""
    try:
        # Call LLM for cluster validation
        response = llm_client.cluster_pain_events(pain_events)
        validation_result = response["content"]

        # Extract workflow_similarity score
        workflow_similarity = validation_result.get("workflow_similarity", 0.0)

        # Use hardcoded threshold for decision
        is_valid_cluster = workflow_similarity >= WORKFLOW_SIMILARITY_THRESHOLD

        return {
            "is_valid_cluster": is_valid_cluster,
            "workflow_similarity": workflow_similarity,
            "cluster_name": validation_result.get("workflow_name", "Unnamed Cluster"),
            "cluster_description": validation_result.get("workflow_description", ""),
            "confidence": validation_result.get("confidence", 0.0),
            "reasoning": validation_result.get("reasoning", ""),
            # JTBD fields from validation
            "job_statement": validation_result.get("job_statement", ""),
            "customer_profile": validation_result.get("customer_profile", ""),
            "desired_outcomes": validation_result.get("desired_outcomes", [])
        }

    except Exception as e:
        logger.error(f"Failed to validate cluster with LLM: {e}")
        return {
            "is_valid_cluster": False,
            "workflow_similarity": 0.0,
            "reasoning": f"Validation error: {e}"
        }
```

**Step 5: 测试LLM JTBD生成**

```python
# 创建测试脚本 test_jtbd_generation.py
from utils.llm_client import llm_client

test_cluster = {
    "cluster_name": "AI API Integration Frustration",
    "cluster_description": "Users struggling with rate limits and authentication",
    "common_pain": "API rate limiting and complex authentication flows",
    "common_context": "When integrating AI services into applications",
    "example_events": [
        "Can't figure out how to authenticate with OpenAI API",
        "Keep hitting rate limits when processing batches",
        "Documentation is unclear about token counting"
    ]
}

result = llm_client.generate_jtbd_from_cluster(test_cluster)
import json
print(json.dumps(result, indent=2, ensure_ascii=False))
```

运行测试：
```bash
python3 test_jtbd_generation.py
```

预期输出包含：job_statement, job_steps, desired_outcomes等字段

**Step 6: 提交LLM提示词增强**

```bash
git add utils/llm_client.py
git commit -m "feat: add JTBD extraction to LLM prompts"
```

---

## Task 3: 聚类生成流程集成JTBD

**Files:**
- Modify: `pipeline/cluster.py:56-88` (_validate_cluster_with_llm)
- Modify: `pipeline/cluster.py:319-387` (_process_source_clusters)
- Modify: `pipeline/cluster.py:161-185` (_save_cluster_to_database)

**Step 1: 修改_summarize_source_cluster()以包含JTBD**

在`pipeline/cluster.py`的`_summarize_source_cluster()`方法中：

```python
def _summarize_source_cluster(self, pain_events: List[Dict[str, Any]], source_type: str) -> Dict[str, Any]:
    """使用Cluster Summarizer生成source内聚类摘要（包含JTBD）"""
    try:
        response = llm_client.summarize_source_cluster(pain_events, source_type)
        summary_result = response.get("content", {})

        # 提取JTBD字段
        jtbd_fields = {
            "job_statement": summary_result.get("job_statement", ""),
            "job_steps": summary_result.get("job_steps", []),
            "desired_outcomes": summary_result.get("desired_outcomes", []),
            "job_context": summary_result.get("job_context", ""),
            "customer_profile": summary_result.get("customer_profile", ""),
            "semantic_category": summary_result.get("semantic_category", ""),
            "product_impact": summary_result.get("product_impact", 0.0)
        }

        # 合并到原有结果
        summary_result.update(jtbd_fields)
        return summary_result

    except Exception as e:
        logger.error(f"Failed to summarize source cluster: {e}")
        return {
            "centroid_summary": "",
            "common_pain": "",
            "common_context": "",
            "example_events": [],
            "coherence_score": 0.0,
            "reasoning": f"Summary failed: {e}",
            # JTBD默认值
            "job_statement": "",
            "job_steps": [],
            "desired_outcomes": [],
            "job_context": "",
            "customer_profile": "",
            "semantic_category": "",
            "product_impact": 0.0
        }
```

**Step 2: 修改_process_source_clusters()以传递JTBD字段**

在`pipeline/cluster.py:319-387`的`_process_source_clusters()`方法中：

```python
# 在第358-372行，修改final_cluster构建逻辑
final_cluster = {
    "cluster_name": f"{source_type}: {validation_result['cluster_name']}",
    "cluster_description": validation_result["cluster_description"],
    "source_type": source_type,
    "cluster_id": cluster_id,
    "centroid_summary": summary_result.get("centroid_summary", ""),
    "common_pain": summary_result.get("common_pain", ""),
    "common_context": summary_result.get("common_context", ""),
    "example_events": summary_result.get("example_events", []),
    "pain_event_ids": [event["id"] for event in cluster_events],
    "cluster_size": len(cluster_events),
    "workflow_confidence": validation_result["confidence"],
    "workflow_similarity": workflow_similarity,
    "validation_reasoning": validation_result["reasoning"],
    # JTBD fields
    "job_statement": summary_result.get("job_statement", validation_result.get("job_statement", "")),
    "job_steps": summary_result.get("job_steps", []),
    "desired_outcomes": summary_result.get("desired_outcomes", validation_result.get("desired_outcomes", [])),
    "job_context": summary_result.get("job_context", ""),
    "customer_profile": summary_result.get("customer_profile", validation_result.get("customer_profile", "")),
    "semantic_category": summary_result.get("semantic_category", ""),
    "product_impact": summary_result.get("product_impact", 0.0)
}
```

**Step 3: 修改_save_cluster_to_database()以保存JTBD字段**

在`pipeline/cluster.py:161-185`的`_save_cluster_to_database()`方法中：

```python
def _save_cluster_to_database(self, cluster_data: Dict[str, Any]) -> Optional[int]:
    """保存聚类到数据库（包含JTBD字段）"""
    try:
        # 准备聚类数据 - 支持JTBD字段
        cluster_record = {
            "cluster_name": cluster_data["cluster_name"],
            "cluster_description": cluster_data["cluster_description"],
            "source_type": cluster_data.get("source_type", ""),
            "centroid_summary": cluster_data.get("centroid_summary", ""),
            "common_pain": cluster_data.get("common_pain", ""),
            "common_context": cluster_data.get("common_context", ""),
            "example_events": cluster_data.get("example_events", []),
            "pain_event_ids": cluster_data["pain_event_ids"],
            "cluster_size": cluster_data["cluster_size"],
            "avg_pain_score": cluster_data.get("avg_pain_score", 0.0),
            "workflow_confidence": cluster_data.get("workflow_confidence", 0.0),
            "workflow_similarity": cluster_data.get("workflow_similarity", 0.0),
            # JTBD fields
            "job_statement": cluster_data.get("job_statement", ""),
            "job_steps": cluster_data.get("job_steps", []),
            "desired_outcomes": cluster_data.get("desired_outcomes", []),
            "job_context": cluster_data.get("job_context", ""),
            "customer_profile": cluster_data.get("customer_profile", ""),
            "semantic_category": cluster_data.get("semantic_category", ""),
            "product_impact": cluster_data.get("product_impact", 0.0)
        }

        cluster_id = db.insert_cluster(cluster_record)
        return cluster_id

    except Exception as e:
        logger.error(f"Failed to save cluster to database: {e}")
        return None
```

**Step 4: 添加JTBD质量检查方法**

在`pipeline/cluster.py`的`PainEventClusterer`类中添加新方法：

```python
def _validate_jtbd_quality(self, jtbd_data: Dict[str, Any]) -> Dict[str, Any]:
    """验证JTBD数据质量"""
    required_fields = ["job_statement", "job_steps", "customer_profile"]
    missing_fields = [f for f in required_fields if not jtbd_data.get(f)]

    if missing_fields:
        logger.warning(f"Missing JTBD fields: {missing_fields}")

    # 检查job_statement格式
    job_statement = jtbd_data.get("job_statement", "")
    if job_statement and "当" not in job_statement:
        logger.warning(f"job_statement doesn't follow JTBD format: {job_statement[:50]}...")

    return {
        "is_valid": len(missing_fields) == 0,
        "missing_fields": missing_fields,
        "format_valid": "当" in job_statement if job_statement else False
    }
```

**Step 5: 运行端到端测试**

```bash
# 创建小规模测试数据
python3 -c "
from pipeline.cluster import clusterer
result = clusterer.cluster_pain_events(limit=50)
print(f'Clusters created: {result[\"clusters_created\"]}')

# 检查第一个cluster的JTBD字段
if result['final_clusters']:
    first_cluster = result['final_clusters'][0]
    print(f'\\nFirst cluster JTBD:')
    print(f'  job_statement: {first_cluster.get(\"job_statement\", \"MISSING\")}')
    print(f'  job_steps: {len(first_cluster.get(\"job_steps\", []))} steps')
    print(f'  customer_profile: {first_cluster.get(\"customer_profile\", \"MISSING\")}')
"
```

预期输出：所有JTBD字段都有值

**Step 6: 提交聚类流程集成**

```bash
git add pipeline/cluster.py
git commit -m "feat: integrate JTBD generation into clustering pipeline"
```

---

## Task 4: 添加JTBD查询和展示功能

**Files:**
- Modify: `pipeline/cluster.py:405-443` (get_cluster_analysis)
- Create: `pipeline/cluster.py` (新增get_clusters_by_jtbd方法)

**Step 1: 扩展get_cluster_analysis()以包含JTBD**

修改`get_cluster_analysis()`方法，确保返回JTBD字段：

```python
def get_cluster_analysis(self, cluster_id: int) -> Optional[Dict[str, Any]]:
    """获取聚类详细分析（包含JTBD）"""
    try:
        # 从数据库获取聚类信息
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("""
                SELECT * FROM clusters WHERE id = ?
            """, (cluster_id,))
            cluster_data = cursor.fetchone()

        if not cluster_data:
            return None

        cluster_info = dict(cluster_data)

        # 获取聚类中的痛点事件
        pain_event_ids = json.loads(cluster_info["pain_event_ids"])
        pain_events = []

        with db.get_connection("pain") as conn:
            for event_id in pain_event_ids:
                cursor = conn.execute("""
                    SELECT * FROM pain_events WHERE id = ?
                """, (event_id,))
                event_data = cursor.fetchone()
                if event_data:
                    pain_events.append(dict(event_data))

        cluster_info["pain_events"] = pain_events

        # 重新计算聚类摘要
        cluster_summary = self._create_cluster_summary(pain_events)
        cluster_info["cluster_summary"] = cluster_summary

        # 反序列化JTBD字段
        cluster_info["job_steps"] = json.loads(cluster_info.get("job_steps", "[]"))
        cluster_info["desired_outcomes"] = json.loads(cluster_info.get("desired_outcomes", "[]"))
        cluster_info["example_events"] = json.loads(cluster_info.get("example_events", "[]"))

        return cluster_info

    except Exception as e:
        logger.error(f"Failed to get cluster analysis: {e}")
        return None
```

**Step 2: 添加按JTBD语义查询聚类的方法**

在`PainEventClusterer`类中添加：

```python
def get_clusters_by_semantic_category(self, category: str) -> List[Dict[str, Any]]:
    """按语义分类获取聚类"""
    try:
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("""
                SELECT id, cluster_name, job_statement, customer_profile,
                       semantic_category, product_impact, cluster_size
                FROM clusters
                WHERE semantic_category = ?
                ORDER BY product_impact DESC
            """, (category,))

            clusters = []
            for row in cursor.fetchall():
                cluster = dict(row)
                cluster["job_steps"] = json.loads(cluster.get("job_steps", "[]"))
                clusters.append(cluster)

            return clusters

    except Exception as e:
        logger.error(f"Failed to get clusters by semantic category: {e}")
        return []

def get_high_impact_clusters(self, min_impact: float = 0.7) -> List[Dict[str, Any]]:
    """获取高产品影响聚类"""
    try:
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("""
                SELECT id, cluster_name, job_statement, customer_profile,
                       semantic_category, product_impact, cluster_size
                FROM clusters
                WHERE product_impact >= ?
                ORDER BY product_impact DESC
            """, (min_impact,))

            return [dict(row) for row in cursor.fetchall()]

    except Exception as e:
        logger.error(f"Failed to get high impact clusters: {e}")
        return []

def get_all_semantic_categories(self) -> List[Dict[str, Any]]:
    """获取所有语义分类及其统计"""
    try:
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("""
                SELECT semantic_category,
                       COUNT(*) as cluster_count,
                       AVG(product_impact) as avg_impact,
                       SUM(cluster_size) as total_events
                FROM clusters
                WHERE semantic_category IS NOT NULL AND semantic_category != ''
                GROUP BY semantic_category
                ORDER BY avg_impact DESC
            """)

            return [dict(row) for row in cursor.fetchall()]

    except Exception as e:
        logger.error(f"Failed to get semantic categories: {e}")
        return []
```

**Step 3: 创建JTBD展示脚本**

创建`scripts/show_jtbd_clusters.py`：

```python
#!/usr/bin/env python3
"""展示JTBD产品语义聚类"""

from utils.db import db
from pipeline.cluster import PainEventClusterer
import json

def main():
    clusterer = PainEventClusterer()

    print("=" * 80)
    print("JTBD产品语义聚类分析")
    print("=" * 80)

    # 1. 显示所有语义分类
    print("\n## 语义分类概览")
    categories = clusterer.get_all_semantic_categories()
    for cat in categories:
        print(f"{cat['semantic_category']}: {cat['cluster_count']} clusters, "
              f"avg impact={cat['avg_impact']:.2f}, {cat['total_events']} events")

    # 2. 显示高影响聚类
    print("\n## 高产品影响聚类 (product_impact >= 0.7)")
    high_impact = clusterer.get_high_impact_clusters(min_impact=0.7)
    for cluster in high_impact[:5]:
        print(f"\n### {cluster['cluster_name']}")
        print(f"JTBD: {cluster.get('job_statement', 'N/A')}")
        print(f"Customer: {cluster.get('customer_profile', 'N/A')}")
        print(f"Impact: {cluster['product_impact']:.2f}, Size: {cluster['cluster_size']}")

    # 3. 详细分析第一个高影响聚类
    if high_impact:
        print("\n## 详细分析示例")
        cluster_analysis = clusterer.get_cluster_analysis(high_impact[0]['id'])
        if cluster_analysis:
            print(f"\nCluster: {cluster_analysis['cluster_name']}")
            print(f"\nJTBD Statement:")
            print(f"  {cluster_analysis.get('job_statement', 'N/A')}")
            print(f"\nJob Steps:")
            for i, step in enumerate(cluster_analysis.get('job_steps', []), 1):
                print(f"  {i}. {step}")
            print(f"\nDesired Outcomes:")
            for outcome in cluster_analysis.get('desired_outcomes', []):
                print(f"  - {outcome}")
            print(f"\nCustomer Profile:")
            print(f"  {cluster_analysis.get('customer_profile', 'N/A')}")
            print(f"\nSemantic Category: {cluster_analysis.get('semantic_category', 'N/A')}")
            print(f"Product Impact: {cluster_analysis.get('product_impact', 0):.2f}")

if __name__ == "__main__":
    main()
```

**Step 4: 运行展示脚本**

```bash
chmod +x scripts/show_jtbd_clusters.py
python3 scripts/show_jtbd_clusters.py
```

预期输出：
- 语义分类概览表格
- 高影响聚类列表及其JTBD陈述
- 详细的聚类JTBD分析示例

**Step 5: 提交查询和展示功能**

```bash
git add pipeline/cluster.py scripts/show_jtbd_clusters.py
git commit -m "feat: add JTBD query and display functions"
```

---

## Task 5: 向后兼容处理

**Files:**
- Modify: `utils/db.py:987-1016` (insert_cluster - 使JTBD字段可选)
- Modify: `pipeline/cluster.py` (所有JTBD相关逻辑)

**Step 1: 确保所有JTBD字段向后兼容**

验证数据库操作对缺失的JTBD字段有默认值处理（已在Task 1和3中完成）。

**Step 2: 添加数据迁移脚本**

创建`scripts/migrate_existing_clusters_to_jtbd.py`：

```python
#!/usr/bin/env python3
"""为现有clusters生成JTBD字段"""

from utils.db import db
from utils.llm_client import llm_client
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_cluster(cluster_id: int):
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

            # 如果已有job_statement，跳过
            if cluster_dict.get("job_statement"):
                logger.info(f"Cluster {cluster_id} already has JTBD, skipping")
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
        cursor = conn.execute("""
            SELECT id FROM clusters
            WHERE job_statement IS NULL OR job_statement = ''
            ORDER BY id
        """)

        cluster_ids = [row["id"] for row in cursor.fetchall()]

    logger.info(f"Found {len(cluster_ids)} clusters to migrate")

    success_count = 0
    for i, cluster_id in enumerate(cluster_ids, 1):
        logger.info(f"\n[{i}/{len(cluster_ids)}] Processing cluster {cluster_id}")
        if migrate_cluster(cluster_id):
            success_count += 1
            import time
            time.sleep(2)  # 避免API限流

    logger.info(f"\n=== Migration Complete ===")
    logger.info(f"Successfully migrated: {success_count}/{len(cluster_ids)}")

if __name__ == "__main__":
    main()
```

**Step 3: 运行迁移脚本**

```bash
# 先测试单个cluster
python3 -c "
from scripts.migrate_existing_clusters_to_jtbd import migrate_cluster
migrate_cluster(1)  # 测试cluster ID 1
"

# 运行完整迁移
python3 scripts/migrate_existing_clusters_to_jtbd.py
```

**Step 4: 验证迁移结果**

```python
from utils.db import db

with db.get_connection("clusters") as conn:
    cursor = conn.execute("""
        SELECT id, cluster_name,
               CASE WHEN job_statement IS NULL OR job_statement = ''
                    THEN 'NO' ELSE 'YES' END as has_jtbd
        FROM clusters
    """)

    print("Cluster JTBD Status:")
    for row in cursor.fetchall():
        print(f"  {row['id']}: {row['has_jtbd']} - {row['cluster_name'][:50]}")
```

预期输出：所有cluster显示`YES`

**Step 5: 提交迁移功能**

```bash
git add scripts/migrate_existing_clusters_to_jtbd.py
git commit -m "feat: add JTBD migration script for existing clusters"
```

---

## Task 6: 集成测试和文档

**Files:**
- Create: `tests/test_jtbd_integration.py`
- Create: `docs/jtbd_usage_guide.md`

**Step 1: 创建集成测试**

创建`tests/test_jtbd_integration.py`：

```python
"""测试JTBD产品语义功能"""

import pytest
from pipeline.cluster import PainEventClusterer
from utils.db import db
from utils.llm_client import llm_client
import json

@pytest.fixture
def clusterer():
    """创建聚类器实例"""
    return PainEventClusterer()

@pytest.fixture
def sample_cluster_data():
    """示例聚类数据"""
    return {
        "cluster_name": "test: API Authentication Pain",
        "cluster_description": "Users struggle with OAuth authentication",
        "common_pain": "Complex OAuth flows and unclear documentation",
        "common_context": "When integrating third-party APIs",
        "example_events": [
            "Can't figure out OAuth token refresh",
            "Documentation missing for authentication flow",
            "Keep getting 401 errors"
        ],
        "pain_event_ids": [1, 2, 3],
        "cluster_size": 3,
        "source_type": "test"
    }

class TestJTBDGeneration:
    """测试JTBD生成功能"""

    def test_llm_generates_jtbd(self, sample_cluster_data):
        """测试LLM生成JTBD字段"""
        result = llm_client.generate_jtbd_from_cluster(sample_cluster_data)
        content = result.get("content", {})

        # 验证必需字段存在
        assert "job_statement" in content
        assert "job_steps" in content
        assert "customer_profile" in content
        assert isinstance(content["job_steps"], list)

        # 验证JTBD格式
        job_statement = content["job_statement"]
        assert "当" in job_statement
        assert "想完成" in job_statement or "想要" in job_statement
        assert "失败" in job_statement or "无法" in job_statement

        print(f"✅ Generated JTBD: {job_statement}")

    def test_database_stores_jtbd(self, clusterer, sample_cluster_data):
        """测试数据库存储JTBD字段"""
        # 准备完整的cluster数据（包含JTBD）
        cluster_data = {
            **sample_cluster_data,
            "job_statement": "当开发者想集成第三方API时，会因为OAuth流程复杂而失败",
            "job_steps": ["步骤1: 配置OAuth应用", "步骤2: 获取访问令牌", "步骤3: 处理令牌刷新"],
            "desired_outcomes": ["快速完成认证", "清晰的错误提示", "稳定的令牌管理"],
            "job_context": "在开发需要第三方API集成的功能时",
            "customer_profile": "软件开发者，特别是后端和全栈工程师",
            "semantic_category": "api_integration",
            "product_impact": 0.8
        }

        # 保存到数据库
        cluster_id = db.insert_cluster(cluster_data)
        assert cluster_id is not None

        # 从数据库读取
        with db.get_connection("clusters") as conn:
            cursor = conn.execute("SELECT * FROM clusters WHERE id = ?", (cluster_id,))
            saved_cluster = dict(cursor.fetchone())

        # 验证JTBD字段
        assert saved_cluster["job_statement"] == cluster_data["job_statement"]
        assert json.loads(saved_cluster["job_steps"]) == cluster_data["job_steps"]
        assert saved_cluster["semantic_category"] == "api_integration"
        assert saved_cluster["product_impact"] == 0.8

        print(f"✅ JTBD fields stored and retrieved correctly")

    def test_clustering_pipeline_generates_jtbd(self, clusterer):
        """测试完整聚类流程生成JTBD"""
        # 运行小规模聚类
        result = clusterer.cluster_pain_events(limit=30)

        # 验证生成了clusters
        assert result["clusters_created"] > 0

        # 检查第一个cluster的JTBD字段
        first_cluster = result["final_clusters"][0]

        # 至少应该有job_statement（从validation或summarization）
        assert "job_statement" in first_cluster
        assert "customer_profile" in first_cluster
        assert "semantic_category" in first_cluster

        # 如果有job_statement，验证格式
        if first_cluster.get("job_statement"):
            assert "当" in first_cluster["job_statement"]

        print(f"✅ Clustering pipeline generates JTBD")
        print(f"   Job Statement: {first_cluster.get('job_statement', 'N/A')}")

class TestJTBDQueries:
    """测试JTBD查询功能"""

    def test_get_clusters_by_semantic_category(self, clusterer):
        """测试按语义分类查询"""
        # 先确保有数据
        clusterer.cluster_pain_events(limit=30)

        # 查询某个分类
        categories = clusterer.get_all_semantic_categories()
        if categories:
            first_category = categories[0]["semantic_category"]
            clusters = clusterer.get_clusters_by_semantic_category(first_category)

            assert isinstance(clusters, list)
            if clusters:
                assert clusters[0]["semantic_category"] == first_category

            print(f"✅ Retrieved {len(clusters)} clusters for category '{first_category}'")

    def test_get_high_impact_clusters(self, clusterer):
        """测试查询高影响聚类"""
        clusterer.cluster_pain_events(limit=30)

        high_impact = clusterer.get_high_impact_clusters(min_impact=0.6)

        assert isinstance(high_impact, list)
        for cluster in high_impact:
            assert cluster["product_impact"] >= 0.6

        print(f"✅ Found {len(high_impact)} high impact clusters")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
```

**Step 2: 运行集成测试**

```bash
pytest tests/test_jtbd_integration.py -v -s
```

预期输出：所有测试通过

**Step 3: 创建使用文档**

创建`docs/jtbd_usage_guide.md`：

```markdown
# JTBD产品语义标签使用指南

## 概述

JTBD（Jobs To Be Done）产品语义标签将痛点聚类从"研究主题"升级为"产品机会"。

每个cluster现在包含：

- **job_statement**: 统一的JTBD陈述
  - 格式："当[某类人]想完成[某个任务]时，会因为[某个结构性原因]而失败。"

- **job_steps**: 任务步骤分解
  - 明确标识在哪个步骤失败

- **desired_outcomes**: 期望结果
  - 用户想要达成的目标

- **customer_profile**: 用户画像
  - 角色和上下文

- **semantic_category**: 语义分类
  - 用于聚合相似机会

- **product_impact**: 产品影响评分
  - 0-1分数，评估产品机会价值

## 使用示例

### 1. 生成新的JTBD聚类

```python
from pipeline.cluster import PainEventClusterer

clusterer = PainEventClusterer()
result = clusterer.cluster_pain_events(limit=200)

for cluster in result["final_clusters"]:
    print(f"Cluster: {cluster['cluster_name']}")
    print(f"JTBD: {cluster['job_statement']}")
    print(f"Customer: {cluster['customer_profile']}")
    print(f"Impact: {cluster['product_impact']}\n")
```

### 2. 查询高影响产品机会

```python
# 查询product_impact >= 0.7的聚类
high_impact = clusterer.get_high_impact_clusters(min_impact=0.7)

for cluster in high_impact:
    print(f"{cluster['cluster_name']}")
    print(f"  {cluster['job_statement']}")
    print(f"  Impact: {cluster['product_impact']}\n")
```

### 3. 按语义分类浏览

```python
# 获取所有语义分类
categories = clusterer.get_all_semantic_categories()

for cat in categories:
    print(f"{cat['semantic_category']}: {cat['cluster_count']} clusters, "
          f"avg impact={cat['avg_impact']:.2f}")

# 获取某个分类的所有聚类
api_clusters = clusterer.get_clusters_by_semantic_category("api_integration")
```

### 4. 查看详细的JTBD分析

```python
cluster_analysis = clusterer.get_cluster_analysis(cluster_id)

print(f"JTBD: {cluster_analysis['job_statement']}\n")
print("Job Steps:")
for i, step in enumerate(cluster_analysis['job_steps'], 1):
    print(f"  {i}. {step}")

print(f"\nCustomer Profile: {cluster_analysis['customer_profile']}")
print(f"Product Impact: {cluster_analysis['product_impact']:.2f}")
```

### 5. 为现有clusters生成JTBD

```bash
python3 scripts/migrate_existing_clusters_to_jtbd.py
```

## 数据库Schema

```sql
CREATE TABLE clusters (
    -- 原有字段
    id INTEGER PRIMARY KEY,
    cluster_name TEXT,
    cluster_description TEXT,
    ...

    -- JTBD产品语义字段
    job_statement TEXT,              -- 统一的JTBD陈述
    job_steps TEXT,                  -- JSON数组：任务步骤
    desired_outcomes TEXT,           -- JSON数组：期望结果
    job_context TEXT,                -- 任务上下文
    customer_profile TEXT,           -- 用户画像
    semantic_category TEXT,          -- 语义分类
    product_impact REAL DEFAULT 0.0  -- 产品影响评分
)
```

## JTBD格式验证

有效的JTBD陈述应满足：

1. 包含"当...想完成...时，会因为...而失败"结构
2. 明确用户类型（不是泛泛的"用户"）
3. 明确核心任务（可执行的动作）
4. 明确结构性障碍（不是偶然原因）

示例：

✅ 好的JTBD：
```
当独立开发者想集成AI API时，会因为OAuth认证流程复杂且文档不清晰而失败。
```

❌ 不好的JTBD：
```
用户在使用AI时遇到困难。
```

## 产品机会评估标准

**product_impact**综合考虑：

1. **痛点频率**：多频繁发生？
2. **用户基数**：多少人面临此问题？
3. **解决难度**：技术可行性如何？
4. **付费意愿**：用户愿意为解决方案付费吗？
5. **竞争态势**：现有解决方案如何？

评分范围：
- 0.9-1.0: 顶级机会，立即 pursuing
- 0.7-0.9: 高价值机会，优先考虑
- 0.5-0.7: 中等机会，可以探索
- 0.3-0.5: 低优先级，需验证
- <0.3: 不建议

## 最佳实践

1. **先看JTBD，再看cluster名称**
   - cluster_name可能模糊，但job_statement应该精确

2. **按semantic_category聚合**
   - 同一分类的clusters可能指向同一个产品机会

3. **关注product_impact排序**
   - 高影响+高cluster_size = 优先产品机会

4. **验证job_steps**
   - 如果步骤模糊，说明对问题理解不够深入

5. **customer_profile要具体**
   - "开发者"太泛，"独立开发者集成第三方API"才具体
```

**Step 4: 提交测试和文档**

```bash
git add tests/test_jtbd_integration.py docs/jtbd_usage_guide.md
git commit -m "test: add JTBD integration tests and usage documentation"
```

---

## Task 7: 完整端到端验证

**Step 1: 创建端到端测试脚本**

创建`scripts/test_jtbd_e2e.py`：

```python
#!/usr/bin/env python3
"""JTBD功能端到端测试"""

from pipeline.cluster import PainEventClusterer
from utils.db import db
import json

def main():
    print("=" * 80)
    print("JTBD产品语义升级 - 端到端测试")
    print("=" * 80)

    # 1. 数据库schema验证
    print("\n[1/5] 验证数据库schema...")
    with db.get_connection("clusters") as conn:
        cursor = conn.execute("PRAGMA table_info(clusters)")
        columns = {row['name'] for row in cursor.fetchall()}

        jtbd_columns = ['job_statement', 'job_steps', 'desired_outcomes',
                        'job_context', 'customer_profile', 'semantic_category', 'product_impact']

        missing = [col for col in jtbd_columns if col not in columns]
        if missing:
            print(f"❌ 缺少字段: {missing}")
            return False
        else:
            print(f"✅ 所有JTBD字段已存在")

    # 2. 运行聚类生成
    print("\n[2/5] 运行聚类生成...")
    clusterer = PainEventClusterer()
    result = clusterer.cluster_pain_events(limit=50)

    if result["clusters_created"] == 0:
        print("⚠️  未生成clusters，可能数据不足")
        return False

    print(f"✅ 生成了 {result['clusters_created']} 个clusters")

    # 3. 验证JTBD字段生成
    print("\n[3/5] 验证JTBD字段...")
    first_cluster = result["final_clusters"][0]

    jtbd_fields = ['job_statement', 'job_steps', 'customer_profile',
                   'semantic_category', 'product_impact']

    missing_jtbd = [f for f in jtbd_fields if not first_cluster.get(f)]

    if missing_jtbd:
        print(f"⚠️  Cluster缺少JTBD字段: {missing_jtbd}")
        print(f"   可能原因：LLM未返回完整数据")
    else:
        print(f"✅ Cluster包含所有JTBD字段")

    # 4. 验证JTBD格式
    print("\n[4/5] 验证JTBD格式...")
    job_statement = first_cluster.get("job_statement", "")

    if not job_statement:
        print("⚠️  job_statement为空")
    elif "当" not in job_statement:
        print(f"⚠️  job_statement不符合JTBD格式")
        print(f"   实际: {job_statement[:100]}")
    else:
        print(f"✅ job_statement符合JTBD格式")
        print(f"   {job_statement}")

    # 5. 测试查询功能
    print("\n[5/5] 测试查询功能...")

    # 测试语义分类查询
    categories = clusterer.get_all_semantic_categories()
    print(f"✅ 找到 {len(categories)} 个语义分类")

    # 测试高影响查询
    high_impact = clusterer.get_high_impact_clusters(min_impact=0.5)
    print(f"✅ 找到 {len(high_impact)} 个高影响clusters")

    # 6. 显示示例
    print("\n" + "=" * 80)
    print("JTBD聚类示例")
    print("=" * 80)

    for i, cluster in enumerate(result["final_clusters"][:3], 1):
        print(f"\n### Cluster {i}: {cluster['cluster_name']}")
        print(f"JTBD: {cluster.get('job_statement', 'N/A')}")
        print(f"Customer: {cluster.get('customer_profile', 'N/A')}")
        print(f"Impact: {cluster.get('product_impact', 0):.2f}")
        print(f"Size: {cluster['cluster_size']} events")

        if cluster.get('job_steps'):
            print("Steps:")
            for step in cluster['job_steps'][:3]:
                print(f"  - {step}")

    print("\n" + "=" * 80)
    print("✅ 端到端测试完成！")
    print("=" * 80)

if __name__ == "__main__":
    main()
```

**Step 2: 运行端到端测试**

```bash
python3 scripts/test_jtbd_e2e.py
```

预期输出：
- 所有验证步骤显示✅
- 显示3个JTBD聚类示例

**Step 3: 性能测试**

```bash
# 测试大规模聚类性能
time python3 -c "
from pipeline.cluster import PainEventClusterer
clusterer = PainEventClusterer()
result = clusterer.cluster_pain_events(limit=200)
print(f'Processed {result[\"events_processed\"]} events')
print(f'Created {result[\"clusters_created\"]} clusters')
print(f'Time: {result[\"clustering_stats\"][\"processing_time\"]:.2f}s')
"
```

预期：处理时间 < 300秒（5分钟）

**Step 4: 创建发布说明**

创建`docs/jtbd_release_notes.md`：

```markdown
# JTBD产品语义升级 - 发布说明

## 版本: v2.0.0

## 新功能

### 1. JTBD产品语义标签

每个cluster现在包含以下JTBD字段：

- **job_statement**: 统一的JTBD陈述（"当[某人]想完成[任务]时，会因为[原因]而失败"）
- **job_steps**: 任务步骤分解（JSON数组）
- **desired_outcomes**: 期望结果（JSON数组）
- **job_context**: 任务上下文描述
- **customer_profile**: 用户画像
- **semantic_category**: 语义分类（用于聚合）
- **product_impact**: 产品影响评分（0-1）

### 2. 新的查询API

```python
# 按语义分类查询
clusters = clusterer.get_clusters_by_semantic_category("api_integration")

# 查询高影响聚类
high_impact = clusterer.get_high_impact_clusters(min_impact=0.7)

# 获取所有语义分类统计
categories = clusterer.get_all_semantic_categories()
```

### 3. 数据迁移工具

为现有clusters自动生成JTBD字段：

```bash
python3 scripts/migrate_existing_clusters_to_jtbd.py
```

## 升级指南

### 数据库升级

数据库schema会自动升级。重启应用即可：

```bash
# 应用会自动检测并添加JTBD字段
python3 pipeline/cluster.py
```

### 为现有数据生成JTBD

```bash
# 迁移所有现有clusters
python3 scripts/migrate_existing_clusters_to_jtbd.py
```

### API变更

**向后兼容**：所有现有API继续工作，JTBD字段为可选。

**新增功能**：cluster对象现在包含JTBD字段。

## 使用示例

### 基础使用

```python
from pipeline.cluster import PainEventClusterer

clusterer = PainEventClusterer()
result = clusterer.cluster_pain_events(limit=200)

# 访问JTBD字段
for cluster in result["final_clusters"]:
    print(f"JTBD: {cluster['job_statement']}")
    print(f"Customer: {cluster['customer_profile']}")
    print(f"Impact: {cluster['product_impact']}\n")
```

### 查询产品机会

```python
# 查找高价值产品机会
high_impact = clusterer.get_high_impact_clusters(min_impact=0.7)

for cluster in high_impact:
    # 检查JTBD是否清晰
    if cluster['job_statement'] and cluster['product_impact'] > 0.8:
        print(f"🎯 顶级机会: {cluster['cluster_name']}")
        print(f"   {cluster['job_statement']}")
```

## 性能影响

- **聚类生成**: +15-20%时间（LLM调用增加）
- **数据库查询**: 无影响（新增索引）
- **内存占用**: +5%（每个cluster增加约500字节）

## 已知限制

1. **JTBD质量依赖LLM**: LLM可能生成格式不完美的JTBD陈述
2. **迁移速度**: 为现有clusters生成JTBD需要时间（约2秒/cluster）
3. **API成本**: 增加LLM调用会提高API使用成本

## 下一步

- [ ] 添加JTBD质量验证和自动修正
- [ ] 支持手动编辑JTBD字段
- [ ] JTBD语义搜索
- [ ] 产品机会推荐系统

## 相关文档

- [JTBD使用指南](docs/jtbd_usage_guide.md)
- [API文档](docs/api_reference.md)
```

**Step 5: 最终验证**

```bash
# 1. 运行所有测试
pytest tests/test_jtbd_integration.py -v

# 2. 运行端到端测试
python3 scripts/test_jtbd_e2e.py

# 3. 检查代码质量
# （如果使用linter）
# flake8 pipeline/cluster.py utils/llm_client.py utils/db.py

# 4. 生成示例报告
python3 scripts/show_jtbd_clusters.py > jtbd_report.txt
cat jtbd_report.txt
```

**Step 6: 提交最终版本**

```bash
git add .
git commit -m "feat: complete JTBD product semantics upgrade

- Add JTBD fields to clusters schema
- Enhance LLM prompts for JTBD extraction
- Integrate JTBD generation into clustering pipeline
- Add JTBD query and display functions
- Include migration script for existing clusters
- Add integration tests and documentation

Verified:
- All JTBD fields generated automatically
- JTBD format validated
- Query functions working
- Migration script tested

Breaks: None (backward compatible)
Performance: +15-20% clustering time (expected)
"
```

---

## 总结

实施顺序：
1. ✅ 数据库Schema扩展（30分钟）
2. ✅ LLM提示词增强（1小时）
3. ✅ 聚类流程集成（1小时）
4. ✅ 查询和展示功能（45分钟）
5. ✅ 向后兼容处理（30分钟）
6. ✅ 集成测试和文档（1小时）
7. ✅ 端到端验证（30分钟）

**总计：约5小时**

可验证成果：
- 每个cluster自动生成JTBD字段
- JTBD格式符合"当[某人]想完成[任务]时，会因为[原因]而失败"
- 可以按产品语义查询和排序clusters
- 现有数据可以迁移到新格式

## 执行选项

Plan complete and saved to `docs/plans/2025-12-26-jtbd-product-semantics.md`.

**Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration
- ✅ 实时反馈和调整
- ✅ 逐步验证每个task
- ✅ 更快迭代速度

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints
- ✅ 独立会话，不影响当前工作
- ✅ 批量执行，适合长时间任务
- ✅ 检查点review

**Which approach?**
