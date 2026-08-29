from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import time
import urllib.error
import zipfile
from pathlib import Path

import pytest

from pose_care.updater import (
    APPLICATION_EXECUTABLE,
    CHECKSUM_ASSET_NAME,
    EMBEDDED_RELEASE_PATH,
    INSTALL_MANIFEST_NAME,
    RELEASE_ASSET_NAME,
    ApplicationUpdater,
    BuildInfo,
    ReleaseFormatError,
    UnsafeArchiveError,
    UpdateIntegrityError,
    UpdateNetworkError,
    UpdateNotSupportedError,
    _WINDOWS_UPDATE_CREATION_FLAGS,
    is_release_newer,
    load_build_info,
    parse_release_tag,
)


ARCHIVE_URL = (
    "https://github.com/Yuubinkyokutyou/pose-care/releases/download/"
    f"v0.2.0-build.12.1/{RELEASE_ASSET_NAME}"
)
CHECKSUM_URL = (
    "https://github.com/Yuubinkyokutyou/pose-care/releases/download/"
    f"v0.2.0-build.12.1/{CHECKSUM_ASSET_NAME}"
)


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, *, status: int = 200, content_length=True):
        super().__init__(body)
        self.status = status
        self.headers = {}
        if content_length:
            self.headers["Content-Length"] = str(len(body))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class FakeUrlOpen:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def __call__(self, request, *, timeout):
        self.requests.append((request, timeout))
        response = self.responses[request.full_url]
        if isinstance(response, BaseException):
            raise response
        status = 200
        body = response
        if isinstance(response, tuple):
            status, body = response
        return FakeResponse(body, status=status)


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
    return output.getvalue()


def _release_metadata(tag: str) -> bytes:
    version = tag.removeprefix("v").split("-build.", 1)[0]
    return json.dumps(
        {
            "schema_version": 1,
            "version": version,
            "tag": tag,
            "commit": "a" * 40,
            "asset": RELEASE_ASSET_NAME,
            "built_at": "2026-08-23T12:00:00Z",
        },
        separators=(",", ":"),
    ).encode()


def _manifest_bytes(entries: dict[str, bytes], *, mutate=None) -> bytes:
    manifest = {
        "schema_version": 1,
        "product": "PoseCare.Desktop",
        "files": [
            {"path": path, "sha256": hashlib.sha256(body).hexdigest()}
            for path, body in sorted(entries.items())
        ],
    }
    if mutate is not None:
        mutate(manifest)
    return json.dumps(manifest, separators=(",", ":")).encode()


def _install_archive(
    entries: dict[str, bytes],
    *,
    tag: str = "v0.2.0-build.12.1",
    wrapper: bool = True,
    manifest_mutator=None,
    exclude_from_manifest: set[str] | None = None,
    extra_zip_entries: dict[str, bytes] | None = None,
) -> bytes:
    payload = dict(entries)
    payload.setdefault(EMBEDDED_RELEASE_PATH, _release_metadata(tag))
    manifest_entries = {
        path: body
        for path, body in payload.items()
        if path not in (exclude_from_manifest or set())
    }
    payload[INSTALL_MANIFEST_NAME] = _manifest_bytes(
        manifest_entries, mutate=manifest_mutator
    )
    prefix = "PoseCare/" if wrapper else ""
    archive_entries = {f"{prefix}{path}": body for path, body in payload.items()}
    archive_entries.update(extra_zip_entries or {})
    return _zip_bytes(archive_entries)


def _write_install_tree(
    root: Path,
    entries: dict[str, bytes],
    *,
    tag: str = "v0.2.0-build.11.1",
) -> None:
    payload = dict(entries)
    payload.setdefault(EMBEDDED_RELEASE_PATH, _release_metadata(tag))
    for relative, body in payload.items():
        target = root.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    (root / INSTALL_MANIFEST_NAME).write_bytes(_manifest_bytes(payload))


def _release_payload(archive: bytes, *, tag="v0.2.0-build.12.1") -> bytes:
    return json.dumps(
        {
            "tag_name": tag,
            "name": "PoseCare automated build",
            "body": "Changes",
            "html_url": f"https://github.com/example/releases/tag/{tag}",
            "published_at": "2026-08-23T12:00:00Z",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": RELEASE_ASSET_NAME,
                    "size": len(archive),
                    "browser_download_url": ARCHIVE_URL,
                },
                {
                    "name": CHECKSUM_ASSET_NAME,
                    "size": 100,
                    "browser_download_url": CHECKSUM_URL,
                },
            ],
        }
    ).encode()


def _checked_updater(tmp_path, archive, *, tag="v0.2.0-build.12.1"):
    digest = hashlib.sha256(archive).hexdigest()
    api_url = "https://api.github.test/latest"
    opener = FakeUrlOpen(
        {
            api_url: _release_payload(archive, tag=tag),
            CHECKSUM_URL: f"{digest}  {RELEASE_ASSET_NAME}\n".encode(),
            ARCHIVE_URL: archive,
        }
    )
    updater = ApplicationUpdater(
        current_build=BuildInfo("v0.2.0-build.11.1", "0.2.0"),
        latest_release_url=api_url,
        updates_root=tmp_path / "updates",
        urlopen=opener,
    )
    return updater, opener, updater.check_for_update().latest


@pytest.mark.parametrize(
    ("latest", "current", "expected"),
    [
        ("v0.2.0-build.12.1", "v0.2.0-build.11.1", True),
        ("v0.2.0-build.12.2", "v0.2.0-build.12.1", True),
        ("v0.2.0-build.12.1", "v0.2.0-build.12.1", False),
        ("v0.2.0-build.11.1", "v0.2.0-build.12.1", False),
        ("v0.2.0-build.1.1", "v0.2.0", True),
        ("v0.3.0-build.1.1", "v0.2.0-build.999.1", True),
    ],
)
def test_release_tags_compare_package_and_actions_build_ids(
    latest, current, expected
):
    assert is_release_newer(latest, current) is expected


def test_parse_release_tag_rejects_unexpected_or_non_numeric_tags():
    with pytest.raises(ReleaseFormatError):
        parse_release_tag("nightly-latest")
    with pytest.raises(ReleaseFormatError):
        parse_release_tag("v0.2.0-build.run.attempt")


def test_load_build_info_reads_embedded_release_identity(tmp_path):
    path = tmp_path / "release.json"
    path.write_text(
        json.dumps(
            {
                "tag": "v0.2.0-build.123.2",
                "version": "0.2.0",
                "commit": "abc123",
                "built_at": "2026-08-23T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    build = load_build_info(path)

    assert build.tag == "v0.2.0-build.123.2"
    assert build.version == "0.2.0"
    assert build.commit == "abc123"


def test_load_build_info_falls_back_for_missing_or_inconsistent_file(tmp_path):
    missing = load_build_info(tmp_path / "missing.json")
    assert missing.tag.startswith("v")
    path = tmp_path / "release.json"
    path.write_text(
        '{"tag":"v9.0.0-build.1.1","version":"0.2.0"}', encoding="utf-8"
    )
    assert load_build_info(path) == missing


def test_check_for_update_reads_exact_assets_and_reports_same_version_build(tmp_path):
    archive = _zip_bytes({APPLICATION_EXECUTABLE: b"new exe", "_internal/app.dat": b"x"})
    updater, opener, _ = _checked_updater(tmp_path, archive)
    progress = []

    result = updater.check_for_update(progress.append)

    assert result.update_available
    assert result.current.tag == "v0.2.0-build.11.1"
    assert result.latest.tag == "v0.2.0-build.12.1"
    assert result.latest.archive_url == ARCHIVE_URL
    assert progress[-1].stage == "checking"
    assert progress[-1].percent == 100
    api_request, timeout = opener.requests[-1]
    assert api_request.headers["X-github-api-version"] == "2026-03-10"
    assert timeout == 30.0


def test_check_for_update_reports_current_build_when_tags_match(tmp_path):
    archive = _zip_bytes({APPLICATION_EXECUTABLE: b"new exe"})
    api_url = "https://api.github.test/latest"
    updater = ApplicationUpdater(
        current_build=BuildInfo("v0.2.0-build.12.1", "0.2.0"),
        latest_release_url=api_url,
        updates_root=tmp_path,
        urlopen=FakeUrlOpen({api_url: _release_payload(archive)}),
    )

    result = updater.check_for_update()

    assert not result.update_available


def test_check_for_update_rejects_missing_asset_and_untrusted_download_url(tmp_path):
    archive = _zip_bytes({APPLICATION_EXECUTABLE: b"new exe"})
    api_url = "https://api.github.test/latest"
    missing_asset = json.loads(_release_payload(archive))
    missing_asset["assets"] = missing_asset["assets"][:1]
    updater = ApplicationUpdater(
        latest_release_url=api_url,
        updates_root=tmp_path,
        urlopen=FakeUrlOpen({api_url: json.dumps(missing_asset).encode()}),
    )
    with pytest.raises(ReleaseFormatError, match="検証ファイル"):
        updater.check_for_update()

    malicious = json.loads(_release_payload(archive))
    malicious["assets"][0]["browser_download_url"] = "https://attacker.test/app.zip"
    updater = ApplicationUpdater(
        latest_release_url=api_url,
        updates_root=tmp_path,
        urlopen=FakeUrlOpen({api_url: json.dumps(malicious).encode()}),
    )
    with pytest.raises(ReleaseFormatError, match="安全ではありません"):
        updater.check_for_update()


def test_check_for_update_wraps_network_error(tmp_path):
    api_url = "https://api.github.test/latest"
    updater = ApplicationUpdater(
        latest_release_url=api_url,
        updates_root=tmp_path,
        urlopen=FakeUrlOpen(
            {api_url: urllib.error.URLError("temporary network failure")}
        ),
    )

    with pytest.raises(UpdateNetworkError, match="temporary network failure"):
        updater.check_for_update()


def test_frozen_windows_default_workspace_is_app_data(tmp_path, monkeypatch):
    local_app_data = tmp_path / "local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    executable = tmp_path / "portable" / "PoseCare" / APPLICATION_EXECUTABLE
    updater = ApplicationUpdater(
        platform_name="win32",
        frozen=True,
        executable_path=executable,
    )

    assert updater.updates_root == local_app_data / "PoseCare" / "updates"


def test_frozen_windows_default_workspace_uses_sibling_on_another_volume(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    monkeypatch.setattr("pose_care.updater._same_volume", lambda *_: False)
    executable = tmp_path / "portable" / "PoseCare" / APPLICATION_EXECUTABLE

    updater = ApplicationUpdater(
        platform_name="win32",
        frozen=True,
        executable_path=executable,
    )

    assert updater.updates_root == tmp_path / "portable" / ".PoseCare.updates"


def test_prepare_update_downloads_verifies_and_extracts_payload(tmp_path):
    archive = _install_archive(
        {
            APPLICATION_EXECUTABLE: b"new executable",
            "_internal/Qt6Core.dll": b"dll",
        }
    )
    updater, _, release = _checked_updater(tmp_path, archive)
    progress = []

    prepared = updater.prepare_update(release, progress.append)

    assert not prepared.archive_path.exists()
    assert (prepared.payload_dir / APPLICATION_EXECUTABLE).read_bytes() == b"new executable"
    assert (prepared.payload_dir / "_internal" / "Qt6Core.dll").read_bytes() == b"dll"
    assert prepared.sha256 == hashlib.sha256(archive).hexdigest()
    assert prepared.manifest_sha256 == hashlib.sha256(
        (prepared.payload_dir / INSTALL_MANIFEST_NAME).read_bytes()
    ).hexdigest()
    assert {item.stage for item in progress} >= {
        "downloading_checksum",
        "downloading",
        "verifying",
        "extracting",
        "ready",
    }
    prepared.cleanup()
    assert not prepared.workspace.exists()


def test_prepare_update_accepts_single_posecare_wrapper_directory(tmp_path):
    archive = _install_archive(
        {
            APPLICATION_EXECUTABLE: b"new executable",
            "_internal/app.dat": b"data",
        }
    )
    updater, _, release = _checked_updater(tmp_path, archive)

    prepared = updater.prepare_update(release)

    assert prepared.payload_dir.name == "PoseCare"
    assert (prepared.payload_dir / APPLICATION_EXECUTABLE).is_file()


def test_prepare_update_rejects_flat_payload_without_posecare_wrapper(tmp_path):
    archive = _install_archive(
        {APPLICATION_EXECUTABLE: b"new executable"}, wrapper=False
    )
    updater, _, release = _checked_updater(tmp_path, archive)

    with pytest.raises(UnsafeArchiveError, match="PoseCareフォルダー"):
        updater.prepare_update(release)


def test_prepare_update_rejects_manifest_file_hash_mismatch(tmp_path):
    def corrupt_hash(manifest):
        manifest["files"][0]["sha256"] = "0" * 64

    archive = _install_archive(
        {APPLICATION_EXECUTABLE: b"new executable"},
        manifest_mutator=corrupt_hash,
    )
    updater, _, release = _checked_updater(tmp_path, archive)

    with pytest.raises(UpdateIntegrityError, match="SHA-256"):
        updater.prepare_update(release)

    assert list((tmp_path / "updates").iterdir()) == []


def test_prepare_update_rejects_unknown_file_and_empty_directory(tmp_path):
    unknown_file = _install_archive(
        {
            APPLICATION_EXECUTABLE: b"new executable",
            "not-in-manifest.txt": b"unknown",
        },
        exclude_from_manifest={"not-in-manifest.txt"},
    )
    updater, _, release = _checked_updater(tmp_path, unknown_file)
    with pytest.raises(UpdateIntegrityError, match="ファイル構成"):
        updater.prepare_update(release)

    empty_directory = _install_archive(
        {APPLICATION_EXECUTABLE: b"new executable"},
        extra_zip_entries={"PoseCare/unknown-empty/": b""},
    )
    updater, _, release = _checked_updater(tmp_path, empty_directory)
    with pytest.raises(UpdateIntegrityError, match="フォルダー構成"):
        updater.prepare_update(release)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.dat",
        r"folder\backslash.dat",
        "CON/config.dat",
        INSTALL_MANIFEST_NAME,
    ],
)
def test_prepare_update_rejects_unsafe_manifest_paths(tmp_path, unsafe_path):
    def add_unsafe_path(manifest):
        manifest["files"].append({"path": unsafe_path, "sha256": "1" * 64})

    archive = _install_archive(
        {APPLICATION_EXECUTABLE: b"new executable"},
        manifest_mutator=add_unsafe_path,
    )
    updater, _, release = _checked_updater(tmp_path, archive)

    with pytest.raises(UpdateIntegrityError, match="manifest"):
        updater.prepare_update(release)


def test_prepare_update_rejects_case_duplicate_manifest_path(tmp_path):
    def add_case_duplicate(manifest):
        manifest["files"].append({"path": "data.TXT", "sha256": "1" * 64})

    archive = _install_archive(
        {APPLICATION_EXECUTABLE: b"new executable", "Data.txt": b"data"},
        manifest_mutator=add_case_duplicate,
    )
    updater, _, release = _checked_updater(tmp_path, archive)

    with pytest.raises(UpdateIntegrityError, match="大文字小文字"):
        updater.prepare_update(release)


def test_prepare_update_rejects_embedded_release_mismatch(tmp_path):
    archive = _install_archive(
        {
            APPLICATION_EXECUTABLE: b"new executable",
            EMBEDDED_RELEASE_PATH: _release_metadata("v0.2.0-build.999.1"),
        }
    )
    updater, _, release = _checked_updater(tmp_path, archive)

    with pytest.raises(UpdateIntegrityError, match="release.json"):
        updater.prepare_update(release)


def test_prepare_update_rejects_wrong_checksum_and_cleans_workspace(tmp_path):
    archive = _zip_bytes({APPLICATION_EXECUTABLE: b"new executable"})
    updater, opener, release = _checked_updater(tmp_path, archive)
    opener.responses[CHECKSUM_URL] = (
        f"{'0' * 64}  {RELEASE_ASSET_NAME}\n".encode()
    )

    with pytest.raises(UpdateIntegrityError, match="SHA-256"):
        updater.prepare_update(release)

    assert list((tmp_path / "updates").iterdir()) == []


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "../outside.exe",
        "/absolute/PoseCare.exe",
        r"..\outside.exe",
        "folder/file.txt:stream",
        "CON/config.dat",
    ],
)
def test_prepare_update_rejects_unsafe_archive_paths(tmp_path, unsafe_name):
    archive = _zip_bytes(
        {APPLICATION_EXECUTABLE: b"new executable", unsafe_name: b"malicious"}
    )
    updater, _, release = _checked_updater(tmp_path, archive)

    with pytest.raises(UnsafeArchiveError):
        updater.prepare_update(release)

    assert not (tmp_path / "outside.exe").exists()
    assert list((tmp_path / "updates").iterdir()) == []


def test_prepare_update_rejects_archive_symlink(tmp_path):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(APPLICATION_EXECUTABLE, b"new executable")
        link = zipfile.ZipInfo("_internal/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "../../outside")
    updater, _, release = _checked_updater(tmp_path, output.getvalue())

    with pytest.raises(UnsafeArchiveError, match="リンク"):
        updater.prepare_update(release)


def test_launch_update_is_disabled_for_source_and_non_windows_runs(tmp_path):
    archive = _install_archive({APPLICATION_EXECUTABLE: b"new executable"})
    updater, _, release = _checked_updater(tmp_path, archive)
    prepared = updater.prepare_update(release)

    with pytest.raises(UpdateNotSupportedError, match="Windows"):
        updater.launch_update(prepared)


def test_launch_update_starts_background_rollback_helper_for_frozen_app(tmp_path):
    archive = _install_archive(
        {APPLICATION_EXECUTABLE: b"new executable", "_internal/app.dat": b"new"}
    )
    updater, _, release = _checked_updater(tmp_path, archive)
    prepared = updater.prepare_update(release)
    install_dir = tmp_path / "installed" / "PoseCare"
    install_dir.mkdir(parents=True)
    executable = install_dir / APPLICATION_EXECUTABLE
    _write_install_tree(install_dir, {APPLICATION_EXECUTABLE: b"old executable"})
    launches = []
    sentinel_process = object()

    def fake_launcher(command, **kwargs):
        launches.append((command, kwargs))
        return sentinel_process

    frozen_updater = ApplicationUpdater(
        current_build=updater.current_build,
        updates_root=tmp_path / "updates",
        platform_name="win32",
        frozen=True,
        executable_path=executable,
        process_id=4242,
        process_launcher=fake_launcher,
    )
    progress = []

    result = frozen_updater.launch_update(prepared, progress.append)

    assert result.helper_process is sentinel_process
    assert result.script_path.is_file()
    script = result.script_path.read_text(encoding="utf-8-sig")
    assert "Wait-Process" in script
    assert "Restore-PreviousInstall" in script
    assert "Move-Item -LiteralPath $InstallDir -Destination $BackupDir" in script
    command, kwargs = launches[0]
    assert command[0] == "powershell.exe"
    assert command[command.index("-PoseCareProcessId") + 1] == "4242"
    assert command[command.index("-InstallDir") + 1] == str(install_dir.resolve())
    assert command[command.index("-PayloadDir") + 1] == str(
        prepared.payload_dir.resolve()
    )
    assert command[command.index("-ExpectedManifestSha256") + 1] == (
        prepared.manifest_sha256
    )
    assert command[command.index("-ExpectedTag") + 1] == prepared.release.tag
    assert command[command.index("-ReadyPath") + 1] == str(result.ready_path)
    assert command[command.index("-ReadyToken") + 1] == result.ready_token
    assert kwargs["close_fds"] is True
    assert kwargs["creationflags"] == _WINDOWS_UPDATE_CREATION_FLAGS
    assert not kwargs["creationflags"] & getattr(
        subprocess, "DETACHED_PROCESS", 0x00000008
    )
    assert kwargs["cwd"] == str(prepared.workspace.resolve())
    assert progress[-1].stage == "launching"
    assert progress[-1].percent == 100


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell regression")
def test_windows_update_creation_flags_execute_powershell_script(tmp_path):
    script_path = tmp_path / "probe.ps1"
    marker_path = tmp_path / "powershell-started.txt"
    script_path.write_text(
        "param([string]$MarkerPath)\n"
        'Set-Content -LiteralPath $MarkerPath -Value "started" -NoNewline\n',
        encoding="utf-8-sig",
    )

    process = subprocess.Popen(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-MarkerPath",
            str(marker_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=_WINDOWS_UPDATE_CREATION_FLAGS,
        cwd=str(tmp_path),
    )

    try:
        deadline = time.monotonic() + 30
        while not marker_path.exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.05)

        assert marker_path.exists(), (
            f"PowerShell exited with code {process.returncode} without running "
            "the probe script"
            if process.poll() is not None
            else "PowerShell did not run the probe script within 30 seconds"
        )
        assert marker_path.read_text(encoding="utf-8") == "started"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize("mutation", ["payload", "manifest"])
def test_launch_update_detects_prepared_payload_toctou_before_helper(
    tmp_path, mutation
):
    archive = _install_archive(
        {
            APPLICATION_EXECUTABLE: b"new executable",
            "_internal/app.dat": b"verified data",
        }
    )
    updater, _, release = _checked_updater(tmp_path, archive)
    prepared = updater.prepare_update(release)
    install_dir = tmp_path / "installed" / "PoseCare"
    install_dir.mkdir(parents=True)
    executable = install_dir / APPLICATION_EXECUTABLE
    _write_install_tree(install_dir, {APPLICATION_EXECUTABLE: b"old executable"})
    launches = []
    frozen_updater = ApplicationUpdater(
        updates_root=tmp_path / "updates",
        platform_name="win32",
        frozen=True,
        executable_path=executable,
        process_launcher=lambda *args, **kwargs: launches.append((args, kwargs)),
    )
    if mutation == "payload":
        (prepared.payload_dir / "_internal" / "app.dat").write_bytes(b"tampered")
        expected_message = "SHA-256"
    else:
        manifest_path = prepared.payload_dir / INSTALL_MANIFEST_NAME
        manifest_path.write_bytes(manifest_path.read_bytes() + b"\n")
        expected_message = "manifest"

    with pytest.raises(UpdateIntegrityError, match=expected_message):
        frozen_updater.launch_update(prepared)

    assert launches == []


def test_launch_update_rejects_shared_folder_sentinel_before_helper(tmp_path):
    archive = _install_archive({APPLICATION_EXECUTABLE: b"new executable"})
    updater, _, release = _checked_updater(tmp_path, archive)
    prepared = updater.prepare_update(release)
    install_dir = tmp_path / "Desktop" / "PoseCare"
    install_dir.mkdir(parents=True)
    executable = install_dir / APPLICATION_EXECUTABLE
    _write_install_tree(install_dir, {APPLICATION_EXECUTABLE: b"old executable"})
    (install_dir / "family-photos.shared-folder-sentinel").write_text(
        "must not be deleted", encoding="utf-8"
    )
    launches = []
    frozen_updater = ApplicationUpdater(
        updates_root=tmp_path / "updates",
        platform_name="win32",
        frozen=True,
        executable_path=executable,
        process_launcher=lambda *args, **kwargs: launches.append((args, kwargs)),
    )

    with pytest.raises(UpdateIntegrityError, match="ファイル構成"):
        frozen_updater.launch_update(prepared)

    assert launches == []
    assert (install_dir / "family-photos.shared-folder-sentinel").is_file()


def test_launch_update_requires_install_directory_named_posecare(tmp_path):
    archive = _install_archive({APPLICATION_EXECUTABLE: b"new executable"})
    updater, _, release = _checked_updater(tmp_path, archive)
    prepared = updater.prepare_update(release)
    install_dir = tmp_path / "Downloads"
    install_dir.mkdir()
    executable = install_dir / APPLICATION_EXECUTABLE
    _write_install_tree(install_dir, {APPLICATION_EXECUTABLE: b"old executable"})
    frozen_updater = ApplicationUpdater(
        updates_root=tmp_path / "updates",
        platform_name="win32",
        frozen=True,
        executable_path=executable,
        process_launcher=lambda *args, **kwargs: object(),
    )

    with pytest.raises(UpdateNotSupportedError, match="PoseCareフォルダー"):
        frozen_updater.launch_update(prepared)


def test_launch_update_rejects_unexpected_executable_name(tmp_path):
    archive = _install_archive({APPLICATION_EXECUTABLE: b"new executable"})
    updater, _, release = _checked_updater(tmp_path, archive)
    prepared = updater.prepare_update(release)
    executable = tmp_path / "installed" / "python.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"not frozen app")
    frozen_updater = ApplicationUpdater(
        updates_root=tmp_path / "updates",
        platform_name="win32",
        frozen=True,
        executable_path=executable,
        process_launcher=lambda *args, **kwargs: object(),
    )

    with pytest.raises(UpdateNotSupportedError, match=APPLICATION_EXECUTABLE):
        frozen_updater.launch_update(prepared)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows updater integration")
def test_windows_helper_rolls_back_even_when_new_process_exits_zero(tmp_path):
    system_root = Path(os.environ["SystemRoot"])
    harmless_executable = system_root / "System32" / "whoami.exe"
    assert harmless_executable.is_file()
    archive = _install_archive(
        {
            APPLICATION_EXECUTABLE: harmless_executable.read_bytes(),
            "version.txt": b"new build",
            "_internal/app.dat": b"new payload",
        }
    )
    updater, _, release = _checked_updater(tmp_path, archive)
    prepared = updater.prepare_update(release)

    install_dir = tmp_path / "portable install" / "PoseCare"
    install_dir.mkdir(parents=True)
    executable = install_dir / APPLICATION_EXECUTABLE
    _write_install_tree(
        install_dir,
        {
            APPLICATION_EXECUTABLE: harmless_executable.read_bytes(),
            "version.txt": b"old build",
        },
    )
    commands = []

    def capture_launcher(command, **kwargs):
        commands.append((command, kwargs))
        return object()

    frozen_updater = ApplicationUpdater(
        current_build=updater.current_build,
        updates_root=tmp_path / "updates",
        platform_name="win32",
        frozen=True,
        executable_path=executable,
        process_id=2_000_000_000,
        process_launcher=capture_launcher,
    )
    launched = frozen_updater.launch_update(prepared)
    command, kwargs = commands[0]
    backup_dir = Path(command[command.index("-BackupDir") + 1])

    completed = subprocess.run(
        command,
        cwd=kwargs["cwd"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 1, (
        completed.stdout.decode(errors="replace"),
        completed.stderr.decode(errors="replace"),
    )
    assert (install_dir / "version.txt").read_bytes() == b"old build"
    assert not (install_dir / "_internal" / "app.dat").exists()
    assert not backup_dir.exists()
    assert not prepared.payload_dir.exists()
    log = launched.log_path.read_text(encoding="utf-8-sig")
    assert "exited before readiness (code 0)" in log
    assert "restoring backup" in log


@pytest.mark.skipif(sys.platform != "win32", reason="Windows updater integration")
def test_windows_helper_rejects_shared_folder_sentinel_added_after_launch(tmp_path):
    system_root = Path(os.environ["SystemRoot"])
    harmless_executable = system_root / "System32" / "whoami.exe"
    archive = _install_archive(
        {APPLICATION_EXECUTABLE: harmless_executable.read_bytes()}
    )
    updater, _, release = _checked_updater(tmp_path, archive)
    prepared = updater.prepare_update(release)
    install_dir = tmp_path / "shared folder" / "PoseCare"
    install_dir.mkdir(parents=True)
    executable = install_dir / APPLICATION_EXECUTABLE
    _write_install_tree(
        install_dir,
        {APPLICATION_EXECUTABLE: harmless_executable.read_bytes()},
    )
    commands = []

    def capture_launcher(command, **kwargs):
        commands.append((command, kwargs))
        return object()

    frozen_updater = ApplicationUpdater(
        current_build=updater.current_build,
        updates_root=tmp_path / "updates",
        platform_name="win32",
        frozen=True,
        executable_path=executable,
        process_id=2_000_000_000,
        process_launcher=capture_launcher,
    )
    launched = frozen_updater.launch_update(prepared)
    command, kwargs = commands[0]
    backup_dir = Path(command[command.index("-BackupDir") + 1])
    sentinel = install_dir / "shared-folder-sentinel.txt"
    sentinel.write_text("must survive", encoding="utf-8")

    completed = subprocess.run(
        command,
        cwd=kwargs["cwd"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 1
    assert sentinel.read_text(encoding="utf-8") == "must survive"
    assert prepared.payload_dir.exists()
    assert not backup_dir.exists()
    assert "Install file set does not match install manifest" in (
        launched.log_path.read_text(encoding="utf-8-sig")
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows updater integration")
def test_windows_helper_commits_after_matching_ready_handshake(tmp_path):
    system_root = Path(os.environ["SystemRoot"])
    # cmd.exe starts an interactive process with no arguments and remains alive
    # until the test terminates it, unlike modern Notepad's launcher process.
    persistent_executable = system_root / "System32" / "cmd.exe"
    old_executable = system_root / "System32" / "whoami.exe"
    assert persistent_executable.is_file()
    assert old_executable.is_file()
    archive = _install_archive(
        {
            APPLICATION_EXECUTABLE: persistent_executable.read_bytes(),
            "version.txt": b"new ready build",
        }
    )
    updater, _, release = _checked_updater(tmp_path, archive)
    prepared = updater.prepare_update(release)
    install_dir = tmp_path / "ready install" / "PoseCare"
    install_dir.mkdir(parents=True)
    executable = install_dir / APPLICATION_EXECUTABLE
    _write_install_tree(
        install_dir,
        {
            APPLICATION_EXECUTABLE: old_executable.read_bytes(),
            "version.txt": b"old build",
        },
    )
    commands = []

    def capture_launcher(command, **kwargs):
        commands.append((command, kwargs))
        return object()

    frozen_updater = ApplicationUpdater(
        current_build=updater.current_build,
        updates_root=tmp_path / "updates",
        platform_name="win32",
        frozen=True,
        executable_path=executable,
        process_id=2_000_000_000,
        process_launcher=capture_launcher,
    )
    launched = frozen_updater.launch_update(prepared)
    command, kwargs = commands[0]
    backup_dir = Path(command[command.index("-BackupDir") + 1])
    helper = subprocess.Popen(
        command,
        cwd=kwargs["cwd"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    started_pid = None
    try:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if launched.log_path.exists():
                try:
                    log = launched.log_path.read_text(encoding="utf-8-sig")
                except OSError:
                    # PowerShell's Add-Content can briefly hold an exclusive
                    # handle while the helper appends the started-process line.
                    time.sleep(0.05)
                    continue
                match = re.search(r"Started updated PoseCare pid=(\d+)", log)
                if match is not None:
                    started_pid = int(match.group(1))
                    break
            if helper.poll() is not None:
                break
            time.sleep(0.05)
        assert started_pid is not None, (
            launched.log_path.read_text(encoding="utf-8-sig")
            if launched.log_path.exists()
            else "helper produced no log"
        )

        temporary_ready = launched.ready_path.with_suffix(".tmp")
        temporary_ready.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "token": launched.ready_token,
                    "tag": launched.expected_tag,
                    "pid": started_pid,
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        temporary_ready.replace(launched.ready_path)
        stdout, stderr = helper.communicate(timeout=20)

        assert helper.returncode == 0, (
            stdout.decode(errors="replace"),
            stderr.decode(errors="replace"),
            launched.log_path.read_text(encoding="utf-8-sig"),
        )
        assert (install_dir / "version.txt").read_bytes() == b"new ready build"
        assert not backup_dir.exists()
        assert "Update completed successfully" in launched.log_path.read_text(
            encoding="utf-8-sig"
        )
    finally:
        if helper.poll() is None:
            helper.kill()
            helper.wait(timeout=5)
        if started_pid is None and launched.log_path.exists():
            # Recover the exact child PID even when the assertion above failed
            # while the log was momentarily locked, so the test never leaks a
            # copied cmd.exe process into the developer's session.
            try:
                final_log = launched.log_path.read_text(encoding="utf-8-sig")
            except OSError:
                final_log = ""
            final_match = re.search(r"Started updated PoseCare pid=(\d+)", final_log)
            if final_match is not None:
                started_pid = int(final_match.group(1))
        if started_pid is not None:
            subprocess.run(
                ["taskkill.exe", "/PID", str(started_pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
