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
            "distance_km": round((act.get("distance") or 0) / 1000, 2),
            "duration_min": round((act.get("duration") or 0) / 60, 1),
            "avg_hr": act.get("averageHR"),
            "max_hr": act.get("maxHR"),
            "aerobic_te": act.get("aerobicTrainingEffect"),
            "anaerobic_te": act.get("anaerobicTrainingEffect"),
            "training_load": act.get("activityTrainingLoad"),
            # 跑步动态
            "cadence_spm": round(float(s.get("averageRunningCadenceInStepsPerMinute") or 0) * 2) or None,
            "stride_length_m": s.get("avgStrideLength"),
            "vertical_oscillation_cm": s.get("avgVerticalOscillation"),
            "vertical_ratio_pct": s.get("avgVerticalRatio"),
            "ground_contact_ms": s.get("avgGroundContactTime"),
            "ground_contact_balance": s.get("avgGroundContactBalance"),
            "power_w": s.get("avgPower"),
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
# 经期日志
# ============================================================
print("\n=== 今日经期日志（直接回车跳过）===")
cycle_day_input = input("经期第几天（不在经期输 0 或回车跳过）: ").strip()
phase_options = {"1": "月经期", "2": "卵泡期", "3": "排卵期", "4": "黄体期"}
print("阶段：1=月经期  2=卵泡期  3=排卵期  4=黄体期")
phase_input = input("选择阶段（输数字，或回车跳过）: ").strip()
nutrition_input = input("今日饮食备注（回车跳过）: ").strip()

cycle_path = os.path.join(REPO_DIR, "cycle_data.json")
if os.path.exists(cycle_path):
    with open(cycle_path, encoding="utf-8") as f:
        cycle_history = json.load(f)
else:
    cycle_history = []

today = str(date.today())
cycle_history = [e for e in cycle_history if e["date"] != today]

entry = {
    "date": today,
    "cycle_day": int(cycle_day_input) if cycle_day_input.isdigit() else None,
    "cycle_phase": phase_options.get(phase_input) or (phase_input if phase_input else None),
    "nutrition_notes": nutrition_input if nutrition_input else None,
    "hrv": data.get("hrv", {}).get("last_night_avg") if data.get("hrv") else None,
    "sleep_hours": data.get("sleep", {}).get("total_hours") if data.get("sleep") else None,
}
cycle_history.append(entry)
cycle_history.sort(key=lambda x: x["date"])

with open(cycle_path, "w", encoding="utf-8") as f:
    json.dump(cycle_history, f, ensure_ascii=False, indent=2)
print(f"✅ 经期日志已记录：{entry['cycle_phase'] or '未填写'}")

# 推送到 GitHub
print("\n正在推送到 GitHub...")
subprocess.run(["git", "-C", REPO_DIR, "add", "garmin_data.json", "cycle_data.json"], check=True)
result = subprocess.run(["git", "-C", REPO_DIR, "commit", "-m", f"Update data {today}"], capture_output=True, text=True)
if result.returncode == 0:
    subprocess.run(["git", "-C", REPO_DIR, "push"], check=True)
    print("✅ 完成！App 数据已更新。")
else:
    print("ℹ️ 数据无变化，无需推送。")
