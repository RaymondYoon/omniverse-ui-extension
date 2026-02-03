# amr_3d.py — realtime smooth sync (no DebugDraw)

from pathlib import Path
from typing import Optional, Dict, Tuple
import math, time, re
from pxr import Sdf
from pxr import UsdGeom, Gf
from pxr import Usd
import omni.usd
import omni.kit.app as kit_app
from ui_code.ui.utils.common import _file_uri


class Amr3D:
    def __init__(self):
        # 이동 모드(항상 smooth)
        self._mode = "smooth"

        # 그룹 경로
        self._group_path = "/World/AMRs"

        # 좌표/축 보정
        self._TILT_X_DEG = 0.0
        self._YAW_SIGN   = +1.0
        self._YAW_OFFSET = 0.0
        self._SIGN_V     = +1.0
        self._SCALE_CORR = 1.0
        self._OFFSET_U   = 0.0
        self._OFFSET_V   = 0.0

        # 모션 파라미터
        self._MOVE_SPEED_MM_S = 300    # mm/s
        self._YAW_SPEED_DPS   = 360   # deg/s
        self._YAW_EPS_DEG     = 0.5
        self._POS_EPS_UNITS   = 0.01

        self._last_tick = time.perf_counter()

        # 캐시
        self._ops_cache: Dict[str, Tuple] = {}  # rid -> (t_op, rxyz_op, s_op)
        self._pos_cache: Dict[str, Tuple[float, float]] = {}
        self._yaw_cache: Dict[str, float] = {}
        self._targets:   Dict[str, Tuple[float, float, float]] = {}

        self._AMR_SCALE = 0.3
        self._update_sub = None

        # 디버그 로그 rate limit
        self._dbg_last_log = 0.0
        self._dbg_log_interval = 2.0  # 초

    # ───────────────── lifecycle ─────────────────
    def init(self, amr_usd_path: str):
        self._ctx   = omni.usd.get_context()
        self._stage = self._ctx.get_stage()

        if self._stage is None:
            self._ctx.new_stage()
            self._stage = self._ctx.get_stage()

        if not isinstance(self._stage, Usd.Stage):
            print("[Amr3D] ERROR: Invalid stage object:", self._stage)
            return

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

        try:
            xf = UsdGeom.Xformable(self._proto)
            s_op = None
            for op in xf.GetOrderedXformOps():
                if op.GetOpName() == "xformOp:scale":
                    s_op = op
                    break
            if s_op is None:
                s_op = xf.AddScaleOp()
            s_op.Set(Gf.Vec3d(0.1, 0.1, 0.1))
            print("[Amr3D] _AMR_proto scaled down (0.1x)")
        except Exception as e:
            print("[Amr3D] failed to scale proto:", e)


        # Stage 설정
        up = UsdGeom.GetStageUpAxis(self._stage)
        self._is_z_up = (up == UsdGeom.Tokens.z)

        meters_per_unit = UsdGeom.GetStageMetersPerUnit(self._stage) or 0.01
        units_per_meter = 1.0 / meters_per_unit
        self._mm_to_units = units_per_meter / 1000.0   # mm → stage units
        self._POS_EPS_UNITS = 10.0 * self._mm_to_units
        self._TILT_X_DEG = (90.0 if self._is_z_up else 0.0)

        # per-frame 업데이트 구독
        if not self._update_sub:
            app = kit_app.get_app()
            self._update_sub = app.get_update_event_stream().create_subscription_to_pop(
                lambda e: self.update()
            )

    # ───────────────── config ─────────────────
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

    # ───────────────── helpers ─────────────────
    @staticmethod
    def _first_key(d: dict, *names):
        for n in names:
            if n in d and d[n] is not None:
                return n
        return None

    @staticmethod
    def _getf(d: dict, *names, default=0.0):
        for n in names:
            if n in d and d[n] is not None:
                try:
                    return float(d[n])
                except Exception:
                    pass
        return float(default)

    def _get_yaw_deg(self, it: dict) -> float:
        raw = self._getf(it, "robotOrientation", "heading", "yaw", "theta", "angle", "orientationDeg", default=0.0)
        return self._norm_deg(self._YAW_SIGN * raw + self._YAW_OFFSET)

    def _amr_path(self, rid: str) -> str:
        rid = "".join(c if (c.isalnum() or c == "_") else "_" for c in str(rid))
        if rid and rid[0].isdigit():
            rid = f"_{rid}"
        base = self._group.GetPath().pathString if self._group else self._group_path
        return f"{base}/AMR_{rid}"

    def _ensure_ops(self, prim):
        
        xf = UsdGeom.Xformable(prim)

        # 1) 현재 스택에서 우리가 쓸 op 찾아오기
        cur_ops = list(xf.GetOrderedXformOps())
        t_op = r_op = s_op = None

        for op in cur_ops:
            t = op.GetOpType()
            if t == UsdGeom.XformOp.TypeTranslate and t_op is None:
                t_op = op
            elif t == UsdGeom.XformOp.TypeRotateXYZ and r_op is None:
                r_op = op
            elif t == UsdGeom.XformOp.TypeScale and s_op is None:
                s_op = op

        created = False

        # 2) 없는 것만 추가 (스택 날리지 않음)
        if t_op is None:
            t_op = xf.AddTranslateOp()
            created = True
        if r_op is None:
            r_op = xf.AddRotateXYZOp()
            created = True
        if s_op is None:
            s_op = xf.AddScaleOp()
            created = True

        # 3) 새로 생성된 경우에만 TRS를 맨 앞에 두고, 나머지는 기존 순서 유지
        if created:
            # 최신 스택 다시 가져오기 (방금 추가된 op 포함)
            all_ops = list(xf.GetOrderedXformOps())
            others = [op for op in all_ops if op not in (t_op, r_op, s_op)]
            xf.SetXformOpOrder([t_op, r_op, s_op] + others)

        # 4) 기본값 세팅 (위치/회전은 나중에 update()에서 덮어씀)
        if t_op:
            t_op.Set(Gf.Vec3d(0.0, 0.0, 0.0))
        if r_op:
            r_op.Set(Gf.Vec3d(0.0, 0.0, 0.0))
        if s_op:
            s_op.Set(Gf.Vec3d(self._AMR_SCALE, self._AMR_SCALE, self._AMR_SCALE))

        return t_op, r_op, s_op

    def _map_to_units(self, it: dict):
        # 다양한 키 지원 (서버/버전별 호환)
        x_mm = self._getf(it, "x", "posX", "mapX", "positionX", "x_mm", "X", default=0.0)
        y_mm = self._getf(it, "y", "posY", "mapY", "positionY", "y_mm", "Y", default=0.0)
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

    # ───────────────── data → targets ─────────────────
    def sync(self, items):
        stage = self._stage
        items = items or []
        seen = set()

        for i, it in enumerate(items):
            rid  = it.get("robotId") or it.get("amrId") or it.get("id") or f"{i+1}"
            path = self._amr_path(rid)

            prim = stage.GetPrimAtPath(Sdf.Path(path))
            if not prim:
                prim = stage.DefinePrim(path, "Xform")
                prim.GetReferences().AddReference("", self._proto_path)
                prim.Load()

            t_op, rxyz_op, s_op = self._ops_cache.get(rid, (None, None, None))
            if t_op is None:
                t_op, rxyz_op, s_op = self._ensure_ops(prim)
                self._ops_cache[rid] = (t_op, rxyz_op, s_op)

            u, v = self._map_to_units(it)
            yaw = self._get_yaw_deg(it)

            # 목표만 갱신
            self._targets[rid] = (u, v, yaw)
            seen.add(path)

        # 누락된 로봇 제거
        parent = self._group or stage.GetPrimAtPath(Sdf.Path(self._group_path))
        for child in list(parent.GetChildren()):
            if child.GetPath().pathString not in seen:
                stage.RemovePrim(child.GetPath())
                rid = child.GetName()[4:]
                self._ops_cache.pop(rid, None)
                self._pos_cache.pop(rid, None)
                self._yaw_cache.pop(rid, None)
                self._targets.pop(rid, None)

        # ── Debug: 주기적으로 1개 샘플 로그
        if items and (time.perf_counter() - self._dbg_last_log) > self._dbg_log_interval:
            it0 = items[0]
            raw_x = self._getf(it0, "x", "posX", "mapX", "positionX", "x_mm", "X")
            raw_y = self._getf(it0, "y", "posY", "mapY", "positionY", "y_mm", "Y")
            raw_yaw = self._getf(it0, "robotOrientation", "heading", "yaw", "theta", "angle", "orientationDeg")
            u0, v0 = self._map_to_units(it0)
            yaw0 = self._get_yaw_deg(it0)
            # print(f"[Amr3D.sync] sample rid={it0.get('robotId') or it0.get('amrId') or '-'} "
            #       f"raw(x,y,yaw)=({raw_x:.1f}mm,{raw_y:.1f}mm,{raw_yaw:.1f}°) "
            #       f"→ mapped(u,v,yaw)=({u0:.3f},{v0:.3f},{yaw0:.1f}°), mm_to_units={self._mm_to_units:.6f}, "
            #       f"SCALE_CORR={self._SCALE_CORR}, OFFSET=({self._OFFSET_U},{self._OFFSET_V}), SIGN_V={self._SIGN_V}")
            self._dbg_last_log = time.perf_counter()

    # ───────────────── per-frame update ─────────────────
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

            # 위치 보간
            du, dv = (tu - cu), (tv - cv)
            dist = math.hypot(du, dv)
            if dist > self._POS_EPS_UNITS:
                angle = math.atan2(dv, du)
                cu += math.cos(angle) * min(step_u, dist)
                cv += math.sin(angle) * min(step_u, dist)
            else:
                cu, cv = tu, tv

            # 회전 보간
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
        self._mode = "smooth"
