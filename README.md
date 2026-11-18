# 纸序 PaperFlow

一个在本机运行的中文 PDF 合并、拆分与双向文档转换工具。无需账户，无需上传文件。

[下载 Linux / Windows 安装包](https://github.com/youges/paperflow/releases/latest) · [构建进度](https://github.com/youges/paperflow/actions)

## 直接使用

版本 1.4.0 提供以下 64 位（x86_64 / amd64）发行包，无需安装 Python：

| 平台 | 文件 | 安装方式 |
| --- | --- | --- |
| Windows 10 / 11 | `PaperFlow-1.4.0-Windows-x64-Setup.exe` | 双击安装；当前用户安装，无需管理员权限，支持开始菜单、可选桌面快捷方式和卸载 |
| Ubuntu 24.04+ / Debian 13+ | `paperflow_1.4.0_amd64.deb` | 在下载目录执行 `sudo apt install ./paperflow_1.4.0_amd64.deb`，然后在应用菜单打开“纸序 PDF 工具”，或运行 `paperflow` |
| Linux 便携版 | `PaperFlow-1.4.0-Linux-x86_64.tar.gz` | 解压后执行 `./PaperFlow/PaperFlow`，仍需系统桌面依赖和 glibc 2.39+ |
| Windows 便携版 | `PaperFlow-Windows.zip` / `PaperFlow.exe` | 解压后双击程序 |

Linux 包在 Ubuntu 24.04 amd64 上构建、安装及图形界面自检；其他发行版仅在运行库兼容时可使用，不包含 ARM / Alpine musl 支持。建议安装 `fonts-noto-cjk` 以正确显示中文。Debian 13 属兼容目标，未单独在 Debian 上运行集成测试。

Windows 可在“设置 → 应用”或开始菜单的卸载入口卸载；Linux 卸载命令为 `sudo apt remove paperflow`。卸载不会删除用户自己的 PDF 和个人设置。便携版首次打开需要片刻解压运行环境。

### PDF 转 Word（1.4 新增）

1. 进入「PDF 转 Word」，选择源 PDF；加密文件会提示输入打开密码。
2. 选择「可编辑 Word」重建文字、图片及表格，或选择「原页图片」保留页面外观。
3. 页码范围留空处理全部页面，也可填写 `1-5, 8, 10-12`，按原 PDF 页序写入同一个 `.docx`。
4. 选择保存路径，点击「转换为 Word」。已有同名结果会询问是否替换，失败或取消时不会留下不完整的 Word 文件。

PDF 转 Word 使用程序内置组件，无需安装 Word、WPS 或 LibreOffice。输出可用这些应用打开编辑。可编辑模式包含表格列宽修复和防裁切处理，尽量还原原布局；PDF 是固定版式，复杂表格、特殊字体、跨页内容和在不同 Office 软件中的分页可能仍有差异，请核对转换结果。

本功能不含 OCR。没有可提取文字的扫描 PDF，在可编辑模式下会明确提示；可先 OCR，或选择原页图片模式。图片模式每页放置一张整页图片，可选 150/200/300 DPI，文字不可编辑，适合保留扫描页、可见签名、印章和批注。可编辑模式会在内存中固定所选页面的数字签名表单外观再重建版面；两种模式都不继承原 PDF 数字签名的验证效力，原始 PDF 保持完整。

### 文档转 PDF（1.3 新增）

1. 进入「文档转 PDF」，点击「添加文档」，或将文件拖入列表，可多次添加。
2. 选择「每个文档分别保存为 PDF」，或「按列表顺序转换并合为一份 PDF」。拖动文件或点击上移/下移可调整顺序。
3. 选择保存文件夹，点击「转换并保存」。程序会新建 `文档转PDF` 结果文件夹，后续转换自动使用新的编号文件夹。原文档和已有结果不会被覆盖。

| 类别 | 支持的格式 | 转换组件 |
| --- | --- | --- |
| Word / 文字文档 | DOC、DOCX、ODT、RTF | LibreOffice Writer |
| Excel / 表格 | XLS、XLSX、ODS | LibreOffice Calc |
| PowerPoint / 演示 | PPT、PPTX、ODP | LibreOffice Impress |
| 图片 | PNG、JPG、JPEG、BMP、TIF、TIFF（含多页） | 程序自带 |
| 纯文本 | TXT | 程序自带，中文自动换行分页 |

Office 文档需要安装免费的 [LibreOffice](https://www.libreoffice.org/download/download-libreoffice/)，无需 Microsoft Office。Windows 在本页点击「下载 LibreOffice」，安装 Writer、Calc、Impress 后点击「重新检测」。也可选择其 `program/soffice.com` 或 `soffice.exe`；Linux 选择 `soffice` 或 `libreoffice`。程序会记住手选路径，清空路径可恢复自动检测。开发/自动化环境也可设置 `PAPERFLOW_LIBREOFFICE`。

Linux 使用普通 `sudo apt install ./paperflow_1.4.0_amd64.deb` 时会通过推荐依赖安装上述组件。若使用了 `--no-install-recommends` 或便携版，请执行 `sudo apt install libreoffice-writer libreoffice-calc libreoffice-impress fonts-noto-cjk`。未安装组件时，图片和 TXT 仍可使用。

TXT 自动尝试 UTF-8、带 BOM 的 UTF-16 和 GB18030；也可手动选择编码，UTF-16 无 BOM 文件请手选对应编码前先保存为带 BOM 的文本。输出为 A4 纵向，内置中文后备字体，无需安装系统中文字体。保留可复制文字，长行自动换行，长文自动分页。

分别保存时，PDF 沿用原文件名，遇到同名文档自动编号。合为一份时，按列表顺序连接各文档的全部页面，图片按原尺寸成页，TIFF 保留所有帧。处理失败或取消会清理本次临时结果；Office 转换超时（单文件 180 秒）会停止此次批处理，不关闭用户已打开的 LibreOffice 窗口。

转换在本机进行，Office 宏在独立的临时配置中禁用。加密或损坏的 Office 文档请先在原应用中处理后再转换。Office 排版取决于本机字体、LibreOffice 兼容性及文档打印设置；Excel 尤其应先确认打印区域和分页，复杂图表、公式及幻灯片效果请核对输出。转换成 PDF 不会继承源文档的数字签名验证效力。

### 合并 PDF

1. 进入「合并 PDF」，点击「添加 PDF」，也可以把文件拖进列表。
2. 可以多次导入：先导入文件 1，再导入文件 2，结果就是文件 1 的全部页面接着文件 2 的全部页面。
3. 列表从上到下就是最终合并顺序；拖动条目，或选中文件点击「上移 / 下移」可调整顺序。
4. 选择保存路径，点击「合并并保存」。完成后点击「打开结果位置」。

同一批多选时，以文件选择器返回并显示在列表中的顺序为准。若需要严格按照添加先后排列，可逐次添加，并在合并前查看列表编号。程序不会按文件名自动排序。

### 插入到现有 PDF（1.1 新增）

1. 进入「合并 PDF」，将顶部模式切换为「插入到现有 PDF」。
2. 点击「选择现有 PDF」，选择之前已经合并好的文件。
3. 下方添加需要插入的新 PDF，可以添加多个，并调整列表顺序。
4. 选择插入位置：文档开头、文档末尾、指定页之前或指定页之后。指定页码以现有 PDF 的原始页码为准。
5. 例如原文档有 10 页，选择「指定页之后」的第 3 页，结果顺序为：原第 1–3 页 → 所有新文件（按列表顺序）→ 原第 4–10 页。新文件作为一个连续整体插入同一位置。
6. 选择另存路径，点击「插入并另存」。现有 PDF 和新增文件都会保留；若要继续插入，可将新结果作为下一次的现有 PDF。

### 拆分 PDF 或图片

1. 进入「拆分 PDF」，选择一个 PDF；可用左右按钮预览页面。
2. 选择「单页 PDF」「PNG 图片」或「JPG 图片」。
3. 设置起始数字与补零位数，例如起始数字 1、补零位数 3，会得到 `001.pdf、002.pdf、003.pdf`，图片则使用 `.png` 或 `.jpg`。
4. 页码范围留空表示全部页面；也可输入 `1-5, 8, 10-12`。程序会去重，并按原文档的页序连续编号。例如选择第 2、5 页，起始数字为 1，将得到 `1.pdf`（原第 2 页）和 `2.pdf`（原第 5 页）。
5. 图片可选择 72、150、300、600 DPI；DPI 越高，图片越清楚、体积越大。超大页面超过单页 8000 万像素时，请降低 DPI。
6. 选择保存文件夹，点击「拆分并保存」。程序会新建 `原文件名_拆分_PDF`（或 PNG / JPG）子文件夹，已有同名结果会自动使用新文件夹。

### 带数字签名的 PDF（1.1.1 修复）

拆分为单页 PDF 时，默认勾选「保留签名/印章的可见外观」。检测到数字签名后，会先在内存中将该文档的表单（包括签名外观）固定为页面内容，再拆分，避免签名外观在复制页面时丢失。文字与矢量内容保持原有形式，并非将整页转成图片；含签名文档中的其他表单也会失去交互编辑能力。普通未签名表单保持原处理方式。取消勾选可使用原来的复制方式，但数字签名外观可能丢失。

PNG / JPG 会渲染原页面上可见的签名、印章和批注。无可见外观的数字签名本身不会变成图案。保留外观不等于保留证书验证效力：单页新文件不能继承原数字签名，验签仍须使用未被改动的原始签名 PDF。程序不会修改原始文件。

## 其他说明

- 所有 PDF 读取、合并、拆分和文档转换都在本机完成，程序没有上传功能。
- 加密 PDF 会提示输入打开密码；密码只在当前程序内存中保留，不写入设置或日志。导出结果为未加密文件。
- 原始 PDF 不会被覆盖；替换已有合并结果时会先询问。
- 点击「取消」后，在当前处理步骤结束时停止，并清理本次临时结果。保存大型 PDF 时需要等待当前保存步骤结束。
- 页面旋转和页面尺寸会保留，单页 PDF 保留文字、图像与可复制的文本；输出图片为页面的平面图像。
- 支持常见 PDF 页面和表单。单页拆分支持按上述方式保留签名外观；文档级附件、数字签名的验证效力、原有书签不属于本工具的保留范围；请保留原始文件。
- Windows 错误日志在 `%LOCALAPPDATA%\PaperFlow\paperflow.log`；Linux 位于 `${XDG_STATE_HOME:-~/.local/state}/paperflow/paperflow.log`。启动异常日志在同一目录的 `startup.log`。

## 从源码运行

使用 Python 3.14（64 位）在项目目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

## 测试与打包

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
.\build.ps1
```

打包输出：`dist/PaperFlow.exe` 和 `dist/PaperFlow-Windows.zip`。ZIP 中包含可执行文件、说明、源码压缩包和第三方许可文件。

Windows 构建安装包需要 Inno Setup 6；Linux 在 Ubuntu 24.04 安装桌面依赖、`python3-venv`、`dpkg-dev` 后运行 `bash build.sh`。`tools/build_installers.py` 创建原生安装包，`tools/verify_install.py` 验证安装后的程序和卸载。GitHub Actions 分别在 Windows 和 Ubuntu 构建，两个平台的测试全部通过后才发布到 Release。

源码结构：`app.py` 为桌面界面，`launcher.py` 为带启动日志的打包入口，`pdf_engine.py` 为独立 PDF 处理核心，`conversion_engine.py` 为本地文档转 PDF 引擎，`word_engine.py` 为 PDF 转 Word 引擎，`tests/` 为功能与界面集成测试，`tools/` 为构建和界面检查工具。

本项目以 GNU AGPL v3 或更新版本许可发布；使用 PyMuPDF（AGPL / 商业双许可）及 PySide6 / Qt / Shiboken（按随附许可）。详见 `LICENSE.txt`、`THIRD_PARTY_NOTICES.md` 和 `licenses/`。
