# ui_code/ui/panels/mission_panel.py
import omni.ui as ui

_ROW_STYLE = {"background_color": 0x00000000}
_TXT = {"color": 0xFFFFFFFF}
_TXT_DIM = {"color": 0xFFCCCCCC}
_COL_WORK = 0xFFFFAA00     # Working
_COL_WAIT = 0xFF007BFF     # Waiting
_COL_RESV = 0xFF00CC66     # Reservation


class MissionPanel:
    """
    Unity의 MissionListPopupData + MissionContentData UI를 Omniverse로 포팅.
    - resolver() 가 {"working":[...], "waiting":[...], "reserved":[...]} 를 반환
      각 row: {"missionStatus","process","missionCode","amrId","targetNode"}
    - Cancel 버튼은 on_cancel(mission_code=..., node_code=...) 콜백 호출
    - Reset All 버튼은 on_reset_all() 콜백 호출
    """
    def __init__(self, resolver=None, on_cancel=None, on_reset_all=None):
        self._win = None
        self._resolver = resolver
        self._on_cancel = on_cancel
        self._on_reset_all = on_reset_all

        self._lbl_total = None
        self._lbl_work  = None
        self._lbl_wait  = None
        self._lbl_resv  = None

        self._v_work = None
        self._v_wait = None
        self._v_resv = None

        # 현재 렌더된 행(키→Frame)
        self._rows_work = {}
        self._rows_wait = {}
        self._rows_resv = {}

    def set_data_resolver(self, resolver):
        self._resolver = resolver

    def set_cancel_callback(self, on_cancel):
        self._on_cancel = on_cancel

    def set_reset_all_callback(self, on_reset_all):
        self._on_reset_all = on_reset_all

    def show(self):
        if self._win:
            self._win.visible = True
            return

        self._win = ui.Window("Mission List", width=420, height=560,
                              style={"background_color": 0x000000A0})

        with self._win.frame:
            with ui.VStack(spacing=8, padding=10):
                # 헤더 + Reset
                with ui.HStack():
                    ui.Label("Mission List", style={"font_size": 18, "color": 0xFFFFFFFF})
                    ui.Spacer()
                    ui.Button("Reset All", clicked_fn=self._on_click_reset_all)

                with ui.HStack(spacing=10):
                    self._lbl_total = ui.Label("Total: 0", style=_TXT)
                    self._lbl_work  = ui.Label("Working: 0", style={"color": _COL_WORK})
                    self._lbl_wait  = ui.Label("Waiting: 0", style={"color": _COL_WAIT})
                    self._lbl_resv  = ui.Label("Reserved: 0", style=_TXT)

                ui.Separator()

                # Working
                ui.Label("Working", style={"font_size": 16, "color": _COL_WORK})
                with ui.VStack(spacing=4) as v:
                    self._v_work = v

                ui.Separator()

                # Waiting
                ui.Label("Waiting", style={"font_size": 16, "color": _COL_WAIT})
                with ui.VStack(spacing=4) as v:
                    self._v_wait = v

                ui.Separator()

                # Reservation
                ui.Label("Reservation", style={"font_size": 16, "color": _COL_RESV})
                with ui.VStack(spacing=4) as v:
                    self._v_resv = v

        self.refresh()

    def refresh(self):
        if not self._resolver:
            return
        snap = self._resolver() or {}
        self.update_data(
            working=list(snap.get("working") or []),
            waiting=list(snap.get("waiting") or []),
            reserved=list(snap.get("reserved") or []),
        )

    # ---------- 내부 ----------
    def _make_key(self, row):
        # Unity와 동일: 예약은 process, 그 외는 missionCode로 식별
        status = (row.get("missionStatus") or "").lower()
        if status == "reservation":
            return ("R", row.get("process") or "")
        return ("M", row.get("missionCode") or "")

    def _render_row(self, parent, row, color):
        f = ui.Frame(style=_ROW_STYLE)
        with f:
            with ui.HStack(spacing=6):
                lbl_status = ui.Label(_t(row.get("missionStatus")), style={"color": color}, width=90)
                lbl_proc   = ui.Label(_t(row.get("process")),      style=_TXT,      width=120)
                lbl_code   = ui.Label(_t(row.get("missionCode")),  style=_TXT,      width=180)
                lbl_amr    = ui.Label(_t(row.get("amrId")),        style=_TXT_DIM,  width=80)
                lbl_tgt    = ui.Label(_t(row.get("targetNode")),   style=_TXT_DIM,  width=120)
                ui.Spacer()
                ui.Button("Cancel", width=70, clicked_fn=lambda r=row: self._on_click_cancel(r))
        parent.add_child(f)
        # 라벨 핸들을 함께 보관해서 이후에 값만 갱신
        return {
            "frame": f,
            "labels": {
                "missionStatus": lbl_status,
                "process": lbl_proc,
                "missionCode": lbl_code,
                "amrId": lbl_amr,
                "targetNode": lbl_tgt,
            },
        }

    def _sync_section(self, vstack, current_rows: dict, desired_rows: list, color):
        desired_keys = []
        for row in desired_rows:
            k = self._make_key(row)
            desired_keys.append(k)
            if k not in current_rows:
                current_rows[k] = self._render_row(vstack, row, color)
            else:
                self._update_row(current_rows[k], row, color)

        # 제거
        for k in list(current_rows.keys()):
            if k not in desired_keys:
                try:
                    current_rows[k]["frame"].destroy()
                except Exception:
                    pass
                current_rows.pop(k, None)

    def update_data(self, *, working, waiting, reserved):
        total = len(working) + len(waiting) + len(reserved)
        if self._lbl_total: self._lbl_total.text = f"Total: {total}"
        if self._lbl_work:  self._lbl_work.text  = f"Working: {len(working)}"
        if self._lbl_wait:  self._lbl_wait.text  = f"Waiting: {len(waiting)}"
        if self._lbl_resv:  self._lbl_resv.text  = f"Reserved: {len(reserved)}"

        if self._v_work:
            self._sync_section(self._v_work, self._rows_work, working, _COL_WORK)
        if self._v_wait:
            self._sync_section(self._v_wait, self._rows_wait, waiting, _COL_WAIT)
        if self._v_resv:
            self._sync_section(self._v_resv, self._rows_resv, reserved, _COL_RESV)

    # ---------- 버튼 ----------
    def _on_click_cancel(self, row):
        if not self._on_cancel:
            return
        status = (row.get("missionStatus") or "").lower()
        if status == "reservation":
            self._on_cancel(node_code=row.get("process"))
        else:
            code = row.get("missionCode")
            if code:
                self._on_cancel(mission_code=code)

    def _on_click_reset_all(self):
        if self._on_reset_all:
            self._on_reset_all()

    def _update_row(self, row_widgets, row, color):
        lbls = row_widgets["labels"]
        lbls["missionStatus"].text = _t(row.get("missionStatus"))
        lbls["process"].text       = _t(row.get("process"))
        lbls["missionCode"].text   = _t(row.get("missionCode"))
        lbls["amrId"].text         = _t(row.get("amrId"))
        lbls["targetNode"].text    = _t(row.get("targetNode"))


# --- helpers (module level) ---
def _t(v):
    """Unity와 동일: 빈 문자열/None만 '-' 로, 그 외(0 포함)는 그대로."""
    if v is None:
        return "-"
    s = str(v)
    return "-" if s == "" else s
