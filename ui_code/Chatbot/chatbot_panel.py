# ui_code/Chatbot/chatbot_panel.py
# Chat adapter + ChatbotPanel (Omniverse UI) with SSE alert stream.
# Exports: ChatAdapter, ChatbotPanel

import os
import json
import time
import threading
from typing import Optional
import requests

import omni.ui as ui
import omni.kit.app as kit_app

from ui_code.ui.utils.common import _fill

ALERTS_SHOW_SYS = os.getenv("ALERTS_SHOW_SYS", "0") == "1"  # 1 → show [SSE] logs

# ASCII-only separators to avoid missing glyphs
SEP = " | "

# Tag mapping for “alarm-like” lines
ALERT_TAGS = {
    "battery_low":    "LOW",
    "status_offline": "OFFLINE",
    "status_fault":   "FAULT",
    "job_warn":       "WARN",
}


# ───────────────────── Chat Adapter ─────────────────────
class ChatAdapter:
    """Adapter for Django chatbot APIs (chat + health)."""
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or
                         os.environ.get("DJANGO_CHAT_URL",
                                        "http://127.0.0.1:8000/chatbot/api/chat")).rstrip("/")
        self.health_url = self.base_url.replace("/api/chat", "/api/llm/health")

    def send(self, prompt: str, timeout: int = 180) -> str:
        try:
            r = requests.post(self.base_url, json={"prompt": prompt}, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                return data.get("text") or data.get("answer") or "WARNING: Empty response."
            return f"HTTP {r.status_code}: {r.text[:300]}"
        except Exception as e:
            return f"Request failed: {e}"

    def warmup(self):
        try:
            requests.get(self.health_url, timeout=10)
        except Exception:
            pass


# ───────────────────── Chatbot Panel (+ Alerts via SSE) ─────────────────────
class ChatbotPanel:
    def __init__(self, adapter: Optional[ChatAdapter] = None, title: str = "ChatBot"):
        self._adapter = adapter or ChatAdapter()
        self._title = title

        # UI models
        self._win = None
        self._in_model = ui.SimpleStringModel("")
        self._out_model = ui.SimpleStringModel("")
        self._alerts_model = ui.SimpleStringModel("")

        # SSE
        self._alerts_url = (os.environ.get("DJANGO_ALERTS_URL")
                            or self._adapter.base_url.replace("/api/chat", "/alerts/stream"))
        self._alive = False
        self._alerts_thr: Optional[threading.Thread] = None

    # ─────────── UI ───────────
    def show(self):
        if self._win is None:
            self._win = ui.Window(self._title, width=560, height=460,
                                  flags=ui.WINDOW_FLAGS_NO_SCROLLBAR)
            with self._win.frame:
                with ui.VStack(spacing=8, padding=10, width=_fill(), height=_fill()):
                    ui.Label("Prompt")
                    ui.StringField(model=self._in_model, multiline=True, height=120)

                    with ui.HStack(spacing=8):
                        ui.Button("Send", height=28, clicked_fn=self._on_send)
                        ui.Button("Clear", height=28,
                                  clicked_fn=lambda: self._in_model.set_value(""))
                        ui.Spacer(width=8)
                        ui.Button("Reconnect Alerts", height=28, clicked_fn=self._restart_alerts)

                    ui.Label("Response")
                    ui.StringField(model=self._out_model, multiline=True, read_only=True, height=120)

                    ui.Separator()
                    ui.Label("Alerts (Live)")
                    ui.StringField(model=self._alerts_model, multiline=True, read_only=True, height=120)

        self._win.visible = True
        self._win.focus()

        threading.Thread(target=self._adapter.warmup, daemon=True).start()
        self._start_alerts()

    # ─────────── Chat actions ───────────
    def _on_send(self):
        text = (self._in_model.as_string or "").strip()
        if not text:
            self._out_model.set_value("WARNING: Input is empty.")
            return
        self._out_model.set_value("Generating...")
        ans = self._adapter.send(text)
        self._out_model.set_value(ans)

    # ─────────── Alerts (SSE) ───────────
    def _start_alerts(self):
        if self._alerts_thr and self._alerts_thr.is_alive():
            return
        self._alive = True
        self._alerts_thr = threading.Thread(target=self._listen_alerts, daemon=True)
        self._alerts_thr.start()

    def _restart_alerts(self):
        self._stop_alerts()
        def _delay_start():
            time.sleep(0.4)
            self._start_alerts()
        threading.Thread(target=_delay_start, daemon=True).start()

    def _stop_alerts(self):
        self._alive = False

    def _listen_alerts(self):
        """SSE client with reconnect + backoff."""
        backoff = 1.0
        self._sys_note(f"connecting to {self._alerts_url}")
        while self._alive:
            try:
                # connect timeout 5s, read timeout 70s (server heartbeats keep it alive)
                with requests.get(self._alerts_url, stream=True, timeout=(5, 70)) as r:
                    if r.status_code != 200:
                        self._sys_note(f"HTTP {r.status_code}: {self._alerts_url}")
                        time.sleep(backoff)
                        backoff = min(backoff * 2.0, 15.0)
                        continue

                    self._sys_note("connected")
                    backoff = 1.0

                    event_name = "message"
                    data_buf = []

                    for raw in r.iter_lines(decode_unicode=True):
                        if not self._alive:
                            break
                        if raw is None:
                            continue
                        line = raw.strip()

                        if line == "":
                            if data_buf:
                                payload = "\n".join(data_buf)
                                self._handle_sse_event(event_name, payload)
                            event_name = "message"
                            data_buf = []
                            continue

                        if line.startswith("event: "):
                            event_name = line[7:].strip() or "message"
                            continue

                        if line.startswith("data: "):
                            data_buf.append(line[6:])
                            continue
                        # ":" lines (e.g., :ping) are comments → ignore
            except Exception as e:
                if not self._alive:
                    break
                self._sys_note(f"reconnect: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 15.0)

    # ─────────── Formatting & UI append ───────────
    def _handle_sse_event(self, event_name: str, payload: str):
        try:
            obj = json.loads(payload)
        except Exception:
            self._push_chat_line(f"[INFO]{SEP}{self._now_hms()}{SEP}{event_name}{SEP}{payload}")
            return

        label_map = {
            "battery_low":    "Battery Low",
            "status_offline": "Offline",
            "status_fault":   "Fault",
            "job_warn":       "Job Warning",
        }
        label = label_map.get(event_name, event_name)
        tag = ALERT_TAGS.get(event_name, "INFO")

        rid = obj.get("robotId") or "-"
        msg = obj.get("message") or ""
        t_local = self._format_local_time(obj.get("ts"))

        # ASCII-only, “alarm-like” line
        # [TAG] HH:MM:SS | AMR 152 | Offline | status=2 (offline)
        line = f"[{tag}]{SEP}{t_local}{SEP}AMR {rid}{SEP}{label}{SEP}{msg}"
        self._push_chat_line(line)

    def _push_chat_line(self, line: str):
        """Prepend a chat-like alert line. Safe on Kit main thread via next_update."""
        app = kit_app.get_app()
        def _do():
            old = self._alerts_model.as_string or ""
            self._alerts_model.set_value((line + "\n") + old)  # prepend
        try:
            app.next_update.add_task(_do)  # Kit 105+ safe
        except Exception:
            try:
                _do()
            except Exception:
                pass

    def _sys_note(self, text: str):
        if not ALERTS_SHOW_SYS:
            return
        self._push_chat_line(f"[SSE]{SEP}{text}")

    @staticmethod
    def _format_local_time(ts: Optional[str]) -> str:
        if not ts:
            return "now"
        try:
            t = ts.replace("Z", "+00:00")  # ISO Z → +00:00
            from datetime import datetime
            dt = datetime.fromisoformat(t)
            if dt.tzinfo is not None:
                dt = dt.astimezone()
            return dt.strftime("%H:%M:%S")
        except Exception:
            return ts

    @staticmethod
    def _now_hms() -> str:
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")


__all__ = ["ChatAdapter", "ChatbotPanel"]
