# __init__.py — IExt + 네트워크/모델 업데이트 (UI 메서드 호출만)

import os
import json
import threading
import urllib.request
import urllib.error
from collections import deque  # ★ UI 작업 큐

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
        self._sel_sub = None

        # 1) UI 먼저
        UiLayoutBase.on_startup(self, ext_id)
        self._show_placeholder_amr_cards(4)

        self._containers_latest = {}  # 컨테이너 최신 스냅샷 보관소
        self._container_panel.set_data_resolver(lambda: self._containers_latest)

        print("[Platform.ui.__init__] logic startup")

        # 2) 앱 핸들 + UI 작업큐
        self._app = kit_app.get_app()
        self._ui_jobs = deque()

        # 👉 매 프레임은 _on_update 하나만 구독
        if hasattr(self._app, "get_update_event_stream"):
            self._ui_tick_sub = self._app.get_update_event_stream().create_subscription_to_pop(
                self._on_update, name="platform-ui-update"
            )
        else:
            self._ui_tick_sub = self._app.post_render_event_stream.create_subscription_to_pop(
                self._on_update, name="platform-ui-update"
            )

        # 3) 클라이언트 시작
        base_url = self._load_base_url_from_network()
        print(f"[Platform.ui] base_url = {base_url}")

        self._client = DigitalTwinClient(base_url=base_url, interval=0.5, timeout=5.0)
        self._client.add_on_alive_change(self._on_alive_change)
        self._client.add_on_response(self._on_response)
        self._client.add_on_error(self._on_error)
        self._client.add_on_response(self._on_client_response)
        self._client.start(map_code="RR_Floor")

        # 4) Fleet 핑
        fleet_url = "http://172.16.110.190:5000/"
        self._fleet_pinger = HttpPinger(
            url=fleet_url, interval=2.0, timeout=1.5,
            on_change=lambda alive: self._post_to_ui(self._set_status_dot, "Fleet Server", alive),
        )
        self._fleet_pinger.start()
        print(f"[Platform.ui] Fleet pinger started → {fleet_url}")


    def on_shutdown(self):
        try:
            # 이벤트 구독 해제
            if getattr(self, "_ui_tick_sub", None):
                self._ui_tick_sub = None
            if getattr(self, "_sel_sub", None):
                self._sel_sub = None

            # 백그라운드들 정지
            if getattr(self, "_fleet_pinger", None):
                self._fleet_pinger.stop()
            if getattr(self, "_client", None):
                self._client.stop()

            # UI 작업 큐 비우기
            if getattr(self, "_ui_jobs", None):
                try:
                    self._ui_jobs.clear()
                except Exception:
                    pass
                self._ui_jobs = None
        finally:
            UiLayoutBase.on_shutdown(self)
        print("[Platform.ui] using __init__.py:", __file__)



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
                    ip = net.get("opServerIP", "172.16.110.67")
                    port = str(net.get("opServerPort", "49000"))
                    https = bool(net.get("https") or port == "443")
                    scheme = "https" if https else "http"
                    return f"{scheme}://{ip}:{port}/"
                except Exception:
                    pass
        # 파일이 없거나 파싱 실패 시 기본 주소
        return "http://172.16.110.67:49000/"

    # ───────────────────── threading helper ────────────────────
    def _post_to_ui(self, fn, *args, **kwargs):
        """백그라운드 스레드에서 호출 → 메인스레드 update에서 실행"""
        def job():
            try:
                fn(*args, **kwargs)
            except Exception as e:
                print("[Platform.ui] UI update failed:", e)

        # on_startup 아주 초기 타이밍 보호
        if not hasattr(self, "_ui_jobs") or self._ui_jobs is None:
            job()  # 큐가 아직 없다면 즉시 실행(초기 UI 구성 시점)
            return

        self._ui_jobs.append(job)

    def _drain_ui_jobs(self, *_):
        q = getattr(self, "_ui_jobs", None)
        if not q:
            return
        while True:
            try:
                job = q.popleft()
            except IndexError:
                break
            try:
                job()
            except Exception as e:
                print("[Platform.ui] UI update failed:", e)

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

        # __init__.py  → PlatformUiExtension._on_client_response() 내부
        if data_type == "AMRInfo":
            arr = data if isinstance(data, list) else []

            AMR_EXIT      = 1
            AMR_OFFLINE   = 2
            AMR_IDLE      = 3
            AMR_INTASK    = 4
            AMR_CHARGING  = 5
            AMR_UPDATING  = 6
            AMR_EXCEPTION = 7

            def _status_code(it):
                """status/robotStatus/state에서 Unity와 동일한 숫자코드 추출"""
                s = it.get("status") or it.get("robotStatus") or it.get("state")
                if isinstance(s, (int, float)):
                    return int(s)
                # "3", "4" 같은 문자열 숫자면 그대로 변환
                try:
                    return int(str(s).strip())
                except Exception:
                    # 혹시 문자열 상태명이 올 때(옵션): 최소 매핑만 지원
                    m = {
                        "idle": AMR_IDLE,
                        "intask": AMR_INTASK, "running": AMR_INTASK, "working": AMR_INTASK,
                        "charging": AMR_CHARGING,
                    }
                    return m.get((str(s) or "").strip().lower(), 0)

            total = len(arr)
            working = waiting = charging = 0

            for it in arr:
                code = _status_code(it)
                if code == AMR_IDLE:
                    waiting += 1
                elif code == AMR_INTASK:
                    working += 1
                elif code == AMR_CHARGING:
                    charging += 1
                # EXIT/OFFLINE/UPDATING/EXCEPTION 등은 집계에서 제외(=Unity 코드와 동일 동작)

            # UI 모델 갱신 (Unity와 동일한 4항목)
            self._post_to_ui(self._set_model, "m_amr_total",    f"Total: {total}")
            self._post_to_ui(self._set_model, "m_amr_working",  f"Working: {working}")
            self._post_to_ui(self._set_model, "m_amr_waiting",  f"Waiting: {waiting}")
            self._post_to_ui(self._set_model, "m_amr_charging", f"Charging: {charging}")

            # 기존 카드/3D 동기화는 그대로 유지
            self._post_to_ui(self._sync_amr_cards, arr)
            self._post_to_ui(self._amr3d.sync, arr)

        # 최신 AMR 스냅샷 저장(패널 오픈 전/후 모두를 위해)
            self._amrs_latest = arr

            # 패널이 이미 만들어졌다면, 드롭다운 옵션 즉시 갱신
            if hasattr(self, "_amr_control_panel") and self._amr_control_panel:
                arr_for_panel = arr if isinstance(arr, (list, dict)) else []
                self._post_to_ui(self._amr_control_panel.update_amr_list, arr_for_panel)

        elif data_type == "ContainerInfo":
            arr = data if isinstance(data, list) else []

            # ── 통계 집계 ──────────────────────────────────────────────
            total = len(arr)

            def _in_map(c: dict) -> bool:
                # inMapStatus 최우선
                if "inMapStatus" in c:
                    return bool(c.get("inMapStatus"))
                # 보완 규칙
                if c.get("isOffMap") is not None:
                    return not bool(c.get("isOffMap"))
                node = str(c.get("nodeCode", "")).strip().lower()
                return node not in ("", "none", "off_map", "offmap")

            def _carry_kind(c: dict) -> str:
                """
                Stationary / InHandling 분류.
                - bool: True=InHandling, False=Stationary
                - int/str 숫자: 0=Stationary, 1=InHandling
                - 문자열 키워드 매핑
                """
                v = c.get("isCarry")
                if v is None:
                    v = c.get("carryStatus") or c.get("carry")

                if isinstance(v, bool):
                    return "in_handling" if v else "stationary"

                try:
                    iv = int(str(v).strip())
                    return "stationary" if iv == 0 else "in_handling"
                except Exception:
                    pass

                s = (str(v) or "").strip().lower()
                if s in ("0", "stationary", "stay", "parked"):
                    return "stationary"
                if s in ("1", "inhandling", "in_handling", "handling", "moving", "move", "carry", "carrying"):
                    return "in_handling"
                return "in_handling"

            off_map = 0
            stationary = 0
            in_handling = 0

            for c in arr:
                if _in_map(c):
                    kind = _carry_kind(c)
                    if kind == "stationary":
                        stationary += 1
                    else:
                        in_handling += 1
                else:
                    off_map += 1

            # UI 모델 갱신 (카운터만)
            self._post_to_ui(self._set_model, "m_pallet_total",      f"Total: {total}")
            self._post_to_ui(self._set_model, "m_pallet_offmap",     f"Off Map: {off_map}")
            self._post_to_ui(self._set_model, "m_pallet_stationary", f"Stationary: {stationary}")
            self._post_to_ui(self._set_model, "m_pallet_inhandling", f"In Handling: {in_handling}")

            # ── 패널용 데이터는 '정규화'해서 캐시에만 저장 (패널로 직접 푸시 금지) ──
            def _norm_containers(items):
                norm = {}
                for i, it in enumerate(items or []):
                    d = dict(it or {})

                    # ID 보정
                    cid = str(
                        d.get("containerCode")
                        or d.get("id")
                        or d.get("name")
                        or f"C{i+1:03d}"
                    )
                    d["containerCode"] = cid

                    # 모델 표기 보정 (문자열로)
                    model = d.get("containerModelCode") or d.get("model")
                    d["containerModelCode"] = str(model) if model is not None else "-"

                    # 맵 상태 보정
                    if "inMapStatus" not in d:
                        if "isOffMap" in d:
                            d["inMapStatus"] = not bool(d.get("isOffMap"))
                        else:
                            node = str(d.get("nodeCode", "")).strip().lower()
                            d["inMapStatus"] = node not in ("", "none", "offmap", "off_map")

                    norm[cid] = d
                return norm

            norm = _norm_containers(arr)

            # 캐시만 교체하고, 패널 update_data는 호출하지 않음 (스냅샷 방식)
            def _apply():
                self._containers_latest = norm

            self._post_to_ui(_apply)


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

    def _on_update(self, e):
        # 1) AMR 자연스러운 이동/회전 보간
        try:
            if hasattr(self, "_amr3d") and self._amr3d:
                self._amr3d.update()   # dt는 내부에서 자동 계산
        except Exception as ex:
            print("[Platform.ui] amr3d.update failed:", ex)

        # 2) UI 작업큐 비우기 (메인스레드 안전)
        self._drain_ui_jobs(e)
