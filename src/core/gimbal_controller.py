"""Gimbal Controller for 3D gimbal simulation"""

import math
import logging
from typing import Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal

class GimbalController(QObject):
    """Controls gimbal position and movement"""
    
    position_changed = pyqtSignal(dict)
    status_changed = pyqtSignal(str)
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Current position
        self.pan = 0.0
        self.tilt = 0.0
        self.speed = 5
        
        # Movement state
        self.is_moving = False
        self.target_pan = 0.0
        self.target_tilt = 0.0
        
        # Status
        self.status = "Ready"
        
    def get_position(self) -> Dict[str, float]:
        """Get current gimbal position"""
        return {
            'pan': self.pan,
            'tilt': self.tilt,
            'speed': self.speed
        }
    
    def pan_to(self, angle: float, speed: int = 5):
        """Pan to specific angle"""
        self.target_pan = max(-180, min(180, angle))
        self.speed = max(1, min(10, speed))
        self.is_moving = True
        self.status_changed.emit("Moving")
        self.logger.info(f"Pan to {angle}° at speed {speed}")
        
    def tilt_to(self, angle: float, speed: int = 5):
        """Tilt to specific angle"""
        self.target_tilt = max(-90, min(90, angle))
        self.speed = max(1, min(10, speed))
        self.is_moving = True
        self.status_changed.emit("Moving")
        self.logger.info(f"Tilt to {angle}° at speed {speed}")
        
    def move_to_home(self):
        """Move to home position"""
        self.pan_to(0.0, 5)
        self.tilt_to(0.0, 5)
        self.logger.info("Moving to home position")
        
    def stop(self):
        """Stop movement"""
        self.is_moving = False
        self.target_pan = self.pan
        self.target_tilt = self.tilt
        self.status_changed.emit("Ready")
        self.logger.info("Movement stopped")
        
    def update(self):
        """Update gimbal position (called by main loop)"""
        if not self.is_moving:
            return
            
        # Smooth movement towards target
        pan_diff = self.target_pan - self.pan
        tilt_diff = self.target_tilt - self.tilt
        
        if abs(pan_diff) < 0.1 and abs(tilt_diff) < 0.1:
            # Close enough, stop movement
            self.pan = self.target_pan
            self.tilt = self.target_tilt
            self.is_moving = False
            self.status_changed.emit("Ready")
        else:
            # Move towards target
            move_speed = self.speed / 100.0
            self.pan += pan_diff * move_speed
            self.tilt += tilt_diff * move_speed
            
        self.position_changed.emit(self.get_position())
        
    def cleanup(self):
        """Cleanup resources"""
        self.stop()