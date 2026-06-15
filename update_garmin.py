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

# 力量训练
try:
    acts = garth.connectapi("/activitylist-service/activities/search/activities?limit=50&start=0")
    strength = [a for a in acts if a.get("activityType", {}).get("typeKey", "") == "strength_training"][:5]
    data["strength"] = [{
        "date": a.get("startTimeLocal", "")[:10],
        "name": a.get("activityName", "力量训练"),
        "duration_min": round((a.get("duration") or 0) / 60),
        "calories": a.get("calories"),
    } for a in strength]
    print(f"✅ 力量训练：{len(data['strength'])} 条")
except Exception as e:
    data["strength"] = []
    print(f"❌ 力量训练失败：{e}")

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
