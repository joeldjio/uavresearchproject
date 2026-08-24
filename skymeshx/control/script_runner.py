"""
ScriptRunner — executes Python scripts with full drone API access.

Scripts get a pre-injected 'drone' object and can use the full SDK.

Usage:
    runner = ScriptRunner(drone)
    runner.run_file("examples/hover.py")
    runner.run_string("drone.takeoff(10); drone.wait(5); drone.land()")

Script environment:
    drone   — Drone instance
    swarm   — Swarm instance (if available)
    log     — logger function
    sleep   — time.sleep
    math    — math module
"""

import io
import math

from skymeshx.exceptions import ScriptAbortedError
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Callable, Optional


class ScriptRunner:
    def __init__(self, drone, swarm=None):
        self._drone = drone
        self._swarm = swarm
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False
        self._output_cb: Optional[Callable[[str], None]] = None
        self._error_cb: Optional[Callable[[str], None]] = None

    def on_output(self, cb: Callable[[str], None]):
        self._output_cb = cb

    def on_error(self, cb: Callable[[str], None]):
        self._error_cb = cb

    def run_file(self, path: str, blocking: bool = False):
        code = Path(path).read_text(encoding="utf-8")
        self.run_string(code, blocking=blocking, filename=path)

    def run_string(
        self,
        code: str,
        blocking: bool = False,
        filename: str = "<script>",
        use_subprocess: bool = False,
    ):
        if self._running:
            self._emit_error("Script already running. Stop it first.")
            return
        self._stop.clear()
        self._running = True
        if use_subprocess:
            self._thread = threading.Thread(
                target=self._exec_subprocess,
                args=(code, filename),
                daemon=True,
                name="script-runner-sub",
            )
        else:
            self._thread = threading.Thread(
                target=self._exec,
                args=(code, filename),
                daemon=True,
                name="script-runner",
            )
        self._thread.start()
        if blocking:
            self._thread.join()

    def stop(self):
        self._stop.set()

    @property
    def running(self) -> bool:
        return self._running

    def _exec_subprocess(self, code: str, filename: str):
        """Run script in a separate Python process for isolation.

        The subprocess does NOT have access to the live drone object — it
        receives connection_string and reconnects. Suitable for untrusted scripts.
        """
        import os
        import subprocess
        import sys
        import tempfile

        # Write code to a temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tf:
            # Inject connection string if drone has one
            conn_str = getattr(
                getattr(self._drone, "_conn", None),
                "connection_string",
                None,
            )
            header = ""
            if conn_str:
                header = (
                    "from skymeshx import Drone as _Drone\n"
                    f"drone = _Drone({conn_str!r})\n"
                    "drone.connect()\n"
                )
            tf.write(header + code)
            tmp_path = tf.name

        try:
            proc = subprocess.Popen(
                [sys.executable, tmp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            # Stream output
            for line in proc.stdout:
                if self._stop.is_set():
                    proc.terminate()
                    break
                self._emit_output(line.rstrip())
            proc.wait(timeout=5)
            if proc.returncode not in (0, None):
                self._emit_error(f"[script] exited with code {proc.returncode}")
        except Exception:
            import traceback

            self._emit_error(traceback.format_exc())
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            self._running = False
            self._emit_output("[script] done.")

    def _exec(self, code: str, filename: str):
        buf = io.StringIO()
        env = {
            "drone": self._drone,
            "swarm": self._swarm,
            "log": self._emit_output,
            "sleep": self._interruptible_sleep,
            "math": math,
            "time": time,
            "__name__": "__skymeshx_script__",
            "__file__": filename,
        }
        old_stdout = sys.stdout
        sys.stdout = _CallbackWriter(self._emit_output)
        try:
            compiled = compile(code, filename, "exec")
            exec(compiled, env)
        except Exception:
            tb = traceback.format_exc()
            self._emit_error(tb)
        finally:
            sys.stdout = old_stdout
            self._running = False
            self._emit_output("[script] done.")

    def _interruptible_sleep(self, seconds: float):
        end = time.time() + seconds
        while time.time() < end:
            if self._stop.is_set():
                raise ScriptAbortedError("Script stopped by user")
            time.sleep(0.05)

    def _emit_output(self, text: str):
        if self._output_cb:
            self._output_cb(str(text))

    def _emit_error(self, text: str):
        if self._error_cb:
            self._error_cb(str(text))
        else:
            print(f"[script error] {text}", file=sys.stderr)


class _CallbackWriter:
    def __init__(self, cb):
        self._cb = cb

    def write(self, text: str):
        if text.strip():
            self._cb(text)

    def flush(self):
        pass
