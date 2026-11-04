"""Windowed entry point with startup diagnostics, including native-import failures."""
import os
from pathlib import Path
import sys
import traceback
from app_config import log_directory


def launch():
    logdir = log_directory()
    logdir.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(logdir / "startup.log", "a", encoding="utf-8")
    try:
        from app import main
        return main()
    except Exception:
        error = traceback.format_exc()
        (logdir / "startup.log").write_text(error, encoding="utf-8")
        if "--smoke-test" in sys.argv or "--gui-smoke-test" in sys.argv:
            import json
            flag = "--smoke-test" if "--smoke-test" in sys.argv else "--gui-smoke-test"
            folder = Path(sys.argv[sys.argv.index(flag) + 1])
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "smoke.json").write_text(json.dumps({"ok": False, "error": error}, ensure_ascii=False, indent=2), encoding="utf-8")
        elif os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"程序启动失败，错误详情已保存到：\n{logdir / 'startup.log'}", "纸序 PaperFlow", 0x10)
        return 1


if __name__ == "__main__":
    sys.exit(launch())
