# ui_code/ui/sections/bottom_bar.py
import omni.ui as ui
from ui_code.ui.utils.common import _fill
from ui_code.AMR.amr_control_panel import AMRControlPanel

def build_bottom_bar(self):
    # Operate/Edit 상태 초기화
    self._init_mode_state()

    def _open_amr_panel():
        # 최초 클릭 시 생성
        if not hasattr(self, "_amr_control_panel") or self._amr_control_panel is None:
            self._amr_control_panel = AMRControlPanel(
                client=getattr(self, "_client", None),
                map_code="RR_Floor",
                set_selection_passthrough=getattr(self, "_set_selection_passthrough", None),
            )

        # 뒤늦게 client가 준비되었을 수 있으므로 주입
        if self._amr_control_panel.get_client() is None and getattr(self, "_client", None):
            self._amr_control_panel.set_client(self._client)

        # 최신 AMR 목록이 이미 있다면 패널에 반영
        amrs = getattr(self, "_amrs_latest", None)
        if amrs:
            try:
                self._amr_control_panel.update_amr_list(amrs)
            except Exception as e:
                print("[BottomBar] update_amr_list failed:", e)

        # (옵션) 현재 선택된 AMR id 모델이 있다면 전달
        sel_id = None
        sel_model = getattr(self, "m_amr_selected_id", None)
        try:
            sel_id = sel_model.as_string if sel_model else None
        except Exception:
            sel_id = None

        self._amr_control_panel.show(amr_id=sel_id)

    self._bottom_win = ui.Window(
        "Bottom Bar", width=0, height=60,
        style={"background_color": 0x00000080},
    )
    with self._bottom_win.frame:
        with ui.HStack(spacing=20, padding=10, width=_fill(), height=_fill()):
            ui.Spacer()
            ui.Button("Simulation", height=40, style={"color": 0xFFFFFFFF})
            ui.Button("ChatBot",   height=40, style={"color": 0xFFFFFFFF})
            ui.Button(
                "AMR Control",
                height=40,
                style={"color": 0xFFFFFFFF},
                clicked_fn=_open_amr_panel,
            )

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
            self._refresh_mode_button()
            ui.Spacer()
