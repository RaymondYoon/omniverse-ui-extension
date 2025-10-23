# __init__.py — IExt + 네트워크/모델 업데이트 (UI 메서드 호출만) + AMR 실시간 로깅

import os
import json
import threading
import urllib.request
import urllib.error
import time
from collections import deque  # UI 작업 큐
import inspect

import carb
import omni.ext
import omni.kit.app as kit_app
import omni.usd
from omni.usd import StageEventType
from omni.ui import SimpleStringModel

from .client import DigitalTwinClient
from .main import UiLayoutBase
from ui_code.Mission.mission_panel import MissionPanel   # 요청 경로 유지
from ui_code.ui.scene.linecar import LineCarSpawner      # 상단에서만 import

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


def _first_nonempty(d: dict, *keys, default: str = "-") -> str:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s != "":
            return s
    return default


class PlatformUiExtension(UiLayoutBase, omni.ext.IExt):
    # ───────────────────────── lifecycle ───────────────────────
    def on_startup(self, ext_id):
        self._sel_sub = None

        # ── 미션 카운터 모델/캐시 준비
        if not hasattr(self, "m_mission_total"):
            self.m_mission_total   = SimpleStringModel("Total: 0")
            self.m_mission_working = SimpleStringModel("Working: 0")
            self.m_mission_waiting = SimpleStringModel("Waiting: 0")
            self.m_mission_reserved = SimpleStringModel("Reserved: 0")

        self._amr_by_id = {}
        self._missions_latest_count = 0
        self._reservations_latest_count = 0
        self._mission_working = 0
        self._mission_waiting = 0

        # 미션 패널 스냅샷 캐시
        self._working_rows_latest = []
        self._missions_rows_latest = []
        self._reserv_rows_latest = []

        # 1) UI
        UiLayoutBase.on_startup(self, ext_id)
        self._show_placeholder_amr_cards(4)

        # 컨테이너 패널 데이터 리졸버
        self._containers_latest = {}
        self._container_panel.set_data_resolver(lambda: self._containers_latest)

        # 미션 패널
        self._mission_panel = None

        print("[Platform.ui.__init__] logic startup")

        # 2) 앱 핸들 + UI 작업큐
        self._app = kit_app.get_app()
        self._ui_jobs = deque()

        # 매 프레임은 _on_update 하나만 구독
        if hasattr(self._app, "get_update_event_stream"):
            self._ui_tick_sub = self._app.get_update_event_stream().create_subscription_to_pop(
                self._on_update, name="platform-ui-update"
            )
        else:
            self._ui_tick_sub = self._app.post_render_event_stream.create_subscription_to_pop(
                self._on_update, name="platform-ui-update"
            )

        # 3) 설정 로드 (OP 서버, Fleet 서버, mapCode 등) — 하드코딩 제거
        cfg = self._load_config()
        self._base_url  = cfg.get("op_base_url") or ""
        self._fleet_url = cfg.get("fleet_base_url") or ""
        self._map_code  = cfg.get("map_code") or None

        print(f"[Platform.ui] base_url = {self._base_url or 'N/A'}")
        print(f"[Platform.ui] fleet_url = {self._fleet_url or 'N/A'}")
        print(f"[Platform.ui] map_code  = {self._map_code or 'N/A'}")

        # 4) 클라이언트 시작 (URL 없으면 건너뜀)
        self._client = None
        if self._base_url:
            self._client = DigitalTwinClient(base_url=self._base_url, interval=0.5, timeout=5.0)
            self._client.add_on_alive_change(self._on_alive_change)
            self._client.add_on_response(self._on_response)
            self._client.add_on_error(self._on_error)
            self._client.add_on_response(self._on_client_response)

            # AMRInfo 수신 감시(갱신 없을 때 경고용)
            self._last_amrinfo_time = 0.0
            self._last_no_update_warn = 0.0
            self._warn_every_s = 5.0

            # 최근 AMR 원본 좌표 스냅샷(변화 감지)
            self._last_raw_by_rid = {}

            try:
                # map_code가 있으면 전달, 없으면 인자 없이 시도
                if self._map_code:
                    self._client.start(map_code=self._map_code)
                else:
                    self._client.start()
            except TypeError:
                self._client.start()
        else:
            print("[Platform.ui][WARN] 'op_base_url'이 비어 있습니다. DigitalTwinClient 시작을 건너뜁니다.")

        # 5) Fleet 핑 (URL 없으면 건너뜀)
        self._fleet_pinger = None
        if self._fleet_url:
            self._fleet_pinger = HttpPinger(
                url=self._fleet_url, interval=2.0, timeout=1.5,
                on_change=lambda alive: self._post_to_ui(self._set_status_dot, "Fleet Server", alive),
            )
            self._fleet_pinger.start()
            print(f"[Platform.ui] Fleet pinger started → {self._fleet_url}")
        else:
            print("[Platform.ui][WARN] 'fleet_base_url'이 비어 있습니다. Fleet 핑을 건너뜁니다.")

        # 6) 라인카 스포너
        self._line_car_1 = LineCarSpawner(
            usd_path=r"C:\BODY.usd",
            parent_path="/World/LineCars",
            start_x=-2200,
            end_x=9150,
            lane_y=1120,
            count=20,
        )
        self._line_car_1.start()

        self._line_car_2 = LineCarSpawner(
            usd_path=r"C:\BODY.usd",
            parent_path="/World/LineCars2",
            proto_path="/World/_BodyProto2",
            start_x=10950,
            end_x=250,
            lane_y=2425,
            yaw_deg=-90,
            count=19,
        )
        self._line_car_2.start()

    def on_shutdown(self):
        try:
            if getattr(self, "_line_car_1", None):
                try:
                    self._line_car_1.stop()
                except Exception:
                    pass
            if getattr(self, "_line_car_2", None):
                try:
                    self._line_car_2.stop()
                except Exception:
                    pass

            if getattr(self, "_ui_tick_sub", None):
                self._ui_tick_sub = None
            if getattr(self, "_sel_sub", None):
                self._sel_sub = None
            if getattr(self, "_fleet_pinger", None):
                try:
                    self._fleet_pinger.stop()
                except Exception:
                    pass
            if getattr(self, "_client", None):
                try:
                    self._client.stop()
                except Exception:
                    pass
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
    def _load_config(self) -> dict:
        """
        platform_ext/config/Network.json 에서 설정을 읽어온다.
        - OP 서버 URL: baseUrl 또는 opServerIP/opServerPort/https 조합
        - Fleet 서버 URL: fleetUrl 또는 fleetServerIP/fleetServerPort/fleetHttps 조합
        - mapCode: mapCode
        하드코딩된 기본값은 넣지 않는다. (없으면 빈 값 반환)
        """
        def _normalize(u: str) -> str:
            if not u:
                return ""
            u = str(u).strip()
            return u if u.endswith("/") else (u + "/")

        def _url_from_ip_port(ip, port, https_flag) -> str:
            if not ip or not port:
                return ""
            scheme = "https" if (https_flag or str(port) == "443") else "http"
            return f"{scheme}://{ip}:{port}/"

        def _read_json(path: str) -> dict:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}

        # 주 경로: platform_ext/config/Network.json
        this_dir = os.path.dirname(__file__)            # ../platform_ext/ui_code
        ext_root = os.path.dirname(this_dir)            # ../platform_ext
        cfg_path = os.path.join(ext_root, "config", "Network.json")

        # 호환 경로(선택): ui_code/Network.json, 사용자 문서 폴더
        compat1 = os.path.join(this_dir, "Network.json")
        compat2 = os.path.join(os.path.expanduser("~"), "Documents", "Omniverse", "Network.json")

        raw = {}
        used_path = ""
        for p in (cfg_path, compat1, compat2):
            if os.path.exists(p):
                raw = _read_json(p)
                used_path = p
                break

        if used_path:
            print(f"[Platform.ui] config loaded from {used_path}")
        else:
            print("[Platform.ui][WARN] Network.json을 찾지 못했습니다.")

        # OP URL
        op_url = (
            raw.get("baseUrl")
            or raw.get("opBaseUrl")
            or _url_from_ip_port(
                raw.get("opServerIP") or raw.get("opIp"),
                raw.get("opServerPort") or raw.get("opPort"),
                bool(raw.get("https") or raw.get("opHttps"))
            )
        )

        # Fleet URL
        fleet_url = (
            raw.get("fleetUrl")
            or raw.get("fleetBaseUrl")
            or _url_from_ip_port(
                raw.get("fleetServerIP") or raw.get("fleetIp"),
                raw.get("fleetServerPort") or raw.get("fleetPort"),
                bool(raw.get("fleetHttps"))
            )
        )

        map_code = raw.get("mapCode")

        return {
            "op_base_url": _normalize(op_url),
            "fleet_base_url": _normalize(fleet_url),
            "map_code": map_code,
        }

    # ───────────────────── threading helper ────────────────────
    def _post_to_ui(self, fn, *args, **kwargs):
        def job():
            try:
                fn(*args, **kwargs)
            except Exception as e:
                print("[Platform.ui] UI update failed:", e)

        if not hasattr(self, "_ui_jobs") or self._ui_jobs is None:
            job()
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
        # 서버 에러는 조용히 무시(원하면 로깅 추가)
        return

    def _on_response(self, endpoint: str, request_payload: dict, response: dict):
        if not response or not response.get("success", False):
            return

    def _append_amr_errors_to_log(self, items):
        if not items:
            return

        def _norm(s: str) -> str:
            s = (s or "").strip().lower()
            return s.replace(" ", "").replace("-", "").replace("_", "")

        bad_tokens = {}
        rid_seen = set()

        for it in items:
            rid = str(it.get("robotId") or "").strip()
            msg = str(it.get("errorMessage") or "").strip()
            if not rid or not msg:
                continue
            if rid in rid_seen:
                continue
            nmsg = _norm(msg)
            if any(tok and tok in nmsg for tok in bad_tokens):
                continue

            self._append_error_line(f"{rid}, {msg}")
            rid_seen.add(rid)

        if not rid_seen:
            self._append_error_line("No AMR errors")

    def _on_client_response(self, endpoint, payload, response):
        if not payload:
            return
        data_type = payload.get("dataType")
        data = (response or {}).get("data")

        # ───────── AMRInfo ─────────
        if data_type == "AMRInfo":
            self._last_amrinfo_time = time.time()
            arr = data if isinstance(data, list) else []

            AMR_EXIT, AMR_OFFLINE, AMR_IDLE, AMR_INTASK, AMR_CHARGING, AMR_UPDATING, AMR_EXCEPTION = 1, 2, 3, 4, 5, 6, 7

            def _status_code(it):
                s = it.get("status")
                if isinstance(s, (int, float)):
                    try:
                        return int(s)
                    except Exception:
                        return 0
                t = ("" if s is None else str(s)).strip().lower()
                if t.isdigit():
                    return int(t)
                m = {
                    "idle": AMR_IDLE,
                    "intask": AMR_INTASK, "running": AMR_INTASK, "working": AMR_INTASK,
                    "charging": AMR_CHARGING,
                    "exit": AMR_EXIT, "offline": AMR_OFFLINE, "updating": AMR_UPDATING, "exception": AMR_EXCEPTION,
                }
                return m.get(t, 0)

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

            self._post_to_ui(self._set_model, "m_amr_total",    f"Total: {total}")
            self._post_to_ui(self._set_model, "m_amr_working",  f"Working: {working}")
            self._post_to_ui(self._set_model, "m_amr_waiting",  f"Waiting: {waiting}")
            self._post_to_ui(self._set_model, "m_amr_charging", f"Charging: {charging}")

            self._post_to_ui(self._sync_amr_cards, arr)
            self._post_to_ui(self._amr3d.sync, arr)

            # AMR 캐시
            self._amrs_latest = arr
            if hasattr(self, "_amr_control_panel") and self._amr_control_panel:
                self._post_to_ui(self._amr_control_panel.update_amr_list, arr)

            amr_by_id = {}
            for it in arr:
                rid = str(it.get("robotId") or "").strip()
                if rid:
                    amr_by_id[rid] = it
            self._amr_by_id = amr_by_id

            # 에러 로그
            self._post_to_ui(self._append_amr_errors_to_log, arr)

        # ───────── ContainerInfo ─────────
        elif data_type == "ContainerInfo":
            arr = data if isinstance(data, list) else []
            total = len(arr)

            def _in_map(c: dict) -> bool:
                if "inMapStatus" in c:
                    return bool(c.get("inMapStatus"))
                if c.get("isOffMap") is not None:
                    return not bool(c.get("isOffMap"))
                node = str(c.get("nodeCode", "")).strip().lower()
                return node not in ("", "none", "off_map", "offmap")

            def _carry_kind(c: dict) -> str:
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

            self._post_to_ui(self._set_model, "m_pallet_total",      f"Total: {total}")
            self._post_to_ui(self._set_model, "m_pallet_offmap",     f"Off Map: {off_map}")
            self._post_to_ui(self._set_model, "m_pallet_stationary", f"Stationary: {stationary}")
            self._post_to_ui(self._set_model, "m_pallet_inhandling", f"In Handling: {in_handling}")

            # 패널용 캐시
            def _norm_containers(items):
                norm = {}
                for i, it in enumerate(items or []):
                    d = dict(it or {})
                    cid = str(d.get("containerCode") or d.get("id") or d.get("name") or f"C{i+1:03d}")
                    d["containerCode"] = cid
                    model = d.get("containerModelCode") or d.get("model")
                    d["containerModelCode"] = str(model) if model is not None else "-"
                    if "inMapStatus" not in d:
                        if "isOffMap" in d:
                            d["inMapStatus"] = not bool(d.get("isOffMap"))
                        else:
                            node = str(d.get("nodeCode", "")).strip().lower()
                            d["inMapStatus"] = node not in ("", "none", "offmap", "off_map")
                    norm[cid] = d
                return norm

            norm = _norm_containers(arr)
            def _apply():
                self._containers_latest = norm
            self._post_to_ui(_apply)

        # ───────── WorkingInfo (미션) ─────────
        elif data_type == "WorkingInfo":
            if isinstance(data, dict):
                items = [{"Key": k, "Value": v} for k, v in data.items()]
            else:
                items = data if isinstance(data, list) else []

            self._mission_working, self._mission_waiting = self._calc_working_counts(items)
            self._update_mission_counters()

            self._working_rows_latest = [self._norm_working_row(it) for it in items]
            if self._mission_panel:
                self._post_to_ui(self._mission_panel.refresh)

        # ───────── MissionInfo ─────────
        elif data_type == "MissionInfo":
            missions = data if isinstance(data, list) else []
            self._missions_latest_count = len(missions)
            self._update_mission_counters()

            self._missions_rows_latest = [self._norm_reserved_row(it) for it in missions]
            if self._mission_panel:
                self._post_to_ui(self._mission_panel.refresh)

        # ───────── ReservationInfo ─────────
        elif data_type == "ReservationInfo":
            reservations = data if isinstance(data, list) else []
            self._reservations_latest_count = len(reservations)
            self._update_mission_counters()

            self._reserv_rows_latest = [self._norm_reserved_row(it) for it in reservations]
            if self._mission_panel:
                self._post_to_ui(self._mission_panel.refresh)

        # ───────── ConnectionInfo ─────────
        elif data_type == "ConnectionInfo":
            info = data[0] if isinstance(data, list) and data else (data or {})
            opc_ok = bool(info.get("opcuaStatus") or info.get("opcUaStatus") or info.get("opcStatus"))
            storage_ok = bool(info.get("storageIOStatus") or info.get("storageStatus"))
            self._post_to_ui(self._set_status_dot, "OPC UA", opc_ok)
            self._post_to_ui(self._set_status_dot, "Storage I/O", storage_ok)

    # ───────────────────── Operate/Edit 모드 ───────────────────
    def _apply_operate_mode(self, enable: bool):
        s = carb.settings.get_settings()
        value = not enable
        for k in (VIEWPORT_KEY_APP, VIEWPORT_KEY_PERSIST):
            try:
                s.set_bool(k, value)
            except Exception:
                s.set(k, value)

        usd = omni.usd.get_context()
        if enable and not self._sel_sub:
            self._sel_sub = usd.get_stage_event_stream().create_subscription_to_pop(
                self._on_stage_evt, name="operate-mode-deselect"
            )
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
        self._refresh_mode_button()

    def _init_mode_state(self):
        self._settings = carb.settings.get_settings()
        self._operate_mode = bool(self._settings.get_as_bool(SETTING_KEY))
        self._apply_operate_mode(self._operate_mode)
        self._refresh_mode_button()

    def _refresh_mode_button(self):
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
                self._amr3d.update()
        except Exception as ex:
            print("[Platform.ui] amr3d.update failed:", ex)

        # 2) 최근 AMRInfo 수신 확인(3초 무응답 시 5초 간격 경고)
        now = time.time()
        if getattr(self, "_last_amrinfo_time", 0.0) > 0 and (now - self._last_amrinfo_time) > 3.0:
            if (now - getattr(self, "_last_no_update_warn", 0.0)) > getattr(self, "_warn_every_s", 5.0):
                dt = now - self._last_amrinfo_time
                print(f"[AMRInfo][WARN] no update for {dt:.1f}s (check server/mapCode, network, client polling)")
                self._last_no_update_warn = now

        # 3) UI 작업큐 비우기
        self._drain_ui_jobs(e)

    # ───────────────────── Mission helpers ─────────────────────
    def _calc_working_counts(self, items):
        amr_by_id = getattr(self, "_amr_by_id", {}) or {}
        working = waiting = 0

        for it in (items or []):
            if "Key" in it and "Value" in it:
                mcode = str(it.get("Key") or "")
                val = it.get("Value") or {}
                rids = val.get("robotIds") or val.get("robotId") or val.get("robots") or []
                explicit_status = val.get("missionStatus")
            else:
                mcode = str(it.get("missionCode") or it.get("missionId") or it.get("key") or it.get("id") or "")
                rids = it.get("robotIds") or it.get("robotId") or it.get("robots") or []
                explicit_status = it.get("missionStatus")

            if isinstance(explicit_status, str):
                st = explicit_status.strip().lower()
                if st == "working":
                    working += 1
                    continue
                if st == "waiting":
                    waiting += 1
                    continue

            if isinstance(rids, (str, int)):
                rids = [str(rids)]
            else:
                rids = [str(r) for r in rids if r is not None]

            is_working = False
            if len(rids) == 1:
                rid = rids[0]
                amr = amr_by_id.get(rid)
                if amr:
                    amr_mission = str(
                        amr.get("missionCode")
                        or amr.get("missionId")
                        or amr.get("workingMission")
                        or ""
                    )
                    if mcode and (amr_mission == mcode):
                        is_working = True

            if is_working:
                working += 1
            else:
                waiting += 1

        return working, waiting

    def _norm_working_row(self, it):
        if "Key" in it and "Value" in it:
            mcode = str(it.get("Key") or "")
            v = it.get("Value") or {}
        else:
            mcode = str(it.get("missionCode") or it.get("missionId") or it.get("key") or it.get("id") or "")
            v = dict(it or {})

        status = (v.get("missionStatus") or "").strip()
        if not status:
            tmp_w, _tmp_wait = self._calc_working_counts([it])
            status = "Working" if tmp_w == 1 else "Waiting"

        rids = v.get("robotIds")
        if isinstance(rids, (str, int)):
            rids = [str(rids)]
        else:
            rids = [str(r) for r in rids if r is not None]
        amr_id = rids[0] if len(rids) == 1 else "-"
        if amr_id == "-":
            amr_id = _first_nonempty(v, "amrId", "robotId", "rid", "robot", "agvId", "vehicleId", default="-")

        proc = _first_nonempty(
            v,
            "process", "processCode", "processName",
            "node", "nodeCode",
            "task", "operation", "type", "missionType",
            "job", "jobCode", "workType", "work", "action",
            default="-",
        )

        target = "-"
        mission_data_raw = v.get("missionData")
        if mission_data_raw:
            try:
                mission_data = json.loads(mission_data_raw)
                if isinstance(mission_data, list) and len(mission_data) > 0:
                    pos = mission_data[0].get("position")
                    if pos:
                        target = pos
            except Exception as e:
                print(f"[WorkingInfo] missionData parse error: {e}")

        return {
            "missionStatus": status,
            "process": proc,
            "missionCode": mcode or "-",
            "amrId": amr_id,
            "targetNode": target,
        }

    def _norm_reserved_row(self, it):
        d = dict(it or {})
        proc = _first_nonempty(
            d,
            "process", "processCode", "processName",
            "node", "nodeCode", "task", "operation", "type",
            default="-",
        )
        if proc == "-":
            src = _first_nonempty(d, "fromNode", "sourceNode", "src", "srcNode", default="")
            dst = _first_nonempty(d, "target", "targetNode", default="")
            if src or dst:
                proc = f"{src}→{dst}"

        target = _first_nonempty(
            d,
            "targetNode", "target",
            "toNode", "destinationNode", "dst", "dstNode",
            "endNode", "goalNode", "goal", "dest", "to",
            default="-",
        )

        mission_data_raw = d.get("missionData")
        if mission_data_raw and (target == "-" or not target.strip()):
            try:
                mission_data = json.loads(mission_data_raw)
                if isinstance(mission_data, list) and len(mission_data) > 0:
                    pos = mission_data[0].get("position") or mission_data[0].get("to") or mission_data[0].get("target")
                    if pos:
                        target = str(pos)
            except Exception as e:
                print(f"[ReservationInfo] missionData parse error: {e}")

        return {
            "missionStatus": "Reservation",
            "process": proc,
            "missionCode": _first_nonempty(d, "missionCode", "missionId", "key", "id", "reservationCode", default="-"),
            "amrId": _first_nonempty(d, "amrId", "robotId", "rid", default="-"),
            "targetNode": target,
        }

    def _mission_snapshot(self):
        work_rows = []
        wait_rows = []
        for r in (self._working_rows_latest or []):
            st = (r.get("missionStatus") or "").strip().lower()
            if st == "working":
                work_rows.append(r)
            else:
                wait_rows.append(r)
        reserved_rows = list(self._missions_rows_latest or []) + list(self._reserv_rows_latest or [])
        return {"working": work_rows, "waiting": wait_rows, "reserved": reserved_rows}

    def _open_mission_panel(self):
        def _open():
            if not self._mission_panel:
                self._mission_panel = MissionPanel(
                    resolver=self._mission_snapshot,
                    on_cancel=self._mission_cancel,
                    on_reset_all=self._mission_reset_all,
                )
            self._mission_panel.show()
            self._mission_panel.refresh()
        self._post_to_ui(_open)

    def _send_to_client(self, action: str, payload: dict) -> bool:
        c = getattr(self, "_client", None)
        if not c:
            self._post_to_ui(self._append_error_line, "[MissionCancel] client not ready")
            return False

        candidates = ["request_post", "post", "send", "enqueue", "request", "emit", "push", "call", "submit"]

        for name in candidates:
            fn = getattr(c, name, None)
            if not callable(fn):
                continue

            combos = [
                ((), {"payload": payload}),
                ((payload,), {}),
                ((action, payload), {}),
                ((), {"endpoint": action, "payload": payload}),
                ((), {"action": action, "payload": payload}),
                ((), {"path": action, "payload": payload}),
                ((), {"dataType": action, "payload": payload}),
                ((), {"data": payload}),
                ((), {"body": payload}),
            ]

            try:
                sig = inspect.signature(fn)
                params = sig.parameters
            except Exception:
                params = None
                combos = [((payload,), {}), ((action, payload), {})]

            for args, kwargs in combos:
                try:
                    if params is not None:
                        kwargs = {k: v for k, v in kwargs.items()
                                  if (k in params) or any(p.kind == p.VAR_KEYWORD for p in params.values())}
                    fn(*args, **kwargs)
                    return True
                except Exception:
                    continue

        self._post_to_ui(self._append_error_line, "[MissionCancel] No suitable client method")
        return False

    def _optimistic_remove_post_cancel(self, *, mission_code=None, node_code=None):
        changed = False

        if mission_code:
            rows = self._working_rows_latest or []
            keep = []
            w_dec = wait_dec = 0
            for r in rows:
                if (r.get("missionCode") or "") == mission_code:
                    st = (r.get("missionStatus") or "").lower()
                    if st == "working":
                        w_dec += 1
                    else:
                        wait_dec += 1
                    changed = True
                else:
                    keep.append(r)
            self._working_rows_latest = keep
            if w_dec or wait_dec:
                self._mission_working = max(0, int(self._mission_working) - w_dec)
                self._mission_waiting = max(0, int(self._mission_waiting) - wait_dec)

        if node_code:
            before = len(self._missions_rows_latest or [])
            self._missions_rows_latest = [
                r for r in (self._missions_rows_latest or []) if (r.get("process") or "") != node_code
            ]
            removed = before - len(self._missions_rows_latest)
            if removed > 0:
                self._missions_latest_count = max(0, int(self._missions_latest_count) - removed)
                changed = True
            else:
                before = len(self._reserv_rows_latest or [])
                self._reserv_rows_latest = [
                    r for r in (self._reserv_rows_latest or []) if (r.get("process") or "") != node_code
                ]
                removed = before - len(self._reserv_rows_latest)
                if removed > 0:
                    self._reservations_latest_count = max(0, int(self._reservations_latest_count) - removed)
                    changed = True

        if changed:
            self._update_mission_counters()
            if getattr(self, "_mission_panel", None):
                self._post_to_ui(self._mission_panel.refresh)

    def _mission_cancel(self, mission_code=None, node_code=None):
        payload = {"dataType": "MissionCancel"}
        if self._map_code:
            payload["mapCode"] = self._map_code
        if mission_code:
            payload["cancelMissionCode"] = mission_code
        if node_code:
            payload["cancelNodeCode"] = node_code

        ok = self._send_to_client("MissionCancel", payload)
        self._optimistic_remove_post_cancel(mission_code=mission_code, node_code=node_code)
        if not ok:
            pass

    def _mission_reset_all(self):
        snap = self._mission_snapshot()
        for row in (snap.get("working") or []) + (snap.get("waiting") or []):
            code = row.get("missionCode")
            if code and code != "-":
                self._mission_cancel(mission_code=code)

        for row in (snap.get("reserved") or []):
            node = row.get("process")
            if node and node != "-":
                self._mission_cancel(node_code=node)

    def _update_mission_counters(self):
        w    = int(getattr(self, "_mission_working", 0) or 0)
        wait = int(getattr(self, "_mission_waiting", 0) or 0)
        mi   = int(getattr(self, "_missions_latest_count", 0) or 0)
        rs   = int(getattr(self, "_reservations_latest_count", 0) or 0)

        total    = (w + wait) + mi + (rs * 2)
        reserved = mi + (rs * 2)

        self._post_to_ui(self._set_model, "m_mission_total",    f"Total: {total}")
        self._post_to_ui(self._set_model, "m_mission_working",  f"Working: {w}")
        self._post_to_ui(self._set_model, "m_mission_waiting",  f"Waiting: {wait}")
        self._post_to_ui(self._set_model, "m_mission_reserved", f"Reserved: {reserved}")
