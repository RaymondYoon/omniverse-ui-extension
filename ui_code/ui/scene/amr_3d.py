# amr_3d.py — real-time snap-first sync
# (Unity↔USD 축/단위 자동처리, 단일 rotateXYZ 기반 TRS, 그룹 경로 동적, 중복 생성/경고 제거)

from pathlib import Path
from typing import Literal, Optional
from pxr import UsdGeom, Gf
import omni.usd
from ui_code.ui.utils.common import _file_uri
import math, time


class Amr3D:
    def __init__(self):
        # 기본 모드: 서버값 즉시 반영(snap). 필요시 "lerp" / "turnmove" 선택 가능
        self._mode: Literal["snap", "lerp", "turnmove"] = "snap"

        # 현재 AMR 그룹의 루트 경로(이 경로 아래에 AMR_*가 생성됨)
        self._group_path = "/World/AMRs"

        # 좌표/축 보정 기본값
        self._TILT_X_DEG = 0.0
        self._YAW_SIGN   = +1.0
        self._YAW_OFFSET = 0.0
        self._SIGN_V     = +1.0
        self._SCALE_CORR = 1.0
        self._OFFSET_U   = 0.0
        self._OFFSET_V   = 0.0

        # 모션 파라미터(보간 모드)
        self._MOVE_SPEED_MM_S = 1200.0
        self._YAW_SPEED_DPS   = 180.0
        self._YAW_EPS_DEG     = 1.0
        self._POS_EPS_UNITS   = 0.01  # init에서 10mm로 덮어씀

        self._last_tick = time.perf_counter()

        # 캐시/상태
        self._ops_cache  = {}   # rid -> (t_op, rxyz_op, s_op)
        self._pos_cache  = {}   # rid -> (u, v)
        self._yaw_cache  = {}   # rid -> yaw
        self._targets    = {}   # rid -> (tu, tv, tyaw)
        self._state      = {}   # rid -> "turn" | "move" | "idle"

    # -------------------- lifecycle --------------------
    def init(self, amr_usd_path: str):
        self._ctx   = omni.usd.get_context()
        self._stage = self._ctx.get_stage() or (self._ctx.new_stage() or self._ctx.get_stage())

        # /World 보장
        if not self._stage.HasDefaultPrim():
            world = self._stage.DefinePrim("/World", "Xform")
            self._stage.SetDefaultPrim(world)

        # AMR 그룹(Xform) 보장 (현재 경로 사용)
        self._group = self._stage.DefinePrim(self._group_path, "Xform")

        # AMR 프로토타입 로드
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

        meters_per_unit = UsdGeom.GetStageMetersPerUnit(self._stage) or 0.01  # 기본 1unit=1cm
        units_per_meter = 1.0 / meters_per_unit
        self._mm_to_units = units_per_meter / 1000.0
        self._POS_EPS_UNITS = 10.0 * self._mm_to_units  # 10mm

        # 모델이 옆으로 눕는 경우(Z-up 스테이지에서 Unity형 모델)를 대비한 기본 틸트
        self._TILT_X_DEG = (90.0 if self._is_z_up else 0.0)

    # -------------------- public tuning --------------------
    def set_mode(self, mode: Literal["snap", "lerp", "turnmove"] = "snap"):
        self._mode = mode

    def set_config(self, *, tilt_x=None, yaw_sign=None, yaw_offset=None,
                   sign_v=None, scale_corr=None, offset_u=None, offset_v=None):
        if tilt_x     is not None: self._TILT_X_DEG = float(tilt_x)
        if yaw_sign   is not None: self._YAW_SIGN   = float(yaw_sign)
        if yaw_offset is not None: self._YAW_OFFSET = float(yaw_offset)
        if sign_v     is not None: self._SIGN_V     = float(sign_v)
        if scale_corr is not None: self._SCALE_CORR = float(scale_corr)
        if offset_u   is not None: self._OFFSET_U   = float(offset_u)
        if offset_v   is not None: self._OFFSET_V   = float(offset_v)

    def set_motion(self, *, move_speed_mm_s=None, yaw_speed_dps=None,
                   yaw_eps_deg=None, pos_eps_mm=None):
        if move_speed_mm_s is not None: self._MOVE_SPEED_MM_S = float(move_speed_mm_s)
        if yaw_speed_dps   is not None: self._YAW_SPEED_DPS   = float(yaw_speed_dps)
        if yaw_eps_deg     is not None: self._YAW_EPS_DEG     = float(yaw_eps_deg)
        if pos_eps_mm      is not None: self._POS_EPS_UNITS   = float(pos_eps_mm) * self._mm_to_units

    # -------------------- helpers --------------------
    def _amr_path(self, rid: str) -> str:
        """현재 그룹 경로 아래에 안전한 이름으로 AMR 경로 생성."""
        rid = "".join(c if (c.isalnum() or c == "_") else "_" for c in str(rid))
        if rid and rid[0].isdigit():
            rid = f"_{rid}"
        base = self._group.GetPath().pathString if self._group else self._group_path
        return f"{base}/AMR_{rid}"

    def _ensure_ops(self, prim):
        """
        Prim에 'TRS(translate, rotateXYZ, scale)' 스택을 강제.
        - 부모 변환 상속: resetXformStack(False)
        - 기존 xformOp:* 제거 후 원하는 op만 생성
        - opOrder = [translate, rotateXYZ, scale]
        """
        xf = UsdGeom.Xformable(prim)

        try:
            xf.SetResetXformStack(False)
        except Exception:
            pass

        try:
            xf.ClearXformOpOrder()
        except Exception:
            pass

        for prop in list(prim.GetProperties()):
            if prop.GetName().startswith("xformOp:"):
                try:
                    prim.RemoveProperty(prop.GetName())
                except Exception:
                    pass

        t_op = xf.AddTranslateOp()
        r_op = xf.AddRotateXYZOp()
        s_op = xf.AddScaleOp()
        xf.SetXformOpOrder([t_op, r_op, s_op])

        # 기본값 보장
        t_op.Set(Gf.Vec3d(0.0, 0.0, 0.0))
        r_op.Set(Gf.Vec3d(0.0, 0.0, 0.0))
        s_op.Set(Gf.Vec3d(1.0, 1.0, 1.0))
        return t_op, r_op, s_op

    def _map_to_units(self, it: dict):
        # 서버 x,y(mm) → 평면 좌표(u,v)
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
        """단일 rotateXYZ로 'tiltX + yaw'를 합성."""
        if self._is_z_up:
            # Z-up: XY 평면, yaw=Z, tilt=X
            return Gf.Vec3d(self._TILT_X_DEG, 0.0, yaw_deg)
        else:
            # Y-up: XZ 평면, yaw=Y, tilt=X
            return Gf.Vec3d(self._TILT_X_DEG, yaw_deg, 0.0)

    def _apply_pose_immediate(self, t_op, rxyz_op, s_op, u: float, v: float, yaw_deg: float):
        """스냅모드/초기화 공용 즉시 적용 (TRS 순서 유지, 회전은 rotateXYZ 한 개)."""
        rxyz_op.Set(self._compose_euler(yaw_deg))
        vec = Gf.Vec3d(u, 0.0, v) if not self._is_z_up else Gf.Vec3d(u, v, 0.0)
        t_op.Set(vec)

    # -------------------- data → targets --------------------
    def sync(self, items):
        """서버에서 받은 배열(items)을 씬에 반영."""
        stage = self._stage
        items = items or []
        seen = set()

        for i, it in enumerate(items):
            rid  = it.get("robotId") or it.get("amrId") or it.get("id") or f"{i+1}"
            path = self._amr_path(rid)

            prim = stage.GetPrimAtPath(path)
            created = False
            if not prim:
                prim = stage.DefinePrim(path, "Xform")
                prim.GetReferences().AddReference("", self._proto_path)
                prim.Load()
                created = True

            t_op, rxyz_op, s_op = self._ops_cache.get(rid, (None, None, None))
            if t_op is None:
                t_op, rxyz_op, s_op = self._ensure_ops(prim)
                self._ops_cache[rid] = (t_op, rxyz_op, s_op)

            u, v = self._map_to_units(it)
            yaw = self._norm_deg(self._YAW_SIGN * float(it.get("robotOrientation", 0.0)) + self._YAW_OFFSET)

            # 최초값/신규 생성
            if created or rid not in self._pos_cache:
                self._pos_cache[rid] = (u, v)
                self._yaw_cache[rid] = yaw
                self._apply_pose_immediate(t_op, rxyz_op, s_op, u, v, yaw)
                self._state[rid] = "idle"

            if self._mode == "snap":
                self._apply_pose_immediate(t_op, rxyz_op, s_op, u, v, yaw)
                self._pos_cache[rid] = (u, v)
                self._yaw_cache[rid] = yaw
                self._targets.pop(rid, None)
                self._state[rid] = "idle"
            else:
                self._targets[rid] = (u, v, yaw)
                if self._mode == "turnmove":
                    self._state[rid] = "turn"

            seen.add(path)

        # 존재하지 않는 로봇 정리(현재 그룹 기준)
        parent = self._group or stage.GetPrimAtPath(self._group_path)
        for child in list(parent.GetChildren()):
            if child.GetPath().pathString not in seen:
                stage.RemovePrim(child.GetPath())
                rid = child.GetName()[4:]
                self._ops_cache.pop(rid, None)
                self._pos_cache.pop(rid, None)
                self._yaw_cache.pop(rid, None)
                self._targets.pop(rid, None)
                self._state.pop(rid, None)

    # -------------------- per-frame update --------------------
    def update(self, dt: Optional[float] = None):
        # 스냅 모드면 할 일 없음
        if self._mode == "snap" or not self._targets:
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
            state  = self._state.get(rid, "idle")

            if self._mode == "lerp":
                du, dv = (tu - cu), (tv - cv)
                dist = math.hypot(du, dv)
                if dist > 0.0:
                    r = min(1.0, step_u / dist)
                    cu, cv = (cu + du * r, cv + dv * r)
                diff = ((tyaw - cyaw + 180.0) % 360.0) - 180.0
                if abs(diff) > 0.0:
                    cyaw += step_yaw if diff > 0 else -step_yaw
                    cyaw = min(cyaw, tyaw) if diff > 0 else max(cyaw, tyaw)

            elif self._mode == "turnmove":
                if state == "turn":
                    diff = ((tyaw - cyaw + 180.0) % 360.0) - 180.0
                    if abs(diff) <= self._YAW_EPS_DEG:
                        cyaw = tyaw
                        state = "move"
                    else:
                        cyaw += step_yaw if diff > 0 else -step_yaw
                    self._state[rid] = state

                if state == "move":
                    du, dv = (tu - cu), (tv - cv)
                    dist = math.hypot(du, dv)
                    if dist <= self._POS_EPS_UNITS or dist == 0.0:
                        cu, cv = tu, tv
                        state = "idle"
                    else:
                        r = min(1.0, step_u / dist)
                        cu, cv = (cu + du * r, cv + dv * r)
                    self._state[rid] = state
                    cyaw = tyaw

            # 적용
            rxyz_op.Set(self._compose_euler(cyaw))
            vec = Gf.Vec3d(cu, 0.0, cv) if not self._is_z_up else Gf.Vec3d(cu, cv, 0.0)
            t_op.Set(vec)

            self._pos_cache[rid] = (cu, cv)
            self._yaw_cache[rid] = cyaw

    # -------------------- anchoring --------------------
    def set_anchor(self, anchor_path: str = "/World"):
        """
        AMR 그룹을 anchor_path 아래로 이동.
        ex) "/World/t_floor" → "/World/t_floor/AMRs"
        기본값 "/World"면 결과는 "/World/AMRs" (루트 유지).
        """
        stage = self._stage
        anchor = stage.GetPrimAtPath(anchor_path)
        if not anchor:
            raise ValueError(f"Anchor prim not found: {anchor_path}")

        old_path = self._group.GetPath().pathString
        new_path = f"{anchor_path}/AMRs"

        if old_path != new_path:
            import omni.kit.commands as cmds
            if stage.GetPrimAtPath(new_path):
                stage.RemovePrim(new_path)
            cmds.execute("MovePrim", path_from=old_path, path_to=new_path)
            self._group = stage.GetPrimAtPath(new_path)
            self._group_path = new_path

            # 루트에 남은 옛 그룹이 있으면 정리
            if stage.GetPrimAtPath("/World/AMRs") and new_path != "/World/AMRs":
                stage.RemovePrim("/World/AMRs")

        # 그룹은 아이덴티티 TRS + 부모 상속
        gxf = UsdGeom.Xformable(self._group)
        try:
            gxf.SetResetXformStack(False)
            gxf.ClearXformOpOrder()
        except Exception:
            pass
        for p in list(self._group.GetProperties()):
            if p.GetName().startswith("xformOp:"):
                try:
                    self._group.RemoveProperty(p.GetName())
                except Exception:
                    pass

        gt = gxf.AddTranslateOp()
        gr = gxf.AddRotateXYZOp()
        gs = gxf.AddScaleOp()
        gxf.SetXformOpOrder([gt, gr, gs])
        gt.Set(Gf.Vec3d(0, 0, 0))
        gr.Set(Gf.Vec3d(0, 0, 0))
        gs.Set(Gf.Vec3d(1, 1, 1))
