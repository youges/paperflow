# Third-party notices

PaperFlow source code is licensed under the GNU Affero General Public License,
version 3 or later. The full text is supplied in LICENSE.txt.

This distribution includes the following components. Upstream copyright and
license notices remain with their respective authors.

* PyMuPDF 1.28.2 / MuPDF, Copyright Artifex Software, Inc.
  GNU Affero General Public License v3 or Artifex commercial licensing.
  This distribution uses the AGPL option.
  Source: https://github.com/pymupdf/PyMuPDF and https://mupdf.com/
  License: licenses/AGPL-3.0.txt
* PySide6 Essentials, Qt 6.12.0 and Shiboken6 6.12.0, The Qt Company Ltd.
  PySide/Shiboken: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only.
  Qt Core/Gui/Widgets are dynamically linked. Libraries are not modified.
  This distribution uses the LGPL v3 option where available.
  Source: https://code.qt.io/cgit/pyside/pyside-setup.git/
  Qt source: https://code.qt.io/cgit/qt/qtbase.git/
  Licenses: licenses/LGPL-3.0.txt and licenses/GPL-3.0.txt
* CPython 3.14, Python Software Foundation and contributors.
  License: licenses/PYTHON-LICENSE.txt
  Source: https://www.python.org/
* PyInstaller 6.22.3 bootloader, PyInstaller contributors.
  GPL v2 or later with the PyInstaller bootloader exception, as described in
  licenses/PYINSTALLER-LICENSE.txt.
  Source: https://github.com/pyinstaller/pyinstaller

Corresponding application source and build instructions are supplied in
PaperFlow-source.zip. The same source can be run directly with an independently
installed compatible Qt/PySide package; see README.md. PyInstaller extracts the
shared libraries when the executable starts. No application font is redistributed;
the application uses fonts provided by the operating system (Windows fonts or
Linux desktop fonts such as Noto Sans CJK).
