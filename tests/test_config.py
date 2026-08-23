from pose_care.config import SettingsStore
from pose_care.models import AppSettings, PostureProfile


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    settings = AppSettings(
        camera_index=2,
        sensitivity=70,
        profiles=[
            PostureProfile.create("前のめり", [0.1, 0.2], 22),
            PostureProfile.create("正常", [0.3, 0.4], 20, posture_type="normal"),
        ],
    )
    store.save(settings)
    loaded = store.load()
    assert loaded.camera_index == 2
    assert loaded.sensitivity == 70
    assert loaded.profiles[0].name == "前のめり"
    assert loaded.profiles[0].feature == [0.1, 0.2]
    assert loaded.profiles[0].feature_version == 2
    assert loaded.profiles[0].posture_type == "bad"
    assert loaded.profiles[1].posture_type == "normal"


def test_legacy_profile_without_posture_type_remains_bad():
    profile = PostureProfile.from_dict(
        {
            "id": "legacy",
            "name": "猫背",
            "feature": [0.1, 0.2],
            "created_at": "",
            "sample_count": 12,
            "feature_version": 2,
        }
    )
    assert profile.posture_type == "bad"


def test_invalid_settings_are_recovered(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{invalid", encoding="utf-8")
    loaded = SettingsStore(path).load()
    assert loaded.profiles == []
    assert (tmp_path / "settings.invalid.json").exists()
