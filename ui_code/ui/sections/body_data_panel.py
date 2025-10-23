import omni.ui as ui
from pathlib import Path


class BodyDataPanel:
    TITLE = "Body Line Data"

    def __init__(self):
        self._win = None

        # Base paths
        base_dir = Path(__file__).parent.parent.parent  # ui_code/
        fonts_path = base_dir.parent / "fonts" / "static"

        # Font handling (custom or fallback)
        bold_font_path = fonts_path / "NotoSansKR-Bold.ttf"
        regular_font_path = fonts_path / "NotoSansKR-Regular.ttf"

        if bold_font_path.exists() and regular_font_path.exists():
            self.font_bold = "${fonts}/static/NotoSansKR-Bold.ttf"
            self.font_regular = "${fonts}/static/NotoSansKR-Regular.ttf"
        else:
            self.font_bold = "${app}/resources/fonts/OpenSans-SemiBold.ttf"
            self.font_regular = "${app}/resources/fonts/OpenSans-Regular.ttf"

    # ───────────────────────────────────────────────
    def show(self):
        if self._win is None:
            self._win = ui.Window(self.TITLE, width=950, height=500)
            with self._win.frame:
                with ui.VStack(spacing=10, padding=14):
                    # Title
                    ui.Label(
                        "BODY LINE MONITORING DASHBOARD",
                        style={
                            "color": 0xFFFFFFFF,  # bright white
                            "font_size": 24,
                            "font": self.font_bold,
                            "alignment": ui.Alignment.CENTER,
                        },
                    )

                    ui.Label(
                        "Real-time overview of vehicle body production and welding performance.",
                        style={
                            "color": 0x88CCFFFF,  # light blue highlight
                            "font_size": 16,
                            "font": self.font_regular,
                            "alignment": ui.Alignment.CENTER,
                        },
                    )

                    ui.Spacer(height=10)
                    self._build_table()

        self._win.visible = True
        self._win.focus()

    # ───────────────────────────────────────────────
    def _build_table(self):
        headers = [
            "Station",
            "Body ID",
            "Status",
            "Welding Quality (%)",
            "Total Weight (kg)",
            "Process Time (sec)",
        ]

        rows = [
            ("B01", "BODY-00123", "In Progress", "98.4", "835.2", "42.8"),
            ("B02", "BODY-00124", "Completed", "99.1", "834.7", "41.3"),
            ("B03", "BODY-00125", "Waiting", "-", "-", "-"),
            ("B04", "BODY-00126", "In Progress", "97.5", "836.5", "43.1"),
            ("B05", "BODY-00127", "Completed", "99.3", "835.0", "41.6"),
            ("B06", "BODY-00128", "Completed", "99.0", "835.8", "40.9"),
            ("B07", "BODY-00129", "Waiting", "-", "-", "-"),
            ("B08", "BODY-00130", "In Progress", "98.2", "834.9", "42.1"),
        ]

        def status_color(status: str) -> int:
            """Return blue color tones based on status."""
            if "Progress" in status:
                return 0x66CCFFFF  # cyan-blue
            elif "Completed" in status:
                return 0x3399FFFF  # mid blue
            elif "Waiting" in status:
                return 0x99BBFFFF  # pale blue
            return 0xFFFFFFFF  # default white

        # Table
        with ui.ScrollingFrame(
            height=480,
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
        ):
            with ui.VStack(spacing=3):
                # Header
                with ui.HStack(spacing=2, height=32):
                    for h in headers:
                        ui.Label(
                            h,
                            width=150,
                            style={
                                "background_color": 0x2E2E2EFF,  # dark header
                                "color": 0x88CCFFFF,  # header text: light blue
                                "font_size": 16,
                                "alignment": ui.Alignment.CENTER,
                                "font": self.font_bold,
                            },
                        )

                # Data rows
                for i, row in enumerate(rows):
                    row_bg = 0x1C1C1CFF if i % 2 == 0 else 0x242424FF  # alternating background
                    with ui.HStack(spacing=2, height=30):
                        for j, col in enumerate(row):
                            color_val = (
                                status_color(col)
                                if j == 2  # status column
                                else 0xFFFFFFFF  # normal text: bright white
                            )
                            ui.Label(
                                col,
                                width=150,
                                style={
                                    "background_color": row_bg,
                                    "color": color_val,
                                    "font_size": 15,
                                    "alignment": ui.Alignment.CENTER,
                                    "padding": 4,
                                    "font": self.font_regular,
                                },
                            )
