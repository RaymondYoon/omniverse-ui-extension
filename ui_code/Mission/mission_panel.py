import omni.ui as ui


class MissionPanel:
    def __init__(self):
        self._win = None

        # 데이터 모델 (Unity 쪽 workingDataList, missionDataList, reservationDataList 대응)
        self._working_list = ["Working-01", "Working-02"]
        self._waiting_list = ["Waiting-01"]
        self._reservation_list = ["Reservation-01", "Reservation-02"]

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
            with ui.VStack(spacing=8, padding=10, width=300):
                # ───────── Title ─────────
                ui.Label("Mission List", style={"font_size": 18, "color": 0xFFFFFFFF})

                ui.Separator()

                # ───────── Count Summary ─────────
                total = len(self._working_list) + len(self._waiting_list) + len(self._reservation_list)
                ui.Label(f"Total: {total}", style={"color": 0xFFFFFFFF})
                ui.Label(f"Working: {len(self._working_list)}", style={"color": 0xFFFFAA00})
                ui.Label(f"Waiting: {len(self._waiting_list)}", style={"color": 0xFF007BFF})
                ui.Label(f"Reservation: {len(self._reservation_list)}", style={"color": 0xFF00CC66})

                ui.Separator()

                # ───────── Working Missions ─────────
                ui.Label("Working", style={"font_size": 16, "color": 0xFFFFAA00})
                with ui.VStack(spacing=4, width=280):
                    for mission in self._working_list:
                        ui.Label(mission, style={"color": 0xFFFFFFFF})

                ui.Separator()

                # ───────── Waiting Missions ─────────
                ui.Label("Waiting", style={"font_size": 16, "color": 0xFF007BFF})
                with ui.VStack(spacing=4, width=280):
                    for mission in self._waiting_list:
                        ui.Label(mission, style={"color": 0xFFFFFFFF})

                ui.Separator()

                # ───────── Reservation Missions ─────────
                ui.Label("Reservation", style={"font_size": 16, "color": 0xFF00CC66})
                with ui.VStack(spacing=4, width=280):
                    for mission in self._reservation_list:
                        ui.Label(mission, style={"color": 0xFFFFFFFF})
