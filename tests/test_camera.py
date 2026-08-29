import sys
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QImage

from pose_care.camera import (
    CAMERA_FRAME_STALL_TIMEOUT_SECONDS,
    _camera_open_error_message,
    _camera_open_error_type,
    _frame_stream_stalled,
    _shared_camera_groups,
)
from pose_care.camera import CameraConfigurationError, CameraConnectionError
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


@pytest.mark.parametrize(
    ("error_code", "expected_type"),
    [
        (-2_147_024_864, CameraConnectionError),  # 0x80070020 sharing violation
        (-2_147_024_895, CameraConnectionError),  # 0x80070001 after sleep
        (32, CameraConnectionError),
        (-2_147_024_891, CameraConfigurationError),  # 0x80070005 access denied
        (5, CameraConfigurationError),
        (-1_072_844_856, CameraConfigurationError),  # 0xC00DAFC8 unsupported
        (-12345, CameraConnectionError),
    ],
)
def test_camera_open_error_type_retries_device_failures(
    error_code, expected_type
):
    error = OSError(error_code, "camera initialization failed")

    assert _camera_open_error_type(error) is expected_type


def test_camera_open_error_explains_sleep_resume_failure():
    error = OSError(22, "incorrect function", None, -2_147_024_895)

    assert "スリープ復帰後" in _camera_open_error_message(error)


def test_frame_stream_stall_timeout_detects_sleep_gap():
    assert not _frame_stream_stalled(
        100.0,
        100.0 + CAMERA_FRAME_STALL_TIMEOUT_SECONDS - 0.01,
    )
    assert _frame_stream_stalled(
        100.0,
        100.0 + CAMERA_FRAME_STALL_TIMEOUT_SECONDS,
    )


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
        video_media_frame=None,
        close=lambda: None,
    )
    reader = SimpleNamespace(try_acquire_latest_frame=lambda: reference)

    frame = SharedCameraCapture._copy_latest_frame(reader)

    assert frame is not None
    assert frame.shape == (2, 4, 3)
    assert frame.dtype == np.uint8


@pytest.mark.skipif(sys.platform != "win32", reason="WinRT is only available on Windows")
def test_copy_latest_frame_prefers_nv12_software_bitmap_over_raw_buffer():
    from winrt.windows.graphics.imaging import (
        BitmapAlphaMode,
        BitmapPixelFormat,
        SoftwareBitmap,
    )
    from winrt.windows.storage.streams import Buffer

    width = 2
    height = 2
    nv12_pixels = bytes((96, 96, 96, 96, 128, 128))
    nv12_buffer = Buffer(len(nv12_pixels))
    nv12_buffer.length = len(nv12_pixels)
    memoryview(nv12_buffer)[:] = nv12_pixels
    bitmap = SoftwareBitmap(
        BitmapPixelFormat.NV12,
        width,
        height,
        BitmapAlphaMode.IGNORE,
    )
    bitmap.copy_from_buffer(nv12_buffer)
    reference = SimpleNamespace(
        buffer_media_frame=SimpleNamespace(buffer=nv12_buffer),
        video_media_frame=SimpleNamespace(software_bitmap=bitmap),
        close=lambda: None,
    )
    reader = SimpleNamespace(try_acquire_latest_frame=lambda: reference)

    frame = SharedCameraCapture._copy_latest_frame(reader)

    assert frame is not None
    assert frame.shape == (height, width, 3)
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
