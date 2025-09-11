# top_bar.py
import omni.ui as ui
from ui_code.ui.utils.common import _fill

# 높이 튜닝 포인트
TOPBAR_WINDOW_HEIGHT = 260   # ← 창 전체 높이 (기존 200)
TOPBAR_ROW_HEIGHT    = 64    # ← 상단 바 높이 (기존 40)

def build_top_bar(self):
    self._top_win = ui.Window(
        "Meta Factory v3.0",
        width=0,
        height=TOPBAR_WINDOW_HEIGHT,                    # ↑ 창 높이 업
        style={"background_color": 0x000000A0},
    )
    with self._top_win.frame:
        with ui.HStack(height=TOPBAR_ROW_HEIGHT,        # ↑ 바 자체 높이 업
                       padding=(12, 16),                # 여백도 살짝 키움
                       width=_fill()):
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

            ui.Spacer()

            # 가운데 제목
            ui.Label(
                "Meta Factory v3.0",
                alignment=ui.Alignment.CENTER,
                style={"font_size": 20, "color": 0xFFFFFFFF},
                width=300,
                word_wrap=True,
            )

            ui.Spacer()  # 오른쪽 빈 공간 확보
