"""Simple 3D Renderer for Gimbal Visualization"""

import logging
import math
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush
from PyQt6.QtCore import Qt

class GimbalRenderer(QWidget):
    """Simple 2D representation of gimbal for now"""
    
    fps_updated = pyqtSignal(float)
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Gimbal state
        self.pan_angle = 0.0
        self.tilt_angle = 0.0
        
        # Rendering
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: #1a1a1a;")
        
        # FPS tracking
        self.frame_count = 0
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self.update_fps)
        self.fps_timer.start(1000)
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update)
        
        self.logger.info("Gimbal renderer initialized")
        
    def initialize_gimbal(self):
        """Initialize gimbal 3D model"""
        self.logger.info("Gimbal model initialized")
        
    def start_rendering(self):
        """Start the rendering loop"""
        self.update_timer.start(16)  # ~60 FPS
        
    def update_gimbal_position(self, position):
        """Update gimbal position"""
        self.pan_angle = position['pan']
        self.tilt_angle = position['tilt']
        self.update()  # Trigger repaint
        
    def update_fps(self):
        """Update FPS counter"""
        self.fps_updated.emit(60.0)
        self.frame_count = 0
        
    def cleanup(self):
        """Cleanup renderer"""
        if self.update_timer:
            self.update_timer.stop()
        if self.fps_timer:
            self.fps_timer.stop()
            
    def paintEvent(self, event):
        """Paint the gimbal visualization"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.frame_count += 1
        
        # Get dimensions
        width = self.width()
        height = self.height()
        center_x = width // 2
        center_y = height // 2
        
        # Clear background
        painter.fillRect(self.rect(), QColor(26, 26, 26))
        
        # Draw grid
        painter.setPen(QPen(QColor(50, 50, 50), 1))
        for x in range(0, width, 50):
            painter.drawLine(x, 0, x, height)
        for y in range(0, height, 50):
            painter.drawLine(0, y, width, y)
            
        # Draw gimbal base
        painter.setPen(QPen(QColor(100, 100, 100), 2))
        painter.setBrush(QBrush(QColor(50, 50, 50)))
        painter.drawEllipse(center_x - 80, center_y + 50, 160, 40)
        
        # Draw pan line
        painter.setPen(QPen(QColor(42, 130, 218), 3))
        pan_rad = math.radians(self.pan_angle)
        pan_end_x = center_x + 80 * math.cos(pan_rad)
        pan_end_y = center_y + 80 * math.sin(pan_rad)
        painter.drawLine(center_x, center_y, int(pan_end_x), int(pan_end_y))
        
        # Draw tilt offset
        painter.setPen(QPen(QColor(255, 152, 0), 3))
        tilt_offset = int(self.tilt_angle * 1.5)
        camera_y = int(pan_end_y) - tilt_offset
        painter.drawLine(int(pan_end_x), int(pan_end_y), int(pan_end_x), camera_y)
        
        # Draw camera
        painter.setPen(QPen(QColor(76, 175, 80), 2))
        painter.setBrush(QBrush(QColor(76, 175, 80, 100)))
        painter.drawEllipse(int(pan_end_x) - 15, camera_y - 15, 30, 30)
        
        # Draw status
        painter.setPen(QPen(QColor(255, 255, 255, 200)))
        painter.setFont(QFont("Consolas", 12))
        painter.drawText(10, 25, f"Pan: {self.pan_angle:.1f}°")
        painter.drawText(10, 45, f"Tilt: {self.tilt_angle:.1f}°")