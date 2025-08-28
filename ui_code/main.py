# main.py — UI 전용 (IExt 상속 금지, ErrorLog FIFO 로직 포함)

import time
from pathlib import Path
from functools import partial

import omni.ui as ui
from omni.ui import dock_window_in_window, DockPosition
import omni.usd

# main.py (맨 위 임포트 부분만 교체)
from ui_code.ui.utils.common import _fill
from ui_code.ui.components.amr_card import AmrCard

from ui_code.Container.container_panel import ContainerPanel
from ui_code.Mission.mission_panel import MissionPanel

from ui_code.ui.sections.top_bar import build_top_bar
from ui_code.ui.sections.amr_panel import build_amr_panel
from ui_code.ui.sections.status_panel import build_status_panel
from ui_code.ui.sections.bottom_bar import build_bottom_bar



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

        # 외부 패널 핸들
        self._container_panel = ContainerPanel()
        self._mission_panel = MissionPanel()

        # 중복 창 제거
        for t in ["Meta Factory v3.0", "AMR Information", "Status Panel", "Bottom Bar"]:
            self._kill_window(t)

        # 상태/모델 초기화
        self._status_bullets = {}
        self._err_merge_sec = 20.0
        self._err_last = None
        self._err_last_time = 0.0
        self._err_last_count = 0
        self._error_models = []
        self._error_vstack = None

        self.m_amr_running = ui.SimpleStringModel("0 Running")
        self.m_amr_waiting = ui.SimpleStringModel("0 Waiting")
        self.m_pallet_total = ui.SimpleStringModel("Total: 0")
        self.m_pallet_offmap = ui.SimpleStringModel("Off Map: 0")
        self.m_mission_reserved = ui.SimpleStringModel("Reserved: 0")
        self.m_mission_inprogress = ui.SimpleStringModel("In Progress: 0")

        # 화면 구성 (분리된 빌더 호출)
        build_top_bar(self)
        build_amr_panel(self)
        build_status_panel(self)
        build_bottom_bar(self)

        # 도킹
        dock_window_in_window("Meta Factory v3.0", "Viewport", DockPosition.TOP, 0.05)
        dock_window_in_window("AMR Information", "Viewport", DockPosition.LEFT, 0.20)
        dock_window_in_window("Status Panel", "Viewport", DockPosition.RIGHT, 0.25)
        dock_window_in_window("Bottom Bar", "Viewport", DockPosition.BOTTOM, 0.10)

        # (테스트) AMR 모델 레퍼런스 로드 시도
        try:
            self._import_amr_model("C:/omniverse_exts/AMR.usd", prim_name="/World/AMR_0")
        except Exception as e:
            print("[USD Import] Failed:", e)
            self._append_error_line(f"USD Import failed: {e}")

    # 상태 줄
    def _draw_status_line(self, label: str, is_connected: bool):
        glyph = "●" if is_connected else "?"
        GREEN = 0xFF00FF00  # ABGR
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
            card.update(
                {"status": None, "liftStatus": None, "containerCode": None, "batteryLevel": 0}
            )
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
                card = AmrCard(
                    self._amr_list_stack, amr_id,
                    on_plus=lambda a=amr_id: self._on_amr_plus(a)
                )
                self._amr_cards[amr_id] = card
            card.update(it)

        removed_placeholder = False
        # 실제 데이터가 하나라도 있으면 플레이스홀더 제거
        if arr:
            for key in list(self._amr_cards.keys()):
                if key.startswith("__placeholder_"):
                    self._amr_cards[key].destroy()
                    del self._amr_cards[key]
                    removed_placeholder = True

        # 사라진 카드 제거(실제 ID 기준)
        if arr:
            for amr_id in list(self._amr_cards.keys()):
                if not amr_id.startswith("__placeholder_") and amr_id not in seen:
                    self._amr_cards[amr_id].destroy()
                    del self._amr_cards[amr_id]

        if removed_placeholder:
            try:
                if hasattr(self, "_amr_list_stack"):
                    self._amr_list_stack.clear()  # 안전하게 비우기
                    for amr_id, card in list(self._amr_cards.items()):
                        new_card = AmrCard(self._amr_list_stack, amr_id)
                        new_card.update({})
                        self._amr_cards[amr_id] = new_card

                if hasattr(self, "_amr_scroll"):
                    self._amr_scroll.scroll_y = 0.0
            except Exception as e:
                print("[AMR] refresh failed:", e)
