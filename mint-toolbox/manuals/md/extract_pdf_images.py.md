# extract_pdf_images.py — 批量提取 PDF 内嵌图片

> 分类：文件与归档 · 状态：当前版本 · 风险：低 · 启动器：register

## 功能

从单个 PDF 或目录中的所有 PDF 提取内嵌位图；默认去除页面之间的重复图片。

## 用法

```bash
python3 extract_pdf_images.py document.pdf
python3 extract_pdf_images.py ./pdfs --output ./images
python3 extract_pdf_images.py document.pdf --include-duplicates
```

## 参数与选项

- `input`：PDF 文件或包含 PDF 的目录（只扫描该目录直系文件）。
- `-o`、`--output DIR`：默认 `extracted_images`。
- `--include-duplicates`：重复出现的图片也重新导出。

## 依赖与运行环境

- Python3（含 `venv`/`pip`）；依赖 PyMuPDF。
- 脚本会在**自身所在目录**建立 `.extract_pdf_images_venv` 并首次通过 pip 安装 PyMuPDF。

## 输出与副作用

- 在目标目录写入导出的图片文件；输入 PDF 不改动。
- 会创建/修改脚本旁的 venv，首次使用需要网络和写权限。

## 注意事项

- 上传压缩包内的 `.extract_pdf_images_venv` 是环境文件而非待编写手册的自有脚本。
- 推荐使用 LauncherOnOS `register`，避免把脚本复制到不适合创建 venv 的安装目录。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/extract_pdf_images.py`。
- 源文件 SHA-256：`581f5e0d98867091696679ce434d1c0b94abe2c8531561686d5718030b1da691`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
