"""3D OpenGL Renderer — drone + gimbal + realistic scene entities."""

import math
import os
import random
import logging
import time
from typing import Optional

from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import QTimer, pyqtSignal, Qt
from PyQt6.QtGui import QPainter, QColor, QFont, QPen

try:
    from OpenGL.GL  import *
    from OpenGL.GLU import *
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False

# Project root = two levels above this file (src/graphics → src → root)
_HERE      = os.path.dirname(os.path.abspath(__file__))
_PROJ_ROOT = os.path.dirname(os.path.dirname(_HERE))
_ASSETS    = os.path.join(_PROJ_ROOT, "assets", "models")


# ── Material presets ──────────────────────────────────────────────────────────

def _mat_car_paint(r, g, b):
    """Glossy car paint — strong specular, high shininess."""
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR,
                 [min(1, r * 0.5 + 0.55), min(1, g * 0.5 + 0.55),
                  min(1, b * 0.5 + 0.55), 1.0])
    glMaterialf (GL_FRONT_AND_BACK, GL_SHININESS, 90.0)

def _mat_chrome():
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR,  [1.0, 1.0, 1.0, 1.0])
    glMaterialf (GL_FRONT_AND_BACK, GL_SHININESS, 128.0)

def _mat_glass():
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR,  [0.85, 0.90, 1.0, 1.0])
    glMaterialf (GL_FRONT_AND_BACK, GL_SHININESS, 96.0)

def _mat_rubber():
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR,  [0.04, 0.04, 0.04, 1.0])
    glMaterialf (GL_FRONT_AND_BACK, GL_SHININESS, 4.0)

def _mat_matte():
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR,  [0.06, 0.06, 0.06, 1.0])
    glMaterialf (GL_FRONT_AND_BACK, GL_SHININESS, 6.0)

def _mat_drone_shell():
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR,  [0.6, 0.6, 0.65, 1.0])
    glMaterialf (GL_FRONT_AND_BACK, GL_SHININESS, 70.0)

def _mat_reset():
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.0, 0.0, 0.0, 1.0])
    glMaterialf (GL_FRONT_AND_BACK, GL_SHININESS, 0.0)


class GimbalRenderer(QOpenGLWidget):
    """3D OpenGL renderer: live drone + realistic entities + free camera."""

    fps_updated = pyqtSignal(float)

    # Structural constants (metres)
    BODY_H  = 0.12
    ROD_LEN = 0.70
    CAM_ARM = 0.30
    DRONE_Y = 2.0    # kept for legacy get_gimbal_screen_geometry

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.logger = logging.getLogger(__name__)

        self.pan_angle  = 0.0
        self.tilt_angle = 0.0

        self.drone_x = 0.0
        self.drone_y = 0.16
        self.drone_z = 0.0

        # Drone attitude — updated each frame from velocity
        self.drone_yaw        = 0.0   # heading (°), faces direction of travel
        self.drone_roll       = 0.0   # banking into turns (°)
        self.drone_pitch_anim = 0.0   # nose pitch on climb/descent (°)

        # Tracking yaw override — when set, drone body turns toward subject
        # instead of direction-of-travel (set by main_window coordinator)
        self._tracking_yaw: float | None = None

        self.entities = self._init_entities()

        # Legacy ball (control-panel checkbox)
        self.moving_object_enabled = False
        self.obj_x  =  0.0;  self.obj_z  =  0.0
        self.obj_vx =  0.07; self.obj_vz =  0.055
        self.tracking_active = False
        self.tracking_locked = False

        # Camera orbit (observer perspective — scroll-wheel / drag)
        self.cam_distance  = 9.0
        self.cam_elevation = 28.0
        self.cam_azimuth   = 35.0
        self._drag_start   = None

        # PTZ lens zoom — drives FOV; 1× = 60°, 30× ≈ 2°
        self.cam_fov = 60.0

        # FPS
        self.frame_count = 0
        self.last_fps_t  = time.time()
        self.current_fps = 60.0
        self._fps_timer  = QTimer()
        self._fps_timer.timeout.connect(self._tick_fps)
        self._fps_timer.start(1000)

        # Animation
        self.prop_angle  = 0.0
        self.bird_phase  = 0.0   # wing-flap animation

        self._hspeed_mps = 0.0   # updated each frame for HUD speed display

        self._model_mx = None
        self._proj_mx  = None
        self._viewport = None

        # OBJ models — loaded once at startup
        self._obj_meshes: dict = {}   # {"sedan": ObjMesh, "quad_uav": …, "seagull": …}
        self._load_obj_models()

        self._render_timer = QTimer()
        self._render_timer.timeout.connect(self._on_frame)

        self.setMinimumSize(400, 300)
        self.logger.info("3D GimbalRenderer created (OpenGL=%s)", OPENGL_AVAILABLE)

    # ── Entity init ───────────────────────────────────────────────────────────

    def _init_entities(self) -> list:
        rng = random.Random(42)   # deterministic initial positions
        return [
            # Ground vehicles
            {'type':'vehicle','label':'VH-01','x': 2.8,'y':0.30,'z': 1.2,
             'vx': 0.030,'vy':0.0,'vz': 0.022,'color':(0.90,0.22,0.08),
             'phase':0.0,'base_y':0.30},
            {'type':'vehicle','label':'VH-02','x':-3.2,'y':0.30,'z':-1.8,
             'vx':-0.024,'vy':0.0,'vz': 0.034,'color':(0.12,0.42,0.88),
             'phase':1.0,'base_y':0.30},
            {'type':'vehicle','label':'VH-03','x': 1.1,'y':0.30,'z':-3.8,
             'vx': 0.038,'vy':0.0,'vz':-0.019,'color':(0.18,0.68,0.28),
             'phase':2.0,'base_y':0.30},
            # Aerial UAVs
            {'type':'uav','label':'UA-01','x': 1.6,'y':1.9,'z': 2.1,
             'vx': 0.022,'vy':0.0,'vz':-0.031,'color':(0.95,0.82,0.08),
             'phase':0.0,'base_y':1.9},
            {'type':'uav','label':'UA-02','x':-2.1,'y':2.3,'z': 1.6,
             'vx':-0.030,'vy':0.0,'vz': 0.024,'color':(0.62,0.20,0.90),
             'phase':2.1,'base_y':2.3},
            {'type':'uav','label':'UA-03','x': 3.1,'y':2.1,'z':-1.1,
             'vx': 0.016,'vy':0.0,'vz': 0.038,'color':(0.95,0.50,0.10),
             'phase':4.2,'base_y':2.1},
            # Birds
            {'type':'bird','label':'BR-01','x':-1.1,'y':4.6,'z': 3.2,
             'vx': 0.052,'vy':0.0,'vz':-0.040,'color':(0.88,0.90,0.92),
             'phase':0.0,'base_y':4.6,'wing_angle':0.0},
            {'type':'bird','label':'BR-02','x': 2.2,'y':5.6,'z':-2.1,
             'vx':-0.045,'vy':0.0,'vz': 0.031,'color':(0.70,0.78,0.90),
             'phase':3.14,'base_y':5.6,'wing_angle':0.0},
        ]

    # ── OBJ model loading ─────────────────────────────────────────────────────

    # Mapping from user-facing entity type → OBJ filename stem
    _ENTITY_OBJ_MAP = {
        "vehicle": "sedan",
        "uav":     "quad_uav",
        "bird":    "seagull",
        "drone":   "player_drone",   # the controlled drone itself
    }

    def _load_obj_models(self):
        try:
            from graphics.model_gen import ensure_models
            self._obj_meshes = ensure_models(_ASSETS)
            self.logger.info("OBJ models loaded: %s", list(self._obj_meshes.keys()))
        except Exception as exc:
            self.logger.warning("OBJ model load failed: %s — using procedural fallback", exc)
            self._obj_meshes = {}

    def import_model(self, entity_type: str, src_filepath: str) -> bool:
        """Copy *src_filepath* (OBJ) into assets/models and hot-reload it.

        Parameters
        ----------
        entity_type : ``"vehicle"`` | ``"uav"`` | ``"bird"`` | ``"drone"``
        src_filepath : absolute path to a .obj file chosen by the user

        Returns ``True`` on success.
        """
        import shutil
        stem = self._ENTITY_OBJ_MAP.get(entity_type)
        if stem is None:
            self.logger.warning("import_model: unknown entity type %r", entity_type)
            return False
        os.makedirs(_ASSETS, exist_ok=True)
        dest = os.path.join(_ASSETS, f"{stem}.obj")
        try:
            shutil.copy2(src_filepath, dest)
            self.logger.info("Imported model: %s → %s", src_filepath, dest)
        except Exception as exc:
            self.logger.error("import_model copy failed: %s", exc)
            return False

        # Hot-reload just this mesh
        try:
            from graphics.obj_loader import load_obj
            mesh = load_obj(dest)
            if mesh is not None:
                self._obj_meshes[stem] = mesh
                self.logger.info("Hot-reloaded mesh %r (%d tris)", stem, mesh.tri_count)
                return True
            else:
                self.logger.warning("import_model: load_obj returned None for %s", dest)
                return False
        except Exception as exc:
            self.logger.error("import_model reload failed: %s", exc)
            return False

    def _render_obj(self, mesh, r: float, g: float, b: float, scale: float = 1.0):
        """Render an ObjMesh with colour (r,g,b) and optional uniform scale."""
        if mesh is None or not OPENGL_AVAILABLE:
            return
        glColor3f(r, g, b)
        if scale != 1.0:
            glPushMatrix()
            glScalef(scale, scale, scale)
        glBegin(GL_TRIANGLES)
        for i0, i1, i2 in mesh.tris:
            for vi in (i0, i1, i2):
                nx, ny, nz = mesh.normals[vi]
                glNormal3f(nx, ny, nz)
                x, y, z = mesh.verts[vi]
                glVertex3f(x, y, z)
        glEnd()
        if scale != 1.0:
            glPopMatrix()

    # ── Public interface ──────────────────────────────────────────────────────

    def initialize_gimbal(self):      self.logger.info("Gimbal 3D model ready")
    def start_rendering(self):        self._render_timer.start(16)
    def cleanup(self):                self._render_timer.stop(); self._fps_timer.stop()

    def update_gimbal_position(self, position: dict):
        self.pan_angle  = position['pan']
        self.tilt_angle = position['tilt']
        if 'zoom_factor' in position:
            self.cam_fov = max(2.0, 60.0 / max(1.0, position['zoom_factor']))
        self.update()

    def update_drone_position(self, x: float, y: float, z: float):
        vx = x - self.drone_x
        vy = y - self.drone_y
        vz = z - self.drone_z
        horiz_speed = math.sqrt(vx * vx + vz * vz)

        # ── Yaw ───────────────────────────────────────────────────────────────
        yaw_delta = 0.0
        if self._tracking_yaw is not None:
            # Tracking assist: rotate body toward subject (slow, deliberate)
            yaw_delta      = (self._tracking_yaw - self.drone_yaw + 540) % 360 - 180
            self.drone_yaw += yaw_delta * 0.04
            # Level the bank while yaw-locking onto subject
            self.drone_roll += (0.0 - self.drone_roll) * 0.06
        elif horiz_speed > 0.0008:
            # Normal flight: face direction of travel
            target_yaw = math.degrees(math.atan2(vx, vz))
            yaw_delta  = (target_yaw - self.drone_yaw + 540) % 360 - 180
            self.drone_yaw += yaw_delta * 0.10
            # Bank into turns
            target_roll = max(-28.0, min(28.0, -yaw_delta * 1.8))
            self.drone_roll += (target_roll - self.drone_roll) * 0.07

        # ── Pitch: nose up when climbing, nose down when descending ───────────
        if horiz_speed > 0.0008:
            target_pitch = math.degrees(math.atan2(-vy, horiz_speed)) * 0.7
            target_pitch = max(-20.0, min(20.0, target_pitch))
        else:
            target_pitch = 0.0
        self.drone_pitch_anim += (target_pitch - self.drone_pitch_anim) * 0.08
        self._hspeed_mps = horiz_speed * 60   # m/frame → m/s at 60 fps

        self.drone_x = x
        self.drone_y = y
        self.drone_z = z

    def set_tracking_yaw(self, world_yaw: float):
        """Override drone body yaw to face a tracked subject."""
        self._tracking_yaw = world_yaw

    def clear_tracking_yaw(self):
        self._tracking_yaw = None

    def _gps_from_xyz(self, x: float, y: float, z: float) -> tuple:
        """Convert scene XYZ (m) → (lat°, lon°, alt_msl m).

        Scene axes: +X = East, +Z = North, +Y = Up.
        """
        home_lat = self.config.home_lat
        home_lon = self.config.home_lon
        home_alt = self.config.home_alt_msl
        lat_rad  = math.radians(home_lat)
        lat = home_lat + z / 111_320.0
        lon = home_lon + x / (111_320.0 * math.cos(lat_rad))
        alt = home_alt + y
        return lat, lon, alt

    def get_entities(self) -> list:        return self.entities
    def get_nearest_entity(self, entity_type: str) -> Optional[dict]:
        cands = [e for e in self.entities if e['type'] == entity_type]
        if not cands: return None
        return min(cands, key=lambda e: math.sqrt(
            (e['x']-self.drone_x)**2 + (e['y']-self.drone_y)**2 + (e['z']-self.drone_z)**2))

    def get_target_world_pos(self):
        if self.moving_object_enabled: return (self.obj_x, self.obj_z)
        if self.entities:
            n = min(self.entities, key=lambda e:
                    (e['x']-self.drone_x)**2 + (e['z']-self.drone_z)**2)
            return (n['x'], n['z'])
        return None

    def get_target_screen_pos(self):
        if not self.moving_object_enabled: return None
        p = self._project(self.obj_x, 0.17, self.obj_z)
        return p if p else (self.width()//2, self.height()//2)

    def get_gimbal_screen_geometry(self) -> dict:
        cx = self.width()//2; h = self.height()
        gy = self.drone_y - self.BODY_H/2 - self.ROD_LEN
        g  = self._project(self.drone_x, gy, self.drone_z)
        if g: gimbal_cy = g[1]; gimbal_mount_y = gimbal_cy - 20
        else: gimbal_cy = h//2; gimbal_mount_y = gimbal_cy - 20
        return {'cx':cx,'drone_cy':h//4,'gimbal_mount_y':gimbal_mount_y,'gimbal_cy':gimbal_cy}

    def set_moving_object_enabled(self, enabled: bool):
        self.moving_object_enabled = enabled
        if enabled:
            self.obj_x  = random.uniform(-2,2); self.obj_z  = random.uniform(-2,2)
            self.obj_vx = random.choice([-1,1])*random.uniform(.05,.10)
            self.obj_vz = random.choice([-1,1])*random.uniform(.04,.08)
        else: self.tracking_active = False; self.tracking_locked = False

    def set_tracking_active(self, a): self.tracking_active=a; self.tracking_locked = self.tracking_locked and a
    def set_tracking_locked(self, l): self.tracking_locked = l

    # ── Mouse controls ────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position()

    def mouseReleaseEvent(self, event):
        self._drag_start = None

    def mouseMoveEvent(self, event):
        if self._drag_start is None: return
        if event.buttons() & Qt.MouseButton.LeftButton:
            d = event.position() - self._drag_start
            self.cam_azimuth   += d.x() * 0.45
            self.cam_elevation -= d.y() * 0.30
            self.cam_elevation  = max(-8.0, min(82.0, self.cam_elevation))
            self._drag_start = event.position()
            self.update()

    def wheelEvent(self, event):
        self.cam_distance -= event.angleDelta().y() * 0.012
        self.cam_distance  = max(2.0, min(35.0, self.cam_distance))
        self.update()

    # ── Qt / OpenGL overrides ─────────────────────────────────────────────────

    def initializeGL(self):
        if not OPENGL_AVAILABLE: return
        glClearColor(0.04, 0.05, 0.09, 1.0)
        glEnable(GL_DEPTH_TEST); glDepthFunc(GL_LEQUAL)
        glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_NORMALIZE)
        glEnable(GL_LIGHTING); glEnable(GL_LIGHT0); glEnable(GL_LIGHT1)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glShadeModel(GL_SMOOTH)

        # Sun — warm, high upper-right
        glLightfv(GL_LIGHT0, GL_POSITION, [8.0, 14.0,  6.0, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE,  [0.95, 0.92, 0.84, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [1.00, 0.96, 0.88, 1.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT,  [0.07, 0.08, 0.11, 1.0])

        # Cool fill — lower-left
        glLightfv(GL_LIGHT1, GL_POSITION, [-5.0, 2.0, -5.0, 1.0])
        glLightfv(GL_LIGHT1, GL_DIFFUSE,  [0.10, 0.14, 0.22, 1.0])
        glLightfv(GL_LIGHT1, GL_SPECULAR, [0.0,  0.0,  0.0,  1.0])
        glLightfv(GL_LIGHT1, GL_AMBIENT,  [0.0,  0.0,  0.0,  1.0])

        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [0.06, 0.07, 0.09, 1.0])
        self.logger.info("OpenGL initialised")

    def resizeGL(self, w, h):
        if not OPENGL_AVAILABLE: return
        glViewport(0, 0, w, max(h, 1))

    def paintGL(self):
        if not OPENGL_AVAILABLE: return
        # Rebuild projection each frame so PTZ zoom (cam_fov) takes effect immediately
        w, h = self.width(), self.height()
        glMatrixMode(GL_PROJECTION); glLoadIdentity()
        gluPerspective(self.cam_fov, w / max(h, 1), 0.05, 500.0)
        glMatrixMode(GL_MODELVIEW)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        az = math.radians(self.cam_azimuth); el = math.radians(self.cam_elevation)
        d  = self.cam_distance
        cx = self.drone_x + d*math.cos(el)*math.sin(az)
        cy = self.drone_y + d*math.sin(el)
        cz = self.drone_z + d*math.cos(el)*math.cos(az)
        gluLookAt(cx, cy, cz, self.drone_x, self.drone_y, self.drone_z, 0,1,0)

        glLightfv(GL_LIGHT0, GL_POSITION, [8.0, 14.0,  6.0, 1.0])
        glLightfv(GL_LIGHT1, GL_POSITION, [-5.0, 2.0, -5.0, 1.0])

        self._cache_matrices()

        self._draw_sky()
        self._draw_ground()

        # Drone — body rotates with attitude; rod + gimbal stay world-vertical
        glPushMatrix()
        glTranslatef(self.drone_x, self.drone_y, self.drone_z)

        # Body: apply heading, pitch, banking
        glPushMatrix()
        glRotatef(self.drone_yaw,        0, 1, 0)
        glRotatef(self.drone_pitch_anim, 1, 0, 0)
        glRotatef(self.drone_roll,       0, 0, 1)
        self._draw_drone()
        glPopMatrix()

        # Gimbal rod — hangs straight down (stabilized, no attitude rotation)
        glPushMatrix()
        glTranslatef(0, -self.BODY_H/2, 0); glRotatef(180, 1, 0, 0)
        _mat_chrome(); glColor3f(0.55, 0.57, 0.60)
        _cylinder(0.012, self.ROD_LEN, 8); _mat_reset()
        glPopMatrix()

        # Gimbal head
        glTranslatef(0, -(self.BODY_H/2 + self.ROD_LEN), 0)
        self._draw_gimbal()
        glPopMatrix()

        # Entities
        t = time.time()
        self._update_entities(t)
        for e in self.entities: self._draw_entity(e, t)

        # Legacy ball
        if self.moving_object_enabled:
            self._update_ball(); self._draw_ball()

        self.prop_angle  = (self.prop_angle  + 9.0) % 360.0
        self.bird_phase += 0.07
        self.frame_count += 1

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_hud(painter)
        painter.end()

    # ── Per-frame ─────────────────────────────────────────────────────────────

    def _on_frame(self):   self.update()
    def _tick_fps(self):
        now = time.time(); dt = now - self.last_fps_t
        if dt > 0: self.current_fps = self.frame_count / dt
        self.fps_updated.emit(self.current_fps)
        self.frame_count = 0; self.last_fps_t = now

    def _cache_matrices(self):
        try:
            self._model_mx = glGetDoublev(GL_MODELVIEW_MATRIX)
            self._proj_mx  = glGetDoublev(GL_PROJECTION_MATRIX)
            self._viewport = glGetIntegerv(GL_VIEWPORT)
        except Exception: pass

    def _project(self, wx, wy, wz):
        if self._proj_mx is None: return None
        try:
            sx, sy, _ = gluProject(wx, wy, wz, self._model_mx, self._proj_mx, self._viewport)
            return (int(sx), self.height()-int(sy))
        except Exception: return None

    # ── Environment ───────────────────────────────────────────────────────────

    def _draw_sky(self):
        glDisable(GL_LIGHTING); glDisable(GL_DEPTH_TEST)
        glMatrixMode(GL_PROJECTION); glPushMatrix(); glLoadIdentity(); glOrtho(-1,1,-1,1,-1,1)
        glMatrixMode(GL_MODELVIEW); glPushMatrix(); glLoadIdentity()
        glBegin(GL_QUADS)
        glColor3f(0.02,0.03,0.07); glVertex2f(-1,1); glVertex2f(1,1)
        glColor3f(0.07,0.10,0.17); glVertex2f(1,-1); glVertex2f(-1,-1)
        glEnd()
        glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)
        glEnable(GL_DEPTH_TEST); glEnable(GL_LIGHTING)

    def _draw_ground(self):
        glDisable(GL_LIGHTING); G = 12

        # Base fill
        glBegin(GL_QUADS)
        glColor3f(0.065, 0.082, 0.062)
        glVertex3f(-G,0,-G); glVertex3f(G,0,-G); glVertex3f(G,0,G); glVertex3f(-G,0,G)
        glEnd()

        # Checker
        y = 0.0003
        glBegin(GL_QUADS)
        glColor3f(0.088, 0.108, 0.085)
        for ix in range(-G,G):
            for iz in range(-G,G):
                if (ix+iz)%2==0:
                    glVertex3f(ix,y,iz); glVertex3f(ix+1,y,iz)
                    glVertex3f(ix+1,y,iz+1); glVertex3f(ix,y,iz+1)
        glEnd()

        # Grid
        glLineWidth(1.0); glColor4f(0.14,0.18,0.13,0.45)
        glBegin(GL_LINES)
        for i in range(-G,G+1):
            glVertex3f(i,0.002,-G); glVertex3f(i,0.002,G)
            glVertex3f(-G,0.002,i); glVertex3f(G,0.002,i)
        glEnd()

        # Helipad at origin
        self._draw_helipad()

        # North direction indicator
        self._draw_north_arrow()

        glLineWidth(1.0); glEnable(GL_LIGHTING)

    def _draw_north_arrow(self):
        """Draw a North-pointing arrow on the ground (+Z = North in this scene)."""
        y  = 0.007
        ax, az = -8.2, -7.8   # arrow base (South end of shaft)
        glLineWidth(3.0)
        glColor4f(0.95, 0.88, 0.22, 0.88)
        glBegin(GL_LINES)
        glVertex3f(ax, y, az - 0.5)   # tail
        glVertex3f(ax, y, az + 0.5)   # head (pointing +Z = North)
        glEnd()
        glBegin(GL_TRIANGLES)          # arrowhead
        glVertex3f(ax,        y, az + 0.70)
        glVertex3f(ax - 0.20, y, az + 0.25)
        glVertex3f(ax + 0.20, y, az + 0.25)
        glEnd()
        glLineWidth(1.0)

    def _draw_helipad(self):
        y = 0.004
        # Outer circle
        glLineWidth(3.0); glColor4f(0.90, 0.70, 0.10, 0.90)
        segs = 40
        glBegin(GL_LINE_LOOP)
        for i in range(segs):
            a = 2*math.pi*i/segs; glVertex3f(1.4*math.cos(a), y, 1.4*math.sin(a))
        glEnd()
        # Inner fill (faint)
        glColor4f(0.60, 0.50, 0.06, 0.15)
        glBegin(GL_TRIANGLE_FAN); glVertex3f(0,y,0)
        for i in range(segs+1):
            a = 2*math.pi*i/segs; glVertex3f(1.4*math.cos(a),y,1.4*math.sin(a))
        glEnd()
        # H marking
        glLineWidth(4.0); glColor4f(0.90, 0.72, 0.10, 0.90)
        glBegin(GL_LINES)
        glVertex3f(-0.40,y,0.55); glVertex3f(-0.40,y,-0.55)
        glVertex3f( 0.40,y,0.55); glVertex3f( 0.40,y,-0.55)
        glVertex3f(-0.40,y, 0.0); glVertex3f( 0.40,y, 0.0)
        glEnd()
        glLineWidth(1.0)

    # ── Main drone model ──────────────────────────────────────────────────────

    def _draw_drone(self):
        # Body shell
        _mat_drone_shell(); glColor3f(0.24, 0.26, 0.30)
        _box(0.74, self.BODY_H, 0.48)

        # Camera window (front)
        glPushMatrix(); glTranslatef(0,0,0.244)
        _mat_glass(); glColor3f(0.08,0.30,0.58)
        _box(0.16,0.072,0.008); glPopMatrix()

        # Battery lid (top, slightly recessed)
        _mat_matte(); glColor3f(0.18,0.20,0.22)
        glPushMatrix(); glTranslatef(0,0.064,0); _box(0.32,0.006,0.22); glPopMatrix()

        # LEDs
        glDisable(GL_LIGHTING)
        glColor4f(0.08,1.0,0.20,1.0); glPushMatrix(); glTranslatef(-0.20,0.072,0.0)
        _sphere(0.022,7,7); glPopMatrix()
        glColor4f(1.0,0.45,0.0,1.0); glPushMatrix(); glTranslatef(0.20,0.072,0.0)
        _sphere(0.022,7,7); glPopMatrix()
        glEnable(GL_LIGHTING)

        # Landing skids
        _mat_matte(); glColor3f(0.20,0.22,0.24)
        for sx in (-0.32, 0.32):
            glPushMatrix(); glTranslatef(sx,-self.BODY_H/2-0.02,0)
            glRotatef(90,0,0,1); _cylinder(0.013,0.045,8); glPopMatrix()
            glPushMatrix(); glTranslatef(sx,-self.BODY_H/2-0.038,0)
            _cylinder(0.009,0.62,6); glPopMatrix()

        # Arms
        arm_tips = [(0.55,0,0.42),(-0.55,0,0.42),(0.55,0,-0.42),(-0.55,0,-0.42)]
        glDisable(GL_LIGHTING); glLineWidth(7.0); glColor3f(0.20,0.22,0.25)
        glBegin(GL_LINES)
        for ax,ay,az in arm_tips: glVertex3f(0,0,0); glVertex3f(ax,ay,az)
        glEnd(); glLineWidth(1.0); glEnable(GL_LIGHTING)

        # Motor pods + propellers
        for ax,ay,az in arm_tips:
            glPushMatrix(); glTranslatef(ax,ay,az)
            _mat_matte(); glColor3f(0.16,0.18,0.20)
            _cylinder(0.046,0.075,16)
            glTranslatef(0,0.078,0)
            spin = self.prop_angle if (ax>0)==(az>0) else -self.prop_angle
            glRotatef(spin,0,1,0)
            glDisable(GL_LIGHTING)
            glColor4f(0.12,0.48,0.88,0.26); _disc(0.32,22)
            glColor4f(0.20,0.60,1.0,0.78)
            glLineWidth(2.4)
            glBegin(GL_LINES)
            glVertex3f(-0.30,0,0); glVertex3f(0.30,0,0)
            glVertex3f(0,0,-0.30); glVertex3f(0,0,0.30)
            glEnd(); glLineWidth(1.0); glEnable(GL_LIGHTING); glPopMatrix()

    # ── Gimbal assembly ───────────────────────────────────────────────────────

    def _draw_gimbal(self):
        _mat_matte(); glColor3f(0.40,0.42,0.44); _box(0.26,0.042,0.075)
        glPushMatrix(); glRotatef(self.pan_angle,0,1,0)
        _mat_chrome(); glColor3f(0.28,0.52,0.88); _torus(0.175,0.023,32,10)
        glRotatef(-self.tilt_angle,1,0,0)
        glColor3f(0.16,0.38,0.72); glPushMatrix(); glRotatef(90,0,1,0); _torus(0.130,0.019,28,9); glPopMatrix()
        glDisable(GL_LIGHTING); glLineWidth(5.0); glColor3f(0.36,0.38,0.40)
        glBegin(GL_LINES); glVertex3f(0,0,0); glVertex3f(0,-self.CAM_ARM,0); glEnd()
        glLineWidth(1.0); glEnable(GL_LIGHTING)
        glTranslatef(0,-self.CAM_ARM,0)
        _mat_matte(); glColor3f(0.14,0.52,0.14); _box(0.17,0.118,0.19)
        glPushMatrix(); glTranslatef(0,0,0.098); glRotatef(90,1,0,0)
        _mat_chrome(); glColor3f(0.14,0.40,0.78); _cylinder(0.046,0.048,18); glPopMatrix()
        glDisable(GL_LIGHTING)
        _mat_glass(); glColor4f(0.28,0.70,1.0,0.72)
        glPushMatrix(); glTranslatef(0,0,0.118); glRotatef(90,1,0,0); _disc(0.037,18); glPopMatrix()
        glColor4f(0.26,0.65,1.0,0.07)
        glPushMatrix(); glTranslatef(0,0,0.120); glRotatef(-90,1,0,0); _cone(0.44,0.90,22); glPopMatrix()
        glEnable(GL_LIGHTING); _mat_reset()
        glPopMatrix()

    # ── Entity physics ────────────────────────────────────────────────────────

    def _update_entities(self, t: float):
        B = 6.0
        for e in self.entities:
            e['x'] += e['vx']; e['z'] += e['vz']
            if e['type'] != 'vehicle':
                e['y'] = e['base_y'] + 0.22*math.sin(t*1.35+e['phase'])
            if e['type'] == 'bird':
                e['wing_angle'] = 28.0*math.sin(t*4.0+e['phase'])
            if random.random() < 0.007:
                e['vx'] += random.uniform(-0.005,0.005)
                e['vz'] += random.uniform(-0.005,0.005)
                spd = math.sqrt(e['vx']**2+e['vz']**2)
                mx  = 0.09 if e['type']=='bird' else 0.055
                if spd>mx: e['vx']=e['vx']/spd*mx; e['vz']=e['vz']/spd*mx
                elif spd<0.015: e['vx']=math.copysign(0.025,e['vx'])
            if abs(e['x'])>B: e['vx']=-e['vx']; e['x']=math.copysign(B,e['x'])
            if abs(e['z'])>B: e['vz']=-e['vz']; e['z']=math.copysign(B,e['z'])

    # ── Entity rendering ──────────────────────────────────────────────────────

    def _draw_entity(self, e: dict, t: float):
        glPushMatrix()
        glTranslatef(e['x'], e['y'], e['z'])
        # Rotate to face direction of movement
        spd2 = e['vx']**2 + e['vz']**2
        if spd2 > 1e-6:
            heading = -math.degrees(math.atan2(e['vz'], e['vx']))
            glRotatef(heading, 0, 1, 0)
        r,g,b = e['color']
        if   e['type'] == 'vehicle': self._draw_car(r,g,b)
        elif e['type'] == 'uav':     self._draw_mini_uav(r,g,b)
        elif e['type'] == 'bird':    self._draw_bird(r,g,b, e.get('wing_angle',0))
        glPopMatrix()

    def _draw_car(self, r, g, b):
        """Sedan — OBJ mesh with specular paint if available, else procedural."""
        mesh = self._obj_meshes.get("sedan")
        if mesh is not None:
            _mat_car_paint(r, g, b)
            self._render_obj(mesh, r, g, b)
            _mat_reset()
            return

        # ── Procedural fallback ──────────────────────────────────────────────
        # CHASSIS UNDERSIDE
        _mat_matte(); glColor3f(r*0.25,g*0.25,b*0.25); _box(0.68,0.10,0.36)

        # BODY LOWER
        _mat_car_paint(r,g,b); glColor3f(r,g,b)
        glPushMatrix(); glTranslatef(0,0.105,0); _box(0.70,0.16,0.37); glPopMatrix()

        # HOOD (angled)
        glPushMatrix(); glTranslatef(0.185,0.195,0); glRotatef(-14,0,0,1)
        _box(0.33,0.030,0.35); glPopMatrix()

        # TRUNK (angled opposite)
        glPushMatrix(); glTranslatef(-0.195,0.195,0); glRotatef(11,0,0,1)
        _box(0.28,0.028,0.35); glPopMatrix()

        # CABIN (slightly narrower, lighter shade for roof)
        glColor3f(min(1,r*0.92+0.05),min(1,g*0.92+0.05),min(1,b*0.92+0.05))
        glPushMatrix(); glTranslatef(-0.025,0.295,0); _box(0.38,0.195,0.330); glPopMatrix()

        # WINDSHIELD (front)
        _mat_glass()
        glDisable(GL_LIGHTING); glColor4f(0.08,0.14,0.26,0.82)
        glPushMatrix(); glTranslatef(0.115,0.315,0); glRotatef(-22,0,0,1)
        _box(0.175,0.155,0.300); glPopMatrix()
        # REAR WINDOW
        glPushMatrix(); glTranslatef(-0.148,0.310,0); glRotatef(22,0,0,1)
        _box(0.135,0.150,0.290); glPopMatrix()
        # SIDE WINDOWS (left + right)
        glColor4f(0.08,0.14,0.26,0.70)
        for sz in (0.170,-0.170):
            glPushMatrix(); glTranslatef(-0.012,0.300,sz)
            _box(0.275,0.145,0.008); glPopMatrix()
        glEnable(GL_LIGHTING)

        # WHEELS (4x) — tyre + rim
        for wx,wz in ((0.24,0.195),(-0.24,0.195),(0.24,-0.195),(-0.24,-0.195)):
            # Tyre
            _mat_rubber(); glColor3f(0.06,0.06,0.06)
            glPushMatrix(); glTranslatef(wx,0.0,wz); glRotatef(90,0,0,1)
            _cylinder(0.108,0.068,18); glPopMatrix()
            # Outer rim
            _mat_chrome(); glColor3f(0.72,0.76,0.82)
            glPushMatrix(); glTranslatef(wx,0.0,wz+0.035); glRotatef(90,0,0,1)
            _disc(0.078,14); glPopMatrix()
            # Inner rim
            glPushMatrix(); glTranslatef(wx,0.0,wz-0.035); glRotatef(-90,0,0,1)
            _disc(0.072,14); glPopMatrix()
            # Hub
            glColor3f(0.55,0.58,0.62)
            glPushMatrix(); glTranslatef(wx,0.0,wz+0.036); glRotatef(90,0,0,1)
            _cylinder(0.028,0.010,8); glPopMatrix()
            # Spokes (3)
            glDisable(GL_LIGHTING); glLineWidth(2.2); glColor3f(0.60,0.64,0.70)
            for sa in range(3):
                ang = math.radians(sa*120)
                glBegin(GL_LINES)
                glVertex3f(wx,0.0,wz+0.034)
                glVertex3f(wx+math.cos(ang)*0.068,math.sin(ang)*0.068,wz+0.034)
                glEnd()
            glLineWidth(1.0); glEnable(GL_LIGHTING)

        # BUMPERS
        _mat_matte(); glColor3f(0.12,0.12,0.12)
        glPushMatrix(); glTranslatef( 0.355,0.085,0); _box(0.018,0.072,0.310); glPopMatrix()
        glPushMatrix(); glTranslatef(-0.355,0.085,0); _box(0.018,0.072,0.310); glPopMatrix()

        # HEADLIGHTS (yellow-white)
        glDisable(GL_LIGHTING)
        glColor3f(1.0,0.96,0.84)
        for sz in (0.12,-0.12):
            glPushMatrix(); glTranslatef(0.354,0.155,sz); _sphere(0.042,9,7); glPopMatrix()
        # TAILLIGHTS (red)
        glColor3f(0.88,0.08,0.08)
        for sz in (0.10,-0.10):
            glPushMatrix(); glTranslatef(-0.354,0.140,sz); _sphere(0.036,9,7); glPopMatrix()
        glEnable(GL_LIGHTING)
        _mat_reset()

    def _draw_mini_uav(self, r, g, b):
        """Mini-UAV — OBJ mesh if available, else procedural."""
        mesh = self._obj_meshes.get("quad_uav")
        if mesh is not None:
            _mat_drone_shell()
            self._render_obj(mesh, r*0.88, g*0.88, b*0.88)
            _mat_reset()
            return

        # ── Procedural fallback ──────────────────────────────────────────────
        # Body (flat hexagonal-ish box)
        _mat_drone_shell(); glColor3f(r*0.9,g*0.9,b*0.9)
        _box(0.22, 0.06, 0.16)

        # Battery hump on top
        glColor3f(r*0.7,g*0.7,b*0.7)
        glPushMatrix(); glTranslatef(0,0.045,0); _box(0.12,0.04,0.08); glPopMatrix()

        # Camera pod under front
        _mat_glass(); glColor3f(0.08,0.30,0.60)
        glPushMatrix(); glTranslatef(0.08,-0.042,0); _sphere(0.028,10,8); glPopMatrix()

        # Arms (4 diagonal)
        arm_tips_s = [(0.26,0,0.18),(-0.26,0,0.18),(0.26,0,-0.18),(-0.26,0,-0.18)]
        glDisable(GL_LIGHTING); glLineWidth(4.5)
        glColor3f(r*0.6,g*0.6,b*0.6)
        glBegin(GL_LINES)
        for ax,ay,az in arm_tips_s: glVertex3f(0,0,0); glVertex3f(ax,ay,az)
        glEnd()
        glLineWidth(1.0)

        # Motor pods + prop discs
        for ax,ay,az in arm_tips_s:
            glPushMatrix(); glTranslatef(ax,ay,az)
            glColor3f(0.15,0.16,0.18); _cylinder(0.030,0.040,12)
            glTranslatef(0,0.042,0)
            spin = self.prop_angle if (ax>0)==(az>0) else -self.prop_angle
            glRotatef(spin,0,1,0)
            glColor4f(r,g,b,0.30); _disc(0.19,16)
            glColor4f(r,g,b,0.80)
            glLineWidth(1.8)
            glBegin(GL_LINES)
            glVertex3f(-0.17,0,0); glVertex3f(0.17,0,0)
            glVertex3f(0,0,-0.17); glVertex3f(0,0,0.17)
            glEnd(); glLineWidth(1.0); glPopMatrix()

        glEnable(GL_LIGHTING); _mat_reset()

    def _draw_bird(self, r, g, b, wing_angle: float):
        """Bird — OBJ mesh with animated wing rotation if available, else procedural."""
        mesh = self._obj_meshes.get("seagull")
        if mesh is not None:
            _mat_matte()
            glPushMatrix()
            # Animated wing flap: rotate around X axis for left/right halves is
            # baked into the mesh; we tilt the whole model slightly with wing_angle
            glRotatef(wing_angle * 0.4, 0, 0, 1)   # gentle whole-body roll as wings flap
            self._render_obj(mesh, r, g, b)
            glPopMatrix()
            _mat_reset()
            return

        # ── Procedural fallback ──────────────────────────────────────────────
        # Body (elongated ellipsoid via scaled sphere)
        _mat_matte(); glColor3f(r,g,b)
        glPushMatrix(); glScalef(1.0, 0.65, 1.8); _sphere(0.072, 12, 9); glPopMatrix()

        # Head
        glPushMatrix(); glTranslatef(0,0.06,0.14); glScalef(0.8,0.8,0.8)
        _sphere(0.055,10,8); glPopMatrix()

        # Beak
        glDisable(GL_LIGHTING); glColor3f(1.0,0.82,0.20); glLineWidth(2.5)
        glBegin(GL_LINES)
        glVertex3f(0,0.055,0.18); glVertex3f(0,0.038,0.26)
        glEnd(); glLineWidth(1.0); glEnable(GL_LIGHTING)

        # Tail feathers
        glColor3f(r*0.88,g*0.88,b*0.88)
        glPushMatrix(); glTranslatef(0,-0.010,-0.14); glRotatef(15,1,0,0)
        _box(0.062, 0.022, 0.090); glPopMatrix()

        # Wings — left and right, flapping
        wa = math.radians(wing_angle)
        for side, sign in ((1,1),(-1,-1)):
            glPushMatrix()
            glTranslatef(sign*0.040, 0, 0)
            glRotatef(sign*math.degrees(wa), 0, 0, 1)
            # Inner wing
            glColor3f(r,g,b)
            _box(0.19, 0.015, 0.11)
            # Outer wing tip
            glPushMatrix(); glTranslatef(sign*0.18, -0.006, -0.02)
            glRotatef(sign*5, 0, 0, 1)
            _box(0.14, 0.010, 0.08); glPopMatrix()
            glPopMatrix()

        _mat_reset()

    # ── Legacy ball ───────────────────────────────────────────────────────────

    def _update_ball(self):
        B=3.4
        if random.random()<.025: self.obj_vx+=random.uniform(-.012,.012); self.obj_vz+=random.uniform(-.012,.012)
        self.obj_x+=self.obj_vx; self.obj_z+=self.obj_vz
        if abs(self.obj_x)>B: self.obj_vx=-self.obj_vx; self.obj_x=math.copysign(B,self.obj_x)
        if abs(self.obj_z)>B: self.obj_vz=-self.obj_vz; self.obj_z=math.copysign(B,self.obj_z)

    def _draw_ball(self):
        ox,oz=self.obj_x,self.obj_z; R=0.17
        glDisable(GL_LIGHTING)
        glColor4f(0,0,0,.38)
        glPushMatrix(); glTranslatef(ox,.001,oz); glRotatef(90,1,0,0); _disc(R*.9,16); glPopMatrix()
        glColor4f(0,1,.3,.25) if self.tracking_locked else (glColor4f(1,.8,0,.20) if self.tracking_active else glColor4f(1,.68,0,.16))
        glPushMatrix(); glTranslatef(ox,.004,oz); glRotatef(90,1,0,0); _disc(R*2.,20); glPopMatrix()
        glEnable(GL_LIGHTING)
        glPushMatrix(); glTranslatef(ox,R+.01,oz)
        glColor3f(0,.9,.3) if self.tracking_locked else (glColor3f(.95,.78,0) if self.tracking_active else glColor3f(.98,.68,0))
        _sphere(R,18,14); glPopMatrix()

    # ── HUD ───────────────────────────────────────────────────────────────────

    def _draw_hud(self, painter: QPainter):
        w, h = self.width(), self.height()

        # PTZ gimbal axes — top-right
        painter.setPen(QPen(QColor(210, 210, 215, 230)))
        painter.setFont(QFont("Consolas", 10))
        painter.drawText(w - 210, 22, f"Pan:  {self.pan_angle:+.1f}°")
        painter.drawText(w - 210, 38, f"Tilt: {self.tilt_angle:+.1f}°")
        zoom_factor = max(1.0, 60.0 / self.cam_fov)
        painter.setPen(QPen(QColor(255, 152, 0, 230)))
        painter.drawText(w - 210, 54, f"Zoom: {zoom_factor:.1f}×  ({self.cam_fov:.0f}°)")

        # GPS coordinates
        lat, lon, alt_msl = self._gps_from_xyz(self.drone_x, self.drone_y, self.drone_z)
        ns = 'N' if lat >= 0 else 'S'
        ew = 'E' if lon >= 0 else 'W'
        hdg = self.drone_yaw % 360
        spd_kmh = self._hspeed_mps * 3.6
        painter.setPen(QPen(QColor(155, 198, 155, 215)))
        painter.setFont(QFont("Consolas", 8))
        painter.drawText(w - 210, 70, f"{abs(lat):.5f}°{ns}  {abs(lon):.5f}°{ew}")
        painter.drawText(w - 210, 83, f"Alt: {alt_msl:.1f}m MSL   Hdg: {hdg:.0f}°")
        painter.drawText(w - 210, 96, f"Speed: {self._hspeed_mps:.2f} m/s  ({spd_kmh:.1f} km/h)")

        # FPS
        painter.setPen(QPen(QColor(80,140,80,170)))
        painter.drawText(w-68, h-10, f"{self.current_fps:.0f} FPS")

        # Mouse hint
        painter.setPen(QPen(QColor(95,95,108,130)))
        painter.setFont(QFont("Consolas",8))
        painter.drawText(8, h-10, "Drag: orbit   Scroll: zoom")

        # Pan compass
        icx,icy,ir = 60,64,36
        painter.setPen(QPen(QColor(44,46,56,215)))
        painter.setBrush(QColor(14,16,22,215))
        painter.drawEllipse(icx-ir-9,icy-ir-9,(ir+9)*2,(ir+9)*2)
        painter.setPen(QPen(QColor(60,63,76)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(icx-ir,icy-ir,ir*2,ir*2)
        painter.setPen(QPen(QColor(100,104,118)))
        painter.setFont(QFont("Consolas",7))
        painter.drawText(icx-3,icy-ir-2,"F"); painter.drawText(icx-3,icy+ir+10,"B")
        painter.drawText(icx-ir-12,icy+4,"L"); painter.drawText(icx+ir+3,icy+4,"R")
        pr = math.radians(self.pan_angle)
        ax = icx+int((ir-6)*math.sin(pr)); ay = icy-int((ir-6)*math.cos(pr))
        painter.setPen(QPen(QColor(42,130,218),2)); painter.drawLine(icx,icy,ax,ay)
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(42,130,218))
        painter.drawEllipse(ax-4,ay-4,8,8)
        painter.setPen(QPen(QColor(42,130,218)))
        painter.setFont(QFont("Consolas",7,QFont.Weight.Bold))
        painter.drawText(icx-18,icy+ir+22,"TOP VIEW")

        # North arrow "N" label — projected from the 3D arrow tip
        north_pt = self._project(-8.2, 0.1, -7.1)
        if north_pt and 0 < north_pt[0] < w and 0 < north_pt[1] < h:
            painter.setPen(QPen(QColor(230, 215, 55, 220)))
            painter.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            painter.drawText(north_pt[0] - 4, north_pt[1] - 4, "N")

        # Entity labels
        ec = {'vehicle':QColor(255,148,50,225),'uav':QColor(175,100,255,225),'bird':QColor(200,210,222,200)}
        painter.setFont(QFont("Consolas",8,QFont.Weight.Bold))
        for e in self.entities:
            pt = self._project(e['x'], e['y']+0.32, e['z'])
            if pt is None: continue
            sx,sy = pt
            if 10<sx<w-10 and 10<sy<h-10:
                painter.setPen(QPen(ec.get(e['type'],QColor(255,255,255,200))))
                painter.drawText(sx+5,sy-2,e['label'])

        # Tracking badge
        if self.tracking_active and self.moving_object_enabled:
            bc = QColor(0,200,70) if self.tracking_locked else QColor(220,170,0)
            bt = "LOCKED" if self.tracking_locked else "TRACKING"
            bw=94; bx=w//2-bw//2
            painter.setPen(QPen(bc,1)); painter.setBrush(QColor(bc.red(),bc.green(),bc.blue(),44))
            painter.drawRoundedRect(bx,8,bw,22,4,4)
            painter.setPen(QPen(bc)); painter.setFont(QFont("Consolas",9,QFont.Weight.Bold))
            painter.drawText(bx+6,24,bt)


# ── OpenGL geometry primitives ────────────────────────────────────────────────

def _box(w, h, d):
    hw,hh,hd=w/2,h/2,d/2
    glBegin(GL_QUADS)
    glNormal3f(0,0,1);  glVertex3f(-hw,-hh,hd);  glVertex3f(hw,-hh,hd);  glVertex3f(hw,hh,hd);  glVertex3f(-hw,hh,hd)
    glNormal3f(0,0,-1); glVertex3f(hw,-hh,-hd);  glVertex3f(-hw,-hh,-hd); glVertex3f(-hw,hh,-hd); glVertex3f(hw,hh,-hd)
    glNormal3f(-1,0,0); glVertex3f(-hw,-hh,-hd); glVertex3f(-hw,-hh,hd);  glVertex3f(-hw,hh,hd); glVertex3f(-hw,hh,-hd)
    glNormal3f(1,0,0);  glVertex3f(hw,-hh,hd);   glVertex3f(hw,-hh,-hd);  glVertex3f(hw,hh,-hd); glVertex3f(hw,hh,hd)
    glNormal3f(0,1,0);  glVertex3f(-hw,hh,hd);   glVertex3f(hw,hh,hd);    glVertex3f(hw,hh,-hd); glVertex3f(-hw,hh,-hd)
    glNormal3f(0,-1,0); glVertex3f(-hw,-hh,-hd);  glVertex3f(hw,-hh,-hd); glVertex3f(hw,-hh,hd); glVertex3f(-hw,-hh,hd)
    glEnd()

def _cylinder(radius, height, segs=16):
    step = 2*math.pi/segs
    glBegin(GL_QUAD_STRIP)
    for i in range(segs+1):
        a=i*step; nx,nz=math.cos(a),math.sin(a)
        glNormal3f(nx,0,nz); glVertex3f(radius*nx,0,radius*nz); glVertex3f(radius*nx,height,radius*nz)
    glEnd()
    glNormal3f(0,1,0); glBegin(GL_TRIANGLE_FAN); glVertex3f(0,height,0)
    for i in range(segs+1): a=i*step; glVertex3f(radius*math.cos(a),height,radius*math.sin(a))
    glEnd()
    glNormal3f(0,-1,0); glBegin(GL_TRIANGLE_FAN); glVertex3f(0,0,0)
    for i in range(segs+1): a=-i*step; glVertex3f(radius*math.cos(a),0,radius*math.sin(a))
    glEnd()

def _disc(radius, segs=16):
    step=2*math.pi/segs; glNormal3f(0,1,0)
    glBegin(GL_TRIANGLE_FAN); glVertex3f(0,0,0)
    for i in range(segs+1): a=i*step; glVertex3f(radius*math.cos(a),0,radius*math.sin(a))
    glEnd()

def _cone(base_r, height, segs=16):
    step=2*math.pi/segs
    glBegin(GL_TRIANGLE_FAN); glVertex3f(0,height,0)
    for i in range(segs+1):
        a=i*step; glNormal3f(math.cos(a),.3,math.sin(a)); glVertex3f(base_r*math.cos(a),0,base_r*math.sin(a))
    glEnd()

def _sphere(radius, slices=14, stacks=10):
    for i in range(stacks):
        lat0=math.pi*(-0.5+i/stacks); lat1=math.pi*(-0.5+(i+1)/stacks)
        z0,zr0=math.sin(lat0),math.cos(lat0); z1,zr1=math.sin(lat1),math.cos(lat1)
        glBegin(GL_QUAD_STRIP)
        for j in range(slices+1):
            lng=2*math.pi*j/slices; x,y=math.cos(lng),math.sin(lng)
            glNormal3f(x*zr0,z0,y*zr0); glVertex3f(radius*x*zr0,radius*z0,radius*y*zr0)
            glNormal3f(x*zr1,z1,y*zr1); glVertex3f(radius*x*zr1,radius*z1,radius*y*zr1)
        glEnd()

def _torus(major_r, minor_r, maj_segs=26, min_segs=9):
    for i in range(maj_segs):
        a0=2*math.pi*i/maj_segs; a1=2*math.pi*(i+1)/maj_segs
        glBegin(GL_QUAD_STRIP)
        for j in range(min_segs+1):
            b=2*math.pi*j/min_segs
            for a in (a0,a1):
                nx=math.cos(a)*math.cos(b); ny=math.sin(b); nz=math.sin(a)*math.cos(b)
                px=(major_r+minor_r*math.cos(b))*math.cos(a); py=minor_r*math.sin(b)
                pz=(major_r+minor_r*math.cos(b))*math.sin(a)
                glNormal3f(nx,ny,nz); glVertex3f(px,py,pz)
        glEnd()
