"""Exercise installation, installed GUI/PDF operations, and uninstallation in CI."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_config import VERSION


def smoke(executable, output, graphical=False):
    flag = "--gui-smoke-test" if graphical else "--smoke-test"
    command = [str(executable), flag, str(output), "--signature-fixture", str(ROOT / "tests/fixtures/signed-test.pdf")]
    environment = os.environ.copy()
    if graphical:
        environment["QT_QPA_PLATFORM"] = "xcb"
        environment["QT_OPENGL"] = "software"
        command = ["xvfb-run", "-a"] + command
    subprocess.run(command, check=True, timeout=90, env=environment)
    report = json.loads((output / "smoke.json").read_text(encoding="utf-8"))
    assert report.get("ok") and report.get("frozen"), report
    assert "signed_pdf_visible_appearance" in report["checks"], report


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="paperflow-install-check-") as folder:
        temporary = Path(folder)
        if os.name == "nt":
            target = temporary / "installed"
            setup = ROOT / f"dist/PaperFlow-{VERSION}-Windows-x64-Setup.exe"
            subprocess.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", f"/DIR={target}"], check=True, timeout=90)
            executable = target / "PaperFlow.exe"
            assert executable.is_file() and (target / "PaperFlow-source.zip").is_file()
            smoke(executable, temporary / "installed-smoke")
            subprocess.run([str(target / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True, timeout=90)
            for _ in range(40):
                if not executable.exists():
                    break
                time.sleep(0.25)
            assert not executable.exists(), "Uninstaller left application executable behind"
        else:
            deb = ROOT / f"dist/paperflow_{VERSION}_amd64.deb"
            subprocess.run(["sudo", "apt-get", "install", "-y", str(deb)], check=True)
            assert Path("/usr/bin/paperflow").exists()
            assert Path("/opt/paperflow/PaperFlow-source.zip").exists()
            subprocess.run(["desktop-file-validate", "/usr/share/applications/paperflow.desktop"], check=True)
            smoke(Path("/usr/bin/paperflow"), temporary / "installed-smoke", graphical=True)
            subprocess.run(["sudo", "dpkg", "--remove", "paperflow"], check=True)
            assert not Path("/usr/bin/paperflow").exists()
            assert not Path("/usr/share/applications/paperflow.desktop").exists()
    print(f"Installed application and uninstall verification passed on {sys.platform}.")
