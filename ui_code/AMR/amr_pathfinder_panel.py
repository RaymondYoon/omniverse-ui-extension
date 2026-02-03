# amr_pathfinder_panel.py
# Kit 107.3 호환 (ui.MouseArea 미사용)
# - 미니맵: 고정 Frame + 내부 수동 드로잉
# - 마우스 휠: 확대/축소(커서 기준 줌, 다양한 콜백 시그니처 대응)
# - 좌클릭 드래그: 팬(상/하/좌/우)
# - 줌/리셋 버튼 제거, 스크롤바 미사용
# - 로봇 좌표는 resolver(권장) 또는 기본 HTTP (mm→m 자동 보정)

import json
import os
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import requests
import omni.ui as ui


class PathFinderPanel:
    TITLE = "AMR Path Finder"

    # 월드 좌표 범위
    X_MIN, X_MAX = 0.0, 120.0
    Y_MIN, Y_MAX = -80.0, 40.0  # 화면 출력 시 Y는 위가 +가 되도록 뒤집어서 그림

    def __init__(
        self,
        django_base_url: str = "http://127.0.0.1:8000/mapf/",
        map_code: str = "GBFTT",
        robot_limit: int = 20,
        priority: int = 50,
        map_json_path: Optional[str] = None,   # 기본: platform_ext/resource/map_<code>_<code>_1pf.json
        viewport_height: int = 500,            # 미니맵 높이
        px_per_world: float = 8.0,             # 줌=1.0일 때 픽셀 스케일
    ):
        # HTTP
        self._django = django_base_url.rstrip("/") + "/"
        self._map_code = map_code
        self._robot_limit = int(robot_limit)
        self._priority = int(priority)
        self._session_id: Optional[str] = None

        # UI
        self._win: Optional[ui.Window] = None
        self._status = ui.SimpleStringModel("")

        # 데이터
        self._nodes: List[Tuple[float, float]] = []
        self._edges: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        self._robots: List[Tuple[float, float]] = []
        self._robots_lock = threading.Lock()

        # 맵 파일 경로
        self._map_json_path = self._resolve_map_path(map_json_path)

        # 미니맵/뷰 상태
        self._viewport_height = int(viewport_height)
        self._minimap_frame: Optional[ui.Frame] = None

        self._px_base = float(px_per_world)
        self._zoom = 1.0          # 0.3 ~ 3.0
        self._zoom_base = 1.1     # 줌 스텝(감도)
        self._wheel_dir = 1       # 1: 휠↑ 확대, -1: 반전(필요시 변경)

        # 팬: 뷰의 "왼쪽-아래" 월드 좌표(주의: y는 아래 기준)
        self._pan_x = self.X_MIN
        self._pan_y = self.Y_MIN

        # 드래그 상태
        self._dragging = False
        self._drag_last_xy: Tuple[float, float] = (0.0, 0.0)

        # 로봇 폴링
        self._poll_interval = 1.0
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_stop = threading.Event()
        self._robot_resolver: Optional[Callable[[], List[Tuple[float, float]]]] = None

        # 맵 로드
        self._load_map()

    # ----------------------- Map path resolver ----------------
    def _resolve_map_path(self, map_json_path: Optional[str]) -> str:
        """
        새 구조(omniverse_exts/platform_ext/resource/)를 우선 검색.
        사용자가 직접 경로를 넘기면 그대로 사용.
        """
        if map_json_path:
            return map_json_path

        # 현재 파일: .../platform_ext/ui_code/AMR/amr_pathfinder_panel.py
        here = os.path.dirname(os.path.abspath(__file__))
        platform_ext_dir = os.path.abspath(os.path.join(here, "..", ".."))  # .../platform_ext
        resource_dir = os.path.join(platform_ext_dir, "resource")
        guess_name = f"map_{self._map_code}_{self._map_code}_1pf.json"

        candidates = [
            os.path.join(resource_dir, guess_name),           # 1) platform_ext/resource/...
            os.path.abspath(os.path.join(here, "..", "..", "resource", guess_name)),  # 2) ../../resource/...
            os.path.join(here, guess_name),                   # 3) (구) 같은 폴더 추정
        ]

        for p in candidates:
            if os.path.exists(p):
                return p

        # 모두 실패 시 마지막 후보를 반환(에러 메시지는 로딩 단계에서 표출)
        return candidates[0]

    # ----------------------- Public API -----------------------
    def show(self):
        if self._win is None:
            self._build_ui()
        self._win.visible = True
        self._win.focus()
        if self._poll_thread is None:
            self._start_robot_polling()

    def set_robot_resolver(self, fn: Callable[[], List[Tuple[float, float]]]):
        """외부(예: bottom_bar)에서 최신 AMR 좌표를 공급할 수 있음."""
        self._robot_resolver = fn

    # ----------------------- UI Build -------------------------
    def _build_ui(self):
        self._win = ui.Window(self.TITLE, width=720, height=660)

        # 창/프레임도 휠을 직접 받게 포커스 정책 강화
        try:
            if hasattr(self._win, "set_focus_policy"):
                self._win.set_focus_policy(ui.FocusPolicy.STRONG)
            if hasattr(self._win, "frame") and hasattr(self._win.frame, "set_focus_policy"):
                self._win.frame.set_focus_policy(ui.FocusPolicy.STRONG)
        except Exception:
            pass

        if hasattr(self._win, "set_visibility_changed_fn"):
            self._win.set_visibility_changed_fn(self._on_visibility_changed)

        with self._win.frame:
            with ui.VStack(spacing=10, padding=10):
                with ui.HStack(spacing=8):
                    ui.Button("Start", width=230, height=40, clicked_fn=self._on_click_start)
                    ui.Button("Goal", width=230, height=40, clicked_fn=self._on_click_goal)
                    ui.Button("Optimized Goal", width=240, height=40, clicked_fn=self._on_click_optimized_goal)

                # 미니맵 프레임
                self._minimap_frame = ui.Frame(
                    height=self._viewport_height,
                    style={"background_color": 0xFF1E1E1E}
                )

                # 프레임 포커스 정책 강화 (Ctrl 없이 휠 받기 위함)
                try:
                    self._minimap_frame.set_focus_policy(ui.FocusPolicy.STRONG)
                except Exception:
                    pass

                self._minimap_frame.set_build_fn(self._build_minimap)

                # 휠/스크롤을 프레임에도 직접 바인딩(백업 경로)
                self._bind_wheel(self._minimap_frame)

                # 창 레벨에도 바인딩(최후 백업)
                self._bind_wheel(self._win)
                if hasattr(self._win, "frame"):
                    self._bind_wheel(self._win.frame)

                ui.Label("", height=40, word_wrap=True, model=self._status)

    # 공통 휠 바인더
    def _bind_wheel(self, widget):
        if not widget:
            return

        def _wheel_cb(*a, **k):
            try:
                return self._on_wheel_unified(*a, **k)
            except Exception as e:
                self._set(f("[wheel err] {e}"))
                return True

        for name in ("set_mouse_wheel_fn", "set_scroll_fn", "set_mouse_scroll_fn", "set_wheel_fn"):
            fn = getattr(widget, name, None)
            if fn:
                try:
                    fn(_wheel_cb)
                except Exception:
                    pass

        # 포커스 확보: 마우스 진입 시 강제 포커스
        for name in ("set_mouse_entered_fn", "set_entered_fn", "set_hovered_fn"):
            fn = getattr(widget, name, None)
            if fn:
                try:
                    fn(lambda *a, **k: getattr(widget, "focus", lambda: None)() or True)
                except Exception:
                    pass

        # 포커스 정책 강화
        if hasattr(widget, "set_focus_policy"):
            try:
                widget.set_focus_policy(ui.FocusPolicy.STRONG)
            except Exception:
                pass

    # ----------------------- Map / Robots ---------------------
    def _load_map(self):
        try:
            if not os.path.exists(self._map_json_path):
                self._set(f"[MAP] not found: {self._map_json_path}")
                return

            with open(self._map_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            floors = (data or {}).get("floorList") or []
            label_to_xy: Dict[str, Tuple[float, float]] = {}

            for fl in floors:
                nodes = (fl or {}).get("nodeList") or []
                for n in nodes:
                    x = float(n.get("xCoordinate"))
                    y = float(n.get("yCoordinate"))
                    self._nodes.append((x, y))
                    label = n.get("nodeLabel")
                    if label is not None:
                        label_to_xy[label] = (x, y)

                edges = (fl or {}).get("edgeList") or []
                for e in edges:
                    a = label_to_xy.get(e.get("beginNodeLabel"))
                    b = label_to_xy.get(e.get("endNodeLabel"))
                    if not a or not b:
                        continue
                    if abs(a[0] - b[0]) < 1e-6 or abs(a[1] - b[1]) < 1e-6:
                        self._edges.append((a, b))

            self._set(f"[MAP] nodes={len(self._nodes)} edges={len(self._edges)} loaded ({os.path.basename(self._map_json_path)})")
        except Exception as e:
            self._set(f"[ERR load map] {e}")

    def _default_robot_resolver(self) -> List[Tuple[float, float]]:
        try:
            resp = self._get(f"api/robots/{self._map_code}/positions/")
            pts: List[Tuple[float, float]] = []
            for r in (resp or []):
                rx = float(r.get("x", 0.0))
                ry = float(r.get("y", 0.0))
                if abs(rx) > 999.0 or abs(ry) > 999.0:
                    rx *= 0.001
                    ry *= 0.001
                pts.append((rx, ry))
            return pts
        except Exception:
            return []

    def _start_robot_polling(self):
        if self._poll_thread is not None:
            return

        def _poll():
            while not self._poll_stop.is_set():
                try:
                    fn = self._robot_resolver or self._default_robot_resolver
                    pts = fn() or []
                    with self._robots_lock:
                        self._robots = pts
                    self._rebuild_minimap()
                except Exception:
                    pass
                time.sleep(self._poll_interval)

        self._poll_thread = threading.Thread(target=_poll, daemon=True)
        self._poll_thread.start()

    # ----------------------- HTTP helpers ---------------------
    def _get(self, path: str):
        url = self._django + path.lstrip("/")
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, payload: Dict):
        url = self._django + path.lstrip("/")
        r = requests.post(url, json=payload, timeout=5)
        r.raise_for_status()
        return r.json()

    def _set(self, msg: str):
        print("[PathFinderPanel]", msg)
        self._status.set_value(msg)

    # ----------------------- Buttons / Session ----------------
    def _sync_session(self) -> bool:
        try:
            data = self._get(f"api/session/current/{self._map_code}/")
            if data and data.get("ok") and data.get("sessionId"):
                self._session_id = data["sessionId"]
                self._set(f"[SYNC] sid={self._session_id} phase={data.get('phase')}")
                return True
        except Exception as e:
            self._set(f"[ERR sync] {e}")
        return False

    def _on_click_start(self):
        try:
            data = self._post(
                "api/batch/start/",
                {"mapCode": self._map_code, "limit": self._robot_limit, "priority": self._priority},
            )
            if data.get("ok"):
                self._session_id = data.get("sessionId")
            self._set(f"[START] ok={data.get('ok')} sid={self._session_id} phase={data.get('phase')}")
        except Exception as e:
            self._set(f"[ERR start] {e}")

    def _on_click_goal(self):
        try:
            if not self._session_id and not self._sync_session():
                self._set("[GOAL] no session; press Start in web/panel first")
                return
            data = self._post("api/batch/goal/", {"sessionId": self._session_id})
            self._set(f"[GOAL] ok={data.get('ok')} sid={self._session_id} phase={data.get('phase')}")
        except Exception as e:
            self._set(f"[ERR goal] {e}")

    def _on_click_optimized_goal(self):
        try:
            if not self._session_id and not self._sync_session():
                self._set("[OPT] no session; run Start/Goal first")
                return
            data = self._post("api/batch/optimized/begin/", {"sessionId": self._session_id})
            self._set(f"[OPT begin] ok={data.get('ok')} sid={self._session_id} phase={data.get('phase')}")
            threading.Thread(target=self._auto_advance_when_ready, daemon=True).start()
        except Exception as e:
            self._set(f"[ERR opt] {e}")

    def _auto_advance_when_ready(self):
        deadline = time.time() + 120.0
        try:
            while time.time() < deadline:
                time.sleep(1.2)
                if not self._session_id:
                    if not self._sync_session():
                        continue
                stat = self._get(f"api/session/{self._session_id}/status/")
                if not stat or not stat.get("ok"):
                    continue
                if stat.get("phase") != "OPT_TO_START":
                    continue
                asn = stat.get("assignments") or {}
                tot = len(asn)
                arrived = len((stat.get("arrived") or {}).get("start") or [])
                if tot > 0 and arrived == tot:
                    out = self._post("api/batch/optimized/advance/", {"sessionId": self._session_id})
                    self._set(f"[OPT advance] ok={out.get('ok')} phase={out.get('phase')}")
                    return
        except Exception as e:
            self._set(f"[ERR auto-advance] {e}")

    # ----------------------- Minimap Drawing ------------------
    def _px(self) -> float:
        # 너무 작아지지/커지지 않게 제한
        z = max(0.3, min(3.0, self._zoom))
        if z != self._zoom:
            self._zoom = z
        return max(2.0, self._px_base * self._zoom)

    def _rebuild_minimap(self):
        if self._minimap_frame:
            try:
                self._minimap_frame.rebuild()
            except Exception:
                pass

    def _get_minimap_rect(self) -> Tuple[float, float]:
        try:
            if self._minimap_frame:
                rect = self._minimap_frame.computed_content_size
                return float(rect[0]), float(rect[1])
        except Exception:
            pass
        return 720.0, float(self._viewport_height)

    def _build_minimap(self, *_):
        if not self._minimap_frame:
            return

        rect_w, rect_h = self._get_minimap_rect()
        pad = 12.0
        scale = self._px()

        # 현재 뷰의 월드 폭/높이(패딩 제외)
        view_world_w = max(1e-6, (rect_w - 2 * pad) / scale)
        view_world_h = max(1e-6, (rect_h - 2 * pad) / scale)

        # 팬 보정(월드 경계 내)
        self._clamp_pan(view_world_w, view_world_h)

        with ui.ZStack():
            ui.Rectangle(style={"background_color": 0xFF1E1E1E})

            # 화면 경계에 걸치는 것만 그리도록 간단 클리핑
            vx1, vx2 = self._pan_x, self._pan_x + view_world_w
            vy1, vy2 = self._pan_y, self._pan_y + view_world_h

            # 엣지
            edge_thick = 2
            for (a, b) in self._edges:
                if not (min(a[0], b[0]) <= vx2 and max(a[0], b[0]) >= vx1 and
                        min(a[1], b[1]) <= vy2 and max(a[1], b[1]) >= vy1):
                    continue
                sx1, sy1 = self._world_to_screen(a[0], a[1], rect_w, rect_h, pad, scale)
                sx2, sy2 = self._world_to_screen(b[0], b[1], rect_w, rect_h, pad, scale)
                if abs(a[0] - b[0]) < 1e-6:
                    top = min(sy1, sy2)
                    height = int(abs(sy2 - sy1)) or 1
                    with ui.Placer(offset_x=int(sx1 - edge_thick // 2), offset_y=int(top)):
                        ui.Rectangle(width=edge_thick, height=height,
                                     style={"background_color": 0xFF6A6A6A})
                elif abs(a[1] - b[1]) < 1e-6:
                    left = min(sx1, sx2)
                    width = int(abs(sx2 - sx1)) or 1
                    with ui.Placer(offset_x=int(left), offset_y=int(sy1 - edge_thick // 2)):
                        ui.Rectangle(width=width, height=edge_thick,
                                     style={"background_color": 0xFF6A6A6A})

            # 노드
            node_px = 4
            half_n = node_px // 2
            for (nx, ny) in self._nodes:
                if not (vx1 - 1.0 <= nx <= vx2 + 1.0 and vy1 - 1.0 <= ny <= vy2 + 1.0):
                    continue
                sx, sy = self._world_to_screen(nx, ny, rect_w, rect_h, pad, scale)
                with ui.Placer(offset_x=int(sx - half_n), offset_y=int(sy - half_n)):
                    ui.Rectangle(width=node_px, height=node_px,
                                 style={"background_color": 0xFFCFCFCF, "border_radius": half_n})

            # 로봇
            robot_px = 7
            half_r = robot_px // 2
            with self._robots_lock:
                robots_copy = list(self._robots)
            for (rx, ry) in robots_copy:
                if abs(rx) > 999.0 or abs(ry) > 999.0:
                    rx *= 0.001; ry *= 0.001
                if not (vx1 - 1.0 <= rx <= vx2 + 1.0 and vy1 - 1.0 <= ry <= vy2 + 1.0):
                    continue
                sx, sy = self._world_to_screen(rx, ry, rect_w, rect_h, pad, scale)
                with ui.Placer(offset_x=int(sx - half_r), offset_y=int(sy - half_r)):
                    ui.Rectangle(
                        width=robot_px, height=robot_px,
                        style={"background_color": 0xFF22B8FF,
                               "border_radius": half_r,
                               "border_color": 0xFF0D3E66, "border_width": 1}
                    )

            # 테두리
            ui.Rectangle(style={
                "border_color": 0xFF5A5A5A,
                "border_width": 1,
                "background_color": 0x00000000
            })

            # 입력 오버레이(투명)
            self._create_input_overlay(width=int(rect_w), height=int(rect_h))

    # --------- 입력 오버레이 ----------
    def _create_input_overlay(self, width: int, height: int):
        overlay = ui.Rectangle(width=width, height=height, style={"background_color": 0x00000000})

        # 포커스 우선순위/마우스 진입시 포커스
        try:
            overlay.set_focus_policy(ui.FocusPolicy.STRONG)
            for name in ("set_mouse_entered_fn", "set_entered_fn", "set_hovered_fn"):
                fn = getattr(overlay, name, None)
                if fn:
                    try:
                        fn(lambda *a, **k: getattr(overlay, "focus", lambda: None)() or True)
                    except Exception:
                        pass
        except Exception:
            pass

        def _wheel_cb(*a, **k):
            try:
                return self._on_wheel_unified(*a, **k)
            except Exception as e:
                self._set(f"[wheel err] {e}")
                return True

        # 휠/스크롤 바인딩
        for name in ("set_mouse_wheel_fn", "set_scroll_fn", "set_mouse_scroll_fn", "set_wheel_fn"):
            fn = getattr(overlay, name, None)
            if fn:
                try:
                    fn(_wheel_cb)
                except Exception:
                    pass

        # --- 드래그 바인딩 ---
        def _pressed(*a, **k):
            try:
                x, y = float(a[0]), float(a[1])
            except Exception:
                x = y = 0.0
            btn = 0
            if "button" in k:
                try:
                    btn = int(k["button"])
                except Exception:
                    btn = 0
            elif len(a) >= 3:
                try:
                    btn = int(a[2])
                except Exception:
                    btn = 0
            if btn != 0:  # 좌클릭만 팬
                return True
            self._dragging = True
            self._drag_last_xy = (x, y)
            return True

        def _moved(*a, **k):
            if not self._dragging:
                return True
            try:
                x, y = float(a[0]), float(a[1])
            except Exception:
                return True
            lx, ly = self._drag_last_xy
            rect_w, rect_h = self._get_minimap_rect()
            pad = 12.0
            scale = self._px()
            view_world_w = max(1e-6, (rect_w - 2 * pad) / scale)
            view_world_h = max(1e-6, (rect_h - 2 * pad) / scale)

            dx = x - lx
            dy = y - ly
            self._drag_last_xy = (x, y)

            self._pan_x -= dx / scale
            self._pan_y += dy / scale  # y축 반전
            self._clamp_pan(view_world_w, view_world_h)
            self._rebuild_minimap()
            return True

        def _released(*a, **k):
            self._dragging = False
            return True

        for name, fn in (
            ("set_mouse_pressed_fn", _pressed),
            ("set_pressed_fn", _pressed),
            ("set_mouse_moved_fn", _moved),
            ("set_mouse_move_fn", _moved),
            ("set_mouse_released_fn", _released),
            ("set_released_fn", _released),
        ):
            setter = getattr(overlay, name, None)
            if setter:
                try:
                    setter(fn)
                except Exception:
                    pass

        return overlay

    # --------- 통합 휠 핸들러 ----------
    def _on_wheel_unified(self, *args, **kwargs):
        """
        다양한 Kit 버전/플랫폼의 휠 이벤트 시그니처를 흡수하고,
        '축소가 안 되는' 환경을 위해 부호 추출을 더 공격적으로 수행한다.

        가능한 시그니처 예:
        - (x, y, button, dy)
        - (x, y, dx, dy)
        - (x, y, dy)
        - (dx, dy)
        - kwargs: dy / delta_y / wheel_y / y_delta / delta
        """
        # 1) dy 후보 키워드에서 먼저 시도
        dy_val = None
        for key in ("dy", "delta_y", "wheel_y", "y_delta", "delta"):
            if key in kwargs:
                try:
                    v = float(kwargs[key])
                    dy_val = v
                    break
                except Exception:
                    pass

        # 2) 위치/델타 혼합 args에서 추출 (부호를 더 공격적으로 탐색)
        if dy_val is None:
            try:
                if len(args) >= 4:
                    cand = [args[3], args[2], args[1]]
                elif len(args) == 3:
                    cand = [args[2], args[1]]
                elif len(args) == 2:
                    cand = [args[1]]
                else:
                    cand = []
                for c in cand:
                    try:
                        v = float(c)
                        if v != 0.0:
                            dy_val = v
                            break
                        if dy_val is None:
                            dy_val = 0.0
                    except Exception:
                        pass
            except Exception:
                pass

        # dy가 여전히 None이면 이벤트를 소비만 하고 종료
        if dy_val is None:
            return True

        # 3) 마우스 좌표 추출 (없으면 중앙 기준)
        mx = my = None
        try:
            if "x" in kwargs and "y" in kwargs:
                mx = float(kwargs["x"]); my = float(kwargs["y"])
        except Exception:
            mx = my = None
        if (mx is None or my is None) and len(args) >= 2:
            try:
                ax, ay = float(args[0]), float(args[1])
                mx, my = ax, ay
            except Exception:
                mx = my = None

        rect_w, rect_h = self._get_minimap_rect()
        pad = 12.0
        old_scale = self._px()

        # 4) 휠 방향(부호) 표준화
        sign = 0
        try:
            if dy_val > 0:
                sign = 1
            elif dy_val < 0:
                sign = -1
            else:
                sign = 0
        except Exception:
            sign = 0

        if sign == 0:
            return True

        direction = 1 if (sign * self._wheel_dir) > 0 else -1
        factor = self._zoom_base if direction > 0 else (1.0 / self._zoom_base)

        # 5) 줌 갱신
        self._zoom = max(0.3, min(3.0, self._zoom * factor))
        new_scale = self._px()

        # 6) 커서 기준 줌 보정 (좌표 없으면 중앙)
        if mx is None or my is None:
            mx = rect_w * 0.5
            my = rect_h * 0.5

        sy_inv = rect_h - my
        wx = (mx - pad) / old_scale + self._pan_x
        wy = (sy_inv - pad) / old_scale + self._pan_y
        self._pan_x = wx - (mx - pad) / new_scale
        self._pan_y = wy - (sy_inv - pad) / new_scale

        # 7) 팬 클램프 & 리빌드
        vw = max(1e-6, (rect_w - 2 * pad) / new_scale)
        vh = max(1e-6, (rect_h - 2 * pad) / new_scale)
        self._clamp_pan(vw, vh)
        self._rebuild_minimap()
        return True

    # 좌표 변환/보조 ------------------------------------------
    def _world_to_screen(self, x: float, y: float, rect_w: float, rect_h: float,
                         pad: float, scale: float) -> Tuple[float, float]:
        sx = pad + (x - self._pan_x) * scale
        sy = pad + (y - self._pan_y) * scale
        sy = rect_h - sy  # 좌상단 원점으로 변환
        return sx, sy

    def _clamp_pan(self, view_world_w: float, view_world_h: float):
        max_x_eff = max(self.X_MIN, self.X_MAX - view_world_w)
        max_y_eff = max(self.Y_MIN, self.Y_MAX - view_world_h)
        self._pan_x = max(self.X_MIN, min(self._pan_x, max_x_eff))
        self._pan_y = max(self.Y_MIN, min(self._pan_y, max_y_eff))

    # ----------------------- Visibility hook ------------------
    def _on_visibility_changed(self, visible: bool):
        if not visible:
            self._poll_stop.set()
            if self._poll_thread:
                self._poll_thread.join(timeout=0.2)
            self._poll_thread = None
        else:
            self._poll_stop.clear()
            if self._poll_thread is None:
                self._start_robot_polling()
