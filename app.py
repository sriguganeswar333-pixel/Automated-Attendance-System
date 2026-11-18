from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    Response,
    send_file
)
import csv
import base64
import cv2
import numpy as np
from attendance import mark_attendance
import io
import math

import os
import sys
import subprocess
import json
import sqlite3

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from werkzeug.security import check_password_hash

from database import (
    initialize_database,
    create_user,
    get_user,
    get_user_by_id,
    get_connection,
    update_institution_type
)

from ai.face_detection import detect_face
from ai.face_recognition import train_model


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "automated-attendance-system-secret-key"
)

app.config["SESSION_PERMANENT"] = False

# Keep the Flask login session stable while moving between
# dashboard, attendance, students and the attendance result page.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False


# ============================================================
# PROJECT DIRECTORY
# ============================================================

PROJECT_DIRECTORY = os.path.dirname(
    os.path.abspath(__file__)
)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

initialize_database()


def initialize_authentication_database():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


def initialize_attendance_settings_database():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance_settings (
            settings_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            attendance_mode TEXT NOT NULL DEFAULT 'full_time',
            start_time TEXT NOT NULL DEFAULT '08:30',
            end_time TEXT NOT NULL DEFAULT '16:00',
            working_days TEXT NOT NULL DEFAULT
                '["Monday","Tuesday","Wednesday","Thursday","Friday"]',
            setup_complete INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    connection.commit()
    connection.close()


initialize_authentication_database()
initialize_attendance_settings_database()


# ============================================================
# INDIA TIMEZONE
# ============================================================

try:
    INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")

except Exception:

    from datetime import timezone, timedelta

    INDIA_TIMEZONE = timezone(
        timedelta(hours=5, minutes=30)
    )


def get_india_datetime():

    return datetime.now(INDIA_TIMEZONE)


# ============================================================
# DEFAULT SETTINGS
# ============================================================

DEFAULT_WORKING_DAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday"
]


# ============================================================
# ATTENDANCE SETTINGS FUNCTIONS
# ============================================================

def get_attendance_settings(user_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM attendance_settings
        WHERE user_id = ?
    """, (user_id,))

    settings = cursor.fetchone()

    connection.close()

    return settings


def save_attendance_settings(
    user_id,
    attendance_mode,
    start_time,
    end_time,
    working_days
):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO attendance_settings
        (
            user_id,
            attendance_mode,
            start_time,
            end_time,
            working_days,
            setup_complete
        )
        VALUES (?, ?, ?, ?, ?, 1)

        ON CONFLICT(user_id)
        DO UPDATE SET
            attendance_mode = excluded.attendance_mode,
            start_time = excluded.start_time,
            end_time = excluded.end_time,
            working_days = excluded.working_days,
            setup_complete = 1,
            updated_at = CURRENT_TIMESTAMP
    """, (
        user_id,
        attendance_mode,
        start_time,
        end_time,
        json.dumps(working_days)
    ))

    connection.commit()
    connection.close()


def attendance_settings_completed(user_id):

    settings = get_attendance_settings(user_id)

    if settings is None:
        return False

    return bool(settings["setup_complete"])


# ============================================================
# GET CURRENT USER ATTENDANCE SETTINGS
# ============================================================

def get_current_attendance_settings():

    default_settings = {
        "mode": "full_time",
        "start_time": "00:00",
        "end_time": "23:59",
        "working_days": [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday"
        ]
    }

    user_id = session.get("user_id")

    if not user_id:

        return default_settings

    settings = get_attendance_settings(
        user_id
    )

    if settings is None:

        return default_settings

    # --------------------------------------------------------
    # READ WORKING DAYS SAFELY
    # --------------------------------------------------------

    try:

        working_days = settings["working_days"]

        if isinstance(working_days, str):

            working_days = json.loads(
                working_days
            )

        if not isinstance(working_days, list):

            working_days = default_settings["working_days"]

    except Exception:

        working_days = default_settings["working_days"]

    # --------------------------------------------------------
    # READ MODE AND TIME SAFELY
    # --------------------------------------------------------

    mode = settings["attendance_mode"] or "full_time"

    start_time = settings["start_time"] or "00:00"

    end_time = settings["end_time"] or "23:59"

    # --------------------------------------------------------
    # NORMALIZE MODE VALUES
    # --------------------------------------------------------

    mode = str(mode).strip().lower()

    if mode in [
        "full-time",
        "fulltime",
        "full time"
    ]:

        mode = "full_time"

    elif mode in [
        "custom-time",
        "custom time",
        "timed"
    ]:

        mode = "custom"

    # --------------------------------------------------------
    # FULL-TIME MODE
    # --------------------------------------------------------

    if mode == "full_time":

        start_time = "00:00"

        end_time = "23:59"

    return {
        "mode": mode,
        "start_time": start_time,
        "end_time": end_time,
        "working_days": working_days
    }


def format_time_for_display(value):

    try:

        return datetime.strptime(
            value,
            "%H:%M"
        ).strftime("%I:%M %p")

    except Exception:

        return value


def time_from_string(value):

    try:

        return datetime.strptime(
            value,
            "%H:%M"
        ).time()

    except Exception:

        return None


# ============================================================
# LOGIN PROTECTION
# ============================================================

@app.context_processor
def inject_institution_context():
    inst_type = "school"
    if "user_id" in session:
        if "institution_type" in session and session["institution_type"]:
            inst_type = session["institution_type"]
        else:
            try:
                acc = get_user_by_id(session["user_id"])
                if acc and "institution_type" in acc.keys() and acc["institution_type"]:
                    inst_type = acc["institution_type"]
                    session["institution_type"] = inst_type
            except Exception:
                pass
    return dict(institution_type=inst_type)


@app.before_request
def require_login():

    allowed_endpoints = {
        "login",
        "signup",
        "static"
    }

    # Login and signup are public
    if request.endpoint in allowed_endpoints:
        return None

    # All other pages require login
    if "user_id" not in session:
        return redirect(url_for("login"))

    return None


# ============================================================
# SIGN UP
# ============================================================

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        username = request.form.get(
            "username",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        institution_type = request.form.get(
            "institution_type",
            ""
        ).strip().lower()

        if not name or not username or not email or not password:

            return render_template(
                "signup.html",
                error="All fields are required."
            )

        if password != confirm_password:

            return render_template(
                "signup.html",
                error="Passwords do not match."
            )

        if institution_type not in [
            "school",
            "college"
        ]:

            return render_template(
                "signup.html",
                error="Please select School or College."
            )

        if len(password) < 6:

            return render_template(
                "signup.html",
                error="Password must contain at least 6 characters."
            )

        # --------------------------------------------------------
        # CREATE ACCOUNT
        # School / College is selected ON THIS SIGNUP PAGE.
        # Therefore there is no second Institution Type page.
        # --------------------------------------------------------

        user_created = create_user(
            name,
            username,
            email,
            password,
            institution_type
        )

        if not user_created:

            return render_template(
                "signup.html",
                error="Username or email already exists."
            )

        return redirect(
            url_for(
                "login",
                registered="1"
            )
        )

    return render_template(
        "signup.html"
    )


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    # Do not use any variable named "user" here.
    # This avoids the previous UnboundLocalError.

    if "user_id" in session:

        # A logged-in user does not need to select Institution Type
        # again. It was already saved during signup.
        # Only Attendance Setup may still be required.

        if not attendance_settings_completed(
            session.get("user_id")
        ):

            return redirect(
                url_for("attendance_setup")
            )

        return redirect(
            url_for("dashboard")
        )

    registered = request.args.get(
        "registered",
        ""
    )

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not username or not password:

            return render_template(
                "login.html",
                error="Username and password are required.",
                registered=registered
            )

        account = get_user(username)

        if account is None:

            return render_template(
                "login.html",
                error="Invalid username or password.",
                registered=registered
            )

        try:

            password_valid = check_password_hash(
                account["password"],
                password
            )

        except Exception:

            password_valid = False

        if not password_valid:

            return render_template(
                "login.html",
                error="Invalid username or password.",
                registered=registered
            )

        # Clear old session data
        session.clear()

        # Save the logged-in account
        session["user_id"] = account["user_id"]
        session["username"] = account["username"]
        session["name"] = account["name"]
        session["email"] = account["email"]
        session["institution_type"] = account["institution_type"] if "institution_type" in account.keys() and account["institution_type"] else "school" 

        # --------------------------------------------------------
        # Institution Type was already selected during signup.
        # Do NOT show institution_setup again.
        # --------------------------------------------------------

        # --------------------------------------------------------
        # NEW ACCOUNT / EXISTING ACCOUNT -> ATTENDANCE SETUP
        # --------------------------------------------------------

        if not attendance_settings_completed(
            account["user_id"]
        ):

            return redirect(
                url_for("attendance_setup")
            )

        return redirect(
            url_for("dashboard")
        )

    return render_template(
        "login.html",
        registered=registered
    )


# ============================================================
# LEGACY INSTITUTION SETUP ROUTE
# ============================================================
# Institution Type is now selected during signup. This route is
# retained only for backward compatibility with older sessions.
# New accounts will never be redirected here.

@app.route(
    "/institution_setup",
    methods=["GET", "POST"]
)
def institution_setup():

    user_id = session.get("user_id")

    if not user_id:

        return redirect(
            url_for("login")
        )

    # --------------------------------------------------------
    # GET CURRENT ACCOUNT
    # --------------------------------------------------------

    account = get_user(
        session.get("username", "")
    )

    if account is None:

        session.clear()

        return redirect(
            url_for("login")
        )

    # Existing completed users should not be forced back here.
    if bool(
        account["institution_setup_complete"]
    ):

        return redirect(
            url_for("dashboard")
        )

    # --------------------------------------------------------
    # SAVE SCHOOL / COLLEGE
    # --------------------------------------------------------

    if request.method == "POST":

        institution_type = request.form.get(
            "institution_type",
            ""
        ).strip().lower()

        if institution_type not in [
            "school",
            "college"
        ]:

            return render_template(
                "institution_setup.html",
                error="Please select School or College."
            )

        saved = update_institution_type(
            user_id,
            institution_type
        )

        if not saved:

            return render_template(
                "institution_setup.html",
                error="Unable to save your selection. Please try again."
            )

        # ----------------------------------------------------
        # FOR NOW: continue to the existing attendance setup.
        # School-specific and College-specific pages will be
        # added later without removing the existing system.
        # ----------------------------------------------------

        return redirect(
            url_for("attendance_setup")
        )

    return render_template(
        "institution_setup.html"
    )


# ============================================================
# ATTENDANCE SETUP
# ============================================================

@app.route(
    "/attendance_setup",
    methods=["GET", "POST"]
)
def attendance_setup():

    user_id = session.get("user_id")

    if not user_id:

        return redirect(
            url_for("login")
        )

    existing_settings = get_attendance_settings(
        user_id
    )

    if request.method == "POST":

        attendance_mode = request.form.get(
            "attendance_mode",
            "custom"
        ).strip()

        start_time = request.form.get(
            "start_time",
            ""
        ).strip()

        end_time = request.form.get(
            "end_time",
            ""
        ).strip()

        working_days = request.form.getlist(
            "working_days"
        )

        if not working_days:

            return render_template(
                "attendance_setup.html",
                settings=existing_settings,
                selected_days=[],
                error="Please select at least one working day."
            )

        if attendance_mode == "full_time":

            start_time = "00:00"
            end_time = "23:59"

        elif attendance_mode == "custom":

            start_object = time_from_string(
                start_time
            )

            end_object = time_from_string(
                end_time
            )

            if start_object is None or end_object is None:

                return render_template(
                    "attendance_setup.html",
                    settings=existing_settings,
                    selected_days=working_days,
                    error="Please enter a valid start and end time."
                )

            if start_object >= end_object:

                return render_template(
                    "attendance_setup.html",
                    settings=existing_settings,
                    selected_days=working_days,
                    error="End time must be later than start time."
                )

        else:

            return render_template(
                "attendance_setup.html",
                settings=existing_settings,
                selected_days=working_days,
                error="Invalid attendance mode."
            )

        save_attendance_settings(
            user_id,
            attendance_mode,
            start_time,
            end_time,
            working_days
        )

        return redirect(
            url_for("dashboard")
        )

    if existing_settings is None:

        settings = {
            "attendance_mode": "full_time",
            "start_time": "00:00",
            "end_time": "23:59",
            "working_days": json.dumps(
                DEFAULT_WORKING_DAYS
            )
        }

    else:

        settings = existing_settings

    try:

        selected_days = json.loads(
            settings["working_days"]
        )

    except Exception:

        selected_days = DEFAULT_WORKING_DAYS

    return render_template(
        "attendance_setup.html",
        settings=settings,
        selected_days=selected_days
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# ============================================================
# ATTENDANCE STATUS
# ============================================================

# ============================================================
# ATTENDANCE STATUS
# ============================================================

def get_attendance_status():

    settings = get_current_attendance_settings()

    current_datetime = get_india_datetime()

    current_time = current_datetime.time()

    today_name = current_datetime.strftime(
        "%A"
    )

    working_days = settings.get(
        "working_days",
        []
    )

    start_time_text = settings.get(
        "start_time",
        "00:00"
    )

    end_time_text = settings.get(
        "end_time",
        "23:59"
    )

    mode = settings.get(
        "mode",
        "full_time"
    )

    # --------------------------------------------------------
    # DEBUG INFORMATION
    # --------------------------------------------------------

    print()
    print("======================================")
    print("       ATTENDANCE STATUS CHECK")
    print("======================================")
    print("Current India date :", current_datetime.strftime("%Y-%m-%d"))
    print("Current India time :", current_datetime.strftime("%I:%M:%S %p"))
    print("Today              :", today_name)
    print("Attendance mode    :", mode)
    print("Start time         :", start_time_text)
    print("End time           :", end_time_text)
    print("Working days       :", working_days)
    print("======================================")
    print()

    # --------------------------------------------------------
    # NORMALIZE WORKING DAYS
    # --------------------------------------------------------

    if not isinstance(working_days, list):

        working_days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday"
        ]

    working_days = [
        str(day).strip()
        for day in working_days
    ]

    # --------------------------------------------------------
    # FULL-TIME MODE
    # --------------------------------------------------------

    if mode == "full_time":

        start_time_text = "00:00"

        end_time_text = "23:59"

    # --------------------------------------------------------
    # CONVERT TIME
    # --------------------------------------------------------

    start_time = time_from_string(
        start_time_text
    )

    end_time = time_from_string(
        end_time_text
    )

    # --------------------------------------------------------
    # INVALID TIME SETTINGS
    # --------------------------------------------------------

    if start_time is None or end_time is None:

        return {
            "status": "closed",
            "label": "Attendance Closed",
            "message": "Attendance time settings are invalid.",
            "can_take": False
        }

    # --------------------------------------------------------
    # CHECK WORKING DAY
    # --------------------------------------------------------

    if today_name not in working_days:

        return {
            "status": "closed",
            "label": "Non-Working Day",
            "message": (
                f"Attendance is not scheduled for {today_name}. "
                f"Selected days: {', '.join(working_days)}"
            ),
            "can_take": False
        }

    # --------------------------------------------------------
    # BEFORE ATTENDANCE TIME
    # --------------------------------------------------------

    if current_time < start_time:

        return {
            "status": "not_started",
            "label": "Attendance Not Started",
            "message": (
                "Attendance starts at "
                f"{format_time_for_display(start_time_text)}."
            ),
            "can_take": False
        }

    # --------------------------------------------------------
    # ATTENDANCE OPEN
    # --------------------------------------------------------

    if start_time <= current_time <= end_time:

        return {
            "status": "open",
            "label": "Attendance Open",
            "message": "Attendance is currently active.",
            "can_take": True
        }

    # --------------------------------------------------------
    # AFTER ATTENDANCE TIME
    # --------------------------------------------------------

    return {
        "status": "closed",
        "label": "Attendance Closed",
        "message": (
            "Today's attendance period has ended. "
            f"Attendance was available from "
            f"{format_time_for_display(start_time_text)} "
            f"to "
            f"{format_time_for_display(end_time_text)}."
        ),
        "can_take": False
    }


# ============================================================
# DASHBOARD
# ============================================================
@app.route("/")
def home():

    # NEVER clear the session here.
    # Returning to "/" after attendance must keep the account logged in.
    # Only the explicit /logout route is allowed to call session.clear().
    if "user_id" in session:

        return redirect(
            url_for("dashboard")
        )

    return redirect(
        url_for("login")
    )

    
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM students
        WHERE user_id = ?
    """, (user_id,))
    total_students = cursor.fetchone()[0]

    today_dt = get_india_datetime().date()
    today = today_dt.strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT COUNT(DISTINCT a.student_id)
        FROM attendance a
        JOIN students s ON a.student_id = s.student_id
        WHERE a.date = ?
        AND a.status = 'Present'
        AND s.user_id = ?
    """, (today, user_id))
    present_today = cursor.fetchone()[0]

    absent_today = total_students - present_today
    if absent_today < 0:
        absent_today = 0

    if total_students > 0:
        attendance_rate = (present_today / total_students) * 100
    else:
        attendance_rate = 0

    # --------------------------------------------------------
    # 7-DAY ATTENDANCE TREND (PHASE 4 ANALYTICS)
    # --------------------------------------------------------
    trend_labels = []
    trend_counts = []
    for i in range(6, -1, -1):
        day = today_dt - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        label_str = day.strftime("%d %b")
        cursor.execute("""
            SELECT COUNT(DISTINCT a.student_id)
            FROM attendance a
            JOIN students s ON a.student_id = s.student_id
            WHERE a.date = ?
            AND a.status = 'Present'
            AND s.user_id = ?
        """, (day_str, user_id))
        count = cursor.fetchone()[0]
        trend_labels.append(label_str)
        trend_counts.append(count)

    # --------------------------------------------------------
    # CLASS-WISE ATTENDANCE COMPARISON (PHASE 4 ANALYTICS)
    # --------------------------------------------------------
    cursor.execute("""
        SELECT class_name, section, COUNT(*) as total_in_class
        FROM students
        WHERE user_id = ?
        GROUP BY class_name, section
        ORDER BY class_name, section
    """, (user_id,))
    class_groups = cursor.fetchall()

    class_labels = []
    class_rates = []
    class_present_counts = []
    class_total_counts = []

    for c_name, sec, total_c in class_groups:
        disp_name = f"Class {c_name} ({sec})" if sec else f"Class {c_name}"
        if sec:
            cursor.execute("""
                SELECT COUNT(DISTINCT a.student_id)
                FROM attendance a
                JOIN students s ON a.student_id = s.student_id
                WHERE a.date = ?
                AND a.status = 'Present'
                AND s.user_id = ?
                AND s.class_name = ?
                AND s.section = ?
            """, (today, user_id, c_name, sec))
        else:
            cursor.execute("""
                SELECT COUNT(DISTINCT a.student_id)
                FROM attendance a
                JOIN students s ON a.student_id = s.student_id
                WHERE a.date = ?
                AND a.status = 'Present'
                AND s.user_id = ?
                AND s.class_name = ?
                AND (s.section IS NULL OR s.section = '')
            """, (today, user_id, c_name))
        present_c = cursor.fetchone()[0]
        rate_c = round((present_c / total_c * 100), 1) if total_c > 0 else 0
        class_labels.append(disp_name)
        class_rates.append(rate_c)
        class_present_counts.append(present_c)
        class_total_counts.append(total_c)

    connection.close()

    attendance_status = get_attendance_status()

    current_time = get_india_datetime().strftime(
        "%I:%M:%S %p"
    )

    settings = get_current_attendance_settings()

    return render_template(
        "dashboard.html",
        total_students=total_students,
        present_today=present_today,
        absent_today=absent_today,
        attendance_rate=round(attendance_rate, 1),
        attendance_status=attendance_status,
        attendance_start=format_time_for_display(settings["start_time"]),
        attendance_end=format_time_for_display(settings["end_time"]),
        current_time=current_time,
        trend_labels=trend_labels,
        trend_counts=trend_counts,
        class_labels=class_labels,
        class_rates=class_rates,
        class_present_counts=class_present_counts,
        class_total_counts=class_total_counts
    )


# ============================================================
# TAKE ATTENDANCE (IN-BROWSER LIVE CAMERA SCANNER + KIOSK)
# ============================================================

@app.route("/take_attendance")
def take_attendance():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # Ensure model is trained
    try:
        train_model()
    except Exception as e:
        print("Model check notice:", e)

    status = get_attendance_status()
    settings = get_current_attendance_settings()

    connection = get_connection()
    cursor = connection.cursor()

    # Total students for this teacher/user
    cursor.execute("SELECT COUNT(*) FROM students WHERE user_id = ?", (user_id,))
    total_students = cursor.fetchone()[0]

    # Today's marked attendance records for this teacher/user
    today = get_india_datetime().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT a.student_id, s.name, s.class_name, s.section, s.roll_number, s.department, s.year, a.time, a.status, a.confidence
        FROM attendance a
        INNER JOIN students s ON a.student_id = s.student_id
        WHERE a.date = ? AND a.status = 'Present' AND s.user_id = ?
        ORDER BY a.time DESC
    """, (today, user_id))
    today_records = [dict(r) for r in cursor.fetchall()]
    present_today = len(today_records)
    marked_ids = [r["student_id"] for r in today_records]

    connection.close()

    return render_template(
        "take_attendance.html",
        total_students=total_students,
        present_today=present_today,
        today_records=today_records,
        marked_ids=marked_ids,
        attendance_status=status
    )


@app.route("/api/recognize_attendance", methods=["POST"])
def api_recognize_attendance():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    user_id = session["user_id"]
    data = request.get_json(silent=True) or {}
    image_b64 = data.get("image")

    if not image_b64:
        return jsonify({"success": False, "message": "No image data"}), 400

    try:
        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]
        image_bytes = base64.b64decode(image_b64)
        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"success": False, "message": "Could not decode frame"}), 400

        model_path = os.path.join(PROJECT_DIRECTORY, "data", "face_model.yml")
        if not os.path.exists(model_path):
            train_model()

        if not os.path.exists(model_path):
            return jsonify({"success": False, "message": "Face model not found"}), 400

        recognizer = cv2.face.LBPHFaceRecognizer_create(radius=1, neighbors=8, grid_x=8, grid_y=8)
        recognizer.read(model_path)

        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(70, 70))

        if len(faces) == 0:
            return jsonify({"success": True, "faces_detected": 0, "recognized": False})

        # Load students registered for this user
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT student_id, name, class_name, section, roll_number, department, year FROM students WHERE user_id = ?", (user_id,))
        user_students = {row["student_id"]: dict(row) for row in cur.fetchall()}
        conn.close()

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

        # Test largest face
        x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
        face_roi = gray[y:y + h, x:x + w]
        face_resized = cv2.resize(face_roi, (200, 200))
        face_enhanced = clahe.apply(face_resized)

        predicted_id, confidence = recognizer.predict(face_enhanced)

        # Distance threshold (LBPH distance < 68 is a valid match)
        if predicted_id in user_students and confidence < 68.0:
            student = user_students[predicted_id]
            res = mark_attendance(predicted_id, round(float(confidence), 2), user_id)

            return jsonify({
                "success": True,
                "faces_detected": len(faces),
                "recognized": True,
                "student_id": predicted_id,
                "name": student["name"],
                "class_name": student["class_name"],
                "section": student["section"],
                "confidence": round(float(confidence), 1),
                "box": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
                "already_marked": res.get("already_marked", False),
                "message": res.get("message", "Attendance recorded successfully!")
            })

        return jsonify({
            "success": True,
            "faces_detected": len(faces),
            "recognized": False,
            "box": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
            "message": "Unrecognized Face"
        })

    except Exception as e:
        print("API RECOGNITION ERROR:", e)
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/start_kiosk_process")
def start_kiosk_process():
    if "user_id" not in session:
        return redirect(url_for("login"))

    logged_in_user_id = session["user_id"]
    script_path = os.path.join(PROJECT_DIRECTORY, "live_recognition.py")
    try:
        train_model()
    except Exception:
        pass

    recognition_command = [
        sys.executable,
        "-u",
        script_path,
        str(logged_in_user_id)
    ]

    try:
        if os.name == "nt":
            subprocess.Popen(
                recognition_command,
                cwd=PROJECT_DIRECTORY,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:
            subprocess.Popen(
                recognition_command,
                cwd=PROJECT_DIRECTORY
            )
        flash("🖥️ Standalone Kiosk Mode launched in a separate window!", "info")
    except Exception as e:
        flash(f"Could not launch kiosk: {e}", "error")

    return redirect(url_for("take_attendance"))


# ============================================================
# STUDENTS
# ============================================================

@app.route("/students")
def students():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    account = get_user_by_id(user_id)
    institution_type = account["institution_type"] if account and "institution_type" in account.keys() and account["institution_type"] else "school"

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            student_id,
            user_id,
            name,
            class_name,
            section,
            roll_number,
            department,
            year,
            created_at
        FROM students
        WHERE user_id = ?
        ORDER BY student_id DESC
    """, (user_id,))

    rows = cursor.fetchall()
    connection.close()

    face_dir = os.path.join(PROJECT_DIRECTORY, "data", "faces")
    enriched_students = []

    for s in rows:
        sid = s["student_id"]
        face_path = os.path.join(face_dir, f"student_{sid}.jpg")
        has_face = os.path.isfile(face_path)

        if not has_face and os.path.isdir(face_dir):
            has_face = any(
                f.startswith(f"student_{sid}_")
                for f in os.listdir(face_dir)
            )

        enriched_students.append({
            "student_id": sid,
            "user_id": s["user_id"],
            "name": s["name"],
            "class_name": s["class_name"],
            "section": s["section"],
            "roll_number": s["roll_number"] if "roll_number" in s.keys() and s["roll_number"] else "",
            "department": s["department"] if "department" in s.keys() and s["department"] else "",
            "year": s["year"] if "year" in s.keys() and s["year"] else "",
            "created_at": s["created_at"],
            "has_face": has_face
        })

    return render_template(
        "students.html",
        students=enriched_students,
        institution_type=institution_type
    )


# ============================================================
# STUDENT ATTENDANCE HISTORY & ANALYTICS
# ============================================================

@app.route("/student/<int:student_id>/attendance")
def student_attendance(student_id):

    if "user_id" not in session:
        return redirect(
            url_for("login")
        )

    user_id = session["user_id"]

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            student_id,
            user_id,
            name,
            class_name,
            section,
            created_at
        FROM students
        WHERE student_id = ? AND user_id = ?
    """, (student_id, user_id))

    student = cursor.fetchone()

    if student is None:
        connection.close()
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    # Fetch attendance history for this student
    cursor.execute("""
        SELECT
            attendance_id,
            student_id,
            date,
            time,
            status,
            confidence
        FROM attendance
        WHERE student_id = ? AND user_id = ?
        ORDER BY date DESC, time DESC
    """, (student_id, user_id))

    attendance_records = cursor.fetchall()

    # Calculate overall unique attendance dates logged for this institution
    cursor.execute("""
        SELECT COUNT(DISTINCT date)
        FROM attendance
        WHERE user_id = ?
    """, (user_id,))

    total_dates_row = cursor.fetchone()
    total_dates = (
        total_dates_row[0]
        if total_dates_row and total_dates_row[0] > 0
        else len(attendance_records)
    )

    present_days = sum(
        1 for r in attendance_records
        if r["status"] == "Present"
    )

    total_days = max(total_dates, len(attendance_records))
    absent_days = max(0, total_days - present_days)

    attendance_percentage = (
        round((present_days / total_days) * 100, 1)
        if total_days > 0
        else 0.0
    )

    connection.close()

    return render_template(
        "student_attendance.html",
        student=student,
        total_days=total_days,
        present_days=present_days,
        absent_days=absent_days,
        attendance_percentage=attendance_percentage,
        attendance_records=attendance_records
    )


# ============================================================
# ADD STUDENT
# ============================================================

# ============================================================
# ADD STUDENT
# ============================================================

@app.route(
    "/add_student",
    methods=["GET", "POST"]
)
def add_student():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("login"))

    account = get_user_by_id(user_id)
    institution_type = account["institution_type"] if account and "institution_type" in account.keys() and account["institution_type"] else "school"

    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if institution_type == "college":
            reg_number = request.form.get("reg_number", "").strip()
            department = request.form.get("department", "").strip()
            year = request.form.get("year", "").strip()
            section = request.form.get("section", "").strip()

            if not name or not reg_number or not department or not year or not section:
                return render_template(
                    "add_student.html",
                    error="All fields (Name, Register Number, Department, Year, Section) are required.",
                    institution_type=institution_type
                )

            roll_number = reg_number
            class_name = f"{department} - {year}"

        else:
            roll_number = request.form.get("roll_number", "").strip()
            class_name = request.form.get("class_name", "").strip()
            section = request.form.get("section", "").strip()
            department = ""
            year = ""

            if not name or not roll_number or not class_name or not section:
                return render_template(
                    "add_student.html",
                    error="All fields (Name, Roll Number, Class, Section) are required.",
                    institution_type=institution_type
                )

        connection = None
        try:
            connection = get_connection()
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO students
                (
                    user_id,
                    name,
                    class_name,
                    section,
                    roll_number,
                    department,
                    year
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    name,
                    class_name,
                    section,
                    roll_number,
                    department,
                    year
                )
            )

            connection.commit()
            return redirect(url_for("students"))

        except Exception as error:
            print("❌ Add student error:", error)
            if connection:
                connection.rollback()
            return render_template(
                "add_student.html",
                error=f"Unable to add student: {error}",
                institution_type=institution_type
            )
        finally:
            if connection:
                connection.close()

    return render_template(
        "add_student.html",
        institution_type=institution_type
    )


# ============================================================
# DELETE STUDENT
# ============================================================

@app.route("/delete_student/<int:student_id>")
def delete_student(student_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM attendance
        WHERE student_id = ? AND user_id = ?
    """, (student_id, user_id))

    cursor.execute("""
        DELETE FROM students
        WHERE student_id = ? AND user_id = ?
    """, (student_id, user_id))

    connection.commit()
    connection.close()

    # Remove all face image samples for this student
    import glob
    face_files = glob.glob(
        os.path.join(
            PROJECT_DIRECTORY,
            "data",
            "faces",
            f"student_{student_id}*.jpg"
        )
    )

    for fp in face_files:
        try:
            os.remove(fp)
        except OSError:
            pass

    # Automatically retrain model so deleted student is removed
    try:
        from ai.face_recognition import train_model
        train_model()
    except Exception as e:
        print("Model retraining after delete:", e)

    flash("Student deleted successfully.", "success")
    return redirect(
        url_for("students")
    )


# ============================================================
# FACE REGISTRATION
# ============================================================

@app.route("/face_registration/<int:student_id>")
def face_registration(student_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT student_id, user_id, name, class_name, section, roll_number, department, year, created_at
        FROM students
        WHERE student_id = ? AND user_id = ?
    """, (student_id, user_id))

    student = cursor.fetchone()
    connection.close()

    if student is None:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    return render_template(
        "camera.html",
        student=student
    )


# ============================================================
# MULTI-SAMPLE FACE REGISTRATION & AUTO-TRAIN
# ============================================================

@app.route("/save_face_samples/<int:student_id>", methods=["POST"])
def save_face_samples(student_id):

    if "user_id" not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT student_id, name
        FROM students
        WHERE student_id = ? AND user_id = ?
    """, (student_id, user_id))

    student = cursor.fetchone()
    connection.close()

    if student is None:
        return jsonify({"success": False, "message": "Student not found."}), 404

    files = request.files.getlist("images")
    if not files or len(files) == 0:
        if "image" in request.files:
            files = [request.files["image"]]
        else:
            return jsonify({"success": False, "message": "No face images received."}), 400

    face_directory = os.path.join(
        PROJECT_DIRECTORY,
        "data",
        "faces"
    )
    os.makedirs(face_directory, exist_ok=True)

    # Clean old samples for this student
    import glob
    old_files = glob.glob(os.path.join(face_directory, f"student_{student_id}*.jpg"))
    for f in old_files:
        try:
            os.remove(f)
        except OSError:
            pass

    import cv2
    import numpy as np

    FACE_CASCADE = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    saved_count = 0
    for idx, file_storage in enumerate(files):
        try:
            file_bytes = np.frombuffer(file_storage.read(), np.uint8)
            img = cv2.imdecode(file_bytes, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue

            detected_faces = FACE_CASCADE.detectMultiScale(
                img,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(60, 60)
            )

            if len(detected_faces) > 0:
                # Pick largest face
                x, y, w, h = max(detected_faces, key=lambda b: b[2] * b[3])
                face_roi = img[y:y + h, x:x + w]
                face_resized = cv2.resize(face_roi, (200, 200))
                face_enhanced = CLAHE.apply(face_resized)

                saved_count += 1
                sample_path = os.path.join(
                    face_directory,
                    f"student_{student_id}_{saved_count}.jpg"
                )
                cv2.imwrite(sample_path, face_enhanced)

                # Keep student_{id}.jpg as primary thumbnail
                if saved_count == 1:
                    primary_path = os.path.join(
                        face_directory,
                        f"student_{student_id}.jpg"
                    )
                    cv2.imwrite(primary_path, face_enhanced)
        except Exception as err:
            print(f"Error processing sample {idx}:", err)
            continue

    if saved_count == 0:
        return jsonify({
            "success": False,
            "message": "No clear face could be detected in the captured frames. Please ensure good lighting and look directly at the camera."
        }), 400

    # Auto retrain model
    model_trained = False
    try:
        from ai.face_recognition import train_model
        model_trained = train_model()
    except Exception as e:
        print("Model training error:", e)

    return jsonify({
        "success": True,
        "saved_samples": saved_count,
        "model_trained": model_trained,
        "message": f"Successfully registered {saved_count} face samples and updated the AI face model!"
    })


# ============================================================
# LEGACY / SINGLE PHOTO SAVE FACE
# ============================================================

@app.route(
    "/save_face/<int:student_id>",
    methods=["POST"]
)
def save_face(student_id):

    return save_face_samples(student_id)


# ============================================================
# ATTENDANCE REPORTS & ANALYTICS
# ============================================================

@app.route("/attendance")
def attendance_reports():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()

    selected_date = request.args.get("date", "").strip()
    selected_student = request.args.get("student", "").strip()
    selected_class = request.args.get("class_name", "").strip()
    selected_section = request.args.get("section", "").strip()

    today = get_india_datetime().strftime("%Y-%m-%d")
    report_date = selected_date or today

    # --------------------------------------------------------
    # STUDENTS LIST FOR DROPDOWN
    # --------------------------------------------------------
    cursor.execute("""
        SELECT student_id, name, class_name, section, roll_number, department, year
        FROM students
        WHERE user_id = ?
        ORDER BY name ASC
    """, (user_id,))
    students_list = cursor.fetchall()

    # --------------------------------------------------------
    # ATTENDANCE RECORDS (FILTERED)
    # --------------------------------------------------------
    query = """
        SELECT
            attendance.attendance_id,
            attendance.student_id,
            students.name,
            students.class_name,
            students.section,
            students.roll_number,
            students.department,
            students.year,
            attendance.date,
            attendance.time,
            attendance.status,
            attendance.confidence
        FROM attendance
        INNER JOIN students
            ON attendance.student_id = students.student_id
        WHERE students.user_id = ?
    """
    parameters = [user_id]

    if selected_date:
        query += " AND attendance.date = ? "
        parameters.append(selected_date)

    if selected_student:
        query += " AND attendance.student_id = ? "
        parameters.append(selected_student)

    if selected_class:
        query += " AND students.class_name = ? "
        parameters.append(selected_class)

    if selected_section:
        query += " AND students.section = ? "
        parameters.append(selected_section)

    query += " ORDER BY attendance.date DESC, attendance.time DESC "

    cursor.execute(query, parameters)
    attendance_records = cursor.fetchall()

    # --------------------------------------------------------
    # TOTAL STUDENTS FOR THIS USER
    # --------------------------------------------------------
    cursor.execute("""
        SELECT COUNT(*)
        FROM students
        WHERE user_id = ?
    """, (user_id,))
    total_students = cursor.fetchone()[0]

    # --------------------------------------------------------
    # PRESENT ON REPORT DATE
    # --------------------------------------------------------
    present_query = """
        SELECT
            students.student_id,
            students.name,
            students.class_name,
            students.section,
            students.roll_number,
            students.department,
            students.year,
            MIN(attendance.time) AS time
        FROM attendance
        INNER JOIN students
            ON attendance.student_id = students.student_id
        WHERE students.user_id = ?
        AND attendance.date = ?
        AND attendance.status = 'Present'
    """
    present_parameters = [user_id, report_date]

    if selected_student:
        present_query += " AND students.student_id = ? "
        present_parameters.append(selected_student)
    if selected_class:
        present_query += " AND students.class_name = ? "
        present_parameters.append(selected_class)
    if selected_section:
        present_query += " AND students.section = ? "
        present_parameters.append(selected_section)

    present_query += " GROUP BY students.student_id, students.name, students.class_name, students.section, students.roll_number, students.department, students.year ORDER BY students.name ASC "
    cursor.execute(present_query, present_parameters)
    present_students = cursor.fetchall()
    today_present = len(present_students)

    # --------------------------------------------------------
    # ABSENT ON REPORT DATE
    # --------------------------------------------------------
    absent_query = """
        SELECT
            students.student_id,
            students.name,
            students.class_name,
            students.section,
            students.roll_number,
            students.department,
            students.year
        FROM students
        WHERE students.user_id = ?
        AND students.student_id NOT IN (
            SELECT DISTINCT student_id
            FROM attendance
            WHERE user_id = ?
            AND date = ?
            AND status = 'Present'
        )
    """
    absent_parameters = [user_id, user_id, report_date]

    if selected_student:
        absent_query += " AND students.student_id = ? "
        absent_parameters.append(selected_student)
    if selected_class:
        absent_query += " AND students.class_name = ? "
        absent_parameters.append(selected_class)
    if selected_section:
        absent_query += " AND students.section = ? "
        absent_parameters.append(selected_section)

    absent_query += " ORDER BY students.name ASC "
    cursor.execute(absent_query, absent_parameters)
    absent_students = cursor.fetchall()
    today_absent = len(absent_students)

    # --------------------------------------------------------
    # FILTERED TOTAL & ATTENDANCE RATE
    # --------------------------------------------------------
    filtered_total = today_present + today_absent
    attendance_rate = round((today_present / filtered_total * 100), 1) if filtered_total > 0 else 0.0

    cursor.execute("""
        SELECT COUNT(*)
        FROM attendance
        WHERE user_id = ? AND status = 'Present'
    """, (user_id,))
    total_present = cursor.fetchone()[0]

    # --------------------------------------------------------
    # DEFAULTERS LIST (< 75% ATTENDANCE)
    # --------------------------------------------------------
    cursor.execute("""
        SELECT COUNT(DISTINCT date)
        FROM attendance
        WHERE user_id = ?
    """, (user_id,))
    total_inst_days_row = cursor.fetchone()
    total_inst_days = total_inst_days_row[0] if total_inst_days_row and total_inst_days_row[0] > 0 else 0

    defaulters_list = []
    for s in students_list:
        sid = s["student_id"]
        cursor.execute("""
            SELECT COUNT(DISTINCT date)
            FROM attendance
            WHERE student_id = ? AND user_id = ? AND status = 'Present'
        """, (sid, user_id))
        att_days = cursor.fetchone()[0]

        if total_inst_days > 0:
            pct = round((att_days / total_inst_days) * 100, 1)
        else:
            pct = 100.0

        if pct < 75.0:
            required = math.ceil(0.75 * total_inst_days)
            shortage = max(0, required - att_days)
            defaulters_list.append({
                "student_id": sid,
                "name": s["name"],
                "class_name": s["class_name"],
                "section": s["section"],
                "roll_number": s["roll_number"] if "roll_number" in s.keys() and s["roll_number"] else "",
                "department": s["department"] if "department" in s.keys() and s["department"] else "",
                "year": s["year"] if "year" in s.keys() and s["year"] else "",
                "attended_days": att_days,
                "total_days": total_inst_days,
                "attendance_percentage": pct,
                "shortage": shortage
            })

    connection.close()

    account = get_user_by_id(user_id)
    institution_type = account["institution_type"] if account and "institution_type" in account.keys() and account["institution_type"] else "school"

    return render_template(
        "attendance.html",
        institution_type=institution_type,
        attendance_records=attendance_records,
        students_list=students_list,
        present_students=present_students,
        absent_students=absent_students,
        total_students=total_students,
        total_present=total_present,
        today_present=today_present,
        today_absent=today_absent,
        attendance_rate=attendance_rate,
        selected_date=selected_date,
        selected_student=selected_student,
        selected_class=selected_class,
        selected_section=selected_section,
        report_date=report_date,
        defaulters_list=defaulters_list,
        defaulters_count=len(defaulters_list),
        total_inst_days=total_inst_days
    )


# ============================================================
# EXPORT ATTENDANCE TO CSV
# ============================================================

@app.route("/export_attendance_csv")
def export_attendance_csv():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()

    selected_date = request.args.get("date", "").strip()
    selected_student = request.args.get("student", "").strip()
    selected_class = request.args.get("class_name", "").strip()
    selected_section = request.args.get("section", "").strip()

    query = """
        SELECT
            attendance.attendance_id,
            attendance.student_id,
            students.name,
            students.class_name,
            students.section,
            students.roll_number,
            students.department,
            students.year,
            attendance.date,
            attendance.time,
            attendance.status,
            attendance.confidence
        FROM attendance
        INNER JOIN students
            ON attendance.student_id = students.student_id
        WHERE students.user_id = ?
    """
    parameters = [user_id]

    if selected_date:
        query += " AND attendance.date = ? "
        parameters.append(selected_date)
    if selected_student:
        query += " AND attendance.student_id = ? "
        parameters.append(selected_student)
    if selected_class:
        query += " AND students.class_name = ? "
        parameters.append(selected_class)
    if selected_section:
        query += " AND students.section = ? "
        parameters.append(selected_section)

    query += " ORDER BY attendance.date DESC, attendance.time DESC "
    cursor.execute(query, parameters)
    records = cursor.fetchall()
    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)

    account = get_user_by_id(user_id)
    institution_type = account["institution_type"] if account and "institution_type" in account.keys() and account["institution_type"] else "school"

    if institution_type == "college":
        writer.writerow([
            "Record ID",
            "Student ID",
            "Register Number",
            "Student Name",
            "Department",
            "Year",
            "Section",
            "Date",
            "Time",
            "Attendance Status",
            "Confidence Score"
        ])
        for r in records:
            conf = f"{r['confidence']:.2f}" if r["confidence"] is not None else "N/A"
            writer.writerow([
                r["attendance_id"],
                r["student_id"],
                r["roll_number"] or "N/A",
                r["name"],
                r["department"] or r["class_name"],
                r["year"] or "N/A",
                r["section"],
                r["date"],
                r["time"],
                r["status"],
                conf
            ])
    else:
        writer.writerow([
            "Record ID",
            "Student ID",
            "Roll Number",
            "Student Name",
            "Class",
            "Section",
            "Date",
            "Time",
            "Attendance Status",
            "Confidence Score"
        ])
        for r in records:
            conf = f"{r['confidence']:.2f}" if r["confidence"] is not None else "N/A"
            writer.writerow([
                r["attendance_id"],
                r["student_id"],
                r["roll_number"] or "N/A",
                r["name"],
                r["class_name"],
                r["section"],
                r["date"],
                r["time"],
                r["status"],
                conf
            ])

    timestamp = get_india_datetime().strftime("%Y%m%d_%H%M%S")
    filename = f"attendance_report_{timestamp}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ============================================================
# EXPORT ATTENDANCE TO EXCEL (.XLSX)
# ============================================================

@app.route("/export_attendance_excel")
def export_attendance_excel():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    connection = get_connection()
    cursor = connection.cursor()

    selected_date = request.args.get("date", "").strip()
    selected_student = request.args.get("student", "").strip()
    selected_class = request.args.get("class_name", "").strip()
    selected_section = request.args.get("section", "").strip()

    query = """
        SELECT
            attendance.attendance_id,
            attendance.student_id,
            students.name,
            students.class_name,
            students.section,
            students.roll_number,
            students.department,
            students.year,
            attendance.date,
            attendance.time,
            attendance.status,
            attendance.confidence
        FROM attendance
        INNER JOIN students
            ON attendance.student_id = students.student_id
        WHERE students.user_id = ?
    """
    parameters = [user_id]

    if selected_date:
        query += " AND attendance.date = ? "
        parameters.append(selected_date)
    if selected_student:
        query += " AND attendance.student_id = ? "
        parameters.append(selected_student)
    if selected_class:
        query += " AND students.class_name = ? "
        parameters.append(selected_class)
    if selected_section:
        query += " AND students.section = ? "
        parameters.append(selected_section)

    query += " ORDER BY attendance.date DESC, attendance.time DESC "
    cursor.execute(query, parameters)
    records = cursor.fetchall()
    connection.close()

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()

    # --------------------------------------------------------
    # SHEET 1: ATTENDANCE RECORDS
    # --------------------------------------------------------
    ws = wb.active
    ws.title = "Attendance Records"

    # Title block
    ws.merge_cells("A1:H1")
    ws["A1"] = "AUTOMATED ATTENDANCE MANAGEMENT SYSTEM — REPORT"
    ws["A1"].font = Font(name="Segoe UI", size=15, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    # Generated date block
    ws.merge_cells("A2:H2")
    ws["A2"] = f"Generated On: {get_india_datetime().strftime('%d %B %Y, %I:%M:%S %p')} IST"
    ws["A2"].font = Font(name="Segoe UI", size=10, italic=True, color="64748B")
    ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    account = get_user_by_id(user_id)
    institution_type = account["institution_type"] if account and "institution_type" in account.keys() and account["institution_type"] else "school"

    if institution_type == "college":
        headers = [
            "Record ID",
            "Student ID",
            "Register Number",
            "Student Name",
            "Department",
            "Year",
            "Section",
            "Date",
            "Time",
            "Status",
            "Confidence"
        ]
    else:
        headers = [
            "Record ID",
            "Student ID",
            "Roll Number",
            "Student Name",
            "Class",
            "Section",
            "Date",
            "Time",
            "Status",
            "Confidence"
        ]

    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1")
    )

    ws.append([])  # Blank row 3
    ws.append(headers)  # Row 4
    ws.row_dimensions[4].height = 25

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=4, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    present_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    absent_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    present_font = Font(name="Segoe UI", size=10, bold=True, color="15803D")
    absent_font = Font(name="Segoe UI", size=10, bold=True, color="B91C1C")
    regular_font = Font(name="Segoe UI", size=10)

    for r_idx, r in enumerate(records, start=5):
        ws.row_dimensions[r_idx].height = 22
        conf = f"{r['confidence']:.2f}" if r["confidence"] is not None else "—"
        if institution_type == "college":
            row_values = [
                r["attendance_id"],
                r["student_id"],
                r["roll_number"] or "N/A",
                r["name"],
                r["department"] or r["class_name"],
                r["year"] or "N/A",
                r["section"],
                r["date"],
                r["time"],
                r["status"],
                conf
            ]
        else:
            row_values = [
                r["attendance_id"],
                r["student_id"],
                r["roll_number"] or "N/A",
                r["name"],
                r["class_name"],
                r["section"],
                r["date"],
                r["time"],
                r["status"],
                conf
            ]
        ws.append(row_values)

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=r_idx, column=col_idx)
            cell.font = regular_font
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center", vertical="center")

            if col_idx == 3:  # Name
                cell.alignment = Alignment(horizontal="left", vertical="center")

            if col_idx == 8:  # Status
                if r["status"] == "Present":
                    cell.fill = present_fill
                    cell.font = present_font
                else:
                    cell.fill = absent_fill
                    cell.font = absent_font

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row > 2 and cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = max(max_len + 5, 12)

    # --------------------------------------------------------
    # SHEET 2: DEFAULTERS LIST (< 75%)
    # --------------------------------------------------------
    ws2 = wb.create_sheet(title="Defaulters (<75%)")

    ws2.merge_cells("A1:G1")
    ws2["A1"] = "ATTENDANCE DEFAULTERS LIST (< 75% ATTENDANCE)"
    ws2["A1"].font = Font(name="Segoe UI", size=14, bold=True, color="FFFFFF")
    ws2["A1"].fill = PatternFill(start_color="B91C1C", end_color="B91C1C", fill_type="solid")
    ws2["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 32

    defaulter_headers = [
        "Student ID",
        "Student Name",
        "Class",
        "Section",
        "Total Days",
        "Attended Days",
        "Attendance %",
        "Shortage"
    ]
    ws2.append([])
    ws2.append(defaulter_headers)
    ws2.row_dimensions[3].height = 24

    for col_idx in range(1, len(defaulter_headers) + 1):
        cell = ws2.cell(row=3, column=col_idx)
        cell.font = header_font
        cell.fill = PatternFill(start_color="475569", end_color="475569", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    # Fetch defaulters for user
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT student_id, name, class_name, section
        FROM students
        WHERE user_id = ?
        ORDER BY name ASC
    """, (user_id,))
    all_studs = c.fetchall()

    c.execute("""
        SELECT COUNT(DISTINCT date)
        FROM attendance
        WHERE user_id = ?
    """, (user_id,))
    tot_days_row = c.fetchone()
    tot_days = tot_days_row[0] if tot_days_row and tot_days_row[0] > 0 else 0

    curr_row = 4
    for s in all_studs:
        c.execute("""
            SELECT COUNT(DISTINCT date)
            FROM attendance
            WHERE student_id = ? AND user_id = ? AND status = 'Present'
        """, (s["student_id"], user_id))
        att = c.fetchone()[0]
        pct = round((att / tot_days * 100), 1) if tot_days > 0 else 100.0

        if pct < 75.0:
            shortage = max(0, math.ceil(0.75 * tot_days) - att)
            ws2.append([
                s["student_id"],
                s["name"],
                s["class_name"],
                s["section"],
                tot_days,
                att,
                f"{pct}%",
                f"{shortage} days needed"
            ])
            for col_idx in range(1, len(defaulter_headers) + 1):
                cell = ws2.cell(row=curr_row, column=col_idx)
                cell.font = regular_font
                cell.border = thin_border
                cell.alignment = Alignment(horizontal="center", vertical="center")
                if col_idx == 7:
                    cell.fill = absent_fill
                    cell.font = absent_font
            curr_row += 1

    conn.close()

    for col in ws2.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.row > 2 and cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws2.column_dimensions[col_letter].width = max(max_len + 5, 14)

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)

    timestamp = get_india_datetime().strftime("%Y%m%d_%H%M%S")
    download_name = f"Attendance_Report_{timestamp}.xlsx"

    return send_file(
        bio,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=download_name
    )


# ============================================================
# EXPORT DEFAULTERS EXCEL STANDALONE
# ============================================================

@app.route("/export_defaulters_excel")
def export_defaulters_excel():
    return export_attendance_excel()


# ============================================================
# ATTENDANCE DEBUG PAGE
# ============================================================

@app.route("/attendance_debug")
def attendance_debug():

    settings = get_current_attendance_settings()

    status = get_attendance_status()

    return {
        "logged_in_user_id": session.get("user_id"),
        "settings": settings,
        "status": status,
        "india_time": get_india_datetime().strftime(
            "%Y-%m-%d %I:%M:%S %p"
        )
    }

# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    print()
    print("======================================")
    print("   AUTOMATED ATTENDANCE SYSTEM")
    print("======================================")
    print()

    print(
        "India Time:",
        get_india_datetime().strftime(
            "%Y-%m-%d %I:%M:%S %p"
        )
    )

    print()
    print("Login URL: http://127.0.0.1:5000/login")
    print("Signup URL: http://127.0.0.1:5000/signup")
    print("Dashboard URL: http://127.0.0.1:5000/")
    print()

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
        use_reloader=False
    )

