"""Physics-based drone controller — NLP-commanded, starts on ground."""

import math
import logging
from enum import Enum
from PyQt6.QtCore import QObject, pyqtSignal

# Structural constants shared with the renderer (metres)
BODY_H  = 0.12
ROD_LEN = 0.70

# Scene bounds
_XMIN, _XMAX = -9.0,  9.0
_ZMIN, _ZMAX = -9.0,  9.0
_YMIN        =  0.0
_YMAX        =  8.0


def _norm_angle(a: float) -> float:
    """Normalise angle to [-180, 180]."""
    return (a + 180.0) % 360.0 - 180.0


class DroneState(str, Enum):
    GROUNDED   = "Grounded"
    TAKING_OFF = "Taking Off"
    HOVERING   = "Hovering"
    MOVING     = "Moving"
    LANDING    = "Landing"


class DroneAutoPilot(QObject):
    """Smooth, physics-driven drone that responds to NLP commands.

    Starts idle on the ground.  Call ``update()`` once per frame (~60 fps).
    Issue commands via ``command_*`` methods (called by main_window after LLM decoding).

    Signals
    -------
    position_changed(x, y, z)
    state_changed(state_name: str, detail: str)
    """

    position_changed = pyqtSignal(float, float, float)
    state_changed    = pyqtSignal(str, str)

    # ── Physics constants ─────────────────────────────────────────────────────
    # NOTE: All velocities are in m/frame (not m/s).
    # Integration: pos += vel each frame.  At 60 fps: 0.05 m/frame ≈ 3 m/s.
    DT           = 1.0 / 60.0
    MAX_H_SPEED  = 0.12   # m/frame cap  ≈ 7.2 m/s
    MAX_V_SPEED  = 0.08   # m/frame cap  ≈ 4.8 m/s
    ACCEL_LERP   = 0.06   # horizontal velocity ramp-up lerp (smooth acceleration)
    DECEL_LERP   = 0.04   # deceleration lerp when coasting
    HEAD_LERP    = 0.05   # heading smoothing lerp
    ALT_GAIN     = 0.04   # P-gain for altitude (in m/frame units)
    ALT_LERP     = 0.10   # vy smoothing lerp
    DEFAULT_HOVER_ALT = 2.5   # m — default takeoff altitude

    def _speed_to_mf(self, speed: int) -> float:
        """Map speed 1–10 to metres per frame.

        speed 5 → 0.050 m/frame ≈ 3 m/s at 60 fps.
        """
        return max(0.012, min(self.MAX_H_SPEED, speed * 0.010))

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

        # World position (m)
        self.x: float = 0.0
        self.y: float = 0.0
        self.z: float = 0.0

        # Velocity (m/s)
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.vz: float = 0.0

        # Heading (degrees, 0 = toward +Z, clockwise when viewed from above)
        self.heading: float = 0.0

        # Waypoint navigation
        self._waypoint: tuple[float, float, float] | None = None
        self._cruise_speed: float = 3.0   # m/s — set by commands

        # Altitude P-controller
        self._target_y: float | None = None

        # Altitude assist from gimbal tracking coordinator
        self._assist_y: float | None = None

        # Circle / orbit mode
        self._circle_center: tuple[float, float] | None = None  # (cx, cz) world
        self._circle_radius: float = 3.0
        self._circle_angle:  float = 0.0   # current angle (radians)
        self._circle_omega:  float = 0.0   # rad/frame (positive = CW)

        self._state = DroneState.GROUNDED
        self.logger.info("DroneAutoPilot ready — drone on ground at (0, 0, 0)")

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def state(self) -> DroneState:
        return self._state

    @property
    def gimbal_y(self) -> float:
        """Y position of the gimbal pivot (below drone body)."""
        return max(0.01, self.y - BODY_H / 2 - ROD_LEN)

    # Backward-compat stubs used by renderer / main_window
    @property
    def current_path_style(self) -> str:
        return self._state.value

    @property
    def current_path_index(self) -> int:
        return 0

    @property
    def waypoint_count(self) -> int:
        return 0

    @property
    def horizontal_speed(self) -> float:
        return math.sqrt(self.vx ** 2 + self.vz ** 2)

    # ── Command interface ─────────────────────────────────────────────────────

    def command_takeoff(self, altitude: float = 0.0, speed: int = 5):
        """Take off and hover at *altitude* metres (0 = use default)."""
        if self._state != DroneState.GROUNDED:
            return
        alt = max(0.5, min(_YMAX, altitude if altitude > 0.1 else self.DEFAULT_HOVER_ALT))
        self._target_y = alt
        self._state    = DroneState.TAKING_OFF
        self._emit_state(f"Climbing to {alt:.1f} m")

    def command_land(self, speed: int = 5):
        """Begin controlled descent to ground."""
        if self._state == DroneState.GROUNDED:
            return
        self._clear_motion()
        self._target_y = 0.0
        self._state    = DroneState.LANDING
        self.vx *= 0.3
        self.vz *= 0.3
        self._emit_state("Landing")

    def command_hover(self):
        """Stop all movement and hold current position."""
        if self._state in (DroneState.TAKING_OFF, DroneState.LANDING,
                           DroneState.GROUNDED):
            return
        self._clear_motion()
        self._target_y = None
        self._state    = DroneState.HOVERING
        self._emit_state(f"Hovering at {self.y:.1f} m")

    def command_move(self, direction: str, speed: int = 5, distance: float = 3.0):
        """Move in *direction* relative to current heading for approximately *distance* metres.

        direction: "forward" | "back" | "backward" | "left" | "right"
        Uses waypoint navigation for smooth, natural deceleration at destination.
        """
        if self._state not in (DroneState.HOVERING, DroneState.MOVING):
            return
        self._circle_center = None

        hr = math.radians(self.heading)
        fwd_x, fwd_z =  math.sin(hr),  math.cos(hr)
        rgt_x, rgt_z =  math.cos(hr), -math.sin(hr)

        if direction == "forward":
            dx, dz = fwd_x * distance, fwd_z * distance
        elif direction in ("back", "backward"):
            dx, dz = -fwd_x * distance, -fwd_z * distance
        elif direction == "left":
            dx, dz = -rgt_x * distance, -rgt_z * distance
        elif direction == "right":
            dx, dz = rgt_x * distance, rgt_z * distance
        else:
            return

        target_x = max(_XMIN, min(_XMAX, self.x + dx))
        target_z = max(_ZMIN, min(_ZMAX, self.z + dz))
        self._waypoint     = (target_x, self.y, target_z)
        self._cruise_speed = self._speed_to_mf(speed)
        self._state        = DroneState.MOVING
        self._emit_state(f"Flying {direction} {distance:.1f} m")

    def command_ascend(self, value: float = 2.0, speed: int = 5):
        """Climb *value* metres from current altitude."""
        if self._state not in (DroneState.HOVERING, DroneState.MOVING):
            return
        self._target_y = max(0.5, min(_YMAX, self.y + value))
        self._state    = DroneState.MOVING
        self._emit_state(f"Ascending to {self._target_y:.1f} m")

    def command_descend(self, value: float = 2.0, speed: int = 5):
        """Descend *value* metres from current altitude."""
        if self._state not in (DroneState.HOVERING, DroneState.MOVING):
            return
        self._target_y = max(0.3, self.y - value)
        self._state    = DroneState.MOVING
        self._emit_state(f"Descending to {self._target_y:.1f} m")

    def command_yaw(self, angle: float, speed: int = 5):
        """Rotate the drone heading by *angle* degrees (+ = clockwise)."""
        self.heading = (self.heading + angle) % 360
        self._emit_state(f"Heading {self.heading:.0f}°")

    def command_goto(self, x: float, z: float, speed: int = 5):
        """Move toward a world-space (x, z) point."""
        if self._state not in (DroneState.HOVERING, DroneState.MOVING):
            return
        self._circle_center = None
        wx = max(_XMIN, min(_XMAX, x))
        wz = max(_ZMIN, min(_ZMAX, z))
        self._waypoint     = (wx, self.y, wz)
        self._cruise_speed = self._speed_to_mf(speed)
        self._state        = DroneState.MOVING
        self._emit_state(f"Going to ({x:.1f}, {z:.1f})")

    def command_goto_gps(self, lat: float, lon: float, alt_msl: float,
                         home_lat: float, home_lon: float, home_alt_msl: float,
                         speed: int = 5):
        """Navigate to a real-world GPS coordinate.

        Converts (lat, lon, alt_msl) to scene XYZ using the scene origin
        (home_lat, home_lon, home_alt_msl).  Scene axes: +X=East, +Z=North, +Y=Up.
        alt_msl = 0 keeps the current altitude.
        """
        if self._state not in (DroneState.HOVERING, DroneState.MOVING):
            return

        lat_rad = math.radians(home_lat)
        x = (lon - home_lon) * 111_320.0 * math.cos(lat_rad)
        z = (lat - home_lat) * 111_320.0

        if alt_msl > 0:
            y = max(0.3, min(_YMAX, alt_msl - home_alt_msl))
        else:
            y = self.y   # maintain current altitude

        x = max(_XMIN, min(_XMAX, x))
        z = max(_ZMIN, min(_ZMAX, z))

        self._circle_center = None
        self._waypoint      = (x, y, z)
        self._cruise_speed  = self._speed_to_mf(speed)
        if alt_msl > 0:
            self._target_y = y
        self._state = DroneState.MOVING
        ns = 'N' if lat >= 0 else 'S'
        ew = 'E' if lon >= 0 else 'W'
        self._emit_state(
            f"GPS → {abs(lat):.5f}°{ns} {abs(lon):.5f}°{ew}"
            + (f" {alt_msl:.1f}m MSL" if alt_msl > 0 else "")
        )

    def command_circle(self, radius: float = 3.0, speed: int = 5,
                       clockwise: bool = True):
        """Orbit in a continuous circle — drone naturally banks into the turn.

        The circle is centred perpendicular to the current heading so the drone
        starts on the arc immediately without a gap.
        """
        if self._state not in (DroneState.HOVERING, DroneState.MOVING):
            return
        self._waypoint = None
        r = max(1.0, min(7.0, radius))
        self._circle_radius = r

        # Place centre to the right (CW) or left (CCW) of current heading
        hr = math.radians(self.heading)
        if clockwise:
            cx = self.x + math.cos(hr) * r
            cz = self.z - math.sin(hr) * r
        else:
            cx = self.x - math.cos(hr) * r
            cz = self.z + math.sin(hr) * r

        # Clamp center so the full circle stays (mostly) in bounds
        cx = max(_XMIN + r, min(_XMAX - r, cx))
        cz = max(_ZMIN + r, min(_ZMAX - r, cz))
        self._circle_center = (cx, cz)

        # Starting angle: angle from centre to drone
        self._circle_angle = math.atan2(self.x - cx, self.z - cz)

        # Angular velocity (rad/frame): arc_speed_mf / radius
        arc_mf = self._speed_to_mf(speed)
        omega  = arc_mf / r   # rad/frame
        self._circle_omega = omega if clockwise else -omega

        self._state = DroneState.MOVING
        self._emit_state(f"Orbiting r={r:.1f} m {'CW' if clockwise else 'CCW'}")

    def emergency_stop(self):
        self.vx = self.vy = self.vz = 0.0
        self._clear_motion()
        if self._state != DroneState.GROUNDED:
            self._state = DroneState.HOVERING
        self._emit_state("Emergency stop")

    # ── Altitude assist ───────────────────────────────────────────────────────

    def set_altitude_assist(self, y: float):
        if self._state in (DroneState.HOVERING, DroneState.MOVING):
            self._assist_y = max(_YMIN + 0.3, min(_YMAX, y))

    def clear_altitude_assist(self):
        self._assist_y = None

    # ── Main physics update — call once per frame ─────────────────────────────

    def update(self):
        if self._state == DroneState.GROUNDED:
            return

        if self._state == DroneState.TAKING_OFF:
            self._run_altitude_ctrl()
            if (self._target_y is not None
                    and abs(self.y - self._target_y) < 0.05
                    and abs(self.vy) < 0.05):
                self.y         = self._target_y
                self.vy        = 0.0
                self._target_y = None
                self._state    = DroneState.HOVERING
                self._emit_state(f"Hovering at {self.y:.1f} m")

        elif self._state == DroneState.LANDING:
            self.vx *= 0.88
            self.vz *= 0.88
            self._run_altitude_ctrl()

        elif self._state == DroneState.HOVERING:
            # Strong smooth deceleration to a dead stop
            self.vx += (0.0 - self.vx) * (self.DECEL_LERP * 4)
            self.vz += (0.0 - self.vz) * (self.DECEL_LERP * 4)
            self.vy *= 0.82
            if abs(self.vx) < 0.001: self.vx = 0.0
            if abs(self.vz) < 0.001: self.vz = 0.0
            if abs(self.vy) < 0.001: self.vy = 0.0
            if self._assist_y is not None:
                self.vy += (self._assist_y - self.y) * 0.015

        elif self._state == DroneState.MOVING:
            self._run_movement()
            # Altitude
            if self._target_y is not None:
                self._run_altitude_ctrl()
                if abs(self.y - self._target_y) < 0.05 and abs(self.vy) < 0.05:
                    self.y         = self._target_y
                    self.vy        = 0.0
                    self._target_y = None
            elif self._assist_y is not None:
                self.vy += (self._assist_y - self.y) * 0.015
            else:
                self.vy *= 0.90

        # Integrate position
        self.x += self.vx
        self.y += self.vy
        self.z += self.vz

        # Enforce scene bounds — soft bounce off walls
        if self.x < _XMIN:
            self.x  = _XMIN
            self.vx = abs(self.vx) * 0.25
            if self._circle_center is not None:
                self._circle_omega *= -1
        elif self.x > _XMAX:
            self.x  = _XMAX
            self.vx = -abs(self.vx) * 0.25
            if self._circle_center is not None:
                self._circle_omega *= -1

        if self.z < _ZMIN:
            self.z  = _ZMIN
            self.vz = abs(self.vz) * 0.25
        elif self.z > _ZMAX:
            self.z  = _ZMAX
            self.vz = -abs(self.vz) * 0.25

        self.y = max(_YMIN, min(_YMAX, self.y))

        # Ground landing completion
        if self.y <= _YMIN and self._state == DroneState.LANDING:
            self.y         = 0.0
            self.vx        = self.vy = self.vz = 0.0
            self._target_y = None
            self._state    = DroneState.GROUNDED
            self._emit_state("Landed")

        self.position_changed.emit(self.x, self.y, self.z)

    # ── Movement sub-update (waypoint + circle) ───────────────────────────────

    def _run_movement(self):
        """Smooth movement update: circle mode or waypoint navigation."""
        if self._circle_center is not None:
            self._run_circle()
            return

        if self._waypoint is not None:
            wx, _, wz = self._waypoint
            dx = wx - self.x
            dz = wz - self.z
            dist = math.sqrt(dx * dx + dz * dz)

            if dist < 0.35:
                # Arrived at waypoint
                self._waypoint = None
                self._state    = DroneState.HOVERING
                self._emit_state(f"Hovering at {self.y:.1f} m")
                return

            # Slow down as we approach (within 1.8 m start braking)
            approach = min(1.0, dist / 1.8)
            spd = self._cruise_speed * approach

            target_vx = (dx / dist) * spd
            target_vz = (dz / dist) * spd

            # Smooth acceleration toward target velocity
            self.vx += (target_vx - self.vx) * self.ACCEL_LERP
            self.vz += (target_vz - self.vz) * self.ACCEL_LERP

            # Smoothly face direction of travel
            h_spd = math.sqrt(self.vx ** 2 + self.vz ** 2)
            if h_spd > 0.3:
                travel_heading = math.degrees(math.atan2(self.vx, self.vz)) % 360
                hdelta = _norm_angle(travel_heading - self.heading)
                self.heading = (self.heading + hdelta * self.HEAD_LERP) % 360

        else:
            # No target — coast to a stop
            self.vx += (0.0 - self.vx) * self.DECEL_LERP
            self.vz += (0.0 - self.vz) * self.DECEL_LERP
            spd_sq = self.vx ** 2 + self.vz ** 2 + self.vy ** 2
            if spd_sq < 0.001 and self._target_y is None:
                self._state = DroneState.HOVERING
                self._emit_state(f"Hovering at {self.y:.1f} m")

    def _run_circle(self):
        """Advance the orbital circle by one frame."""
        cx, cz = self._circle_center
        self._circle_angle += self._circle_omega

        # Target position on the arc
        tx = cx + math.sin(self._circle_angle) * self._circle_radius
        tz = cz + math.cos(self._circle_angle) * self._circle_radius

        dx = tx - self.x
        dz = tz - self.z
        dist = math.sqrt(dx * dx + dz * dz)

        if dist > 0.01:
            arc_spd = min(self.MAX_H_SPEED,
                          self._circle_radius * abs(self._circle_omega))
            self.vx += ((dx / dist) * arc_spd - self.vx) * 0.12
            self.vz += ((dz / dist) * arc_spd - self.vz) * 0.12

        # Face tangent: direction perpendicular to radius in direction of travel
        # d/dθ of (sin θ, cos θ) = (cos θ, -sin θ) for CW; negate for CCW
        sign = 1 if self._circle_omega > 0 else -1
        tx_head = math.cos(self._circle_angle) * sign
        tz_head = -math.sin(self._circle_angle) * sign
        target_heading = math.degrees(math.atan2(tx_head, tz_head)) % 360
        hdelta = _norm_angle(target_heading - self.heading)
        self.heading = (self.heading + hdelta * 0.08) % 360

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _clear_motion(self):
        """Cancel waypoint and circle, zero target velocities."""
        self._waypoint      = None
        self._circle_center = None

    def _run_altitude_ctrl(self):
        """P-controller: smoothly drive vy toward _target_y."""
        if self._target_y is None:
            return
        err        = self._target_y - self.y
        desired_vy = max(-self.MAX_V_SPEED, min(self.MAX_V_SPEED, err * self.ALT_GAIN))
        self.vy   += (desired_vy - self.vy) * self.ALT_LERP

    def _emit_state(self, detail: str = ""):
        self.state_changed.emit(self._state.value, detail)
