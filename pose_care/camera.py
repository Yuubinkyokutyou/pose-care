from __future__ import annotations

import threading
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

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
        capture = None
        try:
            self.status_changed.emit("モデルを準備しています")
            ensure_model(self.model_file, self.model_progress.emit)
            if self._stop_event.is_set():
                return

            import cv2
            import mediapipe as mp

            self.status_changed.emit("カメラに接続しています")
            capture = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not capture.isOpened():
                capture.release()
                capture = cv2.VideoCapture(self.camera_index)
            if not capture.isOpened():
                raise RuntimeError(
                    f"カメラ {self.camera_index} を開けません。設定でカメラ番号を変更してください。"
                )
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
            capture.set(cv2.CAP_PROP_FPS, 30)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

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
                self.status_changed.emit("カメラ準備完了")
                last_inference = 0.0
                last_timestamp_ms = 0
                frames = 0
                fps_started = time.perf_counter()
                last_landmarks: list[Landmark] = []
                while not self._stop_event.is_set():
                    ok, frame = capture.read()
                    if not ok:
                        time.sleep(0.05)
                        continue
                    frame = cv2.flip(frame, 1)
                    now = time.perf_counter()
                    if now - last_inference >= (1.0 / 15.0):
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
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

                    self._draw_landmarks(frame, last_landmarks, cv2)
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    height, width, channels = rgb_frame.shape
                    qimage = QImage(
                        rgb_frame.data,
                        width,
                        height,
                        channels * width,
                        QImage.Format.Format_RGB888,
                    ).copy()
                    self.frame_ready.emit(qimage)

                    frames += 1
                    fps_elapsed = now - fps_started
                    if fps_elapsed >= 1.5:
                        self.fps_changed.emit(frames / fps_elapsed)
                        frames = 0
                        fps_started = now
        except Exception as error:
            self.camera_error.emit(str(error))
        finally:
            if capture is not None:
                capture.release()

    @staticmethod
    def _draw_landmarks(frame, landmarks: list[Landmark], cv2_module) -> None:
        if not landmarks:
            return
        height, width = frame.shape[:2]
        points = [
            (int(item[0] * width), int(item[1] * height), item[3])
            for item in landmarks
        ]
        for start, end in UPPER_BODY_CONNECTIONS:
            if start >= len(points) or end >= len(points):
                continue
            first, second = points[start], points[end]
            if first[2] < 0.35 or second[2] < 0.35:
                continue
            cv2_module.line(frame, first[:2], second[:2], (186, 208, 53), 3, cv2_module.LINE_AA)
        for index, (x, y, visibility) in enumerate(points):
            if index > 22 or visibility < 0.35:
                continue
            radius = 5 if index in (0, 11, 12) else 3
            cv2_module.circle(frame, (x, y), radius, (235, 244, 235), -1, cv2_module.LINE_AA)

        if len(points) > 12 and all(points[index][2] >= 0.35 for index in (0, 11, 12)):
            shoulder_mid = (
                (points[11][0] + points[12][0]) // 2,
                (points[11][1] + points[12][1]) // 2,
            )
            cv2_module.line(frame, points[0][:2], shoulder_mid, (96, 184, 244), 4, cv2_module.LINE_AA)
            cv2_module.circle(frame, shoulder_mid, 6, (96, 184, 244), -1, cv2_module.LINE_AA)
