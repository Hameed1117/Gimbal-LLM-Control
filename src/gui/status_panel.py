"""Status Panel GUI component"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox
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
        self.speed_label = QLabel("Speed: 5")
        self.status_label = QLabel("Status: Ready")
        
        for label in [self.pan_label, self.tilt_label, self.speed_label, self.status_label]:
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
        
        # System Info Group
        info_group = QGroupBox("💻 System Info")
        info_layout = QVBoxLayout(info_group)
        
        import platform
        import sys
        
        self.platform_label = QLabel(f"Platform: {platform.system()}")
        self.python_label = QLabel(f"Python: {sys.version.split()[0]}")
        self.llm_status_label = QLabel("LLM: Checking...")
        
        for label in [self.platform_label, self.python_label, self.llm_status_label]:
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
        
        # Add stretch to push content to top
        layout.addStretch()
        
    def update_gimbal_position(self, position):
        """Update gimbal position display"""
        self.pan_label.setText(f"Pan: {position['pan']:.1f}°")
        self.tilt_label.setText(f"Tilt: {position['tilt']:.1f}°")
        self.speed_label.setText(f"Speed: {position['speed']}")
        
    def update_status(self, status):
        """Update gimbal status"""
        self.status_label.setText(f"Status: {status}")
        
        # Color coding
        if status == "Ready":
            color = "#4caf50"
        elif status == "Moving":
            color = "#ff9800"
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
        
    def update_llm_status(self, status):
        """Update LLM connection status"""
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