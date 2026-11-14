# 日志程序二号 · Android

本项目基于 [Quillpad](https://github.com/quillpad/quillpad/tree/bd5baff4af9002f5a710020700e399572b2dd408)，保留原项目的 GPL-3.0 许可证与版权声明。应用 ID 为 `io.github.zhouandrew.journaltwo`，可和原版并存。

在笔记编辑页打开「⋮」，选择「另存为 Markdown」或「另存为 HTML」。通过 Android 系统文件选择器保存到所选位置。导出包含标题、正文或清单，有附件时导出为 ZIP，内有 note.md 或 note.html 和 attachments/。解压后打开文档，图片可直接显示，音频、视频及其他文件可从文档访问。

从本目录用 Android Studio 打开，安装 Gradle 指定的工具链和 Android SDK 37 后运行 `./gradlew :app:assembleDebug`。调试 APK 生成在 `app/build/outputs/apk/` 下。

## 位置与 WordPress

在文本笔记菜单中选择「添加当前位置」，按 Android 提示授权。坐标作为 OpenStreetMap 链接保存在正文中。普通 Markdown 和 HTML 导出都会携带该位置。

从菜单选择「导出到 WordPress」生成 HTML ZIP。将 ZIP 传到有 Python 3 且能访问 WordPress 的电脑，运行：

```bash
python3 import-wordpress.py 日志.html.zip https://andrew.local 用户名
```

按提示输入 WordPress 应用密码。导入程序创建草稿，上传附件至媒体库，并把草稿中引用的附件路径改为媒体库网址。站点拒绝某种文件类型时，导入会报错并保留已经创建的草稿；再次运行前可从终端显示的草稿 ID 检查结果。

在编辑器菜单选择「录制视频」打开 Android 系统相机。确认后，视频作为当前笔记的附件保存，可随 HTML、Markdown 或 WordPress ZIP 导出。
