from __future__ import annotations

import pytest

from pose_care.models import PoseFeature, PostureProfile
from pose_care.posture import (
    PostureDetector,
    aggregate_features,
    extract_pose_feature,
    feature_similarity,
    similarity_threshold,
)


def make_landmarks(scale: float = 1.0, offset=(0.0, 0.0, 0.0)):
    values = [(0.0, 0.0, 0.0, 1.0) for _ in range(33)]
    points = {
        0: (0.0, -0.82, -0.08),
        11: (-0.20, -0.50, 0.0),
        12: (0.20, -0.50, 0.0),
        23: (-0.15, 0.0, 0.0),
        24: (0.15, 0.0, 0.0),
    }
    for index, point in points.items():
        values[index] = (
            (point[0] * scale) + offset[0],
            (point[1] * scale) + offset[1],
            (point[2] * scale) + offset[2],
            1.0,
        )
    return values


def test_feature_is_translation_and_scale_invariant():
    base = extract_pose_feature(make_landmarks())
    transformed = extract_pose_feature(make_landmarks(scale=1.8, offset=(2.0, -1.0, 0.7)))
    assert base is not None
    assert transformed is not None
    assert transformed.vector == pytest.approx(base.vector, abs=1e-9)
    assert feature_similarity(base.vector, transformed.vector) == pytest.approx(1.0)


def test_feature_requires_visible_core_landmarks():
    landmarks = make_landmarks()
    landmarks[0] = (*landmarks[0][:3], 0.2)
    assert extract_pose_feature(landmarks) is None


def test_feature_does_not_require_hips_or_lower_body():
    landmarks = make_landmarks()
    for index in range(23, 33):
        landmarks[index] = (*landmarks[index][:3], 0.0)
    assert extract_pose_feature(landmarks) is not None


def test_aggregate_uses_median_to_reject_outlier():
    samples = [
        PoseFeature((1.0, 2.0), {}),
        PoseFeature((1.1, 2.1), {}),
        PoseFeature((20.0, 30.0), {}),
    ]
    assert aggregate_features(samples) == pytest.approx((1.1, 2.1))


def test_detector_requires_hold_time_and_honors_cooldown():
    feature = extract_pose_feature(make_landmarks())
    assert feature is not None
    profile = PostureProfile.create("猫背", list(feature.vector), 30)
    detector = PostureDetector()

    warning = detector.process(feature, [profile], 55, 3.0, 2, now=10.0)
    assert warning.kind == "warning"
    assert not warning.should_notify

    bad = detector.process(feature, [profile], 55, 3.0, 2, now=13.1)
    assert bad.kind == "bad"
    assert bad.should_notify

    cooldown = detector.process(feature, [profile], 55, 3.0, 2, now=20.0)
    assert cooldown.kind == "bad"
    assert not cooldown.should_notify
    assert cooldown.cooldown_remaining == pytest.approx(113.1)

    later = detector.process(feature, [profile], 55, 3.0, 2, now=134.0)
    assert later.should_notify


def test_new_background_session_can_alert_again_after_hold():
    feature = extract_pose_feature(make_landmarks())
    assert feature is not None
    profile = PostureProfile.create("猫背", list(feature.vector), 30)
    detector = PostureDetector()
    detector.process(feature, [profile], 55, 3.0, 5, now=1.0)
    assert detector.process(feature, [profile], 55, 3.0, 5, now=4.1).should_notify

    detector.reset(clear_alerts=True)
    assert detector.process(feature, [profile], 55, 3.0, 5, now=5.0).kind == "warning"
    assert detector.process(feature, [profile], 55, 3.0, 5, now=8.1).should_notify


def test_good_posture_rearms_notification_before_fixed_cooldown():
    feature = extract_pose_feature(make_landmarks())
    assert feature is not None
    profile = PostureProfile.create("猫背", list(feature.vector), 30)
    far_feature = PoseFeature(tuple(value + 5.0 for value in feature.vector), {})
    detector = PostureDetector()
    detector.process(feature, [profile], 55, 3.0, 5, now=1.0)
    assert detector.process(feature, [profile], 55, 3.0, 5, now=4.1).should_notify

    assert detector.process(far_feature, [profile], 55, 3.0, 5, now=10.0).kind == "good"
    detector.process(far_feature, [profile], 55, 3.0, 5, now=18.1)
    detector.process(feature, [profile], 55, 3.0, 5, now=19.0)
    warning = detector.process(feature, [profile], 55, 3.0, 5, now=19.2)
    assert warning.kind == "warning"
    assert detector.process(feature, [profile], 55, 3.0, 5, now=22.3).should_notify


def test_higher_sensitivity_accepts_looser_matches():
    assert similarity_threshold(100) < similarity_threshold(0)


def test_registered_normal_posture_excludes_ambiguous_bad_match():
    feature = extract_pose_feature(make_landmarks())
    assert feature is not None
    bad_profile = PostureProfile.create("猫背", list(feature.vector), 30)
    normal_profile = PostureProfile.create(
        "いつもの正常姿勢",
        list(feature.vector),
        30,
        posture_type="normal",
    )

    state = PostureDetector().process(
        feature,
        [bad_profile, normal_profile],
        55,
        3.0,
        2,
        now=1.0,
    )

    assert state.kind == "normal"
    assert state.profile_name == "いつもの正常姿勢"
    assert not state.should_notify


def test_closest_bad_posture_is_still_detected_when_normal_is_far():
    feature = extract_pose_feature(make_landmarks())
    assert feature is not None
    bad_profile = PostureProfile.create("猫背", list(feature.vector), 30)
    normal_vector = [value + 0.8 for value in feature.vector]
    normal_profile = PostureProfile.create(
        "正常",
        normal_vector,
        30,
        posture_type="normal",
    )

    state = PostureDetector().process(
        feature,
        [bad_profile, normal_profile],
        55,
        3.0,
        2,
        now=1.0,
    )

    assert state.kind == "warning"
    assert state.profile_name == "猫背"


def test_normal_profiles_alone_do_not_configure_alert_detection():
    feature = extract_pose_feature(make_landmarks())
    assert feature is not None
    normal_profile = PostureProfile.create(
        "正常",
        list(feature.vector),
        30,
        posture_type="normal",
    )
    state = PostureDetector().process(feature, [normal_profile], 55, 3.0, 2, now=1.0)
    assert state.kind == "unconfigured"


def test_detector_rejects_profiles_from_old_feature_format():
    feature = extract_pose_feature(make_landmarks())
    assert feature is not None
    profile = PostureProfile.create("旧方式", list(feature.vector), 20)
    profile.feature_version = 1
    state = PostureDetector().process(feature, [profile], 55, 3.0, 2, now=1.0)
    assert state.kind == "unconfigured"
