from typing import Optional
import omni.ui as ui
from omni.ui import DockPosition
from ui_code.ui.utils.common import _fill

# 예시: 서버 요청용 함수 (실제로는 REST API client 연결)
def send_amr_command(amr_id: str, command: str, container: str = "", node: str = ""):
    print(f"[AMRControl] send_amr_command: id={amr_id}, cmd={command}, cont={container}, node={node}")
    # TODO: 실제 서버 API 호출 코드 작성
    # DigitalTwinClient.instance().post_command(...)


class AMRControlPanel:
    TITLE = "AMR Control"

    def __init__(self):
        self._win: Optional[ui.Window] = None
        self._selected_id = ui.SimpleStringModel("-")
        self._cmd_model   = ui.SimpleStringModel("Move")
        self._container   = ui.SimpleStringModel("")
        self._node        = ui.SimpleStringModel("")

    def show(self, amr_id: Optional[str] = None):
        if amr_id:
            self._selected_id.set_value(str(amr_id))

        if self._win:
            self._win.visible = True
            return

        self._win = ui.Window(
            self.TITLE,
            width=380, height=260,
            style={"background_color": 0x000000C0},
        )

        with self._win.frame:
            with ui.VStack(spacing=10, padding=10, width=_fill()):
                ui.Label("AMR Control Panel", style={"font_size": 18, "color": 0xFFFFFFFF})

                # AMR ID
                with ui.HStack():
                    ui.Label("AMR ID:", width=80, style={"color": 0xFFFFFFFF})
                    ui.StringField(model=self._selected_id, read_only=True, width=_fill())

                # Command 선택
                with ui.HStack():
                    ui.Label("Command:", width=80, style={"color": 0xFFFFFFFF})
                    ui.ComboBox(0, "Move", "Rack Move", "Pause", "Resume", "Cancel",
                                model=self._cmd_model, width=_fill())

                # Container 입력
                with ui.HStack():
                    ui.Label("Container:", width=80, style={"color": 0xFFFFFFFF})
                    ui.StringField(model=self._container, width=_fill())

                # Node 입력
                with ui.HStack():
                    ui.Label("Target Node:", width=80, style={"color": 0xFFFFFFFF})
                    ui.StringField(model=self._node, width=_fill())

                ui.Separator()

                # Dispatch 버튼
                ui.Button(
                    "Dispatch",
                    height=40,
                    style={"color": 0xFFFFFFFF},
                    clicked_fn=self._on_dispatch
                )

        self._win.visible = True

    def _on_dispatch(self):
        amr_id = self._selected_id.as_string
        cmd = self._cmd_model.as_string
        container = self._container.as_string
        node = self._node.as_string
        send_amr_command(amr_id, cmd, container, node)
