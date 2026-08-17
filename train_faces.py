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