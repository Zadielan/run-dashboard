import streamlit as st
import anthropic
import json
import os
import time
from stravalib import Client
import pandas as pd

# ============================================================
STRAVA_CLIENT_ID     = st.secrets["STRAVA_CLIENT_ID"]
STRAVA_CLIENT_SECRET = st.secrets["STRAVA_CLIENT_SECRET"]
CLAUDE_API_KEY       = st.secrets["CLAUDE_API_KEY"]
REDIRECT_URI         = "https://run-dashboard-dnsuxhdltqm8mlquhnhxb6.streamlit.app/"
# ============================================================

st.set_page_config(page_title="跑步数据", page_icon="🏃", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* 背景 */
.stApp { background: #f0f2f6; }

/* 隐藏 streamlit 默认元素 */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2rem; padding-bottom: 2rem; }

/* 大标题 */
.page-title {
    font-size: 2rem;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 4px;
}
.page-subtitle {
    color: #6b7280;
    font-size: 0.9rem;
    margin-bottom: 1.5rem;
}

/* 统计卡片 */
.stat-card {
    background: white;
    border-radius: 16px;
    padding: 20px 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.04);
    border-left: 4px solid;
}
.stat-card.orange { border-color: #f97316; }
.stat-card.green  { border-color: #22c55e; }
.stat-card.blue   { border-color: #3b82f6; }
.stat-card.red    { border-color: #ef4444; }
.stat-value { font-size: 2rem; font-weight: 700; color: #1a1a2e; line-height: 1.2; }
.stat-label { font-size: 0.78rem; color: #6b7280; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.05em; }

/* 分析卡片 */
.analysis-card {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border-radius: 20px;
    padding: 28px 32px;
    color: white;
    box-shadow: 0 8px 32px rgba(26,26,46,0.2);
    margin: 1rem 0;
}
.analysis-card h3 { font-size: 1rem; font-weight: 600; opacity: 0.7; margin-bottom: 12px; letter-spacing: 0.05em; }
.analysis-card p { line-height: 1.75; font-size: 0.95rem; opacity: 0.92; }

/* 图表容器 */
.chart-card {
    background: white;
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    margin-bottom: 1rem;
}

/* 对话气泡 */
.chat-user {
    background: #3b82f6;
    color: white;
    border-radius: 18px 18px 4px 18px;
    padding: 10px 16px;
    margin: 6px 0;
    margin-left: 20%;
    font-size: 0.92rem;
}
.chat-ai {
    background: white;
    color: #1a1a2e;
    border-radius: 18px 18px 18px 4px;
    padding: 10px 16px;
    margin: 6px 0;
    margin-right: 20%;
    font-size: 0.92rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    line-height: 1.65;
}

/* Tab 样式 */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background: transparent;
}
.stTabs [data-baseweb="tab"] {
    background: white;
    border-radius: 10px;
    padding: 6px 20px;
    font-weight: 500;
}
.stTabs [aria-selected="true"] {
    background: #1a1a2e !important;
    color: white !important;
}

/* 侧边栏 */
[data-testid="stSidebar"] {
    background: white;
    border-right: 1px solid #e5e7eb;
}

/* 按钮 */
.stButton button {
    border-radius: 10px;
    font-weight: 500;
    border: none;
    background: #1a1a2e;
    color: white;
}
.stButton button:hover { background: #2d2d4e; }
</style>
""", unsafe_allow_html=True)


# ---------- Strava OAuth ----------

def get_strava_client():
    if "strava_token" not in st.session_state:
        return None
    token = st.session_state.strava_token
    strava = Client()
    if token["expires_at"] < time.time():
        new_token = strava.refresh_access_token(
            client_id=STRAVA_CLIENT_ID,
            client_secret=STRAVA_CLIENT_SECRET,
            refresh_token=token["refresh_token"]
        )
        st.session_state.strava_token = dict(new_token)
        token = st.session_state.strava_token
    strava.access_token = token["access_token"]
    return strava

def get_auth_url():
    strava = Client()
    return strava.authorization_url(
        client_id=STRAVA_CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        scope=["activity:read_all"]
    )

def handle_oauth_callback():
    params = st.query_params
    if "code" in params and "error" not in params:
        strava = Client()
        token = strava.exchange_code_for_token(
            client_id=STRAVA_CLIENT_ID,
            client_secret=STRAVA_CLIENT_SECRET,
            code=params["code"]
        )
        st.session_state.strava_token = dict(token)
        st.query_params.clear()
        return True
    return False


# ---------- 数据 ----------

def fetch_runs(strava, limit=30):
    runs = []
    for activity in strava.get_activities(limit=limit):
        if activity.type != "Run":
            continue
        distance_km = round(float(activity.distance) / 1000, 2)
        duration_min = round(activity.moving_time.total_seconds() / 60, 1)
        pace = round(duration_min / distance_km, 2) if distance_km > 0 else None
        runs.append({
            "date": str(activity.start_date)[:10],
            "name": activity.name,
            "distance": distance_km,
            "duration": duration_min,
            "pace": pace,
            "heartrate": activity.average_heartrate,
            "elevation": round(float(activity.total_elevation_gain), 1) if activity.total_elevation_gain else 0,
        })
    runs.sort(key=lambda x: x["date"])
    return runs

def analyze(runs):
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    prompt = f"""我最近的跑步数据（{len(runs)} 次）：

{json.dumps(runs, ensure_ascii=False, indent=2)}

请用中文分析（简洁）：
1. 训练量和配速趋势
2. 亮点和需要改进的地方
3. 接下来2周的具体训练建议

不要用 markdown 表格，语言自然流畅。"""
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text

def chat_with_claude(user_msg, runs, history):
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    system = f"""你是一个跑步教练助手。用户的跑步数据如下：

{json.dumps(runs, ensure_ascii=False, indent=2)}

根据这些数据回答用户的问题，用中文，简洁实用。"""
    messages = []
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_msg})
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=system,
        messages=messages
    )
    return msg.content[0].text


# ---------- 侧边栏 ----------

with st.sidebar:
    st.markdown("### 🏃 跑步助手")
    st.divider()
    limit = st.slider("显示最近几次", 10, 50, 20)
    refresh = st.button("🔄 刷新数据", use_container_width=True)
    st.divider()
    if st.button("重新授权 Strava", use_container_width=True):
        st.session_state.clear()
        st.rerun()


# ---------- 主内容 ----------

st.markdown('<div class="page-title">🏃 我的跑步数据</div>', unsafe_allow_html=True)

# 处理 OAuth 回调
if "code" in st.query_params:
    with st.spinner("正在完成授权..."):
        handle_oauth_callback()
    st.rerun()

# 授权检查
strava = get_strava_client()
if strava is None:
    st.markdown('<div class="page-subtitle">连接 Strava 开始分析你的跑步数据</div>', unsafe_allow_html=True)
    auth_url = get_auth_url()
    st.markdown(f'''
        <a href="{auth_url}" target="_self" style="
            display:inline-block;
            background:#1a1a2e;
            color:white;
            padding:12px 24px;
            border-radius:10px;
            font-weight:500;
            text-decoration:none;
            font-size:1rem;
        ">🔗 连接 Strava 账号</a>
    ''', unsafe_allow_html=True)
    st.stop()

# 获取数据
if "runs" not in st.session_state or refresh:
    with st.spinner("正在同步 Strava 数据..."):
        st.session_state.runs = fetch_runs(strava, limit=limit)
    if "analysis" in st.session_state:
        del st.session_state["analysis"]

runs = st.session_state.runs
if not runs:
    st.warning("没有找到跑步记录")
    st.stop()

last_run = runs[-1]["date"]
st.markdown(f'<div class="page-subtitle">最近 {len(runs)} 次跑步 · 最后同步：{last_run}</div>', unsafe_allow_html=True)

# 统计卡片
total_km = round(sum(r["distance"] for r in runs), 1)
valid_paces = [r["pace"] for r in runs if r["pace"]]
avg_pace = round(sum(valid_paces) / len(valid_paces), 2) if valid_paces else 0
best_pace = min(valid_paces) if valid_paces else 0
longest = max(r["distance"] for r in runs)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f'<div class="stat-card orange"><div class="stat-value">{total_km}</div><div class="stat-label">总里程 km</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="stat-card green"><div class="stat-value">{len(runs)}</div><div class="stat-label">跑步次数</div></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="stat-card blue"><div class="stat-value">{avg_pace}</div><div class="stat-label">平均配速 min/km</div></div>', unsafe_allow_html=True)
with c4:
    st.markdown(f'<div class="stat-card red"><div class="stat-value">{longest}</div><div class="stat-label">最长单次 km</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 图表 + 对话 两列布局
left, right = st.columns([3, 2])

with left:
    df = pd.DataFrame(runs)
    df["date"] = pd.to_datetime(df["date"])

    tab1, tab2, tab3 = st.tabs(["📈 配速趋势", "📊 距离", "❤️ 心率"])
    with tab1:
        st.line_chart(df.set_index("date")["pace"], color="#f97316", height=220)
        st.caption("min/km · 越低越快")
    with tab2:
        st.bar_chart(df.set_index("date")["distance"], color="#22c55e", height=220)
        st.caption("单次距离 km")
    with tab3:
        hr_df = df[df["heartrate"].notna()]
        if not hr_df.empty:
            st.line_chart(hr_df.set_index("date")["heartrate"], color="#ef4444", height=220)
            st.caption("平均心率 bpm")
        else:
            st.info("没有心率数据")

    # Claude 分析
    if "analysis" not in st.session_state:
        with st.spinner("Claude 分析中..."):
            st.session_state.analysis = analyze(runs)
    st.markdown(f"""
    <div class="analysis-card">
        <h3>✨ CLAUDE 分析</h3>
        <p>{st.session_state.analysis.replace(chr(10), '<br>')}</p>
    </div>
    """, unsafe_allow_html=True)

    # 详细记录
    with st.expander("查看所有记录"):
        display_df = df[["date","name","distance","pace","heartrate","elevation"]].copy()
        display_df.columns = ["日期","名称","距离(km)","配速","心率","爬升(m)"]
        display_df["日期"] = display_df["日期"].dt.strftime("%Y-%m-%d")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

with right:
    st.markdown("### 💬 问 Claude")
    st.caption("可以问任何关于你训练的问题")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # 显示对话历史
    chat_container = st.container(height=420)
    with chat_container:
        if not st.session_state.chat_history:
            st.markdown("""
            <div style="color:#9ca3af; font-size:0.85rem; padding:12px 0;">
            💡 试试问：<br>
            · 我下周应该怎么跑？<br>
            · 我的配速为什么没提升？<br>
            · 我适合备战半马吗？
            </div>
            """, unsafe_allow_html=True)
        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                content = msg["content"].replace("\n", "<br>")
                st.markdown(f'<div class="chat-ai">{content}</div>', unsafe_allow_html=True)

    # 输入框
    with st.form("chat_form", clear_on_submit=True):
        col_input, col_btn = st.columns([5, 1])
        with col_input:
            user_input = st.text_input("", placeholder="问点什么...", label_visibility="collapsed")
        with col_btn:
            send = st.form_submit_button("发送")

    if send and user_input.strip():
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.spinner(""):
            reply = chat_with_claude(user_input, runs, st.session_state.chat_history[:-1])
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        st.rerun()

    if st.session_state.chat_history:
        if st.button("清空对话", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()
