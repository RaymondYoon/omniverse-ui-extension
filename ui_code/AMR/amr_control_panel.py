# ui_code/AMR/amr_control_panel.py
from typing import Optional, Iterable, Dict, Any, List
import re
import omni.ui as ui
from ui_code.ui.utils.common import _fill


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
        map_code: str = "RR_Floor",
        set_selection_passthrough=None,
    ):
        self._client = client
        self._map_code = map_code
        self._set_selection_passthrough = set_selection_passthrough or (lambda *_: None)

        self._win: Optional[ui.Window] = None

        # ▼ AMR 콤보: 화면은 IntModel로 움직이되, 실제 값은 StringModel로 유지
        self._amr_ids: List[str] = ["-"]
        self._amr_idx = ui.SimpleIntModel(0)           # 뷰 인덱스(선택)
        self._amr_id_str = ui.SimpleStringModel("-")   # 실제 전송에 쓰는 값
        self._amr_combo_frame: Optional[ui.Frame] = None
        self._amr_idx.add_value_changed_fn(lambda m: self._sync_selected_string())

        # 명령 & 파라미터
        self._cmd_idx = ui.SimpleIntModel(0)
        self._container = ui.SimpleStringModel("")
        self._node = ui.SimpleStringModel("")
        self._mission = ui.SimpleStringModel("")

        self._row_container: Optional[ui.Frame] = None
        self._row_node: Optional[ui.Frame] = None
        self._row_mission: Optional[ui.Frame] = None
        self._container_field: Optional[ui.StringField] = None
        self._node_field: Optional[ui.StringField] = None
        self._mission_field: Optional[ui.StringField] = None

        self._cmd_idx.add_value_changed_fn(lambda m: self._refresh_fields())

    # ───────── 외부 주입 ─────────
    def set_client(self, client): self._client = client
    def get_client(self): return self._client

    # ───────── AMR 리스트 갱신 (AMRInfo 수신마다 호출) ─────────
    def update_amr_list(self, items: Iterable[Dict[str, Any]] | Dict[str, Dict[str, Any]]):
        # 1) 수신 → id 추출
        src = (items.values() if isinstance(items, dict) else (items or []))
        ids: List[str] = []
        for it in src:
            it = it or {}
            rid = str(it.get("robotId") or it.get("amrId") or it.get("id") or "").strip()
            if rid:
                ids.append(rid)
        ids = _numeric_sort(ids) or ["-"]

        # 이전 선택(문자열) 보존
        prev_id = (self._amr_id_str.as_string or "-").strip()

        # 2) 옵션이 바뀐 경우에만 콤보 재구성(매 틱 재생성 금지)
        if ids != self._amr_ids:
            self._amr_ids = ids
            if self._amr_combo_frame:
                self._amr_combo_frame.clear()
                with self._amr_combo_frame:
                    ui.ComboBox(
                        self._index_of(prev_id),   # 보이는 초기값
                        *self._amr_ids,
                        model=self._amr_idx,
                        width=_fill(),
                    )

        # 3) 콤보 인덱스를 값(prev_id)에 맞춰 보정 + 문자열 모델 동기화
        idx = self._index_of(prev_id)
        if self._amr_idx.get_value_as_int() != idx:
            self._amr_idx.set_value(idx)
        self._sync_selected_string()

    def _index_of(self, rid: Optional[str]) -> int:
        if rid and rid in self._amr_ids:
            return self._amr_ids.index(rid)
        return 0

    def _sync_selected_string(self):
        idx = self._amr_idx.get_value_as_int()
        val = self._amr_ids[idx] if 0 <= idx < len(self._amr_ids) else "-"
        if (self._amr_id_str.as_string or "") != val:
            self._amr_id_str.set_value(val)

    # ───────── 표시 ─────────
    def show(self, amr_id: Optional[str] = None):
        # 외부에서 특정 AMR으로 열기를 원하면 반영
        if amr_id:
            want_idx = self._index_of(str(amr_id))
            self._amr_idx.set_value(want_idx)
            self._sync_selected_string()

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
                        ui.ComboBox(
                            self._amr_idx.get_value_as_int(),
                            *self._amr_ids,
                            model=self._amr_idx,
                            width=_fill(),
                        )

                # Command
                with ui.HStack():
                    ui.Label("Command:", width=100, style={"color": 0xFFFFFFFF})
                    ui.ComboBox(0, *_COMMANDS, model=self._cmd_idx, width=_fill())

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

    # ───────── 입력 필드 활성/비활성 ─────────
    def _refresh_fields(self):
        cmd = _COMMANDS[self._cmd_idx.get_value_as_int()]
        if not (self._container_field and self._node_field and self._mission_field):
            return

        if cmd == "Move":
            self._container_field.read_only = True
            self._node_field.read_only = False
            self._mission_field.read_only = True
        elif cmd == "Rack Move":
            self._container_field.read_only = False
            self._node_field.read_only = False
            self._mission_field.read_only = True
        elif cmd in ("Pause", "Resume"):
            self._container_field.read_only = True
            self._node_field.read_only = True
            self._mission_field.read_only = True
        else:  # Cancel
            self._container_field.read_only = True
            self._node_field.read_only = True
            self._mission_field.read_only = False

    # ───────── 보조: 노드 코드 정규화 ─────────
    def _canon_node(self, s: str) -> str:
        """'.304D_STG' 같은 오타를 '_304D_STG'로 보정, 대문자/공백제거."""
        s = (s or "").strip().upper().replace(" ", "")
        if s.startswith("."):
            s = "_" + s[1:]
        # 필요 시 더 강한 검증: re.fullmatch(r"[A-Z0-9_]+", s)
        return s

    # ───────── Dispatch ─────────
    def _on_dispatch(self):
        amr_id = (self._amr_id_str.as_string or "").strip()  # ★ 드롭다운의 "실제 값" 사용
        cmd = _COMMANDS[self._cmd_idx.get_value_as_int()]
        data_type = _DATATYPE_MAP.get(cmd, "ManualMove")

        payload: Dict[str, Any] = {
            "dataType": data_type,
            "mapCode": self._map_code,
            "amrId": amr_id,
        }

        cont = (self._container.as_string or "").strip()
        node_in = (self._node.as_string or "")
        node = self._canon_node(node_in)
        mission = (self._mission.as_string or "").strip()

        if data_type == "ManualMove":
            if node:
                payload["targetNodeCode"] = node

        elif data_type == "ManualRackMove":
            if cont:
                payload["containerCode"] = cont
            if node:
                payload["targetNodeCode"] = node

        elif data_type == "MissionCancel":
            if mission:
                payload["cancelMissionCode"] = mission

        # Pause/Resume 은 여분 필드 금지

        print("[AMRControl] payload →", payload)

        if self._client:
            try:
                self._client.post_digital_twin(payload)
            except Exception as e:
                print("[AMRControl] post_digital_twin failed:", e)

        self._close()

    def _close(self):
        try:
            if self._win:
                self._win.visible = False
        except Exception:
            pass
