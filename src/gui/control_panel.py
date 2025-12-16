"""Control Panel GUI component"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, 
    QLabel, QSlider, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal

class ControlPanel(QWidget):
    """Left panel with LLM command input and manual controls"""
    
    llm_command_requested = pyqtSignal(str)
    manual_command_requested = pyqtSignal(dict)
    gimbal_home_requested = pyqtSignal()
    
    def __init__(self, config, gimbal_controller):
        super().__init__()
        self.config = config
        self.gimbal_controller = gimbal_controller
        self.logger = logging.getLogger(__name__)
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the control panel UI"""
        
        layout = QVBoxLayout(self)
        
        # LLM Command Group
        llm_group = QGroupBox("🤖 LLM Commands")
        llm_layout = QVBoxLayout(llm_group)
        
        # Command input
        self.command_input = QTextEdit()
        self.command_input.setMaximumHeight(80)
        self.command_input.setPlaceholderText(
            "Enter command:\n• Pan left 45 degrees\n• Tilt up slowly\n• Go to home position"
        )
        llm_layout.addWidget(self.command_input)
        
        # Send button
        send_button = QPushButton("Send Command")
        send_button.clicked.connect(self.send_llm_command)
        llm_layout.addWidget(send_button)
        
        # Response area
        self.response_label = QLabel("Ready")
        self.response_label.setWordWrap(True)
        self.response_label.setStyleSheet("""
            QLabel {
                background-color: #1a1a1a;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 8px;
                color: #cccccc;
                min-height: 40px;
            }
        """)
        llm_layout.addWidget(self.response_label)
        
        layout.addWidget(llm_group)
        
        # Manual Control Group
        manual_group = QGroupBox("🎮 Manual Controls")
        manual_layout = QVBoxLayout(manual_group)
        
        # Pan controls
        pan_layout = QHBoxLayout()
        pan_layout.addWidget(QLabel("Pan:"))
        
        pan_left_btn = QPushButton("← 45°")
        pan_left_btn.clicked.connect(lambda: self.manual_command("pan", -45))
        pan_layout.addWidget(pan_left_btn)
        
        pan_right_btn = QPushButton("45° →")
        pan_right_btn.clicked.connect(lambda: self.manual_command("pan", 45))
        pan_layout.addWidget(pan_right_btn)
        
        manual_layout.addLayout(pan_layout)
        
        # Tilt controls
        tilt_layout = QHBoxLayout()
        tilt_layout.addWidget(QLabel("Tilt:"))
        
        tilt_up_btn = QPushButton("↑ 30°")
        tilt_up_btn.clicked.connect(lambda: self.manual_command("tilt", 30))
        tilt_layout.addWidget(tilt_up_btn)
        
        tilt_down_btn = QPushButton("↓ 30°")
        tilt_down_btn.clicked.connect(lambda: self.manual_command("tilt", -30))
        tilt_layout.addWidget(tilt_down_btn)
        
        manual_layout.addLayout(tilt_layout)
        
        # Speed control
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Speed:"))
        
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 10)
        self.speed_slider.setValue(5)
        speed_layout.addWidget(self.speed_slider)
        
        self.speed_label = QLabel("5")
        self.speed_slider.valueChanged.connect(
            lambda v: self.speed_label.setText(str(v))
        )
        speed_layout.addWidget(self.speed_label)
        
        manual_layout.addLayout(speed_layout)
        
        # Home button
        home_btn = QPushButton("🏠 Home Position")
        home_btn.clicked.connect(self.gimbal_home_requested.emit)
        manual_layout.addWidget(home_btn)
        
        layout.addWidget(manual_group)
        layout.addStretch()
        
    def send_llm_command(self):
        """Send LLM command"""
        command = self.command_input.toPlainText().strip()
        if command:
            self.response_label.setText("Processing...")
            self.llm_command_requested.emit(command)
            
    def manual_command(self, action: str, value: float):
        """Send manual command"""
        command = {
            'action': action,
            'value': value,
            'speed': self.speed_slider.value()
        }
        self.manual_command_requested.emit(command)
        
    def update_response(self, message: str, success: bool = True):
        """Update command response display"""
        self.response_label.setText(message)
        color = "#4caf50" if success else "#f44336"
        self.response_label.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(76, 175, 80, 0.1);
                border: 1px solid {color};
                border-radius: 4px;
                padding: 8px;
                color: {color};
                min-height: 40px;
            }}
        """)