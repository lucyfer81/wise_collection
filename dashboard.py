# dashboard.py
import streamlit as st
import pandas as pd
import libsql
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
    """Caches the database connection."""
    try:
        # These secrets are set in the Streamlit Cloud dashboard
        db_url = st.secrets["DB_URL"]
        auth_token = st.secrets["DB_AUTH_TOKEN"]
        conn = libsql.connect(database="", sync_url=db_url, auth_token=auth_token)
        print("✅ Database connection successful.")
        return conn
    except Exception as e:
        st.error(f"❌ 数据库连接失败: {e}")
        st.error("请确保您已在 Streamlit Cloud 的 Secrets 中正确设置了 DB_URL 和 DB_AUTH_TOKEN。")
        sys.exit(1)

conn = get_db_connection()

# --- Debug Database Connection ---
try:
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    st.write(f"数据库中的表: {tables}")
    
    if not any('topics' in table for table in tables):
        st.warning("topics表不存在，正在创建...")
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            topic_name TEXT NOT NULL,
            topic_keywords TEXT,
            summary_english TEXT,
            summary_chinese TEXT,
            post_count INTEGER DEFAULT 0,
            avg_score REAL DEFAULT 0.0,
            cluster_id INTEGER,
            file_name TEXT
        );
        """
        cursor.execute(create_table_sql)
        conn.commit()
        st.success("topics表创建成功")
    else:
        st.success("topics表已存在")
        
except Exception as e:
    st.error(f"数据库调试失败: {e}")

# --- Data Loading Functions ---
@st.cache_data(ttl=600) # Cache data for 10 minutes
def load_data(query):
    """Loads data from the database using a given query."""
    try:
        return pd.read_sql_query(query, conn)
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
    recent_topics_df = load_data("SELECT created_at, topic_name, topic_keywords, summary_chinese FROM topics ORDER BY created_at DESC LIMIT 50")

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
    all_topics_df = load_data("SELECT id, created_at, topic_name, topic_keywords, summary_english, summary_chinese FROM topics ORDER BY id DESC")

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
