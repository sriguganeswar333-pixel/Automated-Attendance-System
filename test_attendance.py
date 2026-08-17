from attendance import mark_attendance


print()
print("======================================")
print("       ATTENDANCE TEST")
print("======================================")
print()


result = mark_attendance(
    student_id=1,
    confidence=35.26
)


print(result["message"])


if result.get("date"):

    print(
        f"📅 Date: {result['date']}"
    )

    print(
        f"⏰ Time: {result['time']}"
    )


print()