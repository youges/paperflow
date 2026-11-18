"""Build and smoke-test the native Windows or Linux application."""
from pathlib import Path
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from app import app_icon, configure_application
from app_config import VERSION


def prepare_assets():
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    app = QApplication.instance() or QApplication([])
    configure_application(app)
    if not app_icon().pixmap(256, 256).save(str(assets / "paperflow.png"), "PNG"):
        raise RuntimeError("Failed to create PNG icon")
    if os.name == "nt" and not app_icon().pixmap(128, 128).save(str(assets / "paperflow.ico"), "ICO"):
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
    for name in ("pdf2docx", "python-docx", "numpy", "opencv-python-headless", "fonttools", "lxml", "typing_extensions", "fire", "termcolor"):
        dependency = importlib.metadata.distribution(name)
        destination = licenses / "dependencies" / f"{name}-{dependency.version}"
        for file in dependency.files or ():
            parts = file.parts
            if not parts or not parts[0].endswith(".dist-info"):
                continue
            if not any("licen" in part.lower() or "copying" in part.lower() or "notice" in part.lower() for part in parts[1:]):
                continue
            target = destination.joinpath(*parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(Path(dependency.locate_file(file)).read_bytes())
    distribution = importlib.metadata.distribution("pyinstaller")
    installed = next(Path(distribution.locate_file(file)) for file in distribution.files
                     if str(file).endswith("COPYING.txt"))
    (licenses / "PYINSTALLER-LICENSE.txt").write_bytes(installed.read_bytes())
    (ROOT / "LICENSE.txt").write_bytes((licenses / "AGPL-3.0.txt").read_bytes())
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.exists():
        python_license = Path(sys.base_prefix) / "LICENSE"
    if python_license.exists():
        (licenses / "PYTHON-LICENSE.txt").write_bytes(python_license.read_bytes())


def package():
    source = ROOT / "dist/PaperFlow-source.zip"
    files = [ROOT / name for name in (
        "app.py", "app_config.py", "launcher.py", "pdf_engine.py", "conversion_engine.py", "word_engine.py", "requirements.txt", "requirements-dev.txt",
        "README.md", "build.ps1", "build.sh", "THIRD_PARTY_NOTICES.md", "LICENSE.txt", ".gitignore", ".gitattributes",
    )]
    for folder in ("tests", "tools", "assets", "licenses", ".github", "packaging"):
        files.extend(path for path in (ROOT / folder).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    if os.name != "nt":
        with tarfile.open(ROOT / f"dist/PaperFlow-{VERSION}-Linux-x86_64.tar.gz", "w:gz") as archive:
            for path in [ROOT / "dist/PaperFlow", source, ROOT / "README.md", ROOT / "LICENSE.txt", ROOT / "THIRD_PARTY_NOTICES.md", ROOT / "licenses"]:
                archive.add(path, arcname="PaperFlow/" + path.name)
        return
    with zipfile.ZipFile(ROOT / "dist/PaperFlow-Windows.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in [ROOT / "dist/PaperFlow.exe", source, ROOT / "README.md", ROOT / "LICENSE.txt", ROOT / "THIRD_PARTY_NOTICES.md"]:
            archive.write(path, "PaperFlow/" + path.name)
        for path in (ROOT / "licenses").rglob("*"):
            if path.is_file():
                archive.write(path, "PaperFlow/licenses/" + path.relative_to(ROOT / "licenses").as_posix())


if __name__ == "__main__":
    os.chdir(ROOT)
    prepare_assets()
    build_env = os.environ.copy()
    windows = Path(os.environ.get("WINDIR", "C:/Windows"))
    # Third-party tools on PATH can carry obsolete UCRT DLLs. Never let a
    # developer's image/PDF tools shadow the Windows 10/11 system runtime.
    if os.name == "nt":
        build_env["PATH"] = os.pathsep.join([
        str(ROOT / ".venv/Scripts"), str(Path(sys.base_prefix)),
        str(Path(sys.base_prefix) / "DLLs"), str(windows / "System32"), str(windows),
    ])
    for variable in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        build_env.pop(variable, None)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "PaperFlow",
        "--exclude-module", "PySide6.QtQml", "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.QtTest", "launcher.py",
    ]
    if os.name == "nt":
        command.extend(["--icon", str(ROOT / "assets/paperflow.ico")])
    subprocess.run(command, check=True, env=build_env)
    checkdir = ROOT / "tmp/release-check"
    checkdir.mkdir(parents=True, exist_ok=True)
    (checkdir / "smoke.json").unlink(missing_ok=True)
    executable = ROOT / ("dist/PaperFlow.exe" if os.name == "nt" else "dist/PaperFlow")
    arguments = [str(executable), "--smoke-test", str(checkdir),
                 "--signature-fixture", str(ROOT / "tests/fixtures/signed-test.pdf")]
    if os.environ.get("PAPERFLOW_REQUIRE_OFFICE") == "1":
        sys.path.insert(0, str(ROOT / "tests"))
        from document_samples import make_docx, make_xlsx, make_pptx
        fixtures = checkdir / "office-fixtures"
        fixtures.mkdir(exist_ok=True)
        make_docx(fixtures / "word.docx")
        make_xlsx(fixtures / "excel.xlsx")
        make_pptx(fixtures / "slides.pptx")
        arguments.extend(["--document-fixtures", str(fixtures)])
    subprocess.run(arguments, check=True, env=build_env, timeout=180)
    report = json.loads((checkdir / "smoke.json").read_text(encoding="utf-8"))
    if not report.get("ok") or not report.get("frozen"):
        raise RuntimeError(f"Portable executable verification failed: {report}")
    package()
    subprocess.run([sys.executable, str(ROOT / "tools/build_installers.py")], check=True)
    print(f"Built and verified PaperFlow {VERSION} for {sys.platform}")
