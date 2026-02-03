from typing import Optional, Iterable, Dict, Any, List
import re
import omni.ui as ui
from ui_code.ui.utils.common import _fill
import json
import omni.usd
import omni.kit.commands
import omni.kit.app

# 표시용 명령 목록과 서버 dataType 매핑
_COMMANDS: List[str] = ["Move", "Rack Move", "Pause", "Resume", "Cancel"]
_DATATYPE_MAP: Dict[str, str] = {
    "Move":       "ManualMove",
    "Rack Move":  "ManualRackMove",
    "Pause":      "AMRPause",
    "Resume":     "AMRResume",
    "Cancel":     "MissionCancel",
}

def _numeric_sort(ids: List[str]) -> List[str]:
    """문자/숫자 혼재 시 숫자는 숫자 기준, 나머지는 사전식."""
    def keyf(s: str):
        t = s.strip()
        return (0, int(t)) if t.isdigit() else (1, t)
    return sorted(set(ids), key=keyf)


class AMRControlPanel:
    TITLE = "AMR Control"

    def __init__(
        self,
        client: Optional[object] = None,
        map_code: str = "E_Comp",
        set_selection_passthrough=None,
    ):
        self._client = client
        self._map_code = map_code
        self._set_selection_passthrough = set_selection_passthrough or (lambda *_: None)

        self._win: Optional[ui.Window] = None

        # ▼ AMR 콤보(옵션/모델/프레임)
        self._amr_ids: List[str] = ["-"]
        self._amr_idx: Optional[ui.AbstractValueModel] = None  # ComboBox 내부 모델
        self._amr_combo_frame: Optional[ui.Frame] = None

        # 표시용(디버그/외부호출 대비) — 전송은 항상 인덱스에서 읽음
        self._amr_id_str = ui.SimpleStringModel("-")

        # 명령 & 파라미터
        self._cmd_idx: Optional[ui.AbstractValueModel] = None  # Command 콤보 내부 모델
        self._container = ui.SimpleStringModel("")
        self._node = ui.SimpleStringModel("")
        self._mission = ui.SimpleStringModel("")

        self._row_container: Optional[ui.Frame] = None
        self._row_node: Optional[ui.Frame] = None
        self._row_mission: Optional[ui.Frame] = None
        self._container_field: Optional[ui.StringField] = None
        self._node_field: Optional[ui.StringField] = None
        self._mission_field: Optional[ui.StringField] = None

        self._sel_poll = None          # 업데이트 스트림 구독 핸들
        self._last_sel_name = None     # 마지막으로 반영한 이름(변화 없을 때 스킵)

        # ▼ 최신 AMR 정보/미션코드 캐시
        self._amr_latest: Dict[str, Dict[str, Any]] = {}
        self._amr_mission_map: Dict[str, str] = {}

    # ───────── 외부 주입 ─────────
    def set_client(self, client): self._client = client
    def get_client(self): return self._client

    # ───────── AMR 리스트 갱신 (AMRInfo 수신마다 호출) ─────────
    def update_amr_list(self, items: Iterable[Dict[str, Any]] | Dict[str, Dict[str, Any]]):
        # 1) 수신 → id 추출 & 미션코드 캐시
        src = (items.values() if isinstance(items, dict) else (items or []))
        new_ids: List[str] = []
        for it in src:
            it = it or {}
            rid = str(it.get("robotId") or it.get("amrId") or it.get("id") or "").strip()
            if not rid:
                continue
            new_ids.append(rid)
            self._amr_latest[rid] = it
            mc = str(it.get("missionCode") or "").strip()
            # 빈 문자열이면 기존 값 제거(스테일 방지)
            if mc:
                self._amr_mission_map[rid] = mc
            else:
                self._amr_mission_map.pop(rid, None)

        new_ids = _numeric_sort(new_ids) or ["-"]

        # 현재 선택 라벨 보존
        cur_val = self._current_amr_value()

        # 2) 목록이 바뀐 경우에만 콤보 재구성
        if new_ids != self._amr_ids:
            self._amr_ids = new_ids
            if self._amr_combo_frame:
                self._amr_combo_frame.clear()
                with self._amr_combo_frame:
                    cb = ui.ComboBox(0, *self._amr_ids)  # 내부 모델 사용
                    self._amr_idx = cb.model.get_item_value_model()
                    # 이전 선택 라벨이 새 목록에 있으면 그 인덱스로 복원
                    self._amr_idx.set_value(self._index_of(cur_val))
                    self._amr_idx.add_value_changed_fn(self._on_amr_idx_changed)

            # 문자열 모델만 동기화
            self._sync_selected_string()
        else:
            # 목록 동일: 인덱스가 범위를 벗어나면만 보정
            if self._amr_idx:
                idx = self._amr_idx.get_value_as_int()
                if not (0 <= idx < len(self._amr_ids)):
                    self._amr_idx.set_value(0)
            self._sync_selected_string()

        # Cancel 모드에서 미션코드 자동 채움(현재 선택 AMR 기준)
        if self._current_command_label() == "Cancel":
            self._autofill_mission_if_empty()

    def _get_current_mission_code(self, amr_id: Optional[str] = None) -> str:
        rid = (amr_id or self._current_amr_value() or "").strip()
        return (self._amr_mission_map.get(rid) or "").strip()

    def _autofill_mission_if_empty(self):
        """Cancel 모드에서 미션 입력칸이 비어 있으면 현재 AMR의 missionCode로 자동 채움."""
        if self._current_command_label() != "Cancel":
            return
        cur = (self._mission.as_string or "").strip()
        if cur:
            return
        auto = self._get_current_mission_code()
        if auto:
            self._mission.set_value(auto)
            print(f"[AMRControl] Autofill cancelMissionCode from AMR {self._current_amr_value()} → {auto}")
        else:
            # 비어 있음을 명시적으로 알림(디버그)
            print(f"[AMRControl][WARN] No active missionCode for AMR {self._current_amr_value()}")

    def _current_amr_value(self) -> str:
        """현재 콤보가 가리키는 라벨을 안전하게 반환."""
        if self._amr_idx:
            try:
                i = self._amr_idx.get_value_as_int()
                if 0 <= i < len(self._amr_ids):
                    return self._amr_ids[i]
            except Exception:
                pass
        return (self._amr_id_str.as_string or "-").strip()

    def _index_of(self, rid: Optional[str]) -> int:
        if rid and rid in self._amr_ids:
            return self._amr_ids.index(rid)
        return 0

    def _sync_selected_string(self):
        val = self._current_amr_value()
        if (self._amr_id_str.as_string or "") != val:
            self._amr_id_str.set_value(val)
            print(f"[AMRControl] selection → {val}")

    # ───────── 표시 ─────────
    def show(self, amr_id: Optional[str] = None):
        if self._win:
            self._win.visible = True
            self._refresh_fields()
            return

        self._win = ui.Window(self.TITLE, width=420, height=300,
                              style={"background_color": 0x000000C0})

        with self._win.frame:
            with ui.VStack(spacing=10, padding=10, width=_fill()):
                ui.Label("AMR Control Panel", style={"font_size": 18, "color": 0xFFFFFFFF})

                # AMR 드롭다운
                with ui.HStack():
                    ui.Label("AMR:", width=100, style={"color": 0xFFFFFFFF})
                    self._amr_combo_frame = ui.Frame()
                    with self._amr_combo_frame:
                        cb_amr = ui.ComboBox(0, *self._amr_ids)
                        self._amr_idx = cb_amr.model.get_item_value_model()
                        # 외부에서 특정 AMR으로 열기를 원하면 반영
                        if amr_id:
                            self._amr_idx.set_value(self._index_of(str(amr_id)))
                        self._amr_idx.add_value_changed_fn(self._on_amr_idx_changed)
                        self._sync_selected_string()

                # Command
                with ui.HStack():
                    ui.Label("Command:", width=100, style={"color": 0xFFFFFFFF})
                    cb_cmd = ui.ComboBox(0, *_COMMANDS)
                    self._cmd_idx = cb_cmd.model.get_item_value_model()
                    self._cmd_idx.set_value(0)  # 기본 Move
                    self._cmd_idx.add_value_changed_fn(self._on_cmd_idx_changed)

                # Container
                self._row_container = ui.Frame()
                with self._row_container:
                    with ui.HStack():
                        ui.Label("Container:", width=100, style={"color": 0xFFFFFFFF})
                        self._container_field = ui.StringField(model=self._container, width=_fill())

                # Target Node
                self._row_node = ui.Frame()
                with self._row_node:
                    with ui.HStack():
                        ui.Label("Target Node:", width=100, style={"color": 0xFFFFFFFF})
                        self._node_field = ui.StringField(model=self._node, width=_fill())

                # Mission Code (Cancel 전용)
                self._row_mission = ui.Frame()
                with self._row_mission:
                    with ui.HStack():
                        ui.Label("Mission Code:", width=100, style={"color": 0xFFFFFFFF})
                        self._mission_field = ui.StringField(model=self._mission, width=_fill())

                ui.Separator()
                with ui.HStack(spacing=8, width=_fill()):
                    ui.Button("Dispatch", height=36, style={"color": 0xFFFFFFFF}, clicked_fn=self._on_dispatch)
                    ui.Button("Close",    height=36, style={"color": 0xFFFFFFFF}, clicked_fn=self._close)

        self._win.visible = True
        self._refresh_fields()
        if not self._sel_poll:              # ← 중복 구독 방지
            self._subscribe_to_selection()

    def _subscribe_to_selection(self):
        # 매 프레임 호출되는 업데이트 이벤트 스트림에 구독
        app = omni.kit.app.get_app()
        self._sel_poll = app.get_update_event_stream().create_subscription_to_pop(
            self._on_selection_poll,
            name="AMRControlPanel_SelectionPoll",
        )

    def _on_selection_poll(self, _e):
        """매 프레임 현재 선택을 읽어 Target Node에 '이름만' 반영."""
        try:
            # Cancel 모드일 때는 사용자 입력 우선: 자동 덮어쓰기 금지
            if self._current_command_label() == "Cancel":
                return

            ctx = omni.usd.get_context()
            sel = ctx.get_selection()
            paths = sel.get_selected_prim_paths()
            if not paths:
                return

            prim_path = str(paths[0])
            node_name = prim_path.split("/")[-1]  # ← 경로의 마지막 토큰만

            # 'mesh' 같은 토큰이면 한 단계 위 사용
            if node_name.lower() == "mesh" and "/" in prim_path:
                node_name = prim_path.rstrip("/").split("/")[-2]

            # 변화 없으면 스킵(불필요한 set/로그 억제)
            if not node_name or node_name == self._last_sel_name:
                return

            self._last_sel_name = node_name
            if self._node:
                self._node.set_value(node_name)
                print(f"[AMRControl] Viewport 선택 → Target Node = {node_name}")

        except Exception:
            pass

    # ───────── 입력 필드 활성/비활성 ─────────
    def _refresh_fields(self):
        cmd = self._current_command_label()
        if not (self._container_field and self._node_field and self._mission_field):
            return

        if cmd == "Move":
            self._container_field.read_only = True
            self._node_field.read_only = False
            self._mission_field.read_only = True
            self._container.set_value("")
            self._mission.set_value("")
        elif cmd == "Rack Move":
            self._container_field.read_only = False
            self._node_field.read_only = False
            self._mission_field.read_only = True
            self._mission.set_value("")
        elif cmd in ("Pause", "Resume"):
            self._container_field.read_only = True
            self._node_field.read_only = True
            self._mission_field.read_only = True
            self._container.set_value("")
            self._node.set_value("")
            self._mission.set_value("")
        elif cmd == "Cancel":
            # Cancel은 미션코드로만 취소: 노드/컨테이너 비활성화 및 초기화
            self._container_field.read_only = True
            self._node_field.read_only = True
            self._mission_field.read_only = False
            self._container.set_value("")
            self._node.set_value("")  # 남아있던 값 제거
            # 자동 채움
            self._autofill_mission_if_empty()

    def _current_command_label(self) -> str:
        if self._cmd_idx:
            try:
                i = self._cmd_idx.get_value_as_int()
                if 0 <= i < len(_COMMANDS):
                    return _COMMANDS[i]
            except Exception:
                pass
        return "Move"

    # ───────── 보조: 노드 코드 정규화 ─────────
    def _canon_node(self, s: str) -> str:
        """'.304D_STG' 같은 오타를 '_304D_STG'로 보정, 대문자/공백제거."""
        s = (s or "").strip().upper().replace(" ", "")
        if s.startswith("."):
            s = "_" + s[1:]
        return s

    # ───────── Dispatch ─────────
    def _on_dispatch(self):
        # AMR 선택값: 인덱스에서 직접 읽기
        amr_id = self._current_amr_value().strip()

        # Command/Type
        cmd_label = self._current_command_label()
        data_type = _DATATYPE_MAP.get(cmd_label, "ManualMove")

        # 입력값 취득
        cont = (self._container.as_string or "").strip()
        node_in = (self._node.as_string or "")
        node = self._canon_node(node_in)
        mission = (self._mission.as_string or "").strip()

        # Cancel은 자동 채움 시도(미션 비었을 때)
        if data_type == "MissionCancel" and not mission:
            auto = self._get_current_mission_code(amr_id)
            if auto:
                mission = auto
                self._mission.set_value(auto)
                print(f"[AMRControl] Auto-use cancelMissionCode from AMR {amr_id} → {auto}")

        # 사전 유효성 검사
        if data_type == "ManualMove" and not node:
            print("[AMRControl] Move에는 targetNodeCode가 필요합니다.")
            return
        if data_type == "ManualRackMove" and (not cont or not node):
            print("[AMRControl] Rack Move에는 containerCode와 targetNodeCode가 필요합니다.")
            return
        if data_type == "MissionCancel":
            # 미션코드만 허용
            if not mission:
                print("[AMRControl] Cancel은 미션 코드(cancelMissionCode)가 필수입니다. (해당 AMR에 활성 미션 없음)")
                return

        payload: Dict[str, Any] = {
            "dataType": data_type,
            "mapCode": self._map_code,
            "amrId": amr_id,
        }
        if data_type == "ManualMove":
            payload["targetNodeCode"] = node
        elif data_type == "ManualRackMove":
            payload["containerCode"] = cont
            payload["targetNodeCode"] = node
        elif data_type == "MissionCancel":
            payload["cancelMissionCode"] = mission

        # 타입별 허용 필드만 남기기 하이 ㅋ 
        ALLOW_BY_TYPE = {
            "ManualMove":     {"dataType", "mapCode", "amrId", "targetNodeCode"},
            "ManualRackMove": {"dataType", "mapCode", "amrId", "containerCode", "targetNodeCode"},
            "AMRPause":       {"dataType", "mapCode", "amrId"},
            "AMRResume":      {"dataType", "mapCode", "amrId"},
            "MissionCancel":  {"dataType", "mapCode", "amrId", "cancelMissionCode"},
        }

        allow = ALLOW_BY_TYPE.get(data_type, {"dataType", "mapCode", "amrId"})
        safe_payload = {k: v for k, v in payload.items() if k in allow and v not in ("", None, "-")}

        print(f"[AMRControl] dispatch: cmd={cmd_label}({data_type}), amrId={amr_id}")
        print("[AMRControl] payload →", safe_payload)
        if data_type == "MissionCancel" and "cancelMissionCode" not in safe_payload:
            print("[AMRControl][WARN] cancelMissionCode 누락으로 Cancel이 전송되지 않았습니다.")

        if self._client:
            try:
                self._client.post_digital_twin(dict(safe_payload))
            except Exception as e:
                print("[AMRControl] post_digital_twin failed:", e)

        self._close()

    # ───────── 이벤트 핸들러 ─────────
    def _on_amr_idx_changed(self, m):
        try:
            idx = m.get_value_as_int()
        except Exception:
            idx = self._index_of(self._current_amr_value())
        val = self._amr_ids[idx] if 0 <= idx < len(self._amr_ids) else "-"
        if (self._amr_id_str.as_string or "") != val:
            self._amr_id_str.set_value(val)
        print(f"[AMRControl] AMR changed: idx={idx}, val={val}")

        # Cancel 모드에서 AMR 바꾸면 미션코드 자동 갱신
        if self._current_command_label() == "Cancel":
            auto = self._get_current_mission_code(val)
            self._mission.set_value(auto or "")
            if auto:
                print(f"[AMRControl] Autofill cancelMissionCode for AMR {val} → {auto}")
            else:
                print(f"[AMRControl][WARN] No active missionCode for AMR {val}")

    def _on_cmd_idx_changed(self, m):
        try:
            idx = m.get_value_as_int()
        except Exception:
            idx = 0
        label = _COMMANDS[idx] if 0 <= idx < len(_COMMANDS) else "Move"
        print(f"[AMRControl] Command changed: idx={idx}, label={label}")
        self._refresh_fields()

    # ───────── Close ─────────
    def _close(self):
        try:
            if self._win:
                self._win.visible = False
        except Exception:
            pass

        # ▼ 폴링 구독 해제 (중복/누수 방지)
        try:
            if self._sel_poll and hasattr(self._sel_poll, "unsubscribe"):
                self._sel_poll.unsubscribe()
        except Exception:
            pass
        self._sel_poll = None
        self._last_sel_name = None
