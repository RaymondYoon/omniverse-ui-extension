# status_panel.py
import omni.ui as ui
from ui_code.ui.utils.common import _fill

_FIELD_STYLE = {
    "color": 0xFFFFFFFF,
    "background_color": 0x00000000,
    "border_width": 0,
    "padding": 0,
}

def build_status_panel(self):
    self._status_win = ui.Window(
        "Status Panel", width=320, height=0,
        style={"background_color": 0x000000A0},
    )
    with self._status_win.frame:
        with ui.ScrollingFrame(style={"background_color": 0x000000A0}, width=_fill(), height=_fill()):
            with ui.Frame(clip=True, width=_fill(), height=_fill()):
                with ui.VStack(spacing=8, padding=10, width=_fill()):
                    ui.Label("Equipment Status", style={"font_size": 18, "color": 0xFFFFFFFF}, word_wrap=True, width=_fill())
                    ui.Separator()

                    ui.Label("AMR Status", style={"font_size": 16, "color": 0xFFFFFFFF}, word_wrap=True, width=_fill())
                    self._text(self.m_amr_running, _FIELD_STYLE)
                    self._text(self.m_amr_waiting, _FIELD_STYLE)
                    ui.Separator()

                    self._section_header_with_button("Pallet List", self._open_container_panel, btn_text="+")
                    self._text(self.m_pallet_total, _FIELD_STYLE)
                    self._text(self.m_pallet_offmap, _FIELD_STYLE)
                    ui.Separator()

                    self._section_header_with_button("Mission List", self._open_mission_panel, btn_text="+")
                    self._text(self.m_mission_reserved, _FIELD_STYLE)
                    self._text(self.m_mission_inprogress, _FIELD_STYLE)
                    ui.Separator()

                    ui.Label("Error Log", style={"font_size": 16, "color": 0xFFFFFFFF}, word_wrap=True, width=_fill())
                    with ui.Frame(height=140, width=_fill()):
                        with ui.VStack(width=_fill()) as v:
                            self._error_vstack = v
                    ui.Separator()

                    ui.Label("Connection Status", style={"font_size": 16, "color": 0xFFFFFFFF}, word_wrap=True, width=_fill())
                    with ui.VStack(spacing=5, width=_fill()):
                        self._draw_status_line("Operation Server", False)
                        self._draw_status_line("Fleet Server", False)
                        self._draw_status_line("OPC UA", False)
                        self._draw_status_line("Storage I/O", False)

                    ui.Spacer(height=8)
