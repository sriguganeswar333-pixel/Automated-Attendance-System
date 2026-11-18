import os
import sys
import time
import subprocess
from datetime import datetime, time as datetime_time
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from database import get_connection
from attendance import get_user_schedule

try:
    INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")
except Exception:
    from datetime import timezone, timedelta
    INDIA_TIMEZONE = timezone(timedelta(hours=5, minutes=30))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIVE_RECOGNITION = os.path.join(BASE_DIR, "live_recognition.py")


def get_target_user_id():
    if len(sys.argv) > 1:
        try:
            return int(sys.argv[1])
        except ValueError:
            pass

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id, name FROM users ORDER BY user_id LIMIT 1")
    row = cur.fetchone()
    conn.close()

    if row:
        return row["user_id"]
    return None


def get_india_datetime():
    return datetime.now(INDIA_TIMEZONE)


def wait_until_start(target_user_id):
    schedule = get_user_schedule(target_user_id)
    start_time = schedule["start_time"]
    end_time = schedule["end_time"]

    print()
    print("======================================")
    print("    AUTOMATED ATTENDANCE SCHEDULER")
    print("======================================")
    print(f"👤 Target User ID : {target_user_id}")
    print(f"🇮🇳 Timezone       : Asia/Kolkata")
    if schedule["mode"] == "full_time":
        print("🕐 Schedule Mode  : Full Time (Starts immediately)")
        return True
    else:
        print(f"🕐 Start Time     : {start_time.strftime('%I:%M %p')}")
        print(f"🕐 End Time       : {end_time.strftime('%I:%M %p')}")
    print()

    while True:
        now = get_india_datetime()
        current_time = now.time()

        print(
            "\rCurrent India Time: " + now.strftime("%I:%M:%S %p"),
            end="",
            flush=True
        )

        if current_time < start_time:
            time.sleep(1)
            continue

        if current_time > end_time:
            print("\n\n❌ Today's attendance period has ended.")
            return False

        print("\n\n✅ Attendance time reached!")
        return True


def start_attendance(target_user_id):
    if not os.path.exists(LIVE_RECOGNITION):
        print("❌ live_recognition.py not found.")
        return

    try:
        print("Starting live attendance for user ID:", target_user_id)
        cmd = [sys.executable, LIVE_RECOGNITION, str(target_user_id)]
        process = subprocess.Popen(cmd, cwd=BASE_DIR)
        print("✅ Attendance process started. PID:", process.pid)
        process.wait()
        print("🔥 Attendance process finished.")
    except Exception as error:
        print("❌ Could not start attendance:", error)


if __name__ == "__main__":
    uid = get_target_user_id()
    if not uid:
        print("❌ No valid user found in database.")
        sys.exit(1)

    should_start = wait_until_start(uid)
    if should_start:
        start_attendance(uid)

    print("\nScheduler stopped.")
