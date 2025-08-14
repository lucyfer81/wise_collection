# dashboard.py
import streamlit as st
import pandas as pd
import requests
import json
import sys

# --- Page Configuration ---
st.set_page_config(
    page_title="智能趋势分析仪表盘",
    page_icon="📈",
    layout="wide"
)

# --- Database Connection ---
@st.cache_resource
def get_db_connection():
    """Caches the database connection using HTTP API."""
    try:
        # These secrets are set in the Streamlit Cloud dashboard
        db_url = st.secrets["DB_URL"]
        auth_token = st.secrets["DB_AUTH_TOKEN"]
        
        # Extract database name from URL
        db_name = "wisecollection"
        
        # Create HTTP API URL
        api_url = f"https://{db_url.replace('libsql://', '')}/v2/pipeline"
        
        return {
            'api_url': api_url,
            'auth_token': auth_token,
            'db_name': db_name
        }
    except Exception as e:
        st.error(f"❌ 数据库连接失败: {e}")
        st.error("请确保您已在 Streamlit Cloud 的 Secrets 中正确设置了 DB_URL 和 DB_AUTH_TOKEN。")
        sys.exit(1)

def execute_query(conn_info, query):
    """Execute SQL query using HTTP API"""
    try:
        headers = {
            'Authorization': f'Bearer {conn_info["auth_token"]}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'requests': [
                {
                    'type': 'execute',
                    'stmt': {
                        'sql': query
                    }
                }
            ]
        }
        
        response = requests.post(conn_info['api_url'], headers=headers, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            if 'results' in result and len(result['results']) > 0:
                query_result = result['results'][0]['response']['result']
                if 'rows' in query_result:
                    # Extract values from rows
                    extracted_rows = []
                    for row in query_result['rows']:
                        extracted_row = []
                        for cell in row:
                            if isinstance(cell, dict) and 'value' in cell:
                                extracted_row.append(cell['value'])
                            else:
                                extracted_row.append(cell)
                        extracted_rows.append(extracted_row)
                    return extracted_rows
            return []
        else:
            st.error(f"Query failed: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        st.error(f"Query error: {e}")
        return []

conn = get_db_connection()

# --- Database Table Check ---
try:
    # 首先尝试直接查询topics表
    count_rows = execute_query(conn, "SELECT COUNT(*) FROM topics;")
    if count_rows:
        count = count_rows[0][0]
        st.success(f"✅ 数据库连接成功！topics表包含 {count} 条数据")
    else:
        st.warning("topics表不存在或为空")
        
except Exception as e:
    st.error(f"数据库表检查失败: {e}")

# --- Data Loading Functions ---
@st.cache_data(ttl=600) # Cache data for 10 minutes
def load_data(query, column_names=None):
    """Loads data from the database using a given query."""
    try:
        rows = execute_query(conn, query)
        if rows:
            # Convert rows to DataFrame
            if column_names:
                # Use provided column names
                return pd.DataFrame(rows, columns=column_names)
            elif query.startswith("SELECT"):
                # Extract column names from query
                columns = []
                if "SELECT" in query.upper():
                    # Simple column name extraction
                    select_part = query.upper().split("SELECT")[1].split("FROM")[0].strip()
                    columns = [col.strip() for col in select_part.split(",")]
                
                # Clean up column names
                clean_columns = []
                for col in columns:
                    if " AS " in col.upper():
                        clean_columns.append(col.split(" AS ")[-1].strip())
                    elif "." in col:
                        clean_columns.append(col.split(".")[-1].strip())
                    else:
                        clean_columns.append(col.strip())
                
                return pd.DataFrame(rows, columns=clean_columns)
            else:
                return pd.DataFrame(rows)
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"数据加载失败: {e}")
        return pd.DataFrame()

# --- UI Layout ---
st.title("📈 智能趋势分析仪表盘")
st.markdown("一个用于探索和分析 AI 领域新兴主题的动态仪表盘。")

# --- Sidebar for Filters ---
st.sidebar.header("🔍 筛选与搜索")
search_term = st.sidebar.text_input("在主题摘要中搜索关键词")

# --- Main Content ---
tab1, tab2 = st.tabs(["📅 最新主题概览", "📚 所有主题数据库"])

with tab1:
    st.header("最近分析的主题")
    recent_topics_df = load_data("SELECT created_at, topic_name, topic_keywords, summary_chinese FROM topics ORDER BY created_at DESC LIMIT 50", 
                               column_names=['created_at', 'topic_name', 'topic_keywords', 'summary_chinese'])

    if recent_topics_df.empty:
        st.warning("数据库中还没有任何主题。请先运行分析脚本。")
    else:
        # Apply search filter
        if search_term:
            recent_topics_df = recent_topics_df[recent_topics_df['summary_chinese'].str.contains(search_term, case=False, na=False)]

        st.metric("总主题数", len(recent_topics_df))
        st.dataframe(recent_topics_df, use_container_width=True)

with tab2:
    st.header("主题数据库全览")
    all_topics_df = load_data("SELECT id, created_at, topic_name, topic_keywords, summary_english, summary_chinese FROM topics ORDER BY id DESC",
                               column_names=['id', 'created_at', 'topic_name', 'topic_keywords', 'summary_english', 'summary_chinese'])

    if all_topics_df.empty:
        st.warning("数据库中还没有任何主题。")
    else:
        # Apply search filter
        if search_term:
            all_topics_df = all_topics_df[all_topics_df['summary_chinese'].str.contains(search_term, case=False, na=False) | all_topics_df['summary_english'].str.contains(search_term, case=False, na=False)]

        st.dataframe(all_topics_df, use_container_width=True)

        # Expander for details
        st.subheader("查看单个主题详情")
        selected_id = st.selectbox("选择一个主题ID进行查看:", options=all_topics_df['id'])
        if selected_id:
            selected_topic = all_topics_df[all_topics_df['id'] == selected_id].iloc[0]
            st.markdown(f"### {selected_topic['topic_name']}")
            st.markdown("#### 中文战略简报")
            st.markdown(selected_topic['summary_chinese'], unsafe_allow_html=True)
            with st.expander("查看英文原文"):
                st.markdown(selected_topic['summary_english'], unsafe_allow_html=True)

st.sidebar.info("报告由 Wise Collection 项目自动生成。")
