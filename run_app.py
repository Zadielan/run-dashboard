import streamlit as st
import anthropic
import json
import os
import time
import requests as http_req
from datetime import date, timedelta, datetime
import pandas as pd
from stravalib import Client

# ============================================================
STRAVA_CLIENT_ID     = st.secrets["STRAVA_CLIENT_ID"]
STRAVA_CLIENT_SECRET = st.secrets["STRAVA_CLIENT_SECRET"]
CLAUDE_API_KEY       = st.secrets["CLAUDE_API_KEY"]
STRAVA_REFRESH_TOKEN = st.secrets["STRAVA_REFRESH_TOKEN"]
GARMIN_OAUTH1        = st.secrets["GARMIN_OAUTH1"]
GARMIN_OAUTH2        = st.secrets["GARMIN_OAUTH2"]
GARMIN_USER_ID       = "119995800"
BERLIN_DATE          = date(2026, 9, 27)
GITHUB_TOKEN     = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_REPO      = "Zadielan/run-dashboard"
GARMIN_DATA_URL  = "https://raw.githubusercontent.com/Zadielan/run-dashboard/main/garmin_data.json"
CYCLE_DATA_URL   = "https://raw.githubusercontent.com/Zadielan/run-dashboard/main/cycle_data.json"
BODY_DATA_URL    = "https://raw.githubusercontent.com/Zadielan/run-dashboard/main/body_data.json"
# ============================================================

st.set_page_config(page_title="健康训练", page_icon="🏃", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #f0ebe0; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1.5rem 2rem 2rem; max-width: 1200px; }

/* Cards */
.card {
    background: white; border-radius: 18px; padding: 20px 22px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07); margin-bottom: 14px;
}
.card h4 {
    font-size: 0.8rem; font-weight: 700; color: #6b7280;
    text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 14px;
}

/* Pills / tags */
.pill {
    display: inline-block; border-radius: 20px; padding: 4px 12px;
    font-size: 0.8rem; font-weight: 500; margin: 3px 3px 3px 0;
}
.pill-beige  { background: #f0ebe0; color: #4a3f30; border: 1px solid #ddd5c5; }
.pill-green  { background: #d1fae5; color: #065f46; border: 1px solid #6ee7b7; }
.pill-red    { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
.pill-purple { background: #ede9fe; color: #5b21b6; border: 1px solid #c4b5fd; }
.pill-orange { background: #fff7ed; color: #9a3412; border: 1px solid #fdba74; }
.pill-dark   { background: #1a3c2e; color: white; }

/* Readiness circle */
.readiness-wrap { display: flex; flex-direction: column; align-items: center; justify-content: center; }

/* Stat mini */
.mini-stat { text-align: center; padding: 10px; }
.mini-stat .val { font-size: 1.5rem; font-weight: 800; color: #1a1a1a; }
.mini-stat .lbl { font-size: 0.7rem; color: #9ca3af; margin-top: 2px; }

/* Claude output */
.ai-block { background: #f8faf8; border-left: 3px solid #2d4a3e; border-radius: 0 12px 12px 0; padding: 14px 18px; margin: 8px 0; font-size: 0.88rem; line-height: 1.75; color: #1a1a1a; }
.ai-label { font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #2d4a3e; margin-bottom: 4px; }

/* Chat */
.chat-user { background: #2d4a3e; color: white; border-radius: 18px 18px 4px 18px; padding: 10px 16px; margin: 6px 0; margin-left: 20%; font-size: 0.9rem; }
.chat-ai   { background: white; color: #1a1a1a; border-radius: 18px 18px 18px 4px; padding: 10px 16px; margin: 6px 0; margin-right: 20%; font-size: 0.9rem; box-shadow: 0 1px 4px rgba(0,0,0,0.08); line-height: 1.65; }

/* Berlin banner */
.berlin-banner {
    background: #1a3c2e; color: white; border-radius: 16px;
    padding: 16px 24px; margin-bottom: 20px;
    display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 4px; background: white; border-radius: 14px; padding: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.07); }
.stTabs [data-baseweb="tab"] { border-radius: 10px; padding: 7px 18px; font-weight: 500; font-size: 0.9rem; color: #6b7280; }
.stTabs [aria-selected="true"] { background: #1a3c2e !important; color: white !important; }

/* Buttons */
.stButton button { border-radius: 12px; font-weight: 600; border: none; background: #1a3c2e; color: white; padding: 10px 20px; }
.stButton button:hover { background: #2d5a44; }

/* Progress bars */
.prog-wrap { margin: 8px 0; }
.prog-label { display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 4px; }
.prog-bar-bg { background: #f0ebe0; border-radius: 6px; height: 8px; overflow: hidden; }
.prog-bar-fill { height: 8px; border-radius: 6px; }

/* Running dynamics grid */
.dyn-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; }
.dyn-item .dv { font-size: 1.1rem; font-weight: 700; }
.dyn-item .dl { font-size: 0.7rem; color: #9ca3af; margin-top: 2px; }
.dyn-item .dt { font-size: 0.65rem; color: #c4b5aa; }

[data-testid="stSidebar"] { background: white; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# DATA FUNCTIONS
# ══════════════════════════════════════════════════════

def get_strava_client():
    if "strava_token" in st.session_state:
        token = st.session_state.strava_token
        if token["expires_at"] > time.time():
            c = Client(); c.access_token = token["access_token"]; return c
    c = Client()
    token = c.refresh_access_token(
        client_id=STRAVA_CLIENT_ID, client_secret=STRAVA_CLIENT_SECRET,
        refresh_token=STRAVA_REFRESH_TOKEN
    )
    st.session_state.strava_token = dict(token)
    c.access_token = token["access_token"]
    return c

def fetch_runs(strava, limit=50):
    runs = []
    for a in strava.get_activities(limit=limit):
        if a.type != "Run": continue
        if not a.distance or float(a.distance) == 0: continue
        dist_km = round(float(a.distance)/1000, 2)
        dist_m  = float(a.distance)
        mt = a.moving_time
        if mt is None: continue
        dur_sec = mt.total_seconds() if hasattr(mt,'total_seconds') else int(mt)
        dur_min = round(dur_sec/60, 1)
        pace = round(dur_min/dist_km, 2) if dist_km > 0 else None
        cad_raw = a.average_cadence
        cadence = round(float(cad_raw)*2) if cad_raw else None
        stride_cm = round(dist_m/(cadence*dur_min)*100) if cadence and dur_min>0 else None
        runs.append({
            "date": str(a.start_date)[:10], "name": a.name,
            "distance": dist_km, "duration": dur_min, "pace": pace,
            "heartrate": a.average_heartrate, "max_heartrate": a.max_heartrate,
            "elevation": round(float(a.total_elevation_gain),1) if a.total_elevation_gain else 0,
            "cadence": cadence, "stride_cm": stride_cm,
        })
    runs.sort(key=lambda x: x["date"])
    return runs

def fetch_garmin_data():
    if "garmin_data" in st.session_state:
        return st.session_state.garmin_data
    try:
        r = http_req.get(GARMIN_DATA_URL, timeout=10); r.raise_for_status()
        data = r.json()
    except Exception as e:
        data = {"error": f"读取 Garmin 数据失败: {e}"}
    st.session_state.garmin_data = data
    return data

def fetch_cycle_data():
    if "cycle_data" in st.session_state:
        return st.session_state.cycle_data
    try:
        r = http_req.get(CYCLE_DATA_URL, timeout=10); r.raise_for_status()
        data = r.json()
    except:
        data = []
    st.session_state.cycle_data = data
    return data

def fetch_body_data():
    if "body_data" in st.session_state:
        return st.session_state.body_data
    try:
        r = http_req.get(BODY_DATA_URL, timeout=10); r.raise_for_status()
        data = r.json()
    except:
        data = []
    st.session_state.body_data = data


def push_json_to_github(filename, data, commit_msg):
    """Push JSON file to GitHub via API. Returns (success, message)."""
    import base64
    if not GITHUB_TOKEN:
        return False, "未配置 GITHUB_TOKEN"
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    # Get current SHA (needed for updates)
    r = http_req.get(url, headers=headers, timeout=10)
    sha = r.json().get("sha") if r.status_code == 200 else None
    content = base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode()).decode()
    payload = {"message": commit_msg, "content": content}
    if sha:
        payload["sha"] = sha
    resp = http_req.put(url, headers=headers, json=payload, timeout=15)
    if resp.status_code in (200, 201):
        return True, "已保存"
    return False, f"保存失败: {resp.status_code}"
    return data


# ══════════════════════════════════════════════════════
# LOGIC HELPERS
# ══════════════════════════════════════════════════════

PHASE_INFO = {
    "月经期": {"emoji":"🔴","color":"#ef4444","tip":"低能量期，适合轻松慢跑、瑜伽、散步。多补铁和水分。","hrv":"HRV 通常偏低，休息优先。"},
    "卵泡期": {"emoji":"🌱","color":"#22c55e","tip":"精力逐渐上升，适合提速训练、力量训练。","hrv":"HRV 开始回升，身体恢复力强。"},
    "排卵期": {"emoji":"⚡","color":"#f97316","tip":"精力巅峰！适合冲击配速 PR、高强度间歇。","hrv":"HRV 通常最高，训练适应性最好。"},
    "黄体期": {"emoji":"🌙","color":"#a855f7","tip":"精力下降，体温升高。适合中低强度，重视睡眠。","hrv":"HRV 可能下降，不必强迫完成计划。"},
}

def predict_cycle(history):
    today_date = date.today()
    period_entries = sorted(
        [e for e in history if e.get("cycle_day")==1 or e.get("is_period_start")],
        key=lambda x: x["date"]
    )
    if not period_entries: return None
    period_starts = [e["date"] for e in period_entries]
    last_entry = period_entries[-1]
    last_start = date.fromisoformat(last_entry["date"])
    days_since = (today_date - last_start).days + 1
    # Use stored cycle_length if available, else calculate from intervals
    if last_entry.get("cycle_length"):
        avg_cycle = last_entry["cycle_length"]
    elif len(period_starts) >= 2:
        intervals = [(date.fromisoformat(period_starts[i+1]) - date.fromisoformat(period_starts[i])).days
                     for i in range(len(period_starts)-1)]
        avg_cycle = round(sum(intervals)/len(intervals))
    else:
        avg_cycle = 28
    actual_day = days_since if days_since <= avg_cycle else (days_since % avg_cycle or avg_cycle)
    next_period = last_start + timedelta(days=avg_cycle - 1)
    if actual_day <= 5:    phase = "月经期"
    elif actual_day <= 13: phase = "卵泡期"
    elif actual_day <= 15: phase = "排卵期"
    else:                  phase = "黄体期"
    return {
        "cycle_day": actual_day, "cycle_phase": phase, "avg_cycle": avg_cycle,
        "next_period": str(next_period), "days_to_next": (next_period - today_date).days,
    }

def compute_readiness(garmin):
    """0-100 readiness score from HRV, sleep, body battery"""
    score = 50
    hrv_data = garmin.get("hrv", {})
    if hrv_data and hrv_data.get("last_night_avg"):
        hrv_val  = hrv_data["last_night_avg"]
        hrv_low  = hrv_data.get("baseline_low") or 35
        hrv_high = hrv_data.get("baseline_high") or 55
        hrv_mid  = (hrv_low + hrv_high) / 2
        if hrv_val >= hrv_high:
            contrib = 20 + min(5, (hrv_val - hrv_high) * 0.5)
        elif hrv_val >= hrv_mid:
            contrib = (hrv_val - hrv_mid) / (hrv_high - hrv_mid) * 20
        elif hrv_val >= hrv_low:
            contrib = -(hrv_mid - hrv_val) / (hrv_mid - hrv_low) * 10
        else:
            contrib = max(-15, -10 - (hrv_low - hrv_val)*0.5)
        score += min(25, contrib)
    sleep_data = garmin.get("sleep", {})
    if sleep_data:
        h = sleep_data.get("total_hours", 0) or 0
        if h >= 8.5:   score += 20
        elif h >= 7.5: score += 15
        elif h >= 7.0: score += 10
        elif h >= 6.5: score += 4
        elif h >= 6.0: score += 0
        elif h >= 5.0: score -= 8
        else:          score -= 15
        bb = sleep_data.get("body_battery_change")
        if bb: score += min(10, max(-10, (bb or 0) * 0.15))
    return max(0, min(100, round(score)))

def readiness_color(s):
    if s >= 75: return "#2d4a3e"
    if s >= 55: return "#b8952a"
    return "#c0543a"

def readiness_label(s):
    if s >= 80: return "状态极佳"
    if s >= 65: return "状态良好"
    if s >= 50: return "一般恢复"
    return "需要休息"


# ══════════════════════════════════════════════════════
# CLAUDE FUNCTIONS
# ══════════════════════════════════════════════════════

def comprehensive_analysis(runs, garmin, cycle_today):
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    sleep_text = hrv_text = form_text = cycle_text = ""
    if garmin.get("sleep"):
        s = garmin["sleep"]
        sleep_text = f"睡眠：{s['total_hours']}h，深睡{s['deep_min']}min，体能电量变化{s.get('body_battery_change','?')}"
    if garmin.get("hrv"):
        h = garmin["hrv"]
        hrv_text = f"HRV：{h['last_night_avg']}（基准{h['baseline_low']}-{h['baseline_high']}，{h['status']}）"
    if cycle_today and cycle_today.get("cycle_phase"):
        cycle_text = f"生理周期：{cycle_today['cycle_phase']}第{cycle_today.get('cycle_day','?')}天"
    garmin_runs = garmin.get("garmin_runs", [])
    if garmin_runs:
        gr = garmin_runs[0]; parts = []
        if gr.get("cadence_spm"):            parts.append(f"步频{gr['cadence_spm']}SPM")
        if gr.get("stride_length_cm"):       parts.append(f"步幅{gr['stride_length_cm']}cm")
        if gr.get("vertical_oscillation_cm"):parts.append(f"垂直振幅{gr['vertical_oscillation_cm']}cm")
        if gr.get("vertical_ratio_pct"):     parts.append(f"垂直比{gr['vertical_ratio_pct']}%")
        if gr.get("ground_contact_ms"):      parts.append(f"触地{gr['ground_contact_ms']}ms")
        if garmin.get("vo2max"):             parts.append(f"VO2Max={garmin['vo2max']}")
        form_text = "跑步动态：" + "，".join(parts) if parts else ""
    days_left = (BERLIN_DATE - date.today()).days
    recent = runs[-5:] if len(runs) >= 5 else runs
    prompt = f"""你是我的个人运动教练，请综合数据给今日建议：
目标：{days_left}天后柏林马拉松（2026.9.27）
{sleep_text}
{hrv_text}
{cycle_text}
{form_text}
最近跑步：{json.dumps(recent, ensure_ascii=False)}

请用中文，分三部分各1-2句：
【读身体】当前身体状态（结合HRV睡眠周期）
【训练】今日具体建议（跑/休/力量？配速距离？）
【跑姿】步频步幅等数据反馈+1条改进建议
语言简洁，像教练说话。"""
    msg = client.messages.create(model="claude-sonnet-4-6", max_tokens=500, messages=[{"role":"user","content":prompt}])
    return msg.content[0].text

def chat_with_claude(user_msg, runs, garmin, cycle_today, history):
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    system = f"""你是用户的个人运动健康教练。数据：
跑步：{json.dumps(runs[-8:], ensure_ascii=False)}
Garmin：{json.dumps({k:v for k,v in garmin.items() if k!='garmin_runs'}, ensure_ascii=False)}
周期：{json.dumps(cycle_today, ensure_ascii=False)}
用中文简洁直接回答，像教练风格。"""
    msgs = [{"role":h["role"],"content":h["content"]} for h in history]
    msgs.append({"role":"user","content":user_msg})
    msg = client.messages.create(model="claude-sonnet-4-6", max_tokens=500, system=system, messages=msgs)
    return msg.content[0].text


# ══════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("### 健康助手")
    st.divider()
    limit = st.slider("跑步记录数", 10, 100, 50)
    if st.button("🔄 刷新数据", use_container_width=True):
        for k in ["runs","garmin_data","cycle_data","body_data","analysis"]:
            if k in st.session_state: del st.session_state[k]
        st.rerun()
    st.divider()
    st.caption("数据来源：Strava · Garmin Connect")
    st.caption("每日运行 update_garmin.py 更新")


# ══════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════

with st.spinner("同步数据..."):
    strava = get_strava_client()
    if "runs" not in st.session_state:
        st.session_state.runs = fetch_runs(strava, limit=limit)
    garmin = fetch_garmin_data()
    cycle_history = fetch_cycle_data()
    body_history  = fetch_body_data()

runs = st.session_state.runs
cycle_pred  = predict_cycle(cycle_history)
today_str   = str(date.today())
cycle_today_raw = next((e for e in reversed(cycle_history) if e.get("date") <= today_str), None)
cycle_today = {**(cycle_today_raw or {}), **(cycle_pred or {})}

readiness = compute_readiness(garmin)
r_color   = readiness_color(readiness)
r_label   = readiness_label(readiness)

days_to_berlin = (BERLIN_DATE - date.today()).days
weeks_to_berlin = days_to_berlin // 7

recent_4w = [r for r in runs if r["date"] >= str(date.today() - timedelta(days=28))]
weekly_km = round(sum(r["distance"] for r in recent_4w)/4, 1) if recent_4w else 0


# ══════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════

today_display = date.today().strftime("今日 · %Y-%m-%d")
phase_now = cycle_today.get("cycle_phase","")
phase_info = PHASE_INFO.get(phase_now, {})
cycle_day_now = cycle_today.get("cycle_day","")

col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown(f'<div style="font-size:1.8rem;font-weight:800;color:#1a1a1a;margin-bottom:2px">{today_display}</div>', unsafe_allow_html=True)
with col_h2:
    if phase_now:
        st.markdown(f'<div style="text-align:right;padding-top:8px"><div style="font-size:0.75rem;color:#6b7280">D{cycle_day_now}</div><div style="font-size:0.85rem;font-weight:600;color:{phase_info.get("color","#333")}">{phase_info.get("emoji","")} {phase_now}</div></div>', unsafe_allow_html=True)

# Berlin banner
if days_to_berlin > 7:
    if days_to_berlin > 70:   train_phase, phase_tip_b = "基础期", "有氧为主，每周稳步增量"
    elif days_to_berlin > 28: train_phase, phase_tip_b = "专项期", "马配跑+长距离节奏跑"
    else:                     train_phase, phase_tip_b = "减量期 🎯", "大幅减量，信任积累"
    st.markdown(f"""
<div class="berlin-banner">
  <div>
    <div style="font-size:0.7rem;opacity:0.5;letter-spacing:0.1em">🎯 目标赛事</div>
    <div style="font-size:1.1rem;font-weight:700">柏林马拉松 2026</div>
    <div style="font-size:0.78rem;opacity:0.6;margin-top:2px">{train_phase} · {phase_tip_b}</div>
  </div>
  <div style="text-align:center">
    <div style="font-size:2.2rem;font-weight:800;color:#c8a84b">{days_to_berlin}</div>
    <div style="font-size:0.7rem;opacity:0.5">天</div>
  </div>
  <div style="text-align:center">
    <div style="font-size:1.6rem;font-weight:700;color:#7ecfaa">{weeks_to_berlin}</div>
    <div style="font-size:0.7rem;opacity:0.5">周</div>
  </div>
  <div style="text-align:center">
    <div style="font-size:1.6rem;font-weight:700;color:#9bb8ac">{weekly_km}</div>
    <div style="font-size:0.7rem;opacity:0.5">近4周均周km</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════

tab_today, tab_trend, tab_body = st.tabs(["♥ 今日", "📈 趋势", "💪 身体"])


# ──────────────────────────────────────────────────────
# TAB: 今日
# ──────────────────────────────────────────────────────

with tab_today:
    col_left, col_right = st.columns([1, 2])

    with col_left:
        # Readiness circle
        circumference = 2 * 3.14159 * 48
        dash = circumference * readiness / 100
        gap  = circumference - dash
        offset = circumference * 0.25

        sleep_h = garmin.get("sleep",{}).get("total_hours","—") if garmin.get("sleep") else "—"
        hrv_v   = garmin.get("hrv",{}).get("last_night_avg","—") if garmin.get("hrv") else "—"

        st.markdown(f"""
<div class="card" style="text-align:center;padding:28px 20px">
  <svg viewBox="0 0 120 120" width="150" height="150" style="margin:0 auto;display:block">
    <circle cx="60" cy="60" r="48" fill="none" stroke="#e8e2d6" stroke-width="9"/>
    <circle cx="60" cy="60" r="48" fill="none" stroke="{r_color}" stroke-width="9"
      stroke-dasharray="{dash:.1f} {gap:.1f}"
      stroke-dashoffset="{offset:.1f}"
      stroke-linecap="round" transform="rotate(-90 60 60)"/>
    <text x="60" y="56" text-anchor="middle" font-family="Inter,sans-serif" font-size="28" font-weight="800" fill="#1a1a1a">{readiness}</text>
    <text x="60" y="71" text-anchor="middle" font-family="Inter,sans-serif" font-size="9" fill="#9ca3af" letter-spacing="2">READINESS</text>
  </svg>
  <div style="font-size:0.9rem;font-weight:600;color:{r_color};margin-top:8px">{r_label}</div>
  <div style="margin-top:12px;display:flex;justify-content:center;gap:20px">
    <div class="mini-stat"><div class="val">{sleep_h}</div><div class="lbl">睡眠 h</div></div>
    <div class="mini-stat"><div class="val">{hrv_v}</div><div class="lbl">HRV</div></div>
  </div>
</div>
""", unsafe_allow_html=True)

        # Status pills
        pills_html = ""
        if garmin.get("sleep") and garmin["sleep"].get("total_hours"):
            h = garmin["sleep"]["total_hours"]
            cls = "pill-green" if h >= 7 else "pill-orange" if h >= 6 else "pill-red"
            pills_html += f'<span class="pill {cls}">睡眠 {h}h</span>'
        if garmin.get("hrv") and garmin["hrv"].get("status"):
            status = garmin["hrv"]["status"]
            cls = "pill-green" if "BALANCED" in status else "pill-red"
            pills_html += f'<span class="pill {cls}">HRV {"平衡" if "BALANCED" in status else "偏低"}</span>'
        if phase_now:
            pills_html += f'<span class="pill pill-beige">{phase_info.get("emoji","")} {phase_now}</span>'
        if days_to_berlin <= 14:
            pills_html += f'<span class="pill pill-red">全马·还有 {days_to_berlin} 天</span>'
        elif days_to_berlin <= 42:
            pills_html += f'<span class="pill pill-orange">全马·还有 {days_to_berlin} 天</span>'
        else:
            pills_html += f'<span class="pill pill-beige">全马·还有 {days_to_berlin} 天</span>'

        if pills_html:
            st.markdown(f'<div style="margin-top:4px">{pills_html}</div>', unsafe_allow_html=True)

    with col_right:
        # Claude analysis
        if "analysis" not in st.session_state:
            with st.spinner("Claude 分析中..."):
                st.session_state.analysis = comprehensive_analysis(runs, garmin, cycle_today)

        raw = st.session_state.analysis
        # Parse sections
        import re
        sections = re.split(r'【(读身体|训练|跑姿)】', raw)
        if len(sections) >= 4:
            label_map = {"读身体":"🩺 读身体","训练":"🏃 训练","跑姿":"👟 跑姿"}
            for i in range(1, len(sections)-1, 2):
                lbl = sections[i]; txt = sections[i+1].strip()
                st.markdown(f'<div class="ai-block"><div class="ai-label">{label_map.get(lbl,lbl)}</div>{txt}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="ai-block">{raw.replace(chr(10),"<br>")}</div>', unsafe_allow_html=True)

        if st.button("🔄 重新分析", key="reanalyze"):
            if "analysis" in st.session_state: del st.session_state["analysis"]
            st.rerun()

    st.divider()

    # Chat
    st.markdown("**💬 问 Claude**")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    chat_container = st.container(height=280)
    with chat_container:
        if not st.session_state.chat_history:
            st.markdown('<div style="color:#9ca3af;font-size:0.85rem;padding:8px 0">💡 试试问：今天适合跑步吗？ · 经期该怎么训练？ · 我的HRV偏低怎么办？</div>', unsafe_allow_html=True)
        for msg in st.session_state.chat_history:
            cls = "chat-user" if msg["role"]=="user" else "chat-ai"
            content = msg["content"].replace(chr(10),"<br>")
            st.markdown(f'<div class="{cls}">{content}</div>', unsafe_allow_html=True)

    col_ci, col_cb, col_cc = st.columns([5,1,1])
    with col_ci:
        user_input = st.text_input("chat", placeholder="输入问题...", label_visibility="collapsed", key="chat_input")
    with col_cb:
        send = st.button("发送", key="chat_send")
    with col_cc:
        if st.button("清空", key="chat_clear"):
            st.session_state.chat_history = []; st.rerun()

    if send and user_input.strip():
        st.session_state.chat_history.append({"role":"user","content":user_input})
        with st.spinner(""):
            reply = chat_with_claude(user_input, runs, garmin, cycle_today, st.session_state.chat_history[:-1])
        st.session_state.chat_history.append({"role":"assistant","content":reply})
        st.rerun()


# ──────────────────────────────────────────────────────
# TAB: 趋势
# ──────────────────────────────────────────────────────

with tab_trend:
    df = pd.DataFrame(runs)
    df["date"] = pd.to_datetime(df["date"])

    # Garmin runs DataFrame (for vertical ratio etc.)
    garmin_runs = garmin.get("garmin_runs", [])
    df_gr = pd.DataFrame(garmin_runs) if garmin_runs else pd.DataFrame()
    if not df_gr.empty:
        df_gr["date"] = pd.to_datetime(df_gr["date"])

    # Time range selector
    range_days = st.radio("时间范围", ["14天","30天","全部"], horizontal=True, index=1)
    cutoff = {"14天": 14, "30天": 30, "全部": 9999}[range_days]
    cutoff_dt = pd.Timestamp(date.today() - timedelta(days=cutoff))
    df_f = df[df["date"] >= cutoff_dt]
    df_gr_f = df_gr[df_gr["date"] >= cutoff_dt] if not df_gr.empty else df_gr

    def trend_card(title, chart_fn, note=None):
        st.markdown(f'<div class="card"><h4>{title}</h4>', unsafe_allow_html=True)
        chart_fn()
        if note:
            st.markdown(f'<div style="font-size:0.8rem;margin-top:4px;color:#6b7280">{note}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        # 配速
        def _pace():
            if not df_f.empty: st.line_chart(df_f.set_index("date")["pace"], color="#2d4a3e", height=155)
        trend_card("配速趋势 (min/km)", _pace)

        # 步频
        def _cad():
            df_cad = df_f[df_f["cadence"].notna()]
            if not df_cad.empty:
                st.line_chart(df_cad.set_index("date")["cadence"], color="#b8952a", height=155)
        avg_cad = round(df_f["cadence"].dropna().mean()) if not df_f.empty and df_f["cadence"].notna().any() else None
        cad_note = f"{'✅' if avg_cad and avg_cad>=170 else '⚠️'} 均值 {avg_cad} SPM" if avg_cad else None
        trend_card("步频趋势 (SPM)", _cad, cad_note)

        # 心率
        def _hr():
            df_hr = df_f[df_f["heartrate"].notna()].copy()
            if not df_hr.empty:
                plot_cols = ["heartrate"]
                if "max_heartrate" in df_hr.columns and df_hr["max_heartrate"].notna().any():
                    plot_cols.append("max_heartrate")
                st.line_chart(df_hr.set_index("date")[plot_cols], color=["#c0543a","#f4a49a"][:len(plot_cols)], height=155)
        avg_hr = round(df_f["heartrate"].dropna().mean()) if not df_f.empty and df_f["heartrate"].notna().any() else None
        trend_card("心率趋势 (bpm)", _hr, f"均值 {avg_hr} bpm" if avg_hr else None)

        # 步幅（优先 Garmin，否则 Strava 估算）
        def _stride():
            if not df_gr_f.empty and "stride_length_cm" in df_gr_f.columns and df_gr_f["stride_length_cm"].notna().any():
                st.line_chart(df_gr_f.set_index("date")["stride_length_cm"].dropna(), color="#7ecfaa", height=155)
            elif not df_f.empty and "stride_cm" in df_f.columns and df_f["stride_cm"].notna().any():
                st.line_chart(df_f[df_f["stride_cm"].notna()].set_index("date")["stride_cm"], color="#7ecfaa", height=155)
        trend_card("步幅趋势 (cm)", _stride)

    with c2:
        # 跑量
        def _dist():
            if not df_f.empty: st.bar_chart(df_f.set_index("date")["distance"], color="#c8a84b", height=155)
        trend_card("跑量 (km)", _dist)

        # HRV
        df_cyc = pd.DataFrame(cycle_history) if cycle_history else pd.DataFrame()
        if not df_cyc.empty and "hrv" in df_cyc.columns:
            df_cyc["date"] = pd.to_datetime(df_cyc["date"])
            df_cyc_f = df_cyc[df_cyc["hrv"].notna() & (df_cyc["date"] >= cutoff_dt)]
            def _hrv():
                if not df_cyc_f.empty:
                    st.line_chart(df_cyc_f.set_index("date")["hrv"], color="#a855f7", height=155)
            trend_card("HRV 趋势", _hrv)

        # 睡眠
        if not df_cyc.empty and "sleep_hours" in df_cyc.columns:
            df_sleep_f = df_cyc[df_cyc["sleep_hours"].notna() & (df_cyc["date"] >= cutoff_dt)].copy()
            def _sleep():
                if not df_sleep_f.empty:
                    st.bar_chart(df_sleep_f.set_index("date")["sleep_hours"], color="#3b82f6", height=155)
            avg_sl = round(df_sleep_f["sleep_hours"].mean(), 1) if not df_sleep_f.empty else None
            sl_note = f"均值 {avg_sl}h {'✅' if avg_sl and avg_sl>=7 else '⚠️ 睡眠不足'}" if avg_sl else None
            trend_card("睡眠时长 (h)", _sleep, sl_note)

        # 垂直振幅比
        def _vr():
            if not df_gr_f.empty and "vertical_ratio_pct" in df_gr_f.columns and df_gr_f["vertical_ratio_pct"].notna().any():
                st.line_chart(df_gr_f.set_index("date")["vertical_ratio_pct"].dropna(), color="#f97316", height=155)
            else:
                st.markdown('<div style="color:#9ca3af;font-size:0.85rem;padding:20px 0">运行 update_garmin.py 后显示</div>', unsafe_allow_html=True)
        avg_vr = round(df_gr_f["vertical_ratio_pct"].dropna().mean(), 1) if not df_gr_f.empty and "vertical_ratio_pct" in df_gr_f.columns and df_gr_f["vertical_ratio_pct"].notna().any() else None
        vr_note = f"均值 {avg_vr}% {'✅' if avg_vr and avg_vr<=8.5 else '⚠️ 偏高，减少上下弹跳'}" if avg_vr else None
        trend_card("垂直振幅比 (%)", _vr, vr_note)

    # All runs table
    with st.expander("跑步记录详情"):
        cols = ["date","distance","pace","heartrate","cadence","stride_cm"]
        cols_e = [c for c in cols if c in df.columns]
        d = df[cols_e].rename(columns={"date":"日期","distance":"距离km","pace":"配速","heartrate":"心率","cadence":"步频","stride_cm":"步幅cm"})
        d["日期"] = d["日期"].dt.strftime("%m-%d")
        st.dataframe(d.sort_values("日期",ascending=False), hide_index=True, use_container_width=True)


# ──────────────────────────────────────────────────────
# TAB: 身体
# ──────────────────────────────────────────────────────

with tab_body:
    # ── At a Glance ──────────────────────────────────────
    st.markdown("**📊 今日一览**")
    g1, g2, g3, g4, g5 = st.columns(5)

    sleep_d  = garmin.get("sleep", {}) or {}
    hrv_d    = garmin.get("hrv", {}) or {}
    es_d     = garmin.get("endurance_score") or {}
    bb_cur   = garmin.get("body_battery_current")
    bb_chg   = sleep_d.get("body_battery_change")
    rhr      = sleep_d.get("resting_hr")
    hrv_val  = hrv_d.get("last_night_avg")
    hrv_7d   = hrv_d.get("weekly_avg")
    hrv_st   = hrv_d.get("status","")
    slp_h    = sleep_d.get("total_hours")
    slp_sc   = sleep_d.get("sleep_score")

    with g1:
        rhr_color = "#2d4a3e" if rhr and rhr < 55 else "#b8952a" if rhr and rhr < 65 else "#c0543a"
        st.markdown(f"""<div class="card" style="text-align:center;padding:16px 12px">
<div style="font-size:0.7rem;color:#9ca3af;margin-bottom:8px">❤️ 静息心率</div>
<div style="font-size:1.8rem;font-weight:800;color:{rhr_color}">{rhr or '—'}</div>
<div style="font-size:0.72rem;color:#9ca3af">bpm</div>
</div>""", unsafe_allow_html=True)

    with g2:
        bb_color = "#2d4a3e" if bb_cur and bb_cur >= 60 else "#b8952a" if bb_cur and bb_cur >= 30 else "#c0543a"
        charged_str = f'<div style="font-size:0.72rem;color:#2d4a3e">+{bb_chg} 充电</div>' if bb_chg and bb_chg > 0 else ""
        st.markdown(f"""<div class="card" style="text-align:center;padding:16px 12px">
<div style="font-size:0.7rem;color:#9ca3af;margin-bottom:8px">⚡ Body Battery</div>
<div style="font-size:1.8rem;font-weight:800;color:{bb_color}">{bb_cur or '—'}</div>
{charged_str}
</div>""", unsafe_allow_html=True)

    with g3:
        slp_color = "#2d4a3e" if slp_h and slp_h >= 7 else "#b8952a" if slp_h and slp_h >= 6 else "#c0543a"
        sc_str = f'<div style="font-size:0.72rem;color:#9ca3af">得分 {slp_sc}</div>' if slp_sc else ""
        st.markdown(f"""<div class="card" style="text-align:center;padding:16px 12px">
<div style="font-size:0.7rem;color:#9ca3af;margin-bottom:8px">😴 睡眠</div>
<div style="font-size:1.8rem;font-weight:800;color:{slp_color}">{slp_h or '—'}</div>
<div style="font-size:0.72rem;color:#9ca3af">小时</div>
{sc_str}
</div>""", unsafe_allow_html=True)

    with g4:
        hrv_ok = "BALANCED" in (hrv_st or "")
        hrv_color = "#2d4a3e" if hrv_ok else "#c0543a"
        st.markdown(f"""<div class="card" style="text-align:center;padding:16px 12px">
<div style="font-size:0.7rem;color:#9ca3af;margin-bottom:8px">💓 HRV</div>
<div style="font-size:1.8rem;font-weight:800;color:{hrv_color}">{hrv_val or '—'}</div>
<div style="font-size:0.72rem;color:{hrv_color}">{'平衡' if hrv_ok else '偏低'}</div>
<div style="font-size:0.7rem;color:#9ca3af">7日均值 {hrv_7d or '—'}</div>
</div>""", unsafe_allow_html=True)

    with g5:
        # 用最近一跑的耐力消耗替代 Endurance Score
        gr_list = garmin.get("garmin_runs", [])
        last_stamina = next((g for g in gr_list if g.get("stamina_end_pct") is not None), None)
        if last_stamina:
            s_end = round(last_stamina["stamina_end_pct"])
            s_start = round(last_stamina.get("stamina_start_pct", 100))
            drop = s_start - s_end
            s_color = "#2d4a3e" if s_end >= 60 else "#b8952a" if s_end >= 35 else "#c0543a"
            s_label = "储备充足" if s_end >= 60 else "适度消耗" if s_end >= 35 else "透支"
            st.markdown(f"""<div class="card" style="text-align:center;padding:16px 12px">
<div style="font-size:0.7rem;color:#9ca3af;margin-bottom:8px">🏅 耐力剩余</div>
<div style="font-size:1.8rem;font-weight:800;color:{s_color}">{s_end}%</div>
<div style="font-size:0.72rem;color:#9ca3af">{s_label} (-{drop}%)</div>
</div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="card" style="text-align:center;padding:16px 12px">
<div style="font-size:0.7rem;color:#9ca3af;margin-bottom:8px">🏅 耐力剩余</div>
<div style="font-size:1.4rem;color:#d1c7b8">—</div>
<div style="font-size:0.7rem;color:#c4b5aa">运行脚本后显示</div>
</div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_b1, col_b2 = st.columns([1, 1])

    with col_b1:
        # Running dynamics (last run)
        garmin_runs = garmin.get("garmin_runs", [])
        if garmin_runs:
            gr = garmin_runs[0]
            def fmt(v, unit="", dec=1):
                return f"{round(v,dec)}{unit}" if v is not None else "—"
            def mc(v, lo, hi):
                if v is None: return "#9ca3af"
                return "#2d4a3e" if lo<=v<=hi else "#c0543a"
            def mc_lt(v, t):
                if v is None: return "#9ca3af"
                return "#2d4a3e" if v<=t else "#c0543a"

            te_cn = {"TEMPO":"节奏跑","BASE":"基础有氧","RECOVERY":"恢复","THRESHOLD":"乳酸阈","INTERVAL":"间歇","VO2MAX":"VO2Max"}
            te_label_cn = te_cn.get(gr.get("te_label",""), gr.get("te_label",""))

            st.markdown(f"""<div class="card">
<h4>跑步动态 · {gr['date']} · {gr.get('name','')}</h4>
<div class="dyn-grid">
  <div class="dyn-item"><div class="dv" style="color:{mc(gr.get('cadence_spm'),170,185)}">{fmt(gr.get('cadence_spm'),'',0)}</div><div class="dl">步频 SPM</div><div class="dt">理想 170-180</div></div>
  <div class="dyn-item"><div class="dv" style="color:#2d4a3e">{fmt(gr.get('stride_length_cm'),'cm',0)}</div><div class="dl">步幅</div></div>
  <div class="dyn-item"><div class="dv" style="color:{mc_lt(gr.get('ground_contact_ms'),250)}">{fmt(gr.get('ground_contact_ms'),'ms',0)}</div><div class="dl">触地时间</div><div class="dt">&lt;250ms 为佳</div></div>
  <div class="dyn-item"><div class="dv" style="color:{mc(gr.get('vertical_oscillation_cm'),6,9)}">{fmt(gr.get('vertical_oscillation_cm'),'cm')}</div><div class="dl">垂直振幅</div><div class="dt">理想 6-9cm</div></div>
  <div class="dyn-item"><div class="dv" style="color:{mc_lt(gr.get('vertical_ratio_pct'),8.5)}">{fmt(gr.get('vertical_ratio_pct'),'%')}</div><div class="dl">垂直振幅比</div><div class="dt">&lt;8.5% 为佳</div></div>
  <div class="dyn-item"><div class="dv" style="color:#6b7280">{fmt(gr.get('avg_power_w'),'W',0)}</div><div class="dl">平均功率</div></div>
</div>
<div style="border-top:1px solid #f0ebe0;margin:12px 0;padding-top:12px">
<div class="dyn-grid">
  <div class="dyn-item"><div class="dv" style="color:#b8952a">{fmt(gr.get('aerobic_te'),'',1)}</div><div class="dl">有氧效果 {te_label_cn}</div></div>
  <div class="dyn-item"><div class="dv" style="color:#9ca3af">{fmt(gr.get('anaerobic_te'),'',1)}</div><div class="dl">无氧效果</div></div>
  <div class="dyn-item"><div class="dv" style="color:#2d4a3e">{fmt(gr.get('training_load'),'',0)}</div><div class="dl">训练负荷</div></div>
  <div class="dyn-item"><div class="dv" style="color:#7ecfaa">{fmt(gr.get('stamina_start_pct'),'%',0)} → {fmt(gr.get('stamina_end_pct'),'%',0)}</div><div class="dl">耐力消耗</div></div>
  <div class="dyn-item"><div class="dv" style="color:{'#c0543a' if (gr.get('body_battery_change') or 0)<0 else '#2d4a3e'}">{fmt(gr.get('body_battery_change'),'',0)}</div><div class="dl">体能电量变化</div></div>
  <div class="dyn-item"><div class="dv" style="color:#6b7280">{gr.get('steps','—')}</div><div class="dl">总步数</div></div>
</div></div></div>""", unsafe_allow_html=True)

        # VO2Max
        if garmin.get("vo2max"):
            vo2 = garmin["vo2max"]
            vo2_lv = "精英" if vo2>=60 else "优秀" if vo2>=52 else "良好" if vo2>=44 else "一般"
            # Progress bar 0-80
            pct = min(100, round(vo2/80*100))
            st.markdown(f"""<div class="card">
<h4>VO2Max</h4>
<div style="display:flex;align-items:center;gap:14px;margin-bottom:10px">
  <div style="font-size:2.2rem;font-weight:800;color:#2d4a3e">{vo2}</div>
  <div><div style="font-weight:600">{vo2_lv}</div><div style="font-size:0.78rem;color:#9ca3af">mL/kg/min</div></div>
</div>
<div class="prog-wrap">
  <div class="prog-bar-bg"><div class="prog-bar-fill" style="width:{pct}%;background:#2d4a3e"></div></div>
  <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:#9ca3af;margin-top:3px"><span>0</span><span>一般 44</span><span>优秀 52</span><span>精英 60+</span></div>
</div>
</div>""", unsafe_allow_html=True)

        # Endurance card
        stamina_runs = [g for g in garmin_runs if g.get("stamina_start_pct") is not None]
        if stamina_runs:
            latest_s = stamina_runs[0]
            s_start = latest_s.get("stamina_start_pct", 0)
            s_end   = latest_s.get("stamina_end_pct", 0)
            s_drop  = round(s_start - s_end, 1) if s_start and s_end else None
            # Color: less drop = greener
            drop_color = "#2d4a3e" if s_drop and s_drop < 20 else "#b8952a" if s_drop and s_drop < 35 else "#c0543a"

            # Build bar rows for recent runs
            bars_html = ""
            for g in stamina_runs[:6]:
                ss = g.get("stamina_start_pct") or 0
                se = g.get("stamina_end_pct") or 0
                d  = g.get("date", "")[-5:]
                dist = g.get("distance_km") or 0
                drop_pct = round(ss - se, 0)
                bar_w = round(se / ss * 100) if ss else 0
                bars_html += f"""
<div style="margin-bottom:8px">
  <div style="display:flex;justify-content:space-between;font-size:0.72rem;color:#9ca3af;margin-bottom:3px">
    <span>{d} · {dist}km</span>
    <span>{round(ss,0)}% → {round(se,0)}% <span style="color:#c0543a">(-{round(drop_pct,0)}%)</span></span>
  </div>
  <div style="background:#f0ebe0;border-radius:4px;height:6px;overflow:hidden">
    <div style="width:{bar_w}%;background:#7ecfaa;height:6px;border-radius:4px"></div>
  </div>
</div>"""

            st.markdown(f"""<div class="card">
<h4>耐力 Endurance</h4>
<div style="display:flex;align-items:center;gap:16px;margin-bottom:14px">
  <div>
    <div style="font-size:1.8rem;font-weight:800;color:{drop_color}">-{s_drop}%</div>
    <div style="font-size:0.75rem;color:#9ca3af">最近一跑耐力消耗</div>
  </div>
  <div style="flex:1">
    <div style="font-size:0.82rem;color:#1a1a1a">{round(s_start,0)}% <span style="color:#9ca3af">→</span> {round(s_end,0)}%</div>
    <div style="font-size:0.72rem;color:#9ca3af;margin-top:2px">{'✅ 耐力储备充足' if s_drop and s_drop < 20 else '⚠️ 耐力消耗较大，注意配速控制' if s_drop and s_drop < 35 else '❗ 耐力严重透支'}</div>
  </div>
</div>
<div style="font-size:0.75rem;color:#9ca3af;margin-bottom:6px">近期跑步耐力趋势</div>
{bars_html}
</div>""", unsafe_allow_html=True)

    with col_b2:
        # Body composition
        st.markdown('<div class="card"><h4>体成分 · 最新数据</h4>', unsafe_allow_html=True)
        if body_history:
            latest = body_history[-1]
            metrics = [
                ("体脂", latest.get("body_fat_pct"), "%", 0),
                ("肌肉量", latest.get("muscle_mass_kg"), "kg", 1),
                ("体重", latest.get("weight_kg"), "kg", 1),
                ("内脏脂肪", latest.get("visceral_fat_cm2"), "cm²", 0),
                ("相位角", latest.get("phase_angle"), "°", 1),
            ]
            grid = "".join([
                f'<div class="dyn-item"><div class="dv" style="color:#2d4a3e">{round(v,d) if v else "—"}{u if v else ""}</div><div class="dl">{n}</div></div>'
                for n,v,u,d in metrics if v
            ])
            st.markdown(f'<div class="dyn-grid">{grid}</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="font-size:0.75rem;color:#9ca3af;margin-top:8px">记录于 {latest.get("date","")}</div>', unsafe_allow_html=True)

            # Trend charts if multiple records
            if len(body_history) >= 2:
                df_b = pd.DataFrame(body_history)
                df_b["date"] = pd.to_datetime(df_b["date"])
                if "body_fat_pct" in df_b and df_b["body_fat_pct"].notna().sum() >= 2:
                    st.line_chart(df_b.set_index("date")[["body_fat_pct","muscle_mass_kg"]].dropna(how="all"), height=140)
        else:
            st.markdown('<div style="color:#9ca3af;font-size:0.85rem">运行 update_garmin.py 记录体成分数据（体脂、肌肉量、相位角等）</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # Period tracker — interactive
        st.markdown('<div class="card"><h4>月经周期规律</h4>', unsafe_allow_html=True)

        period_list = sorted(
            [e for e in cycle_history if e.get("cycle_day")==1 or e.get("is_period_start")],
            key=lambda x: x["date"], reverse=True
        )

        # Current prediction display
        if cycle_pred:
            phase_c = PHASE_INFO.get(cycle_pred["cycle_phase"], {})
            days_to_next = cycle_pred["days_to_next"]
            next_p = cycle_pred["next_period"]
            if days_to_next < 0:
                next_str = f'<span style="color:#c0543a">⚠️ 预计已逾期 {-days_to_next} 天</span>'
            elif days_to_next <= 3:
                next_str = f'<span style="color:#c0543a">🔴 {days_to_next} 天后来经（{next_p}）</span>'
            else:
                next_str = f'<span style="color:#6b7280">📅 下次预计 {next_p}（{days_to_next} 天后）</span>'
            st.markdown(f"""
<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
  <span style="font-size:1.6rem">{phase_c.get('emoji','')}</span>
  <div>
    <div style="font-size:1rem;font-weight:700;color:{phase_c.get('color','#333')}">{cycle_pred['cycle_phase']}</div>
    <div style="font-size:0.78rem;color:#9ca3af">D{cycle_pred['cycle_day']} · 周期 {cycle_pred['avg_cycle']} 天</div>
  </div>
</div>
<div style="font-size:0.82rem;margin-bottom:10px">{next_str}</div>
""", unsafe_allow_html=True)

        # Add new period record
        default_date = date.fromisoformat(period_list[0]["date"]) if period_list else date.today()
        with st.form("period_form"):
            st.markdown('<div style="font-size:0.78rem;color:#9ca3af;margin-bottom:4px">记录经期开始日</div>', unsafe_allow_html=True)
            col_pd, col_pl, col_pb = st.columns([2, 1, 1])
            with col_pd:
                new_period_date = st.date_input(
                    "开始日", value=default_date,
                    max_value=date.today(), label_visibility="collapsed"
                )
            with col_pl:
                manual_cycle_len = st.number_input(
                    "周期天数", min_value=20, max_value=45, value=28,
                    step=1, label_visibility="collapsed",
                    help="你的周期长度（天）"
                )
            with col_pb:
                save_period = st.form_submit_button("+ 记录", use_container_width=True)

            if save_period:
                date_str = str(new_period_date)
                updated = [e for e in cycle_history if e.get("date") != date_str]
                updated.append({
                    "date": date_str, "cycle_day": 1, "cycle_phase": "月经期",
                    "is_period_start": True, "cycle_length": int(manual_cycle_len)
                })
                updated.sort(key=lambda x: x["date"])
                ok, msg = push_json_to_github("cycle_data.json", updated, f"Record period start {date_str}")
                if ok:
                    st.session_state.cycle_data = updated
                    st.success(f"✅ 已记录 {date_str}，周期 {manual_cycle_len} 天")
                    st.rerun()
                else:
                    st.error(msg + "（请检查 GITHUB_TOKEN）")

        # History list with delete buttons
        if period_list:
            st.markdown('<div style="margin-top:10px;font-size:0.75rem;color:#9ca3af;margin-bottom:4px">历史记录</div>', unsafe_allow_html=True)
            for i, p in enumerate(period_list[:6]):
                d_str = p["date"]
                stored_len = p.get("cycle_length")
                if stored_len:
                    length_str = f"周期 {stored_len} 天"
                elif i < len(period_list) - 1:
                    prev = date.fromisoformat(period_list[i+1]["date"])
                    length_str = f"周期 {(date.fromisoformat(d_str) - prev).days} 天"
                else:
                    length_str = "最近一次"

                col_dl, col_dt, col_dd = st.columns([2, 1, 0.4])
                with col_dl:
                    st.markdown(f'<div style="font-size:0.85rem;padding:6px 0;color:#1a1a1a">{d_str}</div>', unsafe_allow_html=True)
                with col_dt:
                    st.markdown(f'<div style="font-size:0.8rem;padding:6px 0;color:#9ca3af">{length_str}</div>', unsafe_allow_html=True)
                with col_dd:
                    if st.button("✕", key=f"del_period_{d_str}", help=f"删除 {d_str}"):
                        updated = [e for e in cycle_history if e.get("date") != d_str or not (e.get("is_period_start") or e.get("cycle_day")==1)]
                        ok, msg = push_json_to_github("cycle_data.json", updated, f"Delete period {d_str}")
                        if ok:
                            st.session_state.cycle_data = updated
                            st.rerun()
                        else:
                            st.error(msg)

        st.markdown('</div>', unsafe_allow_html=True)

        # Strength
        if garmin.get("strength"):
            st.markdown('<div class="card"><h4>近期力量训练</h4>', unsafe_allow_html=True)
            for s in garmin["strength"][:4]:
                st.markdown(f'<div style="padding:6px 0;border-bottom:1px solid #f0ebe0;font-size:0.85rem">🏋️ <b>{s["date"]}</b> {s["name"]} · {s["duration_min"]}min</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
