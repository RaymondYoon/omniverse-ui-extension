# ui_code/Container/container_list_panel.py
from typing import Optional, Dict, Any, Callable
import re
import omni.ui as ui
from ui_code.ui.utils.common import _fill

_COL_TEXT = 0xFFFFFFFF
_COL_BG   = 0x000000A0

# 모델 enum → 표기 문자열
_MODEL_MAP = {1: "LR", 2: "LF", 3: "AR", 4: "AC", 5: "AF", 6: "P"}

class ContainerPanel:
    TITLE = "Container List"

    def __init__(self):
        self._win: Optional[ui.Window] = None
        self._data: Dict[str, Dict[str, Any]] = {}
        self._widgets: Dict[str, ui.Frame] = {}
        self._resolver: Optional[Callable[[], Optional[Dict[str, Dict[str, Any]]]]] = None

        # 콤보 선택 인덱스(ValueModel) - 둘 다 즉시 적용
        self._model_idx: Optional[ui.AbstractValueModel] = None
        self._status_idx: Optional[ui.AbstractValueModel] = None

        self._model_options  = ["All"]
        self._status_options = ["All", "On Map", "Off Map"]

        self._model_combo_frame: Optional[ui.Frame] = None
        self._debug = False

    def set_data_resolver(self, fn: Callable[[], Optional[Dict[str, Dict[str, Any]]]]):
        self._resolver = fn

    def show(self):
        if self._win:
            self._win.visible = True
            self.refresh_from_resolver()
            return

        self._win = ui.Window(self.TITLE, width=500, height=520,
                              style={"background_color": _COL_BG})
        with self._win.frame:
            with ui.VStack(spacing=8, padding=10, width=_fill()):
                ui.Label("Container List", style={"font_size": 18, "color": _COL_TEXT})

                with ui.HStack(spacing=8, width=_fill(), height=26):
                    # ── Model 콤보 (index 기반, 즉시 적용) ──
                    ui.Label("Model", style={"color": _COL_TEXT}, width=60)
                    self._model_combo_frame = ui.Frame()
                    with self._model_combo_frame:
                        cb_model = ui.ComboBox(0, *self._model_options)  # 초기 인덱스 0
                        self._model_idx = cb_model.model.get_item_value_model()
                        self._model_idx.set_value(0)  # 명시 초기화
                        self._model_idx.add_value_changed_fn(lambda *_: self.refresh())

                    # ── Status 콤보 (index 기반, 즉시 적용) ──
                    ui.Label("Status", style={"color": _COL_TEXT}, width=60)
                    cb_status = ui.ComboBox(0, *self._status_options)   # 초기 인덱스 0
                    self._status_idx = cb_status.model.get_item_value_model()
                    self._status_idx.set_value(0)  # 명시 초기화
                    self._status_idx.add_value_changed_fn(lambda *_: self.refresh())

                with ui.HStack(spacing=10, width=_fill()):
                    ui.Button("Reset", width=100, clicked_fn=self._on_reset)

                ui.Separator()
                self._scroll = ui.ScrollingFrame(height=380)
                with self._scroll:
                    self._list_stack = ui.VStack(spacing=4, width=_fill())

        self._win.visible = True
        self.refresh_from_resolver()

    @staticmethod
    def _canon_model(raw, container_code=None) -> str:
        try:
            if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.strip().isdigit()):
                iv = int(str(raw).strip())
                if iv in _MODEL_MAP:
                    return _MODEL_MAP[iv]
                return str(iv)
        except Exception:
            pass
        s = (str(raw) or "").strip().upper()
        if s and s not in ("-", "NONE"):
            if s.isdigit():
                return _MODEL_MAP.get(int(s), s)
            return s
        if container_code:
            m = re.match(r"[A-Z]+", str(container_code).upper())
            if m:
                return m.group(0)
        return "-"

    def update_data(self, containers: Dict[str, Dict[str, Any]] | list):
        prev_all = self._data
        norm: Dict[str, Dict[str, Any]] = {}

        def _normalize_one(d: Dict[str, Any], cid: str):
            d = dict(d or {})
            d.setdefault("containerCode", cid)

            raw_model = d.get("containerModelCode") or d.get("model")
            d["containerModelCode"] = self._canon_model(raw_model, d.get("containerCode"))

            if "inMapStatus" in d:
                d["inMapStatus"] = self._as_bool(d["inMapStatus"])
            elif "isOffMap" in d:
                d["inMapStatus"] = (not self._as_bool(d["isOffMap"]))
            else:
                prev = (prev_all or {}).get(cid)
                d["inMapStatus"] = self._as_bool(prev.get("inMapStatus")) if prev else False
            return d

        if isinstance(containers, dict):
            for k, v in containers.items():
                cid = str(k)
                norm[cid] = _normalize_one(v, cid)
        elif isinstance(containers, list):
            for i, it in enumerate(containers):
                cid = str((it or {}).get("containerCode") or (it or {}).get("id") or f"C{i+1:03d}")
                norm[cid] = _normalize_one(it, cid)

        self._data = norm

        # ── Model 콤보 옵션 갱신 (이전 선택 "라벨"로 복원) ──
        prev_label = "All"
        if self._model_idx:
            try:
                cur_i = self._model_idx.get_value_as_int()
                if 0 <= cur_i < len(self._model_options):
                    prev_label = self._model_options[cur_i]
            except Exception:
                pass

        models = ["All"] + sorted({d.get("containerModelCode", "-") for d in self._data.values()})
        if models != self._model_options:
            self._model_options = models
            if self._model_combo_frame:
                self._model_combo_frame.clear()
                with self._model_combo_frame:
                    cb_model = ui.ComboBox(0, *self._model_options)  # 새 콤보(0 선택)
                    self._model_idx = cb_model.model.get_item_value_model()
                    idx_map = {label: i for i, label in enumerate(self._model_options)}
                    self._model_idx.set_value(idx_map.get(prev_label, 0))
                    self._model_idx.add_value_changed_fn(lambda *_: self.refresh())

        self.refresh()

    def refresh_from_resolver(self):
        if self._resolver:
            got = self._resolver() or {}
            self.update_data(got)
        else:
            self.refresh()

    def refresh(self):
        if not hasattr(self, "_list_stack"):
            return
        self._list_stack.clear()
        self._widgets.clear()

        midx = self._model_idx.get_value_as_int() if self._model_idx else 0
        sidx = self._status_idx.get_value_as_int() if self._status_idx else 0

        model_filter  = self._model_options[midx]  if 0 <= midx < len(self._model_options) else "All"
        status_filter = self._status_options[sidx] if 0 <= sidx < len(self._status_options) else "All"

        if self._debug:
            print(f"[ContainerPanel] refresh(): model={model_filter}, status={status_filter}, items={len(self._data)}")

        any_item = False
        with self._list_stack:
            for cid, data in self._data.items():
                model_val = str(data.get("containerModelCode") or "-")
                if model_filter != "All" and model_val != model_filter:
                    continue
                in_map = self._as_bool(data.get("inMapStatus"))
                if status_filter == "On Map" and not in_map:
                    continue
                if status_filter == "Off Map" and in_map:
                    continue

                frame = self._build_item(cid, data)
                if frame is None:
                    continue
                any_item = True
                self._widgets[cid] = frame

        if not any_item:
            with self._list_stack:
                ui.Label("No containers to display.", style={"color": 0xAAAAAAFF})

    def _build_item(self, cid: str, data: Dict[str, Any]) -> Optional[ui.Frame]:
        in_map = self._as_bool(data.get("inMapStatus"))
        frame = ui.Frame(style={"background_color": 0x202020FF, "border_radius": 6},
                         height=60, width=_fill())
        with frame:
            with ui.HStack(spacing=6, padding=8, width=_fill()):
                dot_col = 0xFF00FF00 if in_map else 0xFF0000FF
                ui.Label("O", style={"color": dot_col, "font_size": 16}, width=16)

                ui.Label(f"{cid}", style={"color": _COL_TEXT, "font_size": 14}, width=140)
                ui.Label(f"Model: {data.get('containerModelCode', '-')}",
                         style={"color": _COL_TEXT}, width=180)
                ui.Label("On Map" if in_map else "Off Map",
                         style={"color": _COL_TEXT}, width=_fill())
        return frame

    def _on_reset(self):
        if self._model_idx:
            self._model_idx.set_value(0)
        if self._status_idx:
            self._status_idx.set_value(0)
        self.refresh()

    @staticmethod
    def _as_bool(v) -> bool:
        if isinstance(v, bool): return v
        if v is None: return False
        if isinstance(v, (int, float)): return int(v) != 0
        s = str(v).strip().lower()
        return s in ("1", "true", "t", "y", "yes", "on")
