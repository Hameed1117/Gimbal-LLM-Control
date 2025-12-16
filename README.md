# Gimbal LLM Control

A cross-platform desktop application for controlling camera gimbals using natural language commands powered by Large Language Models (LLMs).

## Features

- 🤖 **LLM Integration**: Control gimbal using natural language commands
- 🎮 **Manual Controls**: Direct gimbal control with buttons and sliders
- 🎯 **Real-time Visualization**: 2D gimbal position visualization
- 🔄 **Cross-platform**: Works on Windows, macOS, and Linux
- 🏠 **Local LLM Support**: Uses Ollama for local AI processing
- ☁️ **Cloud LLM Support**: Optional OpenAI API integration

## Screenshots

*[Add screenshots of your application here]*

## Prerequisites

- Python 3.9 or higher
- Ollama (for local LLM support)
- Virtual environment (recommended)

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/gimbal-llm-control.git
cd gimbal-llm-control
```

### 2. Create virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Install Ollama (for local LLM)
- **Windows**: Download from [ollama.ai](https://ollama.ai/download/windows)
- **macOS**: `brew install ollama`
- **Linux**: `curl -fsSL https://ollama.ai/install.sh | sh`

### 5. Pull LLM model
```bash
ollama pull llama3.2:1b
```

## Usage

### Run the application
```bash
python src/main.py
```

### LLM Commands Examples
- "Pan left 45 degrees"
- "Tilt up slowly"
- "Go to home position"
- "Stop movement"

### Manual Controls
- Use the manual control buttons for direct gimbal operation
- Adjust speed with the slider (1-10)
- Click "Home" to return to center position

## Configuration

The application uses environment variables for configuration:
```bash
# Optional: Create .env file for API keys
OPENAI_API_KEY=your_openai_key_here
LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
```

## Project Structure
```
gimbal-llm-control/
├── src/
│   ├── main.py                 # Application entry point
│   ├── core/
│   │   ├── config.py          # Configuration management
│   │   └── gimbal_controller.py # Gimbal logic
│   ├── gui/
│   │   ├── main_window.py     # Main application window
│   │   ├── control_panel.py   # Command input panel
│   │   └── status_panel.py    # Status display panel
│   ├── graphics/
│   │   └── renderer.py        # 2D gimbal visualization
│   └── llm/
│       └── llm_service.py     # LLM integration service
├── requirements.txt           # Python dependencies
└── README.md                 # This file
```

## Development

### Building executable
```bash
python build/build.py
```

### Running tests
```bash
pytest tests/
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Ollama](https://ollama.ai/) for local LLM support
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) for the GUI framework
- [OpenAI](https://openai.com/) for API integration support

## Support

If you encounter any issues or have questions, please [open an issue](https://github.com/khadhar17/gimbal-llm-control/issues).