from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtWidgets import QApplication

from pose_care.config import SettingsStore
from pose_care.history import PostureHistory
from pose_care.models import AppSettings
from pose_care.ui.controller import PoseCareController
from pose_care.ui.image_provider import CameraImageProvider
from pose_care.ui.style import make_app_icon
from pose_care.updater import (
    BuildInfo,
    PreparedUpdate,
    ReleaseInfo,
    UpdateCheck,
    UpdateNetworkError,
    UpdateProgress,
)


class FakeNotifier:
    def send(self, title, message, on_activated=None):
        del title, message, on_activated
        return True


class FakeApplicationUpdater:
    def __init__(self, *, can_apply_update: bool = True) -> None:
        self.current_build = BuildInfo("v0.2.0-build.10.1", "0.2.0")
        self.can_apply_update = can_apply_update
        self.check_outcome: UpdateCheck | BaseException | None = None
        self.prepare_outcome: PreparedUpdate | BaseException | None = None
        self.check_calls = 0
        self.prepare_calls: list[ReleaseInfo] = []
        self.launch_calls: list[PreparedUpdate] = []
        self.worker_thread_ids: list[int] = []

    def check_for_update(
        self, progress: Callable[[UpdateProgress], None]
    ) -> UpdateCheck:
        self.check_calls += 1
        self.worker_thread_ids.append(threading.get_ident())
        progress(UpdateProgress("checking", 35, "GitHub Releasesを確認しています"))
        outcome = self.check_outcome
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, UpdateCheck)
        progress(UpdateProgress("checking", 100, "確認が完了しました"))
        return outcome

    def prepare_update(
        self,
        release: ReleaseInfo,
        progress: Callable[[UpdateProgress], None],
    ) -> PreparedUpdate:
        self.prepare_calls.append(release)
        self.worker_thread_ids.append(threading.get_ident())
        progress(UpdateProgress("downloading_checksum", 100, "検証情報を取得しました"))
        progress(UpdateProgress("downloading", 50, "ダウンロードしています… 50%"))
        progress(UpdateProgress("verifying", 100, "検証が完了しました"))
        progress(UpdateProgress("extracting", 100, "更新ファイルを準備しました"))
        outcome = self.prepare_outcome
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, PreparedUpdate)
        return outcome

    def launch_update(
        self,
        prepared: PreparedUpdate,
        progress: Callable[[UpdateProgress], None],
    ) -> object:
        self.launch_calls.append(prepared)
        progress(UpdateProgress("launching", 100, "更新プログラムを起動しました"))
        return object()


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _release(tag: str = "v0.2.0-build.11.1") -> ReleaseInfo:
    return ReleaseInfo(
        tag=tag,
        version="0.2.0",
        name=tag,
        notes="",
        page_url=f"https://github.com/example/releases/tag/{tag}",
        published_at="2026-08-23T12:00:00Z",
        archive_url=f"https://github.com/example/releases/download/{tag}/app.zip",
        checksum_url=f"https://github.com/example/releases/download/{tag}/app.zip.sha256",
        archive_size=100,
    )


def _prepared_update(tmp_path: Path, release: ReleaseInfo) -> PreparedUpdate:
    workspace = tmp_path / "prepared-update"
    payload = workspace / "payload"
    payload.mkdir(parents=True)
    (payload / "PoseCare.exe").write_bytes(b"verified payload")
    return PreparedUpdate(
        release=release,
        workspace=workspace,
        archive_path=workspace / "PoseCare-windows-x64.zip",
        payload_dir=payload,
        sha256="a" * 64,
        manifest_sha256="b" * 64,
    )


@pytest.fixture
def controller_factory(tmp_path):
    application = _application()
    controllers: list[PoseCareController] = []

    def create(updater: FakeApplicationUpdater) -> PoseCareController:
        index = len(controllers)
        controller = PoseCareController(
            SettingsStore(tmp_path / f"settings-{index}.json"),
            AppSettings(),
            make_app_icon(),
            CameraImageProvider(),
            history=PostureHistory(tmp_path / f"history-{index}.sqlite3"),
            notifier=FakeNotifier(),
            updater=updater,
        )
        controllers.append(controller)
        return controller

    yield application, create

    for controller in controllers:
        controller.shutdown()
        thread = controller._update_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)
    application.processEvents()


def _wait_until(
    application: QApplication,
    condition: Callable[[], bool],
    *,
    timeout: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        application.processEvents()
        if condition():
            return
        time.sleep(0.005)
    application.processEvents()
    assert condition(), "Qtの非同期更新処理が時間内に完了しませんでした"


@pytest.mark.parametrize(
    ("outcome_kind", "expected_state", "expected_status"),
    [
        ("available", "available", "v0.2.0-build.11.1 を利用できます"),
        ("current", "upToDate", "PoseCareは最新です"),
        ("error", "error", "GitHubに接続できません"),
    ],
)
def test_check_for_updates_updates_controller_from_worker_thread(
    controller_factory,
    outcome_kind,
    expected_state,
    expected_status,
):
    application, create_controller = controller_factory
    updater = FakeApplicationUpdater()
    release = _release()
    if outcome_kind == "error":
        updater.check_outcome = UpdateNetworkError("GitHubに接続できません")
    else:
        updater.check_outcome = UpdateCheck(
            current=updater.current_build,
            latest=release,
            update_available=outcome_kind == "available",
        )
    controller = create_controller(updater)
    main_thread_id = threading.get_ident()

    controller.checkForUpdates()

    assert controller.updateState == "checking"
    _wait_until(application, lambda: controller.updateState == expected_state)
    assert updater.check_calls == 1
    assert len(updater.worker_thread_ids) == 1
    assert updater.worker_thread_ids[0] != main_thread_id
    assert controller.updateStatus == expected_status
    if outcome_kind == "error":
        assert controller.latestVersion == ""
        assert controller.updateProgress == 0.0
    else:
        assert controller.latestVersion == release.tag
        assert controller.updateProgress == 1.0


def test_available_update_is_prepared_asynchronously_and_becomes_ready(
    controller_factory, tmp_path
):
    application, create_controller = controller_factory
    updater = FakeApplicationUpdater(can_apply_update=True)
    release = _release()
    prepared = _prepared_update(tmp_path, release)
    updater.check_outcome = UpdateCheck(
        current=updater.current_build,
        latest=release,
        update_available=True,
    )
    updater.prepare_outcome = prepared
    controller = create_controller(updater)

    controller.checkForUpdates()
    _wait_until(application, lambda: controller.updateState == "available")
    controller.installUpdate()

    assert controller.updateState == "downloading"
    _wait_until(application, lambda: controller.updateState == "ready")
    assert updater.prepare_calls == [release]
    assert controller._prepared_update is prepared
    assert controller.updateProgress == 1.0
    assert controller.updateStatus == "ダウンロード完了。再起動すると更新されます"
    assert prepared.workspace.exists()


def test_source_run_refuses_install_before_downloading(controller_factory):
    application, create_controller = controller_factory
    updater = FakeApplicationUpdater(can_apply_update=False)
    release = _release()
    updater.check_outcome = UpdateCheck(
        current=updater.current_build,
        latest=release,
        update_available=True,
    )
    controller = create_controller(updater)

    controller.checkForUpdates()
    _wait_until(application, lambda: controller.updateState == "available")
    controller.installUpdate()

    assert controller.updateState == "error"
    assert "Windows向けにビルドされたPoseCare.exe" in controller.updateStatus
    assert updater.prepare_calls == []
    assert updater.launch_calls == []


def test_shutdown_cleans_unapplied_prepared_update(controller_factory, tmp_path):
    application, create_controller = controller_factory
    updater = FakeApplicationUpdater(can_apply_update=True)
    release = _release()
    prepared = _prepared_update(tmp_path, release)
    updater.check_outcome = UpdateCheck(
        current=updater.current_build,
        latest=release,
        update_available=True,
    )
    updater.prepare_outcome = prepared
    controller = create_controller(updater)

    controller.checkForUpdates()
    _wait_until(application, lambda: controller.updateState == "available")
    controller.installUpdate()
    _wait_until(application, lambda: controller.updateState == "ready")
    assert prepared.workspace.exists()

    controller.shutdown()

    assert not prepared.workspace.exists()
    assert controller._prepared_update is None
