import cv2


# Load OpenCV's pre-trained face detector
FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades +
    "haarcascade_frontalface_default.xml"
)


def detect_face(image_path):
    """
    Detect whether at least one face exists
    in the supplied image.
    """

    image = cv2.imread(image_path)

    if image is None:
        return False

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    faces = FACE_CASCADE.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(80, 80)
    )

    return len(faces) > 0