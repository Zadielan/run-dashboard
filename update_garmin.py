#!/usr/bin/env python3
"""
本地运行此脚本，抓取 Garmin 数据 + 记录经期日志，并推送到 GitHub。
每天运行一次即可。
"""
import garth, json, subprocess, os
from datetime import date, timedelta

GARMIN_USER_ID = "119995800"
REPO_DIR = os.path.expanduser("~/run-dashboard")

print("正在连接 Garmin...")
garth.resume(os.path.expanduser("~/.garth"))

yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
data = {"date": yesterday, "updated_at": str(date.today())}

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
    print(f"✅ 睡眠：{data['sleep']['total_hours']}h")
except Exception as e:
    data["sleep"] = None
    print(f"❌ 睡眠失败：{e}")

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
    print(f"✅ HRV：{data['hrv']['last_night_avg']}")
except Exception as e:
    data["hrv"] = None
    print(f"❌ HRV 失败：{e}")

# 活动列表（跑步 + 力量）
try:
    acts = garth.connectapi("/activitylist-service/activities/search/activities?limit=50&start=0")
except Exception as e:
    acts = []
    print(f"❌ 活动列表失败：{e}")

# 力量训练
strength = [a for a in acts if a.get("activityType", {}).get("typeKey", "") == "strength_training"][:5]
data["strength"] = [{
    "date": a.get("startTimeLocal", "")[:10],
    "name": a.get("activityName", "力量训练"),
    "duration_min": round((a.get("duration") or 0) / 60),
    "calories": a.get("calories"),
} for a in strength]
print(f"✅ 力量训练：{len(data['strength'])} 条")

# VO2Max（从活动列表或用户档案）
try:
    vo2_acts = [a for a in acts if a.get("vO2MaxValue")]
    if vo2_acts:
        data["vo2max"] = vo2_acts[0]["vO2MaxValue"]
        print(f"✅ VO2Max：{data['vo2max']}")
    else:
        profile = garth.connectapi("/userprofile-service/userprofile/personal-information")
        data["vo2max"] = profile.get("vO2Max") or profile.get("vo2Max")
        print(f"✅ VO2Max（档案）：{data['vo2max']}")
except Exception as e:
    data["vo2max"] = None
    print(f"❌ VO2Max 失败：{e}")

# 跑步动态详情（最近10次）
running_acts = [a for a in acts if a.get("activityType", {}).get("typeKey", "") in ("running", "track_running", "treadmill_running")][:10]
garmin_runs = []
print(f"正在获取 {len(running_acts)} 次跑步详情...")
for act in running_acts:
    act_id = act.get("activityId")
    try:
        detail = garth.connectapi(f"/activity-service/activity/{act_id}")
        s = detail.get("summaryDTO", {})
        garmin_runs.append({
            "date": act.get("startTimeLocal", "")[:10],
            "name": act.get("activityName", ""),
            "distance_km": round((s.get("distance") or 0) / 1000, 2),
            "duration_min": round((s.get("duration") or 0) / 60, 1),
            "avg_hr": s.get("averageHR"),
            "max_hr": s.get("maxHR"),
            "calories": s.get("calories"),
            "steps": s.get("steps"),
            # 跑步动态（字段名来自 Garmin API 实测）
            "cadence_spm": round(s.get("averageRunCadence") or 0) or None,  # 已是双脚 SPM
            "stride_length_cm": s.get("strideLength"),          # cm
            "vertical_oscillation_cm": s.get("verticalOscillation"),  # cm
            "vertical_ratio_pct": round(s.get("verticalRatio") or 0, 1) or None,  # %
            "ground_contact_ms": round(s.get("groundContactTime") or 0) or None,  # ms
            "avg_power_w": s.get("averagePower"),
            "normalized_power_w": s.get("normalizedPower"),
            # 训练效果
            "aerobic_te": s.get("trainingEffect"),
            "anaerobic_te": s.get("anaerobicTrainingEffect"),
            "te_label": s.get("trainingEffectLabel"),
            "training_load": s.get("activityTrainingLoad"),
            # 耐力
            "stamina_start_pct": s.get("beginPotentialStamina"),
            "stamina_end_pct": s.get("endPotentialStamina"),
            "body_battery_change": s.get("differenceBodyBattery"),
            "vigorous_min": s.get("vigorousIntensityMinutes"),
        })
    except Exception as e:
        print(f"  ⚠️ 活动 {act_id} 详情失败：{e}")
data["garmin_runs"] = garmin_runs
print(f"✅ 跑步动态：{len(garmin_runs)} 条")

# 保存 garmin_data.json
garmin_path = os.path.join(REPO_DIR, "garmin_data.json")
with open(garmin_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# ============================================================
# 经期日志（自动推算阶段，只需标记经期第一天）
# ============================================================
print("\n=== 今日经期日志 ===")

cycle_path = os.path.join(REPO_DIR, "cycle_data.json")
if os.path.exists(cycle_path):
    with open(cycle_path, encoding="utf-8") as f:
        cycle_history = json.load(f)
else:
    cycle_history = []

today = str(date.today())
today_date = date.today()

# 找到最近一次经期开始日期
period_starts = sorted([
    date.fromisoformat(e["date"])
    for e in cycle_history
    if e.get("cycle_day") == 1 or e.get("is_period_start")
])

# 计算今天预测的周期天数
if period_starts:
    last_start = period_starts[-1]
    days_since = (today_date - last_start).days + 1
    if len(period_starts) >= 2:
        intervals = [(period_starts[i+1] - period_starts[i]).days for i in range(len(period_starts)-1)]
        avg_cycle = round(sum(intervals) / len(intervals))
    else:
        avg_cycle = 28
    actual_day = days_since if days_since <= avg_cycle else days_since % avg_cycle or avg_cycle
    if actual_day <= 5:   auto_phase = "月经期"
    elif actual_day <= 13: auto_phase = "卵泡期"
    elif actual_day <= 15: auto_phase = "排卵期"
    else:                  auto_phase = "黄体期"
    print(f"📅 预测：周期第 {actual_day} 天 → {auto_phase}（基于 {last_start} 开始，平均周期 {avg_cycle} 天）")
else:
    actual_day, auto_phase, avg_cycle = None, None, 28
    print("⚠️ 还没有经期记录，请记录今天是否为经期第一天")

# 只问是否经期开始（其他自动推算）
period_start_input = input("今天是否是经期第一天？(y/n，回车跳过): ").strip().lower()
nutrition_input = input("今日饮食备注（回车跳过）: ").strip()

is_period_start = period_start_input == "y"
if is_period_start:
    actual_day = 1
    auto_phase = "月经期"
    print("✅ 已标记为经期第一天，阶段自动设为月经期")

cycle_history = [e for e in cycle_history if e["date"] != today]
entry = {
    "date": today,
    "cycle_day": actual_day,
    "cycle_phase": auto_phase,
    "is_period_start": is_period_start,
    "nutrition_notes": nutrition_input if nutrition_input else None,
    "hrv": data.get("hrv", {}).get("last_night_avg") if data.get("hrv") else None,
    "sleep_hours": data.get("sleep", {}).get("total_hours") if data.get("sleep") else None,
}
cycle_history.append(entry)
cycle_history.sort(key=lambda x: x["date"])

with open(cycle_path, "w", encoding="utf-8") as f:
    json.dump(cycle_history, f, ensure_ascii=False, indent=2)
print(f"✅ 经期日志已记录：{entry['cycle_phase'] or '暂无记录'}")

# ============================================================
# 体成分录入（测过才需要填，平时直接回车跳过）
# ============================================================
print("\n=== 体成分数据（刚做过 InBody / 体脂测量才需要填，直接回车全部跳过）===")
weight_input   = input("体重 (kg, 回车跳过): ").strip()
fat_input      = input("体脂 (%, 回车跳过): ").strip()
muscle_input   = input("肌肉量 (kg, 回车跳过): ").strip()
visceral_input = input("内脏脂肪 (cm², 回车跳过): ").strip()
phase_input    = input("相位角 (°, 回车跳过): ").strip()

def try_float(s):
    try: return float(s) if s else None
    except: return None

body_entry_data = {
    "weight_kg":          try_float(weight_input),
    "body_fat_pct":       try_float(fat_input),
    "muscle_mass_kg":     try_float(muscle_input),
    "visceral_fat_cm2":   try_float(visceral_input),
    "phase_angle":        try_float(phase_input),
}

if any(v is not None for v in body_entry_data.values()):
    body_path = os.path.join(REPO_DIR, "body_data.json")
    if os.path.exists(body_path):
        with open(body_path, encoding="utf-8") as f:
            body_history = json.load(f)
    else:
        body_history = []
    body_history = [e for e in body_history if e["date"] != today]
    body_entry_data["date"] = today
    body_history.append(body_entry_data)
    body_history.sort(key=lambda x: x["date"])
    with open(body_path, "w", encoding="utf-8") as f:
        json.dump(body_history, f, ensure_ascii=False, indent=2)
    print(f"✅ 体成分已记录：体脂 {fat_input or '—'}%，肌肉量 {muscle_input or '—'}kg")
else:
    print("ℹ️ 体成分：跳过")

# 推送到 GitHub
print("\n正在推送到 GitHub...")
files_to_add = ["garmin_data.json", "cycle_data.json"]
if any(v is not None for v in body_entry_data.values()):
    files_to_add.append("body_data.json")
subprocess.run(["git", "-C", REPO_DIR, "add"] + files_to_add, check=True)
result = subprocess.run(["git", "-C", REPO_DIR, "commit", "-m", f"Update data {today}"], capture_output=True, text=True)
if result.returncode == 0:
    subprocess.run(["git", "-C", REPO_DIR, "push"], check=True)
    print("✅ 完成！App 数据已更新。")
else:
    print("ℹ️ 数据无变化，无需推送。")
