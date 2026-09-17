"""Ephemeral, camera-coordinate survival game; no camera or score persistence."""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, Property, QTimer, Qt, Signal, Slot


@dataclass
class Bone:
    x: float
    y: float
    vx: float
    vy: float
    angle: float = 0
    reflected: bool = False


def closest_point(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / length2)) if length2 else 0
    return a[0] + t * dx, a[1] + t * dy


class BoneGame(QObject):
    changed = Signal()
    INTRO_SECONDS = 1.6
    RESULT_SECONDS = 5.0
    BONE_RADIUS = 22.0

    def __init__(self, parent=None, *, clock=time.monotonic, rng=None):
        super().__init__(parent)
        self.clock = clock
        self.rng = rng or random.Random()
        self.phase = "idle"
        self.lives = 2
        self.elapsed = 0.0
        self.bones: list[Bone] = []
        self.width, self.height = 640.0, 480.0
        self.frame_width, self.frame_height = 640, 480
        self.landmarks = []
        self.pose_at = -math.inf
        self.phase_at = self.clock()
        self.last_tick = self.phase_at
        self.clicks = []
        self.spawn_in = 0.0
        self.invulnerable = 0.0
        self.missing_for = 0.0
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)

    state = Property(str, lambda self: self.phase, notify=changed)
    hearts = Property(int, lambda self: self.lives, notify=changed)
    score = Property(float, lambda self: self.elapsed, notify=changed)
    hitFlash = Property(bool, lambda self: self.invulnerable > 0.55, notify=changed)
    tracking = Property(bool, lambda self: self._nose() is not None, notify=changed)
    nosePosition = Property("QVariantMap", lambda self: self._nose_position(), notify=changed)
    sprites = Property("QVariantList", lambda self: [
        {"x": b.x, "y": b.y, "angle": b.angle, "reflected": b.reflected}
        for b in self.bones
    ], notify=changed)
    arms = Property("QVariantList", lambda self: [
        {"ax": a[0], "ay": a[1], "bx": b[0], "by": b[1]}
        for a, b in self._arms()
    ], notify=changed)

    def set_pose(self, landmarks):
        self.landmarks = landmarks
        self.pose_at = self.clock()

    def _point(self, index):
        if self.clock() - self.pose_at > 0.6 or index >= len(self.landmarks):
            return None
        x, y, _z, visibility = self.landmarks[index]
        if visibility < 0.5 or not all(math.isfinite(v) for v in (x, y, visibility)):
            return None
        # Match Image.PreserveAspectCrop, centered, without mirroring.
        scale = max(self.width / self.frame_width, self.height / self.frame_height)
        return (x * self.frame_width * scale - (self.frame_width * scale - self.width) / 2,
                y * self.frame_height * scale - (self.frame_height * scale - self.height) / 2)

    def _nose(self):
        nose = self._point(0)
        return nose if nose and 0 <= nose[0] <= self.width and 0 <= nose[1] <= self.height else None

    def _nose_position(self):
        nose = self._nose()
        return {"x": nose[0], "y": nose[1]} if nose is not None else {}

    def _arms(self):
        segments = []
        for start, end in ((11, 13), (13, 15), (12, 14), (14, 16)):
            a, b = self._point(start), self._point(end)
            if a is not None and b is not None:
                segments.append((a, b))
        return segments

    @Slot(float, float)
    def setViewport(self, width, height):
        if width > 0 and height > 0:
            # Keep in-flight objects aligned when the window is resized.
            for bone in self.bones:
                bone.x *= width / self.width
                bone.y *= height / self.height
            self.width, self.height = width, height

    @Slot()
    def click(self):
        if self.phase != "idle":
            return
        now = self.clock()
        self.clicks = [t for t in self.clicks if now - t < 1.2] + [now]
        if len(self.clicks) < 3:
            return
        self.clicks.clear()
        self.phase = "intro"
        self.phase_at = self.last_tick = now
        self.lives, self.elapsed = 2, 0.0
        self.spawn_in, self.invulnerable, self.missing_for = 0.0, 0.0, 0.0
        self.bones.clear()
        self.timer.start()
        self.changed.emit()

    @Slot()
    def reset(self):
        self.timer.stop()
        self.phase = "idle"
        self.bones.clear()
        self.clicks.clear()
        self.lives, self.elapsed, self.invulnerable = 2, 0.0, 0.0
        self.changed.emit()

    @staticmethod
    def difficulty(seconds):
        ramp = min(1.5, seconds / 30.0)
        return max(0.15, 1.1 - 0.9 * ramp), 160 + 200 * ramp

    def _spawn(self, nose):
        edge = self.rng.randrange(4)
        x, y = self.rng.random() * self.width, self.rng.random() * self.height
        if edge == 0:
            x = -48
        elif edge == 1:
            x = self.width + 48
        elif edge == 2:
            y = -48
        else:
            y = self.height + 48
        # Most throws threaten the head, but allow small gaps to dodge through.
        tx, ty = nose[0] + self.rng.uniform(-45, 45), nose[1] + self.rng.uniform(-35, 35)
        distance = max(1, math.hypot(tx - x, ty - y))
        speed = self.difficulty(self.elapsed)[1] * min(self.width, self.height) / 480
        self.bones.append(Bone(x, y, (tx - x) / distance * speed,
                               (ty - y) / distance * speed, self.rng.uniform(0, 360)))

    def _step(self, dt, nose):
        self.invulnerable = max(0, self.invulnerable - dt)
        self.spawn_in -= dt
        if self.spawn_in <= 0:
            self._spawn(nose)
            self.spawn_in += self.difficulty(self.elapsed)[0]
        segments = self._arms()
        remaining = []
        for bone in self.bones:
            bone.x += bone.vx * dt
            bone.y += bone.vy * dt
            bone.angle += dt * (220 if bone.reflected else 75)
            if not bone.reflected:
                for a, b in segments:
                    cx, cy = closest_point(bone.x, bone.y, a, b)
                    dx, dy = bone.x - cx, bone.y - cy
                    distance = math.hypot(dx, dy)
                    if distance > self.BONE_RADIUS + 8:
                        continue
                    if distance < 0.001:
                        dx, dy = -bone.vx, -bone.vy
                        distance = max(1, math.hypot(dx, dy))
                    nx, ny = dx / distance, dy / distance
                    dot = bone.vx * nx + bone.vy * ny
                    if dot < 0:
                        bone.vx -= 2 * dot * nx
                        bone.vy -= 2 * dot * ny
                    bone.vx *= 1.35
                    bone.vy *= 1.35
                    bone.x, bone.y = cx + nx * 32, cy + ny * 32
                    bone.reflected = True
                    break
            if (not bone.reflected and math.hypot(bone.x - nose[0], bone.y - nose[1]) < self.BONE_RADIUS + 13):
                if self.invulnerable <= 0:
                    self.lives -= 1
                    self.invulnerable = 0.9
                    if self.lives == 0:
                        self.phase = "result"
                        self.phase_at = self.clock()
                        self.bones.clear()
                        return
                continue
            # Only cull once a projectile is outside and travelling away.
            if ((bone.x < -80 and bone.vx < 0) or (bone.x > self.width + 80 and bone.vx > 0)
                    or (bone.y < -80 and bone.vy < 0) or (bone.y > self.height + 80 and bone.vy > 0)):
                continue
            remaining.append(bone)
        self.bones = remaining

    def tick(self):
        now = self.clock()
        delta = max(0, now - self.last_tick)
        self.last_tick = now
        if self.phase == "result":
            if now - self.phase_at >= self.RESULT_SECONDS:
                self.reset()
                return
        elif self.phase in ("intro", "playing"):
            nose = self._nose()
            if nose is None:
                self.missing_for += delta
                if self.missing_for >= 5:
                    self.reset()
                    return
            else:
                self.missing_for = 0
                if self.phase == "intro":
                    if now - self.phase_at >= self.INTRO_SECONDS:
                        self.phase = "playing"
                else:
                    # Ignore app stalls; use small steps so fast bones cannot tunnel through arms.
                    delta = min(delta, 0.1)
                    while delta > 0.000001 and self.phase == "playing":
                        step = min(delta, 1 / 120)
                        self.elapsed += step
                        self._step(step, nose)
                        delta -= step
        self.changed.emit()
