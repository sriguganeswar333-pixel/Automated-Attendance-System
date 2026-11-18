import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from ai.face_recognition import train_model

print()
print("======================================")
print("      FACE RECOGNITION TRAINING")
print("======================================")
print()

success = train_model()

if success:
    print()
    print("🔥 TRAINING COMPLETED SUCCESSFULLY!")
    print("📁 Model saved: data/face_model.yml")
    print()
else:
    print()
    print("❌ TRAINING FAILED!")
    print()
