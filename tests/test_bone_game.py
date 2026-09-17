import math
import os
import random

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from pose_care.bone_game import Bone, BoneGame


@pytest.fixture
def game():
    application = QApplication.instance() or QApplication([])
    now = [100.0]
    instance = BoneGame(clock=lambda: now[0], rng=random.Random(4))
    pose = [(0.5, 0.25, 0, 0)] * 33
    pose[0] = (0.5, 0.25, 0, 1)
    instance.set_pose(pose)
    yield instance, now, pose
    instance.reset()


def start(instance):
    for _ in range(3):
        instance.click()
    instance.timer.stop()


def test_triple_click_window_and_restart(game):
    g, now, pose = game
    g.click()
    now[0] += 2
    g.click()
    g.click()
    assert g.state == "idle"
    g.click()
    assert g.state == "intro"
    now[0] += 1.7
    g.set_pose(pose)
    g.tick()
    assert g.state == "playing"
    g.reset()
    assert g.state == "idle" and not g.timer.isActive() and g.sprites == []
    start(g)
    assert g.hearts == 2 and g.score == 0


def test_two_hits_score_and_automatic_cleanup(game):
    g, now, pose = game
    start(g)
    g.phase = "playing"
    g.spawn_in = 100
    for hit in range(2):
        g.invulnerable = 0
        g.bones = [Bone(320, 120, 0, 0)]
        now[0] += 0.05
        g.set_pose(pose)
        g.tick()
        assert g.hearts == 1 - hit
    score = g.score
    assert g.state == "result" and 0 < score <= 0.1
    assert not g.bones
    now[0] += 2
    g.tick()
    assert g.score == score
    now[0] += 3.1
    g.tick()
    assert g.state == "idle" and not g.timer.isActive()


def test_arm_reflects_incoming_bone_and_culls_offscreen(game):
    g, now, pose = game
    pose[11] = (0.25, 0.5, 0, 1)
    pose[13] = (0.75, 0.5, 0, 1)
    g.set_pose(pose)
    g.spawn_in = 100
    bone = Bone(300, 212, 0, 300)
    g.bones = [bone]
    g._step(1 / 120, (320, 120))
    assert bone.reflected and bone.vy < 0
    assert math.hypot(bone.vx, bone.vy) == pytest.approx(405)
    for _ in range(120):
        g._step(1 / 120, (320, 120))
    assert not g.bones and g.hearts == 2


def test_invulnerability_prevents_simultaneous_double_hit(game):
    g, _, _ = game
    g.spawn_in = 100
    g.bones = [Bone(320, 120, 0, 0), Bone(320, 120, 0, 0)]
    g._step(0.01, (320, 120))
    assert g.hearts == 1 and not g.bones


def test_missing_pose_pauses_score_and_eventually_cleans_up(game):
    g, now, _ = game
    start(g)
    g.phase = "playing"
    now[0] += 0.7
    g.tick()
    assert g.score == 0 and not g.tracking
    now[0] += 5
    g.tick()
    assert g.state == "idle" and not g.timer.isActive()


def test_crop_coordinates_and_invisible_arm_filter(game):
    g, _, pose = game
    g.frame_width, g.frame_height = 1280, 720
    g.setViewport(400, 600)
    assert g._nose() == pytest.approx((200, 150))
    assert g._arms() == []
    pose[0] = (0, 0.25, 0, 1)
    g.set_pose(pose)
    assert g._nose() is None


def test_difficulty_increases_and_throws_come_from_all_edges(game):
    g, _, _ = game
    early_interval, early_speed = g.difficulty(0)
    late_interval, late_speed = g.difficulty(30)
    assert late_interval <= early_interval / 5
    assert late_speed >= early_speed * 2
    for _ in range(100):
        g._spawn((320, 120))
    assert any(b.x < 0 for b in g.bones)
    assert any(b.x > g.width for b in g.bones)
    assert any(b.y < 0 for b in g.bones)
    assert any(b.y > g.height for b in g.bones)
    assert all((320 - b.x) * b.vx + (120 - b.y) * b.vy > 0 for b in g.bones)
