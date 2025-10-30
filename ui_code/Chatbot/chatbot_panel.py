import os
import json
import time
import threading
import requests
import omni.ui as ui
import omni.kit.app as kit_app
from ui_code.ui.utils.common import _fill


# ───────────────────── Chat Adapter ─────────────────────
class ChatAdapter:
    """Adapter for Django chatbot APIs (chat + health)."""
    def __init__(self, base_url: str | None = None):
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
            else:
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
    def __init__(self, adapter: ChatAdapter | None = None, title: str = "ChatBot"):
        self._adapter = adapter or ChatAdapter()
        self._title = title

        # UI
        self._win = None
        self._in_model = ui.SimpleStringModel("")
        self._out_model = ui.SimpleStringModel("")
        self._alerts_model = ui.SimpleStringModel("")

        # SSE
        self._alerts_url = (os.environ.get("DJANGO_ALERTS_URL")
                            or self._adapter.base_url.replace("/api/chat", "/alerts/stream"))
        self._alive = False
        self._alerts_thr: threading.Thread | None = None

    # ─────────── UI ───────────
    def show(self):
        if self._win is None:
            self._win = ui.Window(self._title, width=560, height=460,
                                  flags=ui.WINDOW_FLAGS_NO_SCROLLBAR)
            with self._win.frame:
                with ui.VStack(spacing=8, padding=10, width=_fill(), height=_fill()):
                    ui.Label("Prompt", style={"color": 0xFFFFFFFF})
                    ui.StringField(model=self._in_model, multiline=True, height=120,
                                   style={"color": 0xFFFFFFFF})

                    with ui.HStack(spacing=8):
                        ui.Button("Send", height=28, clicked_fn=self._on_send)
                        ui.Button("Clear", height=28,
                                  clicked_fn=lambda: self._in_model.set_value(""))
                        ui.Spacer(width=8)
                        ui.Button("Reconnect Alerts", height=28, clicked_fn=self._restart_alerts)

                    ui.Label("Response", style={"color": 0xFFFFFFFF})
                    ui.StringField(model=self._out_model, multiline=True, read_only=True,
                                   height=120, style={"color": 0xFFFFFFFF})

                    ui.Separator()
                    ui.Label("Alerts (Live: battery/status/job)", style={"color": 0xFFFFFFFF})
                    ui.StringField(model=self._alerts_model, multiline=True, read_only=True,
                                   height=120, style={"color": 0xFFFFFFFF})

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
        self._append_alert_line(f"[SSE] connecting to {self._alerts_url}")
        while self._alive:
            try:
                # connect timeout 5s, read timeout 70s (주기적 핑으로 갱신)
                with requests.get(self._alerts_url, stream=True, timeout=(5, 70)) as r:
                    if r.status_code != 200:
                        self._append_alert_line(f"[SSE] HTTP {r.status_code}: {self._alerts_url}")
                        time.sleep(backoff)
                        backoff = min(backoff * 2.0, 15.0)
                        continue

                    self._append_alert_line("[SSE] connected")
                    backoff = 1.0  # reset on success

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
                        # ':' ping 등은 무시
            except Exception as e:
                if not self._alive:
                    break
                self._append_alert_line(f"[SSE] reconnect due to error: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2.0, 15.0)

    def _handle_sse_event(self, event_name: str, payload: str):
        try:
            obj = json.loads(payload)
        except Exception:
            self._append_alert_line(f"[{event_name}] {payload}")
            return

        title = obj.get("title") or event_name
        msg = obj.get("message") or ""
        rid = obj.get("robotId")
        ts = obj.get("ts") or ""
        line = f"[{event_name}] {title} — {msg}" + (f" (AMR {rid})" if rid else "") + (f" @ {ts}" if ts else "")
        self._append_alert_line(line)

    def _append_alert_line(self, line: str):
        """UI 업데이트는 메인 쓰레드에서: post_update 사용"""
        app = kit_app.get_app()
        def _do():
            old = self._alerts_model.as_string or ""
            self._alerts_model.set_value((line + "\n") + old)
        app.post_update(_do)

    # ─────────── lifecycle (옵션) ───────────
    def destroy(self):
        self._stop_alerts()
