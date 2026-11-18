"""Shared application version and platform-specific locations."""
import os
from pathlib import Path

VERSION = "1.4.0"
UI_FONT = "Microsoft YaHei UI" if os.name == "nt" else "Noto Sans CJK SC"


def log_directory() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PaperFlow"
    state = os.environ.get("XDG_STATE_HOME")
    base = Path(state) if state and Path(state).is_absolute() else Path.home() / ".local/state"
    return base / "paperflow"
