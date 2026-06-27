"""画像に顔が写っているかをローカルで判定する（OpenCV haarcascade・オフライン）。"""
from pathlib import Path


def has_face(image_path: Path) -> bool:
    import cv2  # opencv-python

    img = cv2.imread(str(image_path))
    if img is None:
        return False
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    return len(faces) > 0
