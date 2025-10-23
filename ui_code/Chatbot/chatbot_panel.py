# ui_code/Chatbot/chatbot_panel.py
import os, io, ssl, json, base64, threading, urllib.request, urllib.error
from collections import deque
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple

import omni.kit.app as kit_app
import omni.ui as ui

# ──────────────────────────────────────────────────────────────
# Unity 매핑 개요
#  - ChatbotButton.ShowChatbotPanel  → ChatbotPanel.show() (토글)
#  - ChatButtonSystem (Text/STT 토글) → input on_change 로 버튼 가시성 전환
#  - ChatSender (POST /chat, [image] 처리, 모드) → HttpChatAdapter + Panel 로직
#  - ClearManager (UI 비우고 /clear) → clear_history(send_server=True)
#  - ChatSaver (HTML 저장) → save_to_html(path)
#  - ImageViewer (확대) → 별도 윈도우로 원본 크기 제한 표시
# ──────────────────────────────────────────────────────────────

# 색상 (0xAARRGGBB)
COL_BG_WIN  = 0xF0151515
COL_BG_USER = 0xFF2D6CDF
COL_TXT_USR = 0xFFFFFFFF
COL_BG_BOT  = 0xFF2A2A2A
COL_TXT_BOT = 0xFFEFEFEF

# 모드 드롭다운 항목 (Unity TextDropdownSelector 매핑)
CHAT_MODES = ["(None)", "SQL Query", "Function Call", "RAG Response"]

@dataclass
class Msg:
    role: str          # "user" | "bot"
    kind: str          # "text" | "image"
    text: str = ""     # 텍스트
    image_name: str = ""   # 파일명(서버에서 받은)
    image_path: str = ""   # 디스크 저장 경로
    image_bytes: bytes = b""  # HTML 저장용

class ChatAdapter:
    """개발용(에코)"""
    def send(self, url: str, payload: Dict[str, Any], *, verify_ssl: bool = True) -> Dict[str, Any]:
        # Unity: Debug echo
        msg = str(payload.get("message", ""))
        return {"message": f"echo: {msg}"}

class HttpChatAdapter(ChatAdapter):
    """Unity의 UnityWebRequest POST를 urllib로 구현. 인증서 무시는 verify_ssl=False."""
    def send(self, url: str, payload: Dict[str, Any], *, verify_ssl: bool = True) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        ctx = None if verify_ssl else ssl._create_unverified_context()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as res:
                raw = res.read().decode("utf-8", errors="replace")
                try:
                    return json.loads(raw)
                except Exception:
                    return {"message": raw}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            return {"message": f"[HTTP {e.code}] {body}"}
        except Exception as e:
            return {"message": f"[HTTP error] {e}"}

class ChatbotPanel:
    def __init__(self, *, adapter: Optional[ChatAdapter] = None, title: str = "ChatBot"):
        self._adapter = adapter or ChatAdapter()
        self._title   = title

        # 서버 설정 (Unity와 동일 개념)
        self._server_ip = "127.0.0.1"
        self._port      = 8000
        self._https     = True         # Unity는 https 기본
        self._verify_ssl = False       # Unity BypassCertificate와 동일(개발용)
        # 엔드포인트
        self._chat_path  = "/chat"
        self._static_path = "/static/"
        self._clear_path = "/clear"

        # 상태
        self._win: Optional[ui.Window] = None
        self._history: List[Msg] = []
        self._mode_index = 0
        self._jobs: deque = deque()
        self._tick_sub = None

        # UI 모델
        self._input_model = ui.SimpleStringModel("")
        self._save_path_model = ui.SimpleStringModel(self._default_save_path())

        # 버튼 가시성 제어용
        self._btn_send: Optional[ui.Button] = None
        self._btn_stt: Optional[ui.Button]  = None

        # 동적 빌드
        self._history_frame: Optional[ui.Frame] = None

        self._build_window()
        self._bind_events()

    # ───────────────────────── Config ─────────────────────────
    def set_server(self, ip: str, port: int, https: bool = True, verify_ssl: bool = False):
        self._server_ip = ip
        self._port = int(port)
        self._https = bool(https)
        self._verify_ssl = bool(verify_ssl)

    # ───────────────────────── UI Build ───────────────────────
    def _build_window(self):
        self._win = ui.Window(self._title, width=600, height=400, dockPreference=ui.DockPreference.RIGHT)
        with self._win.frame:
            with ui.ZStack():
                ui.Rectangle(style={"background_color": COL_BG_WIN})
                with ui.VStack(spacing=8, padding=10):
                    # 상단: 모드 + 서버표시 + Clear/Save
                    with ui.HStack(spacing=8, height=28):
                        ui.Label("Mode:", width=ui.Pixel(40), style={"color": 0xFFCCCCCC})
                        ui.ComboBox(self._mode_index, *CHAT_MODES, changed_fn=self._on_mode_changed)
                        ui.Spacer()
                        # 저장 경로(간단 표시/수정 가능)
                        ui.StringField(self._save_path_model, width=ui.Percent(45))
                        ui.Button("Save", width=60, clicked_fn=self._on_save_clicked)
                        ui.Button("Clear", width=60, clicked_fn=lambda: self.clear_history(send_server=True))

                    # 히스토리 (동적 프레임)
                    self._history_frame = ui.Frame(height=ui.Fraction(1), build_fn=self._build_history)

                    # 입력/전송 영역 (Text/STT 토글)
                    with ui.HStack(spacing=8, height=32):
                        # 입력
                        ui.StringField(self._input_model, height=0,
                                       on_return_pressed_fn=self._on_send_clicked,
                                       changed_fn=self._on_input_changed)

                        # STT / Send 버튼 (가시성 토글)
                        self._btn_stt  = ui.Button("STT",  width=60, clicked_fn=self._on_stt_clicked)
                        self._btn_send = ui.Button("Send", width=60, clicked_fn=self._on_send_clicked)

                        # 초기 가시성 업데이트
                        self._update_text_stt_visibility()

        # 프레임 업데이트 큐 구독
        app = kit_app.get_app()
        self._tick_sub = app.get_update_event_stream().create_subscription_to_pop(self._drain_jobs,
                                                                                  name="chatbot-ui-jobs")

    def _bind_events(self):  # placeholder (필요시 확장)
        pass

    # 동적 빌드 함수: history → 버블 렌더링
    def _build_history(self):
        with ui.ScrollingFrame():
            with ui.VStack(spacing=6, padding=4):
                for m in self._history:
                    if m.kind == "text":
                        self._build_text_bubble(m.text, is_user=(m.role == "user"))
                    elif m.kind == "image":
                        self._build_image_bubble(m, is_user=False)

    # ───────────────────────── Helpers ────────────────────────
    def _default_save_path(self) -> str:
        # Unity의 Application.persistentDataPath 대체
        root = os.path.join(os.path.expanduser("~"), "Documents", "Omniverse")
        os.makedirs(root, exist_ok=True)
        return os.path.join(root, "ChatLog.html")

    def _base_url(self) -> str:
        scheme = "https" if self._https else "http"
        return f"{scheme}://{self._server_ip}:{self._port}"

    def _chat_url(self) -> str:
        return self._base_url() + self._chat_path

    def _static_url(self, filename: str) -> str:
        return self._base_url() + self._static_path + filename

    def _clear_url(self) -> str:
        return self._base_url() + self._clear_path

    def _post(self, fn, *args, **kwargs):
        self._jobs.append((fn, args, kwargs))

    def _drain_jobs(self, _e):
        while self._jobs:
            fn, args, kwargs = self._jobs.popleft()
            try:
                fn(*args, **kwargs)
            except Exception as ex:
                print("[ChatbotPanel] UI job failed:", ex)

    def _update_text_stt_visibility(self):
        text = (self._input_model.as_string or "").strip()
        has_text = len(text) > 0
        if self._btn_send: self._btn_send.visible = has_text
        if self._btn_stt:  self._btn_stt.visible  = not has_text

    # ───────────────────────── Bubbles ────────────────────────
    def _build_text_bubble(self, text: str, *, is_user: bool):
        with ui.HStack(spacing=8):
            if is_user:
                ui.Spacer()
            with ui.VStack(width=ui.Percent(75)):
                with ui.Frame(style={
                    "background_color": (COL_BG_USER if is_user else COL_BG_BOT),
                    "border_radius": 8, "padding": 8
                }):
                    ui.Label(text, word_wrap=True,
                             style={"color": (COL_TXT_USR if is_user else COL_TXT_BOT)})
            if not is_user:
                ui.Spacer()

    def _build_image_bubble(self, m: Msg, *, is_user: bool):
        # 이미지도 봇 말풍선으로 처리
        with ui.HStack(spacing=8):
            if is_user:
                ui.Spacer()
            with ui.VStack(width=ui.Percent(75)):
                # 버튼으로 감싸 클릭 확대
                with ui.Button("", height=0, style={"background_color": 0x00000000}):
                    # ui.Image는 파일 경로 필요 → 캐시 파일 저장 경로 사용
                    if os.path.isfile(m.image_path):
                        ui.Image(m.image_path)
                    else:
                        ui.Label(f"(image missing) {m.image_name}", style={"color": 0xFFCCCCCC})

                # 클릭 콜백
                def _open():
                    self._open_image_viewer(m)
                ui.Spacer(height=1)  # 클릭 영역 분리 위해
                # 위 Button이 클릭을 받지만, 안전을 위해 라벨에도 버튼 하나 더 추가할 수 있음
            if not is_user:
                ui.Spacer()

    def _open_image_viewer(self, m: Msg):
        # Unity ImageViewer와 동일: 800x400 제한
        w = ui.Window(f"Image: {m.image_name}", width=840, height=480)
        with w.frame:
            with ui.VStack(spacing=6, padding=8):
                ui.Label(f"{m.image_name}", style={"color": 0xFFCCCCCC})
                if os.path.isfile(m.image_path):
                    ui.Image(m.image_path)
                else:
                    ui.Label("(file not found)")

    # ───────────────────────── Actions ────────────────────────
    def show(self, *, amr_id: Optional[str] = None):
        # Unity: 첫 클릭 시 생성을 했지만, 여기선 윈도우가 항상 있으니 토글로 동작
        if not self._win:
            self._build_window()
        self._win.visible = not self._win.visible if self._win.visible is not None else True
        if amr_id:
            self._history.append(Msg(role="bot", kind="text", text=f"선택된 AMR: {amr_id}"))
            self._history_frame.rebuild()

    def set_adapter(self, adapter: ChatAdapter):
        self._adapter = adapter

    def _on_mode_changed(self, idx: int):
        self._mode_index = int(idx)

    def _on_input_changed(self, *_):
        self._update_text_stt_visibility()

    def _on_stt_clicked(self, *_):
        # Unity: "STT 버튼 클릭됨" 로그 → 여기서는 안내 메시지
        self._history.append(Msg(role="bot", kind="text", text="(STT) 음성 인식 준비…"))
        self._history_frame.rebuild()

    def _on_send_clicked(self, *_):
        text = (self._input_model.as_string or "").strip()
        if not text:
            return
        self._input_model.as_string = ""
        self._update_text_stt_visibility()

        # 사용자 말풍선
        self._history.append(Msg(role="user", kind="text", text=text))
        self._history_frame.rebuild()

        # 백엔드 호출
        threading.Thread(target=self._send_worker, args=(text,), daemon=True).start()

    def _payload_for_mode(self, message: str) -> Dict[str, Any]:
        # Unity ChatSender: 선택된 모드에 따라 "mode" 필드 추가
        if self._mode_index <= 0:
            return {"message": message}
        else:
            return {"message": message, "mode": CHAT_MODES[self._mode_index]}

    def _send_worker(self, message: str):
        url = self._chat_url()
        payload = self._payload_for_mode(message)
        res = self._adapter.send(url, payload, verify_ssl=self._verify_ssl)

        reply = str(res.get("message") or "")
        if reply.startswith("[image]"):
            filename = reply.replace("[image]", "").strip()
            img_msg = self._download_image(filename)
            if img_msg:
                self._history.append(img_msg)
        else:
            self._history.append(Msg(role="bot", kind="text", text=reply))

        self._post(self._history_frame.rebuild)

    # Unity: LoadAndDisplayImage (서버에서 이미지 내려받아 표시)
    def _download_image(self, filename: str) -> Optional[Msg]:
        url = self._static_url(filename)
        ctx = None if self._verify_ssl else ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(url, timeout=30, context=ctx) as res:
                data = res.read()
        except Exception as e:
            return Msg(role="bot", kind="text", text=f"(이미지 다운로드 실패) {e}")

        # 캐시 파일로 저장 (ui.Image는 파일 경로 필요)
        cache_root = os.path.join(os.path.expanduser("~"), "Documents", "Omniverse", "ChatbotCache")
        os.makedirs(cache_root, exist_ok=True)
        safe_name = filename.replace("/", "_").replace("\\", "_")
        file_path = os.path.join(cache_root, safe_name)
        try:
            with open(file_path, "wb") as f:
                f.write(data)
        except Exception as e:
            return Msg(role="bot", kind="text", text=f"(이미지 저장 실패) {e}")

        return Msg(role="bot", kind="image", image_name=filename, image_path=file_path, image_bytes=data)

    # Unity: ClearManager (UI 비우고 서버 clear)
    def clear_history(self, *, send_server: bool = False):
        self._history.clear()
        self._history_frame.rebuild()
        if send_server:
            threading.Thread(target=self._send_clear_request, daemon=True).start()

    def _send_clear_request(self):
        url = self._clear_url()
        ctx = None if self._verify_ssl else ssl._create_unverified_context()
        # Unity는 PostWwwForm "" → 여기서는 간단 POST
        data = b"{}"
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx) as res:
                _ = res.read()
        except Exception as e:
            self._post(self._history.append, Msg(role="bot", kind="text", text=f"(clear 실패) {e}"))
            self._post(self._history_frame.rebuild)

    # Unity: ChatSaver
    def save_to_html(self, path: Optional[str] = None):
        path = path or self._default_save_path()
        html = io.StringIO()
        html.write("<!DOCTYPE html><html><head><meta charset='utf-8'>")
        html.write("<style>.user{color:blue;font-weight:bold;margin-bottom:10px}")
        html.write(".bot{color:black;margin-bottom:30px}img{max-width:800px;max-height:400px;margin-bottom:30px}</style></head><body>")
        for m in self._history:
            if m.kind == "text":
                cls = "user" if m.role == "user" else "bot"
                prefix = "질문: " if m.role == "user" else "답변:<br>"
                safe = (m.text or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br>")
                html.write(f"<div class='{cls}'>{prefix}{safe}</div>\n")
            elif m.kind == "image":
                b64 = base64.b64encode(m.image_bytes or b"").decode("ascii") if m.image_bytes else ""
                if b64:
                    html.write(f"<img src='data:image/png;base64,{b64}' />\n")
                else:
                    html.write(f"<div class='bot'>(이미지 없음) {m.image_name}</div>\n")
        html.write("</body></html>")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html.getvalue())

    def _on_save_clicked(self, *_):
        try:
            self.save_to_html(self._save_path_model.as_string or self._default_save_path())
            self._history.append(Msg(role="bot", kind="text", text=f"저장 완료: {self._save_path_model.as_string}"))
        except Exception as e:
            self._history.append(Msg(role="bot", kind="text", text=f"(저장 실패) {e}"))
        self._history_frame.rebuild()
