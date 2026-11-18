import os
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo
import sqlite3

from database import get_connection

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ============================================================
# INDIA TIMEZONE
# ============================================================

try:
    INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")
except Exception:
    from datetime import timezone, timedelta
    INDIA_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


def get_india_datetime():
    return datetime.now(INDIA_TIMEZONE)


# ============================================================
# DEFAULT TIME SETTINGS (Fallback)
# ============================================================

DEFAULT_START_TIME = time(8, 30)    # 08:30 AM
DEFAULT_END_TIME = time(16, 0)      # 04:00 PM


# ============================================================
# GET ATTENDANCE SCHEDULE FOR USER
# ============================================================

def get_user_schedule(user_id=None):
    """
    Fetch attendance settings for a user, or return default schedule.
    """
    if user_id is None:
        return {
            "mode": "full_time",
            "start_time": DEFAULT_START_TIME,
            "end_time": DEFAULT_END_TIME,
            "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        }

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT attendance_mode, start_time, end_time, working_days
        FROM attendance_settings
        WHERE user_id = ?
    """, (user_id,))

    row = cursor.fetchone()
    connection.close()

    if not row:
        return {
            "mode": "full_time",
            "start_time": DEFAULT_START_TIME,
            "end_time": DEFAULT_END_TIME,
            "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        }

    try:
        import json
        working_days = json.loads(row["working_days"]) if row["working_days"] else []
    except Exception:
        working_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    try:
        sh, sm = map(int, row["start_time"].split(":"))
        eh, em = map(int, row["end_time"].split(":"))
        start_t = time(sh, sm)
        end_t = time(eh, em)
    except Exception:
        start_t = DEFAULT_START_TIME
        end_t = DEFAULT_END_TIME

    return {
        "mode": row["attendance_mode"],
        "start_time": start_t,
        "end_time": end_t,
        "working_days": working_days
    }


# ============================================================
# CHECK ATTENDANCE WINDOW
# ============================================================

def is_attendance_open(user_id=None):
    now = get_india_datetime()
    current_time = now.time()
    today_name = now.strftime("%A")

    schedule = get_user_schedule(user_id)

    # If full_time mode, it is always open
    if schedule["mode"] == "full_time":
        return True

    # Check working day
    if schedule["working_days"] and today_name not in schedule["working_days"]:
        return False

    return schedule["start_time"] <= current_time <= schedule["end_time"]


# ============================================================
# GET ATTENDANCE STATUS
# ============================================================

def get_attendance_status(user_id=None):
    now = get_india_datetime()
    current_time = now.time()
    today_name = now.strftime("%A")

    schedule = get_user_schedule(user_id)

    if schedule["mode"] == "full_time":
        return {
            "open": True,
            "message": "🟢 Attendance is OPEN (24/7 Full-time Mode)",
            "start": "All Day",
            "end": "All Day",
            "current_time": now.strftime("%I:%M:%S %p")
        }

    if schedule["working_days"] and today_name not in schedule["working_days"]:
        return {
            "open": False,
            "message": f"🔴 Attendance is CLOSED (Today is {today_name}, not a configured working day).",
            "start": schedule["start_time"].strftime("%I:%M %p"),
            "end": schedule["end_time"].strftime("%I:%M %p"),
            "current_time": now.strftime("%I:%M:%S %p")
        }

    if schedule["start_time"] <= current_time <= schedule["end_time"]:
        return {
            "open": True,
            "message": "🟢 Attendance is OPEN",
            "start": schedule["start_time"].strftime("%I:%M %p"),
            "end": schedule["end_time"].strftime("%I:%M %p"),
            "current_time": now.strftime("%I:%M:%S %p")
        }

    if current_time < schedule["start_time"]:
        return {
            "open": False,
            "message": "🟡 Attendance has not started yet.",
            "start": schedule["start_time"].strftime("%I:%M %p"),
            "end": schedule["end_time"].strftime("%I:%M %p"),
            "current_time": now.strftime("%I:%M:%S %p")
        }

    return {
        "open": False,
        "message": "🔴 Attendance is CLOSED",
        "start": schedule["start_time"].strftime("%I:%M %p"),
        "end": schedule["end_time"].strftime("%I:%M %p"),
        "current_time": now.strftime("%I:%M:%S %p")
    }


# ============================================================
# MARK ATTENDANCE
# ============================================================

def mark_attendance(student_id, confidence, user_id=None):
    """
    Marks attendance for a student.
    If user_id is omitted or None, it will be automatically fetched from the student record.
    """
    connection = get_connection()
    cursor = connection.cursor()

    # 1. Fetch student info
    if user_id:
        cursor.execute(
            """
            SELECT student_id, user_id, name, class_name, section
            FROM students
            WHERE student_id = ? AND user_id = ?
            """,
            (student_id, user_id)
        )
    else:
        cursor.execute(
            """
            SELECT student_id, user_id, name, class_name, section
            FROM students
            WHERE student_id = ?
            """,
            (student_id,)
        )

    student = cursor.fetchone()

    if student is None:
        connection.close()
        return {
            "success": False,
            "already_marked": False,
            "student_id": student_id,
            "message": "❌ Student not found in database."
        }

    student_name = student["name"]
    actual_user_id = student["user_id"]

    now = get_india_datetime()
    today = now.strftime("%Y-%m-%d")
    current_time_str = now.strftime("%H:%M:%S")

    # 2. Check if already marked present today
    cursor.execute(
        """
        SELECT attendance_id, time
        FROM attendance
        WHERE student_id = ?
        AND user_id = ?
        AND date = ?
        AND status = 'Present'
        """,
        (
            student_id,
            actual_user_id,
            today
        )
    )

    existing_attendance = cursor.fetchone()

    if existing_attendance is not None:
        previous_time = existing_attendance["time"]
        connection.close()
        return {
            "success": True,
            "already_marked": True,
            "student_id": student_id,
            "name": student_name,
            "time": previous_time,
            "message": f"🟡 {student_name} is already marked PRESENT today at {previous_time}."
        }

    # 3. Insert attendance record
    cursor.execute(
        """
        INSERT INTO attendance
        (
            student_id,
            user_id,
            date,
            time,
            status,
            confidence
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            student_id,
            actual_user_id,
            today,
            current_time_str,
            "Present",
            float(confidence) if confidence is not None else None
        )
    )

    connection.commit()
    connection.close()

    return {
        "success": True,
        "already_marked": False,
        "student_id": student_id,
        "name": student_name,
        "date": today,
        "time": current_time_str,
        "confidence": confidence,
        "message": f"✅ Attendance marked for {student_name}!"
    }
