from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from pose_care.models import (
    POSTURE_FEATURE_VERSION,
    DetectionState,
    PoseFeature,
    PostureProfile,
)


Landmark = tuple[float, float, float, float]
FEATURE_INDICES = (0, 11, 12)
MIN_VISIBILITY = 0.42


def _midpoint(left: Landmark, right: Landmark) -> tuple[float, float, float]:
    return (
        (left[0] + right[0]) / 2.0,
        (left[1] + right[1]) / 2.0,
        (left[2] + right[2]) / 2.0,
    )


def _distance_3d(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((first - second) ** 2 for first, second in zip(a, b)))


def extract_pose_feature(world_landmarks: Sequence[Landmark]) -> PoseFeature | None:
    """Create a head-and-shoulders feature that does not depend on visible hips."""
    if len(world_landmarks) < 13:
        return None
    if any(world_landmarks[index][3] < MIN_VISIBILITY for index in FEATURE_INDICES):
        return None

    left_shoulder = world_landmarks[11]
    right_shoulder = world_landmarks[12]
    nose = world_landmarks[0]
    mid_shoulder = _midpoint(left_shoulder, right_shoulder)
    shoulder_width = _distance_3d(left_shoulder[:3], right_shoulder[:3])
    if shoulder_width < 0.08:
        return None

    vector: list[float] = []
    for index in FEATURE_INDICES:
        landmark = world_landmarks[index]
        vector.extend((
            (landmark[0] - mid_shoulder[0]) / shoulder_width,
            (landmark[1] - mid_shoulder[1]) / shoulder_width,
            (landmark[2] - mid_shoulder[2]) / shoulder_width,
        ))

    shoulder_tilt = math.atan2(
        right_shoulder[1] - left_shoulder[1],
        max(0.001, abs(right_shoulder[0] - left_shoulder[0])),
    ) / math.pi
    shoulder_depth = (right_shoulder[2] - left_shoulder[2]) / shoulder_width
    head_side = (nose[0] - mid_shoulder[0]) / shoulder_width
    head_drop = (nose[1] - mid_shoulder[1]) / shoulder_width
    head_forward = (nose[2] - mid_shoulder[2]) / shoulder_width
    vector.extend((shoulder_tilt, shoulder_depth, head_side, head_drop, head_forward))

    return PoseFeature(
        vector=tuple(vector),
        metrics={
            "head_forward": head_forward,
            "head_side": head_side,
            "shoulder_tilt": shoulder_tilt * 180.0,
            "shoulder_depth": shoulder_depth,
        },
    )


def aggregate_features(samples: Sequence[PoseFeature]) -> tuple[float, ...]:
    if not samples:
        raise ValueError("姿勢サンプルがありません")
    width = len(samples[0].vector)
    if any(len(sample.vector) != width for sample in samples):
        raise ValueError("姿勢サンプルの形式が一致しません")
    return tuple(statistics.median(sample.vector[index] for sample in samples) for index in range(width))


def feature_similarity(current: Sequence[float], registered: Sequence[float]) -> float:
    if len(current) != len(registered) or not current:
        return 0.0
    coordinate_count = len(FEATURE_INDICES) * 3
    weighted_error = 0.0
    weight_sum = 0.0
    for index, (first, second) in enumerate(zip(current, registered)):
        if index < coordinate_count:
            weight = 0.72 if index % 3 == 2 else 1.0
        else:
            weight = 1.35
        weighted_error += weight * (first - second) ** 2
        weight_sum += weight
    distance = math.sqrt(weighted_error / weight_sum)
    return max(0.0, min(1.0, math.exp(-4.0 * distance)))


def similarity_threshold(sensitivity: int) -> float:
    normalized = max(0, min(100, sensitivity)) / 100.0
    return 0.86 - (0.24 * normalized)


class PostureDetector:
    GOOD_POSTURE_REARM_SECONDS = 8.0
    # When normal and bad examples overlap slightly, prefer the explicitly
    # registered normal posture to avoid a false notification.
    NORMAL_PRIORITY_MARGIN = 0.04

    def __init__(self) -> None:
        self._candidate_id: str | None = None
        self._candidate_since = 0.0
        self._last_alert: dict[str, float] = {}
        self._smoothed_scores: dict[str, float] = {}
        self._good_since = 0.0
        self._rearmed_during_good = False

    def reset(self, clear_alerts: bool = False) -> None:
        self._candidate_id = None
        self._candidate_since = 0.0
        self._smoothed_scores.clear()
        self._good_since = 0.0
        self._rearmed_during_good = False
        if clear_alerts:
            self._last_alert.clear()

    def _safe_state(
        self,
        now: float,
        *,
        kind: str,
        profile_name: str | None = None,
        similarity: float = 0.0,
    ) -> DetectionState:
        self._candidate_id = None
        self._candidate_since = 0.0
        if self._good_since == 0.0:
            self._good_since = now
            self._rearmed_during_good = False
        elif (
            not self._rearmed_during_good
            and now - self._good_since >= self.GOOD_POSTURE_REARM_SECONDS
        ):
            self._last_alert.clear()
            self._rearmed_during_good = True
        return DetectionState(
            kind=kind,
            profile_name=profile_name,
            similarity=similarity,
        )

    def process(
        self,
        feature: PoseFeature | None,
        profiles: Sequence[PostureProfile],
        sensitivity: int,
        hold_seconds: float,
        cooldown_minutes: int,
        now: float,
    ) -> DetectionState:
        if feature is None:
            self._candidate_id = None
            self._good_since = 0.0
            self._rearmed_during_good = False
            return DetectionState(kind="no_pose")
        compatible_profiles = [
            profile
            for profile in profiles
            if profile.feature_version == POSTURE_FEATURE_VERSION
        ]
        bad_profiles = [profile for profile in compatible_profiles if profile.posture_type == "bad"]
        if not bad_profiles:
            self.reset()
            return DetectionState(kind="unconfigured")

        scores: list[tuple[float, PostureProfile]] = []
        for profile in compatible_profiles:
            raw_score = feature_similarity(feature.vector, profile.feature)
            previous = self._smoothed_scores.get(profile.id, raw_score)
            score = (previous * 0.68) + (raw_score * 0.32)
            self._smoothed_scores[profile.id] = score
            scores.append((score, profile))
        bad_score, bad_profile = max(
            (item for item in scores if item[1].posture_type == "bad"),
            key=lambda item: item[0],
        )
        normal_scores = [item for item in scores if item[1].posture_type == "normal"]
        threshold = similarity_threshold(sensitivity)
        if normal_scores:
            normal_score, normal_profile = max(normal_scores, key=lambda item: item[0])
            if (
                normal_score >= threshold
                and normal_score >= bad_score - self.NORMAL_PRIORITY_MARGIN
            ):
                return self._safe_state(
                    now,
                    kind="normal",
                    profile_name=normal_profile.name,
                    similarity=normal_score,
                )

        if bad_score < threshold:
            return self._safe_state(now, kind="good", similarity=bad_score)

        self._good_since = 0.0
        self._rearmed_during_good = False
        if self._candidate_id != bad_profile.id:
            self._candidate_id = bad_profile.id
            self._candidate_since = now
        elapsed = max(0.0, now - self._candidate_since)
        progress = min(1.0, elapsed / max(0.1, hold_seconds))
        if progress < 1.0:
            return DetectionState(
                kind="warning",
                profile_name=bad_profile.name,
                similarity=bad_score,
                progress=progress,
            )

        cooldown_seconds = cooldown_minutes * 60.0
        last_alert = self._last_alert.get(bad_profile.id)
        cooldown_remaining = (
            0.0
            if last_alert is None
            else max(0.0, cooldown_seconds - (now - last_alert))
        )
        should_notify = cooldown_remaining <= 0.0
        if should_notify:
            self._last_alert[bad_profile.id] = now
        return DetectionState(
            kind="bad",
            profile_name=bad_profile.name,
            similarity=bad_score,
            progress=1.0,
            should_notify=should_notify,
            cooldown_remaining=cooldown_remaining,
        )
