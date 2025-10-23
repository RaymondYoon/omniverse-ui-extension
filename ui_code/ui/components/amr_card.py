from typing import Callable, Optional, Dict, Any
import omni.ui as ui
from ui_code.ui.utils.common import _fill, ASSET_DIR, _fmt_status, _fmt_lift


class AmrCard:
    def __init__(self, parent_vstack: ui.VStack, amr_id: str, on_plus: Optional[Callable] = None):
        self.amr_id = str(amr_id)
        self._on_plus = on_plus

        self.m_status = ui.SimpleStringModel("-")
        self.m_lift   = ui.SimpleStringModel("-")
        self.m_rack   = ui.SimpleStringModel("-")
        self.m_wtype  = ui.SimpleStringModel("-")
        # 배터리(0~1)
        self.m_batt   = ui.SimpleFloatModel(0.0, min=0.0, max=1.0)

        with parent_vstack:
            self._root = ui.Frame(style={"background_color": 0x00000080}, height=120, width=_fill())
        with self._root:
            with ui.VStack(spacing=6, padding=8, width=_fill()):
                # ── 헤더 ──
                with ui.HStack(width=_fill(), height=24):
                    ui.Label(
                        f"AMR ID : {self.amr_id}",
                        style={"font_size": 14, "color": 0xFFFFFFFF},
                        width=_fill()
                    )
                    ui.Button("+", width=14, height=12, style={"color": 0xFFFFFFFF},
                              clicked_fn=self._handle_plus)

                # ── 본문 ──
                with ui.HStack(spacing=10, width=_fill()):
                    # 썸네일
                    with ui.Frame(width=60, height=40, style={"background_color": 0x222222FF}):
                        try:
                            candidates = [ASSET_DIR / "amr.PNG"]
                            img_path = next((p for p in candidates if p.exists()), None)
                            if img_path:
                                ui.Image(
                                    img_path.as_posix(),
                                    width=_fill(),
                                    height=_fill(),
                                    fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT
                                )
                            else:
                                ui.Label("IMG", alignment=ui.Alignment.CENTER, style={"color": 0xFFFFFFFF})
                        except Exception:
                            ui.Label("IMG", alignment=ui.Alignment.CENTER, style={"color": 0xFFFFFFFF})

                    # 키-값 영역
                    with ui.VStack(spacing=1, width=_fill()):
                        self._kv("Status :",      self.m_status, font_size=8)
                        self._kv("Lift Status :", self.m_lift,   font_size=8)
                        self._kv("Rack :",        self.m_rack,   font_size=8)
                        self._kv("Working Type :",self.m_wtype,  font_size=8)

                # ── 배터리 바 (커스텀: 두께/텍스트 완전 제어) ──
                # 높이는 여기의 height로 정확히 반영됨
                with ui.ZStack(width=_fill(), height=2):
                    # 트랙(배경)
                    ui.Rectangle(width=_fill(), height=_fill(),
                                 style={"background_color": 0x803C3C3C})

                    # 채워지는 바
                    with ui.HStack(width=_fill(), height=_fill()):
                        self._batt_fill = ui.Rectangle(
                            height=_fill(),
                            width=ui.Percent(0),
                            style={"background_color": 0x80800000}  # 초기색(>=70% 가정)
                        )
                        ui.Spacer(width=_fill())

                    # 텍스트(우측 정렬, 소수 0자리 = 정수부만)
                    with ui.HStack(width=_fill(), height=_fill()):
                        ui.Spacer(width=_fill())
                        self._batt_text = ui.Label(
                            "0",
                            style={"color": 0xFFFFFFFF, "font_size": 10}
                        )

                # 값 변경 시 색/폭/텍스트 동기화 + 초기 1회
                self.m_batt.add_value_changed_fn(self._on_batt_changed)
                self._on_batt_changed()

    # ───────────────────────── helpers ─────────────────────────
    def _fmt_ratio_int(self, v: float) -> str:
    # 0~1 → 0~100 정수(반올림). % 기호는 붙이지 않음.
        v = max(0.0, min(1.0, float(v)))
        return str(int(round(v * 100.0)))

    def _sync_batt_color_and_fill(self):
        # 색상: <20% 빨강, 20~70% 주황, ≥70% 파랑(기존 상수 유지)
        try:
            v = float(self.m_batt.as_float)
        except Exception:
            v = 0.0
        v = max(0.0, min(1.0, v))

        if   v >= 0.70: col = 0x80800000  # BLUE (ABGR 주석 그대로 유지)
        elif v >= 0.20: col = 0xFF00AAFF  # ORANGE
        else:           col = 0xFF0000FF  # RED

        try:
            self._batt_fill.set_style({"background_color": col})
        except Exception:
            self._batt_fill.style = {"background_color": col}

        try:
            self._batt_fill.width = ui.Percent(int(v * 100))
        except Exception:
            pass

    def _sync_batt_text(self):
        try:
            v = float(self.m_batt.as_float)
        except Exception:
            v = 0.0
        v = max(0.0, min(1.0, v))
        self._batt_text.text = self._fmt_ratio_int(v)

    def _on_batt_changed(self, *_):
        self._sync_batt_color_and_fill()
        self._sync_batt_text()

    def _handle_plus(self):
        try:
            if self._on_plus:
                self._on_plus(self.amr_id)
        except Exception as e:
            print("[AmrCard] on_plus failed:", e)

    def _kv(self, key, model, font_size=12):
        with ui.HStack(width=_fill()):
            ui.Label(key, width=_fill(), style={"color": 0xFFFFFFFF, "font_size": font_size})
            ui.StringField(model=model, read_only=True,
                           style={"color": 0xFFFFFFFF, "font_size": font_size},
                           width=_fill())

    # ───────────────────────── public ──────────────────────────
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

        batt = g("batteryLevel") or 0
        try:
            batt = float(batt)
        except Exception:
            batt = 0.0
        if batt > 1.0:  # 0~100 → 0~1 보정
            batt /= 100.0
        batt = max(0.0, min(1.0, batt))
        self.m_batt.set_value(batt)  # 콜백 통해 색/폭/텍스트 동기화

    def destroy(self):
        try:
            self._root.destroy()
        except Exception:
            self._root.visible = False
