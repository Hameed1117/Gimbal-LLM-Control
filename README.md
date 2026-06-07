# Gimbal LLM Control

A cross-platform desktop application for controlling a PTZ camera gimbal and piloting a drone through natural language commands, powered by Large Language Models. Type a plain-English instruction and the system interprets it, routes it to the correct subsystem, and executes it in real time — rendered live in a 3D OpenGL scene at 60 fps.

Developed in association with **KWF — Kashmir World Foundation.**

---

## Screenshot

![Gimbal LLM Control](docs/Screenshot%202026-06-07%20183309.png)

---

## Features

### Natural Language Control
- Type any free-form command — the LLM interprets intent and routes it to the correct subsystem
- Live **scene context** (drone GPS position, all entity positions, current gimbal angles, zoom level) is injected into every LLM call so the model always knows the current world state
- Three-tier fallback: **OpenRouter** (cloud) → **Ollama** (local) → **keyword/regex parser** (fully offline, no internet required)

### PTZ Gimbal
| Axis | Range | PWM Signal |
|------|-------|-----------|
| Pan  | ±180° | 1000–2000 µs @ 50 Hz |
| Tilt | ±90°  | 1000–2000 µs @ 50 Hz |
| Zoom | 1×–30× | 1000–2000 µs @ 50 Hz |

- Smooth motor interpolation every frame at configurable speed (1–10)
- Real-time PWM value display with visual bar graphs in the status panel

### Drone Controller (Physics Engine)
- Starts on the ground — command it to take off and fly
- **Flight commands:** takeoff, land, hover, move (forward / back / left / right), ascend, descend, yaw, circle/orbit
- **GPS navigation:** converts real-world decimal degree coordinates to scene XYZ and navigates there
- Smooth waypoint-based movement with natural acceleration and braking
- Continuous orbit mode with automatic inward-banking heading
- Scene bounds enforced with soft wall bounce

### Entity Tracking
- Three entity types: **ground vehicles** (VH-01, VH-02, VH-03), **aerial UAVs** (UA-01, UA-02, UA-03), **birds** (BR-01, BR-02)
- `track <entity>` command locks the gimbal onto the nearest matching entity in real time
- **Coordinated tracking:** when the gimbal reaches its comfort limits (±75° pan / ±55° tilt), the drone autonomously yaws or adjusts altitude to keep the target centred without losing lock

### 3D OpenGL Renderer
- Real-time 3D scene at ~60 fps using PyOpenGL
- Drone body, gimbal rod, and PTZ camera rendered with correct physical proportions
- Dynamic field-of-view driven by zoom factor (60° wide angle → 2° telephoto)
- Top-view compass overlay showing pan direction
- **Import any `.obj` model** via *File → Import 3D Model* to hot-swap the mesh for vehicles, UAVs, or birds at runtime

### LLM Integration
- **OpenRouter** — access Claude, GPT-4o, Gemini, Llama, Mistral, Kimi K2, and more from a single API key
- **Ollama** — fully local inference, no internet connection needed; tested with `llama3.2:1b`
- **In-app model switcher** — live-fetches the OpenRouter model catalogue and lets you swap models mid-session without restarting
- All LLM calls are processed on a background thread — the UI never blocks

---

## Project Structure

```
gimbal-llm-control/
├── src/
│   ├── main.py                    # Entry point — GimbalApplication(QApplication)
│   ├── core/
│   │   ├── config.py              # Config dataclass, environment variable loading
│   │   ├── gimbal_controller.py   # PTZ motor logic, PWM output, smooth interpolation
│   │   └── drone_autopilot.py     # Physics drone — waypoints, orbit, GPS navigation
│   ├── gui/
│   │   ├── main_window.py         # Wires all subsystems; drives the 60 fps tick loop
│   │   ├── control_panel.py       # NLP command input, manual buttons, model selector
│   │   ├── status_panel.py        # PWM bar graphs, gimbal angles, drone state
│   │   └── model_dialog.py        # LLM model-switching dialog
│   ├── graphics/
│   │   ├── renderer.py            # QOpenGLWidget — 3D scene, entity drawing, FOV
│   │   ├── model_gen.py           # Procedural 3D mesh generation for default entities
│   │   └── obj_loader.py          # Wavefront OBJ parser for custom model import
│   └── llm/
│       └── llm_service.py         # LLMService — async worker, OpenRouter, Ollama, fallback
├── docs/
│   └── screenshot.png             # Application screenshot
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
| Ollama *(optional)* | For local LLM inference without an API key |
| OpenRouter API key *(optional)* | For cloud-based LLM access |

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
# Open .env and add your API keys
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
take off to 3 metres
fly forward 5 metres
circle clockwise with radius 4
fly to GPS 51.50722 N 0.12750 W at 30 metres
hover
land
```

**Gimbal / camera**
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

All settings are loaded from the `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openrouter` | `openrouter` or `ollama` |
| `OPENROUTER_API_KEY` | — | API key from [openrouter.ai](https://openrouter.ai/keys) |
| `OPENROUTER_MODEL` | `anthropic/claude-sonnet-4-6` | Any model ID on OpenRouter |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server address |
| `OLLAMA_MODEL` | `llama3.2:1b` | Local model name |
| `HOME_LAT` / `HOME_LON` | `51.507` / `-0.128` | GPS origin for real-world coordinate display |
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

**Signal flow:**
- `LLMService.command_processed` → `MainWindow` dispatches by `action` field
- `GimbalController.position_changed` → `StatusPanel` (PWM bars) + `GimbalRenderer` (FOV update)
- `DroneAutoPilot.position_changed` → `GimbalRenderer` (drone XYZ) + `StatusPanel` (coordinates)

---

## LLM Action Reference

| Action | Subsystem | Key Fields |
|--------|-----------|-----------|
| `pan` | Gimbal | `value` (°), `speed` |
| `tilt` | Gimbal | `value` (°), `speed` |
| `track` | Gimbal | `target_type` (vehicle / uav / bird) |
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

Output is placed in `dist/`. PyInstaller bundles Python, PyQt6, and PyOpenGL into a single portable folder that runs without a Python installation.

---

## Project Aim

This project was built to demonstrate how Large Language Models can serve as a practical, real-time interface for hardware control systems — removing the need for memorising commands, learning interfaces, or operating joysticks.

The core idea: a user describes what they want in plain English, and the system understands, interprets, and acts on it immediately. The simulation layer — physics drone, 3D OpenGL scene, PTZ gimbal with PWM output — is built to match real hardware behaviour as closely as possible. GPS coordinate mapping, motor interpolation, PWM signal generation, and servo speed control are all modelled as they would behave on physical equipment, making the path from simulation to real deployment a matter of swapping the output layer rather than rewriting the control logic.

Every LLM command is enriched with live scene context: the drone's current GPS position, heading, speed, gimbal pan/tilt/zoom angles, and the real-world coordinates of every tracked entity in the scene. The model reasons over this full state to produce the correct action — not just pattern-matching on keywords, but understanding spatial relationships and operating priorities.

---

## Future Expansions

### Real Hardware Integration
- Serial/PWM output to Arduino or Raspberry Pi GPIO for physical gimbal motor control
- MAVLink / ArduPilot / PX4 protocol support to connect to real drones and replace the physics simulation with live telemetry
- Per-axis servo calibration with configurable PWM min/max/centre values

### Computer Vision
- Live RTSP or USB camera feed integrated directly into the renderer viewport
- YOLO-based real-time object detection to auto-detect and classify targets in the camera frame
- Optical flow stabilisation to compensate for gimbal vibration and camera motion

### Voice and Multimodal Input
- Push-to-talk microphone input via Whisper (local or API) for hands-free operation
- Image-based commands — paste a camera frame and have the LLM describe the scene and issue corrective gimbal moves
- MediaPipe hand-tracking for gesture-based pan/tilt control

### Mission Planning
- Multi-step mission definition in plain English, decomposed into ordered command sequences by the LLM
- Automated survey and mapping path generation over a defined GPS bounding box
- Mission save and load as JSON for replay, sharing, and iteration

### Connectivity and Telemetry
- REST API endpoint so external scripts, mobile apps, or dashboards can issue commands
- WebSocket live telemetry stream for a browser-based monitoring interface
- Full session recording and playback at 60 fps for analysis and demonstration

### Simulation Improvements
- IMU and vibration model for testing stabilisation algorithms under realistic noise conditions
- Multi-drone support — spawn and independently command multiple drones in the same scene
- Dynamic weather effects including wind gusts and turbulence affecting drone physics
- Day/night lighting cycle with realistic visibility constraints

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
