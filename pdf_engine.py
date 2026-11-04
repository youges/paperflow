"""Local PDF operations. The order of inputs is part of the public contract."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Callable, Iterable

import pymupdf


class PdfError(ValueError):
    pass


class PasswordRequired(PdfError):
    pass


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class PdfSource:
    path: Path
    pages: int
    size: int
    password: str = field(default="", repr=False)
    preview: bytes = field(default=b"", repr=False, compare=False)


Progress = Callable[[int, int, str], None]


def _check(cancel: Callable[[], bool] | None) -> None:
    if cancel and cancel():
        raise Cancelled("操作已取消，没有生成不完整的结果。")


@contextmanager
def open_pdf(path: Path | str, password: str = ""):
    path = Path(path)
    if not path.is_file():
        raise PdfError(f"找不到文件：{path.name}")
    try:
        document = pymupdf.open(str(path))
    except Exception as exc:
        raise PdfError(f"无法读取 {path.name}，文件可能已损坏。") from exc
    try:
        if not document.is_pdf:
            raise PdfError(f"{path.name} 不是 PDF 文件。")
        if document.needs_pass and not document.authenticate(password):
            raise PasswordRequired(f"{path.name} 需要正确的打开密码。")
        if document.page_count < 1:
            raise PdfError(f"{path.name} 没有可处理的页面。")
        yield document
    finally:
        document.close()


def _preview(page) -> bytes:
    longest = max(page.rect.width, page.rect.height)
    if not math.isfinite(longest) or longest <= 0:
        raise PdfError("页面尺寸无效。")
    pix = page.get_pixmap(matrix=pymupdf.Matrix(1000 / longest, 1000 / longest), alpha=False)
    return pix.tobytes("png")


def inspect_pdf(path: Path | str, password: str = "") -> PdfSource:
    path = Path(path).resolve()
    with open_pdf(path, password) as document:
        return PdfSource(path, document.page_count, path.stat().st_size, password, _preview(document[0]))


def preview_page(source: PdfSource, index: int) -> bytes:
    with open_pdf(source.path, source.password) as document:
        if index < 0 or index >= document.page_count:
            raise PdfError("页码超出范围。")
        return _preview(document[index])


def parse_pages(text: str, total: int) -> list[int]:
    """Return unique zero-based pages in their original document order."""
    if total < 1:
        raise PdfError("PDF 没有页面。")
    text = text.strip().replace("，", ",").replace("、", ",").replace("－", "-")
    if not text:
        return list(range(total))
    pages: set[int] = set()
    for token in text.split(","):
        match = re.fullmatch(r"\s*([0-9]+)\s*(?:-\s*([0-9]+)\s*)?", token)
        if not match:
            raise PdfError("页码格式不正确，请填写 1-5, 8, 10-12，或留空处理全部页面。")
        first = int(match[1])
        last = int(match[2] or match[1])
        if first < 1 or last > total or first > last:
            raise PdfError(f"页码必须在 1 到 {total} 之间，范围请从小到大填写。")
        pages.update(range(first - 1, last))
    return sorted(pages)


def numeric_name(number: int, padding: int, extension: str) -> str:
    return f"{number:0{padding}d}.{extension}"


def _same_file(left: Path, right: Path) -> bool:
    if os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve())):
        return True
    try:
        return left.samefile(right)
    except OSError:
        return False


def merge_pdfs(
    sources: Iterable[PdfSource], destination: Path | str, *, overwrite: bool = False,
    base: PdfSource | None = None, insert_after: int | None = None,
    progress: Progress | None = None, cancel: Callable[[], bool] | None = None,
) -> Path:
    sources = list(sources)  # Never sort: import/list order is the output order.
    if not sources:
        raise PdfError("请先添加要合并的 PDF。")
    if base is not None and (type(insert_after) is not int or not 0 <= insert_after <= base.pages):
        raise PdfError(f"插入位置必须在 0 到 {base.pages} 页之间，0 表示文档开头。")
    if base is None and insert_after is not None:
        raise PdfError("请先选择要插入的现有 PDF。")
    destination = Path(destination).absolute()
    if destination.suffix.lower() != ".pdf":
        raise PdfError("合并文件名必须以 .pdf 结尾。")
    if not destination.parent.is_dir():
        raise PdfError("保存文件夹不存在，请重新选择。")
    if any(_same_file(source.path, destination) for source in sources + ([base] if base else [])):
        raise PdfError("输出文件不能覆盖任何一个原始 PDF，请换一个文件名。")
    if destination.exists() and not overwrite:
        raise PdfError("输出文件已存在，请换一个文件名。")
    handle, temporary = tempfile.mkstemp(prefix=".paperflow-", suffix=".pdf", dir=destination.parent)
    os.close(handle)
    temporary = Path(temporary)
    try:
        with pymupdf.open() as merged:
            total = sum(source.pages for source in sources) + (base.pages if base else 0)
            done = 0
            cursor = -1
            if base is not None:
                _check(cancel)
                with open_pdf(base.path, base.password) as document:
                    if document.page_count != base.pages:
                        raise PdfError("现有 PDF 页数已改变，请重新选择该文件。")
                    merged.insert_pdf(document, widgets=True, join_duplicates=False)
                    done = document.page_count
                cursor = insert_after
                if progress:
                    progress(done, total, f"已读取现有 PDF：{base.path.name}")
            for source in sources:
                _check(cancel)
                with open_pdf(source.path, source.password) as document:
                    merged.insert_pdf(document, start_at=cursor, widgets=True, join_duplicates=False)
                    if cursor >= 0:
                        cursor += document.page_count
                    done += document.page_count
                if progress:
                    progress(done, total, f"已合并 {source.path.name}")
            _check(cancel)
            if progress:
                progress(total, total, "正在保存 PDF…")
            merged.set_metadata({"title": destination.stem, "creator": "PaperFlow 纸序"})
            merged.save(str(temporary), garbage=4, deflate=True)
        _check(cancel)
        if overwrite:
            os.replace(temporary, destination)
        elif os.name == "nt":
            # Windows rename refuses an existing target and works on USB/exFAT too.
            os.rename(temporary, destination)
        else:
            # Hard-link creation is atomic and cannot overwrite a new competing file.
            os.link(temporary, destination)
            temporary.unlink()
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def split_pdf(
    source: PdfSource, output_parent: Path | str, *, output_format: str = "pdf",
    pages: str = "", start: int = 1, padding: int = 1, dpi: int = 150,
    preserve_signature_appearance: bool = True,
    progress: Progress | None = None, cancel: Callable[[], bool] | None = None,
) -> Path:
    if output_format not in {"pdf", "png", "jpg"}:
        raise PdfError("请选择 PDF、PNG 或 JPG 格式。")
    if not 0 <= start <= 999999999 or not 1 <= padding <= 10:
        raise PdfError("起始数字或补零位数无效。")
    if not 72 <= dpi <= 600:
        raise PdfError("图片分辨率应在 72 到 600 DPI 之间。")
    output_parent = Path(output_parent).resolve()
    if not output_parent.is_dir():
        raise PdfError("保存文件夹不存在，请重新选择。")
    _check(cancel)
    staging = Path(tempfile.mkdtemp(prefix=".paperflow-", dir=output_parent))
    try:
        with open_pdf(source.path, source.password) as document:
            selected = parse_pages(pages, document.page_count)
            if output_format == "pdf" and preserve_signature_appearance:
                # Copied signature widgets cannot retain cryptographic validity,
                # and readers may stop displaying their appearance. Bake first.
                # Only the in-memory document changes; never save over the source.
                signed = False
                for page in document:
                    _check(cancel)
                    if any(widget.is_signed for widget in (page.widgets(types=(pymupdf.PDF_WIDGET_TYPE_SIGNATURE,)) or ())):
                        signed = True
                        break
                if signed:
                    if progress:
                        progress(0, len(selected), "正在固定签名与表单外观…")
                    _check(cancel)
                    document.bake(annots=False, widgets=True)
                    _check(cancel)
            for order, page_index in enumerate(selected):
                _check(cancel)
                target = staging / numeric_name(start + order, padding, output_format)
                if output_format == "pdf":
                    with pymupdf.open() as single:
                        single.insert_pdf(document, from_page=page_index, to_page=page_index, widgets=True)
                        single.save(str(target), garbage=4, deflate=True)
                else:
                    page = document[page_index]
                    pixels = page.rect.width * page.rect.height * (dpi / 72) ** 2
                    if not math.isfinite(pixels) or pixels <= 0 or pixels > 80_000_000:
                        raise PdfError(f"第 {page_index + 1} 页图片过大，请降低 DPI 后重试（单页上限 8000 万像素）。")
                    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False, annots=True)
                    if output_format == "jpg":
                        pix.save(str(target), jpg_quality=95)
                    else:
                        pix.save(str(target))
                if progress:
                    progress(order + 1, len(selected), f"第 {page_index + 1} 页 → {target.name}")
        _check(cancel)
        # Results become visible together, and an existing result is never overwritten.
        base = source.path.stem[:100] + "_拆分_" + output_format.upper()
        for index in range(1, 10000):
            folder = output_parent / (base if index == 1 else f"{base} ({index})")
            if folder.exists():
                continue
            for attempt in range(6):
                try:
                    staging.rename(folder)
                    return folder
                except FileExistsError:
                    break
                except PermissionError:
                    # Windows antivirus/indexers can briefly hold a newly written file.
                    if folder.exists():
                        break
                    if attempt == 5:
                        raise
                    _check(cancel)
                    time.sleep(0.05 * (attempt + 1))
        raise PdfError("同名输出文件夹过多，请选择另一个保存位置。")
    finally:
        if staging.exists():
            shutil.rmtree(staging)
