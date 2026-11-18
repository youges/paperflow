from pathlib import Path
import os
import sys
import struct
import subprocess
import time

import pymupdf
import pytest

import conversion_engine as engine
from conversion_engine import convert_documents, find_libreoffice
from pdf_engine import Cancelled, PdfError
from document_samples import make_docx, make_xlsx, make_pptx


def content(path):
    with pymupdf.open(path) as document:
        return "".join(page.get_text() for page in document)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "gb18030", "utf-16"])
def test_text_unicode_encoding_pagination_and_long_lines(tmp_path, encoding):
    source = tmp_path / "中文说明.txt"
    source.write_text("中文测试 ABC\n" + "很长一行XYZ" * 180 + "\n" + "下一行\n" * 65, encoding=encoding)
    original = source.read_bytes()
    folder = convert_documents([source], tmp_path)
    output = folder / "中文说明.pdf"
    with pymupdf.open(output) as document:
        assert len(document) >= 3
        text = "".join(page.get_text() for page in document)
        assert "中文测试 ABC" in text
        assert text.count("很") == 180
        for page in document:
            for block in page.get_text("blocks"):
                assert block[0] >= 40 and block[2] < 555
                assert block[1] >= 30 and block[3] < 810
    assert source.read_bytes() == original


def test_batch_same_names_order_and_existing_results(tmp_path):
    left, right = tmp_path / "a", tmp_path / "b"
    left.mkdir()
    right.mkdir()
    a, b = left / "说明.txt", right / "说明.txt"
    a.write_text("FIRST", encoding="utf-8")
    b.write_text("SECOND", encoding="utf-8")
    folder = convert_documents([a, b, a], tmp_path)
    assert [content(folder / name).strip() for name in ("说明.pdf", "说明 (2).pdf", "说明 (3).pdf")] == ["FIRST", "SECOND", "FIRST"]
    merged = convert_documents([b, a], tmp_path, combine=True)
    assert merged != folder
    with pymupdf.open(merged / "合并结果.pdf") as document:
        assert [page.get_text().strip() for page in document] == ["SECOND", "FIRST"]
    assert len(list(merged.iterdir())) == 1
    assert (folder / "说明.pdf").is_file()


@pytest.mark.parametrize("extension", ["png", "jpg", "jpeg", "bmp", "tif", "tiff"])
def test_image_pixels_and_page_size(tmp_path, extension):
    # Qt supplies only synthetic input; production conversion uses MuPDF directly.
    from PySide6.QtGui import QImage, QColor
    image = QImage(160, 240, QImage.Format.Format_RGB32)
    image.fill(QColor("#21694b"))
    source = tmp_path / f"图片.{extension}"
    if not image.save(str(source)):
        pytest.skip(f"Qt cannot create a {extension} fixture")
    folder = convert_documents([source], tmp_path)
    with pymupdf.open(source) as original, pymupdf.open(folder / "图片.pdf") as result:
        assert result.page_count == original.page_count == 1
        assert result[0].rect == original[0].rect
        pix = result[0].get_pixmap(alpha=False)
        assert max(abs(a - b) for a, b in zip(pix.pixel(10, 10), (33, 105, 75))) <= 3


def test_failed_batch_and_cancel_leave_no_results(tmp_path):
    good = tmp_path / "good.txt"
    good.write_text("GOOD", encoding="utf-8")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(PdfError):
        convert_documents([good, bad], tmp_path)
    stop = False
    def progress(done, total, text):
        nonlocal stop
        stop = done == 1
    with pytest.raises(Cancelled):
        convert_documents([good, good], tmp_path, progress=progress, cancel=lambda: stop)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["bad.png", "good.txt"]


def test_multipage_tiff_keeps_all_pages(tmp_path):
    source = tmp_path / "多页.tiff"
    ifd_size, pixel_size = 126, 16 * 24 * 3
    bits_offset = 8 + 2 * ifd_size
    pixel_offset = bits_offset + 6
    data = bytearray(struct.pack("<2sHI", b"II", 42, 8))
    for index in range(2):
        entries = [(256, 4, 1, 16), (257, 4, 1, 24), (258, 3, 3, bits_offset),
                   (259, 3, 1, 1), (262, 3, 1, 2), (273, 4, 1, pixel_offset + pixel_size * index),
                   (277, 3, 1, 3), (278, 4, 1, 24), (279, 4, 1, pixel_size), (284, 3, 1, 1)]
        data.extend(struct.pack("<H", len(entries)))
        for entry in entries:
            data.extend(struct.pack("<HHII", *entry))
        data.extend(struct.pack("<I", 8 + ifd_size if index == 0 else 0))
    data.extend(struct.pack("<3H", 8, 8, 8))
    data.extend(bytes((255, 0, 0)) * (16 * 24))
    data.extend(bytes((0, 0, 255)) * (16 * 24))
    source.write_bytes(data)
    folder = convert_documents([source], tmp_path)
    with pymupdf.open(folder / "多页.pdf") as document:
        assert len(document) == 2
        assert document[0].get_pixmap().pixel(2, 2) == (255, 0, 0)
        assert document[1].get_pixmap().pixel(2, 2) == (0, 0, 255)


def test_missing_office_invalid_input_and_encoding(tmp_path, monkeypatch):
    docx = make_docx(tmp_path / "word.docx")
    monkeypatch.setattr(engine, "find_libreoffice", lambda *args: None)
    with pytest.raises(PdfError, match="LibreOffice"):
        convert_documents([docx], tmp_path)
    unsupported = tmp_path / "file.exe"
    unsupported.touch()
    with pytest.raises(PdfError, match="不支持"):
        convert_documents([unsupported], tmp_path)
    source = tmp_path / "file.txt"
    source.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(PdfError):
        convert_documents([source], tmp_path)
    assert not list(tmp_path.glob(".paperflow-*"))


@pytest.fixture(scope="module")
def office():
    executable = find_libreoffice()
    if executable is None:
        if os.environ.get("PAPERFLOW_REQUIRE_OFFICE") == "1":
            pytest.fail("LibreOffice is mandatory for CI integration tests")
        pytest.skip("LibreOffice is not installed")
    return executable


@pytest.mark.parametrize("factory,extension,tag", [(make_docx, "docx", "WORD SAMPLE"), (make_xlsx, "xlsx", "EXCEL SAMPLE"), (make_pptx, "pptx", "POWERPOINT SAMPLE")])
def test_real_office_conversion(office, tmp_path, factory, extension, tag):
    source = factory(tmp_path / f"中文样例.{extension}")
    original = source.read_bytes()
    folder = convert_documents([source], tmp_path, libreoffice=str(office))
    output = folder / "中文样例.pdf"
    assert tag in content(output)
    assert "中文测试" in content(output).replace(" ", "")
    assert source.read_bytes() == original
    assert not list(tmp_path.glob(".paperflow-*"))


@pytest.mark.parametrize("factory,input_ext,legacy_ext,tag", [(make_docx, "docx", "doc", "WORD SAMPLE"), (make_xlsx, "xlsx", "xls", "EXCEL SAMPLE"), (make_pptx, "pptx", "ppt", "POWERPOINT SAMPLE")])
def test_legacy_office_formats(office, tmp_path, factory, input_ext, legacy_ext, tag):
    source = factory(tmp_path / f"legacy.{input_ext}")
    subprocess.run([str(office), f"-env:UserInstallation={(tmp_path / 'fixture-profile').as_uri()}",
                    "--headless", "--convert-to", legacy_ext, "--outdir", str(tmp_path), str(source)],
                   check=True, timeout=90, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    legacy = source.with_suffix("." + legacy_ext)
    assert legacy.is_file(), "LibreOffice could not generate the synthetic legacy fixture"
    folder = convert_documents([legacy], tmp_path, libreoffice=str(office))
    assert tag in content(folder / "legacy.pdf")


def test_office_long_output_directory_and_inherited_environment(office, tmp_path, monkeypatch):
    source = make_docx(tmp_path / "word.docx")
    first, second = "nested-output-" * 6, "more-subfolders-" * 5
    if os.name == "nt":
        # Exercise nested output without requiring Windows' optional long-path
        # registry policy just to create the fixture itself.
        available = max(8, 180 - len(str(tmp_path)) - 2)
        first, second = first[:available // 2], second[:available - available // 2]
    destination = tmp_path / first / second
    destination.mkdir(parents=True)
    poison = tmp_path / "unrelated-runtime"
    poison.mkdir()
    monkeypatch.setenv("PATH", str(poison) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("PYTHONHOME", str(poison))
    monkeypatch.setenv("PYTHONPATH", str(poison))
    monkeypatch.setenv("QT_PLUGIN_PATH", str(poison))
    folder = convert_documents([source], destination, libreoffice=str(office))
    assert "WORD SAMPLE" in content(folder / "word.pdf")
    assert os.environ["PYTHONHOME"] == str(poison)


def test_office_failure_exit_zero_and_timeout_cleanup(tmp_path, monkeypatch):
    source = make_docx(tmp_path / "file.docx")
    monkeypatch.setattr(engine, "find_libreoffice", lambda *args: Path(sys.executable))
    # Launch a real child process so timeout, exit-zero and cleanup are exercised.
    real_popen = engine.subprocess.Popen
    for code, timeout, match in [("pass", 10, "无法转换"), ("import time; time.sleep(60)", 0.25, "超时")]:
        children = []
        def launch(command, **options):
            if Path(command[0]).stem.lower() == "taskkill":
                return real_popen(command, **options)
            child = real_popen([sys.executable, "-c", code], **options)
            children.append(child)
            return child
        monkeypatch.setattr(engine.subprocess, "Popen", launch)
        with pytest.raises(PdfError, match=match):
            convert_documents([source], tmp_path, office_timeout=timeout)
        assert all(child.poll() is not None for child in children)
        assert not list(tmp_path.glob(".paperflow-*"))


def test_office_cancellation_terminates_owned_child(tmp_path, monkeypatch):
    source = make_docx(tmp_path / "file.docx")
    monkeypatch.setattr(engine, "find_libreoffice", lambda *args: Path(sys.executable))
    real_popen = engine.subprocess.Popen
    children = []
    def launch(command, **options):
        child = real_popen([sys.executable, "-c", "import time; time.sleep(60)"], **options)
        children.append(child)
        return child
    monkeypatch.setattr(engine.subprocess, "Popen", launch)
    # Bypass the test's Popen interceptor for Windows taskkill.
    real_terminate = engine._terminate
    def terminate(process):
        monkeypatch.setattr(engine.subprocess, "Popen", real_popen)
        real_terminate(process)
    monkeypatch.setattr(engine, "_terminate", terminate)
    started = time.monotonic()
    with pytest.raises(Cancelled):
        convert_documents([source], tmp_path, cancel=lambda: bool(children) and time.monotonic() - started > 0.25)
    assert children and children[0].poll() is not None
    assert not list(tmp_path.glob(".paperflow-*"))
