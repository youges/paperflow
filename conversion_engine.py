"""Offline document conversion with isolated LibreOffice processes and batch cleanup."""
from __future__ import annotations

import codecs
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Callable, Iterable

import pymupdf

from pdf_engine import Cancelled, PdfError, Progress, _check, inspect_pdf, merge_pdfs


OFFICE_EXTENSIONS = frozenset({".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp"})
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"})
SUPPORTED_EXTENSIONS = OFFICE_EXTENSIONS | IMAGE_EXTENSIONS | {".txt"}
FILE_FILTER = "支持的文档 (*.doc *.docx *.odt *.rtf *.xls *.xlsx *.ods *.ppt *.pptx *.odp *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.txt)"


def find_libreoffice(configured: str = "") -> Path | None:
    """A user-selected executable takes precedence; never execute a shell string."""
    if configured.strip():
        path = Path(configured.strip()).expanduser()
        if path.name.lower() == "soffice.exe" and path.with_suffix(".com").is_file():
            path = path.with_suffix(".com")
        return path.resolve() if path.is_file() else None
    candidates = [os.environ.get("PAPERFLOW_LIBREOFFICE", "")]
    candidates += [shutil.which(name) or "" for name in ("soffice.com", "soffice", "libreoffice")]
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", "C:/Program Files"), os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")):
            candidates.extend(str(Path(base) / "LibreOffice/program" / name) for name in ("soffice.com", "soffice.exe"))
    else:
        candidates.extend(("/usr/bin/libreoffice", "/usr/bin/soffice", "/opt/libreoffice/program/soffice"))
    return next((Path(path).resolve() for path in candidates if path and Path(path).is_file()), None)


def validate_inputs(paths: Iterable[Path | str]) -> list[Path]:
    result = [Path(path).resolve() for path in paths]
    if not result:
        raise PdfError("请先添加需要转换的文档。")
    for path in result:
        if not path.is_file():
            raise PdfError(f"找不到文件：{path.name}")
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise PdfError(f"不支持的格式：{path.name}")
    return result


def _terminate(process: subprocess.Popen) -> None:
    # Only terminate the process tree launched with our private user profile.
    # Never kill by executable name: the user's interactive LibreOffice stays open.
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=15, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=15)


def _office_pdf(source: Path, output: Path, executable: Path, workspace: Path,
                cancel: Callable[[], bool] | None, timeout: float) -> None:
    # Convert a copy and disable macros. A fresh profile avoids locks from open
    # LibreOffice windows and does not change the user's preferences.
    incoming, converted = workspace / "input", workspace / "output"
    incoming.mkdir()
    converted.mkdir()
    local_source = incoming / ("document" + source.suffix.lower())
    shutil.copyfile(source, local_source)
    profile = workspace / "profile"
    security = profile / "user"
    security.mkdir(parents=True)
    (security / "registrymodifications.xcu").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
        '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
        '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
        '</item></oor:items>', encoding="utf-8")
    command = [str(executable), f"-env:UserInstallation={profile.as_uri()}",
               "--headless", "--nologo", "--nodefault", "--nofirststartwizard",
               "--convert-to", "pdf", "--outdir", str(converted), str(local_source)]
    environment = os.environ.copy()
    # PyInstaller points these at its own Qt; LO must load its own runtime.
    for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_PLATFORM", "QML2_IMPORT_PATH"):
        environment.pop(key, None)
    if "LD_LIBRARY_PATH_ORIG" in environment:
        environment["LD_LIBRARY_PATH"] = environment["LD_LIBRARY_PATH_ORIG"]
    else:
        environment.pop("LD_LIBRARY_PATH", None)
    environment["SAL_USE_VCLPLUGIN"] = "svp"
    frozen_directory = getattr(sys, "_MEIPASS", "")
    if frozen_directory:
        environment["PATH"] = os.pathsep.join(
            part for part in environment.get("PATH", "").split(os.pathsep)
            if not part.casefold().startswith(str(frozen_directory).casefold()))
    options = ({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
               if os.name == "nt" else {"start_new_session": True})
    started = time.monotonic()
    with (workspace / "office.log").open("wb") as log:
        try:
            if os.name == "nt" and frozen_directory:
                import ctypes
                ctypes.windll.kernel32.SetDllDirectoryW(None)
            try:
                process = subprocess.Popen(command, cwd=workspace, env=environment, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=log, **options)
            finally:
                if os.name == "nt" and frozen_directory:
                    ctypes.windll.kernel32.SetDllDirectoryW(str(frozen_directory))
        except OSError as exc:
            raise PdfError("无法启动 LibreOffice，请检查转换组件路径。") from exc
        try:
            while process.poll() is None:
                _check(cancel)
                if time.monotonic() - started >= timeout:
                    raise PdfError(f"{source.name} 转换超时，请检查文件是否加密或损坏。")
                time.sleep(0.1)
            _check(cancel)
        finally:
            if process.poll() is None:
                _terminate(process)
    generated = converted / "document.pdf"
    if process.returncode != 0 or not generated.is_file():
        # LO can exit successfully without producing a PDF (e.g. password files).
        raise PdfError(f"无法转换 {source.name}，请检查是否加密、损坏，或缺少对应的 LibreOffice 组件。")
    shutil.move(generated, output)


def _read_text(source: Path, encoding: str) -> str:
    data = source.read_bytes()
    if encoding == "auto":
        if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            choices = ["utf-16"]
        else:
            choices = ["utf-8-sig", "gb18030"]
    elif encoding in {"utf-8-sig", "utf-16", "gb18030"}:
        choices = [encoding]
    else:
        raise PdfError("TXT 编码选项无效。")
    for choice in choices:
        try:
            text = data.decode(choice)
            if "\x00" in text:
                raise PdfError(f"{source.name} 包含无效文本，请选择正确的 TXT 编码。")
            return text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
        except UnicodeError:
            continue
    raise PdfError(f"无法读取 {source.name}，请手动选择 TXT 编码。")


def _text_pdf(source: Path, output: Path, encoding: str, cancel) -> None:
    text = _read_text(source, encoding)
    font = pymupdf.Font("cjk")  # Bundled Unicode fallback: no installed CJK font required.
    font_size, line_height = 11, 17
    width, height, margin = 595, 842, 42
    with pymupdf.open() as document:
        page = document.new_page(width=width, height=height)
        writer = pymupdf.TextWriter(page.rect)
        y = margin + font_size

        def emit(line):
            nonlocal page, writer, y
            _check(cancel)
            if y > height - margin:
                writer.write_text(page)
                page = document.new_page(width=width, height=height)
                writer = pymupdf.TextWriter(page.rect)
                y = margin + font_size
            if line:
                writer.append((margin, y), line, font=font, fontsize=font_size)
            y += line_height

        for paragraph in text.split("\n"):
            _check(cancel)
            line, used = [], 0.0
            for index, character in enumerate(paragraph):
                if index % 1024 == 0:
                    _check(cancel)
                advance = font.glyph_advance(ord(character)) * font_size
                if used + advance > width - 2 * margin and line:
                    emit("".join(line))
                    line, used = [], 0.0
                line.append(character)
                used += advance
            emit("".join(line))
        writer.write_text(page)
        document.set_metadata({"title": source.stem, "creator": "PaperFlow 纸序"})
        document.save(output, garbage=4, deflate=True)


def _image_pdf(source: Path, output: Path, cancel) -> None:
    with pymupdf.open(source) as image:
        _check(cancel)
        data = image.convert_to_pdf()
    with pymupdf.open("pdf", data) as document:
        _check(cancel)
        document.set_metadata({"title": source.stem, "creator": "PaperFlow 纸序"})
        document.save(output, garbage=4, deflate=True)


def convert_documents(paths: Iterable[Path | str], output_parent: Path | str, *,
                      combine: bool = False, libreoffice: str = "", text_encoding: str = "auto",
                      progress: Progress | None = None, cancel: Callable[[], bool] | None = None,
                      office_timeout: float = 180) -> Path:
    """All-or-nothing batch: return a new directory, never overwrite an original/result."""
    sources = validate_inputs(paths)
    parent = Path(output_parent).resolve()
    if not parent.is_dir():
        raise PdfError("保存文件夹不存在，请重新选择。")
    executable = find_libreoffice(libreoffice)
    if any(path.suffix.lower() in OFFICE_EXTENSIONS for path in sources) and executable is None:
        raise PdfError("Office 文档转换需要 LibreOffice（Writer、Calc、Impress）。请安装后点击「重新检测」，或选择 soffice 程序路径。图片和 TXT 可直接转换。")
    _check(cancel)
    with tempfile.TemporaryDirectory(prefix=".paperflow-convert-", dir=parent) as temporary:
        staging = Path(temporary)
        results = staging / "results"
        results.mkdir()
        used: set[str] = set()
        converted = []
        for index, source in enumerate(sources):
            _check(cancel)
            name = source.stem[:100]
            suffix = 1
            target_name = name + ".pdf"
            while target_name.casefold() in used:
                suffix += 1
                target_name = f"{name} ({suffix}).pdf"
            used.add(target_name.casefold())
            target = results / target_name
            if progress:
                progress(index, len(sources), f"正在转换：{source.name}")
            try:
                extension = source.suffix.lower()
                if extension in OFFICE_EXTENSIONS:
                    workspace = staging / f"office-{index}"
                    workspace.mkdir()
                    _office_pdf(source, target, executable, workspace, cancel, office_timeout)
                elif extension == ".txt":
                    _text_pdf(source, target, text_encoding, cancel)
                else:
                    _image_pdf(source, target, cancel)
                converted.append(inspect_pdf(target))
            except (PdfError, Cancelled):
                raise
            except Exception as exc:
                raise PdfError(f"无法转换 {source.name}，请检查文件内容和保存位置。") from exc
            if progress:
                progress(index + 1, len(sources), f"已转换：{source.name}")
        if combine:
            merged = staging / "合并结果.pdf"
            merge_pdfs(converted, merged, cancel=cancel)
            for source in converted:
                source.path.unlink()
            shutil.move(merged, results / "合并结果.pdf")
        _check(cancel)
        # Reserve the result name without overwriting another process's directory.
        for number in range(1, 10000):
            folder = parent / ("文档转PDF" if number == 1 else f"文档转PDF ({number})")
            try:
                folder.mkdir()
            except FileExistsError:
                continue
            try:
                for target in results.iterdir():
                    target.rename(folder / target.name)
            except BaseException:
                shutil.rmtree(folder)
                raise
            return folder
        raise PdfError("同名结果文件夹过多，请更换保存位置。")
