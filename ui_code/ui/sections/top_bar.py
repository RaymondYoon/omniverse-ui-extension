# top_bar.py
import omni.ui as ui
from ui_code.ui.utils.common import _fill

def build_top_bar(self):
    self._top_win = ui.Window(
        "Meta Factory v3.0", width=0, height=40,
        style={"background_color": 0x000000A0},
    )
    with self._top_win.frame:
        with ui.HStack(height=40, padding=10, width=_fill()):
            # 왼쪽 상단 Automes + URL
            with ui.VStack(width=200):  
                ui.Label(
                    "Automes",
                    alignment=ui.Alignment.LEFT,
                    style={"font_size": 16, "color": 0xFFFFFFFF},
                )
                ui.Label(
                    "http://www.automes.co.kr",
                    alignment=ui.Alignment.LEFT,
                    style={"font_size": 12, "color": 0xFFFFFFFF},
                )

            ui.Spacer()  # 가운데 띄우기

            # 가운데 제목
            ui.Label(
                "Meta Factory v3.0",
                alignment=ui.Alignment.CENTER,
                style={"font_size": 20, "color": 0xFFFFFFFF},
                width=300,
                word_wrap=True,
            )

            ui.Spacer()  # 오른쪽 빈 공간 확보
