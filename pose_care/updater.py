from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO
from urllib.parse import urlparse

from pose_care import __version__
from pose_care.config import app_data_dir


REPOSITORY_SLUG = "Yuubinkyokutyou/pose-care"
LATEST_RELEASE_API_URL = f"https://api.github.com/repos/{REPOSITORY_SLUG}/releases/latest"
RELEASE_ASSET_NAME = "PoseCare-windows-x64.zip"
CHECKSUM_ASSET_NAME = f"{RELEASE_ASSET_NAME}.sha256"
APPLICATION_EXECUTABLE = "PoseCare.exe"
INSTALL_MANIFEST_NAME = "PoseCare.install.json"
INSTALL_MANIFEST_PRODUCT = "PoseCare.Desktop"
INSTALL_MANIFEST_SCHEMA_VERSION = 1
EMBEDDED_RELEASE_PATH = "_internal/pose_care/release.json"
UPDATE_READY_FILE_ENV = "POSE_CARE_UPDATE_READY_FILE"
UPDATE_READY_TOKEN_ENV = "POSE_CARE_UPDATE_READY_TOKEN"
UPDATE_EXPECTED_TAG_ENV = "POSE_CARE_UPDATE_EXPECTED_TAG"

_API_VERSION = "2026-03-10"
_MAX_RELEASE_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_CHECKSUM_BYTES = 16 * 1024
_MAX_ARCHIVE_BYTES = 750 * 1024 * 1024
_MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024
_MAX_ARCHIVE_ENTRIES = 10_000
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_MAX_RELEASE_METADATA_BYTES = 64 * 1024
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
_RELEASE_TAG_PATTERN = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-build\.(?P<build_id>0|[1-9]\d*)\.(?P<attempt>0|[1-9]\d*))?$"
)
_CHECKSUM_PATTERN = re.compile(
    r"^(?P<digest>[0-9a-fA-F]{64})(?:\s+[*]?(?P<filename>\S+))?$"
)
_WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_TRUSTED_DOWNLOAD_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "github-releases.githubusercontent.com",
}

# Windows PowerShell 5.1 can exit successfully without executing a script when
# it is created with DETACHED_PROCESS.  CREATE_NO_WINDOW keeps the helper
# invisible, while CREATE_NEW_PROCESS_GROUP isolates it from parent console
# control events without preventing normal PowerShell startup.
_WINDOWS_UPDATE_CREATION_FLAGS = (
    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
)


class UpdateError(RuntimeError):
    """Base class for errors that can be shown in the update UI."""


class UpdateNetworkError(UpdateError):
    """GitHub could not be reached or returned an invalid HTTP response."""


class ReleaseFormatError(UpdateError):
    """A GitHub release did not contain the expected metadata or assets."""


class UpdateIntegrityError(UpdateError):
    """The downloaded archive did not match the published checksum."""


class UnsafeArchiveError(UpdateError):
    """The downloaded archive contains unsafe or unsupported entries."""


class UpdateNotSupportedError(UpdateError):
    """The running environment cannot safely replace the application."""


class UpdateStorageError(UpdateError):
    """The update workspace could not be created or written."""


@dataclass(frozen=True)
class ReleaseTag:
    text: str
    version: tuple[int, int, int]
    build: tuple[int, int] | None

    @property
    def version_text(self) -> str:
        return ".".join(str(value) for value in self.version)

    @property
    def ordering_key(self) -> tuple[int, int, int, int, int]:
        # A source/dev build has no GitHub Actions build ID.  Treat it as
        # older than the first published build of the same package version.
        build_id, attempt = self.build if self.build is not None else (-1, -1)
        return (*self.version, build_id, attempt)


@dataclass(frozen=True)
class BuildInfo:
    tag: str
    version: str
    commit: str = ""
    built_at: str = ""


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    version: str
    name: str
    notes: str
    page_url: str
    published_at: str
    archive_url: str
    checksum_url: str
    archive_size: int


@dataclass(frozen=True)
class UpdateCheck:
    current: BuildInfo
    latest: ReleaseInfo
    update_available: bool


@dataclass(frozen=True)
class UpdateProgress:
    stage: str
    percent: int
    message: str


@dataclass(frozen=True)
class InstallManifestEntry:
    path: PurePosixPath
    sha256: str


@dataclass(frozen=True)
class InstallManifest:
    entries: tuple[InstallManifestEntry, ...]
    sha256: str


@dataclass(frozen=True)
class PreparedUpdate:
    release: ReleaseInfo
    workspace: Path
    archive_path: Path
    payload_dir: Path
    sha256: str
    manifest_sha256: str

    def cleanup(self) -> None:
        """Remove an update which has not been handed to the helper process."""

        shutil.rmtree(self.workspace, ignore_errors=True)


@dataclass(frozen=True)
class LaunchedUpdate:
    helper_process: Any
    script_path: Path
    log_path: Path
    ready_path: Path
    ready_token: str
    expected_tag: str


ProgressCallback = Callable[[UpdateProgress], None]
UrlOpen = Callable[..., BinaryIO]
ProcessLauncher = Callable[..., Any]


def parse_release_tag(value: str) -> ReleaseTag:
    normalized = value.strip()
    match = _RELEASE_TAG_PATTERN.fullmatch(normalized)
    if match is None:
        raise ReleaseFormatError(
            f"リリースタグの形式が正しくありません: {normalized or '(空)'}"
        )
    build = None
    if match.group("build_id") is not None:
        build = (int(match.group("build_id")), int(match.group("attempt")))
    return ReleaseTag(
        text=normalized,
        version=(
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch")),
        ),
        build=build,
    )


def load_build_info(path: Path | None = None) -> BuildInfo:
    """Load build identity embedded by GitHub Actions.

    Source checkouts intentionally have no ``release.json``.  They use the
    package version as a build-less tag so a published build of that version
    can still be detected while developing the UI.
    """

    build_path = path or Path(__file__).with_name("release.json")
    fallback = BuildInfo(tag=f"v{__version__}", version=__version__)
    try:
        payload = json.loads(build_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return fallback
    if not isinstance(payload, Mapping):
        return fallback
    tag = payload.get("tag")
    version = payload.get("version")
    if not isinstance(tag, str) or not isinstance(version, str):
        return fallback
    try:
        parsed_tag = parse_release_tag(tag)
    except ReleaseFormatError:
        return fallback
    if parsed_tag.version_text != version.strip():
        return fallback
    commit = payload.get("commit", "")
    built_at = payload.get("built_at", "")
    return BuildInfo(
        tag=parsed_tag.text,
        version=parsed_tag.version_text,
        commit=commit if isinstance(commit, str) else "",
        built_at=built_at if isinstance(built_at, str) else "",
    )


def is_release_newer(latest_tag: str, current_tag: str) -> bool:
    latest = parse_release_tag(latest_tag)
    current = parse_release_tag(current_tag)
    return latest.ordering_key > current.ordering_key


class ApplicationUpdater:
    """Synchronous, UI-framework-independent GitHub Releases updater.

    Network work should be called from a worker thread.  ``progress`` is safe
    to bridge to a Qt signal and receives stage-local percentages.
    """

    def __init__(
        self,
        *,
        current_build: BuildInfo | None = None,
        latest_release_url: str = LATEST_RELEASE_API_URL,
        asset_name: str = RELEASE_ASSET_NAME,
        checksum_asset_name: str = CHECKSUM_ASSET_NAME,
        updates_root: Path | None = None,
        timeout_seconds: float = 30.0,
        urlopen: UrlOpen = urllib.request.urlopen,
        process_launcher: ProcessLauncher = subprocess.Popen,
        platform_name: str | None = None,
        frozen: bool | None = None,
        executable_path: Path | None = None,
        process_id: int | None = None,
    ) -> None:
        self.current_build = current_build or load_build_info()
        self.latest_release_url = latest_release_url
        self.asset_name = asset_name
        self.checksum_asset_name = checksum_asset_name
        self.timeout_seconds = timeout_seconds
        self._urlopen = urlopen
        self._process_launcher = process_launcher
        self.platform_name = platform_name if platform_name is not None else sys.platform
        self.frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        executable_value = executable_path or Path(sys.executable)
        self.executable_path = Path(os.path.abspath(executable_value))
        if updates_root is not None:
            self.updates_root = Path(os.path.abspath(updates_root))
        else:
            data_updates_root = Path(os.path.abspath(app_data_dir() / "updates"))
            if (
                self.platform_name == "win32"
                and self.frozen
                and not _same_volume(self.executable_path.parent, data_updates_root)
            ):
                # Replacing the complete install directory requires atomic moves on
                # one volume. Portable installs on another drive therefore keep the
                # workspace beside, but never inside, the PoseCare directory.
                self.updates_root = (
                    self.executable_path.parent.parent / ".PoseCare.updates"
                )
            else:
                self.updates_root = data_updates_root
        self.process_id = process_id if process_id is not None else os.getpid()

    @property
    def can_apply_update(self) -> bool:
        return self.platform_name == "win32" and self.frozen

    def check_for_update(
        self, progress: ProgressCallback | None = None
    ) -> UpdateCheck:
        self._report(progress, "checking", 0, "最新版を確認しています")
        request = urllib.request.Request(
            self.latest_release_url,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": _API_VERSION,
                "User-Agent": f"PoseCare/{self.current_build.version}",
            },
        )
        payload = self._read_json(request)
        release = self._parse_release(payload)
        try:
            update_available = is_release_newer(release.tag, self.current_build.tag)
        except ReleaseFormatError as error:
            raise ReleaseFormatError(
                f"現在のビルド情報と最新版を比較できません: {error}"
            ) from error
        message = (
            f"新しいバージョン {release.tag} があります"
            if update_available
            else "PoseCareは最新です"
        )
        self._report(progress, "checking", 100, message)
        return UpdateCheck(
            current=self.current_build,
            latest=release,
            update_available=update_available,
        )

    def prepare_update(
        self,
        release: ReleaseInfo,
        progress: ProgressCallback | None = None,
    ) -> PreparedUpdate:
        try:
            self.updates_root.mkdir(parents=True, exist_ok=True)
            workspace = Path(
                tempfile.mkdtemp(prefix="posecare-update-", dir=self.updates_root)
            ).resolve()
        except OSError as error:
            raise UpdateStorageError(
                f"更新ファイルの保存場所を作成できませんでした: {error}"
            ) from error
        archive_path = workspace / self.asset_name
        extraction_path = workspace / "payload"
        try:
            self._report(
                progress, "downloading_checksum", 0, "検証情報を取得しています"
            )
            checksum_request = self._download_request(release.checksum_url)
            checksum_body = self._read_limited(
                checksum_request, _MAX_CHECKSUM_BYTES, "検証情報"
            )
            expected_sha256 = self._parse_checksum(checksum_body)
            self._report(
                progress, "downloading_checksum", 100, "検証情報を取得しました"
            )

            archive_request = self._download_request(release.archive_url)
            actual_sha256 = self._download_archive(
                archive_request,
                archive_path,
                release.archive_size,
                progress,
            )
            self._report(progress, "verifying", 25, "ダウンロードを検証しています")
            if not hmac.compare_digest(actual_sha256, expected_sha256):
                raise UpdateIntegrityError(
                    "更新ファイルのSHA-256がリリースの検証値と一致しません"
                )
            self._report(progress, "verifying", 100, "検証が完了しました")

            self._report(progress, "extracting", 0, "更新ファイルを準備しています")
            payload_dir = self._extract_archive(archive_path, extraction_path)
            manifest = _verify_install_tree(
                payload_dir,
                release=release,
                verify_hashes=True,
            )
            # The verified payload is the only input used by the replacement
            # helper.  Keeping the archive would temporarily double the disk
            # usage of a large PyInstaller onedir distribution.
            archive_path.unlink()
            self._report(progress, "extracting", 100, "更新ファイルを準備しました")
            prepared = PreparedUpdate(
                release=release,
                workspace=workspace,
                archive_path=archive_path,
                payload_dir=payload_dir,
                sha256=actual_sha256,
                manifest_sha256=manifest.sha256,
            )
            self._report(
                progress, "ready", 100, "PoseCareを再起動して更新できます"
            )
            return prepared
        except UpdateError:
            shutil.rmtree(workspace, ignore_errors=True)
            raise
        except (OSError, ValueError, TypeError) as error:
            shutil.rmtree(workspace, ignore_errors=True)
            raise UpdateStorageError(
                f"更新ファイルを準備できませんでした: {error}"
            ) from error
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise

    def launch_update(
        self,
        prepared: PreparedUpdate,
        progress: ProgressCallback | None = None,
    ) -> LaunchedUpdate:
        """Launch the detached Windows helper; the caller should then quit.

        The helper waits for this process, renames the complete installation to
        a backup, moves the verified payload into place, and restores the backup
        on every replacement/startup failure.
        """

        if not self.can_apply_update:
            raise UpdateNotSupportedError(
                "自動更新はWindows向けにビルドされたPoseCare.exeでのみ実行できます"
            )
        workspace_path = Path(os.path.abspath(prepared.workspace))
        payload_path = Path(os.path.abspath(prepared.payload_dir))
        if not workspace_path.is_dir() or not payload_path.is_dir():
            raise UpdateNotSupportedError("準備した更新ファイルが見つかりません")
        _assert_directory_root_safe(workspace_path, "更新workspace")
        workspace = workspace_path.resolve()
        payload_dir = payload_path.resolve()
        updates_root = self.updates_root.resolve()
        if (
            not _is_relative_to(workspace, updates_root)
            or not _is_relative_to(payload_dir, workspace)
        ):
            raise UpdateNotSupportedError("準備した更新ファイルの場所が不正です")
        if not re.fullmatch(r"[0-9a-f]{64}", prepared.manifest_sha256):
            raise UpdateIntegrityError("準備したinstall manifestの検証値が不正です")

        # Re-hash every staged file immediately before the helper is launched.
        # This detects local modification between download/prepare and apply.
        _verify_install_tree(
            payload_dir,
            release=prepared.release,
            verify_hashes=True,
            expected_manifest_sha256=prepared.manifest_sha256,
        )

        executable_path = Path(os.path.abspath(self.executable_path))
        install_path = executable_path.parent
        executable = executable_path.resolve()
        install_dir = install_path.resolve()
        if executable.name.casefold() != APPLICATION_EXECUTABLE.casefold():
            raise UpdateNotSupportedError(
                f"実行中のファイルが{APPLICATION_EXECUTABLE}ではありません"
            )
        if not executable.is_file():
            raise UpdateNotSupportedError("実行中のPoseCare.exeを確認できません")
        if install_path.name.casefold() != "posecare":
            raise UpdateNotSupportedError(
                "自動更新できるインストール先はPoseCareフォルダーに限定されます"
            )
        if _is_filesystem_root(install_dir):
            raise UpdateNotSupportedError("ドライブ直下のアプリは自動更新できません")
        if _paths_overlap(install_dir, payload_dir):
            raise UpdateNotSupportedError("更新元とインストール先が重複しています")
        _verify_install_tree(
            install_path,
            release=None,
            verify_hashes=False,
        )
        if not (
            _same_volume(install_dir, workspace)
            and _same_volume(install_dir, payload_dir)
        ):
            raise UpdateNotSupportedError(
                "更新workspaceとPoseCareは同じドライブにある必要があります"
            )

        token = workspace.name.removeprefix("posecare-update-")
        safe_token = re.sub(r"[^A-Za-z0-9_-]", "", token) or "pending"
        backup_dir = install_dir.parent / f".PoseCare.backup-{safe_token}"
        if backup_dir.exists():
            raise UpdateNotSupportedError("更新用のバックアップ先がすでに存在します")
        script_path = workspace / "apply-update.ps1"
        log_path = workspace / "apply-update.log"
        ready_path = workspace / "update-ready.json"
        ready_token = secrets.token_urlsafe(32)
        try:
            ready_path.unlink(missing_ok=True)
            script_path.write_text(_UPDATE_HELPER_SCRIPT, encoding="utf-8-sig")
        except OSError as error:
            raise UpdateStorageError(
                f"更新プログラムを準備できませんでした: {error}"
            ) from error

        command = [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-PoseCareProcessId",
            str(self.process_id),
            "-InstallDir",
            str(install_dir),
            "-PayloadDir",
            str(payload_dir),
            "-BackupDir",
            str(backup_dir),
            "-LogPath",
            str(log_path),
            "-ExpectedManifestSha256",
            prepared.manifest_sha256,
            "-ExpectedTag",
            prepared.release.tag,
            "-ExpectedVersion",
            prepared.release.version,
            "-ReadyPath",
            str(ready_path),
            "-ReadyToken",
            ready_token,
        ]
        self._report(progress, "launching", 0, "更新後に再起動します")
        try:
            helper_process = self._process_launcher(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=_WINDOWS_UPDATE_CREATION_FLAGS,
                cwd=str(workspace),
            )
        except OSError as error:
            raise UpdateNotSupportedError(
                f"更新プログラムを起動できませんでした: {error}"
            ) from error
        self._report(progress, "launching", 100, "更新プログラムを起動しました")
        return LaunchedUpdate(
            helper_process=helper_process,
            script_path=script_path,
            log_path=log_path,
            ready_path=ready_path,
            ready_token=ready_token,
            expected_tag=prepared.release.tag,
        )

    def _parse_release(self, payload: Any) -> ReleaseInfo:
        if not isinstance(payload, Mapping) or payload.get("draft") is True:
            raise ReleaseFormatError("GitHubのリリース情報が正しくありません")
        tag = payload.get("tag_name")
        assets = payload.get("assets")
        if not isinstance(tag, str) or not isinstance(assets, list):
            raise ReleaseFormatError("GitHubのリリース情報が不足しています")
        parsed_tag = parse_release_tag(tag)
        asset_values: dict[str, Mapping[str, Any]] = {}
        for value in assets:
            if isinstance(value, Mapping) and isinstance(value.get("name"), str):
                asset_values[value["name"]] = value
        archive = asset_values.get(self.asset_name)
        checksum = asset_values.get(self.checksum_asset_name)
        if archive is None or checksum is None:
            raise ReleaseFormatError(
                f"リリースに{self.asset_name}または検証ファイルがありません"
            )
        archive_url = _asset_url(archive, self.asset_name)
        checksum_url = _asset_url(checksum, self.checksum_asset_name)
        archive_size = archive.get("size", 0)
        if not isinstance(archive_size, int) or not 0 < archive_size <= _MAX_ARCHIVE_BYTES:
            raise ReleaseFormatError("更新ファイルのサイズが正しくありません")
        return ReleaseInfo(
            tag=parsed_tag.text,
            version=parsed_tag.version_text,
            name=_optional_string(payload, "name") or parsed_tag.text,
            notes=_optional_string(payload, "body"),
            page_url=_optional_string(payload, "html_url"),
            published_at=_optional_string(payload, "published_at"),
            archive_url=archive_url,
            checksum_url=checksum_url,
            archive_size=archive_size,
        )

    def _read_json(self, request: urllib.request.Request) -> Any:
        body = self._read_limited(
            request, _MAX_RELEASE_RESPONSE_BYTES, "リリース情報"
        )
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise ReleaseFormatError(
                "GitHubから受信したリリース情報を読み取れません"
            ) from error

    def _read_limited(
        self,
        request: urllib.request.Request,
        maximum_bytes: int,
        description: str,
    ) -> bytes:
        try:
            with self._urlopen(request, timeout=self.timeout_seconds) as response:
                _ensure_success_response(response)
                body = response.read(maximum_bytes + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise UpdateNetworkError(
                f"{description}を取得できませんでした: {_network_error_detail(error)}"
            ) from error
        if len(body) > maximum_bytes:
            raise ReleaseFormatError(f"{description}のサイズが大きすぎます")
        return body

    def _download_archive(
        self,
        request: urllib.request.Request,
        target: Path,
        expected_size: int,
        progress: ProgressCallback | None,
    ) -> str:
        if not 0 < expected_size <= _MAX_ARCHIVE_BYTES:
            raise ReleaseFormatError("更新ファイルのサイズが正しくありません")
        temporary_target = target.with_suffix(f"{target.suffix}.part")
        digest = hashlib.sha256()
        downloaded = 0
        self._report(progress, "downloading", 0, "更新ファイルをダウンロードしています")
        try:
            with self._urlopen(request, timeout=self.timeout_seconds) as response:
                _ensure_success_response(response)
                content_length = _response_content_length(response)
                if content_length is not None and (
                    content_length != expected_size
                    or content_length > _MAX_ARCHIVE_BYTES
                ):
                    raise UpdateIntegrityError(
                        "更新ファイルのサイズがリリース情報と一致しません"
                    )
                with temporary_target.open("xb") as stream:
                    while True:
                        chunk = response.read(_DOWNLOAD_CHUNK_BYTES)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > expected_size or downloaded > _MAX_ARCHIVE_BYTES:
                            raise UpdateIntegrityError(
                                "更新ファイルのサイズがリリース情報を超えています"
                            )
                        stream.write(chunk)
                        digest.update(chunk)
                        percent = min(99, int(downloaded * 100 / expected_size))
                        self._report(
                            progress,
                            "downloading",
                            percent,
                            f"更新ファイルをダウンロードしています… {percent}%",
                        )
            if downloaded != expected_size:
                raise UpdateIntegrityError(
                    "更新ファイルのサイズがリリース情報と一致しません"
                )
            temporary_target.replace(target)
        except (UpdateError, UnsafeArchiveError):
            temporary_target.unlink(missing_ok=True)
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            temporary_target.unlink(missing_ok=True)
            raise UpdateNetworkError(
                f"更新ファイルをダウンロードできませんでした: {_network_error_detail(error)}"
            ) from error
        self._report(progress, "downloading", 100, "ダウンロードが完了しました")
        return digest.hexdigest()

    def _parse_checksum(self, body: bytes) -> str:
        try:
            text = body.decode("ascii").strip()
        except UnicodeDecodeError as error:
            raise ReleaseFormatError("SHA-256検証ファイルを読み取れません") from error
        # sha256sum files may end in a newline, but must describe exactly one file.
        if "\n" in text or "\r" in text:
            raise ReleaseFormatError("SHA-256検証ファイルの形式が正しくありません")
        match = _CHECKSUM_PATTERN.fullmatch(text)
        if match is None:
            raise ReleaseFormatError("SHA-256検証ファイルの形式が正しくありません")
        filename = match.group("filename")
        if filename is not None and Path(filename).name != self.asset_name:
            raise ReleaseFormatError("SHA-256検証ファイルの対象名が一致しません")
        return match.group("digest").lower()

    def _extract_archive(self, archive_path: Path, destination: Path) -> Path:
        destination.mkdir(parents=False, exist_ok=False)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                entries = archive.infolist()
                if not entries or len(entries) > _MAX_ARCHIVE_ENTRIES:
                    raise UnsafeArchiveError("更新ZIPのファイル数が正しくありません")
                total_size = sum(entry.file_size for entry in entries)
                if total_size <= 0 or total_size > _MAX_EXTRACTED_BYTES:
                    raise UnsafeArchiveError("更新ZIPの展開サイズが大きすぎます")
                seen_paths: set[str] = set()
                extracted_size = 0
                for entry in entries:
                    relative = _safe_archive_path(entry)
                    collision_key = str(relative).casefold()
                    if collision_key in seen_paths:
                        raise UnsafeArchiveError(
                            "更新ZIPに重複するファイル名があります"
                        )
                    seen_paths.add(collision_key)
                    target = destination.joinpath(*relative.parts)
                    if not _is_relative_to(target.resolve(), destination.resolve()):
                        raise UnsafeArchiveError("更新ZIPに不正なパスがあります")
                    if entry.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        with archive.open(entry, "r") as source, target.open("xb") as output:
                            while True:
                                chunk = source.read(_DOWNLOAD_CHUNK_BYTES)
                                if not chunk:
                                    break
                                extracted_size += len(chunk)
                                if extracted_size > _MAX_EXTRACTED_BYTES:
                                    raise UnsafeArchiveError(
                                        "更新ZIPの展開サイズが大きすぎます"
                                    )
                                output.write(chunk)
                    except RuntimeError as error:
                        raise UnsafeArchiveError(
                            "暗号化された更新ZIPは利用できません"
                        ) from error
                if extracted_size != sum(
                    entry.file_size for entry in entries if not entry.is_dir()
                ):
                    raise UnsafeArchiveError("更新ZIPを完全に展開できませんでした")
        except zipfile.BadZipFile as error:
            raise UnsafeArchiveError("更新ファイルは有効なZIPではありません") from error

        children = list(destination.iterdir())
        if (
            len(children) == 1
            and children[0].name == "PoseCare"
            and children[0].is_dir()
            and (children[0] / APPLICATION_EXECUTABLE).is_file()
            and (children[0] / INSTALL_MANIFEST_NAME).is_file()
        ):
            _assert_directory_root_safe(children[0], "更新ZIPのPoseCareフォルダー")
            return children[0]
        raise UnsafeArchiveError(
            "更新ZIPは単一のPoseCareフォルダーをrootに持つ必要があります"
        )

    def _download_request(self, url: str) -> urllib.request.Request:
        _validate_download_url(url)
        return urllib.request.Request(
            url,
            headers={
                "Accept": "application/octet-stream",
                "User-Agent": f"PoseCare/{self.current_build.version}",
            },
        )

    @staticmethod
    def _report(
        callback: ProgressCallback | None,
        stage: str,
        percent: int,
        message: str,
    ) -> None:
        if callback is None:
            return
        callback(UpdateProgress(stage, max(0, min(100, percent)), message))


def _optional_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _asset_url(asset: Mapping[str, Any], name: str) -> str:
    url = asset.get("browser_download_url")
    if not isinstance(url, str):
        raise ReleaseFormatError(f"{name}のダウンロードURLがありません")
    _validate_download_url(url)
    return url


def _validate_download_url(url: str) -> None:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").casefold()
    trusted = hostname in _TRUSTED_DOWNLOAD_HOSTS or hostname.endswith(
        ".githubusercontent.com"
    )
    if parsed.scheme != "https" or not trusted or parsed.username or parsed.password:
        raise ReleaseFormatError("更新ファイルのダウンロードURLが安全ではありません")


def _ensure_success_response(response: Any) -> None:
    status = getattr(response, "status", None)
    if status is None and hasattr(response, "getcode"):
        status = response.getcode()
    if status is not None and not 200 <= int(status) < 300:
        raise UpdateNetworkError(f"GitHubがHTTP {status}を返しました")


def _response_content_length(response: Any) -> int | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    value = headers.get("Content-Length")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise UpdateIntegrityError("更新ファイルのContent-Lengthが不正です")


def _network_error_detail(error: BaseException) -> str:
    reason = getattr(error, "reason", None)
    return str(reason or error)


def _verify_install_tree(
    root: Path,
    *,
    release: ReleaseInfo | None,
    verify_hashes: bool,
    expected_manifest_sha256: str | None = None,
) -> InstallManifest:
    root = Path(os.path.abspath(root))
    files, directories = _enumerate_install_tree(root)
    manifest_path = files.get(INSTALL_MANIFEST_NAME)
    if manifest_path is None:
        raise UpdateIntegrityError(
            f"{INSTALL_MANIFEST_NAME}がないため専用PoseCareフォルダーと確認できません"
        )
    manifest = _parse_install_manifest(manifest_path)
    if expected_manifest_sha256 is not None and not hmac.compare_digest(
        manifest.sha256, expected_manifest_sha256
    ):
        raise UpdateIntegrityError(
            "install manifestが準備後に変更されたため更新を中止しました"
        )

    manifest_files = {str(entry.path) for entry in manifest.entries}
    required_files = {APPLICATION_EXECUTABLE, EMBEDDED_RELEASE_PATH}
    missing_required = required_files - manifest_files
    if missing_required:
        raise UpdateIntegrityError(
            "install manifestにPoseCareの必須ファイルがありません: "
            + ", ".join(sorted(missing_required))
        )
    expected_files = manifest_files | {INSTALL_MANIFEST_NAME}
    actual_files = set(files)
    if actual_files != expected_files:
        raise UpdateIntegrityError(
            _file_set_error("ファイル", expected_files, actual_files)
        )

    expected_directories = _manifest_parent_directories(expected_files)
    if directories != expected_directories:
        raise UpdateIntegrityError(
            _file_set_error("フォルダー", expected_directories, directories)
        )

    if verify_hashes:
        for entry in manifest.entries:
            actual_sha256 = _sha256_file(files[str(entry.path)])
            if not hmac.compare_digest(actual_sha256, entry.sha256):
                raise UpdateIntegrityError(
                    f"更新payloadのSHA-256が一致しません: {entry.path}"
                )

    if release is not None:
        metadata = _read_strict_json_file(
            files[EMBEDDED_RELEASE_PATH],
            _MAX_RELEASE_METADATA_BYTES,
            "埋め込みrelease.json",
        )
        if not isinstance(metadata, Mapping):
            raise UpdateIntegrityError("埋め込みrelease.jsonの形式が正しくありません")
        tag = metadata.get("tag")
        version = metadata.get("version")
        if tag != release.tag or version != release.version:
            raise UpdateIntegrityError(
                "埋め込みrelease.jsonがGitHub Releaseと一致しません"
            )
    return manifest


def _parse_install_manifest(path: Path) -> InstallManifest:
    payload, raw = _read_strict_json_file(
        path,
        _MAX_MANIFEST_BYTES,
        "install manifest",
        include_raw=True,
    )
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema_version",
        "product",
        "files",
    }:
        raise UpdateIntegrityError("install manifestのtop-level構造が正しくありません")
    if (
        type(payload["schema_version"]) is not int
        or payload["schema_version"] != INSTALL_MANIFEST_SCHEMA_VERSION
        or payload["product"] != INSTALL_MANIFEST_PRODUCT
        or not isinstance(payload["files"], list)
        or not 0 < len(payload["files"]) <= _MAX_ARCHIVE_ENTRIES
    ):
        raise UpdateIntegrityError("install manifestの識別情報が正しくありません")

    entries: list[InstallManifestEntry] = []
    seen_paths: set[str] = set()
    for value in payload["files"]:
        if not isinstance(value, Mapping) or set(value) != {"path", "sha256"}:
            raise UpdateIntegrityError("install manifestのfile entryが正しくありません")
        path_value = value["path"]
        digest = value["sha256"]
        if not isinstance(path_value, str) or not isinstance(digest, str):
            raise UpdateIntegrityError("install manifestのfile entryが正しくありません")
        relative = _safe_manifest_path(path_value)
        collision_key = path_value.casefold()
        if collision_key in seen_paths:
            raise UpdateIntegrityError(
                "install manifestに大文字小文字が重複するpathがあります"
            )
        seen_paths.add(collision_key)
        if path_value.casefold() == INSTALL_MANIFEST_NAME.casefold():
            raise UpdateIntegrityError("install manifest自身をfilesへ含めることはできません")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise UpdateIntegrityError("install manifestのSHA-256が正しくありません")
        entries.append(InstallManifestEntry(relative, digest))
    return InstallManifest(tuple(entries), hashlib.sha256(raw).hexdigest())


def _read_strict_json_file(
    path: Path,
    maximum_bytes: int,
    description: str,
    *,
    include_raw: bool = False,
) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise UpdateIntegrityError(f"{description}を読み取れません: {error}") from error
    if not raw or len(raw) > maximum_bytes:
        raise UpdateIntegrityError(f"{description}のサイズが正しくありません")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise UpdateIntegrityError(f"{description}は有効なJSONではありません") from error
    return (payload, raw) if include_raw else payload


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _safe_manifest_path(value: str) -> PurePosixPath:
    if "\\" in value:
        raise UpdateIntegrityError("install manifestのpathはforward slash形式が必要です")
    try:
        relative = _safe_relative_path(value)
    except UnsafeArchiveError as error:
        raise UpdateIntegrityError(f"install manifestのpathが不正です: {value}") from error
    if str(relative) != value:
        raise UpdateIntegrityError(f"install manifestのpathがcanonicalではありません: {value}")
    return relative


def _enumerate_install_tree(root: Path) -> tuple[dict[str, Path], set[str]]:
    _assert_directory_root_safe(root, "PoseCareフォルダー")
    files: dict[str, Path] = {}
    directories: set[str] = set()
    seen_casefold: set[str] = set()
    pending: list[tuple[Path, PurePosixPath | None]] = [(root, None)]
    try:
        while pending:
            directory, prefix = pending.pop()
            with os.scandir(directory) as iterator:
                children = sorted(iterator, key=lambda entry: entry.name.casefold())
            for child in children:
                relative = (
                    PurePosixPath(child.name)
                    if prefix is None
                    else prefix / child.name
                )
                relative_text = str(relative)
                _safe_manifest_path(relative_text)
                collision_key = relative_text.casefold()
                if collision_key in seen_casefold:
                    raise UpdateIntegrityError(
                        "PoseCareフォルダーに大文字小文字が重複するpathがあります"
                    )
                seen_casefold.add(collision_key)
                child_stat = child.stat(follow_symlinks=False)
                if _stat_is_reparse(child_stat) or stat.S_ISLNK(child_stat.st_mode):
                    raise UpdateIntegrityError(
                        f"PoseCareフォルダーにreparse pointがあります: {relative_text}"
                    )
                child_path = Path(child.path)
                if stat.S_ISDIR(child_stat.st_mode):
                    directories.add(relative_text)
                    pending.append((child_path, relative))
                elif stat.S_ISREG(child_stat.st_mode):
                    files[relative_text] = child_path
                else:
                    raise UpdateIntegrityError(
                        f"PoseCareフォルダーに特殊ファイルがあります: {relative_text}"
                    )
    except OSError as error:
        raise UpdateIntegrityError(
            f"PoseCareフォルダーを検証できませんでした: {error}"
        ) from error
    return files, directories


def _assert_directory_root_safe(path: Path, description: str) -> None:
    try:
        value = path.lstat()
    except OSError as error:
        raise UpdateIntegrityError(f"{description}を確認できません: {error}") from error
    if (
        not stat.S_ISDIR(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or _stat_is_reparse(value)
    ):
        raise UpdateIntegrityError(f"{description}は通常フォルダーではありません")


def _stat_is_reparse(value: os.stat_result) -> bool:
    attributes = getattr(value, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    return bool(attributes & reparse_flag)


def _manifest_parent_directories(paths: set[str]) -> set[str]:
    directories: set[str] = set()
    for value in paths:
        parent = PurePosixPath(value).parent
        while parent != PurePosixPath("."):
            directories.add(str(parent))
            parent = parent.parent
    return directories


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        value = path.lstat()
        if (
            not stat.S_ISREG(value.st_mode)
            or stat.S_ISLNK(value.st_mode)
            or _stat_is_reparse(value)
        ):
            raise UpdateIntegrityError(f"通常ファイルではありません: {path.name}")
        with path.open("rb") as stream:
            while chunk := stream.read(_DOWNLOAD_CHUNK_BYTES):
                digest.update(chunk)
    except OSError as error:
        raise UpdateIntegrityError(f"ファイルを検証できません: {path.name}: {error}") from error
    return digest.hexdigest()


def _file_set_error(label: str, expected: set[str], actual: set[str]) -> str:
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    details: list[str] = []
    if missing:
        details.append("不足=" + ", ".join(missing[:5]))
    if unknown:
        details.append("未知=" + ", ".join(unknown[:5]))
    return f"PoseCareの{label}構成がinstall manifestと一致しません（{' / '.join(details)}）"


def _safe_relative_path(value: str) -> PurePosixPath:
    normalized = value.replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("/")
        or normalized.startswith("//")
        or _WINDOWS_DRIVE_PATTERN.match(normalized)
        or "\x00" in normalized
    ):
        raise UnsafeArchiveError("不正な相対pathです")
    relative = PurePosixPath(normalized)
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise UnsafeArchiveError("不正な相対pathです")
    if len(normalized) > 240:
        raise UnsafeArchiveError("長すぎるpathです")
    for part in relative.parts:
        if (
            len(part) > 255
            or ":" in part
            or part.endswith((" ", "."))
            or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
        ):
            raise UnsafeArchiveError("Windowsで使用できない名前です")
    return relative


def _safe_archive_path(entry: zipfile.ZipInfo) -> PurePosixPath:
    original = entry.filename
    try:
        relative = _safe_relative_path(original)
    except UnsafeArchiveError as error:
        raise UnsafeArchiveError("更新ZIPに不正なパスまたは名前があります") from error
    unix_mode = (entry.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode)
    if file_type == stat.S_IFLNK or file_type not in {
        0,
        stat.S_IFREG,
        stat.S_IFDIR,
    }:
        raise UnsafeArchiveError("更新ZIPにリンクまたは特殊ファイルがあります")
    if entry.flag_bits & 0x1:
        raise UnsafeArchiveError("暗号化された更新ZIPは利用できません")
    return relative


def _is_relative_to(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _is_filesystem_root(path: Path) -> bool:
    resolved = path.resolve()
    return resolved == Path(resolved.anchor)


def _paths_overlap(first: Path, second: Path) -> bool:
    first = first.resolve()
    second = second.resolve()
    return _is_relative_to(first, second) or _is_relative_to(second, first)


def _same_volume(first: Path, second: Path) -> bool:
    first_anchor = first.resolve().anchor.casefold()
    second_anchor = second.resolve().anchor.casefold()
    return bool(first_anchor) and first_anchor == second_anchor


_UPDATE_HELPER_SCRIPT = r'''param(
    [Parameter(Mandatory = $true)][int]$PoseCareProcessId,
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [Parameter(Mandatory = $true)][string]$PayloadDir,
    [Parameter(Mandatory = $true)][string]$BackupDir,
    [Parameter(Mandatory = $true)][string]$LogPath,
    [Parameter(Mandatory = $true)][string]$ExpectedManifestSha256,
    [Parameter(Mandatory = $true)][string]$ExpectedTag,
    [Parameter(Mandatory = $true)][string]$ExpectedVersion,
    [Parameter(Mandatory = $true)][string]$ReadyPath,
    [Parameter(Mandatory = $true)][string]$ReadyToken
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$ManifestName = "PoseCare.install.json"
$ManifestProduct = "PoseCare.Desktop"
$EmbeddedReleasePath = "_internal/pose_care/release.json"
$started = $null

function Write-UpdateLog([string]$Message) {
    try {
        $timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
        Add-Content -LiteralPath $LogPath -Value "$timestamp $Message" -Encoding UTF8
    }
    catch {
        # Logging is best effort and must never block replacement or rollback.
    }
}

function Assert-ExactProperties($Value, [string[]]$Expected, [string]$Description) {
    if ($null -eq $Value) {
        throw "$Description is null."
    }
    $names = @($Value.PSObject.Properties | ForEach-Object { $_.Name })
    if ($names.Count -ne $Expected.Count) {
        throw "$Description has unexpected properties."
    }
    foreach ($name in $Expected) {
        if (-not ($names -ccontains $name)) {
            throw "$Description is missing property $name."
        }
    }
}

function Assert-SafeRelativePath([object]$Value) {
    if (-not ($Value -is [string]) -or [string]::IsNullOrWhiteSpace($Value)) {
        throw "Manifest path is not a string."
    }
    if (
        $Value.Contains("\") -or
        $Value.StartsWith("/") -or
        $Value -match '^[A-Za-z]:' -or
        $Value.Contains([char]0) -or
        $Value.Length -gt 240
    ) {
        throw "Unsafe manifest path: $Value"
    }
    $reserved = @("CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9")
    $parts = @($Value.Split('/'))
    foreach ($part in $parts) {
        if (
            [string]::IsNullOrEmpty($part) -or
            $part -eq "." -or
            $part -eq ".." -or
            $part.Length -gt 255 -or
            $part.Contains(":") -or
            $part.EndsWith(" ") -or
            $part.EndsWith(".")
        ) {
            throw "Unsafe manifest path: $Value"
        }
        $baseName = $part.Split('.')[0].ToUpperInvariant()
        if ($reserved -contains $baseName) {
            throw "Reserved Windows path in manifest: $Value"
        }
    }
}

function Get-Sha256([string]$Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try {
        $bytes = $algorithm.ComputeHash($stream)
        return ([BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $stream.Dispose()
        $algorithm.Dispose()
    }
}

function Get-InstallSnapshot([string]$Root) {
    $rootItem = Get-Item -LiteralPath $Root -Force
    if (
        -not $rootItem.PSIsContainer -or
        (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
    ) {
        throw "Install root is not a normal directory: $Root"
    }
    $rootPrefix = $rootItem.FullName.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    $pending = New-Object 'System.Collections.Generic.Stack[System.IO.DirectoryInfo]'
    $pending.Push([IO.DirectoryInfo]$rootItem)
    $files = New-Object 'System.Collections.Generic.List[string]'
    $directories = New-Object 'System.Collections.Generic.List[string]'
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    while ($pending.Count -gt 0) {
        $directory = $pending.Pop()
        foreach ($item in @(Get-ChildItem -LiteralPath $directory.FullName -Force)) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Reparse point found in install tree: $($item.FullName)"
            }
            $fullName = [IO.Path]::GetFullPath($item.FullName)
            if (-not $fullName.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Item escaped install root: $fullName"
            }
            $relative = $fullName.Substring($rootPrefix.Length).Replace("\", "/")
            Assert-SafeRelativePath $relative
            if (-not $seen.Add($relative)) {
                throw "Case-insensitive duplicate path in install tree: $relative"
            }
            if ($item.PSIsContainer) {
                $directories.Add($relative)
                $pending.Push([IO.DirectoryInfo]$item)
            }
            elseif ($item -is [IO.FileInfo]) {
                $files.Add($relative)
            }
            else {
                throw "Special filesystem item in install tree: $relative"
            }
        }
    }
    return [pscustomobject]@{ Files = $files; Directories = $directories }
}

function Read-InstallManifest([string]$Root) {
    $manifestPath = Join-Path $Root $ManifestName
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Install manifest is missing: $manifestPath"
    }
    if ((Get-Item -LiteralPath $manifestPath -Force).Length -gt 8388608) {
        throw "Install manifest is too large."
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-ExactProperties $manifest @("schema_version", "product", "files") "Install manifest"
    $schema = $manifest.schema_version
    if (
        -not (($schema -is [int]) -or ($schema -is [long])) -or
        [long]$schema -ne 1 -or
        $manifest.product -cne $ManifestProduct -or
        -not ($manifest.files -is [System.Array])
    ) {
        throw "Install manifest identity is invalid."
    }
    $values = @($manifest.files)
    if ($values.Count -eq 0 -or $values.Count -gt 10000) {
        throw "Install manifest file count is invalid."
    }
    $entries = New-Object 'System.Collections.Generic.List[object]'
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($value in $values) {
        Assert-ExactProperties $value @("path", "sha256") "Install manifest entry"
        Assert-SafeRelativePath $value.path
        if ($value.path -ceq $ManifestName -or $value.path -ieq $ManifestName) {
            throw "Install manifest must not list itself."
        }
        if (-not $seen.Add([string]$value.path)) {
            throw "Duplicate manifest path: $($value.path)"
        }
        if (-not ($value.sha256 -is [string]) -or $value.sha256 -cnotmatch '^[0-9a-f]{64}$') {
            throw "Invalid SHA-256 for manifest path $($value.path)."
        }
        $entries.Add([pscustomobject]@{ Path = [string]$value.path; Sha256 = [string]$value.sha256 })
    }
    $pathSet = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($entry in $entries) { [void]$pathSet.Add($entry.Path) }
    if (-not $pathSet.Contains("PoseCare.exe") -or -not $pathSet.Contains($EmbeddedReleasePath)) {
        throw "Install manifest is missing required PoseCare files."
    }
    $digest = Get-Sha256 $manifestPath
    return [pscustomobject]@{ Entries = $entries; Digest = $digest }
}

function Get-ExpectedDirectories([System.Collections.IEnumerable]$Paths) {
    $result = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($pathValue in $Paths) {
        $path = [string]$pathValue
        $separator = $path.LastIndexOf('/')
        while ($separator -ge 0) {
            $parent = $path.Substring(0, $separator)
            [void]$result.Add($parent)
            $separator = $parent.LastIndexOf('/')
        }
    }
    return $result
}

function Assert-ExactSet([System.Collections.IEnumerable]$Actual, [System.Collections.IEnumerable]$Expected, [string]$Description) {
    $actualSet = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    $actualInsensitive = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($value in $Actual) {
        if (-not $actualInsensitive.Add([string]$value)) {
            throw "$Description has a case-insensitive duplicate: $value"
        }
        [void]$actualSet.Add([string]$value)
    }
    $expectedSet = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($value in $Expected) { [void]$expectedSet.Add([string]$value) }
    if (-not $actualSet.SetEquals($expectedSet)) {
        throw "$Description does not match install manifest."
    }
}

function Assert-InstallTree([string]$Root, [bool]$VerifyHashes, [string]$ManifestDigest, [string]$ReleaseTag, [string]$ReleaseVersion) {
    $snapshot = Get-InstallSnapshot $Root
    $manifest = Read-InstallManifest $Root
    if ($ManifestDigest -and $manifest.Digest -cne $ManifestDigest) {
        throw "Install manifest digest changed before replacement."
    }
    $expectedFiles = New-Object 'System.Collections.Generic.List[string]'
    foreach ($entry in $manifest.Entries) { $expectedFiles.Add($entry.Path) }
    $expectedFiles.Add($ManifestName)
    Assert-ExactSet $snapshot.Files $expectedFiles "Install file set"
    $expectedDirectories = Get-ExpectedDirectories $expectedFiles
    Assert-ExactSet $snapshot.Directories $expectedDirectories "Install directory set"

    if ($VerifyHashes) {
        foreach ($entry in $manifest.Entries) {
            $filePath = Join-Path $Root $entry.Path.Replace('/', '\')
            $actualDigest = Get-Sha256 $filePath
            if ($actualDigest -cne $entry.Sha256) {
                throw "Payload hash mismatch: $($entry.Path)"
            }
        }
    }
    if ($ReleaseTag) {
        $metadataPath = Join-Path $Root $EmbeddedReleasePath.Replace('/', '\')
        if ((Get-Item -LiteralPath $metadataPath -Force).Length -gt 65536) {
            throw "Embedded release metadata is too large."
        }
        $metadata = Get-Content -LiteralPath $metadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $metadataNames = @($metadata.PSObject.Properties | ForEach-Object { $_.Name })
        if (
            -not ($metadataNames -ccontains "tag") -or
            -not ($metadataNames -ccontains "version") -or
            -not ($metadata.tag -is [string]) -or
            -not ($metadata.version -is [string]) -or
            $metadata.tag -cne $ReleaseTag -or
            $metadata.version -cne $ReleaseVersion
        ) {
            throw "Embedded release metadata does not match expected Release."
        }
    }
}

function Restore-PreviousInstall {
    if (Test-Path -LiteralPath $InstallDir) {
        Remove-Item -LiteralPath $InstallDir -Recurse -Force
    }
    if (Test-Path -LiteralPath $BackupDir) {
        Move-Item -LiteralPath $BackupDir -Destination $InstallDir
    }
}

function Stop-UpdatedProcess {
    if ($null -eq $started) { return }
    try {
        $started.Refresh()
        if (-not $started.HasExited) {
            Stop-Process -Id $started.Id -Force
            Wait-Process -Id $started.Id -Timeout 15 -ErrorAction SilentlyContinue
        }
    }
    catch {
        Write-UpdateLog "Could not stop failed updated process: $($_.Exception.Message)"
    }
}

try {
    Write-UpdateLog "Waiting for PoseCare process $PoseCareProcessId"
    Wait-Process -Id $PoseCareProcessId -Timeout 90 -ErrorAction SilentlyContinue
    if (Get-Process -Id $PoseCareProcessId -ErrorAction SilentlyContinue) {
        throw "PoseCare did not exit within 90 seconds."
    }
    if ((Split-Path -Leaf $InstallDir) -ine "PoseCare") {
        throw "Install directory must be named PoseCare."
    }
    if (Test-Path -LiteralPath $BackupDir) {
        throw "The backup directory already exists."
    }
    $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    if ((Split-Path -Parent ([IO.Path]::GetFullPath($ReadyPath))) -cne ([IO.Path]::GetFullPath($scriptDirectory))) {
        throw "Ready handshake path is outside updater workspace."
    }
    if ([IO.Path]::GetPathRoot($InstallDir) -ine [IO.Path]::GetPathRoot($PayloadDir)) {
        throw "Install and payload are on different volumes."
    }

    # Validate both complete trees after the old process released every file.
    Assert-InstallTree $InstallDir $false "" "" ""
    Assert-InstallTree $PayloadDir $true $ExpectedManifestSha256 $ExpectedTag $ExpectedVersion

    Write-UpdateLog "Moving current installation to backup"
    Move-Item -LiteralPath $InstallDir -Destination $BackupDir
    try {
        Write-UpdateLog "Moving verified payload into place"
        Move-Item -LiteralPath $PayloadDir -Destination $InstallDir
        $newExecutable = Join-Path $InstallDir "PoseCare.exe"
        if (Test-Path -LiteralPath $ReadyPath) {
            Remove-Item -LiteralPath $ReadyPath -Force
        }

        Write-UpdateLog "Starting updated PoseCare"
        [Environment]::SetEnvironmentVariable("POSE_CARE_UPDATE_READY_FILE", $ReadyPath, "Process")
        [Environment]::SetEnvironmentVariable("POSE_CARE_UPDATE_READY_TOKEN", $ReadyToken, "Process")
        [Environment]::SetEnvironmentVariable("POSE_CARE_UPDATE_EXPECTED_TAG", $ExpectedTag, "Process")
        try {
            $started = Start-Process -FilePath $newExecutable -WorkingDirectory $InstallDir -PassThru
        }
        finally {
            [Environment]::SetEnvironmentVariable("POSE_CARE_UPDATE_READY_FILE", $null, "Process")
            [Environment]::SetEnvironmentVariable("POSE_CARE_UPDATE_READY_TOKEN", $null, "Process")
            [Environment]::SetEnvironmentVariable("POSE_CARE_UPDATE_EXPECTED_TAG", $null, "Process")
        }
        Write-UpdateLog "Started updated PoseCare pid=$($started.Id)"

        $readyReceived = $false
        $readyDeadline = [DateTime]::UtcNow.AddSeconds(60)
        while ([DateTime]::UtcNow -lt $readyDeadline) {
            $started.Refresh()
            if ($started.HasExited) {
                throw "Updated PoseCare exited before readiness (code $($started.ExitCode))."
            }
            if (Test-Path -LiteralPath $ReadyPath -PathType Leaf) {
                $ready = Get-Content -LiteralPath $ReadyPath -Raw -Encoding UTF8 | ConvertFrom-Json
                Assert-ExactProperties $ready @("schema_version", "token", "tag", "pid") "Ready handshake"
                if (
                    -not (($ready.schema_version -is [int]) -or ($ready.schema_version -is [long])) -or
                    [long]$ready.schema_version -ne 1 -or
                    -not ($ready.token -is [string]) -or
                    -not ($ready.tag -is [string]) -or
                    -not (($ready.pid -is [int]) -or ($ready.pid -is [long])) -or
                    $ready.token -cne $ReadyToken -or
                    $ready.tag -cne $ExpectedTag -or
                    [long]$ready.pid -ne [long]$started.Id
                ) {
                    throw "Ready handshake does not match the started PoseCare process."
                }
                $readyReceived = $true
                break
            }
            Start-Sleep -Milliseconds 200
        }
        if (-not $readyReceived) {
            throw "Updated PoseCare did not report readiness within 60 seconds."
        }

        $survivalDeadline = [DateTime]::UtcNow.AddSeconds(2)
        while ([DateTime]::UtcNow -lt $survivalDeadline) {
            $started.Refresh()
            if ($started.HasExited) {
                throw "Updated PoseCare exited during the readiness grace period (code $($started.ExitCode))."
            }
            Start-Sleep -Milliseconds 100
        }
    }
    catch {
        Write-UpdateLog "Replacement failed; stopping new process and restoring backup: $($_.Exception.Message)"
        Stop-UpdatedProcess
        Restore-PreviousInstall
        throw
    }

    Write-UpdateLog "Update completed successfully"
    try { Remove-Item -LiteralPath $ReadyPath -Force -ErrorAction SilentlyContinue } catch {}
    try {
        Remove-Item -LiteralPath $BackupDir -Recurse -Force
    }
    catch {
        Write-UpdateLog "Could not remove backup: $($_.Exception.Message)"
    }
    exit 0
}
catch {
    Write-UpdateLog "Update failed: $($_.Exception.Message)"
    Stop-UpdatedProcess
    try {
        if (Test-Path -LiteralPath $BackupDir) {
            if (Test-Path -LiteralPath $InstallDir) {
                Remove-Item -LiteralPath $InstallDir -Recurse -Force
            }
            Move-Item -LiteralPath $BackupDir -Destination $InstallDir
        }
        if (
            -not (Get-Process -Id $PoseCareProcessId -ErrorAction SilentlyContinue) -and
            (Test-Path -LiteralPath (Join-Path $InstallDir "PoseCare.exe") -PathType Leaf)
        ) {
            Start-Process -FilePath (Join-Path $InstallDir "PoseCare.exe") -WorkingDirectory $InstallDir
        }
    }
    catch {
        Write-UpdateLog "Recovery could not be completed: $($_.Exception.Message)"
    }
    exit 1
}
'''
