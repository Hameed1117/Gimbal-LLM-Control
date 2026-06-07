"""LLM Service — natural-language control for gimbal, camera, and drone.

Control priority:
  1. GIMBAL  — pan / tilt / track / home / stop
  2. CAMERA  — zoom
  3. DRONE   — takeoff / land / move / hover / ascend / descend / yaw / circle
"""

import logging
import json
import re
from dataclasses import dataclass, field
from typing import Optional
from PyQt6.QtCore import QObject, QThread, pyqtSignal


@dataclass
class GimbalCommand:
    """Unified command returned by the LLM or fallback parser."""
    # ── Routing ──────────────────────────────────────────────────────────────
    action:      str            # see ACTION LIST below
    # ── Gimbal / gimbal-track ─────────────────────────────────────────────────
    value:       float = 0.0   # degrees (pan/tilt/yaw); zoom delta/factor; metres
    speed:       int   = 5     # 1–10
    target_type: str   = ""    # vehicle | uav | bird  (for "track")
    # ── Drone motion ─────────────────────────────────────────────────────────
    direction:   str   = ""    # forward | back | left | right  (drone_move)
    distance:    float = 3.0   # metres to travel               (drone_move)
    altitude:    float = 0.0   # target altitude for takeoff (0 = default)
    clockwise:   bool  = True  # circle direction               (drone_circle)
    # ── GPS navigation ────────────────────────────────────────────────────────
    gps_lat:     float = 0.0   # decimal degrees, positive = North (drone_goto_gps)
    gps_lon:     float = 0.0   # decimal degrees, positive = East  (drone_goto_gps)
    gps_alt:     float = 0.0   # metres MSL; 0 = maintain current altitude
    # ── Meta ─────────────────────────────────────────────────────────────────
    message:     str   = ""
    success:     bool  = True
    error:       Optional[str] = None

    # ACTION LIST
    # Gimbal:  pan | tilt | track | home | stop
    # Camera:  camera_zoom (delta ±)  |  camera_zoom_abs (absolute 1–30×)
    # Drone:   takeoff | land | drone_move | drone_hover
    #          drone_ascend | drone_descend | drone_yaw | drone_circle
    #          drone_goto_gps


# ── System prompt ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are the AI controller for a camera-gimbal system mounted on a controllable
drone.  You receive free-form natural-language commands and always return a
single JSON object — you NEVER say "not supported" or refuse a command.
When a command is ambiguous or unclear, pick the closest reasonable action.

━━━  CONTROL HIERARCHY  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Priority 1 — GIMBAL (pan / tilt / track / home / stop)
Priority 2 — CAMERA (zoom in / zoom out)
Priority 3 — DRONE  (takeoff / land / move / hover / ascend / descend / yaw / circle)

When a command clearly targets one subsystem, respond with that action only.
When ambiguous, favour Priority 1 (gimbal first).

━━━  GIMBAL CAPABILITIES  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• pan   – rotate camera horizontally: left = negative°, right = positive°
          range ±180°
• tilt  – pitch camera vertically: up = positive°, down = negative°
          range ±90°
• track – continuously aim gimbal at a scene entity (+ optional drone assist)
• home  – return both motors to 0°, stop all assists
• stop  – freeze all motor movement

Natural phrases for GIMBAL:
  "look right / swing right / pan right / camera right"  → pan positive°
  "look left / swing left / pan left / camera left"      → pan negative°
  "look up / tilt up / nose up / aim high"               → tilt positive°
  "look down / tilt down / aim down / dip"               → tilt negative°
  "track/follow/chase/watch/shadow/lock on [entity]"     → track
  "centre/home/reset/level/zero/straight"                → home
  "stop/halt/freeze/hold/pause/standby"                  → stop

━━━  CAMERA / ZOOM CAPABILITIES (PTZ axis 3)  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Zoom range: 1× (widest, 60° FOV) → 30× (most telephoto, 2° FOV).
Current zoom is reported in LIVE STATE as "zoom=N×".

• camera_zoom     – relative: value = zoom-factor DELTA (+in / −out)
• camera_zoom_abs – absolute: value = target zoom factor 1–30

Natural phrases:
  "zoom in / magnify / close up / telephoto"       → camera_zoom  value=+5
  "zoom in a lot / maximum zoom / full zoom"       → camera_zoom_abs value=30
  "zoom out / wide angle / pull back / wide view"  → camera_zoom  value=−5
  "zoom out fully / widest / reset zoom"           → camera_zoom_abs value=1
  "zoom to 5× / zoom to 10x / set zoom 15"        → camera_zoom_abs value=<N>

━━━  DRONE CAPABILITIES  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Drone starts on the ground.  Smooth waypoint-based physics: gradual accel,
deceleration on arrival, natural banking into turns.

• takeoff       – lift off to altitude metres (0 = default 2.5 m)
• land          – controlled descent to ground
• drone_move    – translate in direction (forward|back|left|right) by distance m
• drone_hover   – stop and hold current position
• drone_ascend  – climb value metres from current altitude
• drone_descend – descend value metres from current altitude
• drone_yaw     – rotate drone heading by value degrees (+ = clockwise)
• drone_circle  – orbit in a continuous circle; value = radius metres (default 3),
                  clockwise = true/false
• drone_goto_gps – navigate to a real-world GPS coordinate:
    gps_lat = decimal degrees (positive=North, negative=South)
    gps_lon = decimal degrees (positive=East,  negative=West)
    gps_alt = altitude MSL metres (0 = keep current altitude)

Natural phrases for DRONE:
  "take off / launch / lift off / get airborne / go up"  → takeoff
  "land / touch down / come down / set down / descend to ground" → land
  "fly forward / go forward / move ahead / push forward" → drone_move forward
  "go left / slide left / strafe left"                   → drone_move left
  "go right / slide right / strafe right"               → drone_move right
  "fly back / retreat / pull back / go backward"         → drone_move back
  "hover / hold / stay / maintain / freeze position"     → drone_hover
  "climb / go higher / rise / ascend / gain altitude"    → drone_ascend
  "drop / go lower / descend / lose altitude / sink"     → drone_descend
  "spin / rotate / turn / yaw / pivot"                   → drone_yaw
  "circle / orbit / loop / ring / go around / do a lap"  → drone_circle
  "circle clockwise / loop right"                        → drone_circle clockwise=true
  "circle counter-clockwise / loop left / anti-clockwise" → drone_circle clockwise=false
  "do a 360 / pirouette / full spin / full rotation"     → drone_yaw value=360
  "wander / roam / explore / patrol / drift around"      → drone_circle value=5 (large)
  "rush forward / sprint / go fast"                      → drone_move forward speed=9
  "drift gently left / ease left"                        → drone_move left speed=2 dist=2
  "fly to 51.5074, -0.1278 / navigate to lat lon"        → drone_goto_gps
  "go to GPS 51.5094° N 0.1278° W at 30 metres"         → drone_goto_gps gps_alt=30

━━━  SCENE ENTITIES  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ground vehicles (Y ≈ 0 m):
  VH-01 → orange/red car    VH-02 → blue car    VH-03 → green car

Aerial UAVs (Y ≈ 2 m):
  UA-01 → yellow drone    UA-02 → purple drone    UA-03 → orange drone

Birds (Y ≈ 5 m):
  BR-01 → silver/white bird    BR-02 → steel-blue bird

━━━  LIVE SCENE STATE (injected by system each call)  ━━━━━━━━━━━━━━━━━━━━━

━━━  SPEED & DISTANCE LANGUAGE  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Speed:
  "slowly / gently / softly / carefully / drift"  → speed 2–3
  normal (no qualifier)                           → speed 5
  "quickly / fast / rapid / rush / sprint / snap" → speed 8–10

Distance / angle:
  "a bit / slightly / little / nudge / gently"    → small  (gimbal 15° | drone 1.5 m)
  no qualifier                                    → medium (gimbal 45° | drone 3.0 m)
  "a lot / far / fully / all the way / maximum"   → large  (gimbal 90° | drone 6.0 m)

━━━  OUTPUT FORMAT  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Respond with ONLY a single JSON object — no markdown, no text outside JSON.
NEVER return an error or "not supported" — always pick the closest action.

{
  "action":      "<pan|tilt|track|home|stop|camera_zoom|camera_zoom_abs|takeoff|land|drone_move|drone_hover|drone_ascend|drone_descend|drone_yaw|drone_circle|drone_goto_gps>",
  "value":       <degrees for pan/tilt/yaw; zoom delta for camera_zoom; zoom factor 1-30 for camera_zoom_abs; metres for ascend/descend/circle-radius; altitude for takeoff; 0 otherwise>,
  "speed":       <integer 1–10>,
  "target_type": "<vehicle|uav|bird|empty string>",
  "direction":   "<forward|back|left|right|empty string>",
  "distance":    <metres for drone_move, default 3.0>,
  "altitude":    <target altitude metres for takeoff, 0 for default>,
  "clockwise":   <true or false, for drone_circle only>,
  "gps_lat":     <decimal degrees for drone_goto_gps, positive=North, 0 otherwise>,
  "gps_lon":     <decimal degrees for drone_goto_gps, positive=East, 0 otherwise>,
  "gps_alt":     <metres MSL for drone_goto_gps, 0 = keep current altitude>,
  "message":     "<short natural confirmation of what you understood>"
}
"""


# ── Background worker ──────────────────────────────────────────────────────────

class _LLMWorker(QThread):
    done = pyqtSignal(object)   # emits GimbalCommand

    def __init__(self, service: "LLMService", text: str, scene_context: str = ""):
        super().__init__()
        self._service       = service
        self._text          = text
        self._scene_context = scene_context

    def run(self):
        result = self._service._process_sync(self._text, self._scene_context)
        self.done.emit(result)


class _FetchModelsWorker(QThread):
    done = pyqtSignal(list)   # emits list of (display_name, model_id)

    def __init__(self, service: "LLMService"):
        super().__init__()
        self._service = service

    def run(self):
        self.done.emit(self._service.fetch_openrouter_models())


# ── LLM Service ────────────────────────────────────────────────────────────────

class LLMService(QObject):
    """Natural-language → unified command (gimbal + camera + drone).

    Primary: OpenRouter  |  Secondary: Ollama  |  Fallback: keyword parser.
    Use ``process_command_async(text, scene_context)`` — non-blocking.
    """

    command_processed   = pyqtSignal(object)   # GimbalCommand
    processing_started  = pyqtSignal()
    processing_finished = pyqtSignal()

    # Curated fallback list (used when API fetch fails or no key)
    CURATED_MODELS = [
        # ── Flagship models ────────────────────────────────────────────────────
        ("Claude Sonnet 4.6 — Fast + Smart",       "anthropic/claude-sonnet-4-6"),
        ("Claude Opus 4.6  — Most Capable",        "anthropic/claude-opus-4-6"),
        ("GPT-4o — OpenAI Flagship",               "openai/gpt-4o"),
        ("Gemini 2.0 Flash — Google Fast",         "google/gemini-2.0-flash"),
        # ── Kimi (Moonshot AI) ─────────────────────────────────────────────────
        ("Kimi K2 — Moonshot AI",                  "moonshotai/kimi-k2"),
        # ── Low-token / efficient models ───────────────────────────────────────
        ("GPT-4o Mini — OpenAI Efficient",         "openai/gpt-4o-mini"),
        ("Gemini Flash 1.5 8B — Ultra Efficient",  "google/gemini-flash-1.5-8b"),
        ("Llama 3.2 3B — Tiny + Fast",             "meta-llama/llama-3.2-3b-instruct"),
        ("Phi-3 Mini 128k — Microsoft Efficient",  "microsoft/phi-3-mini-128k-instruct"),
        ("Mistral 7B — Lean Open Source",          "mistralai/mistral-7b-instruct"),
    ]

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.ollama_available = self._test_ollama()
        self._worker: _LLMWorker | None = None

    # ── Connection helpers ────────────────────────────────────────────────────

    def _test_ollama(self) -> bool:
        try:
            import ollama
            ollama.Client(host=self.config.ollama_url).list()
            self.logger.info("Ollama connected")
            return True
        except Exception as e:
            self.logger.warning("Ollama not available: %s", e)
            return False

    def get_available_ollama_models(self) -> list:
        try:
            import ollama
            result = ollama.Client(host=self.config.ollama_url).list()
            return [m["name"] for m in result.get("models", [])]
        except Exception:
            return []

    def switch_model(self, model_name: str, provider: str = "ollama",
                     api_key: str = "") -> bool:
        if provider == "openrouter":
            self.config.llm_provider       = "openrouter"
            self.config.openrouter_api_key = api_key or self.config.openrouter_api_key
            self.config.openrouter_model   = model_name
            return True
        self.config.llm_provider = "ollama"
        self.config.ollama_model = model_name
        self.ollama_available    = self._test_ollama()
        return self.ollama_available

    def get_active_model_display(self) -> str:
        if self.config.llm_provider == "openrouter":
            return f"OR: {self.config.openrouter_model}"
        return self.config.ollama_model if self.ollama_available else "Fallback Parser"

    @property
    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    # ── OpenRouter model fetcher ──────────────────────────────────────────────

    def fetch_openrouter_models(self) -> list:
        """Return a list of (display_name, model_id) for top OpenRouter models."""
        api_key = self.config.openrouter_api_key
        if not api_key:
            return self.CURATED_MODELS

        try:
            import requests
            resp = requests.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=6,
            )
            if resp.status_code != 200:
                self.logger.warning("OpenRouter models API returned %d", resp.status_code)
                return self.CURATED_MODELS

            data = resp.json().get("data", [])

            priority_prefixes = [
                "anthropic/", "openai/", "google/", "meta-llama/",
                "mistralai/", "deepseek/", "cohere/", "moonshotai/",
                "microsoft/", "qwen/",
            ]
            filtered = [
                m for m in data
                if any(m.get("id", "").startswith(p) for p in priority_prefixes)
                and "context_length" in m
            ]
            filtered.sort(key=lambda m: m.get("context_length", 0), reverse=True)

            seen: set = set()
            result   = []
            for m in filtered:
                provider = m["id"].split("/")[0]
                if provider not in seen:
                    seen.add(provider)
                    name = m.get("name", m["id"])
                    ctx  = m.get("context_length", 0)
                    result.append((f"{name}  ({ctx // 1000}k ctx)", m["id"]))
                if len(result) >= 10:
                    break

            return result if len(result) >= 2 else self.CURATED_MODELS

        except Exception as e:
            self.logger.warning("OpenRouter model fetch failed: %s", e)
            return self.CURATED_MODELS

    def fetch_openrouter_models_async(self) -> _FetchModelsWorker:
        """Start an async model fetch; caller connects worker.done signal."""
        worker = _FetchModelsWorker(self)
        return worker

    # ── Async entry point (preferred) ────────────────────────────────────────

    def process_command_async(self, user_text: str, scene_context: str = "") -> bool:
        if self.is_busy:
            self.logger.warning("LLM busy — ignoring request")
            return False
        self._worker = _LLMWorker(self, user_text, scene_context)
        self._worker.done.connect(self._on_worker_done)
        self._worker.finished.connect(self._worker.deleteLater)
        self.processing_started.emit()
        self._worker.start()
        return True

    def _on_worker_done(self, result):
        self._worker = None
        self.processing_finished.emit()
        self.command_processed.emit(result)

    # ── Synchronous (internal / tests) ───────────────────────────────────────

    def _process_sync(self, user_text: str, scene_context: str = "") -> GimbalCommand:
        try:
            if self.config.llm_provider == "openrouter" and self.config.openrouter_api_key:
                return self._call_openrouter(user_text, scene_context)
            if self.ollama_available:
                return self._call_ollama(user_text, scene_context)
            return self._fallback(user_text)
        except Exception as e:
            self.logger.error("process_command failed: %s", e)
            return GimbalCommand(action="drone_hover", message=str(e), success=True)

    def process_command(self, user_text: str) -> GimbalCommand:
        return self._process_sync(user_text)

    # ── System prompt builder ─────────────────────────────────────────────────

    @staticmethod
    def _build_system(scene_context: str) -> str:
        if scene_context:
            return _SYSTEM_PROMPT + "\nCURRENT LIVE STATE:\n" + scene_context
        return _SYSTEM_PROMPT

    # ── LLM backends ─────────────────────────────────────────────────────────

    def _call_openrouter(self, text: str, scene_context: str = "") -> GimbalCommand:
        from openai import OpenAI
        client = OpenAI(
            base_url=self.config.openrouter_base_url,
            api_key=self.config.openrouter_api_key,
        )
        try:
            resp = client.chat.completions.create(
                model=self.config.openrouter_model,
                messages=[
                    {"role": "system", "content": self._build_system(scene_context)},
                    {"role": "user",   "content": text},
                ],
                temperature=0.2,
            )
            return self._parse(resp.choices[0].message.content.strip(), text)
        except Exception as e:
            self.logger.warning("OpenRouter failed: %s", e)
            return self._fallback(text)

    def _call_ollama(self, text: str, scene_context: str = "") -> GimbalCommand:
        import ollama
        try:
            client = ollama.Client(host=self.config.ollama_url)
            resp   = client.chat(
                model=self.config.ollama_model,
                messages=[
                    {"role": "system", "content": self._build_system(scene_context)},
                    {"role": "user",   "content": text},
                ],
                options={"temperature": 0.2},
            )
            return self._parse(resp["message"]["content"].strip(), text)
        except Exception as e:
            self.logger.warning("Ollama failed: %s", e)
            return self._fallback(text)

    # ── Response parsing ──────────────────────────────────────────────────────

    def _parse(self, raw: str, original: str) -> GimbalCommand:
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                raise ValueError("No JSON in response")
            data = json.loads(match.group())
            return GimbalCommand(
                action      = str(data.get("action", "drone_hover")),
                value       = float(data.get("value", 0.0)),
                speed       = max(1, min(10, int(data.get("speed", 5)))),
                target_type = str(data.get("target_type", "")),
                direction   = str(data.get("direction", "")).lower(),
                distance    = float(data.get("distance", 3.0)),
                altitude    = float(data.get("altitude", 0.0)),
                clockwise   = bool(data.get("clockwise", True)),
                gps_lat     = float(data.get("gps_lat", 0.0)),
                gps_lon     = float(data.get("gps_lon", 0.0)),
                gps_alt     = float(data.get("gps_alt", 0.0)),
                message     = str(data.get("message", "")),
                success     = True,
            )
        except Exception:
            return self._fallback(original)

    # ── Fallback keyword parser ───────────────────────────────────────────────

    _COLOUR_MAP = {
        "orange car":   "vehicle", "red car":    "vehicle",
        "blue car":     "vehicle", "green car":  "vehicle",
        "yellow drone": "uav",     "yellow mini": "uav",
        "purple drone": "uav",     "orange drone": "uav",
        "white bird":   "bird",    "silver bird": "bird",
        "blue bird":    "bird",    "steel bird":  "bird",
    }

    def _entity_type(self, c: str) -> str:
        for phrase, etype in self._COLOUR_MAP.items():
            if phrase in c:
                return etype
        if any(w in c for w in ("bird", "avian", "feather", "flock", "pigeon")):
            return "bird"
        if any(w in c for w in ("uav", "drone", "quadcopter", "mini", "aerial",
                                "copter", "rotor")):
            return "uav"
        return "vehicle"

    def _fallback(self, text: str) -> GimbalCommand:  # noqa: C901
        c    = text.lower().strip()
        nums = [float(n) for n in re.findall(r"[-+]?\d+\.?\d*", c)]

        def num(i, default=0.0):
            return nums[i] if i < len(nums) else default

        # Speed modifier
        speed = 5
        if any(w in c for w in ("slowly", "gently", "carefully", "slow",
                                 "softly", "drift", "ease", "lazy", "gradual")):
            speed = 2
        elif any(w in c for w in ("quickly", "fast", "rapid", "snap", "quick",
                                   "rush", "sprint", "bolt", "hurry", "speed")):
            speed = 9

        # Size / distance modifier
        def _dist(small=1.5, med=3.0, large=6.0) -> float:
            if any(w in c for w in ("a bit", "slightly", "little", "nudge",
                                     "tiny", "small", "inch", "touch")):
                return small
            if any(w in c for w in ("a lot", "far", "long", "fully", "all the way",
                                     "maximum", "max", "huge", "massive")):
                return large
            v = num(0)
            return v if v > 0.1 else med

        def _angle(small=15.0, med=45.0, large=90.0) -> float:
            if any(w in c for w in ("a bit", "slightly", "little", "nudge",
                                     "tiny", "small", "inch", "touch")):
                return small
            if any(w in c for w in ("a lot", "fully", "all the way", "maximum",
                                     "max", "full", "wide")):
                return large
            v = abs(num(0))
            return v if v > 0.1 else med

        # ── Emergency stop ────────────────────────────────────────────────────
        if any(w in c for w in ("emergency stop", "emergency", "abort", "kill")):
            return GimbalCommand(action="stop", message="Emergency stop")

        # ── DRONE: GPS navigation — detect lat/lon decimal patterns ───────────
        gps_coords = re.findall(r'[-+]?\d{1,3}\.\d{4,}', c)
        if len(gps_coords) >= 2:
            try:
                lat_v = float(gps_coords[0])
                lon_v = float(gps_coords[1])
                if re.search(r'\bsouth\b|\b[Ss]\b', c):
                    lat_v = -abs(lat_v)
                if re.search(r'\bwest\b|\b[Ww]\b', c):
                    lon_v = -abs(lon_v)
                alt_m = re.search(r'(?:at|alt|altitude|to)\s+(\d+\.?\d*)\s*m', c)
                alt_v = float(alt_m.group(1)) if alt_m else 0.0
                ns = 'N' if lat_v >= 0 else 'S'
                ew = 'E' if lon_v >= 0 else 'W'
                return GimbalCommand(
                    action="drone_goto_gps",
                    gps_lat=lat_v, gps_lon=lon_v, gps_alt=alt_v,
                    speed=speed,
                    message=f"Flying to {abs(lat_v):.5f}°{ns} {abs(lon_v):.5f}°{ew}"
                            + (f" at {alt_v:.1f}m MSL" if alt_v > 0 else ""),
                )
            except (ValueError, IndexError):
                pass

        # ── DRONE: circle / orbit / loop / wander ─────────────────────────────
        circle_kw = any(w in c for w in (
            "circle", "orbit", "loop", "ring", "lap", "go around",
            "spiral", "wander", "roam", "explore", "patrol", "drift around",
            "survey", "sweep area",
        ))
        if circle_kw:
            r = num(0, 0.0)
            if r < 0.5:
                r = 5.0 if any(w in c for w in ("wander", "roam", "explore",
                                                  "patrol", "survey")) else 3.0
            cw = not any(w in c for w in ("counter", "anti", "ccw", "left",
                                           "anticlockwise", "counterclockwise"))
            return GimbalCommand(action="drone_circle", value=r, speed=speed,
                                 clockwise=cw,
                                 message=f"Orbiting r={r:.1f} m "
                                         f"{'CW' if cw else 'CCW'}")

        # ── DRONE: full-spin / pirouette / 360 ───────────────────────────────
        if any(w in c for w in ("360", "pirouette", "full spin", "full rotation",
                                  "spin around", "do a spin", "rotate 360",
                                  "full turn", "complete rotation")):
            cw = not any(w in c for w in ("left", "counter", "anti", "ccw"))
            deg = 360.0 if "360" in c else 360.0
            return GimbalCommand(action="drone_yaw", value=deg if cw else -deg,
                                 speed=speed, message="Spinning 360°")

        # ── DRONE: take off ───────────────────────────────────────────────────
        if any(w in c for w in ("take off", "takeoff", "launch", "lift off",
                                  "liftoff", "get airborne", "go airborne",
                                  "fly up", "launch drone", "start flying")):
            alt = num(0, 0.0)
            return GimbalCommand(action="takeoff", altitude=alt, speed=speed,
                                 message=f"Taking off"
                                         f"{f' to {alt:.1f} m' if alt > 0 else ''}")

        # ── DRONE: land ───────────────────────────────────────────────────────
        if any(w in c for w in ("land", "landing", "touch down", "touchdown",
                                  "return to ground", "come down", "set down",
                                  "go to ground", "put it down", "descend to ground")):
            return GimbalCommand(action="land", speed=speed, message="Landing")

        # ── DRONE: hover / hold ───────────────────────────────────────────────
        if any(w in c for w in ("hover", "hold position", "stay put", "hold still",
                                  "maintain position", "freeze in place",
                                  "stop moving", "stay here", "park")):
            return GimbalCommand(action="drone_hover", message="Hovering in place")

        # ── DRONE: ascend ─────────────────────────────────────────────────────
        if any(w in c for w in ("ascend", "climb", "go higher", "fly higher",
                                  "rise up", "gain altitude", "go up", "move up",
                                  "increase altitude", "higher", "up more")):
            val = _dist(small=1.0, med=2.0, large=4.0)
            return GimbalCommand(action="drone_ascend", value=val, speed=speed,
                                 message=f"Ascending {val:.1f} m")

        # ── DRONE: descend ────────────────────────────────────────────────────
        if any(w in c for w in ("descend", "go lower", "fly lower", "lose altitude",
                                  "drop altitude", "drop", "sink", "lower", "go down",
                                  "decrease altitude", "down more", "come down lower")):
            val = _dist(small=1.0, med=2.0, large=4.0)
            return GimbalCommand(action="drone_descend", value=val, speed=speed,
                                 message=f"Descending {val:.1f} m")

        # ── DRONE: yaw / turn / spin ──────────────────────────────────────────
        if any(w in c for w in ("rotate the drone", "yaw", "spin the drone",
                                  "turn the drone", "rotate drone", "pivot drone",
                                  "face", "point drone")):
            deg = _angle(small=30.0, med=45.0, large=90.0)
            direction = -1 if any(w in c for w in ("left", "anti", "counter")) else 1
            return GimbalCommand(action="drone_yaw", value=direction * deg,
                                 speed=speed,
                                 message=f"Yaw {'left' if direction < 0 else 'right'}"
                                         f" {deg:.0f}°")

        # ── DRONE: directional movement ───────────────────────────────────────
        fly_kw = any(w in c for w in (
            "fly", "move the drone", "go ", "travel", "navigate",
            "move drone", "pilot", "drive", "push", "send it",
            "advance", "proceed", "head ", "shoot forward", "dart",
            "rush", "sprint toward",
        ))
        drone_dir = None
        # Direct direction keywords even without fly_ prefix
        if any(w in c for w in ("forward", "forwards", "ahead", "straight ahead")):
            drone_dir = "forward"
        elif any(w in c for w in ("backward", "backwards", "behind", "reverse",
                                   "retreat", "pull back", "back up")):
            drone_dir = "back"
        elif "go left" in c or "move left" in c or "fly left" in c or "slide left" in c or "strafe left" in c:
            drone_dir = "left"
        elif "go right" in c or "move right" in c or "fly right" in c or "slide right" in c or "strafe right" in c:
            drone_dir = "right"
        elif fly_kw:
            if "left" in c:  drone_dir = "left"
            elif "right" in c: drone_dir = "right"
            elif "back" in c:  drone_dir = "back"

        if drone_dir is not None:
            dist = _dist()
            return GimbalCommand(action="drone_move", direction=drone_dir,
                                 distance=dist, speed=speed,
                                 message=f"Flying {drone_dir} {dist:.1f} m")

        # ── CAMERA: zoom ──────────────────────────────────────────────────────
        zoom_kw = any(w in c for w in ("zoom", "magnify", "close up", "closer",
                                        "telephoto", "get closer", "wide angle",
                                        "wide shot", "wider view", "pull back camera"))
        if zoom_kw:
            # Absolute zoom: "zoom to 5x", "zoom to 10", "set zoom 8"
            zoom_to_m = re.search(r'zoom\s+to\s+(\d+\.?\d*)\s*x?', c) or \
                        re.search(r'set\s+zoom\s+(\d+\.?\d*)', c)
            if zoom_to_m:
                factor = max(1.0, min(30.0, float(zoom_to_m.group(1))))
                return GimbalCommand(action="camera_zoom_abs", value=factor,
                                     speed=speed, message=f"Zoom to {factor:.1f}×")
            if any(w in c for w in ("maximum zoom", "max zoom", "full zoom",
                                     "fully zoom", "zoom fully")):
                return GimbalCommand(action="camera_zoom_abs", value=30.0,
                                     speed=speed, message="Maximum zoom (30×)")
            if any(w in c for w in ("zoom reset", "widest", "full wide", "1x",
                                     "one x", "wide angle", "wide shot", "wider view")):
                return GimbalCommand(action="camera_zoom_abs", value=1.0,
                                     speed=speed, message="Widest angle (1×)")
            # Relative zoom delta
            if any(w in c for w in ("zoom out", "pull back camera", "wide")):
                delta = -(abs(num(0, 5.0)) if nums else 5.0)
                if any(w in c for w in ("a bit", "slightly", "little")):
                    delta = -2.0
                elif any(w in c for w in ("a lot", "far", "maximum", "fully")):
                    delta = -15.0
                return GimbalCommand(action="camera_zoom", value=delta,
                                     speed=speed, message=f"Zoom out {abs(delta):.0f}×")
            # Default: zoom in
            delta = abs(num(0, 5.0)) if nums else 5.0
            if any(w in c for w in ("a bit", "slightly", "little", "nudge")):
                delta = 2.0
            elif any(w in c for w in ("a lot", "far", "telephoto")):
                delta = 10.0
            return GimbalCommand(action="camera_zoom", value=delta,
                                 speed=speed, message=f"Zoom in {delta:.0f}×")

        # ── GIMBAL: stop ──────────────────────────────────────────────────────
        if any(w in c for w in ("stop", "halt", "freeze", "cease", "pause gimbal")):
            return GimbalCommand(action="stop", message="Stopping gimbal")

        # ── GIMBAL: home ──────────────────────────────────────────────────────
        if any(w in c for w in ("home", "centre", "center", "reset", "level",
                                  "straight", "zero", "return gimbal", "default",
                                  "calibrate", "recenter")):
            return GimbalCommand(action="home", message="Centering gimbal")

        # ── GIMBAL: track ─────────────────────────────────────────────────────
        if any(w in c for w in ("track", "follow", "chase", "watch", "monitor",
                                  "shadow", "tail", "lock on", "pursue",
                                  "keep on", "stay on", "aim at", "point at",
                                  "look at", "focus on", "target", "stare at")):
            tt = self._entity_type(c)
            return GimbalCommand(action="track", target_type=tt, speed=speed,
                                 message=f"Tracking nearest {tt}")

        # ── GIMBAL: pan ───────────────────────────────────────────────────────
        pan_kw = any(w in c for w in (
            "pan", "rotate camera", "yaw camera", "swing", "turn camera",
            "turn gimbal", "look left", "look right", "camera left",
            "camera right", "face left", "face right", "sweep",
            "scan left", "scan right",
        ))
        dir_only_lr = not pan_kw and any(w in c for w in ("right", "left"))

        if pan_kw or dir_only_lr:
            deg       = _angle()
            direction = -1 if any(w in c for w in ("left", "west", "anti")) else 1
            return GimbalCommand(action="pan", value=direction * deg, speed=speed,
                                 message=f"Panning {'left' if direction < 0 else 'right'}"
                                         f" {deg:.0f}°")

        # ── GIMBAL: tilt ──────────────────────────────────────────────────────
        tilt_kw = any(w in c for w in (
            "tilt", "pitch", "look up", "look down", "aim up", "aim down",
            "point up", "point down", "camera up", "camera down",
            "elevate", "depress", "up", "down",
        ))
        if tilt_kw:
            deg       = _angle(small=15.0, med=30.0, large=90.0)
            direction = -1 if any(w in c for w in ("down", "lower", "ground",
                                                     "depress")) else 1
            return GimbalCommand(action="tilt", value=direction * deg, speed=speed,
                                 message=f"Tilting {'up' if direction > 0 else 'down'}"
                                         f" {deg:.0f}°")

        # ── Final fallback: always do something sensible ──────────────────────
        # Never return an error. Default to centering the gimbal — safe, visible,
        # and signals the system received the command.
        self.logger.info("Unmatched command '%s' — defaulting to gimbal home", text)
        return GimbalCommand(
            action="home", success=True,
            message=f"Centering — try: 'take off', 'fly forward', "
                    "'circle', 'track the orange car', 'zoom in'",
        )
