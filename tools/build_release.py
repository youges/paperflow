"""Build a portable Windows executable and a source-inclusive release ZIP."""
from pathlib import Path
import json
import os
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from app import app_icon, configure_application


def prepare_assets():
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    app = QApplication.instance() or QApplication([])
    configure_application(app)
    if not app_icon().pixmap(128, 128).save(str(assets / "paperflow.ico"), "ICO"):
        raise RuntimeError("Failed to create app icon")
    licenses = ROOT / "licenses"
    licenses.mkdir(exist_ok=True)
    for name, url in {
        "AGPL-3.0.txt": "https://raw.githubusercontent.com/spdx/license-list-data/main/text/AGPL-3.0-only.txt",
        "LGPL-3.0.txt": "https://raw.githubusercontent.com/spdx/license-list-data/main/text/LGPL-3.0-only.txt",
        "GPL-3.0.txt": "https://raw.githubusercontent.com/spdx/license-list-data/main/text/GPL-3.0-only.txt",
    }.items():
        target = licenses / name
        if target.exists():
            continue
        request = urllib.request.Request(url, headers={"User-Agent": "PaperFlow-build/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
        target.write_bytes(data)
    import importlib.metadata
    distribution = importlib.metadata.distribution("pyinstaller")
    installed = next(Path(distribution.locate_file(file)) for file in distribution.files
                     if str(file).endswith("COPYING.txt"))
    (licenses / "PYINSTALLER-LICENSE.txt").write_bytes(installed.read_bytes())
    (ROOT / "LICENSE.txt").write_bytes((licenses / "AGPL-3.0.txt").read_bytes())
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.exists():
        python_license = Path(sys.base_prefix) / "LICENSE"
    (licenses / "PYTHON-LICENSE.txt").write_bytes(python_license.read_bytes())


def package():
    source = ROOT / "dist/PaperFlow-source.zip"
    files = [ROOT / name for name in (
        "app.py", "launcher.py", "pdf_engine.py", "requirements.txt", "requirements-dev.txt",
        "README.md", "build.ps1", "THIRD_PARTY_NOTICES.md", "LICENSE.txt", ".gitignore",
    )]
    for folder in ("tests", "tools", "assets", "licenses", ".github"):
        files.extend(path for path in (ROOT / folder).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(ROOT / "dist/PaperFlow-Windows.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in [ROOT / "dist/PaperFlow.exe", source, ROOT / "README.md", ROOT / "LICENSE.txt", ROOT / "THIRD_PARTY_NOTICES.md"]:
            archive.write(path, "PaperFlow/" + path.name)
        for path in (ROOT / "licenses").iterdir():
            archive.write(path, "PaperFlow/licenses/" + path.name)


if __name__ == "__main__":
    os.chdir(ROOT)
    prepare_assets()
    build_env = os.environ.copy()
    windows = Path(os.environ.get("WINDIR", "C:/Windows"))
    # Third-party tools on PATH can carry obsolete UCRT DLLs. Never let a
    # developer's image/PDF tools shadow the Windows 10/11 system runtime.
    build_env["PATH"] = os.pathsep.join([
        str(ROOT / ".venv/Scripts"), str(Path(sys.base_prefix)),
        str(Path(sys.base_prefix) / "DLLs"), str(windows / "System32"), str(windows),
    ])
    for variable in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        build_env.pop(variable, None)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "PaperFlow", "--icon", str(ROOT / "assets/paperflow.ico"),
        "--exclude-module", "PySide6.QtQml", "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.QtTest", "launcher.py",
    ], check=True, env=build_env)
    checkdir = ROOT / "tmp/release-check"
    checkdir.mkdir(parents=True, exist_ok=True)
    (checkdir / "smoke.json").unlink(missing_ok=True)
    subprocess.run([str(ROOT / "dist/PaperFlow.exe"), "--smoke-test", str(checkdir),
                    "--signature-fixture", str(ROOT / "tests/fixtures/signed-test.pdf")],
                   check=True, env=build_env, timeout=60)
    report = json.loads((checkdir / "smoke.json").read_text(encoding="utf-8"))
    if not report.get("ok") or not report.get("frozen"):
        raise RuntimeError(f"Portable executable verification failed: {report}")
    package()
    print("Built dist/PaperFlow.exe and dist/PaperFlow-Windows.zip")
