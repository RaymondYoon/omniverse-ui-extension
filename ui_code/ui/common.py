from pathlib import Path
import omni.ui as ui

__all__ = ["_fill", "ASSET_DIR", "_file_uri", "_fmt_status", "_fmt_lift"]

def _fill():
    return ui.Fraction(1)

# 이 파일 경로: platform_ext/ui_code/ui/common.py
# resource 폴더: platform_ext/resource
ASSET_DIR = Path(__file__).resolve().parents[2] / "resource"

def _file_uri(p: Path) -> str:
    posix = p.resolve().as_posix()
    return f"file:///{posix}" if ":" in posix[:10] else f"file://{posix}"

_STATUS_MAP = {
    1: "EXIT", 2: "OFFLINE", 3: "IDLE", 4: "INTASK",
    5: "CHARGING", 6: "UPDATING", 7: "EXCEPTION",
}

def _fmt_status(v):
    if isinstance(v, (int, float)):
        return _STATUS_MAP.get(int(v), str(int(v)))
    s = (str(v) if v is not None else "-").strip()
    if s.isdigit():
        return _STATUS_MAP.get(int(s), s)
    return s.upper() if s else "-"

def _fmt_lift(v):
    return "Up" if v is True or v == 1 else "Down" if v is False or v == 0 else "-"
