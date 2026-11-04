from pathlib import Path

import pymupdf
import pytest

from pdf_engine import (
    Cancelled, PasswordRequired, PdfError, inspect_pdf, merge_pdfs, parse_pages,
    preview_page, split_pdf,
)


def make_pdf(path: Path, prefix: str, count: int = 3, password: str = ""):
    with pymupdf.open() as document:
        for index in range(count):
            page = document.new_page(width=320 + index * 20, height=440)
            page.draw_rect(pymupdf.Rect(20, 20, 100, 100), fill=(0.2, 0.55, 0.35))
            page.insert_text((30, 150), f"{prefix} PAGE {index + 1}", fontsize=18)
            if index == 1:
                page.set_rotation(90)
        options = dict(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner-password", user_pw=password) if password else {}
        document.save(str(path), **options)
    return path


@pytest.fixture
def source(tmp_path):
    return inspect_pdf(make_pdf(tmp_path / "原稿.pdf", "SOURCE"))


def texts(path):
    with pymupdf.open(str(path)) as document:
        return [page.get_text().strip() for page in document]


@pytest.mark.parametrize("offset", [0, 1, 2, 3])
def test_insert_into_existing_pdf_preserves_order_and_original(source, tmp_path, offset):
    first = inspect_pdf(make_pdf(tmp_path / "Z新文件.pdf", "NEW1", 2))
    second = inspect_pdf(make_pdf(tmp_path / "A新文件.pdf", "NEW2", 1))
    original_bytes = source.path.read_bytes()
    original = texts(source.path)
    result = merge_pdfs([first, second], tmp_path / "插入结果.pdf", base=source, insert_after=offset)
    assert texts(result) == original[:offset] + ["NEW1 PAGE 1", "NEW1 PAGE 2", "NEW2 PAGE 1"] + original[offset:]
    assert source.path.read_bytes() == original_bytes
    with pymupdf.open(str(result)) as doc:
        # Original second page and inserted second page both keep their rotation.
        assert sum(page.rotation == 90 for page in doc) == 2


def test_insert_rejects_invalid_position_and_protects_base(source, tmp_path):
    for position in (-1, 4, None):
        with pytest.raises(PdfError):
            merge_pdfs([source], tmp_path / "bad.pdf", base=source, insert_after=position)
    original = source.path.read_bytes()
    with pytest.raises(PdfError):
        merge_pdfs([source], source.path, base=source, insert_after=1, overwrite=True)
    assert source.path.read_bytes() == original
    assert not list(tmp_path.glob(".paperflow-*"))


def test_insert_encrypted_base_and_cancellation(tmp_path):
    base = inspect_pdf(make_pdf(tmp_path / "加密原件.pdf", "BASE", 2, "secret"), "secret")
    new = inspect_pdf(make_pdf(tmp_path / "new.pdf", "NEW", 1))
    result = merge_pdfs([new], tmp_path / "result.pdf", base=base, insert_after=1)
    assert texts(result) == ["BASE PAGE 1", "NEW PAGE 1", "BASE PAGE 2"]
    stop = False
    def progress(*args):
        nonlocal stop
        stop = True
    with pytest.raises(Cancelled):
        merge_pdfs([new], tmp_path / "cancel.pdf", base=base, insert_after=1, cancel=lambda: stop, progress=progress)
    assert not (tmp_path / "cancel.pdf").exists()
    assert not list(tmp_path.glob(".paperflow-*"))


def test_merge_follows_import_order_and_keeps_repeated_files(tmp_path):
    first = inspect_pdf(make_pdf(tmp_path / "Z文件1.pdf", "FIRST", 2))
    second = inspect_pdf(make_pdf(tmp_path / "A文件2.pdf", "SECOND", 1))
    result = merge_pdfs([first, second, first], tmp_path / "合并.pdf")
    assert texts(result) == ["FIRST PAGE 1", "FIRST PAGE 2", "SECOND PAGE 1", "FIRST PAGE 1", "FIRST PAGE 2"]
    with pymupdf.open(str(result)) as document:
        assert document[1].rotation == 90
    assert texts(first.path) == ["FIRST PAGE 1", "FIRST PAGE 2"]


def test_split_pdf_numeric_names_and_raster_content(source, tmp_path):
    folder = split_pdf(source, tmp_path, start=7, padding=3)
    assert sorted(path.name for path in folder.iterdir()) == ["007.pdf", "008.pdf", "009.pdf"]
    with pymupdf.open(str(source.path)) as original:
        for index in range(3):
            path = folder / f"{index + 7:03}.pdf"
            with pymupdf.open(str(path)) as single:
                assert single.page_count == 1
                assert single[0].get_text() == original[index].get_text()
                assert single[0].rotation == original[index].rotation
                assert single[0].get_pixmap().samples == original[index].get_pixmap().samples


@pytest.mark.parametrize("output_format", ["png", "jpg"])
def test_images_numeric_order_dimensions_and_content(source, tmp_path, output_format):
    folder = split_pdf(source, tmp_path, output_format=output_format, pages="3,1", start=1, padding=2, dpi=150)
    assert sorted(path.name for path in folder.iterdir()) == [f"01.{output_format}", f"02.{output_format}"]
    with pymupdf.open(str(source.path)) as original:
        for order, index in enumerate((0, 2)):
            pix = pymupdf.Pixmap(str(folder / f"{order + 1:02}.{output_format}"))
            expected = original[index].get_pixmap(dpi=150, colorspace=pymupdf.csRGB, alpha=False)
            assert (pix.width, pix.height) == (expected.width, expected.height)
            if output_format == "png":
                assert pix.samples == expected.samples
            else:
                assert sum(abs(a - b) for a, b in zip(pix.samples, expected.samples)) / len(pix.samples) < 2


def test_selected_pages_follow_document_order(source, tmp_path):
    folder = split_pdf(source, tmp_path, pages="3, 1, 1", start=0)
    assert texts(folder / "0.pdf") == ["SOURCE PAGE 1"]
    assert texts(folder / "1.pdf") == ["SOURCE PAGE 3"]


@pytest.mark.parametrize("text", ["0", "4", "3-1", "1,,2", "a", "1-999999999", "-1"])
def test_invalid_ranges_are_rejected(text):
    with pytest.raises(PdfError):
        parse_pages(text, 3)


def test_range_normalizes_chinese_punctuation():
    assert parse_pages("3，1－2、2", 3) == [0, 1, 2]
    assert parse_pages("", 3) == [0, 1, 2]


def test_existing_split_output_is_preserved(source, tmp_path):
    first = split_pdf(source, tmp_path)
    marker = first / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    second = split_pdf(source, tmp_path)
    assert second != first
    assert marker.read_text(encoding="utf-8") == "keep"
    assert len(list(second.glob("*.pdf"))) == 3


def test_merge_cannot_overwrite_source_or_existing_file(source, tmp_path):
    original = source.path.read_bytes()
    with pytest.raises(PdfError):
        merge_pdfs([source], source.path, overwrite=True)
    assert source.path.read_bytes() == original
    target = tmp_path / "existing.pdf"
    target.write_bytes(b"existing")
    with pytest.raises(PdfError):
        merge_pdfs([source], target)
    assert target.read_bytes() == b"existing"
    merge_pdfs([source], target, overwrite=True)
    assert len(texts(target)) == 3


def test_cancellation_leaves_no_partial_results(source, tmp_path):
    stop = False

    def progress(done, total, text):
        nonlocal stop
        stop = True

    with pytest.raises(Cancelled):
        split_pdf(source, tmp_path, progress=progress, cancel=lambda: stop)
    assert list(tmp_path.iterdir()) == [source.path]
    stop = False
    with pytest.raises(Cancelled):
        merge_pdfs([source], tmp_path / "cancelled.pdf", progress=progress, cancel=lambda: stop)
    assert list(tmp_path.iterdir()) == [source.path]


def test_failed_merge_keeps_existing_output_and_cleans_temporary(source, tmp_path):
    target = tmp_path / "existing.pdf"
    target.write_bytes(b"preserve-me")
    source.path.write_bytes(b"broken")
    with pytest.raises(PdfError):
        merge_pdfs([source], target, overwrite=True)
    assert target.read_bytes() == b"preserve-me"
    assert not list(tmp_path.glob(".paperflow-*"))


def test_password_pdf_can_be_imported_merged_and_split(tmp_path):
    path = make_pdf(tmp_path / "加密.pdf", "LOCKED", 1, "secret")
    with pytest.raises(PasswordRequired):
        inspect_pdf(path)
    with pytest.raises(PasswordRequired):
        inspect_pdf(path, "wrong")
    source = inspect_pdf(path, "secret")
    assert source.preview.startswith(b"\x89PNG")
    assert "secret" not in repr(source)
    result = merge_pdfs([source], tmp_path / "unlocked.pdf")
    assert texts(result) == ["LOCKED PAGE 1"]
    folder = split_pdf(source, tmp_path)
    assert texts(folder / "1.pdf") == ["LOCKED PAGE 1"]


def test_preview_and_corrupted_file(source, tmp_path):
    assert preview_page(source, 1).startswith(b"\x89PNG")
    with pytest.raises(PdfError):
        preview_page(source, 3)
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf")
    with pytest.raises(PdfError):
        inspect_pdf(broken)


def test_cancellation_before_start_creates_nothing(source, tmp_path):
    with pytest.raises(Cancelled):
        split_pdf(source, tmp_path, cancel=lambda: True)
    assert not list(tmp_path.glob(".paperflow-*"))


def test_forms_survive_merge_with_duplicate_names(tmp_path):
    paths = []
    for index in range(2):
        path = tmp_path / f"form{index}.pdf"
        with pymupdf.open() as document:
            page = document.new_page()
            widget = pymupdf.Widget()
            widget.field_name = "customer"
            widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            widget.field_value = f"Customer {index}"
            widget.rect = pymupdf.Rect(50, 50, 250, 100)
            page.add_widget(widget)
            document.save(str(path))
        paths.append(inspect_pdf(path))
    output = merge_pdfs(paths, tmp_path / "forms.pdf")
    with pymupdf.open(str(output)) as document:
        widgets = [list(page.widgets())[0] for page in document]
        assert [widget.field_value for widget in widgets] == ["Customer 0", "Customer 1"]
        assert len({widget.field_name for widget in widgets}) == 2
