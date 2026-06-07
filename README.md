# Gimbal LLM Control

A cross-platform desktop application that lets you control a camera gimbal and pilot a drone entirely through natural language. Type a command like *"take off, fly forward, then track the orange car"* and the LLM translates it into precise PTZ motor instructions and physics-based flight manoeuvres — rendered live in a 3D OpenGL scene at 60 fps.

Built as an AI-engineering portfolio project demonstrating real-time LLM integration, physics simulation, and hardware-ready motor control output.

---

## Demo

> *Screenshots / GIF coming soon — run `python src/main.py` to see it live.*

---

## Features

### Natural Language Control
- Type any free-form command — the LLM interprets intent and routes it to the correct subsystem
- Live **scene context** (drone GPS position, all entity positions, current gimbal angles) is injected into every LLM call so the model always knows the world state
- Three-tier fallback: **OpenRouter** (cloud) → **Ollama** (local) → **keyword/regex parser** (fully offline)

### PTZ Gimbal
| Axis | Range | PWM Signal |
|------|-------|-----------|
| Pan  | ±180° | 1000–2000 µs @ 50 Hz |
| Tilt | ±90°  | 1000–2000 µs @ 50 Hz |
| Zoom | 1×–30× | 1000–2000 µs @ 50 Hz |

- Smooth motor interpolation every frame (configurable speed 1–10)
- Real-time PWM value display in the status panel

### Drone Autopilot (Physics Engine)
- Starts on the ground — command it to take off and explore
- **Commands:** takeoff, land, hover, move (forward/back/left/right), ascend, descend, yaw, circle/orbit
- **GPS navigation:** `drone_goto_gps` converts real-world coordinates (decimal degrees) to scene XYZ
- Smooth waypoint-based navigation with natural acceleration and braking
- Orbit mode with automatic inward-banking heading
- Scene bounds enforced with soft wall bounce

### Entity Tracking
- Three entity types in the scene: **ground vehicles** (VH-01/02/03), **aerial UAVs** (UA-01/02/03), **birds** (BR-01/02)
- `track <entity>` command locks the gimbal onto the nearest matching entity
- **Coordinated tracking:** when gimbal reaches ±75° pan or ±55° tilt, the drone autonomously yaws / adjusts altitude to keep the target centred

### 3D OpenGL Renderer
- Real-time scene at ~60 fps using PyOpenGL
- Drone body, gimbal rod, and PTZ camera rendered in 3D
- Dynamic field-of-view driven by zoom factor (60° wide → 2° telephoto)
- **Import any `.obj` model** via *File → Import 3D Model* to hot-swap vehicles, UAVs, or birds at runtime

### LLM Integration
- **OpenRouter** — access Claude, GPT-4o, Gemini, Llama, Mistral, Kimi K2, and more from one API key
- **Ollama** — fully local inference; tested with `llama3.2:1b` and other models
- **In-app model switcher** — live fetches the OpenRouter catalogue and lets you swap models mid-session
- Async processing (non-blocking UI with visual busy indicator)

---

## Project Structure

```
gimbal-llm-control/
├── src/
│   ├── main.py                    # Entry point — GimbalApplication(QApplication)
│   ├── core/
│   │   ├── config.py              # Config dataclass, env var loading
│   │   ├── gimbal_controller.py   # PTZ motor logic, PWM output, smooth interpolation
│   │   └── drone_autopilot.py     # Physics-based drone — waypoints, orbit, GPS nav
│   ├── gui/
│   │   ├── main_window.py         # Wires all subsystems; 60 fps tick loop
│   │   ├── control_panel.py       # LLM input, manual buttons, model selector
│   │   ├── status_panel.py        # PWM bars, gimbal angles, drone state
│   │   └── model_dialog.py        # LLM model-switching dialog
│   ├── graphics/
│   │   ├── renderer.py            # QOpenGLWidget — 3D scene, entity drawing, FOV
│   │   ├── model_gen.py           # Procedural 3D mesh generation for default entities
│   │   └── obj_loader.py          # Wavefront OBJ parser for custom model import
│   └── llm/
│       └── llm_service.py         # LLMService — async worker, OpenRouter, Ollama, fallback
├── assets/                        # Runtime model/texture cache (gitignored)
├── .env.example                   # Copy to .env and fill in your API keys
├── requirements.txt
└── README.md
```

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.10+ | 3.9 minimum; 3.11 recommended |
| PyQt6 | GUI framework |
| PyOpenGL | 3D rendering |
| Ollama *(optional)* | For local LLM inference |
| OpenRouter API key *(optional)* | For cloud LLM access |

---

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/Hameed1117/Gimbal-LLM-Control.git
cd Gimbal-LLM-Control
```

### 2. Create and activate a virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
```bash
cp .env.example .env
# Edit .env and add your API keys
```

### 5. (Optional) Set up Ollama for local LLM

**Install:**
- **Windows / macOS:** Download from [ollama.ai](https://ollama.ai)
- **Linux:** `curl -fsSL https://ollama.ai/install.sh | sh`

**Pull a model:**
```bash
ollama pull llama3.2:1b
```

---

## Usage

```bash
python src/main.py
```

### Example Commands

**Drone flight**
```
take off
take off to 5 metres
fly forward 10 metres quickly
circle clockwise with radius 4
fly to GPS 51.50722 N 0.12750 W at 30 metres
land
```

**Gimbal control**
```
pan right 45 degrees
tilt up slowly
look left a bit
zoom in to 10x
zoom out fully
home
stop
```

**Entity tracking**
```
track the orange car
follow the yellow drone
watch the nearest bird
lock on to the blue vehicle
```

---

## Configuration

All configuration is via environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openrouter` | `openrouter` or `ollama` |
| `OPENROUTER_API_KEY` | — | API key from [openrouter.ai](https://openrouter.ai/keys) |
| `OPENROUTER_MODEL` | `anthropic/claude-sonnet-4-6` | Any model ID on OpenRouter |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server address |
| `OLLAMA_MODEL` | `llama3.2:1b` | Local model name |
| `HOME_LAT` / `HOME_LON` | `51.507` / `-0.128` | GPS reference origin for coordinate display |
| `HOME_ALT_MSL` | `10.0` | Home altitude in metres MSL |

---

## Architecture Overview

```
User input (text)
      │
      ▼
 ControlPanel  ──llm_command_requested──►  MainWindow
                                               │
                                               ├── LLMService (async QThread)
                                               │     ├── OpenRouter backend
                                               │     ├── Ollama backend
                                               │     └── Keyword fallback parser
                                               │             │
                                               │      GimbalCommand (dataclass)
                                               │             │
                                               ├── GimbalController  ──► PWM / pan / tilt / zoom
                                               ├── DroneAutoPilot    ──► physics / waypoints / GPS
                                               └── GimbalRenderer    ──► OpenGL 3D scene (60 fps)
```

---

## LLM Action Reference

| Action | Subsystem | Key Fields |
|--------|-----------|-----------|
| `pan` | Gimbal | `value` (°), `speed` |
| `tilt` | Gimbal | `value` (°), `speed` |
| `track` | Gimbal | `target_type` (vehicle/uav/bird) |
| `home` | Gimbal | — |
| `stop` | Gimbal | — |
| `camera_zoom` | Camera | `value` (delta ±) |
| `camera_zoom_abs` | Camera | `value` (1–30×) |
| `takeoff` | Drone | `altitude` (m), `speed` |
| `land` | Drone | `speed` |
| `drone_move` | Drone | `direction`, `distance` (m), `speed` |
| `drone_hover` | Drone | — |
| `drone_ascend` / `drone_descend` | Drone | `value` (m), `speed` |
| `drone_yaw` | Drone | `value` (°), `speed` |
| `drone_circle` | Drone | `value` (radius m), `clockwise`, `speed` |
| `drone_goto_gps` | Drone | `gps_lat`, `gps_lon`, `gps_alt` |

---

## Dependencies

```
PyQt6>=6.5.0
PyOpenGL>=3.1.6
numpy>=1.24.0
ollama>=0.1.7
openai>=1.3.0
requests>=2.31.0
python-dotenv>=1.0.0
pyinstaller>=6.0.0
```

---

## Building a Standalone Executable

```bash
python build/build.py
```

Output is placed in `dist/`. PyInstaller bundles Python, PyQt6, and PyOpenGL into a single portable folder.

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "Add your feature"`
4. Push the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

## Project Aim

This project was built to explore and demonstrate how Large Language Models can serve as a natural-language interface for real-time hardware control systems. The core idea is simple: instead of learning commands or using a joystick, a user should be able to describe what they want in plain English and have the system understand, interpret, and act on it — reliably and in real time.

The simulation layer (physics drone, 3D scene, PTZ gimbal) was built to be a faithful stand-in for real hardware, with PWM output, GPS coordinate mapping, and motor interpolation all modelled as they would behave on actual equipment. This makes the transition from simulation to physical deployment straightforward — the control logic does not need to change, only the output layer.

Beyond the technical implementation, this project is a proof of concept for **LLM-driven autonomous systems** — where the model is not just answering questions but actively controlling physical processes based on live environmental context. Every command the LLM processes includes the current drone position, gimbal angles, zoom level, and the GPS coordinates of every tracked entity in the scene. The model reasons over that state to produce the right action, not just pattern-match on the input text.

---

## Future Expansions

### Real Hardware Integration
- Serial/PWM output to Arduino or Raspberry Pi GPIO for physical gimbal control
- MAVLink / ArduPilot / PX4 protocol support to replace the physics simulation with real drone telemetry
- RC servo calibration per axis with configurable PWM min/max/centre

### Computer Vision
- Live RTSP or USB camera feed integrated into the renderer
- YOLO-based object detection to auto-detect and classify real-world targets
- Optical flow stabilisation to smooth the gimbal against camera motion

### Voice and Multimodal Input
- Push-to-talk microphone input via Whisper (local or API)
- Image-based commands — paste a frame and have the LLM describe and react to the scene
- MediaPipe hand-tracking for gesture-based pan/tilt control

### Mission Planning
- Multi-step mission definition in plain English, decomposed into ordered command sequences by the LLM
- Survey and mapping path generation over a GPS bounding box
- Mission save/load as JSON for replay and sharing

### Connectivity and Telemetry
- REST API endpoint so external scripts or mobile apps can drive the system
- WebSocket live telemetry stream for a browser-based dashboard
- Full session recording and playback at 60 fps for debugging and demo

### Simulation Improvements
- IMU and vibration model for testing stabilisation algorithms
- Multi-drone support — independently command multiple drones in the same scene
- Dynamic weather effects including wind gusts and turbulence
- Day/night lighting cycle matching real-world visibility conditions

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgements

- [Ollama](https://ollama.ai/) — local LLM runtime
- [OpenRouter](https://openrouter.ai/) — unified API for cloud LLMs
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — Python bindings for Qt 6
- [PyOpenGL](https://pyopengl.sourceforge.net/) — OpenGL bindings for Python
- [Anthropic](https://anthropic.com/) — Claude models used as the primary LLM backend

---

*Developed in association with **KWF — Kashmir World Foundation.***
