import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from ai.face_recognition import recognize_face

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
image_path = os.path.join(BASE_DIR, "data", "faces", "student_1.jpg")

print()
print("======================================")
print("        FACE RECOGNITION TEST")
print("======================================")
print()
print(f"Testing recognition with: {image_path}")

student_id = recognize_face(image_path)

if student_id is not None:
    print()
    print("🎉 FACE RECOGNIZED!")
    print(f"🎓 Student ID: {student_id}")
else:
    print()
    print("❌ FACE NOT RECOGNIZED.")

print()
