import streamlit as st
import anthropic
import json
import os
import time
import base64
import tempfile
import requests as http_req
import garth
from stravalib import Client
from datetime import date, timedelta
import pandas as pd

# ============================================================
STRAVA_CLIENT_ID     = st.secrets["STRAVA_CLIENT_ID"]
STRAVA_CLIENT_SECRET = st.secrets["STRAVA_CLIENT_SECRET"]
CLAUDE_API_KEY       = st.secrets["CLAUDE_API_KEY"]
STRAVA_REFRESH_TOKEN = st.secrets["STRAVA_REFRESH_TOKEN"]
GARMIN_OAUTH1        = st.secrets["GARMIN_OAUTH1"]
GARMIN_OAUTH2        = st.secrets["GARMIN_OAUTH2"]
GARMIN_USER_ID       = "119995800"
# ============================================================

st.set_page_config(page_title="健康数据", page_icon="🏃", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #f0f2f6; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2rem; padding-bottom: 2rem; }
.page-title { font-size: 2rem; font-weight: 700; color: #1a1a2e; margin-bottom: 4px; }
.page-subtitle { color: #6b7280; font-size: 0.9rem; margin-bottom: 1.5rem; }
.stat-card { background: white; border-radius: 16px; padding: 16px 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); border-left: 4px solid; margin-bottom: 8px; }
.stat-card.orange { border-color: #f97316; }
.stat-card.green  { border-color: #22c55e; }
.stat-card.blue   { border-color: #3b82f6; }
.stat-card.red    { border-color: #ef4444; }
.stat-card.purple { border-color: #a855f7; }
.stat-card.teal   { border-color: #14b8a6; }
.stat-value { font-size: 1.8rem; font-weight: 700; color: #1a1a2e; line-height: 1.2; }
.stat-label { font-size: 0.75rem; color: #6b7280; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
.analysis-card { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border-radius: 20px; padding: 24px 28px; color: white;
    box-shadow: 0 8px 32px rgba(26,26,46,0.2); margin: 1rem 0; }
.analysis-card h3 { font-size: 0.9rem; font-weight: 600; opacity: 0.7; margin-bottom: 10px; letter-spacing: 0.05em; }
.analysis-card p { line-height: 1.75; font-size: 0.92rem; opacity: 0.92; }
.health-card { background: white; border-radius: 16px; padding: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 12px; }
.health-card h4 { font-size: 0.85rem; font-weight: 600; color: #6b7280;
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; }
.chat-user { background: #3b82f6; color: white; border-radius: 18px 18px 4px 18px;
    padding: 10px 16px; margin: 6px 0; margin-left: 20%; font-size: 0.92rem; }
.chat-ai { background: white; color: #1a1a2e; border-radius: 18px 18px 18px 4px;
    padding: 10px 16px; margin: 6px 0; margin-right: 20%; font-size: 0.92rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08); line-height: 1.65; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; background: transparent; }
.stTabs [data-baseweb="tab"] { background: white; border-radius: 10px; padding: 6px 16px; font-weight: 500; }
.stTabs [aria-selected="true"] { background: #1a1a2e !important; color: white !important; }
[data-testid="stSidebar"] { background: white; border-right: 1px solid #e5e7eb; }
.stButton button { border-radius: 10px; font-weight: 500; border: none; background: #1a1a2e; color: white; }
.stButton button:hover { background: #2d2d4e; }
</style>
""", unsafe_allow_html=True)


# ---------- Strava ----------

def get_strava_client():
    if "strava_token" in st.session_state:
        token = st.session_state.strava_token
        if token["expires_at"] > time.time():
            strava = Client()
            strava.access_token = token["access_token"]
            return strava
    strava = Client()
    token = strava.refresh_access_token(
        client_id=STRAVA_CLIENT_ID,
        client_secret=STRAVA_CLIENT_SECRET,
        refresh_token=STRAVA_REFRESH_TOKEN
    )
    st.session_state.strava_token = dict(token)
    strava.access_token = token["access_token"]
    return strava


BERLIN_DATE = date(2026, 9, 27)  # 柏林马拉松

def fetch_runs(strava, limit=50):
    runs = []
    for activity in strava.get_activities(limit=limit):
        if activity.type != "Run":
            continue
        if not activity.distance or float(activity.distance) == 0:
            continue
        distance_km = round(float(activity.distance) / 1000, 2)
        distance_m = float(activity.distance)
        mt = activity.moving_time
        if mt is None:
            continue
        duration_sec = mt.total_seconds() if hasattr(mt, 'total_seconds') else int(mt)
        duration_min = round(duration_sec / 60, 1)
        pace = round(duration_min / distance_km, 2) if distance_km > 0 else None
        # 步频：Strava 返回单脚步频，×2 得到双脚 SPM
        cadence_raw = activity.average_cadence
        cadence = round(float(cadence_raw) * 2) if cadence_raw else None
        # 步幅（cm）= 距离 / 总步数
        stride_cm = round(distance_m / (cadence * duration_min) * 100) if cadence and duration_min > 0 else None
        runs.append({
            "date": str(activity.start_date)[:10],
            "name": activity.name,
            "distance": distance_km,
            "duration": duration_min,
            "pace": pace,
            "heartrate": activity.average_heartrate,
            "max_heartrate": activity.max_heartrate,
            "elevation": round(float(activity.total_elevation_gain), 1) if activity.total_elevation_gain else 0,
            "cadence": cadence,
            "stride_cm": stride_cm,
        })
    runs.sort(key=lambda x: x["date"])
    return runs


# ---------- Garmin ----------

GARMIN_DATA_URL = "https://raw.githubusercontent.com/Zadielan/run-dashboard/main/garmin_data.json"
CYCLE_DATA_URL  = "https://raw.githubusercontent.com/Zadielan/run-dashboard/main/cycle_data.json"

PHASE_INFO = {
    "月经期": {
        "emoji": "🔴", "color": "#ef4444",
        "tip": "低能量期，适合轻松慢跑、瑜伽、散步。避免高强度训练，多补铁和水分。",
        "hrv": "HRV 通常偏低，休息优先。"
    },
    "卵泡期": {
        "emoji": "🌱", "color": "#22c55e",
        "tip": "精力逐渐上升，适合提速训练、力量训练，这是提升成绩的好时机。",
        "hrv": "HRV 开始回升，身体恢复力强。"
    },
    "排卵期": {
        "emoji": "⚡", "color": "#f97316",
        "tip": "精力巅峰！适合冲击配速 PR、高强度间歇，把握这个窗口期。",
        "hrv": "HRV 通常最高，训练适应性最好。"
    },
    "黄体期": {
        "emoji": "🌙", "color": "#a855f7",
        "tip": "精力下降，体温升高，心率偏高属正常。适合中低强度，重视睡眠和蛋白质摄入。",
        "hrv": "HRV 可能下降，不必强迫完成计划。"
    },
}

def fetch_garmin_data():
    if "garmin_data" in st.session_state:
        return st.session_state.garmin_data
    try:
        r = http_req.get(GARMIN_DATA_URL, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        data = {"error": f"读取 Garmin 数据失败: {e}"}
    st.session_state.garmin_data = data
    return data

def fetch_cycle_data():
    if "cycle_data" in st.session_state:
        return st.session_state.cycle_data
    try:
        r = http_req.get(CYCLE_DATA_URL, timeout=10)
        r.raise_for_status()
        data = r.json()
    except:
        data = []
    st.session_state.cycle_data = data
    return data


# ---------- Claude ----------

def comprehensive_analysis(runs, garmin, daily_log, cycle_today=None):
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    sleep_text = ""
    hrv_text = ""
    strength_text = ""

    if garmin.get("sleep"):
        s = garmin["sleep"]
        sleep_text = f"睡眠（昨晚）：总时长 {s['total_hours']}h，深睡 {s['deep_min']}min，REM {s['rem_min']}min，体能电量变化 {s.get('body_battery_change', '未知')}，静息心率 {s.get('resting_hr', '未知')} bpm"

    if garmin.get("hrv"):
        h = garmin["hrv"]
        hrv_text = f"HRV：昨晚均值 {h['last_night_avg']}，周均值 {h['weekly_avg']}，基准范围 {h['baseline_low']}-{h['baseline_high']}，状态 {h['status']}"

    if garmin.get("strength"):
        strength_text = f"最近力量训练：{json.dumps(garmin['strength'], ensure_ascii=False)}"

    if cycle_today and cycle_today.get("cycle_phase"):
        cycle_text = f"生理周期：{cycle_today['cycle_phase']}，第 {cycle_today.get('cycle_day', '?')} 天"
    elif daily_log.get('cycle_day'):
        cycle_text = f"生理周期：第 {daily_log.get('cycle_day', '未知')} 天，阶段 {daily_log.get('cycle_phase', '未知')}"
    else:
        cycle_text = ""
    nutrition_text = f"今日摄入：{daily_log.get('nutrition_notes', '')}" if daily_log.get('nutrition_notes') else ""

    recent_runs = runs[-5:] if len(runs) >= 5 else runs

    # 跑步动态（Garmin 详细数据）
    garmin_runs = garmin.get("garmin_runs", [])
    form_text = ""
    if garmin_runs:
        gr = garmin_runs[0]
        parts = []
        if gr.get("cadence_spm"): parts.append(f"步频{gr['cadence_spm']}SPM")
        if gr.get("stride_length_m"): parts.append(f"步幅{gr['stride_length_m']}m")
        if gr.get("vertical_oscillation_cm"): parts.append(f"垂直振幅{gr['vertical_oscillation_cm']}cm")
        if gr.get("vertical_ratio_pct"): parts.append(f"垂直振幅比{gr['vertical_ratio_pct']}%")
        if gr.get("ground_contact_ms"): parts.append(f"触地时间{gr['ground_contact_ms']}ms")
        if gr.get("aerobic_te"): parts.append(f"有氧训练效果{gr['aerobic_te']}")
        if gr.get("training_load"): parts.append(f"训练负荷{round(gr['training_load'])}")
        if garmin.get("vo2max"): parts.append(f"VO2Max={garmin['vo2max']}")
        form_text = "最近一次跑步Garmin数据：" + "，".join(parts) if parts else ""
    else:
        cadences = [r["cadence"] for r in recent_runs if r.get("cadence")]
        avg_cadence = round(sum(cadences)/len(cadences)) if cadences else None
        form_text = f"近期平均步频 {avg_cadence} SPM" if avg_cadence else ""

    days_left = (BERLIN_DATE - date.today()).days
    goal_text = f"目标赛事：2026年9月27日柏林马拉松，距今 {days_left} 天（{days_left//7} 周）"

    prompt = f"""你是我的个人运动与健康教练，请综合以下所有数据给出今日训练建议：

【目标】{goal_text}

【跑步（最近5次，含步频步幅）】
{json.dumps(recent_runs, ensure_ascii=False, indent=2)}

【{sleep_text}】
【{hrv_text}】
{f'【{strength_text}】' if strength_text else ''}
{f'【{cycle_text}】' if cycle_text else ''}
{f'【{nutrition_text}】' if nutrition_text else ''}
{f'【{form_text}】' if form_text else ''}

请用中文回答，分四部分：
1. 今日身体状态评估（2-3句，考虑HRV、睡眠、生理周期）
2. 今日训练建议（具体：跑/休/力量？配速？时长？结合备战柏林马拉松阶段）
3. 跑步姿态反馈（步频是否达标170+？步幅是否合理？给出1条具体改进建议）
4. 本周重点提醒（1-2条，围绕马拉松备战）

语言简洁直接，像教练说话。"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text


def chat_with_claude(user_msg, runs, garmin, daily_log, history):
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    system = f"""你是用户的个人运动与健康教练助手。以下是她的数据：

跑步数据（最近）：{json.dumps(runs[-10:], ensure_ascii=False)}
Garmin健康数据：{json.dumps(garmin, ensure_ascii=False)}
今日日志：{json.dumps(daily_log, ensure_ascii=False)}

用中文回答，简洁实用，像教练一样直接给建议。"""
    messages = [{"role": h["role"], "content": h["content"]} for h in history]
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
    st.markdown("### 💪 健康助手")
    st.divider()
    limit = st.slider("跑步记录数", 10, 100, 50)
    refresh = st.button("🔄 刷新所有数据", use_container_width=True)
    if refresh:
        for key in ["runs", "garmin_data", "analysis"]:
            if key in st.session_state:
                del st.session_state[key]

    st.divider()
    st.markdown("**📅 今日日志**")

    cycle_day = st.number_input("生理周期第几天", min_value=0, max_value=35, value=0, step=1)
    cycle_phase = st.selectbox("周期阶段", ["未填写", "月经期", "卵泡期", "排卵期", "黄体期"])
    nutrition_notes = st.text_area("今日摄入备注", placeholder="如：热量1800kcal，蛋白质80g，水2L", height=80)

    daily_log = {
        "cycle_day": cycle_day if cycle_day > 0 else None,
        "cycle_phase": cycle_phase if cycle_phase != "未填写" else None,
        "nutrition_notes": nutrition_notes if nutrition_notes.strip() else None,
    }

    st.divider()
    st.caption("数据来源：Strava · Garmin")


# ---------- 主内容 ----------

st.markdown('<div class="page-title">💪 健康训练助手</div>', unsafe_allow_html=True)

# 获取数据
with st.spinner("连接 Strava..."):
    strava = get_strava_client()

if "runs" not in st.session_state:
    with st.spinner("同步跑步数据..."):
        st.session_state.runs = fetch_runs(strava, limit=limit)

with st.spinner("同步 Garmin 数据..."):
    garmin = fetch_garmin_data()

cycle_history = fetch_cycle_data()
today_str = str(date.today())
cycle_today = next((e for e in reversed(cycle_history) if e.get("date") <= today_str), None)

runs = st.session_state.runs
last_run = runs[-1]["date"] if runs else "无"
st.markdown(f'<div class="page-subtitle">最近 {len(runs)} 次跑步 · {last_run} · Garmin {garmin.get("date", "")}</div>', unsafe_allow_html=True)

# 统计行
total_km = round(sum(r["distance"] for r in runs), 1)
valid_paces = [r["pace"] for r in runs if r["pace"]]
avg_pace = round(sum(valid_paces) / len(valid_paces), 2) if valid_paces else 0
sleep_h = garmin.get("sleep", {}).get("total_hours", "—") if garmin.get("sleep") else "—"
hrv_val = garmin.get("hrv", {}).get("last_night_avg", "—") if garmin.get("hrv") else "—"
hrv_status = garmin.get("hrv", {}).get("status", "") if garmin.get("hrv") else ""

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    st.markdown(f'<div class="stat-card orange"><div class="stat-value">{total_km}</div><div class="stat-label">总里程 km</div></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="stat-card green"><div class="stat-value">{len(runs)}</div><div class="stat-label">跑步次数</div></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="stat-card blue"><div class="stat-value">{avg_pace}</div><div class="stat-label">平均配速</div></div>', unsafe_allow_html=True)
with c4:
    st.markdown(f'<div class="stat-card teal"><div class="stat-value">{sleep_h}</div><div class="stat-label">睡眠时长 h</div></div>', unsafe_allow_html=True)
with c5:
    hrv_color = "green" if "BALANCED" in hrv_status else "red"
    st.markdown(f'<div class="stat-card {hrv_color}"><div class="stat-value">{hrv_val}</div><div class="stat-label">HRV 昨晚</div></div>', unsafe_allow_html=True)
with c6:
    bb = garmin.get("sleep", {}).get("body_battery_change", "—") if garmin.get("sleep") else "—"
    bb_color = "green" if isinstance(bb, (int, float)) and bb > 0 else "red"
    st.markdown(f'<div class="stat-card {bb_color}"><div class="stat-value">{bb}</div><div class="stat-label">体能电量变化</div></div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 柏林马拉松倒计时
days_to_berlin = (BERLIN_DATE - date.today()).days
weeks_to_berlin = days_to_berlin // 7
# 训练阶段判断
if days_to_berlin > 70:
    phase_name, phase_color, phase_tip = "基础积累期", "#3b82f6", "打好有氧底子，轻松跑占80%，每周稳步增量不超过10%"
elif days_to_berlin > 28:
    phase_name, phase_color, phase_tip = "专项训练期", "#f97316", "加入马配跑、长距离节奏跑，每周一次20km+长跑"
elif days_to_berlin > 7:
    phase_name, phase_color, phase_tip = "减量期 🎯", "#22c55e", "大幅减量，保持感觉，不要加练！信任你的训练积累"
else:
    phase_name, phase_color, phase_tip = "赛前最后一周", "#ef4444", "轻松慢跑保持状态，检查装备，提前取号"

recent_4w = [r for r in runs if r["date"] >= str(date.today() - timedelta(days=28))]
weekly_km = round(sum(r["distance"] for r in recent_4w) / 4, 1)

st.markdown(f"""
<div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:16px;padding:20px 24px;margin-bottom:20px;color:white;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
  <div>
    <div style="font-size:0.8rem;opacity:0.6;letter-spacing:0.1em;margin-bottom:4px">🎯 目标赛事</div>
    <div style="font-size:1.3rem;font-weight:700">柏林马拉松 2026</div>
    <div style="font-size:0.85rem;opacity:0.7;margin-top:2px">2026年9月27日</div>
  </div>
  <div style="text-align:center">
    <div style="font-size:2.5rem;font-weight:800;color:#f97316">{days_to_berlin}</div>
    <div style="font-size:0.75rem;opacity:0.6">天后</div>
  </div>
  <div style="text-align:center">
    <div style="font-size:2rem;font-weight:700;color:#22c55e">{weeks_to_berlin}</div>
    <div style="font-size:0.75rem;opacity:0.6">周</div>
  </div>
  <div style="flex:1;min-width:200px">
    <div style="display:inline-block;background:{phase_color}33;border:1px solid {phase_color};border-radius:8px;padding:4px 12px;font-size:0.8rem;color:{phase_color};font-weight:600;margin-bottom:6px">{phase_name}</div>
    <div style="font-size:0.82rem;opacity:0.8">{phase_tip}</div>
  </div>
  <div style="text-align:center">
    <div style="font-size:1.6rem;font-weight:700;color:#a855f7">{weekly_km}</div>
    <div style="font-size:0.75rem;opacity:0.6">近4周均周跑量 km</div>
  </div>
</div>
""", unsafe_allow_html=True)

# 主区域三列
left, mid, right = st.columns([2, 2, 2])

with left:
    st.markdown("**📈 跑步数据**")
    df = pd.DataFrame(runs)
    df["date"] = pd.to_datetime(df["date"])
    tab1, tab2, tab3 = st.tabs(["配速趋势", "距离", "步频"])
    with tab1:
        st.line_chart(df.set_index("date")["pace"], color="#f97316", height=160)
    with tab2:
        st.bar_chart(df.set_index("date")["distance"], color="#22c55e", height=160)
    with tab3:
        df_cad = df[df["cadence"].notna()]
        if not df_cad.empty:
            st.line_chart(df_cad.set_index("date")["cadence"], color="#a855f7", height=160)
            avg_cad = round(df_cad["cadence"].mean())
            cad_color = "#22c55e" if avg_cad >= 170 else "#f97316" if avg_cad >= 160 else "#ef4444"
            tip = "✅ 步频理想（170-180 SPM）" if avg_cad >= 170 else "⚠️ 步频偏低，尝试提高至 170+ SPM" if avg_cad >= 160 else "❗步频过低，建议刻意练习提频"
            st.markdown(f'<div style="font-size:0.85rem;color:{cad_color};padding:4px 0">{tip}（均值 {avg_cad} SPM）</div>', unsafe_allow_html=True)
        else:
            st.info("暂无步频数据")

    with st.expander("所有跑步记录"):
        cols = ["date","distance","pace","heartrate","cadence","stride_cm"]
        cols_exist = [c for c in cols if c in df.columns]
        d = df[cols_exist].rename(columns={"date":"日期","distance":"距离km","pace":"配速","heartrate":"心率","cadence":"步频","stride_cm":"步幅cm"})
        d["日期"] = d["日期"].dt.strftime("%m-%d")
        st.dataframe(d, hide_index=True, use_container_width=True)

with mid:
    st.markdown("**🌙 健康数据**")

    if garmin.get("error"):
        st.error(f"Garmin 认证失败: {garmin['error']}")
    if garmin.get("errors"):
        for err in garmin["errors"]:
            st.warning(err)

    if garmin.get("sleep"):
        s = garmin["sleep"]
        st.markdown(f"""<div class="health-card">
            <h4>昨晚睡眠</h4>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                <div><div style="font-size:1.4rem;font-weight:700">{s['total_hours']}h</div><div style="color:#6b7280;font-size:0.75rem">总睡眠</div></div>
                <div><div style="font-size:1.4rem;font-weight:700">{s['deep_min']}min</div><div style="color:#6b7280;font-size:0.75rem">深睡</div></div>
                <div><div style="font-size:1.4rem;font-weight:700">{s['rem_min']}min</div><div style="color:#6b7280;font-size:0.75rem">REM</div></div>
                <div><div style="font-size:1.4rem;font-weight:700">{s.get('resting_hr','—')}</div><div style="color:#6b7280;font-size:0.75rem">静息心率</div></div>
            </div></div>""", unsafe_allow_html=True)

    if garmin.get("hrv"):
        h = garmin["hrv"]
        status_color = "#22c55e" if "BALANCED" in (h['status'] or '') else "#ef4444"
        status_text = "平衡" if "BALANCED" in (h['status'] or '') else "不平衡"
        st.markdown(f"""<div class="health-card">
            <h4>HRV 状态</h4>
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
                <div style="font-size:2rem;font-weight:700">{h['last_night_avg']}</div>
                <div><div style="color:{status_color};font-weight:600">{status_text}</div>
                <div style="color:#6b7280;font-size:0.75rem">基准 {h['baseline_low']}-{h['baseline_high']}</div></div>
            </div>
            <div style="color:#6b7280;font-size:0.8rem">周均值 {h['weekly_avg']}</div>
        </div>""", unsafe_allow_html=True)

    # VO2Max
    if garmin.get("vo2max"):
        vo2 = garmin["vo2max"]
        vo2_level = "精英" if vo2 >= 60 else "优秀" if vo2 >= 52 else "良好" if vo2 >= 44 else "一般"
        st.markdown(f"""<div class="health-card">
            <h4>VO2Max</h4>
            <div style="display:flex;align-items:center;gap:12px;">
                <div style="font-size:2rem;font-weight:700;color:#3b82f6">{vo2}</div>
                <div style="color:#6b7280;font-size:0.85rem">mL/kg/min · {vo2_level}</div>
            </div>
        </div>""", unsafe_allow_html=True)

    # 跑步动态（最近一次）
    garmin_runs = garmin.get("garmin_runs", [])
    if garmin_runs:
        gr = garmin_runs[0]
        def fmt(v, unit="", decimals=1):
            return f"{round(v, decimals)}{unit}" if v else "—"
        def metric_color(val, good_min, good_max):
            if not val: return "#6b7280"
            return "#22c55e" if good_min <= val <= good_max else "#f97316"
        cad = gr.get("cadence_spm")
        vo_cm = gr.get("vertical_oscillation_cm")
        vr = gr.get("vertical_ratio_pct")
        gct = gr.get("ground_contact_ms")
        st.markdown(f"""<div class="health-card">
            <h4>跑步动态（{gr['date']}）</h4>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:8px;">
                <div>
                    <div style="font-size:1.2rem;font-weight:700;color:{metric_color(cad,170,185)}">{fmt(cad,'',0)}</div>
                    <div style="color:#6b7280;font-size:0.7rem">步频 SPM</div>
                    <div style="font-size:0.7rem;color:#9ca3af">理想 170-180</div>
                </div>
                <div>
                    <div style="font-size:1.2rem;font-weight:700;color:#3b82f6">{fmt(gr.get('stride_length_m'),'m')}</div>
                    <div style="color:#6b7280;font-size:0.7rem">步幅</div>
                </div>
                <div>
                    <div style="font-size:1.2rem;font-weight:700;color:{metric_color(gct,200,270)}">{fmt(gct,'ms',0)}</div>
                    <div style="color:#6b7280;font-size:0.7rem">触地时间</div>
                    <div style="font-size:0.7rem;color:#9ca3af">理想 &lt;250ms</div>
                </div>
                <div>
                    <div style="font-size:1.2rem;font-weight:700;color:{metric_color(vo_cm,6,9)}">{fmt(vo_cm,'cm')}</div>
                    <div style="color:#6b7280;font-size:0.7rem">垂直振幅</div>
                    <div style="font-size:0.7rem;color:#9ca3af">理想 6-9cm</div>
                </div>
                <div>
                    <div style="font-size:1.2rem;font-weight:700;color:{metric_color(vr,None,8.5) if vr and vr<=8.5 else '#f97316'}">{fmt(vr,'%')}</div>
                    <div style="color:#6b7280;font-size:0.7rem">垂直振幅比</div>
                    <div style="font-size:0.7rem;color:#9ca3af">理想 &lt;8.5%</div>
                </div>
                <div>
                    <div style="font-size:1.2rem;font-weight:700;color:#a855f7">{fmt(gr.get('aerobic_te'),'',1)}</div>
                    <div style="color:#6b7280;font-size:0.7rem">有氧训练效果</div>
                </div>
            </div>
            {"<div style='font-size:0.8rem;color:#6b7280'>训练负荷：" + str(round(gr['training_load'])) + " · 无氧效果：" + str(gr.get('anaerobic_te','—')) + "</div>" if gr.get('training_load') else ""}
        </div>""", unsafe_allow_html=True)

    if garmin.get("strength"):
        st.markdown('<div class="health-card"><h4>最近力量训练</h4>', unsafe_allow_html=True)
        for s in garmin["strength"][:3]:
            st.markdown(f"🏋️ **{s['date']}** {s['name']} · {s['duration_min']}min", unsafe_allow_html=False)
        st.markdown('</div>', unsafe_allow_html=True)
    elif not garmin.get("strength"):
        st.info("最近50次活动中无力量训练记录")

    # 经期板块
    st.markdown("---")
    phase = cycle_today.get("cycle_phase") if cycle_today else None
    cycle_day = cycle_today.get("cycle_day") if cycle_today else None
    info = PHASE_INFO.get(phase, {})

    if phase and info:
        st.markdown(f"""<div class="health-card">
            <h4>经期状态</h4>
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
                <span style="font-size:1.8rem">{info['emoji']}</span>
                <div>
                    <div style="font-size:1.1rem;font-weight:700;color:{info['color']}">{phase}</div>
                    <div style="color:#6b7280;font-size:0.8rem">第 {cycle_day or '?'} 天</div>
                </div>
            </div>
            <div style="font-size:0.85rem;color:#374151;margin-bottom:6px">{info['tip']}</div>
            <div style="font-size:0.8rem;color:#6b7280">{info['hrv']}</div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown('<div class="health-card"><h4>经期状态</h4><div style="color:#9ca3af;font-size:0.85rem">运行 update_garmin.py 时记录经期数据</div></div>', unsafe_allow_html=True)

    # 历史对比图
    if len(cycle_history) >= 3:
        st.markdown("**📊 经期 × HRV 趋势**")
        df_cycle = pd.DataFrame(cycle_history)
        df_cycle = df_cycle[df_cycle["hrv"].notna()].copy()
        if not df_cycle.empty:
            df_cycle["date"] = pd.to_datetime(df_cycle["date"])
            phase_color_map = {"月经期": 1, "卵泡期": 2, "排卵期": 3, "黄体期": 4}
            df_cycle["phase_num"] = df_cycle["cycle_phase"].map(phase_color_map)
            st.line_chart(df_cycle.set_index("date")[["hrv"]], color=["#a855f7"], height=150)

with right:
    st.markdown("**💬 问 Claude**")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    chat_container = st.container(height=340)
    with chat_container:
        if not st.session_state.chat_history:
            st.markdown("""<div style="color:#9ca3af;font-size:0.85rem;padding:8px 0;">
            💡 试试问：<br>· 今天适合跑步吗？<br>· 经期该怎么训练？<br>· 我的HRV偏低怎么办？
            </div>""", unsafe_allow_html=True)
        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-ai">{msg["content"].replace(chr(10),"<br>")}</div>', unsafe_allow_html=True)

    with st.form("chat_form", clear_on_submit=True):
        col_i, col_b = st.columns([5, 1])
        with col_i:
            user_input = st.text_input("", placeholder="问点什么...", label_visibility="collapsed")
        with col_b:
            send = st.form_submit_button("发")

    if send and user_input.strip():
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.spinner(""):
            reply = chat_with_claude(user_input, runs, garmin, daily_log, st.session_state.chat_history[:-1])
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        st.rerun()

    if st.session_state.chat_history:
        if st.button("清空", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()

# Claude 综合分析
st.divider()
if "analysis" not in st.session_state:
    with st.spinner("Claude 综合分析中..."):
        st.session_state.analysis = comprehensive_analysis(runs, garmin, daily_log, cycle_today)

st.markdown(f"""
<div class="analysis-card">
    <h3>✨ CLAUDE 今日综合建议</h3>
    <p>{st.session_state.analysis.replace(chr(10), '<br>')}</p>
</div>
""", unsafe_allow_html=True)
