import sys
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

from pose_care.camera import _shared_camera_groups
from pose_care.camera import SharedCameraCapture


def _source(source_id, kind):
    return SimpleNamespace(id=source_id, source_kind=kind)


def _group(group_id, *sources):
    return SimpleNamespace(id=group_id, source_infos=list(sources))


def test_shared_camera_groups_deduplicate_and_prefer_companion_sensors():
    color = object()
    infrared = object()
    standalone = _group("standalone", _source("rgb-a", color))
    combined = _group(
        "combined",
        _source("rgb-a", color),
        _source("ir-a", infrared),
    )
    second_camera = _group("second", _source("rgb-b", color))
    infrared_only = _group("hello-only", _source("ir-b", infrared))

    groups = _shared_camera_groups(
        [standalone, combined, second_camera, infrared_only],
        color,
    )

    assert groups == [combined, second_camera]


@pytest.mark.skipif(sys.platform != "win32", reason="WinRT is only available on Windows")
def test_copy_latest_frame_decodes_native_jpeg_buffer():
    from winrt.windows.storage.streams import Buffer

    source = QImage(4, 2, QImage.Format.Format_RGB888)
    source.fill(QColor("#42d6be"))
    encoded = QByteArray()
    output = QBuffer(encoded)
    output.open(QIODevice.OpenModeFlag.WriteOnly)
    assert source.save(output, "JPG")
    output.close()

    native_buffer = Buffer(len(encoded))
    native_buffer.length = len(encoded)
    memoryview(native_buffer)[:] = bytes(encoded)
    reference = SimpleNamespace(
        buffer_media_frame=SimpleNamespace(buffer=native_buffer),
        close=lambda: None,
    )
    reader = SimpleNamespace(try_acquire_latest_frame=lambda: reference)

    frame = SharedCameraCapture._copy_latest_frame(reader)

    assert frame is not None
    assert frame.shape == (2, 4, 3)
    assert frame.dtype == np.uint8


@pytest.mark.skipif(sys.platform != "win32", reason="WinRT is only available on Windows")
def test_copy_latest_frame_converts_software_bitmap_and_mirrors():
    from winrt.windows.graphics.imaging import (
        BitmapAlphaMode,
        BitmapPixelFormat,
        SoftwareBitmap,
    )
    from winrt.windows.storage.streams import Buffer

    pixels = bytes((0, 0, 255, 255, 255, 0, 0, 255))
    native_buffer = Buffer(len(pixels))
    native_buffer.length = len(pixels)
    memoryview(native_buffer)[:] = pixels
    bitmap = SoftwareBitmap(
        BitmapPixelFormat.BGRA8,
        2,
        1,
        BitmapAlphaMode.IGNORE,
    )
    bitmap.copy_from_buffer(native_buffer)
    reference = SimpleNamespace(
        buffer_media_frame=None,
        video_media_frame=SimpleNamespace(software_bitmap=bitmap),
        close=lambda: None,
    )
    reader = SimpleNamespace(try_acquire_latest_frame=lambda: reference)

    frame = SharedCameraCapture._copy_latest_frame(reader)

    assert frame is not None
    assert frame.tolist() == [[[0, 0, 255], [255, 0, 0]]]
