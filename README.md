# 纸序 PaperFlow

一个在本机运行的中文 PDF 合并、拆分工具。无需账户，无需上传文件。

[下载 Linux / Windows 安装包](https://github.com/youges/paperflow/releases/latest) · [构建进度](https://github.com/youges/paperflow/actions)

## 直接使用

版本 1.2.0 提供以下 64 位（x86_64 / amd64）发行包，无需安装 Python：

| 平台 | 文件 | 安装方式 |
| --- | --- | --- |
| Windows 10 / 11 | `PaperFlow-1.2.0-Windows-x64-Setup.exe` | 双击安装；当前用户安装，无需管理员权限，支持开始菜单、可选桌面快捷方式和卸载 |
| Ubuntu 24.04+ / Debian 13+ | `paperflow_1.2.0_amd64.deb` | 在下载目录执行 `sudo apt install ./paperflow_1.2.0_amd64.deb`，然后在应用菜单打开“纸序 PDF 工具”，或运行 `paperflow` |
| Linux 便携版 | `PaperFlow-1.2.0-Linux-x86_64.tar.gz` | 解压后执行 `./PaperFlow/PaperFlow`，仍需系统桌面依赖和 glibc 2.39+ |
| Windows 便携版 | `PaperFlow-Windows.zip` / `PaperFlow.exe` | 解压后双击程序 |

Linux 包在 Ubuntu 24.04 amd64 上构建、安装及图形界面自检；其他发行版仅在运行库兼容时可使用，不包含 ARM / Alpine musl 支持。建议安装 `fonts-noto-cjk` 以正确显示中文。Debian 13 属兼容目标，未单独在 Debian 上运行集成测试。

Windows 可在“设置 → 应用”或开始菜单的卸载入口卸载；Linux 卸载命令为 `sudo apt remove paperflow`。卸载不会删除用户自己的 PDF 和个人设置。便携版首次打开需要片刻解压运行环境。

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

- 所有 PDF 读取、合并、拆分都在本机完成，程序没有上传功能。
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

源码结构：`app.py` 为桌面界面，`launcher.py` 为带启动日志的打包入口，`pdf_engine.py` 为独立 PDF 处理核心，`tests/` 为功能与界面集成测试，`tools/` 为构建和界面检查工具。

本项目以 GNU AGPL v3 或更新版本许可发布；使用 PyMuPDF（AGPL / 商业双许可）及 PySide6 / Qt / Shiboken（按随附许可）。详见 `LICENSE.txt`、`THIRD_PARTY_NOTICES.md` 和 `licenses/`。
