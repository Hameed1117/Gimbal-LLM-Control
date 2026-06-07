"""Status Panel GUI component"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QProgressBar
)
from PyQt6.QtCore import Qt

class StatusPanel(QWidget):
    """Right panel showing gimbal status"""
    
    def __init__(self, config, gimbal_controller):
        super().__init__()
        self.config = config
        self.gimbal_controller = gimbal_controller
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup status panel UI"""
        
        layout = QVBoxLayout(self)
        
        # Gimbal Status Group
        status_group = QGroupBox("📊 Gimbal Status")
        status_layout = QVBoxLayout(status_group)
        
        # Position display
        self.pan_label = QLabel("Pan: 0°")
        self.tilt_label = QLabel("Tilt: 0°")
        self.zoom_label = QLabel("Zoom: 1.0×")
        self.speed_label = QLabel("Speed: 5")
        self.status_label = QLabel("Status: Ready")

        for label in [self.pan_label, self.tilt_label, self.zoom_label,
                       self.speed_label, self.status_label]:
            label.setStyleSheet("""
                QLabel {
                    padding: 8px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 14px;
                    background-color: #2a2a2a;
                    border: 1px solid #404040;
                    border-radius: 4px;
                    margin: 2px;
                }
            """)
            status_layout.addWidget(label)
            
        layout.addWidget(status_group)

        # PWM Signal Group
        pwm_group = QGroupBox("PWM Signal Output")
        pwm_layout = QVBoxLayout(pwm_group)
        pwm_layout.setSpacing(8)

        # Info label
        pwm_info = QLabel("Standard RC servo protocol: 1000-2000 µs @ 50 Hz\n"
                          "Center (home) = 1500 µs  |  Range = ±500 µs")
        pwm_info.setWordWrap(True)
        pwm_info.setStyleSheet("""
            QLabel {
                padding: 6px;
                font-size: 11px;
                background-color: #1e2a3a;
                border: 1px solid #2a5080;
                border-radius: 4px;
                color: #88aacc;
            }
        """)
        pwm_layout.addWidget(pwm_info)

        # Pan PWM
        pan_pwm_header = QHBoxLayout()
        pan_pwm_title = QLabel("Pan PWM")
        pan_pwm_title.setStyleSheet("font-size:12px; font-weight:bold; color:#aaaaaa; background:transparent; border:none;")
        self.pan_pwm_value = QLabel("1500 µs")
        self.pan_pwm_value.setStyleSheet("font-size:13px; font-family:'Consolas','Monaco',monospace; color:#2a82da; background:transparent; border:none;")
        pan_pwm_header.addWidget(pan_pwm_title)
        pan_pwm_header.addStretch()
        pan_pwm_header.addWidget(self.pan_pwm_value)
        pwm_layout.addLayout(pan_pwm_header)

        pan_pwm_bar_row = QHBoxLayout()
        pan_min_lbl = QLabel("1000")
        pan_min_lbl.setStyleSheet("font-size:10px; color:#666; background:transparent; border:none;")
        self.pan_pwm_bar = QProgressBar()
        self.pan_pwm_bar.setRange(1000, 2000)
        self.pan_pwm_bar.setValue(1500)
        self.pan_pwm_bar.setTextVisible(False)
        self.pan_pwm_bar.setFixedHeight(14)
        self.pan_pwm_bar.setStyleSheet("""
            QProgressBar {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #2a82da;
                border-radius: 3px;
            }
        """)
        pan_max_lbl = QLabel("2000")
        pan_max_lbl.setStyleSheet("font-size:10px; color:#666; background:transparent; border:none;")
        pan_pwm_bar_row.addWidget(pan_min_lbl)
        pan_pwm_bar_row.addWidget(self.pan_pwm_bar)
        pan_pwm_bar_row.addWidget(pan_max_lbl)
        pwm_layout.addLayout(pan_pwm_bar_row)

        # Tilt PWM
        tilt_pwm_header = QHBoxLayout()
        tilt_pwm_title = QLabel("Tilt PWM")
        tilt_pwm_title.setStyleSheet("font-size:12px; font-weight:bold; color:#aaaaaa; background:transparent; border:none;")
        self.tilt_pwm_value = QLabel("1500 µs")
        self.tilt_pwm_value.setStyleSheet("font-size:13px; font-family:'Consolas','Monaco',monospace; color:#4caf50; background:transparent; border:none;")
        tilt_pwm_header.addWidget(tilt_pwm_title)
        tilt_pwm_header.addStretch()
        tilt_pwm_header.addWidget(self.tilt_pwm_value)
        pwm_layout.addLayout(tilt_pwm_header)

        tilt_pwm_bar_row = QHBoxLayout()
        tilt_min_lbl = QLabel("1000")
        tilt_min_lbl.setStyleSheet("font-size:10px; color:#666; background:transparent; border:none;")
        self.tilt_pwm_bar = QProgressBar()
        self.tilt_pwm_bar.setRange(1000, 2000)
        self.tilt_pwm_bar.setValue(1500)
        self.tilt_pwm_bar.setTextVisible(False)
        self.tilt_pwm_bar.setFixedHeight(14)
        self.tilt_pwm_bar.setStyleSheet("""
            QProgressBar {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #4caf50;
                border-radius: 3px;
            }
        """)
        tilt_max_lbl = QLabel("2000")
        tilt_max_lbl.setStyleSheet("font-size:10px; color:#666; background:transparent; border:none;")
        tilt_pwm_bar_row.addWidget(tilt_min_lbl)
        tilt_pwm_bar_row.addWidget(self.tilt_pwm_bar)
        tilt_pwm_bar_row.addWidget(tilt_max_lbl)
        pwm_layout.addLayout(tilt_pwm_bar_row)

        # Zoom PWM
        zoom_pwm_header = QHBoxLayout()
        zoom_pwm_title = QLabel("Zoom PWM")
        zoom_pwm_title.setStyleSheet("font-size:12px; font-weight:bold; color:#aaaaaa; background:transparent; border:none;")
        self.zoom_pwm_value = QLabel("1000 µs  (1.0×)")
        self.zoom_pwm_value.setStyleSheet("font-size:13px; font-family:'Consolas','Monaco',monospace; color:#ff9800; background:transparent; border:none;")
        zoom_pwm_header.addWidget(zoom_pwm_title)
        zoom_pwm_header.addStretch()
        zoom_pwm_header.addWidget(self.zoom_pwm_value)
        pwm_layout.addLayout(zoom_pwm_header)

        zoom_pwm_bar_row = QHBoxLayout()
        zoom_min_lbl = QLabel("1000")
        zoom_min_lbl.setStyleSheet("font-size:10px; color:#666; background:transparent; border:none;")
        self.zoom_pwm_bar = QProgressBar()
        self.zoom_pwm_bar.setRange(1000, 2000)
        self.zoom_pwm_bar.setValue(1000)
        self.zoom_pwm_bar.setTextVisible(False)
        self.zoom_pwm_bar.setFixedHeight(14)
        self.zoom_pwm_bar.setStyleSheet("""
            QProgressBar {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #ff9800;
                border-radius: 3px;
            }
        """)
        zoom_max_lbl = QLabel("2000")
        zoom_max_lbl.setStyleSheet("font-size:10px; color:#666; background:transparent; border:none;")
        zoom_pwm_bar_row.addWidget(zoom_min_lbl)
        zoom_pwm_bar_row.addWidget(self.zoom_pwm_bar)
        zoom_pwm_bar_row.addWidget(zoom_max_lbl)
        pwm_layout.addLayout(zoom_pwm_bar_row)

        # Duty cycle display
        self.duty_label = QLabel("Duty: Pan 7.50%  |  Tilt 7.50%  |  Zoom 5.00%")
        self.duty_label.setStyleSheet("""
            QLabel {
                padding: 5px;
                font-size: 11px;
                font-family: 'Consolas', 'Monaco', monospace;
                background-color: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 4px;
                color: #aaaaaa;
            }
        """)
        pwm_layout.addWidget(self.duty_label)

        layout.addWidget(pwm_group)

        # System Info Group
        info_group = QGroupBox("💻 System Info")
        info_layout = QVBoxLayout(info_group)
        
        import platform
        import sys
        
        self.platform_label = QLabel(f"Platform: {platform.system()}")
        self.python_label = QLabel(f"Python: {sys.version.split()[0]}")
        self.llm_status_label = QLabel("LLM: Checking...")
        self.model_label = QLabel("Model: ---")

        for label in [self.platform_label, self.python_label, self.llm_status_label, self.model_label]:
            label.setStyleSheet("""
                QLabel {
                    padding: 6px;
                    font-size: 12px;
                    background-color: #2a2a2a;
                    border: 1px solid #404040;
                    border-radius: 4px;
                    margin: 1px;
                }
            """)
            info_layout.addWidget(label)
            
        layout.addWidget(info_group)
        
        # Drone Controller Group
        drone_group  = QGroupBox("✈ Drone Controller")
        drone_layout = QVBoxLayout(drone_group)

        self.drone_state_label  = QLabel("State: Grounded")
        self.drone_detail_label = QLabel("On ground — idle")
        self.drone_pos_label    = QLabel("Pos: (0.0, 0.0, 0.0)")
        self.drone_vel_label    = QLabel("Speed: 0.00 m/s  (0.0 km/h)  Alt: 0.0 m")
        self.drone_gps_label    = QLabel("GPS: ---\nAlt: --- MSL")
        self.drone_gps_label.setWordWrap(True)

        _drone_lbl_style = """
            QLabel {
                padding: 6px;
                font-family: 'Consolas','Monaco',monospace;
                font-size: 12px;
                background-color: #1e2a3a;
                border: 1px solid #2a5080;
                border-radius: 4px;
                margin: 1px;
                color: #88aacc;
            }
        """
        for lbl in (self.drone_state_label, self.drone_detail_label,
                    self.drone_pos_label, self.drone_vel_label, self.drone_gps_label):
            lbl.setStyleSheet(_drone_lbl_style)
            drone_layout.addWidget(lbl)

        layout.addWidget(drone_group)

        # Add stretch to push content to top
        layout.addStretch()

    def update_drone_position(self, x: float, y: float, z: float):
        import math
        self.drone_pos_label.setText(f"Pos: ({x:.1f}, {y:.1f}, {z:.1f})")
        prev = getattr(self, '_prev_drone_pos', (x, y, z))
        dx, dy, dz = x - prev[0], y - prev[1], z - prev[2]
        spd_ms  = math.sqrt(dx * dx + dz * dz) * 60   # horizontal m/s at 60 fps
        spd_kmh = spd_ms * 3.6
        self.drone_vel_label.setText(
            f"H-speed: {spd_ms:.2f} m/s  ({spd_kmh:.1f} km/h)  Alt: {y:.1f} m"
        )
        self._prev_drone_pos = (x, y, z)

        # Real-world GPS coordinates
        home_lat = self.config.home_lat
        home_lon = self.config.home_lon
        home_alt = self.config.home_alt_msl
        lat_rad  = math.radians(home_lat)
        lat = home_lat + z / 111_320.0
        lon = home_lon + x / (111_320.0 * math.cos(lat_rad))
        alt_msl = home_alt + y
        ns = 'N' if lat >= 0 else 'S'
        ew = 'E' if lon >= 0 else 'W'
        self.drone_gps_label.setText(
            f"GPS: {abs(lat):.6f}°{ns}  {abs(lon):.6f}°{ew}\n"
            f"     Alt: {alt_msl:.1f} m MSL"
        )

    def update_drone_state(self, state: str, detail: str):
        """Update drone state label and detail text."""
        self.drone_state_label.setText(f"State: {state}")
        if detail:
            self.drone_detail_label.setText(detail)
        # Color the state label based on activity
        if state == "Grounded":
            color = "#888888"
        elif state in ("Taking Off", "Landing"):
            color = "#ff9800"
        elif state == "Hovering":
            color = "#4caf50"
        elif state == "Moving":
            color = "#2a82da"
        else:
            color = "#88aacc"
        self.drone_state_label.setStyleSheet(f"""
            QLabel {{
                padding: 6px;
                font-family: 'Consolas','Monaco',monospace;
                font-size: 12px;
                background-color: #1e2a3a;
                border: 1px solid {color};
                border-radius: 4px;
                margin: 1px;
                color: {color};
                font-weight: bold;
            }}
        """)

    def update_gimbal_position(self, position):
        """Update gimbal position display for all three PTZ axes."""
        self.pan_label.setText(f"Pan: {position['pan']:.1f}°")
        self.tilt_label.setText(f"Tilt: {position['tilt']:.1f}°")
        self.speed_label.setText(f"Speed: {position['speed']}")

        zoom_factor = position.get('zoom_factor', 1.0)
        import math
        fov = max(2.0, 60.0 / max(1.0, zoom_factor))
        self.zoom_label.setText(f"Zoom: {zoom_factor:.1f}×  (FOV {fov:.0f}°)")

        # Update PWM panel
        pan_pwm  = position.get('pan_pwm',  1500)
        tilt_pwm = position.get('tilt_pwm', 1500)
        zoom_pwm = position.get('zoom_pwm', 1000)
        self.pan_pwm_value.setText(f"{pan_pwm} µs")
        self.tilt_pwm_value.setText(f"{tilt_pwm} µs")
        self.zoom_pwm_value.setText(f"{zoom_pwm} µs  ({zoom_factor:.1f}×)")
        self.pan_pwm_bar.setValue(pan_pwm)
        self.tilt_pwm_bar.setValue(tilt_pwm)
        self.zoom_pwm_bar.setValue(zoom_pwm)
        # Duty cycle = pulse_width_µs / period_µs * 100  (period = 20000 µs at 50 Hz)
        pan_duty  = pan_pwm  / 20000.0 * 100
        tilt_duty = tilt_pwm / 20000.0 * 100
        zoom_duty = zoom_pwm / 20000.0 * 100
        self.duty_label.setText(
            f"Duty: Pan {pan_duty:.2f}%  |  Tilt {tilt_duty:.2f}%  |  Zoom {zoom_duty:.2f}%"
        )
        
    def update_status(self, status):
        """Update gimbal status"""
        self.status_label.setText(f"Status: {status}")
        
        # Color coding
        if status == "Ready":
            color = "#4caf50"
        elif status == "Moving":
            color = "#ff9800"
        elif status == "Tracking":
            color = "#2a82da"
        else:
            color = "#f44336"
            
        self.status_label.setStyleSheet(f"""
            QLabel {{
                padding: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 14px;
                background-color: #2a2a2a;
                border: 1px solid {color};
                border-radius: 4px;
                margin: 2px;
                color: {color};
            }}
        """)
        
    def update_llm_status(self, status, model=None):
        """Update LLM connection status and model name"""
        self.llm_status_label.setText(f"LLM: {status}")

        color = "#4caf50" if "Connected" in status else "#f44336"
        self.llm_status_label.setStyleSheet(f"""
            QLabel {{
                padding: 6px;
                font-size: 12px;
                background-color: #2a2a2a;
                border: 1px solid {color};
                border-radius: 4px;
                margin: 1px;
                color: {color};
            }}
        """)

        if model:
            self.model_label.setText(f"Model: {model}")
            self.model_label.setStyleSheet("""
                QLabel {
                    padding: 6px;
                    font-size: 12px;
                    background-color: #2a2a2a;
                    border: 1px solid #2a82da;
                    border-radius: 4px;
                    margin: 1px;
                    color: #2a82da;
                    font-weight: bold;
                }
            """)