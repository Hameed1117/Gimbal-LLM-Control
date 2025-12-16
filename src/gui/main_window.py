"""Main Window for Gimbal LLM Control Application"""

import sys
import logging
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QSplitter, QLabel, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self, config, llm_service, gimbal_controller):
        super().__init__()
        
        self.config = config
        self.llm_service = llm_service
        self.gimbal_controller = gimbal_controller
        self.logger = logging.getLogger(__name__)
        
        # Import GUI components (absolute imports)
        from gui.control_panel import ControlPanel
        from gui.status_panel import StatusPanel
        from graphics.renderer import GimbalRenderer
        
        # UI components
        self.control_panel = ControlPanel(config, gimbal_controller)
        self.status_panel = StatusPanel(config, gimbal_controller)
        self.renderer = GimbalRenderer(config)
        
        # Setup window
        self.setup_window()
        self.setup_ui()
        self.setup_connections()
        
        # Initialize renderer
        self.renderer.initialize_gimbal()
        self.renderer.start_rendering()
        
        # Start update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(16)  # ~60 FPS
        
        self.logger.info("Main window initialized")
    
    def setup_window(self):
        """Setup main window properties"""
        
        self.setWindowTitle("Gimbal LLM Control v1.0")
        self.setGeometry(100, 100, 1400, 900)
        self.setMinimumSize(1000, 600)
        
        # Dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a1a;
                color: white;
            }
            QWidget {
                background-color: #1a1a1a;
                color: white;
                font-family: 'Segoe UI', sans-serif;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #404040;
                border-radius: 8px;
                margin: 8px 0px;
                padding-top: 10px;
                background-color: #2a2a2a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
                color: #ffffff;
            }
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #2a82da;
            }
            QPushButton:pressed {
                background-color: #2a82da;
            }
        """)
    
    def setup_ui(self):
        """Setup the user interface"""
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        
        # Create splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left panel - Control Panel
        control_frame = QFrame()
        control_frame.setMaximumWidth(350)
        control_frame.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border: 1px solid #404040;
                border-radius: 8px;
            }
        """)
        
        control_layout = QVBoxLayout(control_frame)
        control_layout.addWidget(self.control_panel)
        splitter.addWidget(control_frame)
        
        # Center panel - 3D Renderer
        view_frame = QFrame()
        view_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border: 1px solid #404040;
                border-radius: 8px;
            }
        """)
        
        view_layout = QVBoxLayout(view_frame)
        view_layout.setContentsMargins(2, 2, 2, 2)
        view_layout.addWidget(self.renderer)
        splitter.addWidget(view_frame)
        
        # Right panel - Status Panel
        status_frame = QFrame()
        status_frame.setMaximumWidth(300)
        status_frame.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border: 1px solid #404040;
                border-radius: 8px;
            }
        """)
        
        status_layout = QVBoxLayout(status_frame)
        status_layout.addWidget(self.status_panel)
        splitter.addWidget(status_frame)
        
        # Set splitter proportions
        splitter.setSizes([350, 700, 300])
    
    def setup_connections(self):
        """Setup signal-slot connections"""
        
        # Control panel connections
        self.control_panel.llm_command_requested.connect(self.process_llm_command)
        self.control_panel.manual_command_requested.connect(self.process_manual_command)
        self.control_panel.gimbal_home_requested.connect(self.gimbal_home)
        
        # Gimbal controller connections
        self.gimbal_controller.position_changed.connect(self.on_position_changed)
        self.gimbal_controller.status_changed.connect(self.on_status_changed)
    
    def process_llm_command(self, command: str):
        """Process LLM command"""
        try:
            self.logger.info(f"Processing: {command}")
            
            # Process command
            result = self.llm_service.process_command(command)
            
            # Update UI
            self.control_panel.update_response(result.message, result.success)
            
            if result.success:
                self.execute_gimbal_command(result)
            
        except Exception as e:
            self.control_panel.update_response(f"Error: {str(e)}", False)
    
    def process_manual_command(self, command_data):
        """Process manual command"""
        try:
            action = command_data['action']
            value = command_data['value']
            speed = command_data['speed']
            
            if action == "pan":
                self.gimbal_controller.pan_to(value, speed)
            elif action == "tilt":
                self.gimbal_controller.tilt_to(value, speed)
                
            message = f"Manual {action}: {value}°"
            self.control_panel.update_response(message, True)
            
        except Exception as e:
            self.control_panel.update_response(f"Error: {str(e)}", False)
    
    def execute_gimbal_command(self, command):
        """Execute gimbal command"""
        if command.action == "home":
            self.gimbal_controller.move_to_home()
        elif command.action == "stop":
            self.gimbal_controller.stop()
        elif command.action == "pan":
            self.gimbal_controller.pan_to(command.value, command.speed)
        elif command.action == "tilt":
            self.gimbal_controller.tilt_to(command.value, command.speed)
    
    def gimbal_home(self):
        """Move to home position"""
        self.gimbal_controller.move_to_home()
        self.control_panel.update_response("Moving to home", True)
    
    def on_position_changed(self, position):
        """Handle position change"""
        self.status_panel.update_gimbal_position(position)
        self.renderer.update_gimbal_position(position)
    
    def on_status_changed(self, status):
        """Handle status change"""
        self.status_panel.update_status(status)
    
    def update_display(self):
        """Update display"""
        self.gimbal_controller.update()
    
    def closeEvent(self, event):
        """Handle window close"""
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        self.renderer.cleanup()
        self.gimbal_controller.cleanup()
        event.accept()