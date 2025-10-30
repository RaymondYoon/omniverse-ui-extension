# amr_pathfinder_panel.py — 호환 분기 포함: 독립형 미니맵(보조 뷰포트) + 패널 임베드
import importlib
import omni.ui as ui
import omni.usd
from pxr import Usd, UsdGeom, Gf
from omni.kit.viewport.utility import create_viewport_window


class PathFinderPanel:
    TITLE = "Path Finder"

    def __init__(self, url: str = "https://www.naver.com/"):
        self._url = url
        self._win = None
        self._has_webview = importlib.util.find_spec("omni.ui.WebView") is not None

        # ── minimap state ─────────────────────────────────────────────
        self._mini_vp = None                    # 보조 ViewportWindow
        self._mini_provider = None              # ImageWithProvider에 넣을 provider
        self._mini_map_height = 200

        # 탑다운 미니맵 카메라 설정
        self._mini_cam_path = "/World/_MiniCam"
        self._mini_cam_scale = 200.0            # orthographic aperture (줌)
        self._mini_cam_pos = Gf.Vec3d(0.0, 800.0, 0.0)   # 위에서 내려다보는 높이

    # ─────────────────────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────────────────────
    def show(self):
        if self._win is None:
            self._win = ui.Window(self.TITLE, width=720, height=520)
            with self._win.frame:
                with ui.VStack(spacing=8, padding=8):

                    # (1) 미니맵 영역: 보조 뷰포트의 텍스처를 패널에 표시
                    with ui.ZStack(height=self._mini_map_height):
                        if self._mini_vp is None:
                            self._init_minimap_viewport()

                        if self._mini_provider is not None:
                            ui.ImageWithProvider(self._mini_provider, fill_policy=ui.FillPolicy.PRESERVE_ASPECT)
                        else:
                            with ui.VStack():
                                ui.Spacer()
                                ui.Label("Minimap not available", alignment=ui.Alignment.CENTER)
                                ui.Spacer()

                        # 오버레이 컨트롤
                        with ui.HStack(height=0):
                            ui.Label(" Mini Map", style={"color": 0xFFFFFFFF, "font_size": 14})
                            ui.Spacer()
                            with ui.HStack(spacing=4):
                                ui.Button("←", width=28, clicked_fn=lambda: self._nudge_cam(dx=-50))
                                ui.Button("→", width=28, clicked_fn=lambda: self._nudge_cam(dx=+50))
                                ui.Button("↑", width=28, clicked_fn=lambda: self._nudge_cam(dz=-50))
                                ui.Button("↓", width=28, clicked_fn=lambda: self._nudge_cam(dz=+50))
                                ui.Button("-", width=28, clicked_fn=lambda: self._zoom(1.25))  # zoom out
                                ui.Button("+", width=28, clicked_fn=lambda: self._zoom(0.8))   # zoom in
                                ui.Button("Reset", width=52, clicked_fn=self._reset_cam)

                    # (2) 본문
                    ui.Label("Path Finder", style={"color": 0xFFFFFFFF})
                    with ui.HStack(spacing=6):
                        ui.Button("Start", clicked_fn=self._on_start)
                        ui.Button("Clear", clicked_fn=self._on_clear)

                    # (3) 선택: WebView
                    if self._has_webview:
                        ui.Spacer(height=6)
                        self._web = ui.WebView(self._url, width=880, height=500)

        self._win.visible = True
        self._win.focus()

    # ─────────────────────────────────────────────────────────────────────────────
    # Minimap: hidden viewport + camera
    # ─────────────────────────────────────────────────────────────────────────────
    def _init_minimap_viewport(self):
        # 1) 보조 뷰포트 생성 (메인과 완전 독립)
        self._mini_vp = create_viewport_window(name="__MinimapViewportHidden__", width=512, height=512)
        # 숨기고 텍스처만 사용
        self._mini_vp.visible = False

        # 2) 카메라 준비(없으면 생성) + 바인딩
        self._ensure_minimap_camera()
        try:
            # 버전에 따라 set_active_camera / set_active_camera_path 이름이 다를 수 있음
            if hasattr(self._mini_vp.viewport_api, "set_active_camera"):
                self._mini_vp.viewport_api.set_active_camera(self._mini_cam_path)
            elif hasattr(self._mini_vp.viewport_api, "set_active_camera_path"):
                self._mini_vp.viewport_api.set_active_camera_path(self._mini_cam_path)
        except Exception as e:
            print("[Minimap] set_active_camera failed:", e)

        # 3) 텍스처 provider 연결 — 버전 호환 분기
        self._mini_provider = self._resolve_texture_provider(self._mini_vp)

    def _resolve_texture_provider(self, vp_window):
        """
        Kit/Viewport 버전에 따라 provider를 얻는 안전한 방법:
        1) viewport_widget.texture_provider
        2) viewport_widget.get_texture_provider()
        3) viewport_api.get_texture_id() -> ui.DynamicTextureProvider
        """
        try:
            vw = getattr(vp_window, "viewport_widget", None)
            if vw is not None:
                # 1) 속성 접근
                prov = getattr(vw, "texture_provider", None)
                if prov:
                    return prov
                # 2) 메서드 접근
                if hasattr(vw, "get_texture_provider"):
                    prov = vw.get_texture_provider()
                    if prov:
                        return prov
        except Exception as e:
            print("[Minimap] texture_provider via viewport_widget failed:", e)

        # 3) 구버전 경로
        try:
            vp_api = getattr(vp_window, "viewport_api", None)
            if vp_api and hasattr(vp_api, "get_texture_id"):
                tex_id = vp_api.get_texture_id()
                provider = ui.DynamicTextureProvider("__minimap_tex__")
                provider.texture_id = tex_id
                return provider
        except Exception as e:
            print("[Minimap] DynamicTextureProvider via get_texture_id failed:", e)

        print("[Minimap] No compatible texture provider API found on this build.")
        return None

    def _ensure_minimap_camera(self):
        """ /World/_MiniCam (정사영, 탑다운) 생성/동기화 """
        ctx = omni.usd.get_context()
        stage = ctx.get_stage()
        if stage is None:
            return

        prim = stage.GetPrimAtPath(self._mini_cam_path)
        if not prim.IsValid():
            cam = UsdGeom.Camera.Define(stage, self._mini_cam_path)
            cam.CreateProjectionAttr(UsdGeom.Tokens.orthographic)
            cam.CreateClippingRangeAttr(Gf.Vec2f(0.1, 100000.0))
            cam.CreateFocusDistanceAttr(1000.0)
            cam.CreateFocalLengthAttr(50.0)
            cam.CreateHorizontalApertureAttr(self._mini_cam_scale)
            cam.CreateVerticalApertureAttr(self._mini_cam_scale)
        else:
            cam = UsdGeom.Camera(prim)
            if not cam.GetProjectionAttr().HasAuthoredValue():
                cam.CreateProjectionAttr(UsdGeom.Tokens.orthographic)
            if not cam.GetHorizontalApertureAttr().HasAuthoredValue():
                cam.CreateHorizontalApertureAttr(self._mini_cam_scale)
            if not cam.GetVerticalApertureAttr().HasAuthoredValue():
                cam.CreateVerticalApertureAttr(self._mini_cam_scale)

        self._apply_cam_transform(stage)

    def _apply_cam_transform(self, stage: Usd.Stage):
        """ 탑다운(X=-90°) 카메라 위치/회전 적용 """
        prim = stage.GetPrimAtPath(self._mini_cam_path)
        if not prim.IsValid():
            return

        xform = UsdGeom.Xformable(prim)
        ops = xform.GetOrderedXformOps()
        if len(ops) < 2:
            xform.AddXformOp(UsdGeom.XformOp.TypeTranslate)
            xform.AddXformOp(UsdGeom.XformOp.TypeRotateXYZ)
            ops = xform.GetOrderedXformOps()

        # 위치/회전
        ops[0].Set(self._mini_cam_pos)               # translate
        ops[1].Set(Gf.Vec3f(-90.0, 0.0, 0.0))        # rotate top-down

    # ─────────────────────────────────────────────────────────────────────────────
    # Camera controls
    # ─────────────────────────────────────────────────────────────────────────────
    def _nudge_cam(self, dx=0.0, dz=0.0):
        """ 미니맵 카메라 평면 이동 """
        ctx = omni.usd.get_context()
        stage = ctx.get_stage()
        if stage is None:
            return
        self._mini_cam_pos = Gf.Vec3d(
            self._mini_cam_pos[0] + dx,
            self._mini_cam_pos[1],
            self._mini_cam_pos[2] + dz
        )
        self._apply_cam_transform(stage)

    def _zoom(self, factor: float):
        """ 정사영 aperture + 높이 동시 조절 """
        self._mini_cam_scale = max(10.0, min(5000.0, self._mini_cam_scale * factor))
        self._mini_cam_pos = Gf.Vec3d(
            self._mini_cam_pos[0],
            max(50.0, min(5000.0, self._mini_cam_pos[1] * factor)),
            self._mini_cam_pos[2]
        )
        ctx = omni.usd.get_context()
        stage = ctx.get_stage()
        if stage is None:
            return
        prim = stage.GetPrimAtPath(self._mini_cam_path)
        if prim.IsValid():
            cam = UsdGeom.Camera(prim)
            cam.GetHorizontalApertureAttr().Set(self._mini_cam_scale)
            cam.GetVerticalApertureAttr().Set(self._mini_cam_scale)
        self._apply_cam_transform(stage)

    def _reset_cam(self):
        """ 카메라 초기화 """
        self._mini_cam_scale = 200.0
        self._mini_cam_pos = Gf.Vec3d(0.0, 800.0, 0.0)
        ctx = omni.usd.get_context()
        stage = ctx.get_stage()
        if stage:
            prim = stage.GetPrimAtPath(self._mini_cam_path)
            if prim.IsValid():
                cam = UsdGeom.Camera(prim)
                cam.GetHorizontalApertureAttr().Set(self._mini_cam_scale)
                cam.GetVerticalApertureAttr().Set(self._mini_cam_scale)
        self._apply_cam_transform(stage)

    # ─────────────────────────────────────────────────────────────────────────────
    # Buttons
    # ─────────────────────────────────────────────────────────────────────────────
    def _on_start(self):
        print("[PathFinder] Start pressed.")

    def _on_clear(self):
        print("[PathFinder] Clear pressed.")
