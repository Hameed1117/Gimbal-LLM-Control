#!/usr/bin/env python3
"""
Gimbal LLM Control - Main Application Entry Point
Cross-platform gimbal control with LLM integration built in Python
"""

import sys
import os
import logging
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

# PyQt6 imports
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

# Application imports
from core.config import Config
from core.gimbal_controller import GimbalController
from llm.llm_service import LLMService
from gui.main_window import MainWindow

def setup_logging():
    """Setup application logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('gimbal_app.log')
        ]
    )

class GimbalApplication(QApplication):
    """Main application class"""
    
    def __init__(self, argv):
        super().__init__(argv)
        
        # Set application properties
        self.setApplicationName("Gimbal LLM Control")
        self.setApplicationVersion("1.0.0")
        
        # Setup logging
        setup_logging()
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.config = None
        self.gimbal_controller = None
        self.llm_service = None
        self.main_window = None
        
    def initialize_components(self):
        """Initialize application components"""
        
        try:
            # Load configuration
            self.config = Config()
            self.logger.info("Configuration loaded")
            
            # Initialize gimbal controller
            self.gimbal_controller = GimbalController(self.config)
            self.logger.info("Gimbal controller initialized")
            
            # Initialize LLM service
            self.llm_service = LLMService(self.config)
            self.logger.info("LLM service initialized")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Component initialization failed: {e}")
            self.show_error("Initialization Error", f"Failed to initialize components:\n{str(e)}")
            return False
    
    def create_main_window(self):
        """Create and show the main window"""
        
        try:
            self.main_window = MainWindow(
                self.config,
                self.llm_service,
                self.gimbal_controller
            )
            
            self.main_window.show()
            self.logger.info("Main window created and shown")
            return True
            
        except Exception as e:
            self.logger.error(f"Main window creation failed: {e}")
            self.show_error("Window Creation Error", f"Failed to create main window:\n{str(e)}")
            return False
    
    def show_error(self, title: str, message: str):
        """Show error message box"""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.exec()
    
    def run(self):
        """Run the application"""
        
        self.logger.info("Starting Gimbal LLM Control application")
        
        # Initialize all components
        if not self.initialize_components():
            return False
            
        # Create and show main window
        if not self.create_main_window():
            return False
            
        self.logger.info("Application started successfully")
        return True

def main():
    """Main entry point"""
    
    # Create application
    app = GimbalApplication(sys.argv)
    
    # Run application
    if app.run():
        # Start event loop
        sys.exit(app.exec())
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()