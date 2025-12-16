"""LLM Service for Gimbal Control"""

import logging
import json
import re
from dataclasses import dataclass
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal

@dataclass
class GimbalCommand:
    """Structured gimbal command"""
    action: str  # pan, tilt, home, stop
    value: float = 0.0  # degrees
    speed: int = 5  # 1-10
    message: str = ""
    success: bool = True
    error: Optional[str] = None

class LLMService(QObject):
    """LLM service with Ollama integration"""
    
    command_processed = pyqtSignal(object)  # GimbalCommand
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Test Ollama connection
        self.ollama_available = self._test_ollama_connection()
        
    def _test_ollama_connection(self) -> bool:
        """Test if Ollama is available"""
        try:
            import ollama
            client = ollama.Client(host=self.config.ollama_url)
            models = client.list()
            self.logger.info("Ollama connected successfully")
            return True
        except Exception as e:
            self.logger.warning(f"Ollama not available: {e}")
            return False
    
    def process_command(self, command: str) -> GimbalCommand:
        """Process natural language command"""
        try:
            if self.ollama_available:
                return self._process_with_ollama(command)
            else:
                return self._fallback_parsing(command)
        except Exception as e:
            self.logger.error(f"Command processing failed: {e}")
            return GimbalCommand(
                action="error",
                message=f"Error: {str(e)}",
                success=False,
                error=str(e)
            )
    
    def _process_with_ollama(self, command: str) -> GimbalCommand:
        """Process command using Ollama"""
        import ollama
        
        system_prompt = """You are a gimbal controller. Parse commands and return ONLY JSON:
{"action": "pan"|"tilt"|"home"|"stop", "value": degrees, "speed": 1-10, "message": "confirmation"}

Examples:
"pan left 45" → {"action":"pan","value":-45,"speed":5,"message":"Panning left 45 degrees"}
"tilt up 30" → {"action":"tilt","value":30,"speed":5,"message":"Tilting up 30 degrees"}
"go home" → {"action":"home","value":0,"speed":5,"message":"Moving to home position"}"""
        
        try:
            client = ollama.Client(host=self.config.ollama_url)
            response = client.chat(
                model=self.config.ollama_model,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': command}
                ]
            )
            
            response_text = response['message']['content'].strip()
            return self._parse_llm_response(response_text, command)
            
        except Exception as e:
            self.logger.warning(f"Ollama processing failed: {e}")
            return self._fallback_parsing(command)
    
    def _parse_llm_response(self, response: str, original_command: str) -> GimbalCommand:
        """Parse LLM JSON response"""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', response)
            if not json_match:
                raise ValueError("No JSON found")
            
            data = json.loads(json_match.group())
            
            return GimbalCommand(
                action=data.get('action', 'error'),
                value=float(data.get('value', 0)),
                speed=max(1, min(10, int(data.get('speed', 5)))),
                message=data.get('message', f"Executing {data.get('action')} command"),
                success=True
            )
            
        except Exception as e:
            return self._fallback_parsing(original_command)
    
    def _fallback_parsing(self, command: str) -> GimbalCommand:
        """Fallback regex parsing"""
        cmd = command.lower().strip()
        
        # Home position
        if any(word in cmd for word in ['home', 'center']):
            return GimbalCommand(
                action="home",
                message="Moving to home position"
            )
        
        # Stop
        if any(word in cmd for word in ['stop', 'halt']):
            return GimbalCommand(
                action="stop", 
                message="Stopping movement"
            )
        
        # Extract number
        numbers = re.findall(r'\d+', cmd)
        degrees = int(numbers[0]) if numbers else 30
        
        # Pan commands
        if any(word in cmd for word in ['pan', 'left', 'right']):
            direction = -1 if 'left' in cmd else 1
            return GimbalCommand(
                action="pan",
                value=direction * degrees,
                message=f"Panning {'left' if direction < 0 else 'right'} {degrees}°"
            )
        
        # Tilt commands  
        if any(word in cmd for word in ['tilt', 'up', 'down']):
            direction = 1 if 'up' in cmd else -1
            return GimbalCommand(
                action="tilt",
                value=direction * degrees,
                message=f"Tilting {'up' if direction > 0 else 'down'} {degrees}°"
            )
        
        return GimbalCommand(
            action="error",
            message="Command not understood",
            success=False
        )