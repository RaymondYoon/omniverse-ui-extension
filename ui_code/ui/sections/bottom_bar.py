# bottom_bar.py
import omni.ui as ui
from ui_code.ui.utils.common import _fill

def build_bottom_bar(self):
    # operate/edit 모드 상태 먼저 반영
    self._init_mode_state()

    self._bottom_win = ui.Window(
        "Bottom Bar", width=0, height=60,
        style={"background_color": 0x00000080},
    )
    with self._bottom_win.frame:
        with ui.HStack(spacing=20, padding=10, width=_fill(), height=_fill()):
            ui.Spacer()
            ui.Button("Simulation", height=40, style={"color": 0xFFFFFFFF})
            ui.Button("ChatBot",   height=40, style={"color": 0xFFFFFFFF})
            ui.Button("Library",   height=40, style={"color": 0xFFFFFFFF})

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
