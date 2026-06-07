"""Configuration management for Gimbal LLM Control"""

import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    """Application configuration"""
    
    # LLM Configuration
    llm_provider: str = "openrouter"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:1b"

    openai_api_key: Optional[str] = None

    # OpenRouter Configuration
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-opus-4-6"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    
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

    # GPS home position — origin of the scene in real-world coordinates.
    # Scene axes: +X = East, +Z = North, +Y = Up.
    # Override via env vars HOME_LAT / HOME_LON / HOME_ALT_MSL.
    home_lat: float = 51.5074    # decimal degrees (positive = North)
    home_lon: float = -0.1278    # decimal degrees (negative = West)
    home_alt_msl: float = 25.0   # metres above mean sea level at origin

    def __post_init__(self):
        """Load configuration from environment variables"""
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.ollama_url = os.getenv('OLLAMA_URL', self.ollama_url)

        if os.getenv('LLM_PROVIDER'):
            self.llm_provider = os.getenv('LLM_PROVIDER')
        self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY', self.openrouter_api_key)
        self.openrouter_model = os.getenv('OPENROUTER_MODEL', self.openrouter_model)

        if os.getenv('HOME_LAT'):
            self.home_lat = float(os.getenv('HOME_LAT'))
        if os.getenv('HOME_LON'):
            self.home_lon = float(os.getenv('HOME_LON'))
        if os.getenv('HOME_ALT_MSL'):
            self.home_alt_msl = float(os.getenv('HOME_ALT_MSL'))