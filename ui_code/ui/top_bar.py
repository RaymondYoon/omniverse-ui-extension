# top_bar.py
import omni.ui as ui
from .common import _fill

def build_top_bar(self):
    self._top_win = ui.Window(
        "Meta Factory v3.0", width=0, height=40,
        style={"background_color": 0x000000A0},
    )
    with self._top_win.frame:
        with ui.HStack(height=40, padding=10, width=_fill()):
            ui.Spacer()
            ui.Label(
                "Meta Factory v3.0",
                alignment=ui.Alignment.CENTER,
                style={"font_size": 20, "color": 0xFFFFFFFF},
                width=300, word_wrap=True,
            )
            ui.Spacer()
