from __future__ import annotations

import asyncio
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen

from pose_care.posture import Landmark, extract_pose_feature


MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)

UPPER_BODY_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8),
    (9, 10), (11, 12), (11, 13), (13, 15), (15, 17), (15, 19),
    (15, 21), (17, 19), (12, 14), (14, 16), (16, 18), (16, 20),
    (16, 22), (18, 20),
)


def _shared_camera_groups(groups: Sequence[Any], color_kind: Any) -> list[Any]:
    """Deduplicate color cameras and prefer groups that include companion sensors."""
    group_by_color_source: dict[str, Any] = {}
    source_order: list[str] = []
    for group in groups:
        color_source_ids = [
            info.id for info in group.source_infos if info.source_kind == color_kind
        ]
        for source_id in color_source_ids:
            if source_id not in group_by_color_source:
                source_order.append(source_id)
            current = group_by_color_source.get(source_id)
            if current is None or len(group.source_infos) > len(current.source_infos):
                group_by_color_source[source_id] = group

    result: list[Any] = []
    seen_group_ids: set[str] = set()
    for source_id in source_order:
        group = group_by_color_source[source_id]
        if group.id in seen_group_ids:
            continue
        seen_group_ids.add(group.id)
        result.append(group)
    return result


class SharedCameraCapture:
    """Read color frames through the Windows shared camera pipeline."""

    def __init__(self, camera_index: int) -> None:
        self.camera_index = camera_index
        self._capture: Any | None = None
        self._reader: Any | None = None
        self._frame_arrived_token: Any | None = None
        self._frame_available = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._frame_error: Exception | None = None

    async def open(self) -> None:
        from winrt.windows.media.capture import (
            MediaCapture,
            MediaCaptureInitializationSettings,
            MediaCaptureMemoryPreference,
            MediaCaptureSharingMode,
            MediaStreamType,
            StreamingCaptureMode,
        )
        from winrt.windows.media.capture.frames import (
            MediaFrameReaderAcquisitionMode,
            MediaFrameReaderStartStatus,
            MediaFrameSourceGroup,
            MediaFrameSourceKind,
        )
        groups = _shared_camera_groups(
            await MediaFrameSourceGroup.find_all_async(),
            MediaFrameSourceKind.COLOR,
        )
        if self.camera_index >= len(groups):
            raise RuntimeError(
                f"共有カメラ {self.camera_index} が見つかりません。"
                "設定でカメラ番号を変更してください。"
            )

        settings = MediaCaptureInitializationSettings()
        settings.source_group = groups[self.camera_index]
        settings.sharing_mode = MediaCaptureSharingMode.SHARED_READ_ONLY
        settings.memory_preference = MediaCaptureMemoryPreference.CPU
        settings.streaming_capture_mode = StreamingCaptureMode.VIDEO

        capture = MediaCapture()
        reader = None
        frame_arrived_token = None
        try:
            await capture.initialize_with_settings_async(settings)
            sources = [
                source
                for source in capture.frame_sources.values()
                if source.info.source_kind == MediaFrameSourceKind.COLOR
            ]
            if not sources:
                raise RuntimeError("共有カメラにRGB映像ソースがありません。")
            source = min(
                sources,
                key=lambda item: (
                    item.info.media_stream_type != MediaStreamType.VIDEO_PREVIEW,
                    item.info.media_stream_type != MediaStreamType.VIDEO_RECORD,
                ),
            )
            reader = await capture.create_frame_reader_async(source)
            reader.acquisition_mode = MediaFrameReaderAcquisitionMode.REALTIME
            frame_arrived_token = reader.add_frame_arrived(self._on_frame_arrived)
            status = await reader.start_async()
            if status != MediaFrameReaderStartStatus.SUCCESS:
                raise RuntimeError(
                    f"共有カメラを開始できませんでした（{status.name}）。"
                )
        except Exception:
            if reader is not None:
                if frame_arrived_token is not None:
                    reader.remove_frame_arrived(frame_arrived_token)
                reader.close()
            capture.close()
            raise

        self._capture = capture
        self._reader = reader
        self._frame_arrived_token = frame_arrived_token

    def _on_frame_arrived(self, sender: Any, _args: Any) -> None:
        try:
            frame = self._copy_latest_frame(sender)
        except Exception as error:
            with self._frame_lock:
                self._frame_error = error
            self._frame_available.set()
            return
        if frame is None:
            return
        with self._frame_lock:
            self._latest_frame = frame
        self._frame_available.set()

    def read(self) -> np.ndarray | None:
        if self._reader is None or not self._frame_available.is_set():
            return None
        with self._frame_lock:
            frame, self._latest_frame = self._latest_frame, None
            error, self._frame_error = self._frame_error, None
            self._frame_available.clear()
        if error is not None:
            raise error
        return frame

    @staticmethod
    def _copy_latest_frame(reader: Any) -> np.ndarray | None:
        reference = reader.try_acquire_latest_frame()
        if reference is None:
            return None
        bitmap = None
        converted_bitmap = None
        try:
            buffered_frame = reference.buffer_media_frame
            if buffered_frame is not None:
                encoded_buffer = buffered_frame.buffer
                encoded = bytes(memoryview(encoded_buffer)[:encoded_buffer.length])
                image = QImage.fromData(encoded)
                if image.isNull():
                    raise RuntimeError("共有カメラの圧縮フレームを展開できません。")
                image = image.convertToFormat(QImage.Format.Format_RGB888)
                width, height = image.width(), image.height()
                bytes_per_line = image.bytesPerLine()
                pixels = np.frombuffer(
                    image.constBits(),
                    dtype=np.uint8,
                    count=bytes_per_line * height,
                ).reshape((height, bytes_per_line))
                rgb = pixels[:, : width * 3].reshape((height, width, 3))
                return np.ascontiguousarray(rgb[:, ::-1])

            video_frame = reference.video_media_frame
            if video_frame is None:
                return None
            bitmap = video_frame.software_bitmap
            if bitmap is None:
                return None

            from winrt.windows.graphics.imaging import (
                BitmapAlphaMode,
                BitmapPixelFormat,
                SoftwareBitmap,
            )
            from winrt.windows.storage.streams import Buffer

            if bitmap.bitmap_pixel_format != BitmapPixelFormat.BGRA8:
                converted_bitmap = SoftwareBitmap.convert(
                    bitmap,
                    BitmapPixelFormat.BGRA8,
                    BitmapAlphaMode.IGNORE,
                )

            readable_bitmap = converted_bitmap or bitmap
            width = readable_bitmap.pixel_width
            height = readable_bitmap.pixel_height
            byte_count = width * height * 4
            buffer = Buffer(byte_count)
            readable_bitmap.copy_to_buffer(buffer)
            bgra = np.frombuffer(memoryview(buffer), dtype=np.uint8, count=byte_count)
            bgra = bgra.reshape((height, width, 4))
            return np.ascontiguousarray(bgra[:, ::-1, 2::-1])
        finally:
            if converted_bitmap is not None:
                converted_bitmap.close()
            if bitmap is not None:
                bitmap.close()
            reference.close()

    async def close(self) -> None:
        reader, self._reader = self._reader, None
        token, self._frame_arrived_token = self._frame_arrived_token, None
        capture, self._capture = self._capture, None
        if reader is not None:
            try:
                if token is not None:
                    reader.remove_frame_arrived(token)
                await reader.stop_async()
            finally:
                reader.close()
        if capture is not None:
            capture.close()
        with self._frame_lock:
            self._latest_frame = None
            self._frame_error = None
            self._frame_available.clear()


def ensure_model(destination: Path, progress_callback=None) -> Path:
    if destination.exists() and destination.stat().st_size > 1_000_000:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "PoseCare/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response, temporary.open("wb") as output:
            total = int(response.headers.get("Content-Length", "0"))
            downloaded = 0
            while True:
                chunk = response.read(128 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total:
                    progress_callback(min(100, int(downloaded * 100 / total)))
        if temporary.stat().st_size < 1_000_000:
            raise RuntimeError("ダウンロードしたモデルファイルが不完全です")
        temporary.replace(destination)
        return destination
    except Exception:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass
        raise


class CameraWorker(QThread):
    frame_ready = Signal(QImage)
    pose_ready = Signal(object, object)
    status_changed = Signal(str)
    model_progress = Signal(int)
    camera_error = Signal(str)
    fps_changed = Signal(float)

    def __init__(self, camera_index: int, model_file: Path, parent=None) -> None:
        super().__init__(parent)
        self.camera_index = camera_index
        self.model_file = model_file
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            self.status_changed.emit("モデルを準備しています")
            ensure_model(self.model_file, self.model_progress.emit)
            if self._stop_event.is_set():
                return

            from winrt.runtime import ApartmentType, init_apartment, uninit_apartment

            init_apartment(ApartmentType.MULTI_THREADED)
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._run_shared_camera())
            finally:
                asyncio.set_event_loop(None)
                loop.close()
                uninit_apartment()
        except Exception as error:
            self.camera_error.emit(str(error))

    async def _run_shared_camera(self) -> None:
        import mediapipe as mp

        camera = SharedCameraCapture(self.camera_index)
        self.status_changed.emit("共有モードでカメラに接続しています")
        try:
            await camera.open()
            options = mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(self.model_file)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=0.55,
                min_pose_presence_confidence=0.55,
                min_tracking_confidence=0.55,
                output_segmentation_masks=False,
            )
            with mp.tasks.vision.PoseLandmarker.create_from_options(options) as landmarker:
                self.status_changed.emit("カメラ準備完了（共有モード）")
                last_inference = 0.0
                last_timestamp_ms = 0
                frames = 0
                fps_started = time.perf_counter()
                last_landmarks: list[Landmark] = []
                while not self._stop_event.is_set():
                    rgb_frame = camera.read()
                    if rgb_frame is None:
                        await asyncio.sleep(0.01)
                        continue
                    now = time.perf_counter()
                    if now - last_inference >= (1.0 / 15.0):
                        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                        timestamp_ms = max(last_timestamp_ms + 1, int(now * 1000))
                        last_timestamp_ms = timestamp_ms
                        result = landmarker.detect_for_video(image, timestamp_ms)
                        last_inference = now
                        feature = None
                        last_landmarks = []
                        if result.pose_landmarks:
                            normalized = result.pose_landmarks[0]
                            last_landmarks = [
                                (
                                    float(item.x),
                                    float(item.y),
                                    float(item.z),
                                    float(item.visibility if item.visibility is not None else 1.0),
                                )
                                for item in normalized
                            ]
                            if result.pose_world_landmarks:
                                world = [
                                    (
                                        float(item.x),
                                        float(item.y),
                                        float(item.z),
                                        float(item.visibility if item.visibility is not None else 1.0),
                                    )
                                    for item in result.pose_world_landmarks[0]
                                ]
                                feature = extract_pose_feature(world)
                        self.pose_ready.emit(feature, last_landmarks)

                    qimage = self._make_qimage(rgb_frame, last_landmarks)
                    self.frame_ready.emit(qimage)
                    frames += 1
                    fps_elapsed = now - fps_started
                    if fps_elapsed >= 1.5:
                        self.fps_changed.emit(frames / fps_elapsed)
                        frames = 0
                        fps_started = now
        finally:
            await camera.close()

    @classmethod
    def _make_qimage(cls, rgb_frame: np.ndarray, landmarks: list[Landmark]) -> QImage:
        height, width, channels = rgb_frame.shape
        image = QImage(
            rgb_frame.data,
            width,
            height,
            channels * width,
            QImage.Format.Format_RGB888,
        ).copy()
        cls._draw_landmarks(image, landmarks)
        return image

    @staticmethod
    def _draw_landmarks(image: QImage, landmarks: list[Landmark]) -> None:
        if not landmarks:
            return
        width, height = image.width(), image.height()
        points = [
            (int(item[0] * width), int(item[1] * height), item[3])
            for item in landmarks
        ]
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            painter.setPen(QPen(QColor(53, 208, 186), 3))
            for start, end in UPPER_BODY_CONNECTIONS:
                if start >= len(points) or end >= len(points):
                    continue
                first, second = points[start], points[end]
                if first[2] < 0.35 or second[2] < 0.35:
                    continue
                painter.drawLine(first[0], first[1], second[0], second[1])

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(235, 244, 235))
            for index, (x, y, visibility) in enumerate(points):
                if index > 22 or visibility < 0.35:
                    continue
                radius = 5 if index in (0, 11, 12) else 3
                painter.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)

            if len(points) > 12 and all(
                points[index][2] >= 0.35 for index in (0, 11, 12)
            ):
                shoulder_mid = (
                    (points[11][0] + points[12][0]) // 2,
                    (points[11][1] + points[12][1]) // 2,
                )
                painter.setPen(QPen(QColor(244, 184, 96), 4))
                painter.drawLine(
                    points[0][0],
                    points[0][1],
                    shoulder_mid[0],
                    shoulder_mid[1],
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(244, 184, 96))
                painter.drawEllipse(
                    shoulder_mid[0] - 6,
                    shoulder_mid[1] - 6,
                    12,
                    12,
                )
        finally:
            painter.end()
