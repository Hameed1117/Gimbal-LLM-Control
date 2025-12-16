"""Configuration management for Gimbal LLM Control"""

import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    """Application configuration"""
    
    # LLM Configuration
    llm_provider: str = "ollama"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:1b"
    ollama_enabled: bool = True
    
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-3.5-turbo"
    
    # Gimbal Configuration
    gimbal_pan_limit: float = 180.0
    gimbal_tilt_limit: float = 90.0
    gimbal_default_speed: int = 5
    
    # Graphics Configuration
    graphics_fps_target: int = 60
    graphics_vsync: bool = True
    
    # Window Configuration
    window_width: int = 1400
    window_height: int = 900
    window_theme: str = "dark"
    
    def __post_init__(self):
        """Load configuration from environment variables"""
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.ollama_url = os.getenv('OLLAMA_URL', self.ollama_url)
        
        if os.getenv('LLM_PROVIDER'):
            self.llm_provider = os.getenv('LLM_PROVIDER')