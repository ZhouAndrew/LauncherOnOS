# anki-time-travel.sh — Anki 历史 PDF 回填 WordPress

> 分类：Anki 与学习 · 状态：实用工具 / 待实机验收 · 风险：高 · 启动器：register

## 功能

根据 `anki-stats-YYYY-MM-DD@HH-MM-SS.pdf` 文件名中的历史时间创建/复用 WordPress 文章和附件，设置 Anki 分类/标签、PDF 预览并校验时间戳。

## 用法

```bash
anki-time-travel.sh /absolute/path/anki-stats-2026-09-27@15-20-32.pdf
WP_PATH=/var/www/html/wordpress anki-time-travel.sh /absolute/path/file1.pdf /absolute/path/file2.pdf
```

## 参数与选项

- 一个或多个符合 `anki-stats-YYYY-MM-DD@HH-MM-SS.pdf` 的 PDF 路径；建议使用绝对路径。
- 没有实现 `--dry-run` 或 `--help`。

## 依赖与运行环境

- WordPress 根目录默认为 `/var/www/html/wordpress`（可由 `WP_PATH` 覆盖）。
- 需要 WP-CLI `wp`、GNU `date`、数据库访问权限，以及 `sed`、`mktemp`、`cp`、`touch` 等。

## 输出与副作用

- 创建或更新文章/媒体记录；设置 Anki 分类和标签。
- 直接执行 `wp db query` 更新文章及附件创建/修改时间；刷新缓存。
- 重复执行尽可能复用同标题/时间的文章与相同媒体路径的附件。

## 注意事项

- 会直接修改 WordPress 数据库，先备份数据库与上传目录。
- 脚本先进入 WordPress 目录，使用相对 PDF 路径可能找不到源文件；优先绝对路径。
- 不是对 WordPress 进行普通“日期排序”，而是实际回填历史记录。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/anki-time-travel.sh`。
- 源文件 SHA-256：`08cafaed6a8f48114e08950e0ffbfe3482749d8b0d7d8a7997425fc56a3b2085`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
