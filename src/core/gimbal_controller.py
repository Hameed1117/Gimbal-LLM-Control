"""Gimbal controller — pan/tilt motor control with PWM output simulation."""

import math
import logging
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


class GimbalController(QObject):
    """Controls the three-axis PTZ gimbal (pan + tilt + zoom).

    Smooth interpolation toward target angles/zoom at each ``update()`` call.
    PWM output follows the RC servo standard: 1000–2000 µs @ 50 Hz,
    with 1500 µs = centre for pan/tilt, 1000 µs = 1× wide for zoom.

    Pan  range : ±180°       → PWM 1000–2000 µs (1500 = centre)
    Tilt range : ± 90°       → PWM 1000–2000 µs (1500 = centre)
    Zoom range : 1×–30×      → PWM 1000–2000 µs (1000 = wide, 2000 = tele)
    """

    # Emitted every frame while moving (and once when settled)
    position_changed = pyqtSignal(dict)   # {pan, tilt, speed, pan_pwm, tilt_pwm, zoom_factor, zoom_pwm}
    status_changed   = pyqtSignal(str)

    # ── Physical constants ────────────────────────────────────────────────────
    PAN_LIMIT  = 180.0   # ° max from centre
    TILT_LIMIT =  90.0   # ° max from centre
    ZOOM_MIN   =   1.0   # × minimum (widest)
    ZOOM_MAX   =  30.0   # × maximum (most telephoto)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.logger = logging.getLogger(__name__)

        # ── Current angles + zoom ─────────────────────────────────────────────
        self.pan:  float = 0.0
        self.tilt: float = 0.0
        self.speed: int  = 5

        # ── Zoom axis ─────────────────────────────────────────────────────────
        self.zoom_factor:        float = 1.0
        self.target_zoom_factor: float = 1.0

        # ── Target angles (smooth interpolation) ─────────────────────────────
        self.target_pan:  float = 0.0
        self.target_tilt: float = 0.0
        self.is_moving:   bool  = False

        # ── Tracking mode ─────────────────────────────────────────────────────
        # When True, set_tracking_target() drives the targets each frame
        self.tracking_mode: bool = False

        self.logger.info("GimbalController ready (pan ±%.0f°, tilt ±%.0f°, zoom %.0f–%.0f×)",
                         self.PAN_LIMIT, self.TILT_LIMIT, self.ZOOM_MIN, self.ZOOM_MAX)

        # Emit initial state after event loop starts
        QTimer.singleShot(0, lambda: self.position_changed.emit(self.get_position()))
        QTimer.singleShot(0, lambda: self.status_changed.emit("Ready"))

    # ── Getters ───────────────────────────────────────────────────────────────

    def get_position(self) -> dict:
        """Return current gimbal state including PWM values for all three axes."""
        pan_pwm  = int(round(1500 + (self.pan  / self.PAN_LIMIT)  * 500))
        tilt_pwm = int(round(1500 + (self.tilt / self.TILT_LIMIT) * 500))
        zoom_pwm = int(round(1000 + (self.zoom_factor - self.ZOOM_MIN)
                             / (self.ZOOM_MAX - self.ZOOM_MIN) * 1000))
        return {
            "pan":         self.pan,
            "tilt":        self.tilt,
            "speed":       self.speed,
            "pan_pwm":     max(1000, min(2000, pan_pwm)),
            "tilt_pwm":    max(1000, min(2000, tilt_pwm)),
            "zoom_factor": self.zoom_factor,
            "zoom_pwm":    max(1000, min(2000, zoom_pwm)),
        }

    # ── Motor commands ────────────────────────────────────────────────────────

    def pan_to(self, angle: float, speed: int = 5):
        """Drive pan motor to ``angle`` degrees."""
        self.target_pan = max(-self.PAN_LIMIT, min(self.PAN_LIMIT, angle))
        self.speed      = max(1, min(10, speed))
        self.is_moving  = True
        self.status_changed.emit("Moving")
        self.logger.info("Pan  → %.1f° @ speed %d", angle, speed)

    def tilt_to(self, angle: float, speed: int = 5):
        """Drive tilt motor to ``angle`` degrees."""
        self.target_tilt = max(-self.TILT_LIMIT, min(self.TILT_LIMIT, angle))
        self.speed       = max(1, min(10, speed))
        self.is_moving   = True
        self.status_changed.emit("Moving")
        self.logger.info("Tilt → %.1f° @ speed %d", angle, speed)

    def zoom_to(self, factor: float, speed: int = 5):
        """Drive zoom to absolute *factor* (1×–30×)."""
        self.target_zoom_factor = max(self.ZOOM_MIN, min(self.ZOOM_MAX, factor))
        self.speed     = max(1, min(10, speed))
        self.is_moving = True
        self.status_changed.emit("Moving")
        self.logger.info("Zoom → %.1f×  @ speed %d", factor, speed)

    def zoom_by(self, delta: float, speed: int = 5):
        """Adjust zoom by *delta* from the current factor (clamped to 1×–30×)."""
        self.zoom_to(self.zoom_factor + delta, speed)

    def move_to_home(self):
        """Centre all three axes: pan 0°, tilt 0°, zoom 1×."""
        self.pan_to(0.0, 5)
        self.tilt_to(0.0, 5)
        self.zoom_to(1.0, 5)
        self.logger.info("Home")

    def stop(self):
        """Freeze all axes at their current positions."""
        self.is_moving           = False
        self.tracking_mode       = False
        self.target_pan          = self.pan
        self.target_tilt         = self.tilt
        self.target_zoom_factor  = self.zoom_factor
        self.status_changed.emit("Ready")
        self.position_changed.emit(self.get_position())
        self.logger.info("Stop")

    # ── Tracking ──────────────────────────────────────────────────────────────

    def enable_tracking(self, enabled: bool):
        """Enable/disable continuous tracking mode."""
        self.tracking_mode = enabled
        if enabled:
            self.is_moving = True
            self.speed     = 8
            self.status_changed.emit("Tracking")
        else:
            self.is_moving   = False
            self.target_pan  = self.pan
            self.target_tilt = self.tilt
            self.status_changed.emit("Ready")

    def set_tracking_target(self, pan: float, tilt: float):
        """Update tracking target — called each frame when tracking is active."""
        if not self.tracking_mode:
            return
        self.target_pan  = max(-self.PAN_LIMIT,  min(self.PAN_LIMIT,  pan))
        self.target_tilt = max(-self.TILT_LIMIT, min(self.TILT_LIMIT, tilt))
        self.is_moving   = True

    # ── Main update (60 fps) ─────────────────────────────────────────────────

    def update(self):
        """Smooth interpolation tick — call once per frame (all three PTZ axes)."""
        if not self.is_moving and not self.tracking_mode:
            return

        pan_diff  = self.target_pan  - self.pan
        tilt_diff = self.target_tilt - self.tilt
        zoom_diff = self.target_zoom_factor - self.zoom_factor

        if abs(pan_diff) < 0.1 and abs(tilt_diff) < 0.1 and abs(zoom_diff) < 0.05:
            self.pan         = self.target_pan
            self.tilt        = self.target_tilt
            self.zoom_factor = self.target_zoom_factor
            if not self.tracking_mode:
                self.is_moving = False
                self.status_changed.emit("Ready")
        else:
            rate              = self.speed / 100.0
            self.pan         += pan_diff  * rate
            self.tilt        += tilt_diff * rate
            self.zoom_factor += zoom_diff * rate

        self.position_changed.emit(self.get_position())

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self):
        self.stop()
