# amr_panel.py
import omni.ui as ui
from ui_code.ui.utils.common import _fill


def build_amr_panel(self):
    # 도킹/고정 윈도우
    self._amr_win = ui.Window(
        "AMR Information",
        flags=ui.WINDOW_FLAGS_NO_RESIZE | ui.WINDOW_FLAGS_NO_MOVE | ui.WINDOW_FLAGS_NO_COLLAPSE
    )

    self._amr_cards = {}

    with self._amr_win.frame:
        # 전체를 HStack으로 깔고 왼쪽만 고정 폭
        with ui.HStack(height=_fill(), width=_fill()):
            with ui.VStack(width=170):  # ← 여기서 폭 강제
                with ui.ScrollingFrame(
                    style={"background_color": 0x00000000},
                    height=_fill(),
                    width=_fill()
                ) as sf:
                    self._amr_scroll = sf
                    with ui.VStack(spacing=8, width=_fill()) as v:
                        self._amr_list_stack = v

            # 오른쪽은 Spacer로 채워서 폭 고정
            ui.Spacer(width=_fill())
