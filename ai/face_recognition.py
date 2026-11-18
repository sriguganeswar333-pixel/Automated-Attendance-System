import cv2
import os
import sys
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ==================================================
# PATHS (Robust Absolute Resolution)
# ==================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

FACE_DIRECTORY = os.path.join(
    BASE_DIR,
    "data",
    "faces"
)

MODEL_PATH = os.path.join(
    BASE_DIR,
    "data",
    "face_model.yml"
)


# ==================================================
# FACE DETECTOR & CLAHE EQUALIZER
# ==================================================

FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades +
    "haarcascade_frontalface_default.xml"
)

CLAHE = cv2.createCLAHE(
    clipLimit=2.0,
    tileGridSize=(8, 8)
)


def preprocess_face(face_gray):
    """
    Standardize face dimensions to 200x200 and apply
    CLAHE lighting equalization for optimal LBPH texture extraction.
    """
    resized = cv2.resize(face_gray, (200, 200))
    equalized = CLAHE.apply(resized)
    return equalized


# ==================================================
# PREPARE TRAINING DATA
# ==================================================

def prepare_training_data():
    faces = []
    labels = []

    if not os.path.exists(FACE_DIRECTORY):
        print("❌ Face directory not found:", FACE_DIRECTORY)
        return faces, labels

    files = os.listdir(FACE_DIRECTORY)

    for filename in sorted(files):
        # Only image files
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue

        # Only student images (student_1.jpg, student_1_1.jpg, etc.)
        if not filename.startswith("student_"):
            continue

        try:
            parts = os.path.splitext(filename)[0].split("_")
            student_id = int(parts[1])
        except (ValueError, IndexError):
            print(f"⚠️ Invalid student image format: {filename}")
            continue

        image_path = os.path.join(FACE_DIRECTORY, filename)
        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

        if image is None:
            print(f"⚠️ Could not read: {filename}")
            continue

        detected_faces = FACE_CASCADE.detectMultiScale(
            image,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(60, 60)
        )

        if len(detected_faces) == 0:
            # Fallback: if the image was already a cropped/preprocessed face
            h, w = image.shape
            if h >= 50 and w >= 50:
                enhanced = preprocess_face(image)
                faces.append(enhanced)
                labels.append(student_id)
                print(f"✅ Loaded cropped face: {filename} → Student ID {student_id}")
            else:
                print(f"⚠️ No face found in {filename}")
            continue

        # Use the largest detected face in frame
        x, y, w, h = max(detected_faces, key=lambda b: b[2] * b[3])
        face_roi = image[y:y + h, x:x + w]
        enhanced = preprocess_face(face_roi)
        faces.append(enhanced)
        labels.append(student_id)

        print(f"✅ Loaded {filename} → Student ID {student_id}")

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
        print("❌ No valid face images found.")
        return False

    unique_ids = sorted(set(labels))

    print()
    print(f"👥 Students detected: {len(unique_ids)}")
    print(f"🆔 Student IDs: {unique_ids}")
    print(f"📷 Training faces: {len(faces)}")
    print()

    if len(unique_ids) < 2:
        print("⚠️ NOTE: Only one student is currently registered.")
        print("Register more students for broader multi-class classification.")
        print()

    # Create LBPH Face Recognizer with fine-grained radius and grid
    recognizer = cv2.face.LBPHFaceRecognizer_create(
        radius=1,
        neighbors=8,
        grid_x=8,
        grid_y=8
    )

    recognizer.train(
        faces,
        np.array(labels, dtype=np.int32)
    )

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    recognizer.save(MODEL_PATH)

    print("🔥 Face model trained successfully!")
    print(f"📁 Model saved: {MODEL_PATH}")
    print()

    return True


# ==================================================
# RECOGNIZE FACE
# ==================================================

def recognize_face(image_path):
    if not os.path.exists(MODEL_PATH):
        print("❌ Face model not found at:", MODEL_PATH)
        return None

    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        print("❌ Could not read image:", image_path)
        return None

    recognizer = cv2.face.LBPHFaceRecognizer_create(
        radius=1,
        neighbors=8,
        grid_x=8,
        grid_y=8
    )
    recognizer.read(MODEL_PATH)

    detected_faces = FACE_CASCADE.detectMultiScale(
        image,
        scaleFactor=1.1,
        minNeighbors=4,
        minSize=(60, 60)
    )

    if len(detected_faces) == 0:
        h, w = image.shape
        if h >= 50 and w >= 50:
            detected_faces = [(0, 0, w, h)]
        else:
            print("❌ No face detected.")
            return None

    for (x, y, w, h) in detected_faces:
        face_roi = image[y:y + h, x:x + w]
        enhanced = preprocess_face(face_roi)

        student_id, confidence = recognizer.predict(enhanced)

        print()
        print(f"🔍 Predicted Student ID: {student_id}")
        print(f"🔍 LBPH Distance: {confidence:.2f}")

        # In LBPH: lower confidence distance means higher similarity
        if confidence < 70:
            print("✅ Face recognized!")
            return student_id
        else:
            print("❌ Face distance too high (Unrecognized student).")
            return None

    return None
