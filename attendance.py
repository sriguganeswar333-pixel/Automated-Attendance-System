from database import get_connection
from datetime import datetime, time


# ==================================================
# ATTENDANCE TIME SETTINGS
# ==================================================

ATTENDANCE_START = time(8, 30)   # 08:30 AM
ATTENDANCE_END = time(16, 0)     # 04:00 PM


# ==================================================
# CHECK ATTENDANCE WINDOW
# ==================================================

def is_attendance_open():

    current_time = datetime.now().time()

    return (
        ATTENDANCE_START
        <= current_time
        <= ATTENDANCE_END
    )


# ==================================================
# GET ATTENDANCE STATUS
# ==================================================

def get_attendance_status():

    now = datetime.now()
    current_time = now.time()

    if (
        ATTENDANCE_START
        <= current_time
        <= ATTENDANCE_END
    ):

        return {
            "open": True,
            "message": "🟢 Attendance is OPEN",
            "start": "08:30 AM",
            "end": "04:00 PM"
        }

    return {
        "open": False,
        "message": "🔴 Attendance is CLOSED",
        "start": "08:30 AM",
        "end": "04:00 PM"
    }


# ==================================================
# MARK ATTENDANCE
# ==================================================

def mark_attendance(student_id, confidence):

    # ------------------------------------------------
    # CHECK TIME WINDOW FIRST
    # ------------------------------------------------

    if not is_attendance_open():

        return {
            "success": False,
            "already_marked": False,
            "message":
                "🔴 Attendance is currently CLOSED. "
                "Attendance is available only from "
                "08:30 AM to 04:00 PM."
        }


    connection = get_connection()
    cursor = connection.cursor()


    # ------------------------------------------------
    # CURRENT DATE AND TIME
    # ------------------------------------------------

    now = datetime.now()

    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M:%S")


    # ------------------------------------------------
    # CHECK STUDENT
    # ------------------------------------------------

    cursor.execute(
        """
        SELECT name
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
            "message":
                "❌ Student not found."
        }


    student_name = student[0]


    # ------------------------------------------------
    # CHECK TODAY'S ATTENDANCE
    # ------------------------------------------------

    cursor.execute(
        """
        SELECT attendance_id, time
        FROM attendance
        WHERE student_id = ?
        AND date = ?
        AND status = 'Present'
        """,
        (
            student_id,
            today
        )
    )

    existing_attendance = cursor.fetchone()


    # ------------------------------------------------
    # ALREADY PRESENT TODAY
    # ------------------------------------------------

    if existing_attendance is not None:

        previous_time = existing_attendance[1]

        connection.close()

        return {
            "success": True,
            "already_marked": True,
            "student_id": student_id,
            "name": student_name,
            "time": previous_time,
            "message":
                f"🟡 {student_name} is already "
                f"marked PRESENT today."
        }


    # ------------------------------------------------
    # INSERT NEW ATTENDANCE
    # ------------------------------------------------

    cursor.execute(
        """
        INSERT INTO attendance
        (
            student_id,
            date,
            time,
            status,
            confidence
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            student_id,
            today,
            current_time,
            "Present",
            confidence
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
        "time": current_time,
        "confidence": confidence,
        "message":
            f"✅ Attendance marked for "
            f"{student_name}!"
    }