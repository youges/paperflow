"""Shared application version and platform-specific locations."""
import os
from pathlib import Path

VERSION = "1.2.0"
UI_FONT = "Microsoft YaHei UI" if os.name == "nt" else "Noto Sans CJK SC"


def log_directory() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PaperFlow"
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "paperflow"
