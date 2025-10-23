import omni.ui as ui
from ui_code.ui.utils.common import _fill
from ui_code.AMR.amr_control_panel import AMRControlPanel
from ui_code.Chatbot.chatbot_panel import ChatbotPanel, ChatAdapter
from ui_code.AMR.amr_pathfinder_panel import PathFinderPanel
from ui_code.ui.sections.body_data_panel import BodyDataPanel  # ✅ 경로 수정됨

def build_bottom_bar(self):
    self._init_mode_state()

    def _open_amr_control_panel():
        if not hasattr(self, "_amr_control_panel") or self._amr_control_panel is None:
            self._amr_control_panel = AMRControlPanel(
                client=getattr(self, "_client", None),
                map_code="GBFTT",
                set_selection_passthrough=getattr(self, "_set_selection_passthrough", None),
            )

        if self._amr_control_panel.get_client() is None and getattr(self, "_client", None):
            self._amr_control_panel.set_client(self._client)

        amrs = getattr(self, "_amrs_latest", None)
        if amrs:
            try:
                self._amr_control_panel.update_amr_list(amrs)
            except Exception as e:
                print("[BottomBar] update_amr_list failed:", e)

        sel_id = None
        sel_model = getattr(self, "m_amr_selected_id", None)
        try:
            sel_id = sel_model.as_string if sel_model else None
        except Exception:
            sel_id = None

        self._amr_control_panel.show(amr_id=sel_id)

    def _open_chatbot_panel():
        if not hasattr(self, "_chatbot_panel") or self._chatbot_panel is None:
            adapter = ChatAdapter()
            self._chatbot_panel = ChatbotPanel(adapter=adapter, title="ChatBot")
        self._chatbot_panel.show()

    def _open_pathfinder_panel():
        if not hasattr(self, "_pathfinder_panel") or self._pathfinder_panel is None:
            self._pathfinder_panel = PathFinderPanel()
        self._pathfinder_panel.show()

    def _open_bodydata_panel():
        if not hasattr(self, "_bodydata_panel") or self._bodydata_panel is None:
            self._bodydata_panel = BodyDataPanel()
        self._bodydata_panel.show()

    # 하단바 UI 구성
    self._bottom_win = ui.Window(
        "Bottom Bar", width=0, height=60,
        style={"background_color": 0x00000080},
    )
    with self._bottom_win.frame:
        with ui.HStack(spacing=10, padding=10, width=_fill(), height=_fill()):
            ui.Spacer()
            ui.Button("WIFI AP", height=30, style={"color": 0xFFFFFFFF})
            ui.Button("ChatBot", height=30, style={"color": 0xFFFFFFFF}, clicked_fn=_open_chatbot_panel)
            ui.Button("AMR Control", height=30, style={"color": 0xFFFFFFFF}, clicked_fn=_open_amr_control_panel)
            ui.Button("Path Finder", height=30, style={"color": 0xFFFFFFFF}, clicked_fn=_open_pathfinder_panel)
            
            # ✅ 새 버튼 추가
            ui.Button("Body Data", height=30, style={"color": 0xFFFFFFFF}, clicked_fn=_open_bodydata_panel)

            self._btn_edit = ui.Button("Tools * Edit", height=30, style={"color": 0xFFFFFFFF}, clicked_fn=self._toggle_operate_mode)
            self._btn_operate = ui.Button("Tools * Operate", height=30, style={"color": 0xFFFFFFFF}, clicked_fn=self._toggle_operate_mode)
            self._refresh_mode_button()
            ui.Spacer()
