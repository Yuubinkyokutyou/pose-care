from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine

from pose_care.config import SettingsStore
from pose_care.history import PostureHistory
from pose_care.models import AppSettings, DetectionState
from pose_care.notifications import WindowsNotifier
from pose_care.ui.controller import PoseCareController
from pose_care.ui.image_provider import CameraImageProvider
from pose_care.ui.style import make_app_icon


class FakeReminderWindow:
    def __init__(self) -> None:
        self.shows = 0
        self.hides = 0

    def width(self) -> int:
        return 320

    def height(self) -> int:
        return 96

    def setX(self, value: int) -> None:
        pass

    def setY(self, value: int) -> None:
        pass

    def show(self) -> None:
        self.shows += 1

    def hide(self) -> None:
        self.hides += 1


def test_reminder_tracks_bad_posture_until_good_posture_is_stable(tmp_path):
    QApplication.instance() or QApplication([])
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        CameraImageProvider(),
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
    )
    reminder = FakeReminderWindow()
    controller.attach_reminder_window(reminder)
    bad = DetectionState(kind="bad", profile_name="前かがみ")
    good = DetectionState(kind="good")

    controller._update_reminder(bad, 10.0)
    controller._update_reminder(bad, 11.0)
    assert reminder.shows == 1
    assert controller.reminderProfileName == "前かがみ"

    controller._update_reminder(good, 12.0)
    controller._update_reminder(good, 13.9)
    assert reminder.hides == 0
    controller._update_reminder(bad, 14.0)
    controller._update_reminder(good, 15.0)
    controller._update_reminder(good, 17.0)
    assert reminder.hides == 1

    controller._update_reminder(bad, 18.0)
    controller._update_reminder(DetectionState(kind="no_pose"), 19.0)
    controller._update_reminder(DetectionState(kind="no_pose"), 28.0)
    assert reminder.hides == 1
    controller._update_reminder(DetectionState(kind="no_pose"), 29.0)
    assert reminder.hides == 2

    controller._update_reminder(bad, 30.0)
    controller.toggleMonitoring(False)
    assert reminder.hides == 3
    controller.shutdown()


def test_reminder_qml_loads(tmp_path):
    app = QApplication.instance() or QApplication([])
    controller = PoseCareController(
        SettingsStore(tmp_path / "settings.json"),
        AppSettings(),
        make_app_icon(),
        CameraImageProvider(),
        history=PostureHistory(tmp_path / "history.sqlite3"),
        notifier=WindowsNotifier(toaster=object(), toast_factory=lambda fields: fields),
    )
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("controller", controller)
    engine.load(Path(__file__).parents[1] / "pose_care/ui/qml/PostureReminder.qml")
    assert len(engine.rootObjects()) == 1
    assert not engine.rootObjects()[0].isVisible()
    controller.shutdown()
    assert app is not None
