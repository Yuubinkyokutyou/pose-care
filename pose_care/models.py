from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


POSTURE_FEATURE_VERSION = 2


@dataclass(slots=True)
class PostureProfile:
    id: str
    name: str
    feature: list[float]
    created_at: str
    sample_count: int = 0
    feature_version: int = POSTURE_FEATURE_VERSION
    posture_type: str = "bad"

    @classmethod
    def create(
        cls,
        name: str,
        feature: list[float],
        sample_count: int,
        posture_type: str = "bad",
    ) -> "PostureProfile":
        normalized_type = "normal" if posture_type == "normal" else "bad"
        return cls(
            id=str(uuid4()),
            name=name.strip() or ("正常姿勢" if normalized_type == "normal" else "悪い姿勢"),
            feature=[round(value, 7) for value in feature],
            created_at=datetime.now(timezone.utc).isoformat(),
            sample_count=sample_count,
            feature_version=POSTURE_FEATURE_VERSION,
            posture_type=normalized_type,
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PostureProfile":
        return cls(
            id=str(value["id"]),
            name=str(value["name"]),
            feature=[float(item) for item in value["feature"]],
            created_at=str(value.get("created_at", "")),
            sample_count=int(value.get("sample_count", 0)),
            feature_version=int(value.get("feature_version", 1)),
            # Profiles created before normal-posture support were all alert targets.
            posture_type="normal" if value.get("posture_type") == "normal" else "bad",
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AppSettings:
    schema_version: int = 1
    camera_index: int = 0
    sensitivity: int = 55
    hold_seconds: float = 4.0
    cooldown_minutes: int = 5
    notifications_enabled: bool = True
    start_minimized: bool = False
    first_run_complete: bool = False
    profiles: list[PostureProfile] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AppSettings":
        return cls(
            schema_version=int(value.get("schema_version", 1)),
            camera_index=max(0, int(value.get("camera_index", 0))),
            sensitivity=max(0, min(100, int(value.get("sensitivity", 55)))),
            hold_seconds=max(1.0, min(30.0, float(value.get("hold_seconds", 4.0)))),
            cooldown_minutes=max(1, min(120, int(value.get("cooldown_minutes", 5)))),
            notifications_enabled=bool(value.get("notifications_enabled", True)),
            start_minimized=bool(value.get("start_minimized", False)),
            first_run_complete=bool(value.get("first_run_complete", False)),
            profiles=[PostureProfile.from_dict(item) for item in value.get("profiles", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["profiles"] = [profile.to_dict() for profile in self.profiles]
        return result


@dataclass(frozen=True, slots=True)
class PoseFeature:
    vector: tuple[float, ...]
    metrics: dict[str, float]


@dataclass(frozen=True, slots=True)
class DetectionState:
    kind: str
    profile_name: str | None = None
    similarity: float = 0.0
    progress: float = 0.0
    should_notify: bool = False
    cooldown_remaining: float = 0.0
