from ai.face_recognition import recognize_face


image_path = "data/faces/student_1.jpg"


print()
print("======================================")
print("        FACE RECOGNITION TEST")
print("======================================")
print()


student_id = recognize_face(
    image_path
)


if student_id is not None:

    print()
    print(
        f"🎉 FACE RECOGNIZED!"
    )

    print(
        f"🎓 Student ID: {student_id}"
    )

else:

    print()
    print(
        "❌ FACE NOT RECOGNIZED."
    )