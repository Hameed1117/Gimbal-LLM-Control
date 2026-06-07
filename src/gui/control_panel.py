"""Control Panel — NLP command input + manual gimbal controls."""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QSlider, QGroupBox, QCheckBox, QScrollArea
)
from PyQt6.QtCore import Qt, QEvent, pyqtSignal


class ControlPanel(QWidget):
    """Left panel: LLM command input, manual gimbal controls, example commands."""

    llm_command_requested  = pyqtSignal(str)
    manual_command_requested = pyqtSignal(dict)
    gimbal_home_requested  = pyqtSignal()
    object_enabled         = pyqtSignal(bool)
    tracking_toggled       = pyqtSignal(bool)
    model_change_requested = pyqtSignal()

    def __init__(self, config, gimbal_controller):
        super().__init__()
        self.config            = config
        self.gimbal_controller = gimbal_controller
        self.logger            = logging.getLogger(__name__)
        self.setup_ui()

    def setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        # ── Scrollable area for all content ──────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        container = QWidget()
        layout    = QVBoxLayout(container)
        layout.setSpacing(6)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        # ── LLM Command ───────────────────────────────────────────────────────
        llm_group  = QGroupBox("NLP Command Center")
        llm_layout = QVBoxLayout(llm_group)

        self.command_input = QTextEdit()
        self.command_input.setMaximumHeight(75)
        self.command_input.installEventFilter(self)
        self.command_input.setPlaceholderText(
            "Natural language — gimbal, PTZ camera, drone + GPS nav:\n"
            "  'Take off'  •  'Fly to 51.5094, -0.1278'  •  'Pan right 45'\n"
            "  'Track the orange car'  •  'Zoom to 10x'  •  'Land'"
        )
        llm_layout.addWidget(self.command_input)

        btn_row = QHBoxLayout()
        self.send_button = QPushButton("Send Command")
        self.send_button.setStyleSheet(
            "QPushButton { background-color: #2a82da; color: white; font-weight: bold; }"
            "QPushButton:hover { background-color: #3a92ea; }"
            "QPushButton:pressed { background-color: #1a62ba; }"
            "QPushButton:disabled { background-color: #2a2a2a; color: #666; }"
        )
        self.send_button.clicked.connect(self.send_llm_command)
        btn_row.addWidget(self.send_button)

        change_model_btn = QPushButton("Model")
        change_model_btn.setMaximumWidth(70)
        change_model_btn.setToolTip("Change LLM model / provider")
        change_model_btn.clicked.connect(self.model_change_requested.emit)
        btn_row.addWidget(change_model_btn)
        llm_layout.addLayout(btn_row)

        self.response_label = QLabel("Ready")
        self.response_label.setWordWrap(True)
        self.response_label.setStyleSheet("""
            QLabel {
                background-color: #1a1a1a;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 8px;
                color: #cccccc;
                min-height: 36px;
            }
        """)
        llm_layout.addWidget(self.response_label)
        layout.addWidget(llm_group)

        # ── Manual Gimbal Controls ────────────────────────────────────────────
        manual_group  = QGroupBox("Manual Gimbal Controls")
        manual_layout = QVBoxLayout(manual_group)

        pan_layout = QHBoxLayout()
        pan_layout.addWidget(QLabel("Pan:"))
        pan_left_btn = QPushButton("← 45°")
        pan_left_btn.clicked.connect(lambda: self.manual_command("pan", -45))
        pan_layout.addWidget(pan_left_btn)
        pan_right_btn = QPushButton("45° →")
        pan_right_btn.clicked.connect(lambda: self.manual_command("pan", 45))
        pan_layout.addWidget(pan_right_btn)
        manual_layout.addLayout(pan_layout)

        tilt_layout = QHBoxLayout()
        tilt_layout.addWidget(QLabel("Tilt:"))
        tilt_up_btn = QPushButton("↑ 30°")
        tilt_up_btn.clicked.connect(lambda: self.manual_command("tilt", 30))
        tilt_layout.addWidget(tilt_up_btn)
        tilt_down_btn = QPushButton("↓ 30°")
        tilt_down_btn.clicked.connect(lambda: self.manual_command("tilt", -30))
        tilt_layout.addWidget(tilt_down_btn)
        manual_layout.addLayout(tilt_layout)

        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Speed:"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 10)
        self.speed_slider.setValue(5)
        speed_layout.addWidget(self.speed_slider)
        self.speed_label = QLabel("5")
        self.speed_slider.valueChanged.connect(lambda v: self.speed_label.setText(str(v)))
        speed_layout.addWidget(self.speed_label)
        manual_layout.addLayout(speed_layout)

        home_btn = QPushButton("Home Position (Gimbal)")
        home_btn.clicked.connect(self.gimbal_home_requested.emit)
        manual_layout.addWidget(home_btn)
        layout.addWidget(manual_group)

        # ── Example Commands ──────────────────────────────────────────────────
        ex_group  = QGroupBox("Example Commands")
        ex_layout = QVBoxLayout(ex_group)
        ex_layout.setSpacing(2)

        _SECTION_STYLE = (
            "QLabel { color: #888; font-size: 10px; padding: 4px 0 1px 0; "
            "background: transparent; border: none; font-weight: bold; }"
        )
        _BTN_STYLE = """
            QPushButton {
                text-align: left;
                padding: 3px 8px;
                font-size: 11px;
                background-color: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #353535;
                border-color: #2a82da;
                color: #2a82da;
            }
        """

        def _section(title):
            lbl = QLabel(title)
            lbl.setStyleSheet(_SECTION_STYLE)
            ex_layout.addWidget(lbl)

        def _ex(*examples):
            for ex in examples:
                btn = QPushButton(ex)
                btn.setStyleSheet(_BTN_STYLE)
                btn.clicked.connect(lambda _, t=ex: self._set_example(t))
                ex_layout.addWidget(btn)

        _section("DRONE")
        _ex(
            "Take off",
            "Take off to 3 meters",
            "Land",
            "Hover",
            "Fly forward 5 meters",
            "Fly backward",
            "Go left",
            "Go right",
            "Ascend 2 meters",
            "Descend 1 meter",
            "Rotate right 90 degrees",
        )

        _section("GPS NAVIGATION")
        _ex(
            "Fly to 51.50740, -0.12780",
            "Navigate to 51.50940, -0.09000 at 30m",
            "Go to 51.51200, -0.07800",
            "Fly to 51.50500, -0.14000 at 25m",
        )

        _section("GIMBAL")
        _ex(
            "Pan right 45 degrees",
            "Pan left slowly",
            "Swing camera all the way right",
            "Tilt up 30 degrees",
            "Look down a bit",
            "Center the gimbal",
            "Stop",
        )

        _section("CAMERA  (PTZ Zoom)")
        _ex(
            "Zoom in",
            "Zoom in a lot",
            "Zoom to 5x",
            "Zoom to 15x",
            "Maximum zoom",
            "Zoom out",
            "Zoom out fully",
        )

        _section("TRACK (Gimbal + Drone)")
        _ex(
            "Track the orange car",
            "Follow the blue car",
            "Watch the yellow drone",
            "Lock on to the nearest bird",
            "Chase the purple drone",
        )

        layout.addWidget(ex_group)

        # ── Demo Ball Tracking ────────────────────────────────────────────────
        tracking_group  = QGroupBox("Demo Ball Tracking")
        tracking_layout = QVBoxLayout(tracking_group)
        tracking_layout.setSpacing(4)

        self.object_checkbox = QCheckBox("Enable Moving Ball")
        self.object_checkbox.stateChanged.connect(self._on_object_toggled)
        tracking_layout.addWidget(self.object_checkbox)

        self.track_btn = QPushButton("▶  Start Tracking")
        self.track_btn.setCheckable(True)
        self.track_btn.setVisible(False)
        self.track_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 6px;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: rgba(0, 180, 80, 0.25);
                border-color: #00b450;
                color: #00b450;
            }
            QPushButton:hover { border-color: #2a82da; }
        """)
        self.track_btn.clicked.connect(self._on_track_clicked)
        tracking_layout.addWidget(self.track_btn)
        layout.addWidget(tracking_group)

        layout.addStretch()

    # ── Keyboard shortcut ─────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self.command_input and event.type() == QEvent.Type.KeyPress:
            if (event.key() == Qt.Key.Key_Return and
                    event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self.send_llm_command()
                return True
        return super().eventFilter(obj, event)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_example(self, text: str):
        self.command_input.setPlainText(text)
        self.command_input.setFocus()

    def _on_object_toggled(self, state):
        enabled = state == Qt.CheckState.Checked.value
        self.track_btn.setVisible(enabled)
        if not enabled:
            self.track_btn.setChecked(False)
            self.tracking_toggled.emit(False)
        self.object_enabled.emit(enabled)

    def _on_track_clicked(self, checked: bool):
        self.track_btn.setText("■  Stop Tracking" if checked else "▶  Start Tracking")
        self.tracking_toggled.emit(checked)

    def set_processing(self, busy: bool):
        self.send_button.setEnabled(not busy)
        self.send_button.setText("Processing…" if busy else "Send Command")
        if busy:
            self.response_label.setText("Waiting for LLM response…")
            self.response_label.setStyleSheet("""
                QLabel {
                    background-color: rgba(42, 130, 218, 0.1);
                    border: 1px solid #2a82da;
                    border-radius: 4px;
                    padding: 8px;
                    color: #2a82da;
                    min-height: 36px;
                }
            """)

    def send_llm_command(self):
        command = self.command_input.toPlainText().strip()
        if command:
            self.llm_command_requested.emit(command)

    def manual_command(self, action: str, value: float):
        self.manual_command_requested.emit({
            'action': action,
            'value':  value,
            'speed':  self.speed_slider.value(),
        })

    def update_response(self, message: str, success: bool = True):
        self.response_label.setText(message)
        color = "#4caf50" if success else "#f44336"
        bg    = "rgba(76, 175, 80, 0.1)" if success else "rgba(244, 67, 54, 0.1)"
        self.response_label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                border: 1px solid {color};
                border-radius: 4px;
                padding: 8px;
                color: {color};
                min-height: 36px;
            }}
        """)
