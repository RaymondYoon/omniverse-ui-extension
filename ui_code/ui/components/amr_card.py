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
        # ProgressBar 기본 범위(0~1). 명시적으로 min/max 지정
        self.m_batt   = ui.SimpleFloatModel(0.0, min=0.0, max=1.0)

        with parent_vstack:
            self._root = ui.Frame(style={"background_color": 0x00000080}, height=170, width=_fill())
        with self._root:
            with ui.VStack(spacing=6, padding=8, width=_fill()):
                # 헤더
                with ui.HStack(width=_fill(), height=24):
                    ui.Label(f"AMR ID : {self.amr_id}",
                             style={"font_size": 18, "color": 0xFFFFFFFF},
                             width=_fill())
                    ui.Button("+", width=24, height=22, style={"color": 0xFFFFFFFF},
                              clicked_fn=self._handle_plus)

                # 본문
                with ui.HStack(spacing=10, width=_fill()):
                    with ui.Frame(width=120, height=90, style={"background_color": 0x222222FF}):
                        try:
                            candidates = [ASSET_DIR / "amr.png", ASSET_DIR / "amr.PNG",
                                          ASSET_DIR / "AMR.png", ASSET_DIR / "AMR.PNG"]
                            img_path = next((p for p in candidates if p.exists()), None)
                            if img_path:
                                ui.Image(img_path.as_posix(), width=_fill(), height=_fill(),
                                         fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT)
                            else:
                                ui.Label("IMG", alignment=ui.Alignment.CENTER, style={"color": 0xFFFFFFFF})
                        except Exception:
                            ui.Label("IMG", alignment=ui.Alignment.CENTER, style={"color": 0xFFFFFFFF})

                    with ui.VStack(spacing=4, width=_fill()):
                        self._kv("Status :",      self.m_status)
                        self._kv("Lift Status :", self.m_lift)
                        self._kv("Rack :",        self.m_rack)
                        self._kv("Working Type :",self.m_wtype)

                # ── 배터리 바 ──
                # 문서처럼 set_style 사용. 트랙(배경) 색도 살짝 어둡게.
                self._bbar = ui.ProgressBar(model=self.m_batt, width=_fill(), height=26)
                self._apply_progress_style({"background_color": 0x803C3C3C})

                # 값 바뀌면 색 갱신 + 초기 1회 적용
                self.m_batt.add_value_changed_fn(lambda *_: self._sync_batt_color())
                self._sync_batt_color()

    # 진행바 색: <20% 빨강, 20~70% 주황, ≥70% 초록 (ABGR)
    def _sync_batt_color(self):
        v = float(self.m_batt.as_float)
        RED     = 0xFF0000FF  # R=FF
        ORANGE  = 0xFF00AAFF  # R=FF, G=AA
        GREEN   = 0xFF00FF00  # G=FF

        if   v >= 0.70: color = GREEN
        elif v >= 0.20: color = ORANGE
        else:            color = RED

        # 문서 방식 → 폴백 순서대로 적용
        self._apply_progress_style({"color": color})

    def _apply_progress_style(self, base: dict):
        """Kit 버전별 스타일 키 차이에 대비해 안전하게 적용."""
        # 1) 공식 문서 방식
        try:
            self._bbar.set_style(base)
            return
        except Exception:
            pass
        # 2) 대체 키 시도
        for k in ("secondary_color", "bar_color", "color"):
            try:
                st = dict(getattr(self._bbar, "style", {}))
                st.update(base)
                # color 키가 없으면 대체 키로 넣어줌
                if "color" not in base:
                    st[k] = base.get(k, base.get("color"))
                self._bbar.style = st
                return
            except Exception:
                continue

    def _handle_plus(self):
        try:
            if self._on_plus:
                self._on_plus(self.amr_id)
        except Exception as e:
            print("[AmrCard] on_plus failed:", e)

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
            batt /= 100.0
        batt = max(0.0, min(1.0, batt))
        self.m_batt.set_value(batt)

        # 같은 값으로 반복 업데이트될 때를 대비해 한 번 더 색 적용
        self._sync_batt_color()

    def destroy(self):
        try:
            self._root.destroy()
        except Exception:
            self._root.visible = False
