from typing import Callable, Optional, Dict, Any
import omni.ui as ui

from ui_code.ui.utils.common import _fill, ASSET_DIR, _fmt_status, _fmt_lift  # 절대 임포트

class AmrCard:
    def __init__(self, parent_vstack: ui.VStack, amr_id: str, on_plus: Optional[Callable]=None):
        self.amr_id = str(amr_id)
        self.m_status = ui.SimpleStringModel("-")
        self.m_lift   = ui.SimpleStringModel("-")
        self.m_rack   = ui.SimpleStringModel("-")
        self.m_wtype  = ui.SimpleStringModel("-")
        self.m_batt   = ui.SimpleFloatModel(0.0)

        with parent_vstack:
            self._root = ui.Frame(style={"background_color": 0x00000080}, height=170, width=_fill())
        with self._root:
            with ui.VStack(spacing=6, padding=8, width=_fill()):
                with ui.HStack(width=_fill(), height=24):
                    ui.Label(f"AMR ID : {self.amr_id}", style={"font_size": 18, "color": 0xFFFFFFFF}, width=_fill())
                    ui.Button("+", width=24, height=22, style={"color": 0xFFFFFFFF},
                              clicked_fn=(on_plus or (lambda: None)))
                with ui.HStack(spacing=10, width=_fill()):
                    with ui.Frame(width=120, height=90, style={"background_color": 0x222222FF}):
                        try:
                            candidates = [
                                ASSET_DIR / "amr.png",
                                ASSET_DIR / "amr.PNG",
                                ASSET_DIR / "AMR.png",
                                ASSET_DIR / "AMR.PNG",
                            ]
                            img_path = next((p for p in candidates if p.exists()), None)
                            if img_path:
                                ui.Image(img_path.as_posix(),
                                         width=_fill(), height=_fill(),
                                         fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT)
                            else:
                                ui.Label("IMG", alignment=ui.Alignment.CENTER, style={"color": 0xFFFFFFFF})
                        except Exception:
                            ui.Label("IMG", alignment=ui.Alignment.CENTER, style={"color": 0xFFFFFFFF})

                    with ui.VStack(spacing=4, width=_fill()):
                        self._kv("Status :",       self.m_status)
                        self._kv("Lift Status :",  self.m_lift)
                        self._kv("Rack :",         self.m_rack)
                        self._kv("Working Type :", self.m_wtype)
                ui.ProgressBar(model=self.m_batt)

    def _kv(self, key, model):
        with ui.HStack(width=_fill()):
            ui.Label(key, width=120, style={"color": 0xFFFFFFFF})
            ui.StringField(model=model, read_only=True, style={"color": 0xFFFFFFFF}, width=_fill())

    def update(self, src: Dict[str, Any]):
        def g(*keys, default=None):
            for k in keys:
                if k in src and src[k] is not None:
                    return src[k]
            return default

        self.m_status.set_value(_fmt_status(g("status", "robotStatus", "state")))
        self.m_lift.set_value(_fmt_lift(g("liftStatus", "lift_state")))
        self.m_rack.set_value(str(g("containerCode", "palletCode", "container", "rack") or "-"))

        w = g("workingType", "missionType", "mission") or g("missionCode")
        if not w:
            w = "Waiting" if bool(g("isWaiting")) else "-"
        self.m_wtype.set_value(str(w))

        batt = g("batteryLevel", "battery", "batteryPercent") or 0
        try:
            batt = float(batt)
        except Exception:
            batt = 0.0
        if batt > 1.0:
            batt = batt / 100.0
        self.m_batt.set_value(max(0.0, min(1.0, batt)))

    def destroy(self):
        try:
            self._root.destroy()
        except Exception:
            self._root.visible = False
