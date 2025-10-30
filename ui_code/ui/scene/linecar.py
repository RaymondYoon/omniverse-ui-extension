# ui_code/ui/scene/linecar.py
import time
import random
from pathlib import Path
from typing import Dict, List, Optional

import omni.usd
import omni.kit.app as kit_app
from pxr import Sdf, Usd, UsdGeom, Gf, UsdShade


# ─────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────

def _file_uri(p: str) -> str:
    pp = Path(p)
    return pp.as_uri() if pp.drive or pp.is_absolute() else str(pp)

# 검/파/빨/흰/노 (요청 5색) + 초록(옵션)
_COLOR_CHOICES: List[tuple] = [
    (0.0, 0.0, 0.0),  # black
    (0.0, 0.0, 1.0),  # blue
    (1.0, 0.0, 0.0),  # red
    (1.0, 1.0, 1.0),  # white
    (1.0, 1.0, 0.0),  # yellow
    # (0.0, 1.0, 0.0),  # green (원하면 주석 해제)
]

def _random_color() -> tuple:
    return random.choice(_COLOR_CHOICES)

def _safe_compute_bound_material(prim) -> "tuple[Optional[UsdShade.Material], Optional[UsdShade.Relationship], str]":
    """ComputeBoundMaterial() 반환 튜플 길이가 버전에 따라 달라서 안전하게 포장."""
    try:
        bnd = UsdShade.MaterialBindingAPI(prim)
        res = bnd.ComputeBoundMaterial()
        if isinstance(res, tuple):
            if len(res) == 3:
                mat, rel, src = res
                return (mat if mat and mat.GetPrim().IsValid() else None, rel, str(src))
            if len(res) == 2:
                mat, rel = res
                return (mat if mat and mat.GetPrim().IsValid() else None, rel, "unknown")
            if len(res) == 1:
                mat = res[0]
                return (mat if mat and mat.GetPrim().IsValid() else None, None, "unknown")
        if res and hasattr(res, "GetPrim"):
            return (res if res.GetPrim().IsValid() else None, None, "unknown")
    except Exception:
        pass
    return (None, None, "none")

def _dbg_dump_binding(stage, mesh_path: str):
    prim = stage.GetPrimAtPath(mesh_path)
    if not prim or not prim.IsValid():
        print(f"[DBG][Bind] invalid mesh: {mesh_path}")
        return
    try:
        mat, _rel, source_type = _safe_compute_bound_material(prim)
        if mat and mat.GetPrim().IsValid():
            print(f"[DBG][Bind] {mesh_path} -> {mat.GetPath()} (source={source_type})")
        else:
            print(f"[DBG][Bind] {mesh_path} -> <no material>")
    except Exception as e:
        print(f"[DBG][Bind] failed on {mesh_path}: {e}")

def _get_shader_from_look(stage, look_path: str) -> Optional[UsdShade.Shader]:
    """Look(Material/Scope) 아래에서 Surface Shader(OmniPBR/UsdPreviewSurface)를 찾아 반환."""
    look_prim = stage.GetPrimAtPath(look_path)
    if not look_prim or not look_prim.IsValid():
        return None

    shader = None

    # 1) Material이면 SurfaceOutput의 연결 소스를 따라가본다
    if look_prim.GetTypeName() == "Material":
        try:
            mat = UsdShade.Material(look_prim)
            out = mat.GetSurfaceOutput()
            if out and out.HasConnectedSource():
                try:
                    src = out.GetConnectedSource()[0]
                except Exception:
                    src = None
                if src and isinstance(src, UsdShade.Shader):
                    shader = src
        except Exception:
            shader = None

    # 2) Material이 아니거나 못 찾았으면 자식들 중 Shader를 뒤진다
    if shader is None:
        for ch in look_prim.GetChildren():
            if ch.GetTypeName() == "Shader":
                shader = UsdShade.Shader(ch)
                break
        # 흔한 네이밍: Shaders0, Shaders1 ...
        if shader is None:
            for ch in look_prim.GetChildren():
                if ch.GetName().startswith("Shaders"):
                    try:
                        shader = UsdShade.Shader(ch)
                        break
                    except Exception:
                        continue

    if shader and shader.GetPrim().IsValid():
        return shader
    return None

def _set_albedo_on_look(stage, look_path: str, rgb: tuple) -> bool:
    shader = _get_shader_from_look(stage, look_path)
    if not shader:
        print(f"[Color] shader missing under look: {look_path}")
        return False

    # 모든 머티리얼 유형 커버용 후보
    candidate_inputs = [
        "color_tint",             # OmniPBR
        "tint_color",             # OmniPBR_ClearCoat (일부 버전)
        "diffuse_tint",           # OmniPBR older
        "diffuse_color_constant", # OmniPBR older
        "base_color",             # MDL / MaterialX
        "diffuse_color",          # UsdPreviewSurface (요거)
    ]

    found = None
    for name in candidate_inputs:
        inp = shader.GetInput(name)
        if inp:
            found = inp
            break

    if not found:
        print(f"[Color] no color input found on {shader.GetPath()}")
        return False

    prev = found.Get()
    found.Set(Gf.Vec3f(*rgb))
    return True

def _colorize_car(stage, car_path: str, looks_names: List[str], *, single_color_per_car: bool = True):
    """car_path/BODY/Body/Body/New_Scene/Looks 하위의 지정 Look들에 색상 적용."""
    looks_root = f"{car_path}/BODY/Body/Body/New_Scene/Looks"  # ← 여기만 수정됨
    if not stage.GetPrimAtPath(looks_root):
        print(f"[Color] Looks folder missing: {looks_root}")
        return

    car_rgb = _random_color()

    for look_name in looks_names:
        look_path = f"{looks_root}/{look_name}"
        rgb = car_rgb if single_color_per_car else _random_color()
        ok = _set_albedo_on_look(stage, look_path, rgb)
        if not ok:
            print(f"[DBG][Mat] not found or no shader: {look_path}")

# ─────────────────────────────────────────────────────────────
# 텍스처 누락 에러 제거 유틸
# ─────────────────────────────────────────────────────────────

_TEX_INPUTS = {
    "diffuse_texture", "opacity_texture", "normalmap_texture",
    "roughness_texture", "metallic_texture", "specular_texture",
    "emissive_texture", "clearcoat_texture", "coat_normal_texture",
    "file",  # UsdUVTexture 호환
}

def _strip_missing_textures(stage: Usd.Stage, root_prim_path: str):
    """root_prim_path 하위 Shader 입력 중 절대경로 텍스처가 존재하지 않으면 비우고 연결도 끊음."""
    root = stage.GetPrimAtPath(root_prim_path)
    if not root or not root.IsValid():
        return
    for prim in Usd.PrimRange(root):
        if prim.GetTypeName() != "Shader":
            continue
        shader = UsdShade.Shader(prim)
        sid = (shader.GetIdAttr().Get() or "").lower()

        for inp in shader.GetInputs():
            name = inp.GetBaseName()
            if name not in _TEX_INPUTS:
                continue
            attr = inp.GetAttr()
            val  = attr.Get()

            # Sdf.AssetPath 또는 string 처리
            path = ""
            if isinstance(val, Sdf.AssetPath):
                path = val.path or ""
            elif isinstance(val, str):
                path = val

            # omniverse:// 는 건드리지 않음. 윈도우 절대경로만 체크.
            if path and (":\\" in path or ":/" in path) and not path.startswith("omniverse://"):
                try:
                    import os
                    exists = os.path.exists(path)
                except Exception:
                    exists = False
                if not exists:
                    try: attr.Set(Sdf.AssetPath(""))  # 상위 파일값을 오버라이드(빈 경로)
                    except Exception: pass
                    try: inp.DisconnectSource()        # 연결도 끊기
                    except Exception: pass

        # OmniPBR일 때 텍스처 플래그도 꺼줌 + 기본 색 보정
        try:
            if "omnipbr" in sid:
                for flag in ("enable_opacity_texture", "enable_normalmap"):
                    f = shader.GetInput(flag)
                    if f and f.Get() != 0:
                        f.Set(0)
                dc = shader.GetInput("diffuse_color_constant")
                if dc and dc.Get() is None:
                    dc.Set(Gf.Vec3f(0.8, 0.8, 0.8))
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# main spawner
# ─────────────────────────────────────────────────────────────

class LineCarSpawner:
    """
    - 외부 USD(차체)를 /World/_BodyProto 로 1회만 로드하고
    - /World/<parent>/Car_### 들을 내부 레퍼런스로 여러 대 생성
    - 각 차량은 x 방향으로 이동, 끝점 도달 시 loop 또는 respawn
    - BODY/Looks/<look_name>의 albedo를 5색 랜덤 적용(기본 _19___Default)
    """
    def __init__(
        self,
        *,
        usd_path: str = "C:/BODY.usd",
        parent_path: str = "/World/LineCars",
        proto_path: str = "/World/_BodyProto",
        start_x: float = -4200,
        end_x: float = 6550,
        lane_y: float = 2738.0,
        lane_z: float = 0.0,
        speed: float = 50,
        count: int = 19,
        spacing: float = 600.0,          # x축 간격
        mode: str = "loop",              # "loop" | "respawn"
        respawn_delay: float = 0.0,      # respawn일 때만 지연
        yaw_deg: float = 90.0,           # Z yaw (도로 정렬)
        pitch_deg: float = 0.0,          # X 회전
        roll_deg: float = 0.0,           # Y 회전
        scale: float = 1.0,
        colorize: bool = True,
        looks_names: Optional[List[str]] = None,  # 색 적용할 Look 이름들
        single_color_per_car: bool = True,
    ):
        self._ctx = omni.usd.get_context()
        self._stage = self._ctx.get_stage()
        if not self._stage:
            self._ctx.new_stage()
            self._stage = self._ctx.get_stage()

        if not self._stage.HasDefaultPrim():
            world = self._stage.DefinePrim("/World", "Xform")
            self._stage.SetDefaultPrim(world)

        self.usd_path = str(usd_path)
        self.parent_path = parent_path
        self.proto_path = proto_path

        self.start_x = float(start_x)
        self.end_x = float(end_x)
        self.lane_y = float(lane_y)
        self.lane_z = float(lane_z)
        self.speed = float(speed)
        self.count = max(1, int(count))
        self.spacing = float(spacing)
        self.mode = mode.strip().lower()
        self.respawn_delay = float(respawn_delay)

        self._rot = Gf.Vec3d(float(pitch_deg), float(roll_deg), float(yaw_deg))
        self._scale = float(scale)

        # 이동 방향(오른쪽 +, 왼쪽 -)
        self._dir = 1.0 if self.end_x >= self.start_x else -1.0
        self._speed_signed = self.speed * self._dir

        self._cars: Dict[str, Dict] = {}  # name -> {prim, t, r, s, dead_until}
        self._sub = None
        self._last_time = time.perf_counter()

        # 색상 적용 설정
        self._colorize = bool(colorize)
        self._looks_names = list(looks_names) if looks_names else ["New_Material", "Body", "Door", "Trunk"]
        self._single_color_per_car = bool(single_color_per_car)

        # 부모 그룹 보장
        self._stage.DefinePrim(self.parent_path, "Xform")

        # 프로토 타입(외부 USD 한 번만 로드)
        self._ensure_proto()

        print(f"[LineCar] init parent={self.parent_path} proto={self.proto_path} usd={self.usd_path}")

    # ───────── helpers
    def _ensure_proto(self):
        proto = self._stage.GetPrimAtPath(self.proto_path)
        if not proto or not proto.IsValid():
            proto = self._stage.DefinePrim(self.proto_path, "Xform")
            proto.GetReferences().AddReference(_file_uri(self.usd_path))
            proto.Load()

        # 프로토 전체 스케일 축소(원본이 너무 클 때)
        try:
            xf = UsdGeom.Xformable(proto)
            s_op = xf.AddScaleOp()
            s_op.Set(Gf.Vec3d(0.1, 0.1, 0.1))   # ← 핵심: 프로토 자체 0.1x
            print(f"[LineCar] proto scaled down (0.1x)")
        except Exception as e:
            print(f"[LineCar] proto scale set failed:", e)

        # ★ 누락 텍스처 비활성화(에러 로그 방지)
        _strip_missing_textures(self._stage, self.proto_path)

        self._proto = proto

    def _ensure_ops(self, prim):
        xf = UsdGeom.Xformable(prim)
        try:
            xf.ClearXformOpOrder()
        except Exception:
            pass

        # 이전 xformOp 제거(깨끗하게)
        for prop in list(prim.GetProperties()):
            if prop.GetName().startswith("xformOp:"):
                try:
                    prim.RemoveProperty(prop.GetName())
                except Exception:
                    pass

        t = xf.AddTranslateOp()
        r = xf.AddRotateXYZOp()
        s = xf.AddScaleOp()
        xf.SetXformOpOrder([t, r, s])
        t.Set(Gf.Vec3d(0, 0, 0))
        r.Set(Gf.Vec3d(0, 0, 0))
        s.Set(Gf.Vec3d(1, 1, 1))
        return t, r, s

    # ───────── spawn
    def _spawn_one(self, name: str, x0: float):
        car_path = f"{self.parent_path}/{name}"

        # 기존에 같은 경로가 있으면 삭제 후 생성
        if self._stage.GetPrimAtPath(car_path):
            self._stage.RemovePrim(car_path)

        prim = self._stage.DefinePrim(car_path, "Xform")
        # 내부 ref 로 프로토 연결
        prim.GetReferences().AddReference("", Sdf.Path(self.proto_path))
        prim.Load()

        t_op, r_op, s_op = self._ensure_ops(prim)
        r_op.Set(self._rot)
        # ▼ 버그 수정: scale^2가 아니라 균등 스케일
        s_op.Set(Gf.Vec3d(self._scale, self._scale, self._scale))

        start_pos = Gf.Vec3d(x0, self.lane_y, self.lane_z)
        t_op.Set(start_pos)

        self._cars[name] = {"prim": prim, "t": t_op, "r": r_op, "s": s_op, "dead_until": 0.0}

        # 색상 적용
        if self._colorize:
            _colorize_car(
                self._stage,
                car_path,
                self._looks_names,
                single_color_per_car=self._single_color_per_car,
            )

        # (옵션) 바인딩 확인을 원하면 아래 mesh 경로에 맞게 켜서 봐도 됨
        # for mesh_name in ["jt_obj_325", "jt_obj_3s62"]:
        #     mesh_path = f"{car_path}/BODY/Geometry/Body/{mesh_name}/mesh"
        #     _dbg_dump_binding(self._stage, mesh_path)

    def spawn_many(self):
        # 기존 차량 정리(내 라인 parent만 깔끔히 비움)
        parent = self._stage.GetPrimAtPath(self.parent_path)
        if parent:
            for ch in list(parent.GetChildren()):
                self._stage.RemovePrim(ch.GetPath())

        self._cars.clear()

        # count 대를 spacing 간격으로 배치
        offset = self._dir * self.spacing  # 이동 방향 기준 spacing
        for i in range(self.count):
            x0 = self.end_x - offset * i
            self._spawn_one(f"Car_{i+1:03d}", x0)


        print(f"[LineCar] spawned {self.count} cars (mode={self.mode}, spacing={self.spacing}) under {self.parent_path}")

    # ───────── runtime
    def _step_car(self, name: str, dt: float, now: float):
        car = self._cars.get(name)
        if not car:
            return

        # respawn 모드에서 대기 중이면 skip
        if self.mode == "respawn" and now < car.get("dead_until", 0.0):
            return

        t_op = car.get("t")
        if not t_op:
            return

        # 안전하게 get/set
        try:
            pos = t_op.Get()
        except Exception:
            # prim 이 무효해졌으면 제거
            print(f"[LineCar] remove invalid car: {name}")
            self._cars.pop(name, None)
            return

        if pos is None:
            pos = Gf.Vec3d(self.start_x, self.lane_y, self.lane_z)

        pos[0] += self._speed_signed * dt
        t_op.Set(pos)

        # 끝점 체크
        reached = (pos[0] >= self.end_x) if self._dir > 0 else (pos[0] <= self.end_x)
        if reached:
            if self.mode == "loop":
                # 시작점 뒤쪽으로 보냄(간격 유지)
                pos[0] = self.start_x - self._dir * self.spacing
                t_op.Set(pos)
            else:  # respawn
                if self.respawn_delay > 0:
                    car["dead_until"] = now + self.respawn_delay
                t_op.Set(Gf.Vec3d(self.start_x, self.lane_y, self.lane_z))

    def _update(self, dt: float):
        now = time.perf_counter()
        for name in list(self._cars.keys()):
            self._step_car(name, dt, now)

    # ───────── start/stop
    def start(self):
        self.spawn_many()
        app = kit_app.get_app()
        stream = app.get_update_event_stream()
        self._sub = stream.create_subscription_to_pop(self._on_update, name=f"linecar_update_{self.parent_path}")
        print("[LineCar] started")

    def stop(self):
        self._sub = None
        print("[LineCar] stopped")

    def _on_update(self, _e):
        try:
            now = time.perf_counter()
            dt = now - self._last_time
            if dt < 0:
                dt = 0.0
            if dt > 0.1:
                dt = 0.1
            self._last_time = now
            self._update(dt)
        except Exception as ex:
            print(f"[LineCar] update error in {self.parent_path}: {ex}")
