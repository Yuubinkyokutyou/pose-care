from __future__ import annotations

from threading import Lock

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider


class CameraImageProvider(QQuickImageProvider):
    """Keep the latest camera frame available to QML without copying it to a URL."""

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._image = QImage()
        self._lock = Lock()

    def set_image(self, image: QImage) -> None:
        with self._lock:
            self._image = image.copy()

    def clear(self) -> None:
        with self._lock:
            self._image = QImage()

    def requestImage(
        self,
        image_id: str,
        size: QSize,
        requested_size: QSize,
    ) -> QImage:
        del image_id
        with self._lock:
            image = self._image.copy()
        if image.isNull():
            return image
        size.setWidth(image.width())
        size.setHeight(image.height())
        if requested_size.isValid():
            return image.scaled(
                requested_size,
                aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                mode=Qt.TransformationMode.SmoothTransformation,
            )
        return image
