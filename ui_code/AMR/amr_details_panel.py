from typing import Optional, Dict, Any
import omni.ui as ui
from omni.ui import dock_window_in_window, DockPosition

from ui_code.ui.utils.common import _fill, ASSET_DIR, _fmt_status, _fmt_lift

# ABGR 색상
_COL_TEXT    = 0xFFFFFFFF
_COL_TRACK   = 0x803C3C3C
_COL_GREEN   = 0xFF00FF00
_COL_ORANGE  = 0xFF00AAFF
_COL_RED     = 0xFF0000FF

# 상태 점(working / waiting / charging)
_COL_DOT_WORKING  = 0xFF00AAFF
_COL_DOT_WAITING  = 0xFFFF7B00
_COL_DOT_CHARGING = 0xFF66CC00


class AMRPanel:
    TITLE = "AMR Details"

    def __init__(self):
        self._win: Optional[ui.Window] = None

        # 표시 모델
        self._selected_id   = ui.SimpleStringModel("-")
        self._m_status      = ui.SimpleStringModel("-")
        self._m_lift        = ui.SimpleStringModel("-")
        self._m_rack        = ui.SimpleStringModel("-")
        self._m_mission     = ui.SimpleStringModel("-")
        self._m_node        = ui.SimpleStringModel("-")
        self._m_pos         = ui.SimpleStringModel("-")
        self._m_batt        = ui.SimpleFloatModel(0.0)

        # 위젯 참조
        self._bbar: Optional[ui.ProgressBar] = None
        self._status_dot: Optional[ui.Label] = None

    # UI
    def show(self, amr_id: Optional[str] = None):
        if amr_id:
            self._selected_id.set_value(str(amr_id))

        if self._win:
            self._win.visible = True
            return

        self._win = ui.Window(
            self.TITLE,
            width=340,
            height=460,
            style={"background_color": 0x000000A0},
        )

        with self._win.frame:
            with ui.VStack(spacing=10, padding=10, width=_fill()):
                ui.Label("AMR Details", style={"font_size": 18, "color": _COL_TEXT})

                # 상단: ID + 상태 + 썸네일
                with ui.HStack(spacing=10, width=_fill(), height=90):
                    with ui.VStack(width=_fill()):
                        with ui.HStack(width=_fill()):
                            ui.Label("AMR ID :", width=70, style={"color": _COL_TEXT})
                            ui.StringField(model=self._selected_id, read_only=True,
                                           style={"color": _COL_TEXT}, width=_fill())
                        with ui.HStack(spacing=6, width=_fill()):
                            self._status_dot = ui.Label("●", width=14,
                                                        style={"color": _COL_DOT_WAITING, "font_size": 16})
                            ui.StringField(model=self._m_status, read_only=True,
                                           style={"color": _COL_TEXT}, width=_fill())
                    with ui.Frame(width=120, height=90, style={"background_color": 0x222222FF}):
                        try:
                            candidates = [
                                ASSET_DIR / "AMR.PNG",
                            ]
                            img_path = next((p for p in candidates if p.exists()), None)
                            if img_path:
                                ui.Image(img_path.as_posix(), width=_fill(), height=_fill(),
                                         fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT)
                            else:
                                ui.Label("IMG", alignment=ui.Alignment.CENTER, style={"color": _COL_TEXT})
                        except Exception:
                            ui.Label("IMG", alignment=ui.Alignment.CENTER, style={"color": _COL_TEXT})

                # 배터리 바
                self._bbar = ui.ProgressBar(model=self._m_batt, height=16, width=_fill())
                self._sync_batt_color()
                self._m_batt.add_value_changed_fn(lambda *_: self._sync_batt_color())

                ui.Separator()

                # 정보 라인
                self._kv("Lift Status :",  self._m_lift)
                self._kv("Rack :",         self._m_rack)
                self._kv("Mission :",      self._m_mission)
                self._kv("Node Code :",    self._m_node)
                self._kv("Position :",     self._m_pos)

        # 오른쪽 도킹
        try:
            dock_window_in_window(self.TITLE, "Viewport", DockPosition.RIGHT, 0.28)
        except Exception:
            pass
        self._win.visible = True

    def _kv(self, key: str, model: ui.SimpleStringModel):
        with ui.HStack(width=_fill()):
            ui.Label(key, width=90, style={"color": _COL_TEXT})
            ui.StringField(model=model, read_only=True, style={"color": _COL_TEXT}, width=_fill())

    def _sync_batt_color(self):
        if not self._bbar:
            return
        v = float(self._m_batt.as_float)
        if   v >= 0.70: col = _COL_GREEN
        elif v >= 0.20: col = _COL_ORANGE
        else:           col = _COL_RED

        for key in ("secondary_color", "bar_color", "color"):
            try:
                st = dict(getattr(self._bbar, "style", {}))
                st[key] = col
                # st["background_color"] = _COL_TRACK  # 필요하면 트랙도
                self._bbar.style = st
                break
            except Exception:
                continue

    def _sync_status_dot(self, status_text: str):
        if not self._status_dot:
            return
        s = (status_text or "").lower()
        if "charg" in s:
            col = _COL_DOT_CHARGING
        elif "idle" in s or "wait" in s:
            col = _COL_DOT_WAITING
        else:
            col = _COL_DOT_WORKING
        try:
            self._status_dot.style = {"color": col, "font_size": 16}
        except Exception:
            pass

    # 데이터 반영
    def update(self, data: Dict[str, Any]):
        def g(*keys, default=None):
            for k in keys:
                if k in data and data[k] is not None:
                    return data[k]
            return default

        rid = g("robotId", "amrId", "id", "name")
        if rid:
            self._selected_id.set_value(str(rid))

        status_fmt = _fmt_status(g("status", "robotStatus", "state"))
        lift_fmt   = _fmt_lift(g("liftStatus", "lift_state"))
        self._m_status.set_value(status_fmt)
        self._m_lift.set_value(lift_fmt)
        self._sync_status_dot(status_fmt)

        self._m_rack.set_value(str(g("containerCode", "palletCode", "container", "rack") or "-"))
        self._m_mission.set_value(str(g("missionCode", "workingType", "missionType", "mission") or "-"))
        self._m_node.set_value(str(g("nodeCode") or "-"))

        x = g("x"); y = g("y"); th = g("robotOrientation", "theta", "yaw")
        if x is None or y is None:
            self._m_pos.set_value("-")
        else:
            try:
                self._m_pos.set_value(
                    f"({float(x):.2f}, {float(y):.2f})  θ={float(th):.1f}°" if th is not None
                    else f"({float(x):.2f}, {float(y):.2f})"
                )
            except Exception:
                self._m_pos.set_value(f"({x}, {y})")

        batt = g("batteryLevel", "battery", "batteryPercent") or 0
        try:
            batt = float(batt)
        except Exception:
            batt = 0.0
        if batt > 1.0:
            batt /= 100.0
        self._m_batt.set_value(max(0.0, min(1.0, batt)))
        self._sync_batt_color()

    # 선택만 바꾸고 열기
    def set_selected_id(self, amr_id: str):
        self._selected_id.set_value(str(amr_id))
        if self._win:
            self._win.visible = True

    # (옵션) 외부에서 현재 선택 ID 읽을 때 사용
    def get_selected_id(self) -> str:
        return self._selected_id.as_string
