好，这一步我们要**把“想法”压成“工程可执行物”**。下面给你的是：**可以直接交给工程师（或者未来的你）开干的版本**。

我会分三层来讲，但整体是一个脚本级系统，不是平台。

---

# 一、整体代码结构（极简但可扩展）

这是一个**单人公司友好**的目录结构：清晰、可替换、不搞过度抽象。

```
reddit_pain_finder/
│
├── config/
│   ├── subreddits.yaml
│   ├── llm.yaml
│   └── thresholds.yaml
│
├── data/
│   ├── raw_posts.db          # 原始抓取
│   ├── filtered_posts.db     # 通过信号过滤
│   ├── pain_events.db        # 痛点原子
│   └── clusters.db           # 聚类与机会
│
├── pipeline/
│   ├── fetch.py              # 你已经会
│   ├── filter_signal.py
│   ├── extract_pain.py
│   ├── embed.py
│   ├── cluster.py
│   ├── map_opportunity.py
│   └── score_viability.py
│
├── prompts/
│   ├── pain_extraction.txt
│   ├── workflow_clustering.txt
│   ├── opportunity_mapping.txt
│   └── viability_scoring.txt
│
├── utils/
│   ├── llm_client.py
│   ├── embedding.py
│   └── db.py
│
└── run_pipeline.py
```

**原则一句话**：

> 每个模块只干一件“人类本来不想干的重复脑力活”。

---

# 二、Pipeline 各模块职责（工程视角）

## 1️⃣ `filter_signal.py` —— 冷血守门员（无 LLM）

**目标**：  
把 Reddit 的“情绪+幻想+炫耀”挡在门外。

### 输入

- raw_posts（title, body, upvotes, comments）
    

### 逻辑

- 规则匹配（痛点句式）
    
- 最低互动阈值（避免零回应独角戏）
    

```python
def is_pain_signal(post) -> bool:
    if post.upvotes < MIN_UPVOTES:
        return False

    text = (post.title + post.body).lower()
    return any(p in text for p in PAIN_PATTERNS)
```

### 输出

- filtered_posts.db
    

> 这是整个系统**ROI 最高的一步**。  
> 写烂一点都比不用强。

---

## 2️⃣ `extract_pain.py` —— 痛点事件抽取（LLM 第一次出场）

### 🎯 任务定义

**只做结构化抽取，不做判断、不做建议。**

### Prompt：`prompts/pain_extraction.txt`

```
You are an information extraction engine.

Your task:
From the following Reddit post, extract concrete PAIN EVENTS.
A pain event is a specific recurring problem experienced by the author,
not opinions, not general complaints.

Rules:
- Do NOT summarize the post
- Do NOT give advice
- If no concrete pain exists, return an empty list
- Be literal and conservative

Output JSON only.

Fields:
- actor: who experiences the problem
- context: what they are trying to do
- problem: the concrete difficulty
- current_workaround: how they currently cope (if any)
- frequency: how often it happens (explicit or inferred)
- emotional_signal: frustration, anxiety, exhaustion, etc.
- mentioned_tools: tools explicitly named

Post:
Title: {{title}}
Body: {{body}}
Subreddit: {{subreddit}}
Upvotes: {{upvotes}}
Comments: {{comments_count}}
```

### 输出（存 DB）

- pain_events（原子级，**不要合并**）
    

---

## 3️⃣ `embed.py` —— 痛点向量化（为聚类服务）

### Embedding 内容（非常关键）

```text
actor + " | " + context + " | " + problem + " | " + current_workaround
```

不是全文，不是情绪。

### 输出

- pain_event_embeddings（id → vector）
    

---

## 4️⃣ `cluster.py` —— 工作流级聚类（LLM 第二次出场）

### 逻辑分两步

#### Step 1：向量近邻（程序）

- cosine similarity
    
- 小规模（1000 条以内）
    

#### Step 2：LLM 判断是否是“同一工作流”

### Prompt：`workflow_clustering.txt`

```
You are analyzing user pain events.

Given the following pain events,
determine whether they belong to the SAME UNDERLYING WORKFLOW problem.

A workflow means:
- the same repeated activity
- where different people fail in similar ways

If yes:
- give the workflow a short descriptive name
If no:
- say they should not be clustered

Return JSON only.

Pain events:
{{pain_event_list}}
```

### 输出

```json
{
  "same_workflow": true,
  "workflow_name": "early-stage customer onboarding"
}
```

---

## 5️⃣ `map_opportunity.py` —— 从痛点到工具缺口（LLM 第三次）

### 🎯 这是创业思考，但要被约束

### Prompt：`opportunity_mapping.txt`

```
You are a brutally practical product thinker.

Given a cluster of pain events that belong to the same workflow:

1. Identify what tools people CURRENTLY use to survive this problem
2. Identify what capability is missing
3. Explain why existing tools fail (too heavy, too generic, etc.)
4. Propose ONE narrow micro-tool opportunity

Rules:
- No platforms
- No marketplaces
- Assume a solo founder building an MVP
- If no viable tool opportunity exists, say so

Return JSON only.

Pain cluster:
{{cluster_summary}}
```

---

## 6️⃣ `score_viability.py` —— 一人公司冷酷评分（LLM 第四次）

### Prompt：`viability_scoring.txt`

```
You are an experienced solo-founder investor.

Score the following idea for a ONE-PERSON COMPANY.

Criteria:
- Daily or weekly pain?
- Clear buyer?
- MVP buildable by one person?
- Crowded market risk?
- Integration complexity?

Score from 0 to 10.

Also list the TOP 3 killer risks.

Return JSON only.

Idea:
{{opportunity_description}}
```

---

# 三、`run_pipeline.py`（总控）

```python
def main():
    fetch_posts()
    filter_signal()
    extract_pain_events()
    embed_pain_events()
    cluster_workflows()
    map_opportunities()
    score_viability()
```

你甚至可以**每天 cron 跑一次**。

---

# 四、一个现实但重要的提醒

这个系统真正的价值，不在于“告诉你做什么”。

而在于：

- 长期积累 **痛点数据库**
    
- 你能看到：
    
    - 哪些痛点三个月还在出现
        
    - 哪些被新工具“消灭”了
        
    - 哪些你已经能背出原帖语气
        

那一刻，你不需要灵感了。


