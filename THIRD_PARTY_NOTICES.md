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
shared libraries when the executable starts. No separate UI font is redistributed;
the application uses fonts provided by the operating system (Windows fonts or
Linux desktop fonts such as Noto Sans CJK).

Office document conversion invokes a separately installed, unmodified LibreOffice
via its command-line interface. LibreOffice is not bundled in the PaperFlow
Windows executable or portable archive. Linux package recommendations can install
it through the operating system package manager. Its own license notices and
source are available at https://www.libreoffice.org/about-us/licenses/.
The TXT converter uses the unmodified CJK fallback font provided by MuPDF;
this is separate from the system fonts used by the application interface.

PDF-to-Word conversion additionally uses these unmodified components. Their
upstream license texts (including bundled native-library notices) are copied
from installed distributions into licenses/dependencies/ during the build:
* pdf2docx 0.5.13, Artifex Software and contributors: MIT.
  https://github.com/ArtifexSoftware/pdf2docx
* python-docx 1.2.0: MIT. https://github.com/python-openxml/python-docx
* NumPy 2.5.5: BSD-3-Clause, with bundled BLAS/runtime notices.
  https://numpy.org/
* OpenCV Python headless 5.1.0.95: Apache-2.0 and bundled third-party notices.
  https://github.com/opencv/opencv-python
* FontTools 4.68.0: MIT. https://github.com/fonttools/fonttools
* lxml 6.1.3: BSD-3-Clause and libxml2/libxslt notices. https://lxml.de/
* typing_extensions 4.16.0: PSF-2.0. https://github.com/python/typing_extensions
* Fire 0.7.1: Apache-2.0. https://github.com/google/python-fire
* termcolor 3.3.0: MIT. https://github.com/termcolor/termcolor
