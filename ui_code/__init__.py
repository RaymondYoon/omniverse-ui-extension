# __init__.py — IExt + 네트워크/모델 업데이트 (UI 메서드 호출만)
import os
import json
import threading
import urllib.request
import urllib.error

import carb
import omni.ext
import omni.kit.app as kit_app
import omni.usd
from omni.usd import StageEventType

from .client import DigitalTwinClient
from .main import UiLayoutBase

SETTING_KEY = "/ext/platform_ui/operate_mode"
# 다양한 버전 호환(일부는 /app/*, 일부는 /persistent/*만 반영됨)
VIEWPORT_KEY_APP = "/app/viewport/manipulator/showTransformManipulator"
VIEWPORT_KEY_PERSIST = "/persistent/app/viewport/manipulator/showTransformManipulator"


# ────────────────────── 가벼운 HTTP 핑어 ──────────────────────
class HttpPinger:
    def __init__(
        self,
        url: str,
        interval: float = 2.0,
        timeout: float = 1.5,
        on_change=None,
        treat_http_error_as_alive: bool = True,  # 4xx/5xx도 alive 처리 옵션
    ):
        self.url = url
        self.interval = interval
        self.timeout = timeout
        self.on_change = on_change
        self.treat_http_error_as_alive = treat_http_error_as_alive
        self._stop = threading.Event()
        self._thread = None
        self._last = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            alive = False
            try:
                req = urllib.request.Request(self.url, method="HEAD")
                with urllib.request.urlopen(req, timeout=self.timeout):
                    alive = True
            except urllib.error.HTTPError as e:
                alive = True if self.treat_http_error_as_alive else (200 <= e.code < 400)
            except Exception:
                alive = False

            if alive != self._last:
                self._last = alive
                if self.on_change:
                    try:
                        self.on_change(alive)
                    except Exception:
                        pass

            self._stop.wait(self.interval)


class PlatformUiExtension(UiLayoutBase, omni.ext.IExt):
    # ───────────────────────── lifecycle ───────────────────────
    def on_startup(self, ext_id):
        # 선택 이벤트 구독 핸들
        self._sel_sub = None

        # 1) UI 먼저 올림
        UiLayoutBase.on_startup(self, ext_id)

        # UI가 뜨자마자 플레이스홀더 카드로 AMR 패널을 '보이게'
        self._show_placeholder_amr_cards(4)

        print("[Platform.ui.__init__] logic startup")

        # 2) 앱/클라이언트/콜백 설정
        self._app = kit_app.get_app()

        base_url = self._load_base_url_from_network()
        print(f"[Platform.ui] base_url = {base_url}")

        self._client = DigitalTwinClient(base_url=base_url, interval=0.5, timeout=5.0)
        self._client.add_on_alive_change(self._on_alive_change)
        self._client.add_on_response(self._on_response)
        self._client.add_on_error(self._on_error)
        self._client.add_on_response(self._on_client_response)
        self._client.start(map_code="RR_Floor")

        # 3) Fleet 서버 핑 시작
        fleet_url = "http://172.16.110.190:5000/"
        self._fleet_pinger = HttpPinger(
            url=fleet_url,
            interval=2.0,
            timeout=1.5,
            on_change=lambda alive: self._post_to_ui(
                self._set_status_dot, "Fleet Server", alive
            ),
        )
        self._fleet_pinger.start()
        print(f"[Platform.ui] Fleet pinger started → {fleet_url}")

    def on_shutdown(self):
        try:
            # 선택 이벤트 구독 해제
            if getattr(self, "_sel_sub", None):
                self._sel_sub = None
            if getattr(self, "_fleet_pinger", None):
                self._fleet_pinger.stop()
            if getattr(self, "_client", None):
                self._client.stop()
        finally:
            UiLayoutBase.on_shutdown(self)

    # ───────────────────── config loader ───────────────────────
    def _load_base_url_from_network(self) -> str:
        candidates = [
            os.path.join(os.path.dirname(__file__), "Network.json"),
            os.path.join(
                os.path.expanduser("~"), "Documents", "Omniverse", "Network.json"
            ),
        ]
        for p in candidates:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        net = json.load(f)
                    ip = net.get("opServerIP", "127.0.0.1")
                    port = str(net.get("opServerPort", "8000"))
                    https = bool(net.get("https") or port == "443")
                    scheme = "https" if https else "http"
                    return f"{scheme}://{ip}:{port}/"
                except Exception:
                    pass
        # 파일이 없거나 파싱 실패 시 기본 주소
        # return "http://172.16.110.29:49000/"
        return "http://172.16.110.67:49000/"

    # ───────────────────── threading helper ────────────────────
    def _post_to_ui(self, fn, *args, **kwargs):
        app = self._app or kit_app.get_app()
        cb = lambda: fn(*args, **kwargs)
        if hasattr(app, "post_to_main_thread"):
            app.post_to_main_thread(cb)
        elif hasattr(app, "get_async_action_queue"):
            app.get_async_action_queue().put_nowait(cb)
        else:
            cb()

    # ────────────────────── callbacks ──────────────────────────
    def _on_alive_change(self, alive: bool):
        self._post_to_ui(self._set_status_dot, "Operation Server", alive)
        if not alive:
            self._post_to_ui(self._set_status_dot, "OPC UA", False)
            self._post_to_ui(self._set_status_dot, "Storage I/O", False)

    def _on_error(self, exc, endpoint, payload):
        msg = f"{type(exc).__name__}: {exc}"
        self._post_to_ui(self._append_error_line, msg)

    def _on_response(self, endpoint: str, request_payload: dict, response: dict):
        if not response or not response.get("success", False):
            self._post_to_ui(
                self._append_error_line,
                f"[Server] {(response or {}).get('message','Unknown error')}",
            )
            return

    def _on_client_response(self, endpoint, payload, response):
        if not payload:
            return

        data_type = payload.get("dataType")
        data = (response or {}).get("data")

        if data_type == "AMRInfo":
            arr = data if isinstance(data, list) else []

            def _is_running(it):
                # status가 숫자인 경우(예: INTASK=4)도 잡아줌
                s = it.get("status") or it.get("robotStatus") or it.get("state")
                if isinstance(s, (int, float)):
                    return int(s) == 4  # AMRStatusCode.INTASK
                s = (str(s) or "").strip().lower()
                return s in ("running", "working", "move", "moving", "busy", "intask")

            running = sum(1 for it in arr if _is_running(it))
            waiting = max(0, len(arr) - running)
            self._post_to_ui(self._set_model, "m_amr_running", f"{running} Running")
            self._post_to_ui(self._set_model, "m_amr_waiting", f"{waiting} Waiting")
            self._post_to_ui(self._sync_amr_cards, arr)

        elif data_type == "ContainerInfo":
            arr = data if isinstance(data, list) else []
            total = len(arr)
            off_map = sum(
                1
                for c in arr
                if c.get("isOffMap")
                or str(c.get("nodeCode", "")).lower() in ("", "none", "off_map", "offmap")
            )
            self._post_to_ui(self._set_model, "m_pallet_total", f"Total: {total}")
            self._post_to_ui(self._set_model, "m_pallet_offmap", f"Off Map: {off_map}")

        elif data_type == "WorkingInfo":
            items = data if isinstance(data, list) else []
            # robotIds가 존재하는 항목 수를 진행중으로 카운트
            in_progress = sum(1 for item in items if item.get("robotIds"))
            self._post_to_ui(self._set_model, "m_mission_inprogress", f"In Progress: {in_progress}")

        elif data_type == "MissionInfo":
            missions = data if isinstance(data, list) else []
            self._post_to_ui(self._set_model, "m_mission_reserved", f"Reserved: {len(missions)}")

        elif data_type == "ConnectionInfo":
            info = data[0] if isinstance(data, list) and data else (data or {})
            opc_ok = bool(info.get("opcuaStatus") or info.get("opcUaStatus") or info.get("opcStatus"))
            storage_ok = bool(info.get("storageIOStatus") or info.get("storageStatus"))
            self._post_to_ui(self._set_status_dot, "OPC UA", opc_ok)
            self._post_to_ui(self._set_status_dot, "Storage I/O", storage_ok)

    # ───────────────────── Operate/Edit 모드 ───────────────────
    def _apply_operate_mode(self, enable: bool):
        """Operate=True면 기즈모 숨김 + 선택 즉시 해제 구독 활성화."""
        s = carb.settings.get_settings()
        value = not enable  # Operate=True → 기즈모 숨김
        for k in (VIEWPORT_KEY_APP, VIEWPORT_KEY_PERSIST):
            try:
                s.set_bool(k, value)
            except Exception:
                s.set(k, value)

        usd = omni.usd.get_context()
        # Operate 모드: 선택 변경 시 즉시 해제
        if enable and not self._sel_sub:
            self._sel_sub = usd.get_stage_event_stream().create_subscription_to_pop(
                self._on_stage_evt, name="operate-mode-deselect"
            )
            # 이미 선택돼 있던 것들도 해제
            try:
                for p in usd.get_selection().get_selected_prim_paths():
                    usd.get_selection().set_prim_path_selected(p, False, False, True)
            except Exception:
                pass
        elif not enable and self._sel_sub:
            self._sel_sub = None

    def _on_stage_evt(self, evt):
        if not getattr(self, "_operate_mode", False):
            return
        if evt.type != int(StageEventType.SELECTION_CHANGED):
            return
        usd = omni.usd.get_context()
        sel = usd.get_selection().get_selected_prim_paths()
        if not sel:
            return
        # 선택 즉시 해제 → 이동/회전 불가
        try:
            for p in sel:
                usd.get_selection().set_prim_path_selected(p, False, False, True)
        except Exception:
            pass

    def _mode_button_text(self) -> str:
        return "Tools * Operate" if self._operate_mode else "Tools * Edit"

    def _toggle_operate_mode(self):
        self._operate_mode = not self._operate_mode
        self._settings.set_bool(SETTING_KEY, self._operate_mode)
        self._apply_operate_mode(self._operate_mode)
        self._refresh_mode_button()     # ← 라벨 바꾸지 말고 버튼 visible만 갱신

    def _init_mode_state(self):
        self._settings = carb.settings.get_settings()
        self._operate_mode = bool(self._settings.get_as_bool(SETTING_KEY))
        self._apply_operate_mode(self._operate_mode)
        self._refresh_mode_button()   # 버튼이 아직 없으면 hasattr 가드로 그냥 넘어갑니다


    def _refresh_mode_button(self):
        # Operate 모드면 Operate 버튼만 보이고, 아니면 Edit 버튼만 보이게
        try:
            if hasattr(self, "_btn_edit"):
                self._btn_edit.visible = not self._operate_mode
            if hasattr(self, "_btn_operate"):
                self._btn_operate.visible = self._operate_mode
        except Exception:
            pass
