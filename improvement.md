# Python 项目 "wise_collection" 改进建议

这是一个对当前 Python 项目代码的分析与改进建议。该项目展示了强大的数据处理和 AI 集成能力，以下建议旨在使其更加健壮、可维护和高效。

## 1. 整体项目级改进

这些建议适用于项目中的所有脚本。

### 1.1. 统一配置管理

**问题**: `analyze_topics.py`, `curate.py`, `reddit_collection.py` 等多个文件都在文件顶部硬编码了配置变量（如目录路径、模型名称、DBSCAN 参数等）。这使得修改配置变得困难且容易出错。

**建议**:
创建一个中央配置文件，例如 `config.py` 或 `config.json`，来管理所有共享的配置。

**示例 (`config.py`)**:
```python
# config.py
from pathlib import Path

# --- Directories ---
BASE_DIR = Path(__file__).parent
CONTENT_DIR = BASE_DIR / "content"
OUTPUT_DIR = BASE_DIR / "output"
REDDIT_RAW_DIR = CONTENT_DIR / "reddit"
REDDIT_CURATED_DIR = CONTENT_DIR / "reddit_english_curated"
REJECTED_DIR = CONTENT_DIR / "processed_json"
TOPICS_OUTPUT_DIR = OUTPUT_DIR / "topics"

# --- Database ---
DATABASE_FILE = BASE_DIR / "topics_database.db"

# --- API & Models ---
# API Keys should remain in .env
ANALYSIS_MODEL = "Qwen/Qwen3-32B"
TRANSLATION_MODEL = "Qwen/Qwen2.5-7B-Instruct"
JUDGE_MODEL = "Qwen/Qwen2.5-7B-Instruct"

# --- Algorithm Parameters ---
DBSCAN_EPS = 0.8
DBSCAN_MIN_SAMPLES = 2
COMMENTS_TO_FETCH = 20
```
然后，在其他脚本中导入这些配置：
```python
# analyze_topics.py
import config

# 使用 config.REDDIT_CURATED_DIR 而不是硬编码的字符串
input_path = config.REDDIT_CURATED_DIR
```

### 1.2. 创建共享工具模块 (`utils.py`)

**问题**: `analyze_topics.py` 中的 `call_llm` 函数和 `curate.py` 中的 `get_llm_judgement` 函数功能非常相似。数据库连接逻辑也在多个地方重复。

**建议**:
创建一个 `utils.py` 文件来存放这些通用函数。

**示例 (`utils.py`)**:
```python
# utils.py
import os
import json
import sqlite3
from openai import OpenAI
from dotenv import load_dotenv
import config # 导入中央配置

load_dotenv()
API_KEY = os.getenv("SILICONFLOW_API_KEY")
if not API_KEY:
    raise ValueError("Siliconflow API key not found.")

client = OpenAI(api_key=API_KEY, base_url="https://api.siliconflow.cn/v1")

def call_llm(model: str, prompt: str, temperature: float = 0.3, max_tokens: int = 3000) -> str | None:
    """通用 LLM 调用函数。"""
    messages = [{"role": "user", "content": prompt}]
    try:
        chat_completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"LLM call failed: {e}") # 建议使用 logging 模块
        return None

def get_db_connection():
    """获取数据库连接。"""
    return sqlite3.connect(config.DATABASE_FILE)
```

### 1.3. 依赖管理 (`requirements.txt`)

**问题**: 项目没有明确的依赖列表，这使得在新环境中部署变得困难。

**建议**:
创建一个 `requirements.txt` 文件。
```
# requirements.txt
praw
python-dotenv
scikit-learn
openai
pandas
```
可以使用 `pip freeze > requirements.txt` 命令生成，但最好手动清理一下，只保留顶级依赖。

### 1.4. 使用 `logging` 模块

**问题**: 所有脚本都使用 `print()` 来输出状态、警告和错误。

**建议**:
使用 Python 的 `logging` 模块。它可以提供更灵活的控制，例如：
-   按严重性（DEBUG, INFO, WARNING, ERROR）过滤日志。
-   轻松地将日志输出到文件而不是控制台。
-   包含时间戳和模块名，方便调试。

---

## 2. 文件级改进建议

### 2.1. `curate.py`

**🔴 关键缺陷修复**:
**问题**: 在 `main` 函数中，用于保存文件的逻辑存在缺陷。`if destination.is_dir():` 永远为 `False`，导致所有文件（无论是接受还是拒绝）都只通过 `json_file.rename(destination)` 被移动。这意味着为“接受”的帖子生成的 `curation_metadata` **从未被保存**。

**修正建议**:
重构文件处理逻辑，确保在接受帖子时，将包含新元数据的内容写入新文件。

```python
# curate.py -> main() 循环内
# ...
            judgement = get_llm_judgement(data)
            
            if judgement.get("is_rejected"):
                reason = judgement.get('rejection_reason', 'Unknown reason')
                print(f" ❌ REJECTED ({reason})")
                destination = rejected_path / json_file.name
                json_file.rename(destination) # 直接移动原文件
                rejected_count += 1
            else:
                print(f" ✅ ACCEPTED (Type: {judgement.get('content_type')})")
                # 添加元数据并写入新文件
                data['curation_metadata'] = judgement
                destination = curated_path / json_file.name
                with open(destination, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                json_file.unlink() # 删除收件箱中的原文件
                accepted_count += 1
# ...
```

### 2.2. `analyze_topics.py`

**问题**:
1.  **数据库连接**: `init_db` 和 `log_topic_to_db` 每次都打开和关闭数据库连接，效率较低。
2.  **代码可读性**: `[clusters[label].append(posts[i]) for i, label in enumerate(labels)]` 这种列表推导式被用于其副作用（填充字典），这不符合 Python 的最佳实践，降低了可读性。

**建议**:
1.  在 `main` 函数开始时建立一次数据库连接，并将其传递给需要的函数。
2.  使用标准的 `for` 循环来填充 `clusters` 字典。

```python
# analyze_topics.py -> main()
def main():
    # ...
    conn = sqlite3.connect(DATABASE_FILE)
    init_db(conn) # 修改 init_db 以接受连接对象

    # ...
    clusters = defaultdict(list)
    for i, label in enumerate(labels):
        clusters[label].append(posts[i]) # 更清晰的写法

    # ... 循环内
        log_topic_to_db(conn, topic_name, ...) # 传递连接对象
    
    conn.close() # 在脚本末尾关闭连接
# ...
```

### 2.3. `reddit_collection.py`

**问题**:
1.  **路径处理**: 该文件使用 `os.path.join`，而项目中其他脚本已在使用更现代、更面向对象的 `pathlib.Path`。
2.  **函数过长**: `process_and_save_submission` 函数承担了太多责任：过滤、检查交叉帖子、获取评论、构建数据结构和保存文件。

**建议**:
1.  统一使用 `pathlib.Path` 进行所有路径操作。
2.  将 `process_and_save_submission` 分解为更小的辅助函数，例如 `is_high_quality()`, `fetch_comments()`, `save_post_data()`。

### 2.4. `trend_analyzer.py`

**问题**:
1.  **数据库效率**: 每个函数（`query_topics_by_keywords`, `get_related_keywords` 等）都重新连接数据库。对于一个交互式工具，这会带来不必要的开销。
2.  **“魔数” (Magic Numbers)**: `calculate_relevance_score` 中的权重（30, 15, 20, 10, 5）是硬编码的“魔数”，其含义不明确。
3.  **UI 字符串**: 交互界面中的提示语将中英文硬编码在一起（例如 `"🔍 智能趋势分析工具 | Intelligent Trend Analysis Tool"`），不利于维护和未来的国际化。

**建议**:
1.  在 `interactive_search` 函数的开头建立一个数据库连接，并将其传递给其他查询函数。
2.  将权重定义为有意义的常量。
    ```python
    # trend_analyzer.py
    SCORE_EXACT_KEYWORD = 30
    SCORE_PARTIAL_KEYWORD = 15
    # ...
    ```
3.  为 UI 文本创建一个字典，以便于管理。
    ```python
    # trend_analyzer.py
    UI_TEXT = {
        "main_title": "🔍 智能趋势分析工具 | Intelligent Trend Analysis Tool",
        "options": "选项 | Options:",
        # ...
    }
    print(UI_TEXT["main_title"])
    ```
