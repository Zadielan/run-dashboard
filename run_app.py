import streamlit as st
import anthropic
import json
import os
import time
import base64
import tempfile
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

st.set_page_config(page_title="健康数据", page_icon="🏃", layout="wide")

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


def fetch_runs(strava, limit=30):
    runs = []
    for activity in strava.get_activities(limit=limit):
        if activity.type != "Run":
            continue
        if not activity.distance or float(activity.distance) == 0:
            continue
        distance_km = round(float(activity.distance) / 1000, 2)
        mt = activity.moving_time
        if mt is None:
            continue
        duration_sec = mt.total_seconds() if hasattr(mt, 'total_seconds') else int(mt)
        duration_min = round(duration_sec / 60, 1)
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


# ---------- Garmin ----------

def fetch_garmin_data():
    if "garmin_data" in st.session_state:
        return st.session_state.garmin_data

    try:
        tmpdir = tempfile.mkdtemp()
        with open(os.path.join(tmpdir, "oauth1_token.json"), "wb") as f:
            f.write(base64.b64decode(GARMIN_OAUTH1))
        with open(os.path.join(tmpdir, "oauth2_token.json"), "wb") as f:
            f.write(base64.b64decode(GARMIN_OAUTH2))
        garth.resume(tmpdir)
    except Exception as e:
        return {"error": str(e)}

    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    data = {"date": yesterday}

    errors = []

    # 睡眠
    try:
        raw = garth.connectapi(f"/wellness-service/wellness/dailySleepData/{GARMIN_USER_ID}?date={yesterday}")
        dto = raw.get("dailySleepDTO", {})
        data["sleep"] = {
            "total_hours": round(dto.get("sleepTimeSeconds", 0) / 3600, 1),
            "deep_min": round(dto.get("deepSleepSeconds", 0) / 60),
            "rem_min": round(dto.get("remSleepSeconds", 0) / 60),
            "light_min": round(dto.get("lightSleepSeconds", 0) / 60),
            "awake_min": round(dto.get("awakeSleepSeconds", 0) / 60),
            "body_battery_change": raw.get("bodyBatteryChange"),
            "resting_hr": raw.get("restingHeartRate"),
            "avg_overnight_hrv": raw.get("avgOvernightHrv"),
            "sleep_score": dto.get("sleepScores", {}).get("overall", {}).get("value") if isinstance(dto.get("sleepScores"), dict) else None,
        }
    except Exception as e:
        data["sleep"] = None
        errors.append(f"睡眠: {e}")

    # HRV
    try:
        hrv_raw = garth.connectapi(f"/hrv-service/hrv/{yesterday}")
        s = hrv_raw.get("hrvSummary", {})
        baseline = s.get("baseline", {})
        data["hrv"] = {
            "weekly_avg": s.get("weeklyAvg"),
            "last_night_avg": s.get("lastNightAvg"),
            "last_night_5min_high": s.get("lastNight5MinHigh"),
            "baseline_low": baseline.get("balancedLow"),
            "baseline_high": baseline.get("balancedUpper"),
            "status": s.get("status"),
            "feedback": s.get("feedbackPhrase"),
        }
    except Exception as e:
        data["hrv"] = None
        errors.append(f"HRV: {e}")

    # 力量训练（最近5次）
    try:
        acts = garth.connectapi("/activitylist-service/activities/search/activities?limit=50&start=0")
        strength = [a for a in acts if a.get("activityType", {}).get("typeKey", "") == "strength_training"][:5]
        data["strength"] = [{
            "date": a.get("startTimeLocal", "")[:10],
            "name": a.get("activityName", "力量训练"),
            "duration_min": round((a.get("duration") or 0) / 60),
            "calories": a.get("calories"),
        } for a in strength]
    except Exception as e:
        data["strength"] = []
        errors.append(f"力量训练: {e}")

    if errors:
        data["errors"] = errors

    st.session_state.garmin_data = data
    return data


# ---------- Claude ----------

def comprehensive_analysis(runs, garmin, daily_log):
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

    cycle_text = f"生理周期：第 {daily_log.get('cycle_day', '未知')} 天，阶段 {daily_log.get('cycle_phase', '未知')}" if daily_log.get('cycle_day') else ""
    nutrition_text = f"今日摄入：{daily_log.get('nutrition_notes', '')}" if daily_log.get('nutrition_notes') else ""

    recent_runs = runs[-5:] if len(runs) >= 5 else runs

    prompt = f"""你是我的个人运动与健康教练，请综合以下所有数据给出今日训练建议：

【跑步（最近5次）】
{json.dumps(recent_runs, ensure_ascii=False, indent=2)}

【{sleep_text}】
【{hrv_text}】
{f'【{strength_text}】' if strength_text else ''}
{f'【{cycle_text}】' if cycle_text else ''}
{f'【{nutrition_text}】' if nutrition_text else ''}

请用中文回答，分三部分：
1. 今日身体状态评估（2-3句，考虑HRV、睡眠、生理周期）
2. 今日训练建议（具体：跑/休/力量？强度？时长？）
3. 本周重点提醒（1-2条）

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
    limit = st.slider("跑步记录数", 10, 50, 20)
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

# 主区域三列
left, mid, right = st.columns([2, 2, 2])

with left:
    st.markdown("**📈 跑步数据**")
    df = pd.DataFrame(runs)
    df["date"] = pd.to_datetime(df["date"])
    tab1, tab2 = st.tabs(["配速趋势", "距离"])
    with tab1:
        st.line_chart(df.set_index("date")["pace"], color="#f97316", height=180)
    with tab2:
        st.bar_chart(df.set_index("date")["distance"], color="#22c55e", height=180)

    with st.expander("所有跑步记录"):
        d = df[["date","distance","pace","heartrate"]].copy()
        d.columns = ["日期","距离km","配速","心率"]
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

    if garmin.get("strength"):
        st.markdown('<div class="health-card"><h4>最近力量训练</h4>', unsafe_allow_html=True)
        for s in garmin["strength"][:3]:
            st.markdown(f"🏋️ **{s['date']}** {s['name']} · {s['duration_min']}min", unsafe_allow_html=False)
        st.markdown('</div>', unsafe_allow_html=True)
    elif not garmin.get("strength"):
        st.info("最近50次活动中无力量训练记录")

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
        st.session_state.analysis = comprehensive_analysis(runs, garmin, daily_log)

st.markdown(f"""
<div class="analysis-card">
    <h3>✨ CLAUDE 今日综合建议</h3>
    <p>{st.session_state.analysis.replace(chr(10), '<br>')}</p>
</div>
""", unsafe_allow_html=True)
