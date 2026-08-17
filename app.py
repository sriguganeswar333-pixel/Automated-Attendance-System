from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    jsonify
)

import os
import sys
import subprocess

from datetime import datetime, time
from zoneinfo import ZoneInfo

from database import (
    initialize_database,
    get_connection
)

from ai.face_detection import detect_face

# ============================================================
# AUTOMATIC FACE TRAINING
# ============================================================

from ai.face_recognition import train_model


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)


# ============================================================
# PROJECT DIRECTORY
# ============================================================

PROJECT_DIRECTORY = os.path.dirname(
    os.path.abspath(__file__)
)


# ============================================================
# DATABASE
# ============================================================

initialize_database()


# ============================================================
# INDIA TIMEZONE
# ============================================================

try:

    INDIA_TIMEZONE = ZoneInfo(
        "Asia/Kolkata"
    )

except Exception:

    from datetime import timezone, timedelta

    INDIA_TIMEZONE = timezone(
        timedelta(hours=5, minutes=30)
    )


def get_india_datetime():

    return datetime.now(
        INDIA_TIMEZONE
    )


# ============================================================
# ATTENDANCE TIME
# ============================================================

ATTENDANCE_START_TIME = time(
    8,
    30
)

ATTENDANCE_END_TIME = time(
    16,
    0
)


# ============================================================
# ATTENDANCE STATUS
# ============================================================

def get_attendance_status():

    current_time = (
        get_india_datetime().time()
    )


    # --------------------------------------------------------
    # BEFORE 8:30 AM
    # --------------------------------------------------------

    if current_time < ATTENDANCE_START_TIME:

        return {

            "status":
                "not_started",

            "label":
                "Attendance Not Started",

            "message":
                "Attendance starts at 8:30 AM.",

            "can_take":
                False

        }


    # --------------------------------------------------------
    # 8:30 AM TO 4:00 PM
    # --------------------------------------------------------

    if (
        ATTENDANCE_START_TIME
        <= current_time
        <= ATTENDANCE_END_TIME
    ):

        return {

            "status":
                "open",

            "label":
                "Attendance Open",

            "message":
                "Attendance is currently active.",

            "can_take":
                True

        }


    # --------------------------------------------------------
    # AFTER 4:00 PM
    # --------------------------------------------------------

    return {

        "status":
            "closed",

        "label":
            "Attendance Closed",

        "message":
            "Today's attendance period has ended.",

        "can_take":
            False

    }


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def dashboard():

    connection = get_connection()

    cursor = connection.cursor()


    # --------------------------------------------------------
    # TOTAL STUDENTS
    # --------------------------------------------------------

    cursor.execute("""
        SELECT COUNT(*)
        FROM students
    """)

    total_students = (
        cursor.fetchone()[0]
    )


    # --------------------------------------------------------
    # TODAY
    # --------------------------------------------------------

    today = (
        get_india_datetime()
        .strftime("%Y-%m-%d")
    )


    # --------------------------------------------------------
    # PRESENT TODAY
    # --------------------------------------------------------

    cursor.execute("""
        SELECT COUNT(DISTINCT student_id)

        FROM attendance

        WHERE date = ?

        AND status = 'Present'
    """, (
        today,
    ))

    present_today = (
        cursor.fetchone()[0]
    )


    # --------------------------------------------------------
    # ABSENT TODAY
    # --------------------------------------------------------

    absent_today = (
        total_students
        - present_today
    )


    if absent_today < 0:

        absent_today = 0


    # --------------------------------------------------------
    # ATTENDANCE RATE
    # --------------------------------------------------------

    if total_students > 0:

        attendance_rate = (
            present_today
            / total_students
        ) * 100

    else:

        attendance_rate = 0


    connection.close()


    # --------------------------------------------------------
    # ATTENDANCE STATUS
    # --------------------------------------------------------

    attendance_status = (
        get_attendance_status()
    )


    # --------------------------------------------------------
    # CURRENT TIME
    # --------------------------------------------------------

    current_time = (
        get_india_datetime()
        .strftime("%I:%M:%S %p")
    )


    return render_template(

        "dashboard.html",

        total_students=
            total_students,

        present_today=
            present_today,

        absent_today=
            absent_today,

        attendance_rate=
            round(
                attendance_rate,
                1
            ),

        attendance_status=
            attendance_status,

        attendance_start=
            "08:30 AM",

        attendance_end=
            "04:00 PM",

        current_time=
            current_time

    )


# ============================================================
# TAKE ATTENDANCE
# ============================================================

@app.route("/take_attendance")
def take_attendance():

    # --------------------------------------------------------
    # CHECK ATTENDANCE TIME
    # --------------------------------------------------------

    status = (
        get_attendance_status()
    )


    current_time = (
        get_india_datetime()
        .strftime("%I:%M:%S %p")
    )


    # --------------------------------------------------------
    # ATTENDANCE CLOSED
    # --------------------------------------------------------

    if not status["can_take"]:

        return render_template(

            "attendance_started.html",

            status=
                status["status"],

            title=
                status["label"],

            message=
                status["message"],

            current_time=
                current_time,

            start_time=
                "08:30 AM",

            end_time=
                "04:00 PM"

        )


    # ========================================================
    # LIVE RECOGNITION FILE
    # ========================================================

    script_path = os.path.join(

        PROJECT_DIRECTORY,

        "live_recognition.py"

    )


    # --------------------------------------------------------
    # FILE CHECK
    # --------------------------------------------------------

    if not os.path.isfile(
        script_path
    ):

        return f"""

        <html>

        <head>

            <title>
                Attendance Error
            </title>

        </head>

        <body>

            <h2>
                ❌ live_recognition.py not found
            </h2>

            <p>
                Expected file:
            </p>

            <p>
                {script_path}
            </p>

            <br>

            <a href="/">
                ← Back to Dashboard
            </a>

        </body>

        </html>

        """, 404


    # ========================================================
    # AUTOMATIC FACE MODEL TRAINING
    # ========================================================

    print()

    print(
        "======================================"
    )

    print(
        "    AUTOMATIC FACE MODEL TRAINING"
    )

    print(
        "======================================"
    )

    print()


    print(
        "🔄 Updating face recognition model..."
    )


    try:

        training_success = train_model()


        # ----------------------------------------------------
        # TRAINING FAILED
        # ----------------------------------------------------

        if not training_success:

            print()

            print(
                "❌ Face model training failed."
            )

            print()


            return render_template(

                "attendance_started.html",

                status=
                    "error",

                title=
                    "Face Training Failed",

                message=
                    (
                        "❌ Face recognition model "
                        "could not be trained. "
                        "Please register the student "
                        "face again."
                    ),

                current_time=
                    current_time,

                start_time=
                    "08:30 AM",

                end_time=
                    "04:00 PM"

            )


        # ----------------------------------------------------
        # TRAINING SUCCESS
        # ----------------------------------------------------

        print(
            "✅ Face model updated successfully."
        )

        print(
            "📁 Model: data/face_model.yml"
        )

        print()


    except Exception as error:

        print()

        print(
            "❌ FACE TRAINING ERROR"
        )

        print(
            error
        )

        print()


        return render_template(

            "attendance_started.html",

            status=
                "error",

            title=
                "Face Training Error",

            message=
                (
                    "❌ Unable to update the "
                    "face recognition model."
                ),

            current_time=
                current_time,

            start_time=
                "08:30 AM",

            end_time=
                "04:00 PM"

        )


    # ========================================================
    # START CAMERA
    # ========================================================

    try:

        print()

        print(
            "======================================"
        )

        print(
            "       STARTING ATTENDANCE"
        )

        print(
            "======================================"
        )

        print()


        print(
            "🇮🇳 India Time:",
            current_time
        )


        print(
            "📷 Script:",
            script_path
        )


        print(
            "🐍 Python:",
            sys.executable
        )

        print()


        # ----------------------------------------------------
        # WINDOWS
        # ----------------------------------------------------

        if os.name == "nt":

            subprocess.Popen(

                [
                    sys.executable,
                    script_path
                ],

                cwd=
                    PROJECT_DIRECTORY,

                creationflags=
                    subprocess.CREATE_NEW_CONSOLE

            )


        # ----------------------------------------------------
        # LINUX / MAC
        # ----------------------------------------------------

        else:

            subprocess.Popen(

                [
                    sys.executable,
                    script_path
                ],

                cwd=
                    PROJECT_DIRECTORY

            )


        # ----------------------------------------------------
        # WEBSITE SUCCESS
        # ----------------------------------------------------

        return render_template(

            "attendance_started.html",

            status=
                "started",

            title=
                "Attendance Started",

            message=
                (
                    "📷 Attendance camera has "
                    "been started successfully."
                ),

            current_time=
                current_time,

            start_time=
                "08:30 AM",

            end_time=
                "04:00 PM"

        )


    except Exception as error:

        print()

        print(
            "❌ ATTENDANCE START ERROR"
        )

        print(
            error
        )

        print()


        return f"""

        <html>

        <head>

            <title>
                Attendance Error
            </title>

        </head>

        <body>

            <h2>
                ❌ Could not start attendance
            </h2>

            <p>
                {str(error)}
            </p>

            <p>
                Current India time:
                {current_time}
            </p>

            <br>

            <a href="/">
                ← Back to Dashboard
            </a>

        </body>

        </html>

        """, 500


# ============================================================
# STUDENTS
# ============================================================

@app.route("/students")
def students():

    connection = get_connection()

    cursor = connection.cursor()


    cursor.execute("""
        SELECT *

        FROM students

        ORDER BY student_id DESC
    """)


    students_list = (
        cursor.fetchall()
    )


    connection.close()


    return render_template(

        "students.html",

        students=
            students_list

    )


# ============================================================
# ADD STUDENT
# ============================================================

@app.route(
    "/add_student",
    methods=["GET", "POST"]
)
def add_student():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()


        class_name = request.form.get(
            "class_name",
            ""
        ).strip()


        section = request.form.get(
            "section",
            ""
        ).strip()


        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if (
            not name
            or not class_name
            or not section
        ):

            return (
                "All fields are required.",
                400
            )


        connection = get_connection()

        cursor = connection.cursor()


        cursor.execute("""
            INSERT INTO students
            (
                name,
                class_name,
                section
            )

            VALUES (?, ?, ?)
        """, (

            name,
            class_name,
            section

        ))


        connection.commit()

        connection.close()


        return redirect(
            url_for("students")
        )


    return render_template(
        "add_student.html"
    )


# ============================================================
# DELETE STUDENT
# ============================================================

@app.route(
    "/delete_student/<int:student_id>"
)
def delete_student(student_id):

    connection = get_connection()

    cursor = connection.cursor()


    # --------------------------------------------------------
    # DELETE ATTENDANCE
    # --------------------------------------------------------

    cursor.execute("""
        DELETE FROM attendance

        WHERE student_id = ?
    """, (
        student_id,
    ))


    # --------------------------------------------------------
    # DELETE STUDENT
    # --------------------------------------------------------

    cursor.execute("""
        DELETE FROM students

        WHERE student_id = ?
    """, (
        student_id,
    ))


    connection.commit()

    connection.close()


    # --------------------------------------------------------
    # DELETE FACE IMAGE
    # --------------------------------------------------------

    face_path = os.path.join(

        PROJECT_DIRECTORY,

        "data",

        "faces",

        f"student_{student_id}.jpg"

    )


    if os.path.exists(
        face_path
    ):

        try:

            os.remove(
                face_path
            )

        except OSError:

            pass


    return redirect(
        url_for("students")
    )


# ============================================================
# FACE REGISTRATION
# ============================================================

@app.route(
    "/face_registration/<int:student_id>"
)
def face_registration(student_id):

    connection = get_connection()

    cursor = connection.cursor()


    cursor.execute("""
        SELECT *

        FROM students

        WHERE student_id = ?
    """, (
        student_id,
    ))


    student = (
        cursor.fetchone()
    )


    connection.close()


    if student is None:

        return (
            "Student not found.",
            404
        )


    return render_template(

        "camera.html",

        student=
            student

    )


# ============================================================
# SAVE FACE
# ============================================================

@app.route(
    "/save_face/<int:student_id>",
    methods=["POST"]
)
def save_face(student_id):

    connection = get_connection()

    cursor = connection.cursor()


    # --------------------------------------------------------
    # CHECK STUDENT
    # --------------------------------------------------------

    cursor.execute("""
        SELECT *

        FROM students

        WHERE student_id = ?
    """, (
        student_id,
    ))


    student = (
        cursor.fetchone()
    )


    connection.close()


    if student is None:

        return jsonify({

            "message":
                "❌ Student not found."

        }), 404


    # --------------------------------------------------------
    # CHECK IMAGE
    # --------------------------------------------------------

    if "image" not in request.files:

        return jsonify({

            "message":
                "❌ No image received."

        }), 400


    image = request.files[
        "image"
    ]


    if image.filename == "":

        return jsonify({

            "message":
                "❌ Invalid image."

        }), 400


    # --------------------------------------------------------
    # FACE DIRECTORY
    # --------------------------------------------------------

    face_directory = os.path.join(

        PROJECT_DIRECTORY,

        "data",

        "faces"

    )


    os.makedirs(

        face_directory,

        exist_ok=True

    )


    # --------------------------------------------------------
    # IMAGE PATH
    # --------------------------------------------------------

    image_path = os.path.join(

        face_directory,

        f"student_{student_id}.jpg"

    )


    # --------------------------------------------------------
    # SAVE IMAGE
    # --------------------------------------------------------

    image.save(
        image_path
    )


    # --------------------------------------------------------
    # DETECT FACE
    # --------------------------------------------------------

    face_found = detect_face(
        image_path
    )


    # --------------------------------------------------------
    # NO FACE
    # --------------------------------------------------------

    if not face_found:

        if os.path.exists(
            image_path
        ):

            os.remove(
                image_path
            )


        return jsonify({

            "message":
                (
                    "❌ No face detected. "
                    "Please position your face "
                    "clearly and try again."
                )

        })


    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    return jsonify({

        "message":
            (
                "✅ Face detected and registered "
                "successfully!"
            )

    })


# ============================================================
# ATTENDANCE REPORTS
# ============================================================

@app.route("/attendance")
def attendance_reports():

    connection = get_connection()

    cursor = connection.cursor()


    # ========================================================
    # FILTERS
    # ========================================================

    selected_date = request.args.get(
        "date",
        ""
    ).strip()


    selected_student = request.args.get(
        "student",
        ""
    ).strip()


    selected_class = request.args.get(
        "class_name",
        ""
    ).strip()


    selected_section = request.args.get(
        "section",
        ""
    ).strip()


    # ========================================================
    # REPORT DATE
    # ========================================================

    today = (
        get_india_datetime()
        .strftime("%Y-%m-%d")
    )


    report_date = (

        selected_date

        if selected_date

        else today

    )


    # ========================================================
    # STUDENT LIST
    # ========================================================

    cursor.execute("""
        SELECT
            student_id,
            name,
            class_name,
            section

        FROM students

        ORDER BY name ASC
    """)


    students_list = (
        cursor.fetchall()
    )


    # ========================================================
    # ATTENDANCE RECORDS
    # ========================================================

    query = """

        SELECT

            attendance.attendance_id,

            attendance.student_id,

            students.name,

            students.class_name,

            students.section,

            attendance.date,

            attendance.time,

            attendance.status,

            attendance.confidence

        FROM attendance

        INNER JOIN students

        ON attendance.student_id =
           students.student_id

        WHERE 1 = 1

    """


    parameters = []


    # --------------------------------------------------------
    # DATE FILTER
    # --------------------------------------------------------

    if selected_date:

        query += """

            AND attendance.date = ?

        """

        parameters.append(
            selected_date
        )


    # --------------------------------------------------------
    # STUDENT FILTER
    # --------------------------------------------------------

    if selected_student:

        query += """

            AND attendance.student_id = ?

        """

        parameters.append(
            selected_student
        )


    # --------------------------------------------------------
    # CLASS FILTER
    # --------------------------------------------------------

    if selected_class:

        query += """

            AND students.class_name = ?

        """

        parameters.append(
            selected_class
        )


    # --------------------------------------------------------
    # SECTION FILTER
    # --------------------------------------------------------

    if selected_section:

        query += """

            AND students.section = ?

        """

        parameters.append(
            selected_section
        )


    # --------------------------------------------------------
    # ORDER
    # --------------------------------------------------------

    query += """

        ORDER BY
            attendance.date DESC,
            attendance.time DESC

    """


    cursor.execute(
        query,
        parameters
    )


    attendance_records = (
        cursor.fetchall()
    )


    # ========================================================
    # TOTAL STUDENTS
    # ========================================================

    cursor.execute("""
        SELECT COUNT(*)

        FROM students
    """)


    total_students = (
        cursor.fetchone()[0]
    )


    # ========================================================
    # PRESENT COUNT
    # ========================================================

    present_count_query = """

        SELECT COUNT(
            DISTINCT attendance.student_id
        )

        FROM attendance

        INNER JOIN students

        ON attendance.student_id =
           students.student_id

        WHERE attendance.date = ?

        AND attendance.status = 'Present'

    """


    present_count_parameters = [
        report_date
    ]


    if selected_student:

        present_count_query += """

            AND attendance.student_id = ?

        """

        present_count_parameters.append(
            selected_student
        )


    if selected_class:

        present_count_query += """

            AND students.class_name = ?

        """

        present_count_parameters.append(
            selected_class
        )


    if selected_section:

        present_count_query += """

            AND students.section = ?

        """

        present_count_parameters.append(
            selected_section
        )


    cursor.execute(

        present_count_query,

        present_count_parameters

    )


    today_present = (
        cursor.fetchone()[0]
    )


    # ========================================================
    # PRESENT STUDENTS LIST
    # ========================================================

    present_query = """

        SELECT

            students.student_id,

            students.name,

            students.class_name,

            students.section,

            MIN(attendance.time) AS time

        FROM attendance

        INNER JOIN students

        ON attendance.student_id =
           students.student_id

        WHERE attendance.date = ?

        AND attendance.status = 'Present'

    """


    present_parameters = [
        report_date
    ]


    if selected_student:

        present_query += """

            AND students.student_id = ?

        """

        present_parameters.append(
            selected_student
        )


    if selected_class:

        present_query += """

            AND students.class_name = ?

        """

        present_parameters.append(
            selected_class
        )


    if selected_section:

        present_query += """

            AND students.section = ?

        """

        present_parameters.append(
            selected_section
        )


    present_query += """

        GROUP BY

            students.student_id,

            students.name,

            students.class_name,

            students.section

        ORDER BY
            students.name ASC

    """


    cursor.execute(

        present_query,

        present_parameters

    )


    present_students = (
        cursor.fetchall()
    )


    # ========================================================
    # ABSENT STUDENTS
    # ========================================================

    absent_query = """

        SELECT

            students.student_id,

            students.name,

            students.class_name,

            students.section

        FROM students

        WHERE students.student_id NOT IN (

            SELECT DISTINCT
                student_id

            FROM attendance

            WHERE date = ?

            AND status = 'Present'

        )

    """


    absent_parameters = [
        report_date
    ]


    if selected_student:

        absent_query += """

            AND students.student_id = ?

        """

        absent_parameters.append(
            selected_student
        )


    if selected_class:

        absent_query += """

            AND students.class_name = ?

        """

        absent_parameters.append(
            selected_class
        )


    if selected_section:

        absent_query += """

            AND students.section = ?

        """

        absent_parameters.append(
            selected_section
        )


    absent_query += """

        ORDER BY students.name ASC

    """


    cursor.execute(

        absent_query,

        absent_parameters

    )


    absent_students = (
        cursor.fetchall()
    )


    # ========================================================
    # ABSENT COUNT
    # ========================================================

    today_absent = len(
        absent_students
    )


    # ========================================================
    # ATTENDANCE RATE
    # ========================================================

    filtered_total_query = """

        SELECT COUNT(*)

        FROM students

        WHERE 1 = 1

    """


    filtered_total_parameters = []


    if selected_student:

        filtered_total_query += """

            AND student_id = ?

        """

        filtered_total_parameters.append(
            selected_student
        )


    if selected_class:

        filtered_total_query += """

            AND class_name = ?

        """

        filtered_total_parameters.append(
            selected_class
        )


    if selected_section:

        filtered_total_query += """

            AND section = ?

        """

        filtered_total_parameters.append(
            selected_section
        )


    cursor.execute(

        filtered_total_query,

        filtered_total_parameters

    )


    filtered_total_students = (
        cursor.fetchone()[0]
    )


    if filtered_total_students > 0:

        attendance_rate = (

            today_present
            /
            filtered_total_students

        ) * 100

    else:

        attendance_rate = 0


    # ========================================================
    # TOTAL PRESENT RECORDS
    # ========================================================

    cursor.execute("""
        SELECT COUNT(*)

        FROM attendance

        WHERE status = 'Present'
    """)


    total_present = (
        cursor.fetchone()[0]
    )


    connection.close()


    # ========================================================
    # SEND DATA TO HTML
    # ========================================================

    return render_template(

        "attendance.html",

        attendance_records=
            attendance_records,

        students_list=
            students_list,

        present_students=
            present_students,

        absent_students=
            absent_students,

        total_students=
            total_students,

        total_present=
            total_present,

        today_present=
            today_present,

        today_absent=
            today_absent,

        attendance_rate=
            round(
                attendance_rate,
                1
            ),

        selected_date=
            selected_date,

        selected_student=
            selected_student,

        selected_class=
            selected_class,

        selected_section=
            selected_section,

        report_date=
            report_date

    )


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    print()

    print(
        "======================================"
    )

    print(
        "   AUTOMATED ATTENDANCE SYSTEM"
    )

    print(
        "======================================"
    )

    print()


    print(
        "🇮🇳 India Time:",

        get_india_datetime().strftime(
            "%Y-%m-%d %I:%M:%S %p"
        )

    )


    print()


    print(
        "🕐 Attendance:",
        "08:30 AM - 04:00 PM"
    )


    print()


    status = (
        get_attendance_status()
    )


    print(
        "📊 Attendance Status:",
        status["label"]
    )


    print(
        "📌 Can Take Attendance:",
        status["can_take"]
    )


    print()


    print(
        "🌐 Flask starting..."
    )


    print()


    app.run(

        host="127.0.0.1",

        port=5000,

        debug=True,

        use_reloader=False

    )