# amr_panel.py
import omni.ui as ui
from .common import _fill

def build_amr_panel(self):
    # AMR 카드 컨테이너 윈도우 + 스택 준비
    self._amr_win = ui.Window(
        "AMR Information", width=260, height=800,
        style={"background_color": 0x000000A0},
    )
    self._amr_cards = {}
    with self._amr_win.frame:
        with ui.ScrollingFrame(style={"background_color": 0x00000000}, height=_fill()):
            with ui.VStack(spacing=8, width=_fill()) as v:
                self._amr_list_stack = v
