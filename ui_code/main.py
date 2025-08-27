# main.py — UI 전용 (IExt 상속 금지, ErrorLog FIFO 로직 포함)
import time
from pathlib import Path

import omni.ui as ui
from omni.ui import dock_window_in_window, DockPosition
import omni.usd

# (선택) 외부 패널이 없을 수 있으니 안전 가드
try:
    from ui_code.Container.container_panel import ContainerPanel
except Exception:

    class ContainerPanel:
        def show(self):
            print("[platformcode] ContainerPanel not available")


try:
    from ui_code.Mission.mission_panel import MissionPanel
except Exception:

    class MissionPanel:
        def show(self):
            print("[platformcode] MissionPanel not available")


def _fill():
    """부모 폭/높이를 채우는 헬퍼(글자 잘림 방지)."""
    return ui.Fraction(1)

ASSET_DIR = Path(__file__).resolve().parents[1] / "resource"


def _file_uri(p: Path) -> str:
    posix = p.resolve().as_posix()
    return f"file:///{posix}" if ":" in posix[:10] else f"file://{posix}"

# --- helper: AMR status / lift formatting --------------------
_STATUS_MAP = {
    1: "EXIT",
    2: "OFFLINE",
    3: "IDLE",
    4: "INTASK",
    5: "CHARGING",
    6: "UPDATING",
    7: "EXCEPTION",
}
def _fmt_status(v):
    if isinstance(v, (int, float)):
        return _STATUS_MAP.get(int(v), str(int(v)))
    s = (str(v) if v is not None else "-").strip()
    if s.isdigit():
        return _STATUS_MAP.get(int(s), s)
    return s.upper() if s else "-"

def _fmt_lift(v):
    return "Up" if v is True or v == 1 else "Down" if v is False or v == 0 else "-"


# --- AMR 카드 컴포넌트 ---------------------------------------------------------
class AmrCard:
    def __init__(self, parent_vstack: ui.VStack, amr_id: str, on_plus=None):
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
                    ui.Button("+", width=24, height=22, style={"color": 0xFFFFFFFF}, clicked_fn=(on_plus or (lambda: None)))
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
                                # 핵심 1) file:// 대신 순수 경로
                                # 핵심 2) name= 키워드 대신 위치 인자(첫 번째 인자)
                                ui.Image(
                                    img_path.as_posix(),
                                    width=_fill(),
                                    height=_fill(),
                                    fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                )
                                print(f"[AMR Image] Using path {img_path.as_posix()}")
                            else:
                                ui.Label("IMG", alignment=ui.Alignment.CENTER, style={"color": 0xFFFFFFFF})
                                print(f"[AMR Image] Not found. Looked under: {ASSET_DIR}")
                        except Exception as e:
                            ui.Label("IMG", alignment=ui.Alignment.CENTER, style={"color": 0xFFFFFFFF})
                            print(f"[AMR Image] Error: {e}")

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

    def update(self, src: dict):
        def g(*keys, default=None):
            for k in keys:
                if k in src and src[k] is not None:
                    return src[k]
            return default

        # 서버 필드 우선 + 보기 좋게 포맷팅
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


class UiLayoutBase:
    # ───────────────────────── helpers ─────────────────────────
    def _kill_window(self, title: str):
        """같은 제목 창이 이미 있으면 제거(핫리로드/중복생성 방지)."""
        try:
            w = ui.Workspace.get_window(title)
        except Exception:
            w = None
        if w:
            try:
                w.destroy()
            except Exception:
                w.visible = False

    def _text(self, model: ui.SimpleStringModel, style: dict):
        """모델 바인딩 텍스트 위젯"""
        return ui.StringField(model=model, read_only=True, style=style, width=_fill())

    def _section_header_with_button(self, title: str, on_click, btn_text: str = "+"):
        """우측 상단 버튼이 달린 섹션 헤더 라인"""
        with ui.HStack(spacing=6, width=_fill(), height=24):
            ui.Label(title, style={"font_size": 16, "color": 0xFFFFFFFF}, width=_fill())
            ui.Button(
                btn_text,
                width=24,
                height=22,
                style={"color": 0xFFFFFFFF},
                clicked_fn=on_click,
            )

    # ───────────────────────── lifecycle ───────────────────────
    def on_startup(self, ext_id):
        print("[Platform.ui.main] UI startup")
        self._container_panel = ContainerPanel()
        self._mission_panel = MissionPanel()

        # 중복 창 제거
        for t in ["Meta Factory v3.0", "AMR Information", "Status Panel", "Bottom Bar"]:
            self._kill_window(t)

        # 상태 불릿(●/? 아이콘) 보관
        self._status_bullets = {}

        # 에러 로그 상태값
        self._err_merge_sec = 20.0
        self._err_last = None
               # last_time/count 초기화
        self._err_last_time = 0.0
        self._err_last_count = 0

        # ErrorLog 모델/라벨 컨테이너
        self._error_models = []
        self._error_vstack = None

        # 동적 텍스트 모델
        self.m_amr_running = ui.SimpleStringModel("0 Running")
        self.m_amr_waiting = ui.SimpleStringModel("0 Waiting")
        self.m_pallet_total = ui.SimpleStringModel("Total: 0")
        self.m_pallet_offmap = ui.SimpleStringModel("Off Map: 0")
        self.m_mission_reserved = ui.SimpleStringModel("Reserved: 0")
        self.m_mission_inprogress = ui.SimpleStringModel("In Progress: 0")

        field_style = {
            "color": 0xFFFFFFFF,
            "background_color": 0x00000000,
            "border_width": 0,
            "padding": 0,
        }

        # ── Top Bar
        self._top_win = ui.Window(
            "Meta Factory v3.0",
            width=0,
            height=40,
            style={"background_color": 0x000000A0},
        )
        with self._top_win.frame:
            with ui.HStack(height=40, padding=10, width=_fill()):
                ui.Spacer()
                ui.Label(
                    "Meta Factory v3.0",
                    alignment=ui.Alignment.CENTER,
                    style={"font_size": 20, "color": 0xFFFFFFFF},
                    width=300,
                    word_wrap=True,
                )
                ui.Spacer()

        # ── AMR Information (동적 카드 리스트)
        self._amr_win = ui.Window(
            "AMR Information",
            width=260,
            height=800,
            style={"background_color": 0x000000A0},
        )
        self._amr_cards = {}  # {amr_id: AmrCard}
        with self._amr_win.frame:
            with ui.ScrollingFrame(style={"background_color": 0x00000000}, height=_fill()):
                with ui.VStack(spacing=8, width=_fill()) as v:
                    self._amr_list_stack = v

        # ── Status Panel
        self._status_win = ui.Window(
            "Status Panel", width=320, height=0, style={"background_color": 0x000000A0}
        )
        with self._status_win.frame:
            with ui.ScrollingFrame(
                style={"background_color": 0x000000A0}, width=_fill(), height=_fill()
            ):
                with ui.Frame(clip=True, width=_fill(), height=_fill()):
                    with ui.VStack(spacing=8, padding=10, width=_fill()):
                        ui.Label(
                            "Equipment Status",
                            style={"font_size": 18, "color": 0xFFFFFFFF},
                            word_wrap=True,
                            width=_fill(),
                        )
                        ui.Separator()

                        # AMR Status
                        ui.Label(
                            "AMR Status",
                            style={"font_size": 16, "color": 0xFFFFFFFF},
                            word_wrap=True,
                            width=_fill(),
                        )
                        self._text(self.m_amr_running, field_style)
                        self._text(self.m_amr_waiting, field_style)
                        ui.Separator()

                        # Pallet List (제목 우측 버튼)
                        self._section_header_with_button(
                            "Pallet List", self._open_container_panel, btn_text="+"
                        )
                        self._text(self.m_pallet_total, field_style)
                        self._text(self.m_pallet_offmap, field_style)
                        ui.Separator()

                        # Mission List (제목 우측 버튼)
                        self._section_header_with_button(
                            "Mission List", self._open_mission_panel, btn_text="+"
                        )
                        self._text(self.m_mission_reserved, field_style)
                        self._text(self.m_mission_inprogress, field_style)
                        ui.Separator()

                        # Error Log
                        ui.Label(
                            "Error Log",
                            style={"font_size": 16, "color": 0xFFFFFFFF},
                            word_wrap=True,
                            width=_fill(),
                        )
                        with ui.Frame(height=140, width=_fill()):
                            with ui.VStack(width=_fill()) as v:
                                self._error_vstack = v
                        ui.Separator()

                        # Connection Status
                        ui.Label(
                            "Connection Status",
                            style={"font_size": 16, "color": 0xFFFFFFFF},
                            word_wrap=True,
                            width=_fill(),
                        )
                        with ui.VStack(spacing=5, width=_fill()):
                            self._draw_status_line("Operation Server", False)
                            self._draw_status_line("Fleet Server", False)
                            self._draw_status_line("OPC UA", False)
                            self._draw_status_line("Storage I/O", False)

                        ui.Spacer(height=8)

        # ── Bottom Bar
        self._init_mode_state()

        self._bottom_win = ui.Window(
            "Bottom Bar", width=0, height=60, style={"background_color": 0x00000080}
        )
        with self._bottom_win.frame:
            with ui.HStack(spacing=20, padding=10, width=_fill(), height=_fill()):
                ui.Spacer()
                ui.Button("Simulation", height=40, style={"color": 0xFFFFFFFF})
                ui.Button("ChatBot", height=40, style={"color": 0xFFFFFFFF})
                ui.Button("Library", height=40, style={"color": 0xFFFFFFFF})

                # 텍스트 바꾸기 대신 버튼 2개를 만들어 두고 보이기/숨기기만 토글
                self._btn_edit = ui.Button(
                    "Tools * Edit", width=140, height=40,
                    style={"color": 0xFFFFFFFF},
                    clicked_fn=self._toggle_operate_mode,
                )
                self._btn_operate = ui.Button(
                    "Tools * Operate", width=140, height=40,
                    style={"color": 0xFFFFFFFF},
                    clicked_fn=self._toggle_operate_mode,
                )
                # 초기 표시 상태(operate_mode가 True면 Operate 버튼만 보이게)
                self._refresh_mode_button()

                ui.Spacer()


        # ── Dock windows
        dock_window_in_window("Meta Factory v3.0", "Viewport", DockPosition.TOP, 0.05)
        dock_window_in_window("AMR Information", "Viewport", DockPosition.LEFT, 0.20)
        dock_window_in_window("Status Panel", "Viewport", DockPosition.RIGHT, 0.25)
        dock_window_in_window("Bottom Bar", "Viewport", DockPosition.BOTTOM, 0.10)

        # ── 테스트: AMR 모델 불러오기 (예: C:/omniverse_exts/AMR.usd)
        try:
            self._import_amr_model(
                "C:/omniverse_exts/AMR.usd", prim_name="/World/AMR_0"
            )
        except Exception as e:
            # 확실히 확장 실패하지 않도록 예외를 잡아 ErrorLog에만 남김
            print("[USD Import] Failed:", e)
            self._append_error_line(f"USD Import failed: {e}")

    # 상태 줄
    def _draw_status_line(self, label: str, is_connected: bool):
        glyph = "●" if is_connected else "?"
        # ABGR
        GREEN = 0xFF00FF00
        RED = 0xFF0000FF
        color = GREEN if is_connected else RED

        with ui.HStack(width=_fill()):
            ui.Label(label, width=150, style={"color": 0xFFFFFFFF})
            dot = ui.Label(glyph, style={"color": color, "font_size": 18})
            self._status_bullets[label] = dot

    def on_shutdown(self):
        for t in ["Meta Factory v3.0", "AMR Information", "Status Panel", "Bottom Bar"]:
            self._kill_window(t)
        print("[Platform.ui.main] UI shutdown")

    def _open_container_panel(self):
        try:
            self._container_panel.show()
        except Exception as e:
            print("[Platform.ui.main] ContainerPanel.show failed:", e)

    def _open_mission_panel(self):
        try:
            self._mission_panel.show()
        except Exception as e:
            print("[Platform.ui.main] MissionPanel.show failed:", e)

    # ────────────────────── ui helpers ─────────────────────────
    def _set_model(self, model_attr: str, value: str):
        m = getattr(self, model_attr, None)
        if m and hasattr(m, "set_value"):
            m.set_value(value)

    def _set_status_dot(self, label: str, is_ok: bool):
        dots = getattr(self, "_status_bullets", None)
        if not dots:
            return
        dot = dots.get(label)
        if dot:
            GREEN = 0xFF00FF00
            RED = 0xFF0000FF
            dot.style = {"color": GREEN if is_ok else RED}
            try:
                dot.text = "●" if is_ok else "?"
            except Exception:
                pass

    # ────────────────────── ErrorLog: 5줄 FIFO + (xN) 병합 ──────────────────────
    def _append_error_line(self, text: str):
        v = getattr(self, "_error_vstack", None)
        if not v:
            return

        now = time.time()

        if (
            self._err_last == text
            and (now - self._err_last_time) < self._err_merge_sec
            and self._error_models
        ):
            self._err_last_time = now
            if self._err_last_count < 5:
                self._err_last_count += 1
            suffix = f" (x{self._err_last_count})" if self._err_last_count > 1 else ""
            self._error_models[-1].set_value(f"[Error] {text}{suffix}")
            return

        self._err_last = text
        self._err_last_time = now
        self._err_last_count = 1

        if len(self._error_models) < 5:
            model = ui.SimpleStringModel(f"[Error] {text}")
            self._error_models.append(model)
            with self._error_vstack:
                ui.StringField(
                    model=model,
                    read_only=True,
                    style={"color": 0xFFFFFFFF},
                    width=_fill(),
                )
            return

        for i in range(4):
            self._error_models[i].set_value(self._error_models[i + 1].as_string)
        self._error_models[-1].set_value(f"[Error] {text}")

    # ────────────────────── AMR Import (USD API 사용) ──────────────────────
    def _import_amr_model(self, path: str, prim_name: str = "/World/AMR_0"):
        ctx = omni.usd.get_context()
        stage = ctx.get_stage()
        if not stage:
            print("[USD Import] No stage → creating new stage...")
            ctx.new_stage()
            stage = ctx.get_stage()

        # 기본 /World 보장
        if not stage.HasDefaultPrim():
            world = stage.DefinePrim("/World", "Xform")
            stage.SetDefaultPrim(world)

        # 이미 존재하면 중복 방지
        if stage.GetPrimAtPath(prim_name):
            print(f"[USD Import] {prim_name} already exists, skipping import.")
            return

        # 경로 정리: 절대경로 → file:// URI (Win: file:///C:/..., POSIX: file:///home/...)
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"USD file not found: {p}")
        posix = p.resolve().as_posix()
        asset_path = f"file:///{posix}" if ":" in posix[:10] else f"file://{posix}"

        # 프림 생성 후 레퍼런스 추가
        holder = stage.DefinePrim(prim_name, "Xform")
        holder.GetReferences().AddReference(asset_path)

        print(f"[USD Import] Referenced '{asset_path}' at {prim_name}")

    # ────────────────────── AMR 카드 동기화/플레이스홀더 ─────────────────────
    def _amr_id_of(self, it: dict, idx: int) -> str:
        return str(
            it.get("robotId")
            or it.get("amrId")
            or it.get("id")
            or it.get("name")
            or f"AMR-{idx+1}"
        )

    def _on_amr_plus(self, amr_id: str):
        # 필요 시 액션 연결
        print(f"[AMR] plus clicked: {amr_id}")

    def _show_placeholder_amr_cards(self, count: int = 4):
        """데이터 오기 전에도 기본 카드 몇 개 보여주기."""
        if not hasattr(self, "_amr_list_stack"):
            return
        for i in range(count):
            pid = f"__placeholder_{i+1}"
            if pid in getattr(self, "_amr_cards", {}):
                continue
            card = AmrCard(self._amr_list_stack, amr_id=f"AMR {i+1}")
            card.update({"status": None, "liftStatus": None, "containerCode": None, "batteryLevel": 0})
            self._amr_cards[pid] = card

    def _sync_amr_cards(self, items):
        """AMRInfo 배열과 UI 카드들을 생성/갱신/삭제로 동기화"""
        if not hasattr(self, "_amr_list_stack"):
            return

        arr = items if isinstance(items, list) else []
        seen = set()

        for i, it in enumerate(arr):
            amr_id = self._amr_id_of(it, i)
            seen.add(amr_id)

            card = self._amr_cards.get(amr_id)
            if card is None:
                card = AmrCard(self._amr_list_stack, amr_id,
                               on_plus=lambda a=amr_id: self._on_amr_plus(a))
                self._amr_cards[amr_id] = card
            card.update(it)

        # 실제 데이터가 하나라도 있으면 플레이스홀더 제거
        if arr:
            for key in list(self._amr_cards.keys()):
                if key.startswith("__placeholder_"):
                    self._amr_cards[key].destroy()
                    del self._amr_cards[key]

        # 사라진 카드 제거(실제 ID 기준)
        if arr:
            for amr_id in list(self._amr_cards.keys()):
                if not amr_id.startswith("__placeholder_") and amr_id not in seen:
                    self._amr_cards[amr_id].destroy()
                    del self._amr_cards[amr_id]
