# 日志三号

独立的 Android 本地备忘录。打开后可从文件夹进入备忘录列表，也可直接新建。新建后光标位于正文，首行用于列表标题。文字会自动保存。

- 列表支持搜索、置顶、移动和最近删除。长按条目可打开操作菜单。
- 正文工具栏提供标题格式、可勾选清单和附件。照片与视频插在光标位置，已插入的视频可在正文区域点播。系统相机支持情况由设备决定。
- 在编辑页通过「更多」导出 HTML 或 Markdown ZIP，包含原始附件及其相对路径。
- 此版本的数据保存在设备内，卸载应用会删除本地数据。
- 笔记、文件夹和正文存入 SQLite。首次覆盖安装会导入 0.1 的本地存档，之后的读写都走数据库。旧存档保留供恢复，媒体文件原位复用。

## 构建

使用 Linux、JDK 17 或更新版本、Android SDK Platform 35 和 Build Tools 35.0.0。设置 `ANDROID_SDK_ROOT` 后运行：

```bash
./build.sh /absolute/path/Journal-Three-Android.apk
```

APK 最低支持 Android 8.0（API 26）。构建默认使用本地调试密钥，可用 `JOURNAL_KEYSTORE` 指定同一密钥以测试覆盖安装。

## SQLite 验收

先构建主 APK 以生成本地签名密钥。用同一密钥构建验收包，在 Android 模拟器或测试设备中运行：

```bash
./tests/build-store-acceptance.sh "$PWD/StoreAcceptance.apk"
adb install -r Journal-Three-Android.apk
adb install -r StoreAcceptance.apk
adb shell am instrument -w com.journalthree.tests/com.journalthree.StoreAcceptance
```

测试在独立的临时目录中模拟旧版笔记，检查迁移、编辑、重新打开及失败回滚。

## 0.3 编辑器预览

整篇正文共用一个 Android 文本框。照片和视频保存在正文光标处，选区和文本替换可以跨附件。系统剪贴板复制正文时只传递文字。测试同时覆盖编辑页打开、插入两类附件、跨附件替换和 SQLite 回读。

用 `JOURNAL_BUILD_PREVIEW=1` 构建主 APK 和验收 APK，主 APK 将使用独立应用 ID `com.journalthree.preview`，可与此前版本并装，数据目录独立。用原包名构建覆盖升级包时，需要使用原版本的签名密钥。

## 0.3.1 视频回归

在正文中点视频卡片开始播放。播放结束或切到后台时，播放器收起，卡片保留在原位置。运行验收需安装 FFmpeg（含 libx264），测试构建会生成一段本地 H.264 MP4，模拟点按并检查实际播放进度。

通过 GitHub Actions 或 Android 模拟器跑完整预览版验收时，请用 `JOURNAL_BUILD_PREVIEW=1` 分别构建 `Journal-Three-Preview.apk` 与 `StoreAcceptance.apk` 到同一目录，再执行 `./tests/android-acceptance.sh /absolute/path/to/apks`。
