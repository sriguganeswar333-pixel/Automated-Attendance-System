import cv2
import os

from attendance import mark_attendance
from database import get_connection


# ==================================================
# SETTINGS
# ==================================================

MODEL_PATH = os.path.join(
    "data",
    "face_model.yml"
)

RECOGNITION_THRESHOLD = 55


# ==================================================
# FACE DETECTOR
# ==================================================

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades +
    "haarcascade_frontalface_default.xml"
)


# ==================================================
# CHECK FACE DETECTOR
# ==================================================

if face_cascade.empty():

    print()
    print("❌ Face detector could not be loaded.")
    print()

    exit()


# ==================================================
# CHECK MODEL
# ==================================================

if not os.path.exists(MODEL_PATH):

    print()
    print("======================================")
    print("       AUTOMATIC ATTENDANCE")
    print("======================================")
    print()

    print("❌ Face model not found.")

    print()
    print("👉 First run:")
    print("   python train_faces.py")
    print()

    exit()


# ==================================================
# LOAD RECOGNIZER
# ==================================================

recognizer = cv2.face.LBPHFaceRecognizer_create(
    radius=1,
    neighbors=8,
    grid_x=8,
    grid_y=8
)

recognizer.read(
    MODEL_PATH
)


# ==================================================
# LOAD REGISTERED STUDENT IDS
# ==================================================

connection = get_connection()
cursor = connection.cursor()

cursor.execute("""
    SELECT student_id
    FROM students
""")

registered_students = {
    row[0]
    for row in cursor.fetchall()
}

connection.close()


if len(registered_students) == 0:

    print()
    print("❌ No students registered.")
    print()
    print("👉 Add students first.")
    print()

    exit()


print()
print("======================================")
print("       AUTOMATIC ATTENDANCE")
print("======================================")
print()

print(
    f"👥 Registered students: "
    f"{len(registered_students)}"
)

print(
    f"🆔 Student IDs: "
    f"{sorted(registered_students)}"
)

print()

# ==================================================
# START CAMERA
# ==================================================

camera = cv2.VideoCapture(
    0,
    cv2.CAP_DSHOW
)


camera.set(
    cv2.CAP_PROP_FRAME_WIDTH,
    640
)

camera.set(
    cv2.CAP_PROP_FRAME_HEIGHT,
    480
)


if not camera.isOpened():

    print()
    print("❌ Could not open webcam.")
    print()

    exit()


print("📷 Camera started.")
print("👉 Look at the camera.")
print("👉 Press Q to cancel.")
print()


# ==================================================
# ATTENDANCE STATUS
# ==================================================

attendance_done = False


# ==================================================
# LIVE RECOGNITION LOOP
# ==================================================

while True:

    ret, frame = camera.read()


    # ------------------------------------------------
    # CAMERA ERROR
    # ------------------------------------------------

    if not ret:

        print(
            "❌ Could not read camera frame."
        )

        break


    # ------------------------------------------------
    # GRAYSCALE
    # ------------------------------------------------

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )


    # ------------------------------------------------
    # FACE DETECTION
    # ------------------------------------------------

    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(100, 100)
    )


    # ==================================================
    # PROCESS FACES
    # ==================================================

    for (x, y, w, h) in faces:

        face = gray[
            y:y + h,
            x:x + w
        ]


        # ------------------------------------------------
        # RECOGNIZE
        # ------------------------------------------------

        student_id, confidence = recognizer.predict(
            face
        )


        print(
            f"🔍 Predicted ID: {student_id} | "
            f"Distance: {confidence:.2f}"
        )


        # ==================================================
        # VERIFY BOTH:
        #
        # 1. ID exists in database
        # 2. Face distance is good
        # ==================================================

        if (
            student_id in registered_students
            and
            confidence < RECOGNITION_THRESHOLD
        ):


            # ==================================================
            # RECOGNIZED
            # ==================================================

            print()
            print("======================================")
            print("          FACE RECOGNIZED")
            print("======================================")
            print()

            print(
                f"🎓 Student ID: {student_id}"
            )

            print(
                f"📊 Match distance: "
                f"{confidence:.2f}"
            )


            # ------------------------------------------------
            # MARK ATTENDANCE
            # ------------------------------------------------

            result = mark_attendance(
                student_id,
                confidence
            )


            print()
            print(
                result["message"]
            )


            # ==================================================
            # GREEN FACE BOX
            # ==================================================

            cv2.rectangle(
                frame,
                (x, y),
                (x + w, y + h),
                (0, 255, 0),
                3
            )


            # ==================================================
            # STUDENT ID
            # ==================================================

            cv2.putText(
                frame,
                f"Student ID: {student_id}",
                (x, y - 55),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (0, 255, 0),
                2
            )


            # ==================================================
            # RECOGNIZED
            # ==================================================

            cv2.putText(
                frame,
                "RECOGNIZED",
                (x, y - 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )


            # ==================================================
            # ATTENDANCE STATUS
            # ==================================================

            if result.get(
                "already_marked",
                False
            ):

                display_message = (
                    "ALREADY PRESENT"
                )

            else:

                display_message = (
                    "ATTENDANCE MARKED"
                )


            cv2.putText(
                frame,
                display_message,
                (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 255, 0),
                2
            )


            # ==================================================
            # SHOW RESULT
            # ==================================================

            cv2.imshow(
                "Automatic Attendance",
                frame
            )

            cv2.waitKey(1500)


            # ==================================================
            # STOP AFTER ONE SUCCESSFUL RECOGNITION
            # ==================================================

            attendance_done = True

            break


        else:


            # ==================================================
            # UNKNOWN FACE
            # ==================================================

            cv2.rectangle(
                frame,
                (x, y),
                (x + w, y + h),
                (0, 0, 255),
                3
            )


            cv2.putText(
                frame,
                "FACE NOT RECOGNIZED",
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2
            )


    # ==================================================
    # DISPLAY CAMERA
    # ==================================================

    cv2.imshow(
        "Automatic Attendance",
        frame
    )


    # ==================================================
    # STOP AFTER SUCCESS
    # ==================================================

    if attendance_done:

        break


    # ==================================================
    # MANUAL EXIT
    # ==================================================

    key = cv2.waitKey(1) & 0xFF


    if key == ord("q") or key == ord("Q"):

        print()
        print("🛑 Attendance cancelled by user.")
        print()

        break


# ==================================================
# RELEASE CAMERA
# ==================================================

camera.release()

cv2.destroyAllWindows()

cv2.waitKey(1)


# ==================================================
# FINAL MESSAGE
# ==================================================

print()
print("======================================")
print("       ATTENDANCE COMPLETED")
print("======================================")
print()

print("📷 Camera stopped.")
print("🔥 Attendance process finished.")
print()