import cv2
import os
import numpy as np


# ==================================================
# PATHS
# ==================================================

FACE_DIRECTORY = os.path.join(
    "data",
    "faces"
)

MODEL_PATH = os.path.join(
    "data",
    "face_model.yml"
)


# ==================================================
# FACE DETECTOR
# ==================================================

FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades +
    "haarcascade_frontalface_default.xml"
)


# ==================================================
# PREPARE TRAINING DATA
# ==================================================

def prepare_training_data():

    faces = []
    labels = []

    if not os.path.exists(FACE_DIRECTORY):

        print("❌ Face directory not found.")

        return faces, labels


    files = os.listdir(FACE_DIRECTORY)

    for filename in files:

        # Only image files

        if not filename.lower().endswith(
            (".jpg", ".jpeg", ".png")
        ):
            continue


        # Only student images

        if not filename.startswith("student_"):
            continue


        # --------------------------------------------------
        # GET STUDENT ID FROM FILENAME
        # student_1.jpg → 1
        # student_2.jpg → 2
        # --------------------------------------------------

        try:

            student_id = int(
                os.path.splitext(filename)[0]
                .split("_")[1]
            )

        except (ValueError, IndexError):

            print(
                f"⚠️ Invalid student image: {filename}"
            )

            continue


        image_path = os.path.join(
            FACE_DIRECTORY,
            filename
        )


        # --------------------------------------------------
        # READ IMAGE
        # --------------------------------------------------

        image = cv2.imread(
            image_path,
            cv2.IMREAD_GRAYSCALE
        )


        if image is None:

            print(
                f"⚠️ Could not read: {filename}"
            )

            continue


        # --------------------------------------------------
        # DETECT FACE
        # --------------------------------------------------

        detected_faces = FACE_CASCADE.detectMultiScale(
            image,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(80, 80)
        )


        if len(detected_faces) == 0:

            print(
                f"⚠️ No face found in {filename}"
            )

            continue


        # --------------------------------------------------
        # ADD FACES
        # --------------------------------------------------

        for (x, y, w, h) in detected_faces:

            face = image[
                y:y + h,
                x:x + w
            ]

            faces.append(face)

            labels.append(student_id)


        print(
            f"✅ Loaded {filename} → Student ID {student_id}"
        )


    return faces, labels


# ==================================================
# TRAIN MODEL
# ==================================================

def train_model():

    print()
    print("======================================")
    print("      TRAINING FACE MODEL")
    print("======================================")
    print()


    faces, labels = prepare_training_data()


    if len(faces) == 0:

        print(
            "❌ No valid face images found."
        )

        return False


    # --------------------------------------------------
    # SHOW TRAINING INFORMATION
    # --------------------------------------------------

    unique_ids = sorted(
        set(labels)
    )


    print()
    print(
        f"👥 Students detected: {len(unique_ids)}"
    )

    print(
        f"🆔 Student IDs: {unique_ids}"
    )

    print(
        f"📷 Training faces: {len(faces)}"
    )

    print()


    if len(unique_ids) < 2:

        print(
            "⚠️ WARNING:"
        )

        print(
            "Only one student is currently registered."
        )

        print(
            "Register more students for better recognition."
        )

        print()


    # --------------------------------------------------
    # CREATE LBPH RECOGNIZER
    # --------------------------------------------------

    recognizer = cv2.face.LBPHFaceRecognizer_create(
        radius=1,
        neighbors=8,
        grid_x=8,
        grid_y=8
    )


    # --------------------------------------------------
    # TRAIN
    # --------------------------------------------------

    recognizer.train(
        faces,
        np.array(
            labels,
            dtype=np.int32
        )
    )


    # --------------------------------------------------
    # CREATE DATA DIRECTORY
    # --------------------------------------------------

    os.makedirs(
        "data",
        exist_ok=True
    )


    # --------------------------------------------------
    # SAVE MODEL
    # --------------------------------------------------

    recognizer.save(
        MODEL_PATH
    )


    print(
        "🔥 Face model trained successfully!"
    )

    print(
        f"📁 Model saved: {MODEL_PATH}"
    )

    print()


    return True


# ==================================================
# RECOGNIZE FACE
# ==================================================

def recognize_face(image_path):

    if not os.path.exists(
        MODEL_PATH
    ):

        print(
            "❌ Face model not found."
        )

        return None


    # --------------------------------------------------
    # READ IMAGE
    # --------------------------------------------------

    image = cv2.imread(
        image_path,
        cv2.IMREAD_GRAYSCALE
    )


    if image is None:

        print(
            "❌ Could not read image."
        )

        return None


    # --------------------------------------------------
    # CREATE RECOGNIZER
    # --------------------------------------------------

    recognizer = cv2.face.LBPHFaceRecognizer_create(
        radius=1,
        neighbors=8,
        grid_x=8,
        grid_y=8
    )


    recognizer.read(
        MODEL_PATH
    )


    # --------------------------------------------------
    # DETECT FACE
    # --------------------------------------------------

    detected_faces = FACE_CASCADE.detectMultiScale(
        image,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(80, 80)
    )


    if len(detected_faces) == 0:

        print(
            "❌ No face detected."
        )

        return None


    # --------------------------------------------------
    # RECOGNIZE
    # --------------------------------------------------

    for (x, y, w, h) in detected_faces:

        face = image[
            y:y + h,
            x:x + w
        ]


        student_id, confidence = recognizer.predict(
            face
        )


        print()
        print(
            f"🔍 Predicted Student ID: {student_id}"
        )

        print(
            f"🔍 LBPH Distance: {confidence:.2f}"
        )


        # ==================================================
        # IMPORTANT
        # LOWER = BETTER
        # ==================================================

        # Strict threshold
        if confidence < 55:

            print(
                "✅ Face recognized."
            )

            return student_id


        else:

            print(
                "❌ Face does not match registered student."
            )

            return None


    return None
