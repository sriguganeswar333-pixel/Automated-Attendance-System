import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from attendance import mark_attendance
from database import get_connection

print()
print("======================================")
print("       ATTENDANCE TEST")
print("======================================")
print()

conn = get_connection()
cursor = conn.cursor()
cursor.execute("SELECT student_id, user_id, name FROM students ORDER BY student_id LIMIT 1")
student = cursor.fetchone()
conn.close()

if student:
    s_id = student["student_id"]
    u_id = student["user_id"]
    name = student["name"]
    print(f"Testing attendance for: {name} (ID: {s_id}, User ID: {u_id})")

    result = mark_attendance(
        student_id=s_id,
        confidence=35.26,
        user_id=u_id
    )

    print(result["message"])

    if result.get("date"):
        print(f"📅 Date: {result['date']}")
        print(f"⏰ Time: {result['time']}")
else:
    print("❌ No students found in database to test.")

print()
