"""PaperFlow: a completely local Windows and Linux PDF workbench."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys
import threading
from typing import Callable
from app_config import VERSION, UI_FONT, log_directory

from PySide6.QtCore import Qt, QSize, QRectF, QThread, Signal, QUrl, QTimer, QSettings
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QFontDatabase, QFontMetrics, QIcon, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QStyledItemDelegate, QStyle, QVBoxLayout,
    QWidget,
)

from pdf_engine import (
    Cancelled, PasswordRequired, PdfError, PdfSource, inspect_pdf, merge_pdfs,
    numeric_name, parse_pages, preview_page, split_pdf,
)
from conversion_engine import (
    FILE_FILTER, convert_documents, find_libreoffice, validate_inputs,
)


STYLE = """
* { font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', sans-serif; font-size: 13px; color: #263932; }
QMainWindow, QWidget#root { background: #f4f6f5; }
QWidget#sidebar { background: #ffffff; border-right: 1px solid #e1e7e3; }
QLabel { background: transparent; border: none; }
QLabel#brand { font-size: 23px; font-weight: 700; letter-spacing: 2px; }
QLabel#eyebrow { font-size: 10px; color: #8d9992; letter-spacing: 2px; }
QLabel#heading { font-size: 27px; font-weight: 700; color: #173f30; }
QLabel#subheading { color: #77837b; font-size: 13px; }
QLabel#section { font-size: 15px; font-weight: 700; }
QLabel#muted { color: #7e8982; font-size: 12px; }
QLabel#badge { background: #e9f2ed; color: #39785a; padding: 7px 12px; border-radius: 14px; font-size: 11px; }
QFrame#card { background: #ffffff; border: 1px solid #e0e7e2; border-radius: 14px; }
QFrame#notice { background: #eaf3ee; border: 1px solid #dceae1; border-radius: 9px; }
QPushButton { background: #ffffff; border: 1px solid #dce4de; border-radius: 7px; padding: 8px 15px; min-height: 20px; }
QPushButton:hover { background: #f0f6f2; border-color: #aac7b6; }
QPushButton:pressed { background: #e0ece4; }
QPushButton:disabled { color: #aab3ad; background: #f2f4f2; border-color: #e7ebe8; }
QPushButton#primary { background: #21694b; color: #ffffff; border: 1px solid #21694b; font-weight: 600; padding: 11px 25px; }
QPushButton#primary:hover { background: #18583e; }
QPushButton#primary:disabled { background: #9fb4a8; border-color: #9fb4a8; color: #f3f6f4; }
QPushButton#nav { border: none; border-radius: 9px; background: transparent; text-align: left; padding: 13px 18px; font-size: 14px; }
QPushButton#nav:checked { background: #eaf3ed; color: #206649; font-weight: 700; }
QPushButton#nav:hover { background: #f2f6f3; }
QPushButton#ghost { background: transparent; border: none; color: #708077; }
QPushButton#format { padding: 12px 10px; text-align: left; font-weight: 600; }
QPushButton#format:checked { background: #eaf3ed; border: 1px solid #5b9876; color: #21694b; }
QLineEdit, QSpinBox, QComboBox { background: #ffffff; border: 1px solid #dce4de; border-radius: 6px; padding: 8px 10px; selection-background-color: #d5e9dd; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid #5b9876; }
QSpinBox { min-height: 20px; }
QSpinBox QLineEdit { padding: 0; border: none; background: transparent; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { background: #f4f6f4; color: #a2aaa5; }
QListWidget { background: #ffffff; border: none; outline: none; border-radius: 9px; }
QListWidget::item { border-bottom: 1px solid #edf0ee; }
QScrollBar:vertical { width: 8px; background: transparent; }
QScrollBar::handle:vertical { background: #ccd8d0; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QProgressBar { border: none; background: #e6ede8; border-radius: 4px; height: 7px; text-align: center; }
QProgressBar::chunk { background: #438965; border-radius: 4px; }
QWidget#preview { background: #eef1ee; border-radius: 9px; }
QToolTip { color: #ffffff; background: #263e31; border: none; padding: 6px; }
"""


def label(text: str, role: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(role)
    widget.setWordWrap(wrap)
    return widget


def button(text: str, callback=None, role: str = "") -> QPushButton:
    widget = QPushButton(text)
    widget.setObjectName(role)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if callback:
        widget.clicked.connect(callback)
    return widget


def card() -> tuple[QFrame, QVBoxLayout]:
    widget = QFrame()
    widget.setObjectName("card")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(23, 20, 23, 20)
    layout.setSpacing(14)
    return widget, layout


def size_text(size: int) -> str:
    return f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"


def app_icon() -> QIcon:
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#21694b"))
    painter.drawRoundedRect(QRectF(2, 2, 124, 124), 30, 30)
    painter.setBrush(QColor("#b9d8c3"))
    painter.drawRoundedRect(QRectF(30, 25, 56, 73), 6, 6)
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(QRectF(43, 36, 56, 73), 6, 6)
    painter.setPen(QPen(QColor("#438965"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for y in (56, 68, 80):
        painter.drawLine(55, y, 85, y)
    painter.end()
    return QIcon(pixmap)


class Worker(QThread):
    result = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(int, int, str)

    def __init__(self, action: Callable, parent=None):
        super().__init__(parent)
        self.action = action
        self.cancel_event = threading.Event()

    def run(self):
        try:
            result = self.action(self.progress.emit, self.cancel_event.is_set)
            self.result.emit(result)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            logging.exception("Operation failed")
            self.failed.emit(str(exc) or "处理失败，请检查文件和保存位置后重试。")


class FileDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(400, 79)

    def paint(self, painter, option, index):
        source = index.data(Qt.ItemDataRole.UserRole)
        if source is None:
            return
        path = source if isinstance(source, Path) else source.path
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(option.rect, QColor("#eef6f0"))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor("#f8faf8"))
        x, y, width = option.rect.x(), option.rect.y(), option.rect.width()
        painter.setPen(QColor("#819087"))
        painter.setFont(QFont("Microsoft YaHei UI", 10))
        painter.drawText(x + 5, y, 35, 79, Qt.AlignmentFlag.AlignCenter, f"{index.row() + 1:02d}")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f8ece8"))
        painter.drawRoundedRect(QRectF(x + 53, y + 18, 39, 43), 7, 7)
        painter.setPen(QColor("#b16c58"))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        painter.drawText(x + 53, y + 18, 39, 43, Qt.AlignmentFlag.AlignCenter, path.suffix[1:].upper()[:4])
        painter.setPen(QColor("#293f31"))
        painter.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.DemiBold))
        metrics = QFontMetrics(painter.font())
        name = metrics.elidedText(path.name, Qt.TextElideMode.ElideMiddle, max(40, width - 125))
        painter.drawText(x + 108, y + 16, width - 125, 25, Qt.AlignmentFlag.AlignVCenter, name)
        painter.setPen(QColor("#8a958e"))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        detail = str(path.parent) if isinstance(source, Path) else f"{source.pages} 页     ·     {size_text(source.size)}"
        painter.drawText(x + 108, y + 42, width - 125, 22, Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(painter.font()).elidedText(detail, Qt.TextElideMode.ElideMiddle, max(40, width - 125)))
        painter.restore()


class FileList(QListWidget):
    files_dropped = Signal(list)

    def __init__(self, documents=False):
        super().__init__()
        self.documents = documents
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setItemDelegate(FileDelegate(self))
        self.setMouseTracking(True)
        self.setMinimumHeight(210)
        self.setSpacing(2)
        self.setAccessibleName("待转换文档列表，按从上到下顺序处理" if documents else "PDF 合并列表，按当前显示的从上到下顺序合并")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.files_dropped.emit([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
            self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count():
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.viewport().rect()).adjusted(2, 5, -2, -5)
        painter.setPen(QPen(QColor("#d5e1d8"), 1, Qt.PenStyle.DashLine))
        painter.setBrush(QColor("#fafcfb"))
        painter.drawRoundedRect(bounds, 10, 10)
        cy = int(bounds.center().y())
        painter.setPen(QColor("#7d9c87"))
        painter.setFont(QFont("Segoe UI", 34, QFont.Weight.Light))
        painter.drawText(0, cy - 75, int(bounds.width()), 60, Qt.AlignmentFlag.AlignCenter, "+")
        painter.setPen(QColor("#425e4c"))
        painter.setFont(QFont("Microsoft YaHei UI", 12, QFont.Weight.DemiBold))
        painter.drawText(0, cy - 12, int(bounds.width()), 30, Qt.AlignmentFlag.AlignCenter,
                         "将文档或图片拖到这里" if self.documents else "将 PDF 拖到这里")
        painter.setPen(QColor("#8c9991"))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(0, cy + 24, int(bounds.width()), 26, Qt.AlignmentFlag.AlignCenter,
                         "Word / Excel / PowerPoint / 图片 / TXT" if self.documents else "或点击右上角「添加 PDF」选择文件")
        painter.end()


class Preview(QLabel):
    def __init__(self):
        super().__init__("导入 PDF 后预览页面")
        self.setObjectName("preview")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(190, 190)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.original = QPixmap()

    def display(self, data: bytes):
        self.original.loadFromData(data)
        self.rescale()

    def rescale(self):
        if not self.original.isNull():
            self.setPixmap(self.original.scaled(
                self.size() - QSize(30, 30), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.rescale()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("纸序 PaperFlow · PDF 工作台")
        self.setWindowIcon(app_icon())
        self.resize(1120, 850)
        self.setMinimumSize(980, 680)
        self.settings = QSettings("PaperFlow", "PaperFlow")
        self.worker: Worker | None = None
        self.workers: set[Worker] = set()
        self.split_source: PdfSource | None = None
        self.base_source: PdfSource | None = None
        self.page_index = 0
        self.last_output: Path | None = None
        self.busy = False
        self._callback = None
        self._pending = None
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 30, 18, 22)
        side.setSpacing(10)
        brandrow = QHBoxLayout()
        brand_icon = QLabel()
        brand_icon.setPixmap(app_icon().pixmap(38, 38))
        brandrow.addWidget(brand_icon)
        brandrow.addWidget(label("纸序", "brand"))
        brandrow.addStretch()
        side.addLayout(brandrow)
        side.addWidget(label("P A P E R F L O W", "eyebrow"))
        side.addSpacing(35)
        side.addWidget(label("  文件工具", "muted"))
        self.navigation = QButtonGroup(self)
        for index, title in enumerate(("合并 PDF", "拆分 PDF", "文档转 PDF")):
            nav = button(title, role="nav")
            nav.setCheckable(True)
            self.navigation.addButton(nav, index)
            side.addWidget(nav)
        self.navigation.button(0).setChecked(True)
        self.navigation.idClicked.connect(self._switch)
        side.addStretch()
        side.addWidget(label("●  本地离线处理", "badge"))
        side.addWidget(label("文件仅在你的电脑中处理\n无需上传，无需联网", "muted"))
        side.addSpacing(8)
        side.addWidget(label(f"PaperFlow  {VERSION}", "eyebrow"))
        shell.addWidget(sidebar)

        main = QWidget()
        body = QVBoxLayout(main)
        body.setContentsMargins(32, 28, 32, 22)
        body.setSpacing(18)
        top = QHBoxLayout()
        top.addWidget(label("你的文件，井然有序。", "muted"))
        top.addStretch()
        top.addWidget(label("PDF 工作台", "badge"))
        body.addLayout(top)
        self.heading = label("按顺序，合为一份。", "heading")
        self.subheading = label("先导入的文件排在前面，每一页都在正确的位置。", "subheading")
        body.addWidget(self.heading)
        body.addWidget(self.subheading)
        self.pages = QStackedWidget()
        self.pages.setMinimumHeight(575)
        self.pages.addWidget(self._merge_page())
        self.pages.addWidget(self._split_page())
        self.pages.addWidget(self._convert_page())
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget { background: #f4f6f5; border: none; }")
        self.scroll.setWidget(self.pages)
        body.addWidget(self.scroll, 1)

        footer = QFrame()
        footer.setObjectName("card")
        foot = QVBoxLayout(footer)
        foot.setContentsMargins(18, 13, 18, 13)
        foot.setSpacing(8)
        statusrow = QHBoxLayout()
        self.status = label("准备就绪", "muted", True)
        self.status.setMinimumWidth(200)
        statusrow.addWidget(self.status, 1)
        self.open_result = button("打开结果位置", self._open_result)
        self.open_result.hide()
        self.cancel_button = button("取消", self._cancel)
        self.cancel_button.hide()
        self.run_button = button("合并并保存", self._execute, "primary")
        statusrow.addWidget(self.open_result)
        statusrow.addWidget(self.cancel_button)
        statusrow.addWidget(self.run_button)
        foot.addLayout(statusrow)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.hide()
        foot.addWidget(self.progress)
        body.addWidget(footer)
        shell.addWidget(main, 1)

    def _merge_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        self.merge_mode = QComboBox()
        self.merge_mode.addItems(["普通合并 · 按列表顺序生成 PDF", "插入到现有 PDF · 自定义插入位置"])
        self.merge_mode.currentIndexChanged.connect(self._refresh)
        layout.addWidget(self.merge_mode)
        filecard, contents = card()
        toolbar = QHBoxLayout()
        toolbar.addWidget(label("待合并文件", "section"))
        toolbar.addStretch()
        self.add_button = button("＋  添加 PDF", self._choose_merge)
        toolbar.addWidget(self.add_button)
        contents.addLayout(toolbar)
        self.insert_panel = QWidget()
        insertion = QVBoxLayout(self.insert_panel)
        insertion.setContentsMargins(0, 0, 0, 0)
        insertion.setSpacing(10)
        baserow = QHBoxLayout()
        self.base_name = label("先选择一个现有 PDF，再添加下方要插入的新文件。", "muted", True)
        baserow.addWidget(self.base_name, 1)
        baserow.addWidget(button("选择现有 PDF", self._choose_base))
        insertion.addLayout(baserow)
        positionrow = QHBoxLayout()
        positionrow.addWidget(label("插入位置", "muted"))
        self.insert_position = QComboBox()
        self.insert_position.addItems(["文档开头", "文档末尾", "指定页之前", "指定页之后"])
        self.insert_position.setCurrentIndex(1)
        self.insert_position.currentIndexChanged.connect(self._refresh)
        positionrow.addWidget(self.insert_position, 1)
        self.insert_page = QSpinBox()
        self.insert_page.setRange(1, 1)
        self.insert_page.setPrefix("第 ")
        self.insert_page.setSuffix(" 页")
        self.insert_page.valueChanged.connect(self._refresh)
        positionrow.addWidget(self.insert_page)
        insertion.addLayout(positionrow)
        self.insert_summary = label("", "muted", True)
        insertion.addWidget(self.insert_summary)
        contents.addWidget(self.insert_panel)
        contents.addWidget(label("按列表从上到下合并 · 可继续添加，也可拖动文件调整顺序", "muted"))
        self.file_list = FileList()
        self.file_list.files_dropped.connect(lambda paths: self._load_files(paths, "merge"))
        self.file_list.model().rowsMoved.connect(self._refresh)
        self.file_list.currentRowChanged.connect(self._refresh)
        contents.addWidget(self.file_list, 1)
        tools = QHBoxLayout()
        self.count_label = label("尚未添加文件", "muted")
        tools.addWidget(self.count_label, 1)
        self.up_button = button("↑ 上移", lambda: self._move(-1))
        self.down_button = button("↓ 下移", lambda: self._move(1))
        self.remove_button = button("移除", self._remove)
        self.clear_button = button("清空", self._clear, "ghost")
        for action in (self.up_button, self.down_button, self.remove_button, self.clear_button):
            tools.addWidget(action)
        contents.addLayout(tools)
        layout.addWidget(filecard, 1)
        outputcard, out = card()
        out.addWidget(label("保存位置", "section"))
        outputrow = QHBoxLayout()
        self.merge_output = QLineEdit()
        self.merge_output.setPlaceholderText("选择合并后 PDF 的保存路径")
        self.merge_output.setAccessibleName("合并输出路径")
        outputrow.addWidget(self.merge_output, 1)
        outputrow.addWidget(button("浏览…", self._choose_merge_output))
        out.addLayout(outputrow)
        out.addWidget(label("原始文件保持完整；合并结果另存为一个新的 PDF。", "muted"))
        layout.addWidget(outputcard)
        return widget

    def _split_page(self):
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(15)
        columns = QHBoxLayout()
        columns.setSpacing(15)

        sourcecard, left = card()
        sourcetop = QHBoxLayout()
        sourcetop.addWidget(label("源文件", "section"))
        sourcetop.addStretch()
        self.choose_source_button = button("选择 PDF", self._choose_split)
        sourcetop.addWidget(self.choose_source_button)
        left.addLayout(sourcetop)
        self.source_name = label("尚未选择文件", "muted")
        self.source_name.setMinimumWidth(0)
        self.source_name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        left.addWidget(self.source_name)
        self.preview = Preview()
        left.addWidget(self.preview, 1)
        pager = QHBoxLayout()
        self.prev_button = button("‹", lambda: self._navigate(-1))
        self.next_button = button("›", lambda: self._navigate(1))
        self.prev_button.setAccessibleName("上一页")
        self.next_button.setAccessibleName("下一页")
        self.page_label = label("— / —", "muted")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pager.addWidget(self.prev_button)
        pager.addWidget(self.page_label, 1)
        pager.addWidget(self.next_button)
        left.addLayout(pager)
        columns.addWidget(sourcecard, 1)

        settingscard, right = card()
        right.addWidget(label("拆分设置", "section"))
        right.addWidget(label("导出格式", "muted"))
        formats = QHBoxLayout()
        formats.setSpacing(6)
        self.formats = QButtonGroup(self)
        self.format_names = ("pdf", "png", "jpg")
        for index, title in enumerate(("单页 PDF", "PNG 图片", "JPG 图片")):
            choice = button(title, role="format")
            choice.setCheckable(True)
            self.formats.addButton(choice, index)
            formats.addWidget(choice)
        self.formats.button(0).setChecked(True)
        self.formats.idClicked.connect(self._refresh)
        right.addLayout(formats)
        self.format_help = label("每页保存为独立 PDF，保留原页面文字与清晰度。", "muted", True)
        right.addWidget(self.format_help)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(9)
        grid.addWidget(label("起始数字", "muted"), 0, 0)
        grid.addWidget(label("补零位数", "muted"), 0, 1)
        self.start_number = QSpinBox()
        self.start_number.setRange(0, 999999999)
        self.start_number.setValue(1)
        self.start_number.setAccessibleName("拆分文件名起始数字")
        self.start_number.valueChanged.connect(self._refresh)
        self.padding = QSpinBox()
        self.padding.setRange(1, 10)
        self.padding.setValue(1)
        self.padding.setAccessibleName("数字命名补零位数")
        self.padding.valueChanged.connect(self._refresh)
        grid.addWidget(self.start_number, 1, 0)
        grid.addWidget(self.padding, 1, 1)
        right.addLayout(grid)
        self.naming_preview = label("命名示例：1.pdf、2.pdf、3.pdf", "muted", True)
        right.addWidget(self.naming_preview)
        right.addWidget(label("页码范围", "muted"))
        self.page_range = QLineEdit()
        self.page_range.setPlaceholderText("全部页面，或填写 1-5, 8, 10-12")
        self.page_range.setAccessibleName("拆分页码范围，留空表示全部页面")
        self.page_range.textChanged.connect(self._refresh)
        right.addWidget(self.page_range)
        right.addWidget(label("选中页面始终按原文档页序连续编号。", "muted"))
        resolution = QHBoxLayout()
        self.dpi_label = label("图片清晰度", "muted")
        resolution.addWidget(self.dpi_label)
        self.dpi = QComboBox()
        for title, value in (("标准 · 150 DPI", 150), ("高清 · 300 DPI", 300), ("精细 · 600 DPI", 600), ("轻量 · 72 DPI", 72)):
            self.dpi.addItem(title, value)
        resolution.addWidget(self.dpi, 1)
        right.addLayout(resolution)
        self.keep_signature = QCheckBox("保留签名/印章的可见外观")
        self.keep_signature.setChecked(True)
        self.keep_signature.setToolTip("仅对单页 PDF 生效；含数字签名文档中的表单会固定为页面内容。原文件不变，拆分结果不继承原签名的验证效力。图片始终渲染页面上的可见外观。")
        right.addWidget(self.keep_signature)
        right.addWidget(label("含签名文档的表单会固定；拆分结果不继承原签名的验证效力。", "muted", True))
        right.addStretch()
        columns.addWidget(settingscard, 1)
        outer.addLayout(columns, 1)

        outputcard, out = card()
        out.addWidget(label("保存文件夹", "section"))
        row = QHBoxLayout()
        self.split_output = QLineEdit()
        self.split_output.setPlaceholderText("选择拆分结果的保存文件夹")
        self.split_output.setAccessibleName("拆分保存文件夹")
        row.addWidget(self.split_output, 1)
        row.addWidget(button("浏览…", self._choose_split_output))
        out.addLayout(row)
        out.addWidget(label("自动新建结果子文件夹，已有结果会保留。", "muted"))
        outer.addWidget(outputcard)
        return widget

    def _convert_page(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        filecard, content = card()
        toolbar = QHBoxLayout()
        toolbar.addWidget(label("待转换文档", "section"))
        toolbar.addStretch()
        toolbar.addWidget(button("＋  添加文档", self._choose_documents))
        content.addLayout(toolbar)
        content.addWidget(label("可多次添加或拖入文件；合为一份时，按列表从上到下排列。", "muted", True))
        self.document_list = FileList(documents=True)
        self.document_list.files_dropped.connect(self._add_documents)
        self.document_list.currentRowChanged.connect(self._refresh)
        self.document_list.model().rowsMoved.connect(self._refresh)
        content.addWidget(self.document_list, 1)
        actions = QHBoxLayout()
        self.document_count = label("尚未添加文件", "muted")
        actions.addWidget(self.document_count, 1)
        self.document_up = button("↑ 上移", lambda: self._move_document(-1))
        self.document_down = button("↓ 下移", lambda: self._move_document(1))
        self.document_remove = button("移除", self._remove_document)
        self.document_clear = button("清空", self.document_list.clear, "ghost")
        self.document_list.model().rowsRemoved.connect(self._refresh)
        self.document_list.model().modelReset.connect(self._refresh)
        for action in (self.document_up, self.document_down, self.document_remove, self.document_clear):
            actions.addWidget(action)
        content.addLayout(actions)
        layout.addWidget(filecard, 1)

        settingscard, settings = card()
        row = QHBoxLayout()
        row.addWidget(label("保存方式", "section"))
        self.conversion_mode = QComboBox()
        self.conversion_mode.addItems(["每个文档分别保存为 PDF", "按列表顺序转换并合为一份 PDF"])
        row.addWidget(self.conversion_mode, 1)
        row.addWidget(label("TXT 编码", "muted"))
        self.text_encoding = QComboBox()
        for title, value in (("自动", "auto"), ("UTF-8", "utf-8-sig"), ("GB18030 / GBK", "gb18030"), ("UTF-16", "utf-16")):
            self.text_encoding.addItem(title, value)
        row.addWidget(self.text_encoding)
        settings.addLayout(row)
        self.office_status = label("", "muted", True)
        settings.addWidget(self.office_status)
        component = QHBoxLayout()
        self.office_path = QLineEdit(str(self.settings.value("libreoffice_path", "")))
        self.office_path.setPlaceholderText("自动检测 LibreOffice，也可选择 soffice 程序路径")
        self.office_path.setAccessibleName("LibreOffice 程序路径，留空自动检测")
        self.office_path.editingFinished.connect(self._detect_office)
        component.addWidget(self.office_path, 1)
        component.addWidget(button("选择组件…", self._choose_office))
        component.addWidget(button("重新检测", self._detect_office))
        component.addWidget(button("下载 LibreOffice", lambda: QDesktopServices.openUrl(QUrl("https://www.libreoffice.org/download/download-libreoffice/")), "ghost"))
        settings.addLayout(component)
        settings.addWidget(label("Office 需要本机 LibreOffice（Writer / Calc / Impress）；图片和 TXT 可直接转换。Office 排版取决于原文档打印设置和本机字体，请核对转换结果。", "muted", True))
        layout.addWidget(settingscard)

        outputcard, output = card()
        output.addWidget(label("保存文件夹", "section"))
        row = QHBoxLayout()
        self.convert_output = QLineEdit()
        self.convert_output.setPlaceholderText("选择转换结果的保存文件夹")
        self.convert_output.setAccessibleName("文档转 PDF 保存文件夹")
        row.addWidget(self.convert_output, 1)
        row.addWidget(button("浏览…", self._choose_convert_output))
        output.addLayout(row)
        output.addWidget(label("自动新建结果子文件夹；保留原文件，同名文档会自动编号。", "muted", True))
        layout.addWidget(outputcard)
        self._detect_office()
        return widget

    def _documents(self):
        return [self.document_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.document_list.count())]

    def _choose_documents(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "添加要转换的文档或图片", self._last_directory(), FILE_FILTER)
        if paths:
            self._add_documents(paths)

    def _add_documents(self, paths):
        if self.busy or not paths:
            return
        try:
            documents = validate_inputs(paths)
        except PdfError as exc:
            QMessageBox.warning(self, "无法添加文档", str(exc))
            return
        for path in documents:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(str(path))
            self.document_list.addItem(item)
        self.settings.setValue("last_directory", str(documents[-1].parent))
        if not self.convert_output.text().strip():
            self.convert_output.setText(str(documents[0].parent))
        self.document_list.setCurrentRow(self.document_list.count() - 1)
        self._refresh()

    def _move_document(self, offset):
        row = self.document_list.currentRow()
        target = row + offset
        if 0 <= row < self.document_list.count() and 0 <= target < self.document_list.count():
            item = self.document_list.takeItem(row)
            self.document_list.insertItem(target, item)
            self.document_list.setCurrentRow(target)
        self._refresh()

    def _remove_document(self):
        row = self.document_list.currentRow()
        if row >= 0:
            self.document_list.takeItem(row)
        self._refresh()

    def _detect_office(self):
        selected = self.office_path.text().strip()
        executable = find_libreoffice(selected)
        self.settings.setValue("libreoffice_path", selected)
        self.office_status.setText("✓ Office 转换组件已就绪" if executable else "尚未找到 LibreOffice；图片和 TXT 仍可直接转换。")
        self.office_status.setToolTip(str(executable) if executable else "安装后点击「重新检测」，或选择 soffice.com / soffice.exe / soffice。")

    def _choose_office(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 LibreOffice 的 soffice 程序", self.office_path.text() or self._last_directory(),
                                             "LibreOffice 程序 (soffice.exe soffice.com soffice libreoffice);;所有文件 (*)")
        if path:
            self.office_path.setText(path)
            self._detect_office()

    def _choose_convert_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择转换结果的保存文件夹", self.convert_output.text() or self._last_directory())
        if path:
            self.convert_output.setText(path)

    def _switch(self, index):
        if self.busy:
            return
        self.navigation.button(index).setChecked(True)
        self.pages.setCurrentIndex(index)
        self.heading.setText(("按顺序，合为一份。", "逐页拆分，清楚有序。", "多种格式，统一成 PDF。")[index])
        self.subheading.setText(("先导入的文件排在前面，每一页都在正确的位置。",
                                 "导出独立 PDF 或图片，让每一页拥有自己的数字编号。",
                                 "Word、Excel、PowerPoint、图片与 TXT，在本机批量转换。")[index])
        self._refresh()

    def _sources(self) -> list[PdfSource]:
        return [self.file_list.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self.file_list.count())]

    def _refresh(self, *_):
        if not hasattr(self, "run_button"):
            return
        count, row = self.file_list.count(), self.file_list.currentRow()
        inserting = self.merge_mode.currentIndex() == 1
        self.insert_panel.setVisible(inserting)
        self.insert_page.setEnabled(not self.busy and self.base_source is not None and self.insert_position.currentIndex() >= 2)
        self.insert_position.setEnabled(not self.busy and self.base_source is not None)
        self.pages.setMinimumHeight(755 if inserting and self.pages.currentIndex() == 0 else 700 if self.pages.currentIndex() == 2 else 615)
        if self.base_source is not None:
            after = self._insertion_offset()
            tail = self.base_source.pages - after
            self.insert_summary.setText(f"结果顺序：原文档前 {after} 页 → 下方新文件（按列表顺序）→ 原文档后 {tail} 页")
        else:
            self.insert_summary.setText("选择现有 PDF 后，可按其原始页码指定插入位置。")
        pages = sum(source.pages for source in self._sources())
        self.count_label.setText(f"{count} 个文件 · 共 {pages} 页" if count else "尚未添加文件")
        self.up_button.setEnabled(not self.busy and row > 0)
        self.down_button.setEnabled(not self.busy and 0 <= row < count - 1)
        self.remove_button.setEnabled(not self.busy and row >= 0)
        self.clear_button.setEnabled(not self.busy and count > 0)
        self.prev_button.setEnabled(not self.busy and self.split_source is not None and self.page_index > 0)
        self.next_button.setEnabled(not self.busy and self.split_source is not None and self.page_index < self.split_source.pages - 1)
        index = self.formats.checkedId()
        extension = self.format_names[index]
        self.dpi.setEnabled(not self.busy and index != 0)
        self.dpi_label.setEnabled(index != 0)
        self.keep_signature.setEnabled(not self.busy and index == 0)
        self.format_help.setText(("每页保存为独立 PDF，保留原页面文字与清晰度。",
                                  "每页保存为一张无损 PNG，适合文档与清晰文字。",
                                  "每页保存为一张 JPG，适合较小文件和日常分享。")[index])
        samples = [numeric_name(self.start_number.value() + n, self.padding.value(), extension) for n in range(3)]
        self.naming_preview.setText("命名示例：" + "、".join(samples))
        splitting = self.pages.currentIndex() == 1
        converting = self.pages.currentIndex() == 2
        document_count, document_row = self.document_list.count(), self.document_list.currentRow()
        self.document_count.setText(f"{document_count} 个文档" if document_count else "尚未添加文件")
        self.document_up.setEnabled(not self.busy and document_row > 0)
        self.document_down.setEnabled(not self.busy and 0 <= document_row < document_count - 1)
        self.document_remove.setEnabled(not self.busy and document_row >= 0)
        self.document_clear.setEnabled(not self.busy and document_count > 0)
        self.run_button.setText("转换并保存" if converting else "拆分并保存" if splitting else "插入并另存" if inserting else "合并并保存")
        ready = document_count > 0 if converting else self.split_source is not None if splitting else count > 0 and (not inserting or self.base_source is not None)
        self.run_button.setEnabled(not self.busy and ready)
        self.file_list.viewport().update()
        self.document_list.viewport().update()

    def _move(self, offset):
        row = self.file_list.currentRow()
        target = row + offset
        if row < 0 or target < 0 or target >= self.file_list.count():
            return
        item = self.file_list.takeItem(row)
        self.file_list.insertItem(target, item)
        self.file_list.setCurrentRow(target)
        self._refresh()

    def _remove(self):
        row = self.file_list.currentRow()
        if row >= 0:
            self.file_list.takeItem(row)
        self._refresh()

    def _clear(self):
        self.file_list.clear()
        self._refresh()

    def _last_directory(self):
        return str(self.settings.value("last_directory", str(Path.home() / "Documents")))

    def _choose_merge(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "按顺序添加 PDF（可多次添加）", self._last_directory(), "PDF 文件 (*.pdf)")
        if paths:
            self._load_files(paths, "merge")

    def _choose_split(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择要拆分的 PDF", self._last_directory(), "PDF 文件 (*.pdf)")
        if path:
            self._load_files([path], "split")

    def _choose_base(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择要插入的现有 PDF", self._last_directory(), "PDF 文件 (*.pdf)")
        if path:
            self._load_files([path], "base")

    def _insertion_offset(self):
        mode = self.insert_position.currentIndex()
        if mode == 0:
            return 0
        if mode == 1:
            return self.base_source.pages if self.base_source else 0
        return self.insert_page.value() - (1 if mode == 2 else 0)

    def _load_files(self, paths: list[str], mode: str):
        if self.busy or not paths:
            return
        paths = [str(Path(path)) for path in paths]
        if mode in {"split", "base"}:
            paths = paths[:1]
        self.settings.setValue("last_directory", str(Path(paths[0]).parent))

        def load(progress, cancel):
            results = []
            for index, path in enumerate(paths):
                if cancel():
                    raise Cancelled()
                try:
                    result = inspect_pdf(path)
                except Exception as exc:
                    result = exc
                results.append([path, result])
                progress(index + 1, len(paths), f"正在读取 {Path(path).name}")
            return results

        self._run_task(load, lambda results: self._resolve_passwords(results, mode), "正在读取 PDF…")

    def _resolve_passwords(self, results, mode):
        for index, (path, result) in enumerate(results):
            if not isinstance(result, PasswordRequired):
                continue
            password, accepted = QInputDialog.getText(
                self, "PDF 打开密码", f"请输入 {Path(path).name} 的打开密码：",
                QLineEdit.EchoMode.Password,
            )
            if not accepted:
                results[index][1] = PdfError("已跳过需要密码的文件。")
                continue

            def retry(progress, cancel, p=path, pw=password):
                try:
                    return inspect_pdf(p, pw)
                except Exception as exc:
                    return exc

            def resolved(new_result, i=index):
                results[i][1] = new_result
                if isinstance(new_result, PasswordRequired):
                    QMessageBox.information(self, "密码不正确", "密码不正确，请重新输入，或取消以跳过该文件。")
                self._resolve_passwords(results, mode)

            self._run_task(retry, resolved, "正在解锁 PDF…")
            return
        issues = []
        imported = 0
        # Append only after passwords have been resolved: encrypted inputs keep their position.
        for path, result in results:
            if not isinstance(result, PdfSource):
                issues.append(f"{Path(path).name}：{result}")
                continue
            imported += 1
            if mode == "base":
                self.base_source = result
                self.base_name.setText(f"{result.path.name} · 共 {result.pages} 页")
                self.base_name.setToolTip(str(result.path))
                self.insert_page.setMaximum(result.pages)
                self.merge_output.setText(str(result.path.with_name(result.path.stem + "_插入结果.pdf")))
            elif mode == "merge":
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, result)
                item.setToolTip(str(result.path))
                item.setText(result.path.name)
                self.file_list.addItem(item)
                if not self.merge_output.text():
                    self.merge_output.setText(str(result.path.parent / "合并结果.pdf"))
            else:
                self.split_source = result
                self.page_index = 0
                self.source_name.setText(QFontMetrics(self.source_name.font()).elidedText(
                    result.path.name, Qt.TextElideMode.ElideMiddle, max(180, self.source_name.width())))
                self.source_name.setToolTip(str(result.path))
                self.preview.display(result.preview)
                self.page_label.setText(f"1 / {result.pages}")
                self.page_range.clear()
                if not self.split_output.text():
                    self.split_output.setText(str(result.path.parent))
        self.status.setText(f"已导入 {imported} 个 PDF" + (f"，跳过 {len(issues)} 个文件" if issues else ""))
        self._refresh()
        if issues:
            QMessageBox.warning(self, "部分文件未导入", "\n\n".join(issues[:15]))

    def _choose_merge_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存合并 PDF", self.merge_output.text() or str(Path(self._last_directory()) / "合并结果.pdf"),
                                             "PDF 文件 (*.pdf)", options=QFileDialog.Option.DontConfirmOverwrite)
        if path:
            self.merge_output.setText(path if path.lower().endswith(".pdf") else path + ".pdf")

    def _choose_split_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择拆分结果的保存文件夹", self.split_output.text() or self._last_directory())
        if path:
            self.split_output.setText(path)

    def _navigate(self, offset):
        if self.busy or self.split_source is None:
            return
        target = self.page_index + offset
        if not 0 <= target < self.split_source.pages:
            return
        source = self.split_source

        def show(data):
            self.page_index = target
            self.preview.display(data)
            self.page_label.setText(f"{target + 1} / {source.pages}")
            self.status.setText("准备就绪")
            self._refresh()

        self._run_task(lambda progress, cancel: preview_page(source, target), show, "正在载入页面…")

    def _execute(self):
        if self.busy:
            return
        try:
            if self.pages.currentIndex() == 2:
                sources = self._documents()
                if not sources:
                    return
                if not self.convert_output.text().strip():
                    self._choose_convert_output()
                    if not self.convert_output.text().strip():
                        return
                destination = Path(self.convert_output.text().strip())
                options = dict(combine=self.conversion_mode.currentIndex() == 1,
                               libreoffice=self.office_path.text().strip(), text_encoding=self.text_encoding.currentData())
                self._converted_count = 1 if options["combine"] else len(sources)
                self._run_task(lambda p, c: convert_documents(sources, destination, progress=p, cancel=c, **options),
                               self._conversion_complete, "正在转换文档…")
            elif self.pages.currentIndex() == 0:
                base = self.base_source if self.merge_mode.currentIndex() == 1 else None
                if self.merge_mode.currentIndex() == 1 and base is None:
                    raise PdfError("请先选择现有 PDF。")
                offset = self._insertion_offset() if base else None
                if not self.merge_output.text().strip():
                    self._choose_merge_output()
                    if not self.merge_output.text().strip():
                        return
                destination = Path(self.merge_output.text().strip()).absolute()
                overwrite = False
                if destination.exists():
                    if any(os.path.normcase(str(source.path.resolve())) == os.path.normcase(str(destination.resolve())) for source in self._sources() + ([base] if base else [])):
                        raise PdfError("输出位置是原始文件，请换一个文件名。")
                    overwrite = QMessageBox.question(self, "文件已存在", f"{destination.name} 已存在，是否替换？",
                                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                                      QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
                    if not overwrite:
                        return
                sources = self._sources()
                self._merged_count = sum(source.pages for source in sources) + (base.pages if base else 0)
                self._run_task(lambda p, c: merge_pdfs(sources, destination, overwrite=overwrite, base=base, insert_after=offset, progress=p, cancel=c),
                               self._complete, "正在合并 PDF…")
            else:
                if self.split_source is None:
                    return
                selected = parse_pages(self.page_range.text(), self.split_source.pages)
                if not self.split_output.text().strip():
                    self._choose_split_output()
                    if not self.split_output.text().strip():
                        return
                source = self.split_source
                destination = Path(self.split_output.text().strip())
                options = dict(output_format=self.format_names[self.formats.checkedId()], pages=self.page_range.text(),
                               start=self.start_number.value(), padding=self.padding.value(), dpi=self.dpi.currentData(),
                               preserve_signature_appearance=self.keep_signature.isChecked())
                self._split_count = len(selected)
                self._run_task(lambda p, c: split_pdf(source, destination, progress=p, cancel=c, **options),
                               self._complete, "正在拆分 PDF…")
        except (PdfError, OSError) as exc:
            QMessageBox.warning(self, "请检查设置", str(exc))

    def _set_busy(self, busy: bool):
        self.busy = busy
        self.pages.setEnabled(not busy)
        for nav in self.navigation.buttons():
            nav.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.progress.setVisible(busy)
        self.open_result.setVisible(not busy and self.last_output is not None)
        self._refresh()

    def _run_task(self, action: Callable, completed: Callable, message: str):
        if self.busy:
            return
        self._set_busy(True)
        self.status.setText(message)
        self.progress.setRange(0, 0)
        worker = Worker(action, self)
        self.worker = worker
        self.workers.add(worker)
        # Deliver result only after QThread.finished, so the next task cannot overlap.
        state = {}
        worker.result.connect(lambda value: state.update(result=value))
        worker.failed.connect(lambda value: state.update(error=value))
        worker.cancelled.connect(lambda: state.update(cancelled=True))
        worker.progress.connect(self._progress)

        def finished():
            self.workers.discard(worker)
            self.worker = None
            self._set_busy(False)
            worker.deleteLater()
            if "error" in state:
                self.status.setText("处理未完成，请检查后重试")
                QMessageBox.warning(self, "处理失败", state["error"])
            elif state.get("cancelled"):
                self.status.setText("已取消，本次未生成输出文件")
            elif "result" in state:
                completed(state["result"])

        worker.finished.connect(finished)
        worker.start()

    def _progress(self, done, total, text):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.status.setText(QFontMetrics(self.status.font()).elidedText(text, Qt.TextElideMode.ElideMiddle, max(220, self.status.width())))

    def _cancel(self):
        if self.worker:
            self.worker.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.status.setText("正在取消，当前页面处理完毕后停止…")

    def _complete(self, path: Path):
        self.last_output = path
        self.open_result.show()
        if path.is_dir():
            self.status.setText(f"✓ 拆分完成，已导出 {self._split_count} 个文件")
        else:
            self.status.setText(f"✓ 合并完成，共 {self._merged_count} 页")
        self.status.setToolTip(str(path))

    def _conversion_complete(self, path: Path):
        self.last_output = path
        self.open_result.show()
        self.status.setText(f"✓ 转换完成，已保存 {self._converted_count} 个 PDF")
        self.status.setToolTip(str(path))

    def _open_result(self):
        if self.last_output is None:
            return
        target = self.last_output if self.last_output.is_dir() else self.last_output.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def closeEvent(self, event):
        if self.busy:
            QMessageBox.information(self, "正在处理", "请等待处理完成，或先点击「取消」再关闭窗口。")
            event.ignore()
        else:
            event.accept()


def configure_application(app):
    # The offscreen Qt plugin has no system font database on Windows.
    if not QFontDatabase.families() and os.name == "nt":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "seguisym.ttf"):
            if (fonts / name).is_file():
                QFontDatabase.addApplicationFont(str(fonts / name))
    app.setFont(QFont(UI_FONT, 10))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)


def _smoke_pdf_checks(folder: Path) -> list[str]:
    """Exercise the bundled PDF native libraries without opening user files."""
    import tempfile
    import pymupdf
    testdir = Path(tempfile.mkdtemp(prefix="pdf-check-", dir=folder))
    sources = []
    for name, tag, count in (("文件1.pdf", "FIRST", 2), ("文件2.pdf", "SECOND", 1)):
        path = testdir / name
        with pymupdf.open() as document:
            for index in range(count):
                page = document.new_page(width=300, height=420)
                page.insert_text((25, 70), f"{tag} PAGE {index + 1}", fontsize=18)
            document.save(str(path))
        sources.append(inspect_pdf(path))
    merged = merge_pdfs(sources, testdir / "合并结果.pdf")
    with pymupdf.open(str(merged)) as document:
        assert [page.get_text().strip() for page in document] == ["FIRST PAGE 1", "FIRST PAGE 2", "SECOND PAGE 1"]
    combined = inspect_pdf(merged)
    checks = ["merge_import_order", "chinese_paths", "page_preview"]
    for offset in range(4):
        inserted = merge_pdfs([sources[1]], testdir / f"insert-{offset}.pdf", base=combined, insert_after=offset)
        expected = ["FIRST PAGE 1", "FIRST PAGE 2", "SECOND PAGE 1"]
        with pymupdf.open(str(inserted)) as document:
            assert [page.get_text().strip() for page in document] == expected[:offset] + ["SECOND PAGE 1"] + expected[offset:]
    checks.append("insert_into_existing_pdf_all_positions")
    if "--signature-fixture" in sys.argv:
        fixture = Path(sys.argv[sys.argv.index("--signature-fixture") + 1])
        signed_source = inspect_pdf(fixture)
        signed_output = split_pdf(signed_source, testdir, pages="2")
        with pymupdf.open(str(fixture)) as original, pymupdf.open(str(signed_output / "1.pdf")) as single:
            assert single[0].get_pixmap(dpi=144).samples == original[1].get_pixmap(dpi=144).samples
            assert not list(single[0].widgets() or ())
        checks.append("signed_pdf_visible_appearance")
    for extension in ("pdf", "png", "jpg"):
        result = split_pdf(combined, testdir, output_format=extension, padding=3, dpi=72)
        assert sorted(path.name for path in result.iterdir()) == [f"001.{extension}", f"002.{extension}", f"003.{extension}"]
        if extension == "pdf":
            with pymupdf.open(str(result / "001.pdf")) as document:
                assert document.page_count == 1
                assert "FIRST PAGE 1" in document[0].get_text()
        else:
            pixmap = pymupdf.Pixmap(str(result / f"001.{extension}"))
            assert (pixmap.width, pixmap.height) == (300, 420)
        checks.append("split_" + extension + "_numeric_names")
    text = testdir / "中文文本.txt"
    text.write_text("PAPERFLOW TEXT 中文转换\n" + "分页检查\n" * 80, encoding="utf-8")
    image = testdir / "图片.png"
    with pymupdf.open(str(merged)) as document:
        document[0].get_pixmap().save(image)
    result = convert_documents([text, image], testdir, combine=True)
    with pymupdf.open(result / "合并结果.pdf") as document:
        assert len(document) >= 3 and "中文转换" in document[0].get_text()
        assert document[-1].get_images()
    checks.append("convert_images_chinese_text_and_order")
    if "--document-fixtures" in sys.argv:
        fixtures = Path(sys.argv[sys.argv.index("--document-fixtures") + 1])
        office_files = [fixtures / name for name in ("word.docx", "excel.xlsx", "slides.pptx")]
        result = convert_documents(office_files, testdir, combine=True)
        with pymupdf.open(result / "合并结果.pdf") as document:
            assert len(document) == 3
            for page, tag in zip(document, ("WORD SAMPLE", "EXCEL SAMPLE", "POWERPOINT SAMPLE")):
                assert tag in page.get_text()
                assert "中文测试" in page.get_text().replace(" ", "")
        checks.append("convert_word_excel_powerpoint")
    return checks


def main():
    smoke_flag = "--smoke-test" if "--smoke-test" in sys.argv else "--gui-smoke-test"
    smoke = smoke_flag in sys.argv
    if smoke and smoke_flag == "--smoke-test":
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication(sys.argv)
    app.setApplicationName("PaperFlow")
    app.setOrganizationName("PaperFlow")
    configure_application(app)
    logdir = log_directory()
    logdir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=logdir / "paperflow.log", level=logging.ERROR,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    window = MainWindow()
    window.show()
    if smoke:
        folder = Path(sys.argv[sys.argv.index(smoke_flag) + 1]).resolve()
        folder.mkdir(parents=True, exist_ok=True)

        def snapshot():
            try:
                window.grab().save(str(folder / "packaged-merge.png"))
                window._switch(1)
                app.processEvents()
                window.grab().save(str(folder / "packaged-split.png"))
                window._switch(2)
                app.processEvents()
                window.grab().save(str(folder / "packaged-convert.png"))
                checks = _smoke_pdf_checks(folder)
                result = {"ok": True, "frozen": bool(getattr(sys, "frozen", False)),
                          "title": window.windowTitle(), "checks": checks}
                code = 0
            except Exception as exc:
                logging.exception("Packaged smoke check failed")
                result = {"ok": False, "error": str(exc)}
                code = 1
            (folder / "smoke.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            app.exit(code)

        QTimer.singleShot(500, snapshot)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
