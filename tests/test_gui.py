import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from app import MainWindow, configure_application
from test_engine import make_pdf, texts


@pytest.fixture(scope="module")
def qtapp():
    app = QApplication.instance() or QApplication([])
    configure_application(app)
    return app


def wait_until_idle(window, app):
    limit = time.monotonic() + 20
    while window.busy and time.monotonic() < limit:
        app.processEvents()
        QTest.qWait(10)
    app.processEvents()
    assert not window.busy, "Background PDF operation did not finish"


def test_gui_import_reorder_merge_and_split(qtapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(str(args[2])))
    window = MainWindow()
    window.show()
    first = make_pdf(tmp_path / "Z文件1.pdf", "FIRST", 2)
    second = make_pdf(tmp_path / "A文件2.pdf", "SECOND", 1)
    window._load_files([str(first)], "merge")
    wait_until_idle(window, qtapp)
    window._load_files([str(second)], "merge")
    wait_until_idle(window, qtapp)
    assert [source.path for source in window._sources()] == [first, second]
    window.file_list.setCurrentRow(1)
    QTest.mouseClick(window.up_button, Qt.MouseButton.LeftButton)
    assert [source.path for source in window._sources()] == [second, first]
    QTest.mouseClick(window.down_button, Qt.MouseButton.LeftButton)
    destination = tmp_path / "gui-merged.pdf"
    window.merge_output.setText(str(destination))
    QTest.mouseClick(window.run_button, Qt.MouseButton.LeftButton)
    wait_until_idle(window, qtapp)
    assert texts(destination) == ["FIRST PAGE 1", "FIRST PAGE 2", "SECOND PAGE 1"]

    window._switch(1)
    window._load_files([str(destination)], "split")
    wait_until_idle(window, qtapp)
    assert not window.preview.original.isNull()
    QTest.mouseClick(window.next_button, Qt.MouseButton.LeftButton)
    wait_until_idle(window, qtapp)
    assert window.page_index == 1
    window.formats.button(1).click()
    window.padding.setValue(3)
    window.start_number.setValue(10)
    window.page_range.setText("3,1")
    window.split_output.setText(str(tmp_path))
    assert "010.png" in window.naming_preview.text()
    QTest.mouseClick(window.run_button, Qt.MouseButton.LeftButton)
    wait_until_idle(window, qtapp)
    assert sorted(p.name for p in window.last_output.iterdir()) == ["010.png", "011.png"]
    assert window.open_result.isVisible()
    window.close()


def test_encrypted_file_keeps_original_import_position(qtapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("secret", True))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(str(args[2])))
    first = make_pdf(tmp_path / "先导入.pdf", "FIRST", 1, "secret")
    second = make_pdf(tmp_path / "后导入.pdf", "SECOND", 1)
    window = MainWindow()
    window._load_files([str(first), str(second)], "merge")
    wait_until_idle(window, qtapp)
    assert [source.path for source in window._sources()] == [first, second]
    window.close()


def test_gui_insert_before_and_after_page(qtapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(str(args[2])))
    base = make_pdf(tmp_path / "已合并.pdf", "BASE", 3)
    new = make_pdf(tmp_path / "新增.pdf", "NEW", 1)
    window = MainWindow()
    window.show()
    window.merge_mode.setCurrentIndex(1)
    window._load_files([str(new)], "merge")
    wait_until_idle(window, qtapp)
    assert not window.run_button.isEnabled()
    window._load_files([str(base)], "base")
    wait_until_idle(window, qtapp)
    assert window.insert_page.maximum() == 3
    for mode, offset in ((0, 0), (1, 3), (2, 1), (3, 2)):
        window.insert_position.setCurrentIndex(mode)
        window.insert_page.setValue(2)
        output = tmp_path / f"insert-{mode}.pdf"
        window.merge_output.setText(str(output))
        QTest.mouseClick(window.run_button, Qt.MouseButton.LeftButton)
        wait_until_idle(window, qtapp)
        original = ["BASE PAGE 1", "BASE PAGE 2", "BASE PAGE 3"]
        assert texts(output) == original[:offset] + ["NEW PAGE 1"] + original[offset:]
        assert "4 页" in window.status.text()
    window.merge_mode.setCurrentIndex(0)
    assert not window.insert_panel.isVisible()
    window.close()


def test_gui_document_conversion_reorder_and_modes(qtapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(str(args[2])))
    first, second = tmp_path / "Z说明.txt", tmp_path / "A说明.txt"
    first.write_text("FIRST 中文", encoding="utf-8")
    second.write_text("SECOND 中文", encoding="utf-8")
    window = MainWindow()
    window.show()
    window._switch(2)
    assert window.run_button.text() == "转换并保存"
    assert not window.run_button.isEnabled()
    window._add_documents([str(first)])
    window._add_documents([str(second)])
    assert window._documents() == [first, second]
    QTest.mouseClick(window.document_up, Qt.MouseButton.LeftButton)
    assert window._documents() == [second, first]
    window.conversion_mode.setCurrentIndex(1)
    window.convert_output.setText(str(tmp_path))
    QTest.mouseClick(window.run_button, Qt.MouseButton.LeftButton)
    wait_until_idle(window, qtapp)
    merged = window.last_output / "合并结果.pdf"
    assert texts(merged) == ["SECOND 中文", "FIRST 中文"]
    assert "1 个 PDF" in window.status.text()
    window.conversion_mode.setCurrentIndex(0)
    QTest.mouseClick(window.run_button, Qt.MouseButton.LeftButton)
    wait_until_idle(window, qtapp)
    assert sorted(path.name for path in window.last_output.iterdir()) == ["A说明.pdf", "Z说明.pdf"]
    assert merged.is_file()
    QTest.mouseClick(window.document_clear, Qt.MouseButton.LeftButton)
    assert not window.run_button.isEnabled()
    window.close()
