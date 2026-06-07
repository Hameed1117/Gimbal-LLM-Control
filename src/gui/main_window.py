"""Main Window — Gimbal LLM Control Application."""

import math
import logging
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QFrame, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence

from core.drone_autopilot import DroneAutoPilot, BODY_H, ROD_LEN

# Gimbal comfort-zone thresholds for coordinated drone+gimbal assist
_PAN_ASSIST_ON   = 75.0
_PAN_ASSIST_OFF  = 40.0
_TILT_ASSIST_ON  = 55.0
_TILT_ASSIST_OFF = 30.0


def _rgb_name(r: float, g: float, b: float) -> str:
    if r > 0.7 and g < 0.4 and b < 0.3:  return "orange/red"
    if r < 0.3 and g < 0.6 and b > 0.6:  return "blue"
    if r < 0.4 and g > 0.5 and b < 0.4:  return "green"
    if r > 0.8 and g > 0.7 and b < 0.3:  return "yellow"
    if r > 0.5 and g < 0.35 and b > 0.7: return "purple"
    if r > 0.7 and g > 0.8 and b > 0.8:  return "silver/white"
    if r > 0.5 and g > 0.6 and b > 0.7:  return "steel-blue"
    if r > 0.7 and g > 0.4 and b < 0.3:  return "orange"
    return f"rgb({r:.2f},{g:.2f},{b:.2f})"


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, config, llm_service, gimbal_controller):
        super().__init__()

        self.config            = config
        self.llm_service       = llm_service
        self.gimbal_controller = gimbal_controller
        self.logger            = logging.getLogger(__name__)

        from gui.control_panel import ControlPanel
        from gui.status_panel  import StatusPanel
        from graphics.renderer import GimbalRenderer

        self.control_panel = ControlPanel(config, gimbal_controller)
        self.status_panel  = StatusPanel(config, gimbal_controller)
        self.renderer      = GimbalRenderer(config)

        # ── Drone (physics-based, starts on ground) ───────────────────────────
        self.drone = DroneAutoPilot()

        # ── Gimbal entity tracking (LLM "track" command) ──────────────────────
        self._tracking_entity    = None
        self._yaw_assist_active  = False
        self._tilt_assist_active = False

        # Legacy ball tracking (control-panel checkbox)
        self.tracking_active       = False
        self.moving_object_enabled = False

        self.setup_window()
        self.setup_menu()
        self.setup_ui()
        self.setup_connections()

        self.renderer.initialize_gimbal()
        self.renderer.start_rendering()
        self._update_llm_display()

        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._tick)
        self.update_timer.start(16)   # ~60 fps

        self.logger.info("MainWindow initialised")

    # ── Window / UI setup ─────────────────────────────────────────────────────

    def setup_window(self):
        self.setWindowTitle("Gimbal LLM Control v2.0")
        self.setGeometry(100, 100, 1400, 900)
        self.setMinimumSize(1000, 600)
        self.setStyleSheet("""
            QMainWindow { background-color: #1a1a1a; color: white; }
            QWidget { background-color: #1a1a1a; color: white;
                      font-family: 'Segoe UI', sans-serif; }
            QGroupBox { font-weight: bold; border: 1px solid #404040;
                        border-radius: 8px; margin: 8px 0px; padding-top: 10px;
                        background-color: #2a2a2a; }
            QGroupBox::title { subcontrol-origin: margin;
                               subcontrol-position: top center;
                               padding: 0 5px; color: #ffffff; }
            QPushButton { background-color: #3a3a3a; border: 1px solid #555555;
                          border-radius: 6px; padding: 8px 16px; font-weight: 500; }
            QPushButton:hover   { background-color: #4a4a4a; border-color: #2a82da; }
            QPushButton:pressed { background-color: #2a82da; }
        """)

    def setup_menu(self):
        menu_bar = self.menuBar()
        menu_bar.setStyleSheet("""
            QMenuBar { background-color: #1a1a1a; color: #cccccc;
                       border-bottom: 1px solid #333333; }
            QMenuBar::item:selected { background-color: #2a2a2a; color: white; }
            QMenu { background-color: #252525; color: #cccccc;
                    border: 1px solid #404040; }
            QMenu::item:selected { background-color: #2a82da; color: white; }
        """)
        file_menu = self.menuBar().addMenu("File")

        # 3D model import sub-menu
        models_menu = file_menu.addMenu("Import 3D Model")
        for label, etype in (
            ("Car / Ground Vehicle  (sedan.obj)",    "vehicle"),
            ("Aerial UAV  (quad_uav.obj)",           "uav"),
            ("Bird  (seagull.obj)",                  "bird"),
        ):
            act = QAction(label, self)
            act.triggered.connect(
                lambda checked=False, et=etype: self._import_3d_model(et)
            )
            models_menu.addAction(act)

        file_menu.addSeparator()
        exit_act  = QAction("Exit", self)
        exit_act.setShortcut(QKeySequence("Alt+F4"))
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

    def _import_3d_model(self, entity_type: str):
        """Open a file dialog, then hot-swap the OBJ mesh for *entity_type*."""
        labels = {"vehicle": "Car / Ground Vehicle", "uav": "Aerial UAV", "bird": "Bird"}
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            f"Import 3D Model — {labels.get(entity_type, entity_type)}",
            "",
            "Wavefront OBJ (*.obj);;All files (*)",
        )
        if not filepath:
            return
        ok = self.renderer.import_model(entity_type, filepath)
        if ok:
            QMessageBox.information(
                self, "Model Imported",
                f"{labels.get(entity_type, entity_type)} model replaced.\n"
                f"Source: {filepath}"
            )
        else:
            QMessageBox.warning(
                self, "Import Failed",
                f"Could not load OBJ file:\n{filepath}\n\n"
                "Make sure it is a valid Wavefront OBJ with vertex normals (vn lines)."
            )

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        splitter    = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        panel_style = ("QFrame { background-color: #252525; "
                       "border: 1px solid #404040; border-radius: 8px; }")

        ctrl_frame = QFrame()
        ctrl_frame.setMaximumWidth(350)
        ctrl_frame.setStyleSheet(panel_style)
        QVBoxLayout(ctrl_frame).addWidget(self.control_panel)
        splitter.addWidget(ctrl_frame)

        view_frame = QFrame()
        view_frame.setStyleSheet(
            "QFrame { background-color: #1a1a1a; border: 1px solid #404040; border-radius: 8px; }"
        )
        vl = QVBoxLayout(view_frame)
        vl.setContentsMargins(2, 2, 2, 2)
        vl.addWidget(self.renderer)
        splitter.addWidget(view_frame)

        stat_frame = QFrame()
        stat_frame.setMaximumWidth(300)
        stat_frame.setStyleSheet(panel_style)
        QVBoxLayout(stat_frame).addWidget(self.status_panel)
        splitter.addWidget(stat_frame)

        splitter.setSizes([350, 700, 300])

    def setup_connections(self):
        # Control panel → this window
        self.control_panel.llm_command_requested.connect(self.process_llm_command)
        self.control_panel.manual_command_requested.connect(self.process_manual_command)
        self.control_panel.gimbal_home_requested.connect(self.gimbal_home)
        self.control_panel.object_enabled.connect(self.on_object_enabled)
        self.control_panel.tracking_toggled.connect(self.on_tracking_toggled)
        self.control_panel.model_change_requested.connect(self.on_model_change_requested)

        # LLM async pipeline
        self.llm_service.processing_started.connect(
            lambda: self.control_panel.set_processing(True)
        )
        self.llm_service.processing_finished.connect(
            lambda: self.control_panel.set_processing(False)
        )
        self.llm_service.command_processed.connect(self.on_llm_command_result)

        # Gimbal controller → status panel + renderer
        self.gimbal_controller.position_changed.connect(self.on_position_changed)
        self.gimbal_controller.status_changed.connect(self.on_status_changed)

        # Drone physics → renderer + status panel
        self.drone.position_changed.connect(self._on_drone_moved)
        self.drone.state_changed.connect(self.status_panel.update_drone_state)

    # ── Scene context for LLM ─────────────────────────────────────────────────

    @staticmethod
    def _xyz_to_gps(x: float, y: float, z: float, cfg) -> tuple:
        """Convert scene XYZ → (lat, lon, alt_msl). +X=East, +Z=North, +Y=Up."""
        import math
        lat_rad = math.radians(cfg.home_lat)
        lat = cfg.home_lat + z / 111_320.0
        lon = cfg.home_lon + x / (111_320.0 * math.cos(lat_rad))
        alt = cfg.home_alt_msl + y
        return lat, lon, alt

    def _build_scene_context(self) -> str:
        gc  = self.gimbal_controller
        d   = self.drone
        spd = d.horizontal_speed
        lat, lon, alt_msl = self._xyz_to_gps(d.x, d.y, d.z, self.config)
        ns  = 'N' if lat >= 0 else 'S'
        ew  = 'E' if lon >= 0 else 'W'
        lines = [
            f"Drone: GPS=({abs(lat):.5f}°{ns}, {abs(lon):.5f}°{ew})  "
            f"alt={alt_msl:.1f}m MSL  heading={d.heading:.0f}°  "
            f"hspd={spd:.2f} m/s ({spd*3.6:.1f} km/h)  state={d.state.value}",
            f"Gimbal: pan={gc.pan:.0f}°  tilt={gc.tilt:.0f}°  "
            f"zoom={gc.zoom_factor:.1f}x  speed={gc.speed}  "
            f"tracking={'yes' if gc.tracking_mode else 'no'}",
            "Entities (label, type, colour, GPS-lat, GPS-lon, alt-msl, dist_from_drone):",
        ]
        for e in self.renderer.get_entities():
            dist   = math.sqrt((e['x'] - d.x)**2 +
                               (e['y'] - d.y)**2 +
                               (e['z'] - d.z)**2)
            colour = _rgb_name(*e['color'])
            elat, elon, ealt = self._xyz_to_gps(e['x'], e['y'], e['z'], self.config)
            ens = 'N' if elat >= 0 else 'S'
            eew = 'E' if elon >= 0 else 'W'
            lines.append(
                f"  {e['label']}  {e['type']}  {colour}  "
                f"GPS=({abs(elat):.5f}°{ens}, {abs(elon):.5f}°{eew})  "
                f"alt={ealt:.1f}m MSL  dist={dist:.1f}m"
            )
        return "\n".join(lines)

    # ── LLM command processing ────────────────────────────────────────────────

    def process_llm_command(self, command: str):
        self.logger.info("LLM: %s", command)
        accepted = self.llm_service.process_command_async(
            command, self._build_scene_context()
        )
        if not accepted:
            self.control_panel.update_response(
                "Busy — wait for current command to finish", False
            )

    def on_llm_command_result(self, result):
        self.control_panel.update_response(result.message, result.success)
        if result.success:
            self._execute_command(result)

    def _execute_command(self, cmd):
        """Route command to the correct subsystem by control priority."""
        action = cmd.action

        # ── Priority 1: Gimbal ────────────────────────────────────────────────
        if action == "pan":
            self._tracking_entity = None
            self.gimbal_controller.enable_tracking(False)
            self.gimbal_controller.pan_to(cmd.value, cmd.speed)

        elif action == "tilt":
            self._tracking_entity = None
            self.gimbal_controller.enable_tracking(False)
            self.gimbal_controller.tilt_to(cmd.value, cmd.speed)

        elif action == "home":
            self._tracking_entity = None
            self._disengage_assists()
            self.gimbal_controller.enable_tracking(False)
            self.gimbal_controller.move_to_home()

        elif action == "stop":
            self._tracking_entity = None
            self._disengage_assists()
            self.gimbal_controller.stop()

        elif action == "track":
            entity = self.renderer.get_nearest_entity(cmd.target_type)
            if entity is not None:
                # Disable legacy ball tracking before starting entity tracking
                if self.tracking_active:
                    self.tracking_active = False
                    self.renderer.set_tracking_active(False)
                    self.control_panel.update_response("", True)
                self._tracking_entity = entity
                self.gimbal_controller.enable_tracking(True)
            else:
                self.control_panel.update_response(
                    f"No {cmd.target_type or 'entity'} found in scene", False
                )

        # ── Priority 2: Camera (PTZ zoom axis) ───────────────────────────────
        elif action == "camera_zoom":
            self.gimbal_controller.zoom_by(cmd.value, cmd.speed)

        elif action == "camera_zoom_abs":
            factor = max(1.0, cmd.value) if cmd.value > 0 else 1.0
            self.gimbal_controller.zoom_to(factor, cmd.speed)

        # ── Priority 3: Drone ─────────────────────────────────────────────────
        elif action == "takeoff":
            if self.drone.state.value == "Grounded":
                self.drone.command_takeoff(cmd.altitude, cmd.speed)
            else:
                # Already airborne — climb a bit instead
                self.drone.command_ascend(1.5, cmd.speed)
                self.control_panel.update_response(
                    f"Already airborne ({self.drone.state.value}) — ascending", True
                )

        elif action == "land":
            self.drone.command_land(cmd.speed)

        elif action == "drone_move":
            direction = cmd.direction or "forward"
            self.drone.command_move(direction, cmd.speed, cmd.distance)

        elif action == "drone_hover":
            self.drone.command_hover()

        elif action == "drone_ascend":
            val = cmd.value if cmd.value > 0 else 2.0
            self.drone.command_ascend(val, cmd.speed)

        elif action == "drone_descend":
            val = cmd.value if cmd.value > 0 else 2.0
            self.drone.command_descend(val, cmd.speed)

        elif action == "drone_yaw":
            self.drone.command_yaw(cmd.value, cmd.speed)
            # Sync renderer heading immediately
            self.renderer.drone_yaw = self.drone.heading

        elif action == "drone_circle":
            radius = cmd.value if cmd.value > 0.5 else 3.0
            self.drone.command_circle(radius, cmd.speed, cmd.clockwise)

        elif action == "drone_goto_gps":
            cfg = self.config
            self.drone.command_goto_gps(
                cmd.gps_lat, cmd.gps_lon, cmd.gps_alt,
                cfg.home_lat, cfg.home_lon, cfg.home_alt_msl,
                cmd.speed,
            )

        else:
            # Unknown action from LLM — default to gimbal home (always safe)
            self.logger.info("Unrouted action '%s' — defaulting to home", action)
            self.gimbal_controller.move_to_home()

    # ── Manual gimbal commands ────────────────────────────────────────────────

    def process_manual_command(self, command_data: dict):
        action = command_data["action"]
        value  = command_data["value"]
        speed  = command_data["speed"]
        self._tracking_entity = None
        self._disengage_assists()
        self.gimbal_controller.enable_tracking(False)
        if action == "pan":
            self.gimbal_controller.pan_to(value, speed)
        elif action == "tilt":
            self.gimbal_controller.tilt_to(value, speed)
        self.control_panel.update_response(f"Manual {action}: {value:+.0f}°", True)

    def gimbal_home(self):
        self._tracking_entity = None
        self.gimbal_controller.enable_tracking(False)
        self.gimbal_controller.move_to_home()
        self.control_panel.update_response("Gimbal centred", True)

    # ── Signal handlers ───────────────────────────────────────────────────────

    def on_position_changed(self, position: dict):
        self.status_panel.update_gimbal_position(position)
        self.renderer.update_gimbal_position(position)   # also drives FOV via zoom_factor

    def on_status_changed(self, status: str):
        self.status_panel.update_status(status)

    def _on_drone_moved(self, x: float, y: float, z: float):
        self.renderer.update_drone_position(x, y, z)
        self.status_panel.update_drone_position(x, y, z)

    def on_object_enabled(self, enabled: bool):
        self.moving_object_enabled = enabled
        self.renderer.set_moving_object_enabled(enabled)
        if not enabled:
            self.on_tracking_toggled(False)

    def on_tracking_toggled(self, active: bool):
        self.tracking_active = active
        self.renderer.set_tracking_active(active)
        self.gimbal_controller.enable_tracking(active)
        self.control_panel.update_response(
            "Tracking ball" if active else "Ball tracking stopped", True
        )

    def on_model_change_requested(self):
        from gui.model_dialog import ModelDialog
        dialog = ModelDialog(self.llm_service, parent=self)
        if dialog.exec():
            model, provider, api_key = dialog.get_result()
            success = self.llm_service.switch_model(model, provider, api_key)
            self._update_llm_display()
            self.control_panel.update_response(
                f"Model: {self.llm_service.get_active_model_display()}", success
            )

    # ── Gimbal aim math ───────────────────────────────────────────────────────

    def _compute_gimbal_aim(self, tx: float, ty: float, tz: float):
        d   = self.drone
        dx  = tx - d.x
        dz  = tz - d.z
        dy  = ty - d.gimbal_y
        pan   = math.degrees(math.atan2(dx, dz if abs(dz) > 0.01 else 0.01))
        horiz = math.sqrt(dx * dx + dz * dz)
        tilt  = math.degrees(math.atan2(dy, horiz if horiz > 0.01 else 0.01))
        return (max(-180.0, min(180.0, pan)),
                max(-90.0,  min(90.0,  tilt)))

    def _compute_tracking_angles(self):
        """Legacy: compute angles for renderer's ball target."""
        world = self.renderer.get_target_world_pos()
        if world is None:
            return 0.0, 0.0, False
        tx, tz = world
        pan, tilt = self._compute_gimbal_aim(tx, 0.3, tz)
        return pan, tilt, True

    # ── Coordinated drone + gimbal tracking ──────────────────────────────────

    def _coordinate_tracking(self, entity: dict, pan: float, tilt: float):
        d = self.drone

        if abs(pan) > _PAN_ASSIST_ON:
            self._yaw_assist_active = True
        elif abs(pan) < _PAN_ASSIST_OFF:
            self._yaw_assist_active = False

        if self._yaw_assist_active:
            world_yaw = math.degrees(math.atan2(
                entity['x'] - d.x, entity['z'] - d.z,
            ))
            self.renderer.set_tracking_yaw(world_yaw)
        else:
            self.renderer.clear_tracking_yaw()

        if abs(tilt) > _TILT_ASSIST_ON:
            self._tilt_assist_active = True
        elif abs(tilt) < _TILT_ASSIST_OFF:
            self._tilt_assist_active = False

        if self._tilt_assist_active:
            ey     = entity['y']
            horiz  = max(0.5, math.sqrt((entity['x'] - d.x) ** 2 +
                                        (entity['z'] - d.z) ** 2))
            sign   = 1 if tilt > 0 else -1
            ideal_g_y = ey - sign * horiz * math.tan(math.radians(25))
            ideal_d_y = ideal_g_y + BODY_H / 2 + ROD_LEN
            d.set_altitude_assist(ideal_d_y)
        else:
            d.clear_altitude_assist()

    def _disengage_assists(self):
        self._yaw_assist_active  = False
        self._tilt_assist_active = False
        self.renderer.clear_tracking_yaw()
        self.drone.clear_altitude_assist()

    # ── 60 fps update loop ────────────────────────────────────────────────────

    def _tick(self):
        self.drone.update()
        self.gimbal_controller.update()

        # LLM entity tracking
        if self._tracking_entity is not None:
            e = self._tracking_entity
            pan, tilt = self._compute_gimbal_aim(e['x'], e['y'], e['z'])
            self.gimbal_controller.set_tracking_target(pan, tilt)
            self._coordinate_tracking(e, pan, tilt)
        else:
            self._disengage_assists()

        # Legacy ball tracking — only when no LLM entity tracking is active
        if self._tracking_entity is None and self.tracking_active and self.moving_object_enabled:
            pan, tilt, ok = self._compute_tracking_angles()
            if ok:
                self.gimbal_controller.set_tracking_target(pan, tilt)
                locked = (abs(self.gimbal_controller.pan  - pan)  < 5 and
                          abs(self.gimbal_controller.tilt - tilt) < 5)
                self.renderer.set_tracking_locked(locked)
            else:
                self.renderer.set_tracking_locked(False)

    # ── LLM status display ────────────────────────────────────────────────────

    def _update_llm_display(self):
        cfg = self.config
        if cfg.llm_provider == "openrouter" and cfg.openrouter_api_key:
            self.status_panel.update_llm_status("Connected (OpenRouter)",
                                                cfg.openrouter_model)
        elif self.llm_service.ollama_available:
            self.status_panel.update_llm_status("Connected (Ollama)",
                                                cfg.ollama_model)
        else:
            self.status_panel.update_llm_status("Offline (Regex fallback)",
                                                "Keyword Parser")

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if hasattr(self, "update_timer"):
            self.update_timer.stop()
        self.renderer.cleanup()
        self.gimbal_controller.cleanup()
        event.accept()
