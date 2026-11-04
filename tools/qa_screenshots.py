"""Generate local UI samples for visual review, including populated states."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem
from app import MainWindow, configure_application
from pdf_engine import inspect_pdf, split_pdf

app = QApplication([])
configure_application(app)
folder = ROOT / "tmp/qa"
folder.mkdir(parents=True, exist_ok=True)
sources = []
for name, title, count in (("01_项目方案.pdf", "PROJECT PROPOSAL", 3), ("02_参考资料.pdf", "REFERENCE NOTES", 2)):
    path = folder / name
    with pymupdf.open() as document:
        for index in range(count):
            page = document.new_page(width=595, height=842)
            page.draw_rect(pymupdf.Rect(0, 0, 595, 150), color=None, fill=(0.13, 0.41, 0.29))
            page.insert_text((48, 88), "PAPERFLOW", fontsize=30, color=(1, 1, 1))
            page.insert_text((48, 220), title, fontsize=24, color=(0.13, 0.41, 0.29))
            page.insert_text((48, 265), f"Original page {index + 1} of {count}", fontsize=14)
            for y in range(330, 650, 45):
                page.draw_line((48, y), (545, y), color=(0.8, 0.85, 0.82), width=1)
            page.insert_text((48, 780), f"PAGE {index + 1:02d}", fontsize=12, color=(0.4, 0.5, 0.44))
        document.save(str(path))
    sources.append(inspect_pdf(path))
window = MainWindow()
window.show()
for source in sources:
    item = QListWidgetItem(source.path.name)
    item.setData(Qt.ItemDataRole.UserRole, source)
    window.file_list.addItem(item)
window.merge_output.setText(str(folder / "合并结果.pdf"))
window.file_list.setCurrentRow(0)
window._refresh()
app.processEvents()
window.grab().save(str(folder / "merge-populated.png"))
window.merge_mode.setCurrentIndex(1)
window.base_source = sources[0]
window.base_name.setText(f"{sources[0].path.name} · 共 {sources[0].pages} 页")
window.insert_page.setMaximum(sources[0].pages)
window.insert_position.setCurrentIndex(3)
window.insert_page.setValue(2)
window._refresh()
app.processEvents()
window.grab().save(str(folder / "insert-populated.png"))
window.merge_mode.setCurrentIndex(0)
window._switch(1)
window.split_source = sources[0]
window.source_name.setText(sources[0].path.name)
window.preview.display(sources[0].preview)
window.page_label.setText("1 / 3")
window.padding.setValue(3)
window.formats.button(1).click()
window.split_output.setText(str(folder))
window._refresh()
app.processEvents()
window.grab().save(str(folder / "split-populated.png"))
window.resize(980, 780)
app.processEvents()
window.grab().save(str(folder / "split-minimum.png"))
result = split_pdf(sources[0], folder, output_format="png", padding=3, dpi=72)
print(result)
window.close()
