from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]


def test_installer_is_fixed_to_per_user_managed_location():
    script = (PROJECT_ROOT / "scripts" / "installer.iss").read_text(encoding="utf-8")

    assert "DefaultDirName={localappdata}\\Programs\\PoseCare" in script
    assert "DisableDirPage=yes" in script
    assert "UsePreviousAppDir=no" in script
    assert "PrivilegesRequired=lowest" in script
    assert "UninstallFilesDir={localappdata}\\PoseCare\\uninstall" in script
    assert "portablemode" not in script.casefold()


def test_release_publishes_setup_and_keeps_zip_for_internal_updates():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert '"release\\PoseCareSetup-windows-x64.exe"' in workflow
    assert '"release\\PoseCareSetup-windows-x64.exe.sha256"' in workflow
    assert '"release\\PoseCare-update-windows-x64.zip"' in workflow
    assert "reserved for PoseCare's built-in updater" in workflow
    assert "extract it" not in workflow
    assert "PoseCare-windows-x64.zip" not in workflow


def test_legacy_adjacent_update_workspace_is_removed():
    updater = (PROJECT_ROOT / "pose_care" / "updater.py").read_text(encoding="utf-8")
    application = (PROJECT_ROOT / "pose_care" / "app.py").read_text(encoding="utf-8")

    assert ".PoseCare.updates" not in updater
    assert ".PoseCare.updates" not in application
