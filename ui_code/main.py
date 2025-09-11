import time
from pathlib import Path
from typing import Optional, Dict, Any

import omni.ui as ui
from omni.ui import dock_window_in_window, DockPosition
import omni.usd

from ui_code.ui.utils.common import _fill
from ui_code.ui.components.amr_card import AmrCard
from ui_code.ui.scene.amr_3d import Amr3D

from ui_code.Container.container_list_panel import ContainerPanel
from ui_code.Mission.mission_panel import MissionPanel
from ui_code.AMR.amr_details_panel import AMRPanel

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
        return ui.StringField(model=model, read_only=True, style=style, width=_fill())

    def _section_header_with_button(self, title: str, on_click, btn_text: str = "+"):
        with ui.HStack(spacing=6, width=_fill(), height=24):
            ui.Label(title, style={"font_size": 16, "color": 0xFFFFFFFF}, width=_fill())
            ui.Button(btn_text, width=24, height=22, style={"color": 0xFFFFFFFF}, clicked_fn=on_click)

    # ───────────────────────── lifecycle ───────────────────────
    def on_startup(self, ext_id):
        print("[Platform.ui.main] UI startup")

        # 외부 패널
        self._container_panel = ContainerPanel()
        self._mission_panel   = MissionPanel()
        self._amr_panel       = AMRPanel()

        # 중복 창 제거
        for t in ["Meta Factory v3.0", "AMR Information", "Status Panel", "Bottom Bar"]:
            self._kill_window(t)

        # 상태/모델 초기화
        self._status_bullets    = {}
        self._err_merge_sec     = 20.0
        self._err_last          = None
        self._err_last_time     = 0.0
        self._err_last_count    = 0
        self._error_models      = []
        self._error_vstack      = None

        self.m_amr_total    = ui.SimpleStringModel("Total: 0")
        self.m_amr_working  = ui.SimpleStringModel("Working: 0")
        self.m_amr_waiting  = ui.SimpleStringModel("Waiting: 0")
        self.m_amr_charging = ui.SimpleStringModel("Charging: 0")

        self.m_pallet_total       = ui.SimpleStringModel("Total: 0")
        self.m_pallet_offmap      = ui.SimpleStringModel("Off Map: 0")
        self.m_pallet_stationary  = ui.SimpleStringModel("Stationary: 0")
        self.m_pallet_inhandling  = ui.SimpleStringModel("In Handling: 0")

        self.m_mission_reserved   = ui.SimpleStringModel("Reserved: 0")
        self.m_mission_inprogress = ui.SimpleStringModel("In Progress: 0")

        self._amr_latest: Dict[str, Dict[str, Any]] = {}            # ← 추가
        self._amr_panel.set_data_resolver(lambda rid: self._amr_latest.get(str(rid)))

        # 3D 동기화 엔진
        self._amr3d = Amr3D()
        self._amr3d.init("C:/omniverse_exts/AMR.usd")

        # 지금은 /World/AMRs(루트)만 사용. t_floor 앵커는 사용하지 않음.
        # 필요해지면 아래 한 줄을 활성화:
        # self._amr3d.set_anchor("/World/t_floor")

        # 회전/축 보정(필요 시 조정)
        self._amr3d.set_mode("snap")
        self._amr3d.set_config(tilt_x=90, yaw_sign=+1, yaw_offset=0)

        # 화면 구성
        build_top_bar(self)
        build_amr_panel(self)
        build_status_panel(self)
        build_bottom_bar(self)

        # 도킹
        dock_window_in_window("Meta Factory v3.0", "Viewport", DockPosition.TOP, 0.115)
        dock_window_in_window("AMR Information", "Viewport", DockPosition.LEFT, 0.32)
        dock_window_in_window("Status Panel", "Viewport", DockPosition.RIGHT, 0.30)
        dock_window_in_window("Bottom Bar", "Viewport", DockPosition.BOTTOM, 0.11)

    # 상태 줄
    def _draw_status_line(self, label: str, is_connected: bool):
        glyph = "●" if is_connected else "?"
        color = 0xFF00FF00 if is_connected else 0xFF0000FF  # ABGR
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

    def _open_amr_panel(self, amr_id: Optional[str] = None):
        try:
            print(f"[UI] _open_amr_panel({amr_id})")
            if not hasattr(self, "_amr_panel") or self._amr_panel is None:
                self._amr_panel = AMRPanel()
            self._amr_panel.show(amr_id)   # 전달된 AMR ID 반영
        except Exception as e:
            print("[Platform.ui.main] AMRPanel.show failed:", e)

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
            dot.style = {"color": (0xFF00FF00 if is_ok else 0xFF0000FF)}
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
        if self._err_last == text and (now - self._err_last_time) < self._err_merge_sec and self._error_models:
            self._err_last_time = now
            self._err_last_count = min(5, self._err_last_count + 1)
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
                ui.StringField(model=model, read_only=True, style={"color": 0xFFFFFFFF}, width=_fill())
            return

        for i in range(4):
            self._error_models[i].set_value(self._error_models[i + 1].as_string)
        self._error_models[-1].set_value(f"[Error] {text}")

    # ────────────────────── AMR 카드 동기화/플레이스홀더 ─────────────────────
    def _amr_id_of(self, it: dict, idx: int) -> str:
        return str(it.get("robotId") or it.get("amrId") or it.get("id") or it.get("name") or f"AMR-{idx+1}")

    def _show_placeholder_amr_cards(self, count: int = 4):
        if not hasattr(self, "_amr_list_stack"):
            return
        for i in range(count):
            pid = f"__placeholder_{i+1}"
            if pid in getattr(self, "_amr_cards", {}):
                continue
            card = AmrCard(self._amr_list_stack, amr_id=f"AMR {i+1}", on_plus=self._open_amr_panel)
            card.update({"status": None, "liftStatus": None, "containerCode": None, "batteryLevel": 0})
            self._amr_cards[pid] = card

    def _sync_amr_cards(self, items):
        if not hasattr(self, "_amr_list_stack"):
            return

        arr = items if isinstance(items, list) else []
        seen = set()

        # 최신 데이터 저장소가 없으면 만들어 둠(안전)
        if not hasattr(self, "_amr_latest"):
            self._amr_latest = {}

        for i, it in enumerate(arr):
            amr_id = self._amr_id_of(it, i)
            seen.add(amr_id)

            # 최신 데이터 저장
            try:
                self._amr_latest[amr_id] = dict(it)  # (copy해서 보관 추천)
            except Exception:
                self._amr_latest[amr_id] = it

            card = self._amr_cards.get(amr_id)
            if card is None:
                card = AmrCard(self._amr_list_stack, amr_id, on_plus=self._open_amr_panel)
                self._amr_cards[amr_id] = card
            card.update(it)

            # Details가 이 AMR을 보고 있으면 즉시 반영
            try:
                if getattr(self, "_amr_panel", None) and \
                self._amr_panel.get_selected_id() == str(amr_id):
                    self._amr_panel.update(self._amr_latest[amr_id])
            except Exception:
                pass

        removed_placeholder = False
        if arr:
            for key in list(self._amr_cards.keys()):
                if key.startswith("__placeholder_"):
                    self._amr_cards[key].destroy()
                    del self._amr_cards[key]
                    removed_placeholder = True

        if arr:
            for amr_id in list(self._amr_cards.keys()):
                if not amr_id.startswith("__placeholder_") and amr_id not in seen:
                    self._amr_cards[amr_id].destroy()
                    del self._amr_cards[amr_id]
                    # 사라진 AMR은 저장소에서도 제거
                    try:
                        del self._amr_latest[amr_id]
                    except Exception:
                        pass

        if removed_placeholder:
            try:
                if hasattr(self, "_amr_list_stack"):
                    self._amr_list_stack.clear()
                    for amr_id, old_card in list(self._amr_cards.items()):
                        new_card = AmrCard(self._amr_list_stack, amr_id, on_plus=self._open_amr_panel)
                        new_card.update({})
                        self._amr_cards[amr_id] = new_card
                if hasattr(self, "_amr_scroll"):
                    self._amr_scroll.scroll_y = 0.0
            except Exception as e:
                print("[AMR] refresh failed:", e)

