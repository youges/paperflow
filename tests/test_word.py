import hashlib
from pathlib import Path
import zipfile

from docx import Document
from docx.oxml.ns import qn
import pymupdf
import pytest

from pdf_engine import Cancelled, PdfError, inspect_pdf
from word_engine import pdf_to_word
from test_engine import make_pdf


def word_text(path):
    from lxml import etree
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    return "".join(root.itertext(tag=qn("w:t")))


def test_editable_selection_order_password_and_original(tmp_path):
    path = make_pdf(tmp_path / "原稿.pdf", "WORD", 3, "secret")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    source = inspect_pdf(path, "secret")
    output = pdf_to_word(source, tmp_path / "结果.docx", pages="3,1")
    text = word_text(output)
    assert "WORD PAGE 1" in text and "WORD PAGE 3" in text and "WORD PAGE 2" not in text
    assert text.index("WORD PAGE 1") < text.index("WORD PAGE 3")
    assert len(Document(output).sections) == 2
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert not list(tmp_path.glob(".paperflow-*"))


def test_editable_chinese_and_table(tmp_path):
    path = tmp_path / "表格.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=595, height=842)
        page.insert_text((55, 65), "中文转换测试", fontname="china-s", fontsize=16)
        for y in (110, 150, 190):
            page.draw_line((50, y), (500, y), color=(0, 0, 0), width=1)
        for x in (50, 175, 500):
            page.draw_line((x, 110), (x, 190), color=(0, 0, 0), width=1)
        for x, y, text in ((65, 135, "项目"), (290, 135, "数量"), (65, 175, "设备"), (290, 175, "510")):
            page.insert_text((x, y), text, fontname="china-s", fontsize=12)
        document.save(path)
    output = pdf_to_word(inspect_pdf(path), tmp_path / "表格.docx")
    text = word_text(output)
    for value in ("中文转换测试", "项目", "数量", "设备", "510"):
        assert value in text
    assert Document(output).tables
    table = Document(output).tables[0]
    assert table.columns[1].width > table.columns[0].width * 2
    assert all(row.height_rule != 2 for row in table.rows)


def test_page_images_keep_rotation_dimensions_and_annotations(tmp_path):
    source = inspect_pdf(make_pdf(tmp_path / "图片模式.pdf", "IMAGE", 2))
    output = pdf_to_word(source, tmp_path / "图片模式.docx", mode="page_images", dpi=72)
    document = Document(output)
    assert not word_text(output)
    assert len(document.sections) == 2
    with pymupdf.open(source.path) as original:
        for section, page in zip(document.sections, original):
            assert abs(section.page_width.pt - page.rect.width) < 0.1
            assert abs(section.page_height.pt - page.rect.height) < 0.1
    with zipfile.ZipFile(output) as archive:
        assert len([name for name in archive.namelist() if name.startswith("word/media/")]) == 2
        assert archive.read("word/document.xml").count(b"<wp:anchor ") == 2


def test_scanned_pdf_does_not_pretend_to_create_editable_text(tmp_path):
    path = tmp_path / "扫描.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50))
        pixmap.clear_with(210)
        page.insert_image(page.rect, stream=pixmap.tobytes("png"))
        document.save(path)
    source = inspect_pdf(path)
    with pytest.raises(PdfError, match="OCR"):
        pdf_to_word(source, tmp_path / "扫描.docx")
    assert not (tmp_path / "扫描.docx").exists()
    assert pdf_to_word(source, tmp_path / "图片.docx", mode="page_images").is_file()


def test_overlapping_text_is_not_silently_discarded(tmp_path):
    path = tmp_path / "overlap.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((50, 100), "IMPORTANT TEXT", fontsize=12)
        page.insert_text((50, 100), "OVERLAY TEXT", fontsize=12)
        document.save(path)
    target = pdf_to_word(inspect_pdf(path), tmp_path / "overlap.docx")
    text = word_text(target)
    assert "IMPORTANT TEXT" in text and "OVERLAY TEXT" in text


def test_contents_entries_keep_separate_lines_and_right_tab_stops(tmp_path):
    path = tmp_path / "目录.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        for y, text in ((80, "目录"), (120, "第一章 概况 ........ 1"), (150, "第二章 条款 ........ 5"), (180, "第三章 要求 ........ 27")):
            page.insert_text((55, y), text, fontname="china-s", fontsize=12)
        document.save(path)
    target = pdf_to_word(inspect_pdf(path), tmp_path / "目录.docx")
    paragraphs = Document(target).paragraphs
    entries = [p for p in paragraphs if "\t" in p.text]
    assert len(entries) == 3
    assert entries[0].text.endswith("\t1") and entries[-1].text.endswith("\t27")
    assert all(len(p.paragraph_format.tab_stops) == 1 for p in entries)


@pytest.mark.parametrize("mode", ["editable", "page_images"])
def test_cancel_and_existing_output_are_preserved(tmp_path, mode):
    source = inspect_pdf(make_pdf(tmp_path / "源.pdf", "CANCEL", 3))
    target = tmp_path / "existing.docx"
    target.write_bytes(b"KEEP EXISTING")
    with pytest.raises(PdfError, match="已存在"):
        pdf_to_word(source, target)
    stop = False
    def progress(done, total, message):
        nonlocal stop
        stop = done > 0
    with pytest.raises(Cancelled):
        pdf_to_word(source, target, mode=mode, overwrite=True, progress=progress, cancel=lambda: stop)
    assert target.read_bytes() == b"KEEP EXISTING"
    assert not list(tmp_path.glob(".paperflow-*"))


def test_invalid_ranges_and_same_file_are_rejected(tmp_path):
    source = inspect_pdf(make_pdf(tmp_path / "source.pdf", "SAFE", 1))
    for options in ({"pages": "2"}, {"mode": "invalid"}, {"dpi": 600}):
        with pytest.raises(PdfError):
            pdf_to_word(source, tmp_path / "bad.docx", **options)
    with pytest.raises(PdfError):
        pdf_to_word(source, source.path, overwrite=True)
    assert not list(tmp_path.glob(".paperflow-*"))


def test_signed_pdf_visible_appearance_in_word_image_mode(tmp_path):
    fixture = Path(__file__).parent / "fixtures/signed-test.pdf"
    original_bytes = fixture.read_bytes()
    target = pdf_to_word(inspect_pdf(fixture), tmp_path / "签名.docx", mode="page_images", pages="2", dpi=72)
    with zipfile.ZipFile(target) as archive, pymupdf.open(fixture) as original:
        name = next(name for name in archive.namelist() if name.startswith("word/media/"))
        pixmap = pymupdf.Pixmap(archive.read(name))
        assert pixmap.samples == original[1].get_pixmap(dpi=72, alpha=False).samples
    assert fixture.read_bytes() == original_bytes
