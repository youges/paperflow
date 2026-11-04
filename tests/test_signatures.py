"""Self-signed fixture generated and cryptographically checked by tools/create_signed_fixture.py."""
from pathlib import Path

import pymupdf
import pytest

from pdf_engine import inspect_pdf, split_pdf

FIXTURE = Path(__file__).parent / "fixtures/signed-test.pdf"


@pytest.mark.parametrize("pages", ["", "2", "3,2"])
def test_signed_page_appearance_survives_split(tmp_path, pages):
    before = FIXTURE.read_bytes()
    source = inspect_pdf(FIXTURE)
    folder = split_pdf(source, tmp_path, pages=pages)
    indices = [0, 1, 2] if not pages else [1] if pages == "2" else [1, 2]
    with pymupdf.open(str(FIXTURE)) as original:
        assert any(w.is_signed for page in original for w in (page.widgets() or ()))
        for order, index in enumerate(indices):
            with pymupdf.open(str(folder / f"{order + 1}.pdf")) as single:
                assert single.page_count == 1
                assert single[0].rotation == original[index].rotation
                assert f"SIGNED DOCUMENT PAGE {index + 1}" in single[0].get_text()
                assert single[0].get_pixmap(dpi=144).samples == original[index].get_pixmap(dpi=144).samples
                assert not list(single[0].widgets() or ())
                assert len(list(single[0].annots() or ())) == len(list(original[index].annots() or ()))
    assert FIXTURE.read_bytes() == before


def test_opt_out_keeps_original_widget_copy_behavior(tmp_path):
    folder = split_pdf(inspect_pdf(FIXTURE), tmp_path, pages="2", preserve_signature_appearance=False)
    with pymupdf.open(str(FIXTURE)) as original, pymupdf.open(str(folder / "1.pdf")) as single:
        assert any(w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE for w in single[0].widgets())
        assert single[0].get_pixmap().samples == original[1].get_pixmap().samples


@pytest.mark.parametrize("format", ["png", "jpg"])
def test_signed_images_keep_visible_appearance(tmp_path, format):
    folder = split_pdf(inspect_pdf(FIXTURE), tmp_path, pages="2", output_format=format, dpi=72)
    with pymupdf.open(str(FIXTURE)) as original:
        expected = original[1].get_pixmap(dpi=72, alpha=False)
    actual = pymupdf.Pixmap(str(folder / f"1.{format}"))
    assert (actual.width, actual.height) == (expected.width, expected.height)
    if format == "png":
        assert actual.samples == expected.samples
    else:
        assert sum(abs(a - b) for a, b in zip(actual.samples, expected.samples)) / len(actual.samples) < 3


def test_unsigned_form_stays_editable(tmp_path):
    path = tmp_path / "form.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        widget = pymupdf.Widget()
        widget.field_name = "editable"
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        widget.field_value = "Keep editable"
        widget.rect = pymupdf.Rect(10, 10, 200, 50)
        page.add_widget(widget)
        doc.save(str(path))
    folder = split_pdf(inspect_pdf(path), tmp_path)
    with pymupdf.open(str(folder / "1.pdf")) as doc:
        assert list(doc[0].widgets())[0].field_value == "Keep editable"
