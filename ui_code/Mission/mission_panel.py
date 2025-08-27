import omni.ui as ui


class MissionPanel:
    def __init__(self):
        self._win = None

    def show(self):
        if self._win:
            self._win.visible = True
            return

        self._win = ui.Window(
            "Mission List",
            width=300,
            height=400,
            style={"background_color": 0x000000A0},
        )
        with self._win.frame:
            with ui.VStack(spacing=8, padding=10):
                ui.Label("Mission List", style={"font_size": 18, "color": 0xFFFFFFFF})
                for i in range(1, 6):
                    ui.Label(f"Mission-0{i}", style={"color": 0xFFFFFFFF})
