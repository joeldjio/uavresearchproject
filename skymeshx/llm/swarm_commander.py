"""
SwarmCommander — Natural language control of drone swarms via LLM.

Based on: SkySim (Shibu et al., 2025) arXiv:2602.01226
    "SkySim: A ROS2-based Simulation Environment for Natural Language
     Control of Drone Swarms using Large Language Models"

Architecture:
    User text → LLM (with swarm state context) → JSON waypoints
                                                       ↓
                                              APF Safety Filter
                                                       ↓
                                              CoordinatorUAVModel.goto_all()

Supported LLM backends:
    "gemini"   — Google Gemini (requires: pip install google-generativeai)
    "openai"   — OpenAI GPT-4o (requires: pip install openai)
    "ollama"   — Local Ollama server (requires: ollama running locally)
    "mock"     — Deterministic mock for testing (no API key needed)

Supported formation commands (examples):
    "Form a circle with 5m radius"
    "Line up facing north"
    "V formation, 3m spacing"
    "Return to base"
    "Land all drones"
    "Move north 10 meters"
    "Hover in place"
    "Grid formation 4x4"
    "Scatter to corners"

Usage:
    from skymeshx.llm import SwarmCommander
    from skymeshx.safety import APFSafetyFilter, Pose3D

    commander = SwarmCommander(
        backend="gemini",
        api_key="YOUR_KEY",
        apf=APFSafetyFilter(min_separation=2.0),
    )

    # Register current drone positions
    commander.update_state({
        "D1": Pose3D(0, 0, 10),
        "D2": Pose3D(3, 0, 10),
        "D3": Pose3D(6, 0, 10),
    })

    # Send natural language command
    result = commander.command("Form a circle with 5 meter radius")
    print(result.waypoints)   # {drone_id: Pose3D}
    print(result.explanation) # LLM explanation
"""
import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from skymeshx.safety.apf import APFSafetyFilter, Pose3D
from skymeshx.exceptions import ConfigurationError, LLMResponseError


@dataclass
class CommandResult:
    """Result of a SwarmCommander.command() call."""
    success:     bool
    waypoints:   Dict[str, Pose3D]      # safe waypoints per drone
    raw_waypoints: Dict[str, Pose3D]    # before APF filter
    explanation: str                     # LLM explanation
    command:     str                     # original user command
    latency_ms:  float = 0.0
    error:       str   = ""


class SwarmCommander:
    """
    Translates natural language commands into drone swarm waypoints.

    Uses an LLM to interpret commands in the context of current drone
    positions, then applies APF safety filtering before returning waypoints.
    """

    _SYSTEM_PROMPT = """You are a drone controller. Output ONLY a JSON object, no other text.

The user gives you drone positions and a command. You must output new target positions.

IMPORTANT RULES:
- "fly to Xm" or "altitude Xm" means set z=X for all drones (use EXACT number from command)
- "rise Xm" or "up Xm" means add X to current z
- "descend Xm" or "down Xm" means subtract X from current z
- "land" means set z=0
- Keep x and y the same unless told to move horizontally

Output format (ONLY JSON, nothing else):
{
  "waypoints": {
    "<drone_id>": {"x": <float>, "y": <float>, "z": <float>}
  },
  "explanation": "<one sentence>"
}"""

    def __init__(
        self,
        backend:    str   = "mock",
        api_key:    Optional[str] = None,
        model:      Optional[str] = None,
        apf:        Optional[APFSafetyFilter] = None,
        ollama_url: str   = "http://localhost:11434",
        on_command: Optional[Callable[[CommandResult], None]] = None,
    ):
        self._backend    = backend.lower()
        self._api_key    = api_key or os.environ.get("DRONE_LLM_API_KEY", "")
        self._model      = model
        self._apf        = apf or APFSafetyFilter()
        self._ollama_url = ollama_url
        self._on_command = on_command
        self._state: Dict[str, Pose3D] = {}
        self._history: List[dict] = []
        self._client = None
        self._init_client()

    def _init_client(self):
        if self._backend == "gemini":
            try:
                import google.generativeai as genai
                genai.configure(api_key=self._api_key)
                self._model = self._model or "gemini-1.5-pro"
                self._client = genai.GenerativeModel(
                    self._model,
                    system_instruction=self._SYSTEM_PROMPT,
                )
            except ImportError:
                print("[swarm-commander] google-generativeai not installed. "
                      "pip install google-generativeai")
        elif self._backend == "openai":
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key)
                self._model  = self._model or "gpt-4o"
            except ImportError:
                print("[swarm-commander] openai not installed. pip install openai")
        elif self._backend == "ollama":
            self._model = self._model or "llama3"
        elif self._backend == "mock":
            self._client = "mock"

    def update_state(self, positions: Dict[str, Pose3D]):
        """Update current drone positions (call before command())."""
        self._state = dict(positions)

    def command(self, text: str) -> CommandResult:
        """
        Process a natural language command.
        Returns CommandResult with safe waypoints.
        """
        if not self._state:
            return CommandResult(
                success=False, waypoints={}, raw_waypoints={},
                explanation="", command=text,
                error="No drone positions registered. Call update_state() first."
            )
        t0 = time.monotonic()
        prompt = self._build_prompt(text)
        try:
            raw_json = self._call_llm(prompt)
            parsed   = self._parse_response(raw_json)
        except Exception as e:
            return CommandResult(
                success=False, waypoints={}, raw_waypoints={},
                explanation="", command=text, error=str(e),
                latency_ms=(time.monotonic()-t0)*1000,
            )

        raw_wp = parsed.get("waypoints", {})
        explanation = parsed.get("explanation", "")

        # Convert to Pose3D
        raw_poses: Dict[str, Pose3D] = {}
        for did, wp in raw_wp.items():
            if did in self._state:
                raw_poses[did] = Pose3D(
                    float(wp.get("x", self._state[did].x)),
                    float(wp.get("y", self._state[did].y)),
                    float(wp.get("z", self._state[did].z)),
                )

        # APF safety filter
        safe_poses = self._apf.filter(self._state, raw_poses)

        result = CommandResult(
            success=True,
            waypoints=safe_poses,
            raw_waypoints=raw_poses,
            explanation=explanation,
            command=text,
            latency_ms=(time.monotonic()-t0)*1000,
        )
        self._history.append({
            "t":       time.time(),
            "command": text,
            "result":  explanation,
        })
        if self._on_command:
            self._on_command(result)
        return result

    def history(self, last_n: int = 10) -> List[dict]:
        return self._history[-last_n:]

    # ── LLM backends ──────────────────────────────────────────────────────

    def _build_prompt(self, command: str) -> str:
        state_lines = "\n".join(
            f'  "{did}": {{"x": {p.x:.2f}, "y": {p.y:.2f}, "z": {p.z:.2f}}}'
            for did, p in self._state.items()
        )
        return (
            f"Current drone positions:\n{{\n{state_lines}\n}}\n\n"
            f"Command: {command}"
        )

    def _call_llm(self, prompt: str) -> str:
        if self._backend == "gemini":
            return self._call_gemini(prompt)
        elif self._backend == "openai":
            return self._call_openai(prompt)
        elif self._backend == "ollama":
            return self._call_ollama(prompt)
        elif self._backend == "mock":
            return self._call_mock(prompt)
        else:
            raise ConfigurationError(f"Unknown LLM backend: {self._backend!r}")

    def _call_gemini(self, prompt: str) -> str:
        resp = self._client.generate_content(prompt)
        return resp.text

    def _call_openai(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content

    def _call_ollama(self, prompt: str) -> str:
        import urllib.request
        body = json.dumps({
            "model":  self._model,
            "prompt": self._SYSTEM_PROMPT + "\n\n" + prompt,
            "stream": False,
            "format": "json",
        }).encode()
        req = urllib.request.Request(
            f"{self._ollama_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        return data.get("response", "{}")

    def _call_mock(self, prompt: str) -> str:
        """
        Deterministic mock — handles common formation commands
        without any API call. Good for offline testing.
        """
        cmd = prompt.lower()
        ids = list(self._state.keys())
        n   = len(ids)
        # Compute centroid
        cx = sum(p.x for p in self._state.values()) / max(n, 1)
        cy = sum(p.y for p in self._state.values()) / max(n, 1)
        cz = sum(p.z for p in self._state.values()) / max(n, 1)

        waypoints = {}

        if "circle" in cmd:
            r_match = re.search(r"(\d+(?:\.\d+)?)\s*m", cmd)
            radius  = float(r_match.group(1)) if r_match else 5.0
            for i, did in enumerate(ids):
                angle = 2 * math.pi * i / max(n, 1)
                waypoints[did] = {
                    "x": cx + radius * math.cos(angle),
                    "y": cy + radius * math.sin(angle),
                    "z": cz,
                }
            explanation = f"Circle formation, radius={radius}m, centered at ({cx:.1f},{cy:.1f})"

        elif "line" in cmd:
            s_match  = re.search(r"(\d+(?:\.\d+)?)\s*m", cmd)
            spacing  = float(s_match.group(1)) if s_match else 3.0
            for i, did in enumerate(ids):
                waypoints[did] = {
                    "x": cx + (i - (n-1)/2) * spacing,
                    "y": cy,
                    "z": cz,
                }
            explanation = f"Line formation, spacing={spacing}m"

        elif any(w in cmd for w in ["v formation", "v-formation", "wedge"]):
            spacing = 3.0
            for i, did in enumerate(ids):
                side = 1 if i % 2 == 0 else -1
                row  = (i + 1) // 2
                waypoints[did] = {
                    "x": cx - row * spacing * 0.8,
                    "y": cy + side * row * spacing * 0.6,
                    "z": cz,
                }
            explanation = "V formation"

        elif "land" in cmd:
            for did, p in self._state.items():
                waypoints[did] = {"x": p.x, "y": p.y, "z": 0.0}
            explanation = "Landing all drones"

        elif "hover" in cmd or "hold" in cmd:
            for did, p in self._state.items():
                waypoints[did] = {"x": p.x, "y": p.y, "z": p.z}
            explanation = "Holding position"

        elif "takeoff" in cmd or "take off" in cmd:
            for did, p in self._state.items():
                waypoints[did] = {"x": p.x, "y": p.y, "z": max(10.0, p.z + 10.0)}
            explanation = "Taking off to 10m altitude"

        elif "fly to" in cmd or "go to" in cmd or "altitude" in cmd:
            # Extract altitude number
            alt_match = re.search(r"(\d+(?:\.\d+)?)\s*m", cmd)
            altitude = float(alt_match.group(1)) if alt_match else 50.0
            for did, p in self._state.items():
                waypoints[did] = {"x": p.x, "y": p.y, "z": altitude}
            explanation = f"Flying to {altitude}m altitude"

        elif "rise" in cmd or "climb" in cmd or "up" in cmd:
            alt_match = re.search(r"(\d+(?:\.\d+)?)\s*m", cmd)
            amount = float(alt_match.group(1)) if alt_match else 10.0
            for did, p in self._state.items():
                waypoints[did] = {"x": p.x, "y": p.y, "z": p.z + amount}
            explanation = f"Rising {amount}m"

        elif "descend" in cmd or "down" in cmd:
            alt_match = re.search(r"(\d+(?:\.\d+)?)\s*m", cmd)
            amount = float(alt_match.group(1)) if alt_match else 10.0
            for did, p in self._state.items():
                waypoints[did] = {"x": p.x, "y": p.y, "z": max(0, p.z - amount)}
            explanation = f"Descending {amount}m"

        elif "north" in cmd:
            d_match = re.search(r"(\d+(?:\.\d+)?)\s*m", cmd)
            dist = float(d_match.group(1)) if d_match else 5.0
            for did, p in self._state.items():
                waypoints[did] = {"x": p.x + dist, "y": p.y, "z": p.z}
            explanation = f"Moving {dist}m north"

        elif "south" in cmd:
            d_match = re.search(r"(\d+(?:\.\d+)?)\s*m", cmd)
            dist = float(d_match.group(1)) if d_match else 5.0
            for did, p in self._state.items():
                waypoints[did] = {"x": p.x - dist, "y": p.y, "z": p.z}
            explanation = f"Moving {dist}m south"

        elif "up" in cmd or "climb" in cmd:
            d_match = re.search(r"(\d+(?:\.\d+)?)\s*m", cmd)
            dist = float(d_match.group(1)) if d_match else 5.0
            for did, p in self._state.items():
                waypoints[did] = {"x": p.x, "y": p.y, "z": p.z + dist}
            explanation = f"Climbing {dist}m"

        elif "grid" in cmd:
            cols = math.ceil(math.sqrt(n))
            spacing = 3.0
            for i, did in enumerate(ids):
                row = i // cols
                col = i %  cols
                waypoints[did] = {
                    "x": cx + (row - cols/2) * spacing,
                    "y": cy + (col - cols/2) * spacing,
                    "z": cz,
                }
            explanation = f"Grid formation {cols}x{math.ceil(n/cols)}"

        else:
            for did, p in self._state.items():
                waypoints[did] = {"x": p.x, "y": p.y, "z": p.z}
            explanation = f"Command not recognized: '{cmd}' — holding position"

        return json.dumps({"waypoints": waypoints, "explanation": explanation})

    def _parse_response(self, text: str) -> dict:
        # Strip markdown code fences if present
        text = re.sub(r"```(?:json)?", "", text).strip()
        # Find JSON object
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise LLMResponseError(
                f"No JSON found in LLM response: {text[:200]}",
                raw_response=text,
            )
        return json.loads(match.group(0))
