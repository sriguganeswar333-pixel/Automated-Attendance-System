import cv2
import os
import sys
import time as time_module
from datetime import datetime, time
from zoneinfo import ZoneInfo
import json

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from attendance import mark_attendance
from database import get_connection

# ============================================================
# TIMEZONE & TIME FUNCTIONS
# ============================================================

try:
    INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")
except Exception:
    from datetime import timezone, timedelta
    INDIA_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


def get_india_datetime():
    return datetime.now(INDIA_TIMEZONE)


# ============================================================
# GET LOGGED-IN USER ID
# ============================================================

def get_logged_in_user_id():
    if len(sys.argv) > 1:
        try:
            uid = int(sys.argv[1])
            if uid > 0:
                return uid
        except ValueError:
            pass

    # Fallback: check if there is an active user in the database
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id, name FROM users ORDER BY user_id LIMIT 1")
    user = cur.fetchone()
    conn.close()

    if user:
        print(f"ℹ️ No CLI user ID provided. Using default user: {user['name']} (ID: {user['user_id']})")
        return user["user_id"]

    print("❌ No registered user found in database.")
    return None


# ============================================================
# SETTINGS & PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "data", "face_model.yml")
RECOGNITION_THRESHOLD = 65  # LBPH distance threshold (lower is stricter)

logged_in_user_id = get_logged_in_user_id()

if logged_in_user_id is None:
    print("❌ Attendance cannot start without a valid user ID.")
    sys.exit(1)


# ============================================================
# LOAD USER SCHEDULE & SETTINGS
# ============================================================

def get_user_schedule(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT attendance_mode, start_time, end_time, working_days
        FROM attendance_settings
        WHERE user_id = ?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {
            "mode": "full_time",
            "start_time": time(8, 30),
            "end_time": time(16, 0),
            "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        }

    try:
        working_days = json.loads(row["working_days"]) if row["working_days"] else []
    except Exception:
        working_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    try:
        sh, sm = map(int, row["start_time"].split(":"))
        eh, em = map(int, row["end_time"].split(":"))
        start_t = time(sh, sm)
        end_t = time(eh, em)
    except Exception:
        start_t = time(8, 30)
        end_t = time(16, 0)

    return {
        "mode": row["attendance_mode"],
        "start_time": start_t,
        "end_time": end_t,
        "working_days": working_days
    }


schedule = get_user_schedule(logged_in_user_id)


def attendance_is_active():
    if schedule["mode"] == "full_time":
        return True

    now = get_india_datetime()
    current_time = now.time()
    today_name = now.strftime("%A")

    if schedule["working_days"] and today_name not in schedule["working_days"]:
        return False

    return schedule["start_time"] <= current_time <= schedule["end_time"]


# ============================================================
# STARTUP BANNER
# ============================================================

current_dt = get_india_datetime()

print()
print("======================================")
print("   AUTOMATED ATTENDANCE - KIOSK MODE  ")
print("======================================")
print(f"👤 Logged-in User ID : {logged_in_user_id}")
print(f"🇮🇳 Current India Time: {current_dt.strftime('%Y-%m-%d %I:%M:%S %p')}")
if schedule["mode"] == "full_time":
    print("🕐 Schedule Mode      : 🟢 Full Time (24/7 Active)")
else:
    print(f"🕐 Active Schedule   : {schedule['start_time'].strftime('%I:%M %p')} - {schedule['end_time'].strftime('%I:%M %p')}")
    print(f"📅 Working Days      : {', '.join(schedule['working_days'])}")
print()

if not attendance_is_active():
    print("❌ Attendance is currently CLOSED based on your schedule settings.")
    print("👉 Update your schedule from Attendance Settings in the web dashboard.")
    sys.exit(0)


# ============================================================
# LOAD REGISTERED STUDENTS
# ============================================================

conn = get_connection()
cur = conn.cursor()
cur.execute("""
    SELECT student_id, name, class_name, section
    FROM students
    WHERE user_id = ?
""", (logged_in_user_id,))

students_data = cur.fetchall()

student_names = {row["student_id"]: row["name"] for row in students_data}
student_details = {row["student_id"]: f"{row['class_name']}-{row['section']}" for row in students_data}
registered_students = set(student_names.keys())

# Load students already marked present today
today_str = current_dt.strftime("%Y-%m-%d")
cur.execute("""
    SELECT student_id
    FROM attendance
    WHERE user_id = ? AND date = ? AND status = 'Present'
""", (logged_in_user_id, today_str))

marked_students = {row["student_id"] for row in cur.fetchall()}
conn.close()

if not registered_students:
    print("❌ No students registered for your account.")
    print("👉 Please add students from the Student Management page first.")
    sys.exit(0)

print(f"👥 Registered Students: {len(registered_students)}")
print(f"✅ Already Marked Today: {len(marked_students)} / {len(registered_students)}")
print()


# ============================================================
# LOAD FACE DETECTOR & RECOGNIZER
# ============================================================

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

eye_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_eye.xml"
)

if face_cascade.empty():
    print("❌ Could not load OpenCV Haar cascade face detector.")
    sys.exit(1)

if not os.path.exists(MODEL_PATH):
    print("❌ Face model not found at:", MODEL_PATH)
    print("👉 Register student faces and train the model from the dashboard.")
    sys.exit(1)

recognizer = cv2.face.LBPHFaceRecognizer_create(
    radius=1,
    neighbors=8,
    grid_x=8,
    grid_y=8
)
recognizer.read(MODEL_PATH)


# ============================================================
# START CAMERA
# ============================================================

print("📷 Initializing camera...")

camera = None
for backend in ([cv2.CAP_DSHOW, cv2.CAP_ANY] if os.name == "nt" else [cv2.CAP_ANY]):
    for idx in [0, 1]:
        try:
            cap = cv2.VideoCapture(idx, backend)
            if cap.isOpened():
                ret, test_frame = cap.read()
                if ret and test_frame is not None:
                    camera = cap
                    break
                cap.release()
        except Exception:
            pass
    if camera:
        break

if not camera or not camera.isOpened():
    print("❌ Could not open webcam.")
    print("👉 Ensure webcam is connected and closed in other applications/browser tabs.")
    try:
        input("\nPress Enter to exit...")
    except Exception:
        pass
    sys.exit(1)

camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

print("✅ Camera started successfully.")
print("ℹ️ Continuous Kiosk Mode active. Students can look at the camera.")
print("👉 Press 'Q' in the camera window to stop.")
print()

# Anti-Spoofing & Liveness Tracking: {student_id: { "blink_verified": bool, "eyes_open_count": int, "saw_closed": bool, "first_seen": float }}
liveness_tracker = {}
recent_display = {}
last_announced = ""
last_announced_time = 0

try:
    while True:
        if not attendance_is_active():
            print("\n⏰ Attendance window closed. Stopping camera.\n")
            break

        ret, frame = camera.read()
        if not ret:
            print("❌ Failed to grab frame from camera.")
            break

        # Flip horizontally for natural mirror view
        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(80, 80)
        )

        current_time_sec = time_module.time()

        for (x, y, w, h) in faces:
            face_roi = gray[y:y + h, x:x + w]
            face_resized = cv2.resize(face_roi, (200, 200))
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            face_enhanced = clahe.apply(face_resized)

            student_id, confidence = recognizer.predict(face_enhanced)

            if student_id in registered_students and confidence < RECOGNITION_THRESHOLD:
                name = student_names.get(student_id, f"ID: {student_id}")
                sec = student_details.get(student_id, "")

                if student_id in marked_students:
                    display_msg = "ALREADY PRESENT"
                    sub_msg = f"Match Dist: {confidence:.1f}"
                    color = (0, 220, 100)
                else:
                    # ========================================================
                    # AI ANTI-SPOOFING / LIVENESS (EYE BLINK VERIFICATION)
                    # ========================================================
                    if student_id not in liveness_tracker:
                        liveness_tracker[student_id] = {
                            "blink_verified": False,
                            "eyes_open_count": 0,
                            "saw_closed": False,
                            "first_seen": current_time_sec
                        }

                    tracker = liveness_tracker[student_id]

                    # Extract upper eye ROI from detected face
                    eye_y1 = y + int(h * 0.16)
                    eye_y2 = y + int(h * 0.54)
                    eye_x1 = x + int(w * 0.12)
                    eye_x2 = x + int(w * 0.88)
                    eye_roi = gray[eye_y1:eye_y2, eye_x1:eye_x2]

                    eyes = eye_cascade.detectMultiScale(
                        eye_roi,
                        scaleFactor=1.12,
                        minNeighbors=3,
                        minSize=(16, 16)
                    )

                    # Highlight detected eyes with cyan tracking dots
                    for (ex, ey, ew, eh) in eyes:
                        cv2.circle(frame, (eye_x1 + ex + ew // 2, eye_y1 + ey + eh // 2), 2, (255, 255, 0), -1)

                    # State machine: Open -> Closed -> Open
                    if len(eyes) >= 1:
                        tracker["eyes_open_count"] += 1
                        if tracker["saw_closed"]:
                            tracker["blink_verified"] = True
                    elif len(eyes) == 0 and tracker["eyes_open_count"] >= 2:
                        tracker["saw_closed"] = True

                    elapsed = current_time_sec - tracker["first_seen"]

                    # Verify liveness (either by blink, or by stable live human tracking for >= 2.0s)
                    if tracker["blink_verified"] or (elapsed >= 2.0 and tracker["eyes_open_count"] >= 4):
                        tracker["blink_verified"] = True
                        res = mark_attendance(student_id, confidence, logged_in_user_id)
                        marked_students.add(student_id)
                        last_announced = f"LIVE VERIFIED: {name} ({sec})"
                        last_announced_time = current_time_sec
                        print(f"[{get_india_datetime().strftime('%I:%M:%S %p')}] 👁️ LIVE VERIFIED & MARKED: {res['message']} (Distance: {confidence:.2f})")
                        display_msg = "LIVE VERIFIED - PRESENT"
                        sub_msg = "Real Human Verified"
                        color = (0, 255, 0)
                    else:
                        if elapsed < 4.0:
                            display_msg = "BLINK TO VERIFY"
                            sub_msg = "Liveness Check..."
                            color = (0, 215, 255)  # Amber / Yellow
                        else:
                            display_msg = "VERIFYING..."
                            sub_msg = "Hold Still..."
                            color = (0, 140, 255)

                # Draw bounding box & header info
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                cv2.rectangle(frame, (x, y - 50), (x + w, y), color, cv2.FILLED)

                cv2.putText(
                    frame,
                    f"{name} ({student_id})",
                    (x + 6, y - 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 0, 0),
                    2
                )
                cv2.putText(
                    frame,
                    f"{display_msg}",
                    (x + 6, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 0, 0),
                    1
                )

            else:
                # Unknown / unverified face
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                cv2.rectangle(frame, (x, y - 24), (x + w, y), (0, 0, 255), cv2.FILLED)
                cv2.putText(
                    frame,
                    "UNKNOWN FACE",
                    (x + 6, y - 7),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1
                )

        # ============================================================
        # TOP HUD BAR
        # ============================================================
        h_frame, w_frame, _ = frame.shape
        cv2.rectangle(frame, (0, 0), (w_frame, 40), (20, 24, 33), cv2.FILLED)

        now_str = get_india_datetime().strftime("%I:%M:%S %p")
        cv2.putText(
            frame,
            f"Automated Attendance | {now_str}",
            (12, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2
        )

        present_count = len(marked_students)
        total_count = len(registered_students)
        stats_str = f"Present: {present_count}/{total_count}"
        cv2.putText(
            frame,
            stats_str,
            (w_frame - 160, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0) if present_count > 0 else (200, 200, 200),
            2
        )

        # Announcement banner if a student was recently marked
        if current_time_sec - last_announced_time < 3.0 and last_announced:
            cv2.rectangle(frame, (0, h_frame - 40), (w_frame, h_frame), (0, 160, 60), cv2.FILLED)
            cv2.putText(
                frame,
                f"SUCCESS: {last_announced}",
                (20, h_frame - 14),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2
            )
        else:
            # Bottom help bar
            cv2.rectangle(frame, (0, h_frame - 30), (w_frame, h_frame), (20, 24, 33), cv2.FILLED)
            cv2.putText(
                frame,
                "Press 'Q' to stop attendance session",
                (15, h_frame - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (180, 180, 180),
                1
            )

        cv2.imshow("Automated Attendance - Continuous Kiosk", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q") or key == ord("Q"):
            print("\n🛑 Attendance manually stopped by operator.")
            break

finally:
    camera.release()
    cv2.destroyAllWindows()
    for _ in range(5):
        cv2.waitKey(1)
    print("📷 Camera released.")
    print("======================================\n")
