"""Create an Inno Setup installer or a Debian package from the verified binary."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_config import VERSION


def windows_installer():
    compiler = shutil.which("ISCC.exe")
    if not compiler:
        for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
            path = Path(base) / "Inno Setup 6/ISCC.exe"
            if path.is_file():
                compiler = str(path)
                break
    if not compiler:
        raise RuntimeError("Inno Setup 6 is required to create the Windows installer.")
    subprocess.run([compiler, f"/DAppVersion={VERSION}", f"/O{ROOT / 'dist'}",
                    str(ROOT / "packaging/windows/installer.iss")], check=True)


def linux_installer():
    stage = ROOT / f"build/deb-{VERSION}"
    # An existing staging tree is left intact; fresh CI workspaces are expected.
    if stage.exists():
        raise RuntimeError(f"Staging directory already exists: {stage}")
    appdir = stage / "opt/paperflow"
    appdir.mkdir(parents=True)
    shutil.copy2(ROOT / "dist/PaperFlow", appdir / "PaperFlow")
    (appdir / "PaperFlow").chmod(0o755)
    shutil.copy2(ROOT / "dist/PaperFlow-source.zip", appdir / "PaperFlow-source.zip")
    for name in ("LICENSE.txt", "THIRD_PARTY_NOTICES.md", "README.md"):
        shutil.copy2(ROOT / name, appdir / name)
    shutil.copytree(ROOT / "licenses", appdir / "licenses")
    binary = stage / "usr/bin"
    binary.mkdir(parents=True)
    (binary / "paperflow").symlink_to("/opt/paperflow/PaperFlow")
    desktop = stage / "usr/share/applications"
    desktop.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging/linux/paperflow.desktop", desktop / "paperflow.desktop")
    icons = stage / "usr/share/icons/hicolor/256x256/apps"
    icons.mkdir(parents=True)
    shutil.copy2(ROOT / "assets/paperflow.png", icons / "paperflow.png")
    control = stage / "DEBIAN"
    control.mkdir()
    installed_kib = sum(path.stat().st_size for path in stage.rglob('*') if path.is_file() and not path.is_symlink()) // 1024 + 1
    (control / "control").write_text(
        f"Package: paperflow\nVersion: {VERSION}\nArchitecture: amd64\n"
        "Maintainer: youges <96408349+youges@users.noreply.github.com>\n"
        "Section: office\nPriority: optional\n"
        f"Installed-Size: {installed_kib}\n"
        "Depends: libc6 (>= 2.39), libstdc++6, libgcc-s1, libglib2.0-0, libgl1, libegl1, libopengl0, "
        "libfontconfig1, libdbus-1-3, libx11-6, libx11-xcb1, libxext6, libxrender1, libxi6, libsm6, libice6, "
        "libxcb1, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, "
        "libxcb-xinerama0, libxcb-xkb1, libxcb-shape0, libxcb-randr0, libxcb-sync1, libxcb-xfixes0, "
        "libxcb-glx0, libxcb-shm0, libxcb-render0, libxcb-util1, libxkbcommon0, libxkbcommon-x11-0\n"
        "Recommends: fonts-noto-cjk, libreoffice-writer, libreoffice-calc, libreoffice-impress\nHomepage: https://github.com/youges/paperflow\n"
        "Description: Local PDF merge, splitting and document conversion tool\n"
        " Supports ordered merging, page splitting, PDF-to-Word and Office/image/text-to-PDF conversion.\n",
        encoding="utf-8")
    subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(stage),
                    str(ROOT / f"dist/paperflow_{VERSION}_amd64.deb")], check=True)


if __name__ == "__main__":
    windows_installer() if os.name == "nt" else linux_installer()
