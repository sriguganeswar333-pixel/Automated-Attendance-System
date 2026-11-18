import sqlite3
import os
import json

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


# ============================================================
# DATABASE LOCATION
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATABASE = os.path.join(
    BASE_DIR,
    "attendance.db"
)


# ============================================================
# GET DATABASE CONNECTION
# ============================================================

def get_connection():

    connection = sqlite3.connect(
        DATABASE,
        timeout=30,
        check_same_thread=False
    )

    connection.row_factory = sqlite3.Row

    # Wait for other SQLite operations instead of failing immediately
    connection.execute(
        "PRAGMA busy_timeout = 30000"
    )

    # Improve SQLite read/write handling
    connection.execute(
        "PRAGMA journal_mode = WAL"
    )

    # Enable foreign key support
    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


# ============================================================
# INITIALIZE DATABASE
# ============================================================

def initialize_database():

    connection = get_connection()
    cursor = connection.cursor()

    # ========================================================
    # USERS TABLE
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (

            user_id
                INTEGER PRIMARY KEY AUTOINCREMENT,

            name
                TEXT NOT NULL,

            username
                TEXT NOT NULL UNIQUE,

            email
                TEXT NOT NULL UNIQUE,

            password
                TEXT NOT NULL,

            institution_type
                TEXT NOT NULL DEFAULT 'school',

            institution_setup_complete
                INTEGER NOT NULL DEFAULT 1,

            created_at
                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ========================================================
    # MIGRATE OLD USERS TABLE
    # ========================================================

    cursor.execute("PRAGMA table_info(users)")

    user_columns = {
        row["name"]
        for row in cursor.fetchall()
    }

    # Add institution_type if old database does not have it
    if "institution_type" not in user_columns:

        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN institution_type
            TEXT NOT NULL DEFAULT 'school'
        """)

    # Add institution_setup_complete if old database does not have it
    if "institution_setup_complete" not in user_columns:

        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN institution_setup_complete
            INTEGER NOT NULL DEFAULT 1
        """)

    # ========================================================
    # IMPORTANT MIGRATION
    # ========================================================
    # Existing accounts may have been created by the old
    # institution setup flow.
    #
    # If an account already has a valid institution_type,
    # consider institution setup completed.
    #
    # This prevents old accounts from repeatedly opening
    # the Institution Type page.
    # ========================================================

    cursor.execute("""
        UPDATE users
        SET institution_setup_complete = 1
        WHERE institution_type IN ('school', 'college')
    """)

    # ========================================================
    # STUDENTS TABLE
    # Each student belongs to one user
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (

            student_id
                INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id
                INTEGER NOT NULL,

            name
                TEXT NOT NULL,

            class_name
                TEXT NOT NULL,

            section
                TEXT NOT NULL,

            roll_number
                TEXT DEFAULT '',

            department
                TEXT DEFAULT '',

            year
                TEXT DEFAULT '',

            created_at
                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (
                user_id
            )
            REFERENCES users(user_id)
            ON DELETE CASCADE
        )
    """)

    # Migrate students table if columns are missing
    cursor.execute("PRAGMA table_info(students)")
    student_cols = {row["name"] for row in cursor.fetchall()}
    if "roll_number" not in student_cols:
        cursor.execute("ALTER TABLE students ADD COLUMN roll_number TEXT DEFAULT ''")
    if "department" not in student_cols:
        cursor.execute("ALTER TABLE students ADD COLUMN department TEXT DEFAULT ''")
    if "year" not in student_cols:
        cursor.execute("ALTER TABLE students ADD COLUMN year TEXT DEFAULT ''")

    # ========================================================
    # ATTENDANCE TABLE
    # Each attendance record belongs to one user
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (

            attendance_id
                INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id
                INTEGER NOT NULL,

            student_id
                INTEGER NOT NULL,

            date
                TEXT NOT NULL,

            time
                TEXT NOT NULL,

            status
                TEXT NOT NULL,

            confidence
                REAL,

            FOREIGN KEY (
                user_id
            )
            REFERENCES users(user_id)
            ON DELETE CASCADE,

            FOREIGN KEY (
                student_id
            )
            REFERENCES students(student_id)
            ON DELETE CASCADE
        )
    """)

    # ========================================================
    # ATTENDANCE SETTINGS TABLE
    # One separate schedule for each user
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance_settings (

            settings_id
                INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id
                INTEGER NOT NULL UNIQUE,

            attendance_mode
                TEXT NOT NULL DEFAULT 'full_time',

            start_time
                TEXT NOT NULL DEFAULT '00:00',

            end_time
                TEXT NOT NULL DEFAULT '23:59',

            working_days
                TEXT NOT NULL DEFAULT
                '["Monday","Tuesday","Wednesday","Thursday","Friday"]',

            setup_complete
                INTEGER NOT NULL DEFAULT 0,

            updated_at
                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (
                user_id
            )
            REFERENCES users(user_id)
            ON DELETE CASCADE
        )
    """)

    # ========================================================
    # INDEXES
    # ========================================================

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_students_user_id
        ON students(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_attendance_user_id
        ON attendance(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_attendance_student_id
        ON attendance(student_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_attendance_date
        ON attendance(date)
    """)

    connection.commit()
    connection.close()


# ============================================================
# CREATE NEW USER
# ============================================================

def create_user(
    name,
    username,
    email,
    password,
    institution_type=None
):

    connection = get_connection()
    cursor = connection.cursor()

    try:

        # ----------------------------------------------------
        # Validate institution type
        # ----------------------------------------------------

        if institution_type not in ["school", "college"]:
            institution_type = "school"

        # ----------------------------------------------------
        # Hash password
        # ----------------------------------------------------

        hashed_password = generate_password_hash(
            password
        )

        # ----------------------------------------------------
        # Create account
        #
        # Institution Type is selected DURING SIGNUP.
        # Therefore institution_setup_complete = 1.
        # ----------------------------------------------------

        cursor.execute("""
            INSERT INTO users
            (
                name,
                username,
                email,
                password,
                institution_type,
                institution_setup_complete
            )
            VALUES (?, ?, ?, ?, ?, 1)
        """, (
            name,
            username,
            email,
            hashed_password,
            institution_type
        ))

        connection.commit()

        return True

    except sqlite3.IntegrityError:

        connection.rollback()

        return False

    except sqlite3.Error as error:

        connection.rollback()

        print(
            "Error creating user:",
            error
        )

        return False

    finally:

        connection.close()


# ============================================================
# UPDATE INSTITUTION TYPE
# ============================================================
# Kept for compatibility with the existing app.py.
# The new signup flow does not need this function,
# but keeping it prevents import errors.
# ============================================================

def update_institution_type(
    user_id,
    institution_type
):

    connection = get_connection()
    cursor = connection.cursor()

    try:

        if institution_type not in [
            "school",
            "college"
        ]:

            return False

        cursor.execute("""
            UPDATE users
            SET
                institution_type = ?,
                institution_setup_complete = 1
            WHERE user_id = ?
        """, (
            institution_type,
            user_id
        ))

        connection.commit()

        return cursor.rowcount > 0

    except sqlite3.Error as error:

        connection.rollback()

        print(
            "Error saving institution type:",
            error
        )

        return False

    finally:

        connection.close()


# ============================================================
# GET USER FOR LOGIN
# ============================================================

def get_user(username):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM users
        WHERE username = ?
    """, (
        username,
    ))

    user = cursor.fetchone()

    connection.close()

    return user


# ============================================================
# GET USER BY ID
# ============================================================

def get_user_by_id(user_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM users
        WHERE user_id = ?
    """, (
        user_id,
    ))

    user = cursor.fetchone()

    connection.close()

    return user


# ============================================================
# GET ATTENDANCE SETTINGS FOR ONE USER
# ============================================================

def get_attendance_settings(user_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            settings_id,
            user_id,
            attendance_mode,
            start_time,
            end_time,
            working_days,
            setup_complete,
            updated_at
        FROM attendance_settings
        WHERE user_id = ?
    """, (
        user_id,
    ))

    settings = cursor.fetchone()

    connection.close()

    return settings


# ============================================================
# SAVE OR UPDATE ATTENDANCE SETTINGS
# ============================================================

def save_attendance_settings(
    user_id,
    attendance_mode,
    start_time,
    end_time,
    working_days
):

    connection = get_connection()
    cursor = connection.cursor()

    try:

        # Convert Python list into JSON
        working_days_json = json.dumps(
            working_days
        )

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

                attendance_mode =
                    excluded.attendance_mode,

                start_time =
                    excluded.start_time,

                end_time =
                    excluded.end_time,

                working_days =
                    excluded.working_days,

                setup_complete = 1,

                updated_at =
                    CURRENT_TIMESTAMP
        """, (
            user_id,
            attendance_mode,
            start_time,
            end_time,
            working_days_json
        ))

        connection.commit()

        return True

    except sqlite3.Error as error:

        print(
            "Error saving attendance settings:",
            error
        )

        connection.rollback()

        return False

    finally:

        connection.close()


# ============================================================
# CHECK WHETHER USER COMPLETED ATTENDANCE SETUP
# ============================================================

def attendance_settings_completed(user_id):

    settings = get_attendance_settings(
        user_id
    )

    if settings is None:
        return False

    return bool(
        settings["setup_complete"]
    )


# ============================================================
# GET ALL STUDENTS OF ONE USER
# ============================================================

def get_students_by_user(user_id):

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
    """, (
        user_id,
    ))

    students = cursor.fetchall()

    connection.close()

    return students


# ============================================================
# GET ONE STUDENT OF ONE USER
# ============================================================

def get_student_by_id(
    student_id,
    user_id
):

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
        WHERE student_id = ?
        AND user_id = ?
    """, (
        student_id,
        user_id
    ))

    student = cursor.fetchone()

    connection.close()

    return student


# ============================================================
# CREATE STUDENT FOR ONE USER
# ============================================================

def create_student(
    user_id,
    name,
    class_name,
    section,
    roll_number="",
    department="",
    year=""
):

    connection = get_connection()
    cursor = connection.cursor()

    try:

        cursor.execute("""
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
        """, (
            user_id,
            name,
            class_name,
            section,
            roll_number,
            department,
            year
        ))

        connection.commit()

        return cursor.lastrowid

    except sqlite3.Error as error:

        print(
            "Error creating student:",
            error
        )

        connection.rollback()

        return None

    finally:

        connection.close()


# ============================================================
# DELETE STUDENT OF ONE USER
# ============================================================

def delete_student(
    student_id,
    user_id
):

    connection = get_connection()
    cursor = connection.cursor()

    try:

        cursor.execute("""
            DELETE FROM students
            WHERE student_id = ?
            AND user_id = ?
        """, (
            student_id,
            user_id
        ))

        connection.commit()

        return cursor.rowcount > 0

    except sqlite3.Error as error:

        print(
            "Error deleting student:",
            error
        )

        connection.rollback()

        return False

    finally:

        connection.close()


# ============================================================
# SAVE ATTENDANCE FOR ONE USER
# ============================================================

def create_attendance(
    user_id,
    student_id,
    date,
    time,
    status,
    confidence=None
):

    connection = get_connection()
    cursor = connection.cursor()

    try:

        # ----------------------------------------------------
        # SECURITY CHECK
        # Confirm that the student belongs to this user
        # ----------------------------------------------------

        cursor.execute("""
            SELECT student_id
            FROM students
            WHERE student_id = ?
            AND user_id = ?
        """, (
            student_id,
            user_id
        ))

        student = cursor.fetchone()

        if student is None:

            print(
                "Security warning: student does not belong to user"
            )

            return False

        # ----------------------------------------------------
        # Insert attendance
        # ----------------------------------------------------

        cursor.execute("""
            INSERT INTO attendance
            (
                user_id,
                student_id,
                date,
                time,
                status,
                confidence
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            student_id,
            date,
            time,
            status,
            confidence
        ))

        connection.commit()

        return True

    except sqlite3.Error as error:

        print(
            "Error creating attendance:",
            error
        )

        connection.rollback()

        return False

    finally:

        connection.close()


# ============================================================
# GET ATTENDANCE OF ONE USER
# ============================================================

def get_attendance_by_user(user_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            attendance.attendance_id,
            attendance.user_id,
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
            ON attendance.student_id =
               students.student_id
        WHERE attendance.user_id = ?
        AND students.user_id = ?
        ORDER BY attendance.date DESC,
                 attendance.time DESC
    """, (
        user_id,
        user_id
    ))

    records = cursor.fetchall()

    connection.close()

    return records


# ============================================================
# GET ATTENDANCE FOR ONE USER ON ONE DATE
# ============================================================

def get_attendance_by_date(
    user_id,
    date
):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            attendance.attendance_id,
            attendance.user_id,
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
            ON attendance.student_id =
               students.student_id
        WHERE attendance.user_id = ?
        AND students.user_id = ?
        AND attendance.date = ?
        ORDER BY attendance.time DESC
    """, (
        user_id,
        user_id,
        date
    ))

    records = cursor.fetchall()

    connection.close()

    return records


# ============================================================
# DELETE SETTINGS FOR TESTING
# ============================================================

def delete_attendance_settings(user_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM attendance_settings
        WHERE user_id = ?
    """, (
        user_id,
    ))

    connection.commit()
    connection.close()


# ============================================================
# TEST DATABASE
# ============================================================

if __name__ == "__main__":

    initialize_database()

    print()
    print("======================================")
    print("       DATABASE INITIALIZED")
    print("======================================")
    print()

    print(
        "Database:",
        DATABASE
    )

    print()

    print(
        "SQLite database is ready."
    )