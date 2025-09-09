# ui_code/ui/sections/status_panel.py
import math
import numpy as np
import omni.ui as ui
from ui_code.ui.utils.common import _fill

_FIELD_STYLE = {
    "color": 0xFFFFFFFF,
    "background_color": 0x00000000,
    "border_width": 0,
    "padding": 0,
}

# 도넛 설정
_DONUT_SIZE   = 110
_INNER_RATIO  = 0.75
_GAP_DEG      = 2.0
_COLORS       = [
    (255, 170, 0, 255),   # Working → ORANGE
    (0, 123, 255, 255),   # Waiting → BLUE
    (0, 204, 102, 255),   # Charging → GREEN
]
_TRACK_RGBA   = (160, 160, 160, 140)  # 회색 트랙

def build_status_panel(self):
    self._status_win = ui.Window(
        "Status Panel",
        x=0, y=0, width=350, height=800,
        flags=ui.WINDOW_FLAGS_NO_MOVE | ui.WINDOW_FLAGS_NO_RESIZE | ui.WINDOW_FLAGS_NO_COLLAPSE,
        style={"background_color": 0x000000A0},
    )


    with self._status_win.frame:
        # 전체를 HStack으로 감싸고, 왼쪽에 폭 350 고정 Frame
        with ui.HStack(width=_fill(), height=_fill()):
            with ui.Frame(width=350, height=_fill(), style={"background_color": 0x000000A0}):
                with ui.VStack(spacing=8, padding=10, width=_fill()):
                    ui.Label("Equipment Status",
                             style={"font_size": 18, "color": 0xFFFFFFFF},
                             word_wrap=True, width=_fill())
                    ui.Separator()
                    # ... (중략: 기존 도넛 + 리스트 UI 다 이 Frame 안에 넣기) ...
                    ui.Spacer(height=8)

            # 오른쪽은 Spacer → 폭을 늘려도 항상 350 유지
            ui.Spacer(width=_fill())

    # 도넛용 이미지 프로바이더 + 중앙 라벨(문자열)
    self._amr_donut_provider = ui.ByteImageProvider()
    self._amr_donut_center_label = None  # build에서 만든 뒤 _draw_donut에서 .text로 갱신

    with self._status_win.frame:
        with ui.ScrollingFrame(style={"background_color": 0x000000A0}, width=_fill(), height=_fill()):
            with ui.Frame(clip=True, width=_fill(), height=_fill()):
                with ui.VStack(spacing=8, padding=10, width=_fill()):
                    ui.Label("Equipment Status",
                             style={"font_size": 18, "color": 0xFFFFFFFF},
                             word_wrap=True, width=_fill())
                    ui.Separator()

                    ui.Label("AMR Status",
                             style={"font_size": 16, "color": 0xFFFFFFFF},
                             word_wrap=True, width=_fill())

                    with ui.HStack(spacing=8, width=_fill()):
                        # 도넛(이미지 + 중앙 숫자)
                        with ui.ZStack(width=_DONUT_SIZE, height=_DONUT_SIZE):
                            ui.ImageWithProvider(self._amr_donut_provider,
                                                 width=_DONUT_SIZE, height=_DONUT_SIZE)
                            self._amr_donut_center_label = ui.Label(
                                "0",
                                alignment=ui.Alignment.CENTER,
                                style={"font_size": 20, "color": 0xFFFFFFFF},
                                width=_DONUT_SIZE, height=_DONUT_SIZE,
                            )

                        # 범례/숫자
                        with ui.VStack(spacing=3, width=_fill()):
                            with ui.HStack(width=_fill()):
                                ui.Label("-", width=14, style={"color": 0xFFFFFFFF})
                                self._text(self.m_amr_total, _FIELD_STYLE)
                            with ui.HStack(width=_fill()):
                                ui.Label("-", width=14, style={"color": 0xFF007BFF})
                                self._text(self.m_amr_working, _FIELD_STYLE)
                            with ui.HStack(width=_fill()):
                                ui.Label("-", width=14, style={"color": 0xFFFFAA00})
                                self._text(self.m_amr_waiting, _FIELD_STYLE)
                            with ui.HStack(width=_fill()):
                                ui.Label("-", width=14, style={"color": 0xFF00CC66})
                                self._text(self.m_amr_charging, _FIELD_STYLE)

                    # ── 모델 변경 → 도넛 자동 갱신 ─────────────────────────
                    def _parse_num(m: ui.SimpleStringModel) -> int:
                        try:
                            return int(str(m.as_string).split(":")[-1].strip())
                        except Exception:
                            return 0

                    def _upload(provider: ui.ByteImageProvider, img: np.ndarray, w: int, h: int):
                        arr = np.ascontiguousarray(img, dtype=np.uint8).reshape(-1)
                        size = [w, h]
                        # 가장 호환 잘 되는 경로: list[int] + 포맷
                        try:
                            fmt = ui.ByteImageProvider.Format.RGBA8_UNORM
                            provider.set_bytes_data(arr.tolist(), size, fmt)
                        except Exception:
                            try:
                                provider.set_bytes_data(arr.tolist(), size)
                            except Exception as e:
                                print("[Donut] set_bytes_data failed:", e)

                    def _draw_donut(total: int, working: int, waiting: int, charging: int):
                        # 중앙 숫자
                        if self._amr_donut_center_label:
                            self._amr_donut_center_label.text = str(int(waiting))

                        # 비율
                        s = max(working, 0) + max(waiting, 0) + max(charging, 0)
                        ratios = [0.0, 0.0, 0.0] if s == 0 else [working/s, waiting/s, charging/s]

                        # 이미지 버퍼
                        w = h = _DONUT_SIZE
                        img = np.zeros((h, w, 4), dtype=np.uint8)
                        cx, cy = (w - 1) * 0.5, (h - 1) * 0.5
                        outer_r = min(w, h) * 0.5
                        inner_r = outer_r * _INNER_RATIO
                        outer_r2, inner_r2 = outer_r * outer_r, inner_r * inner_r

                        # 트랙
                        for y in range(h):
                            dy = y - cy
                            for x in range(w):
                                dx = x - cx
                                d2 = dx * dx + dy * dy
                                if inner_r2 < d2 < outer_r2:
                                    img[y, x, :4] = _TRACK_RGBA

                        # 세그먼트
                        start = 0.0
                        segs = []
                        for i, r in enumerate(ratios):
                            ang = 360.0 * float(r)
                            end = start + max(0.0, ang - _GAP_DEG)
                            if ang > 0.0:
                                segs.append((start, end, _COLORS[i % len(_COLORS)]))
                            start += ang

                        for y in range(h):
                            dy = y - cy
                            for x in range(w):
                                dx = x - cx
                                d2 = dx * dx + dy * dy
                                if not (inner_r2 < d2 < outer_r2):
                                    continue
                                ang = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
                                for a0, a1, col in segs:
                                    if a0 <= ang <= a1:
                                        img[y, x, 0] = col[0]
                                        img[y, x, 1] = col[1]
                                        img[y, x, 2] = col[2]
                                        img[y, x, 3] = col[3]
                                        break

                        _upload(self._amr_donut_provider, img, w, h)

                    def _refresh_from_models(_=None):
                        total = _parse_num(self.m_amr_total)
                        work  = _parse_num(self.m_amr_working)
                        wait  = _parse_num(self.m_amr_waiting)
                        chg   = _parse_num(self.m_amr_charging)
                        _draw_donut(total, work, wait, chg)

                    for m in (self.m_amr_total, self.m_amr_working, self.m_amr_waiting, self.m_amr_charging):
                        m.add_value_changed_fn(_refresh_from_models)

                    # 첫 렌더(가데이터 → 즉시 모델 값 반영)
                    _draw_donut(total=5, working=0, waiting=3, charging=1)
                    _refresh_from_models()

                    ui.Separator()

                    # ───────── Pallet List ─────────
                    self._section_header_with_button("Pallet List", self._open_container_panel, btn_text="+")
                    with ui.VStack(spacing=3, width=_fill()):
                        with ui.HStack(width=_fill()):
                            ui.Label("-", width=14, style={"color": 0xFFFFFFFF})
                            self._text(self.m_pallet_total, _FIELD_STYLE)
                        with ui.HStack(width=_fill()):
                            ui.Label("-", width=14, style={"color": 0xFFCCCCCC})
                            self._text(self.m_pallet_offmap, _FIELD_STYLE)
                        with ui.HStack(width=_fill()):
                            ui.Label("-", width=14, style={"color": 0xFFFFAA00})
                            self._text(self.m_pallet_stationary, _FIELD_STYLE)
                        with ui.HStack(width=_fill()):
                            ui.Label("-", width=14, style={"color": 0xFF007BFF})
                            self._text(self.m_pallet_inhandling, _FIELD_STYLE)

                    ui.Separator()

                    # ───────── Mission List ─────────
                    self._section_header_with_button("Mission List", self._open_mission_panel, btn_text="+")

                    with ui.VStack(spacing=3, width=_fill()):   # ← 폭 고정
                        with ui.HStack(width=_fill()):
                            ui.Label("-", width=14, style={"color": 0xFFFFFFFF})
                            self._text(self.m_mission_reserved, _FIELD_STYLE)

                        with ui.HStack(width=_fill()):
                            ui.Label("-", width=14, style={"color": 0xFFFFFFFF})
                            self._text(self.m_mission_inprogress, _FIELD_STYLE)

                    ui.Separator(width=_fill())

                    # ───────── Error Log ─────────
                    ui.Label("Error Log", style={"font_size": 16, "color": 0xFFFFFFFF}, word_wrap=True, width=_fill())
                    with ui.Frame(height=140, width=_fill()):
                        with ui.VStack(width=_fill()) as v:
                            self._error_vstack = v
                    ui.Separator()

                    # ───────── Connection Status ─────────
                    ui.Label("Connection Status", style={"font_size": 16, "color": 0xFFFFFFFF}, word_wrap=True, width=_fill())
                    with ui.VStack(spacing=5, width=_fill()):
                        self._draw_status_line("Operation Server", False)
                        self._draw_status_line("Fleet Server", False)
                        self._draw_status_line("OPC UA", False)
                        self._draw_status_line("Storage I/O", False)

                    ui.Spacer(height=8)
