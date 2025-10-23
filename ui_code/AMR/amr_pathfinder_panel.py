import omni.ui as ui
import importlib


class PathFinderPanel:
    TITLE = "Path Finder"

    def __init__(self, url: str = "https://www.naver.com/"):
        self._url = url
        self._win = None
        # WebView 지원 여부 확인
        self._has_webview = importlib.util.find_spec("omni.ui.WebView") is not None

    def show(self):
        if self._win is None:
            self._win = ui.Window(self.TITLE, width=600, height=300)
            with self._win.frame:
                with ui.VStack(spacing=8, padding=8):
                    ui.Label("Path Finder", style={"color": 0xFFFFFFFF})

                    # Start / Clear 버튼 (비워둠)
                    with ui.HStack(spacing=6):
                        ui.Button("Start", clicked_fn=self._on_start)
                        ui.Button("Clear", clicked_fn=self._on_clear)

                    ui.Spacer(height=10)

                    # WebView 또는 대체 메시지
                    if self._has_webview:
                        self._web = ui.WebView(self._url, width=880, height=500)
                    
        self._win.visible = True
        self._win.focus()

    def _on_start(self):
        # 나중에 API 연결 예정
        print("[PathFinder] Start pressed.")

    def _on_clear(self):
        # 나중에 API 연결 예정
        print("[PathFinder] Clear pressed.")
