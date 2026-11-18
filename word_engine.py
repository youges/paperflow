"""Local PDF-to-DOCX conversion with editable layout or full-page images."""
from __future__ import annotations

from io import BytesIO
import math
import os
import re
from pathlib import Path
import tempfile
from statistics import median

import pymupdf

from pdf_engine import PdfError, PdfSource, Progress, _check, _same_file, open_pdf, parse_pages


def _contents_page(page):
    """Recognize a plain static contents page without dropping other content."""
    lines = [line.strip() for line in page.get_text().splitlines() if line.strip()]
    heading = next((i for i, line in enumerate(lines) if re.fullmatch(r"目\s*录|contents|table\s+of\s+contents", line, re.IGNORECASE)), None)
    if heading is None or page.get_images():
        return None
    entries = []
    for line in lines[heading + 1:]:
        match = re.fullmatch(r"(.+?)\s*\.{3,}\s*(\d+)\s*", line)
        if match is None:
            return None
        entries.append((match[1].strip(), match[2]))
    return (lines[:heading], lines[heading], entries) if len(entries) >= 3 else None


def _make_contents(document, page, contents):
    """Use real right-aligned tab stops instead of reflowing dot-leader runs."""
    from docx.enum.section import WD_SECTION_START
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
    from docx.oxml.ns import qn
    from docx.shared import Pt

    section = document.add_section(WD_SECTION_START.NEW_PAGE) if document.paragraphs else document.sections[0]
    section.page_width, section.page_height = Pt(page.rect.width), Pt(page.rect.height)
    section.top_margin, section.bottom_margin = Pt(41), Pt(42)
    section.left_margin = section.right_margin = Pt(54)

    def paragraph(text, size):
        item = document.add_paragraph()
        item.paragraph_format.space_before = item.paragraph_format.space_after = Pt(0)
        run = item.add_run(text)
        run.font.name = "SimSun"
        run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "宋体")
        run.font.size = Pt(size)
        return item

    headers, title, entries = contents
    for header in headers:
        item = paragraph(header, 8)
        item.paragraph_format.space_after = Pt(20)
    item = paragraph(title, 16)
    item.alignment = WD_ALIGN_PARAGRAPH.CENTER
    item.paragraph_format.space_after = Pt(16)
    usable_width = page.rect.width - 108
    for title, number in entries:
        item = paragraph(title + "\t" + number, 12)
        item.paragraph_format.line_spacing = 1.4
        item.paragraph_format.space_after = Pt(8)
        item.paragraph_format.tab_stops.add_tab_stop(Pt(usable_width), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)


def _repair_tables(document):
    """Synchronize the table grid with reconstructed cells for Word/WPS/LibreOffice.

    pdf2docx writes the right cell widths but leaves an equal-width table grid.
    Some readers then narrow wide text columns and clip text in exact-height rows.
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    for table in document.element.body.iter(qn("w:tbl")):
        grid = table.find(qn("w:tblGrid"))
        if grid is None or not len(grid):
            continue
        count = len(grid)
        boundaries = {0: [0]}
        for row in table.findall(qn("w:tr")):
            column, width = 0, 0
            for cell in row.findall(qn("w:tc")):
                properties = cell.find(qn("w:tcPr"))
                if properties is None:
                    break
                span, cell_width = properties.find(qn("w:gridSpan")), properties.find(qn("w:tcW"))
                if cell_width is None or cell_width.get(qn("w:type")) != "dxa":
                    break
                column += int(span.get(qn("w:val"))) if span is not None else 1
                width += int(cell_width.get(qn("w:w")))
                if column <= count:
                    boundaries.setdefault(column, []).append(width)
            properties = row.find(qn("w:trPr"))
            if properties is not None:
                height = properties.find(qn("w:trHeight"))
                if height is not None:
                    height.set(qn("w:hRule"), "atLeast")
                for constraint in properties.findall(qn("w:cantSplit")):
                    properties.remove(constraint)
        if count not in boundaries:
            continue
        known = {column: round(median(values)) for column, values in boundaries.items()}
        for column in range(1, count):
            if column not in known:
                lower = max(key for key in known if key < column)
                upper = min(key for key in known if key > column)
                known[column] = round(known[lower] + (known[upper] - known[lower]) * (column - lower) / (upper - lower))
        widths = [known[index + 1] - known[index] for index in range(count)]
        if any(width <= 0 for width in widths):
            continue
        for column, width in zip(grid, widths):
            column.set(qn("w:w"), str(width))
        properties = table.find(qn("w:tblPr"))
        if properties is not None:
            total = properties.find(qn("w:tblW"))
            if total is None:
                total = OxmlElement("w:tblW")
                properties.insert(0, total)
            total.set(qn("w:type"), "dxa")
            total.set(qn("w:w"), str(sum(widths)))


def _editable(document, source, selected, target, progress, cancel):
    # Import only on demand: normal PDF operations do not load OpenCV/NumPy.
    if progress:
        progress(0, len(selected) * 2 + 2, "正在启动 Word 转换引擎，首次使用需稍候…")
    from docx import Document
    from pdf2docx.converter import Converter

    if not any(document[index].get_text().strip() for index in selected):
        raise PdfError("所选页面没有可提取文字。扫描件请先进行 OCR，或选择「原页图片」模式保留外观。")
    signed = False
    for index in selected:
        _check(cancel)
        if any(widget.is_signed for widget in (document[index].widgets(types=(pymupdf.PDF_WIDGET_TYPE_SIGNATURE,)) or ())):
            signed = True
            break
    if signed:
        # Never change the source file. Flatten visible signed widgets in memory.
        document.bake(annots=False, widgets=True)
        converter = Converter(stream=document.tobytes(garbage=3, deflate=True))
    else:
        converter = Converter(str(source.path), password=source.password)
    try:
        options = converter.default_settings
        options.update(ignore_page_error=False, raw_exceptions=True, multi_processing=False,
                       # Do not discard real text that overlaps stamps/other blocks.
                       line_overlap_threshold=1.01,
                       # Keep space for the reconstructed final line/page number.
                       page_margin_factor_bottom=0.0)
        total = len(selected) * 2 + 2
        if progress:
            progress(0, total, "正在分析 PDF 版面、文字和表格…")
        converter.load_pages(pages=selected)
        converter.parse_document(**options)
        _check(cancel)
        if progress:
            progress(1, total, "版面分析完成，正在重建可编辑内容…")
        for order, index in enumerate(selected, 1):
            _check(cancel)
            try:
                converter.pages[index].parse(**options)
            except Exception as exc:
                raise PdfError(f"第 {index + 1} 页版面解析失败，请尝试「原页图片」模式。") from exc
            if progress:
                progress(order + 1, total, f"已解析第 {index + 1} 页（{order}/{len(selected)}）")
        output = Document()
        for order, index in enumerate(selected, 1):
            _check(cancel)
            page = converter.pages[index]
            if not page.finalized:
                raise PdfError(f"第 {index + 1} 页未完成解析，已停止转换。")
            try:
                contents = _contents_page(document[index])
                if contents:
                    _make_contents(output, document[index], contents)
                else:
                    page.make_docx(output)
            except Exception as exc:
                raise PdfError(f"第 {index + 1} 页写入 Word 失败，请尝试「原页图片」模式。") from exc
            if progress:
                progress(len(selected) + order + 1, total, f"已写入第 {index + 1} 页（{order}/{len(selected)}）")
        output.core_properties.title = source.path.stem
        output.core_properties.author = ""
        output.core_properties.last_modified_by = "PaperFlow"
        _repair_tables(output)
        _check(cancel)
        output.save(target)
        if progress:
            progress(total, total, "正在保存 Word 文档…")
    finally:
        converter.close()


def _anchor_picture(picture):
    """Pin an image to the physical page; inline pictures can create blank pages."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    anchor = picture._inline
    anchor.tag = qn("wp:anchor")
    for name, value in {"distT": "0", "distB": "0", "distL": "0", "distR": "0",
                        "simplePos": "0", "relativeHeight": "0", "behindDoc": "0",
                        "locked": "0", "layoutInCell": "1", "allowOverlap": "1"}.items():
        anchor.set(name, value)
    simple = OxmlElement("wp:simplePos")
    simple.set("x", "0")
    simple.set("y", "0")
    anchor.insert(0, simple)
    for order, direction in enumerate(("H", "V"), 1):
        position = OxmlElement("wp:position" + direction)
        position.set("relativeFrom", "page")
        offset = OxmlElement("wp:posOffset")
        offset.text = "0"
        position.append(offset)
        anchor.insert(order, position)
    anchor.insert(4, OxmlElement("wp:wrapNone"))


def _page_images(document, selected, source, target, dpi, progress, cancel):
    from docx import Document
    from docx.enum.section import WD_SECTION_START
    from docx.enum.text import WD_LINE_SPACING
    from docx.shared import Pt

    output = Document()
    output.core_properties.title = source.path.stem
    output.core_properties.author = ""
    output.core_properties.last_modified_by = "PaperFlow"
    for order, index in enumerate(selected):
        _check(cancel)
        page = document[index]
        pixels = page.rect.width * page.rect.height * (dpi / 72) ** 2
        if not math.isfinite(pixels) or not 0 < pixels <= 80_000_000:
            raise PdfError(f"第 {index + 1} 页图片过大，请降低图片清晰度。")
        section = output.sections[0] if order == 0 else output.add_section(WD_SECTION_START.NEW_PAGE)
        section.page_width, section.page_height = Pt(page.rect.width), Pt(page.rect.height)
        section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Pt(0)
        section.header_distance = section.footer_distance = Pt(0)
        paragraph = output.add_paragraph()
        paragraph.paragraph_format.space_before = paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        paragraph.paragraph_format.line_spacing = Pt(1)
        run = paragraph.add_run()
        run.font.size = Pt(1)
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False, annots=True)
        picture = run.add_picture(BytesIO(pix.tobytes("png")), width=Pt(page.rect.width), height=Pt(page.rect.height))
        picture._inline.docPr.set("descr", f"PDF 原第 {index + 1} 页，整页图片，不含可编辑文字")
        _anchor_picture(picture)
        if progress:
            progress(order + 1, len(selected), f"已保留第 {index + 1} 页外观（{order + 1}/{len(selected)}）")
    _check(cancel)
    output.save(target)


def pdf_to_word(source: PdfSource, destination: Path | str, *, pages: str = "",
                mode: str = "editable", dpi: int = 150, overwrite: bool = False,
                progress: Progress | None = None, cancel=None) -> Path:
    """Create a new DOCX; failures/cancellation never publish partial results."""
    if mode not in {"editable", "page_images"}:
        raise PdfError("请选择可编辑 Word 或原页图片模式。")
    if not 72 <= dpi <= 300:
        raise PdfError("图片清晰度应在 72 到 300 DPI 之间。")
    destination = Path(destination).absolute()
    if destination.suffix.lower() != ".docx":
        raise PdfError("Word 文件名必须以 .docx 结尾。")
    if _same_file(source.path, destination):
        raise PdfError("输出文件不能覆盖原始 PDF。")
    if not destination.parent.is_dir():
        raise PdfError("保存文件夹不存在，请重新选择。")
    if destination.exists() and not overwrite:
        raise PdfError("输出文件已存在，请换一个文件名。")
    _check(cancel)
    with tempfile.TemporaryDirectory(prefix=".paperflow-word-", dir=destination.parent) as temporary:
        target = Path(temporary) / "result.docx"
        with open_pdf(source.path, source.password) as document:
            if document.page_count != source.pages:
                raise PdfError("PDF 页数已改变，请重新选择该文件。")
            selected = parse_pages(pages, document.page_count)
            if mode == "editable":
                _editable(document, source, selected, target, progress, cancel)
            else:
                _page_images(document, selected, source, target, dpi, progress, cancel)
        _check(cancel)
        # Reopen before publishing: a saved ZIP alone does not prove a valid DOCX.
        from docx import Document
        if not Document(target).sections:
            raise PdfError("生成的 Word 文档无效，未保存结果。")
        if overwrite:
            os.replace(target, destination)
        elif os.name == "nt":
            os.rename(target, destination)
        else:
            os.link(target, destination)
            target.unlink()
    return destination
