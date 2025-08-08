# summarize_reddit_posts.py
import os
import json
from pathlib import Path
import time
import sys
import re
from openai import OpenAI # 使用 openai 库
from dotenv import load_dotenv

# --- 配置 ---
# 1. API 配置 (请根据实际情况修改)
#    - 从环境变量或 .env 文件加载 API 密钥 (推荐)
load_dotenv() # 确保 .env 文件中有 SILICONFLOW_API_KEY

API_KEY = os.getenv("SILICONFLOW_API_KEY") # 例如: "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
if not API_KEY:
    raise ValueError("Siliconflow API key not found. Please set SILICONFLOW_API_KEY in your environment or .env file.")

# 2. 初始化 OpenAI 客户端
#    指向 Siliconflow 的 API Base URL
client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.siliconflow.cn/v1" # Siliconflow API endpoint
)

MODEL_NAME = os.getenv("SILICONFLOW_MODEL")  # 默认使用7B模型，避免系统繁忙

# 3. 路径配置
INPUT_DIR = "content/reddit"
OUTPUT_DIR = "output/reddit"
OUTPUT_EXTENSION = ".md"

# 4. Prompt 模板
SYSTEM_PROMPT = "你是知乎上的AI科普专栏作者，以一个关注AI热点的跨国企业中层管理者的身份，用通俗易懂的中文向普通用户分享最新的AI动态。你的目标是用生活化的语言普及AI知识，传递'每个人都能用AI改变生活'的价值观。"

# USER_PROMPT_TEMPLATE 是一个模板，其中 {post_title} 和 {post_text} 将被实际内容替换
USER_PROMPT_TEMPLATE = """
作为一个长期关注AI发展的跨国企业中层管理者，我想和知乎的朋友们分享一篇刚刚在Reddit上看到的AI热门讨论。

**写作目标：**
用最通俗的语言，把这篇技术讨论的核心价值传递给完全没有技术背景的普通用户，让大家明白AI并不是遥不可及的黑科技，而是每个人都能用得上的生活工具。

**写作要求：**
1. **核心思想提炼** - 用比喻或生活化的例子解释这个AI技术/趋势的本质，让大妈都能听懂
2. **讨论焦点** - 总结网友们最关心的实际问题，比如"这个能帮我省多少钱"、"会不会抢我工作"等
3. **生活化应用** - 举3-5个普通人日常能用到的具体场景，比如买菜、做饭、教孩子写作业等
4. **个人体验分享** - 以"我作为一个普通打工人"的角度，聊聊看到这个技术的第一反应和实际尝试的经历
5. **价值传递** - 强调"这个技术对普通人意味着什么"，传递积极拥抱AI的态度
6. **行动建议** - 给出零基础用户开始尝试的简单步骤，比如推荐几个免费工具或APP

**输出格式（中文Markdown，适合知乎体）：**

# {post_title}
*原文讨论：{subreddit_name}社区热门精选*

## 🌟 一句话总结这个技术有多牛
用大白话解释：这玩意儿到底能干啥？

## 🤔 网友都在吵什么？
把技术社区的争论翻译成普通人的疑问：
- 💰 **能省钱吗？** 网友们最关心的经济账
- ⏰ **能省时间吗？** 对996打工人有啥实际好处
- 🚨 **会让我失业吗？** 大家最担心的就业影响

## 🏠 普通人能怎么用上？
分享3-5个接地气的生活场景：
1. **早晨场景**：比如用来...
2. **工作场景**：比如用来...
3. **家庭场景**：比如用来...
4. **学习场景**：比如用来...
5. **娱乐场景**：比如用来...

## 👨‍💼 我的真实体验
作为一个天天坐办公室的普通管理者，我第一次看到这个技术时的反应：
- **第一反应**：这玩意儿靠谱吗？
- **实际尝试**：我具体是怎么试的
- **意外发现**：比我想象中好用的地方
- **踩坑提醒**：大家可能会遇到的问题

## 🎯 给想尝试的朋友的建议
**零基础入门三步走：**
1. **先别花钱**：推荐几个免费的试试水
2. **从小事开始**：不要一上来就想改变世界
3. **加入交流群**：找几个同好一起摸索

## 💡 核心观点
**AI不是取代人类的洪水猛兽，而是像智能手机一样的工具。关键不是技术有多先进，而是我们普通人怎么把它变成生活的小帮手。**

---
## 📖 原文精华摘录

**主贴内容：**
{post_text}

**网友神评：**
{comments_text}
"""

# --- 辅助函数 ---
def call_llm_api(prompt, system_prompt=SYSTEM_PROMPT, model=MODEL_NAME, max_retries=3, retry_delay=5):
    """调用 Siliconflow API (通过 OpenAI 库) 进行分析"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]

    for attempt in range(max_retries + 1):
        try:
            # 使用 OpenAI 库调用 Siliconflow API
            chat_completion = client.chat.completions.create(
                model=model,
                messages=messages,
                # 可以根据需要调整参数
                temperature=0.7, # 稍微提高随机性，使输出更生动
                max_tokens=1500  # 增加输出长度以适应更丰富的内容
            )
            
            # 提取模型回复
            summary_text = chat_completion.choices[0].message.content.strip()
            return summary_text

        except Exception as e: # 捕获 OpenAI 库可能抛出的异常
            print(f"  Error calling API (Attempt {attempt + 1}/{max_retries + 1}): {e}", file=sys.stderr)
            
            # 针对特定的繁忙错误进行特殊处理
            if "System is too busy" in str(e) or "503" in str(e):
                retry_delay *= 2  # 指数退避
                print(f"  System busy, extending retry delay to {retry_delay} seconds...", file=sys.stderr)
                
            if attempt < max_retries:
                print(f"  Retrying in {retry_delay} seconds...", file=sys.stderr)
                time.sleep(retry_delay)
            else:
                print(f"  Failed to get response from API after {max_retries + 1} attempts.", file=sys.stderr)
                # 返回一个友好的错误提示，包含手动处理建议
                return f"**抱歉：** 由于API服务繁忙，暂时无法生成详细分析。建议稍后重试，或者您可以直接阅读下面的原文精华内容。"

    # 理论上不会执行到这里，因为循环里已经处理了
    return "**Error:** Maximum retries exceeded (unexpected)."



def process_json_file(json_file_path, output_dir):
    """处理单个 JSON 文件, 生成 Markdown 文件"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            post_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"  Error reading or parsing {json_file_path}: {e}", file=sys.stderr)
        return

    post_id = post_data.get("id", "unknown_id")
    post_title = post_data.get("title", "")
    post_selftext = post_data.get("selftext", "")
    post_comments = post_data.get("comments", [])
    post_url = post_data.get("url ", post_data.get("url", "#")).strip()

    print(f"Processing post ID: {post_id}")

    # 构建评论文本
    comments_parts = []
    for comment in post_comments:
        author = comment.get("author ", comment.get("author", "Unknown Author")).strip() 
        body = comment.get("body ", comment.get("body", "")).strip()
        score = comment.get("score ", comment.get("score", 0))
        if author and body:
             comments_parts.append(f"**{author}** (Score: {score}):\n{body}\n")
    comments_text = "\n---\n".join(comments_parts) if comments_parts else "No comments available."

    # 构建完整的用户 Prompt（增加subreddit信息）
    full_user_prompt = USER_PROMPT_TEMPLATE.format(
        post_title=post_title,
        post_text=post_selftext,
        comments_text=comments_text,
        post_url=post_url,
        subreddit_name=post_data.get("subreddit", "unknown")
    )

    # 调用 LLM API
    summary_md_content = call_llm_api(full_user_prompt)

    # --- 保存 Markdown 文件 ---
    md_output_file_name = f"{post_id}{OUTPUT_EXTENSION}"
    md_output_file_path = os.path.join(output_dir, md_output_file_name)
    try:
        with open(md_output_file_path, 'w', encoding='utf-8') as f:
            f.write(summary_md_content)
        print(f"  MD summary saved to: {md_output_file_path}")
    except Exception as e:
        print(f"  Error saving MD summary to {md_output_file_path}: {e}", file=sys.stderr)

    # 不再生成JSON文件，只保留MD文件



# --- 主执行逻辑 ---
def main():
    """主函数，遍历目录并处理文件"""
    input_path = Path(INPUT_DIR)
    if not input_path.exists():
        print(f"Error: Input directory '{INPUT_DIR}' does not exist.", file=sys.stderr)
        sys.exit(1)

    output_path = Path(OUTPUT_DIR)
    output_path.mkdir(parents=True, exist_ok=True) # 确保输出目录存在

    # 查找所有 .json 文件
    json_files = list(input_path.glob("*.json"))

    if not json_files:
        print(f"No JSON files found in '{INPUT_DIR}'.")
        return

    # 检查已处理的文件，避免重复处理
    processed_files = [f.stem for f in output_path.glob("*.md")]
    json_files_to_process = [f for f in json_files if f.stem not in processed_files]

    if not json_files_to_process:
        print(f"All {len(json_files)} files have already been processed. Use 'rm output/reddit/*.md' to re-process.")
        return

    print(f"Found {len(json_files)} total JSON files.")
    print(f"Processing {len(json_files_to_process)} new files (skipping {len(processed_files)} already processed).")
    
    processed_count = 0
    for i, json_file in enumerate(json_files_to_process, 1):
        print(f"\n[{i}/{len(json_files_to_process)}] Processing: {json_file.name}")
        process_json_file(json_file, str(output_path))
        processed_count += 1
        
        # 在文件之间添加延迟，避免API速率限制
        if i < len(json_files_to_process):
            print("  Waiting 2 seconds before next file...")
            time.sleep(2)

    print(f"\nProcessing complete. {processed_count} new file(s) analyzed and summaries saved to '{OUTPUT_DIR}'.")

if __name__ == "__main__":
    main()
