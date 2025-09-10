# amr_3d.py — real-time smooth sync for Omniverse
# (서버 좌표는 목표점으로만 사용, 옴니버스에서는 매 프레임 부드럽게 보간 이동)

from pathlib import Path
from typing import Optional
from pxr import UsdGeom, Gf
import omni.usd
import omni.kit.app as kit_app
from ui_code.ui.utils.common import _file_uri
import math, time


class Amr3D:
    def __init__(self):
        # 항상 부드럽게 이동 모드
        self._mode = "smooth"

        # AMR 그룹 루트 경로
        self._group_path = "/World/AMRs"

        # 좌표/축 보정
        self._TILT_X_DEG = 0.0
        self._YAW_SIGN   = +1.0
        self._YAW_OFFSET = 0.0
        self._SIGN_V     = +1.0
        self._SCALE_CORR = 1.0
        self._OFFSET_U   = 0.0
        self._OFFSET_V   = 0.0

        # 모션 파라미터 (속도 기반 이동)
        self._MOVE_SPEED_MM_S = 900.0   # 0.6 m/s
        self._YAW_SPEED_DPS   = 110.0    # 90 deg/s
        self._YAW_EPS_DEG     = 0.5
        self._POS_EPS_UNITS   = 0.01

        self._last_tick = time.perf_counter()

        # 캐시
        self._ops_cache  = {}   # rid -> (t_op, rxyz_op, s_op)
        self._pos_cache  = {}   # rid -> (u, v)
        self._yaw_cache  = {}   # rid -> yaw
        self._targets    = {}   # rid -> (tu, tv, tyaw)

        self._AMR_SCALE = 0.2
        self._update_sub = None

    # -------------------- lifecycle --------------------
    def init(self, amr_usd_path: str):
        self._ctx   = omni.usd.get_context()
        self._stage = self._ctx.get_stage() or (self._ctx.new_stage() or self._ctx.get_stage())

        if not self._stage.HasDefaultPrim():
            world = self._stage.DefinePrim("/World", "Xform")
            self._stage.SetDefaultPrim(world)

        # 그룹 보장
        self._group = self._stage.DefinePrim(self._group_path, "Xform")

        # 프로토타입 로드
        self._asset_uri  = _file_uri(Path(amr_usd_path))
        self._proto_path = "/World/_AMR_proto"
        proto = self._stage.GetPrimAtPath(self._proto_path)
        if not proto:
            proto = self._stage.DefinePrim(self._proto_path, "Xform")
            proto.GetReferences().AddReference(self._asset_uri)
            proto.Load()
        self._proto = proto

        # Stage 설정
        up = UsdGeom.GetStageUpAxis(self._stage)
        self._is_z_up = (up == UsdGeom.Tokens.z)

        meters_per_unit = UsdGeom.GetStageMetersPerUnit(self._stage) or 0.01
        units_per_meter = 1.0 / meters_per_unit
        self._mm_to_units = units_per_meter / 1000.0
        self._POS_EPS_UNITS = 10.0 * self._mm_to_units

        # 기본 틸트
        self._TILT_X_DEG = (90.0 if self._is_z_up else 0.0)

        # 프레임 업데이트 구독
        if not self._update_sub:
            app = kit_app.get_app()
            self._update_sub = app.get_update_event_stream().create_subscription_to_pop(
                lambda e: self.update()
            )

    # -------------------- config --------------------
    def set_config(self, *, tilt_x=None, yaw_sign=None, yaw_offset=None,
                   sign_v=None, scale_corr=None, offset_u=None, offset_v=None, amr_scale=None):
        if tilt_x     is not None: self._TILT_X_DEG = float(tilt_x)
        if yaw_sign   is not None: self._YAW_SIGN   = float(yaw_sign)
        if yaw_offset is not None: self._YAW_OFFSET = float(yaw_offset)
        if sign_v     is not None: self._SIGN_V     = float(sign_v)
        if scale_corr is not None: self._SCALE_CORR = float(scale_corr)
        if offset_u   is not None: self._OFFSET_U   = float(offset_u)
        if offset_v   is not None: self._OFFSET_V   = float(offset_v)
        if amr_scale  is not None: self._AMR_SCALE  = float(amr_scale)

    def set_motion(self, *, move_speed_mm_s=None, yaw_speed_dps=None,
                   yaw_eps_deg=None, pos_eps_mm=None):
        if move_speed_mm_s is not None: self._MOVE_SPEED_MM_S = float(move_speed_mm_s)
        if yaw_speed_dps   is not None: self._YAW_SPEED_DPS   = float(yaw_speed_dps)
        if yaw_eps_deg     is not None: self._YAW_EPS_DEG     = float(yaw_eps_deg)
        if pos_eps_mm      is not None: self._POS_EPS_UNITS   = float(pos_eps_mm) * self._mm_to_units

    # -------------------- helpers --------------------
    def _amr_path(self, rid: str) -> str:
        rid = "".join(c if (c.isalnum() or c == "_") else "_" for c in str(rid))
        if rid and rid[0].isdigit():
            rid = f"_{rid}"
        base = self._group.GetPath().pathString if self._group else self._group_path
        return f"{base}/AMR_{rid}"

    def _ensure_ops(self, prim):
        xf = UsdGeom.Xformable(prim)
        try: xf.SetResetXformStack(False)
        except Exception: pass
        try: xf.ClearXformOpOrder()
        except Exception: pass
        for prop in list(prim.GetProperties()):
            if prop.GetName().startswith("xformOp:"):
                try: prim.RemoveProperty(prop.GetName())
                except Exception: pass
        t_op = xf.AddTranslateOp()
        r_op = xf.AddRotateXYZOp()
        s_op = xf.AddScaleOp()
        xf.SetXformOpOrder([t_op, r_op, s_op])
        t_op.Set(Gf.Vec3d(0.0, 0.0, 0.0))
        r_op.Set(Gf.Vec3d(0.0, 0.0, 0.0))
        s_op.Set(Gf.Vec3d(self._AMR_SCALE, self._AMR_SCALE, self._AMR_SCALE))
        return t_op, r_op, s_op

    def _map_to_units(self, it: dict):
        x_mm = float(it.get("x", 0.0))
        y_mm = float(it.get("y", 0.0))
        u = x_mm * self._mm_to_units * self._SCALE_CORR + self._OFFSET_U
        v = y_mm * self._mm_to_units * self._SCALE_CORR
        v = v * self._SIGN_V + self._OFFSET_V
        return u, v

    @staticmethod
    def _norm_deg(deg: float) -> float:
        return ((deg + 180.0) % 360.0) - 180.0

    def _compose_euler(self, yaw_deg: float) -> Gf.Vec3d:
        if self._is_z_up:
            return Gf.Vec3d(self._TILT_X_DEG, 0.0, yaw_deg)
        else:
            return Gf.Vec3d(self._TILT_X_DEG, yaw_deg, 0.0)

    # -------------------- data → targets --------------------
    def sync(self, items):
        stage = self._stage
        items = items or []
        seen = set()

        for i, it in enumerate(items):
            rid  = it.get("robotId") or it.get("amrId") or it.get("id") or f"{i+1}"
            path = self._amr_path(rid)

            prim = stage.GetPrimAtPath(path)
            if not prim:
                prim = stage.DefinePrim(path, "Xform")
                prim.GetReferences().AddReference("", self._proto_path)
                prim.Load()

            t_op, rxyz_op, s_op = self._ops_cache.get(rid, (None, None, None))
            if t_op is None:
                t_op, rxyz_op, s_op = self._ensure_ops(prim)
                self._ops_cache[rid] = (t_op, rxyz_op, s_op)

            u, v = self._map_to_units(it)
            yaw = self._norm_deg(self._YAW_SIGN * float(it.get("robotOrientation", 0.0)) + self._YAW_OFFSET)

            # 목표만 갱신 (현재 위치는 update에서 보간)
            self._targets[rid] = (u, v, yaw)

            seen.add(path)

        # 존재하지 않는 로봇 제거
        parent = self._group or stage.GetPrimAtPath(self._group_path)
        for child in list(parent.GetChildren()):
            if child.GetPath().pathString not in seen:
                stage.RemovePrim(child.GetPath())
                rid = child.GetName()[4:]
                self._ops_cache.pop(rid, None)
                self._pos_cache.pop(rid, None)
                self._yaw_cache.pop(rid, None)
                self._targets.pop(rid, None)

    # -------------------- per-frame update --------------------
    def update(self, dt: Optional[float] = None):
        if not self._targets:
            self._last_tick = time.perf_counter()
            return

        now = time.perf_counter()
        if dt is None:
            dt = max(0.0, min(0.1, now - self._last_tick))
        self._last_tick = now

        step_u   = (self._MOVE_SPEED_MM_S * self._mm_to_units) * dt
        step_yaw = self._YAW_SPEED_DPS * dt

        for rid, (tu, tv, tyaw) in list(self._targets.items()):
            t_op, rxyz_op, s_op = self._ops_cache.get(rid, (None, None, None))
            if not t_op:
                continue

            cu, cv = self._pos_cache.get(rid, (tu, tv))
            cyaw   = self._yaw_cache.get(rid, tyaw)

            # --- 위치: MoveTowards 방식 ---
            du, dv = (tu - cu), (tv - cv)
            dist = math.hypot(du, dv)
            if dist > self._POS_EPS_UNITS:
                angle = math.atan2(dv, du)
                cu += math.cos(angle) * min(step_u, dist)
                cv += math.sin(angle) * min(step_u, dist)
            else:
                cu, cv = tu, tv

            # --- 회전: 부드러운 보간 ---
            diff = ((tyaw - cyaw + 180.0) % 360.0) - 180.0
            if abs(diff) > self._YAW_EPS_DEG:
                cyaw += max(-step_yaw, min(step_yaw, diff))
            else:
                cyaw = tyaw

            # 적용
            rxyz_op.Set(self._compose_euler(cyaw))
            vec = Gf.Vec3d(cu, 0.0, cv) if not self._is_z_up else Gf.Vec3d(cu, cv, 0.0)
            t_op.Set(vec)

            self._pos_cache[rid] = (cu, cv)
            self._yaw_cache[rid] = cyaw
    def set_mode(self, mode: str = "smooth"):
        """호환성용 set_mode (smooth 이동만 지원)."""
        self._mode = "smooth"  # 외부에서 어떤 값 주더라도 smooth 고정
